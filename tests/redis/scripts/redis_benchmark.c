#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#include <hiredis/hiredis.h>

static int g_port = 16379;
static int g_num_ops = 100000;
static size_t g_value_size = 256;
static int g_iterations = 1;

static void gen_key(char *buf, size_t bufsize, int i) {
    snprintf(buf, bufsize, "bench:key:%012d", i);
}

static void gen_value(char *buf, size_t bufsize, size_t size, int seed) {
    if (size <= 1) { buf[0] = '\0'; return; }
    size_t write_len = size < bufsize ? size : bufsize - 1;
    for (size_t j = 0; j < write_len; j++) {
        buf[j] = 'a' + ((seed + (int)j) % 26);
    }
    buf[write_len - 1] = '\0';
}

static redisContext *connect_redis(int port) {
    redisContext *ctx = redisConnect("127.0.0.1", port);
    if (ctx == NULL || ctx->err) {
        if (ctx) {
            fprintf(stderr, "Connection error: %s\n", ctx->errstr);
            redisFree(ctx);
        } else {
            fprintf(stderr, "Connection error: can't allocate redis context\n");
        }
        return NULL;
    }
    return ctx;
}

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void flush_redis(redisContext *ctx) {
    redisReply *reply = redisCommand(ctx, "FLUSHALL");
    if (reply) freeReplyObject(reply);
}

struct KVWorkloadResult {
    char workload[64];
    int num_ops;
    size_t value_size;
    double total_ops_per_sec;
    double write_ops_per_sec;
    double read_ops_per_sec;
    double write_speed_mbs;
    double read_speed_mbs;
    double write_latency_us;
    double read_latency_us;
    double total_time_s;
};

static struct KVWorkloadResult run_set_only(redisContext *ctx, int num_ops, size_t value_size) {
    struct KVWorkloadResult r = {0};
    strncpy(r.workload, "set_only", sizeof(r.workload) - 1);
    r.num_ops = num_ops;
    r.value_size = value_size;

    char key[64], value[1024];
    double start = get_time_sec();

    for (int i = 0; i < num_ops; i++) {
        gen_key(key, sizeof(key), i);
        gen_value(value, sizeof(value), value_size, i);
        redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
        if (reply) freeReplyObject(reply);
    }

    double end = get_time_sec();
    double elapsed = end - start;

    r.total_ops_per_sec = num_ops / elapsed;
    r.write_ops_per_sec = num_ops / elapsed;
    r.write_speed_mbs = (num_ops * value_size / (1024.0 * 1024.0)) / elapsed;
    r.write_latency_us = (elapsed / num_ops) * 1e6;
    r.total_time_s = elapsed;

    return r;
}

static struct KVWorkloadResult run_get_only(redisContext *ctx, int num_ops, size_t value_size) {
    struct KVWorkloadResult r = {0};
    strncpy(r.workload, "get_only", sizeof(r.workload) - 1);
    r.num_ops = num_ops;
    r.value_size = value_size;

    char key[64], value[1024];
    flush_redis(ctx);

    for (int i = 0; i < num_ops; i++) {
        gen_key(key, sizeof(key), i);
        gen_value(value, sizeof(value), value_size, i);
        redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
        if (reply) freeReplyObject(reply);
    }

    double start = get_time_sec();

    for (int i = 0; i < num_ops; i++) {
        gen_key(key, sizeof(key), i);
        redisReply *reply = redisCommand(ctx, "GET %s", key);
        if (reply) freeReplyObject(reply);
    }

    double end = get_time_sec();
    double elapsed = end - start;

    r.total_ops_per_sec = num_ops / elapsed;
    r.read_ops_per_sec = num_ops / elapsed;
    r.read_speed_mbs = (num_ops * value_size / (1024.0 * 1024.0)) / elapsed;
    r.read_latency_us = (elapsed / num_ops) * 1e6;
    r.total_time_s = elapsed;

    return r;
}

static struct KVWorkloadResult run_mixed_workload(redisContext *ctx, int num_ops,
                                                   size_t value_size, double read_ratio,
                                                   const char *wl_name) {
    struct KVWorkloadResult r = {0};
    strncpy(r.workload, wl_name, sizeof(r.workload) - 1);
    r.num_ops = num_ops;
    r.value_size = value_size;

    char key[64], value[1024];
    flush_redis(ctx);

    for (int i = 0; i < num_ops; i++) {
        gen_key(key, sizeof(key), i);
        gen_value(value, sizeof(value), value_size, i);
        redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
        if (reply) freeReplyObject(reply);
    }

    double start = get_time_sec();
    int total_writes = 0;
    int total_reads = 0;

    for (int i = 0; i < num_ops; i++) {
        if ((double)(i % 100) / 100.0 < read_ratio) {
            gen_key(key, sizeof(key), i % num_ops);
            redisReply *reply = redisCommand(ctx, "GET %s", key);
            if (reply) freeReplyObject(reply);
            total_reads++;
        } else {
            gen_key(key, sizeof(key), i % num_ops);
            gen_value(value, sizeof(value), value_size, i + num_ops);
            redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
            if (reply) freeReplyObject(reply);
            total_writes++;
        }
    }

    double end = get_time_sec();
    double elapsed = end - start;

    r.total_ops_per_sec = num_ops / elapsed;
    r.total_time_s = elapsed;

    if (total_writes > 0) {
        double write_share = (double)total_writes / num_ops;
        r.write_ops_per_sec = total_writes / (elapsed * write_share);
        r.write_speed_mbs = (total_writes * value_size / (1024.0 * 1024.0)) / elapsed;
        r.write_latency_us = (elapsed / num_ops) * 1e6;
    }
    if (total_reads > 0) {
        double read_share = (double)total_reads / num_ops;
        r.read_ops_per_sec = total_reads / (elapsed * read_share);
        r.read_speed_mbs = (total_reads * value_size / (1024.0 * 1024.0)) / elapsed;
        r.read_latency_us = (elapsed / num_ops) * 1e6;
    }

    return r;
}

struct CmdResult {
    char command[32];
    double latency_us;
    double ops_per_sec;
    double speed_mbs;
};

static struct CmdResult run_single_cmd(redisContext *ctx, const char *cmd_name,
                                        int num_ops, size_t value_size) {
    struct CmdResult r = {0};
    strncpy(r.command, cmd_name, sizeof(r.command) - 1);

    char key[64], value[1024], field[64];
    flush_redis(ctx);

    for (int i = 0; i < num_ops; i++) {
        gen_key(key, sizeof(key), i);
        gen_value(value, sizeof(value), value_size, i);
        redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
        if (reply) freeReplyObject(reply);
    }

    double start = get_time_sec();
    int actual_ops = 0;

    if (strcmp(cmd_name, "SET") == 0) {
        for (int i = num_ops; i < num_ops * 2; i++) {
            gen_key(key, sizeof(key), i);
            gen_value(value, sizeof(value), value_size, i);
            redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "GET") == 0) {
        for (int i = 0; i < num_ops; i++) {
            gen_key(key, sizeof(key), i);
            redisReply *reply = redisCommand(ctx, "GET %s", key);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "DEL") == 0) {
        for (int i = num_ops; i < num_ops * 2; i++) {
            gen_key(key, sizeof(key), i);
            redisReply *reply = redisCommand(ctx, "SET %s val_del_%d", key, i);
            if (reply) freeReplyObject(reply);
        }
        start = get_time_sec();
        for (int i = num_ops; i < num_ops * 2; i++) {
            gen_key(key, sizeof(key), i);
            redisReply *reply = redisCommand(ctx, "DEL %s", key);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "LPUSH") == 0) {
        flush_redis(ctx);
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            gen_value(value, sizeof(value), value_size, i);
            redisReply *reply = redisCommand(ctx, "LPUSH bench:list %s", value);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "LRANGE_100") == 0) {
        flush_redis(ctx);
        for (int i = 0; i < 500; i++) {
            gen_value(value, sizeof(value), value_size, i);
            redisReply *reply = redisCommand(ctx, "LPUSH bench:lrange %s", value);
            if (reply) freeReplyObject(reply);
        }
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            redisReply *reply = redisCommand(ctx, "LRANGE bench:lrange 0 99");
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "HSET") == 0) {
        flush_redis(ctx);
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            gen_key(field, sizeof(field), i);
            gen_value(value, sizeof(value), value_size, i);
            redisReply *reply = redisCommand(ctx, "HSET bench:hash %s %s", field, value);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "SADD") == 0) {
        flush_redis(ctx);
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            gen_key(key, sizeof(key), i);
            redisReply *reply = redisCommand(ctx, "SADD bench:set %s", key);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "ZADD") == 0) {
        flush_redis(ctx);
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            gen_key(key, sizeof(key), i);
            redisReply *reply = redisCommand(ctx, "ZADD bench:zset %d %s", i, key);
            if (reply) freeReplyObject(reply);
            actual_ops++;
        }
    } else if (strcmp(cmd_name, "INCR") == 0) {
        flush_redis(ctx);
        redisReply *reply = redisCommand(ctx, "SET bench:counter 0");
        if (reply) freeReplyObject(reply);
        start = get_time_sec();
        for (int i = 0; i < num_ops; i++) {
            redisReply *reply2 = redisCommand(ctx, "INCR bench:counter");
            if (reply2) freeReplyObject(reply2);
            actual_ops++;
        }
    }

    double end = get_time_sec();
    double elapsed = end - start;

    if (actual_ops > 0) {
        r.latency_us = (elapsed / actual_ops) * 1e6;
        r.ops_per_sec = actual_ops / elapsed;
        if (strcmp(cmd_name, "DEL") == 0 || strcmp(cmd_name, "INCR") == 0 ||
            strcmp(cmd_name, "SADD") == 0 || strcmp(cmd_name, "ZADD") == 0) {
            r.speed_mbs = 0;
        } else {
            r.speed_mbs = (actual_ops * value_size / (1024.0 * 1024.0)) / elapsed;
        }
    }

    return r;
}

struct PipelineResult {
    int pipeline_size;
    double ops_per_sec;
    double latency_per_cmd_us;
    double speed_mbs;
    double total_time_s;
};

static struct PipelineResult run_pipeline(redisContext *ctx, int num_ops,
                                           size_t value_size, int pipeline_size) {
    struct PipelineResult r = {0};
    r.pipeline_size = pipeline_size;

    char key[64], value[1024];
    flush_redis(ctx);

    int num_batches = num_ops / pipeline_size;
    double start = get_time_sec();

    for (int b = 0; b < num_batches; b++) {
        for (int j = 0; j < pipeline_size; j++) {
            int idx = b * pipeline_size + j;
            gen_key(key, sizeof(key), idx);
            gen_value(value, sizeof(value), value_size, idx);
            redisAppendCommand(ctx, "SET %s %s", key, value);
        }
        for (int j = 0; j < pipeline_size; j++) {
            redisReply *reply;
            redisGetReply(ctx, &reply);
            if (reply) freeReplyObject(reply);
        }
    }

    double end = get_time_sec();
    double elapsed = end - start;
    int total_ops = num_batches * pipeline_size;

    r.ops_per_sec = total_ops / elapsed;
    r.latency_per_cmd_us = (elapsed / total_ops) * 1e6;
    r.speed_mbs = (total_ops * value_size / (1024.0 * 1024.0)) / elapsed;
    r.total_time_s = elapsed;

    return r;
}

struct MtResult {
    int clients;
    double write_ops_per_sec;
    double read_ops_per_sec;
    double total_time_s;
};

static void *mt_write_thread(void *arg) {
    struct {
        int port;
        int num_ops;
        size_t value_size;
        int thread_id;
        int offset;
    } *params = (void *)arg;

    redisContext *ctx = connect_redis(params->port);
    if (!ctx) return NULL;

    char key[64], value[1024];
    for (int i = 0; i < params->num_ops; i++) {
        int idx = params->offset + i;
        gen_key(key, sizeof(key), idx);
        gen_value(value, sizeof(value), params->value_size, idx);
        redisReply *reply = redisCommand(ctx, "SET %s %s", key, value);
        if (reply) freeReplyObject(reply);
    }

    redisFree(ctx);
    return NULL;
}

static struct MtResult run_mt_bench(int port, int num_ops_per_client,
                                      int num_clients, size_t value_size) {
    struct MtResult r = {0};
    r.clients = num_clients;

    redisContext *ctx = connect_redis(port);
    if (!ctx) { return r; }
    flush_redis(ctx);

    struct {
        int port;
        int num_ops;
        size_t value_size;
        int thread_id;
        int offset;
    } *thread_params = malloc(sizeof(*thread_params) * num_clients);

    pthread_t *threads = malloc(sizeof(pthread_t) * num_clients);

    double start = get_time_sec();

    for (int t = 0; t < num_clients; t++) {
        thread_params[t].port = port;
        thread_params[t].num_ops = num_ops_per_client;
        thread_params[t].value_size = value_size;
        thread_params[t].thread_id = t;
        thread_params[t].offset = t * num_ops_per_client;
        pthread_create(&threads[t], NULL, mt_write_thread, &thread_params[t]);
    }

    for (int t = 0; t < num_clients; t++) {
        pthread_join(threads[t], NULL);
    }

    double end = get_time_sec();
    double elapsed = end - start;
    int total_writes = num_clients * num_ops_per_client;

    r.write_ops_per_sec = total_writes / elapsed;
    r.total_time_s = elapsed;

    double read_start = get_time_sec();
    int total_reads = total_writes / 2;
    char key[64];
    for (int i = 0; i < total_reads; i++) {
        gen_key(key, sizeof(key), i);
        redisReply *reply = redisCommand(ctx, "GET %s", key);
        if (reply) freeReplyObject(reply);
    }
    double read_end = get_time_sec();
    r.read_ops_per_sec = total_reads / (read_end - read_start);

    redisFree(ctx);
    free(thread_params);
    free(threads);

    return r;
}

static void write_kv_json(const char *output_path,
                           struct KVWorkloadResult *results, int num_workloads,
                           int num_ops, size_t value_size, int iterations) {
    FILE *fp = fopen(output_path, "w");
    if (!fp) { fprintf(stderr, "Cannot open %s\n", output_path); return; }

    fprintf(fp, "{\n");
    fprintf(fp, "  \"benchmark\": \"kv_store\",\n");
    fprintf(fp, "  \"description\": \"Redis in-memory key-value store throughput across workload patterns on ARM64\",\n");
    fprintf(fp, "  \"reference\": \"https://github.com/redis/redis\",\n");
    fprintf(fp, "  \"software\": \"redis\",\n");
    fprintf(fp, "  \"version\": \"%s\",\n", version_str);
    fprintf(fp, "  \"architecture\": \"arm64\",\n");
    fprintf(fp, "  \"performance_metrics\": {\n");
    fprintf(fp, "    \"total_ops_per_sec\": {\"unit\": \"ops/s\", \"description\": \"Total operations per second\"},\n");
    fprintf(fp, "    \"write_ops_per_sec\": {\"unit\": \"ops/s\", \"description\": \"Write operations per second\"},\n");
    fprintf(fp, "    \"read_ops_per_sec\": {\"unit\": \"ops/s\", \"description\": \"Read operations per second\"},\n");
    fprintf(fp, "    \"write_speed_mbs\": {\"unit\": \"MB/s\", \"description\": \"Write throughput in megabytes per second\"},\n");
    fprintf(fp, "    \"read_speed_mbs\": {\"unit\": \"MB/s\", \"description\": \"Read throughput in megabytes per second\"}\n");
    fprintf(fp, "  },\n");
    fprintf(fp, "  \"parameters\": {\n");
    fprintf(fp, "    \"num_ops\": %d,\n", num_ops);
    fprintf(fp, "    \"value_size_bytes\": %zu,\n", value_size);
    fprintf(fp, "    \"iterations\": %d\n", iterations);
    fprintf(fp, "  },\n");
    fprintf(fp, "  \"results_summary\": {\n");
    for (int i = 0; i < num_workloads; i++) {
        struct KVWorkloadResult *wr = &results[i];
        fprintf(fp, "    \"%s\": {\n", wr->workload);
        fprintf(fp, "      \"total_ops_per_sec\": %.2f,\n", wr->total_ops_per_sec);
        fprintf(fp, "      \"write_ops_per_sec\": %.2f,\n", wr->write_ops_per_sec);
        fprintf(fp, "      \"read_ops_per_sec\": %.2f,\n", wr->read_ops_per_sec);
        fprintf(fp, "      \"write_speed_mbs\": %.2f,\n", wr->write_speed_mbs);
        fprintf(fp, "      \"read_speed_mbs\": %.2f,\n", wr->read_speed_mbs);
        fprintf(fp, "      \"write_latency_us\": %.2f,\n", wr->write_latency_us);
        fprintf(fp, "      \"read_latency_us\": %.2f,\n", wr->read_latency_us);
        fprintf(fp, "      \"total_time_s\": %.6f\n", wr->total_time_s);
        fprintf(fp, "    }%s\n", i < num_workloads - 1 ? "," : "");
    }
    fprintf(fp, "  }\n");
    fprintf(fp, "}\n");
    fclose(fp);
}

static void write_micro_json(const char *output_path,
                              struct CmdResult *cmd_results, int num_cmds,
                              struct PipelineResult *pipe_results, int num_pipes,
                              struct MtResult *mt_results, int num_mt,
                              int num_ops, size_t value_size, int iterations,
                              int max_threads) {
    FILE *fp = fopen(output_path, "w");
    if (!fp) { fprintf(stderr, "Cannot open %s\n", output_path); return; }

    fprintf(fp, "{\n");
    fprintf(fp, "  \"benchmark\": \"micro_operations\",\n");
    fprintf(fp, "  \"description\": \"Redis micro benchmarks: single command latency, pipeline, multi-client scaling on ARM64\",\n");
    fprintf(fp, "  \"reference\": \"https://github.com/redis/redis\",\n");
    fprintf(fp, "  \"software\": \"redis\",\n");
    fprintf(fp, "  \"version\": \"%s\",\n", version_str);
    fprintf(fp, "  \"architecture\": \"arm64\",\n");
    fprintf(fp, "  \"performance_metrics\": {\n");
    fprintf(fp, "    \"ops_per_sec\": {\"unit\": \"ops/s\", \"description\": \"Operations per second\"},\n");
    fprintf(fp, "    \"latency_us\": {\"unit\": \"us\", \"description\": \"Single operation latency\"},\n");
    fprintf(fp, "    \"speed_mbs\": {\"unit\": \"MB/s\", \"description\": \"Throughput in megabytes per second\"}\n");
    fprintf(fp, "  },\n");
    fprintf(fp, "  \"parameters\": {\n");
    fprintf(fp, "    \"num_ops\": %d,\n", num_ops);
    fprintf(fp, "    \"value_size_bytes\": %zu,\n", value_size);
    fprintf(fp, "    \"iterations\": %d,\n", iterations);
    fprintf(fp, "    \"max_threads\": %d\n", max_threads);
    fprintf(fp, "  },\n");
    fprintf(fp, "  \"results\": {\n");

    fprintf(fp, "    \"single_commands\": {\n");
    for (int i = 0; i < num_cmds; i++) {
        struct CmdResult *cr = &cmd_results[i];
        fprintf(fp, "      \"%s\": {\n", cr->command);
        fprintf(fp, "        \"latency_us\": %.2f,\n", cr->latency_us);
        fprintf(fp, "        \"ops_per_sec\": %.2f,\n", cr->ops_per_sec);
        fprintf(fp, "        \"speed_mbs\": %.2f\n", cr->speed_mbs);
        fprintf(fp, "      }%s\n", i < num_cmds - 1 ? "," : "");
    }
    fprintf(fp, "    },\n");

    fprintf(fp, "    \"pipeline\": {\n");
    for (int i = 0; i < num_pipes; i++) {
        struct PipelineResult *pr = &pipe_results[i];
        fprintf(fp, "      \"pipeline_%d\": {\n", pr->pipeline_size);
        fprintf(fp, "        \"ops_per_sec\": %.2f,\n", pr->ops_per_sec);
        fprintf(fp, "        \"latency_per_cmd_us\": %.2f,\n", pr->latency_per_cmd_us);
        fprintf(fp, "        \"speed_mbs\": %.2f,\n", pr->speed_mbs);
        fprintf(fp, "        \"total_time_s\": %.6f\n", pr->total_time_s);
        fprintf(fp, "      }%s\n", i < num_pipes - 1 ? "," : "");
    }
    fprintf(fp, "    },\n");

    fprintf(fp, "    \"multithread_scaling\": {\n");
    for (int i = 0; i < num_mt; i++) {
        struct MtResult *mr = &mt_results[i];
        fprintf(fp, "      \"clients_%d\": {\n", mr->clients);
        fprintf(fp, "        \"write_ops_per_sec\": %.2f,\n", mr->write_ops_per_sec);
        fprintf(fp, "        \"read_ops_per_sec\": %.2f,\n", mr->read_ops_per_sec);
        fprintf(fp, "        \"total_time_s\": %.6f\n", mr->total_time_s);
        fprintf(fp, "      }%s\n", i < num_mt - 1 ? "," : "");
    }
    fprintf(fp, "    }\n");

    fprintf(fp, "  }\n");
    fprintf(fp, "}\n");
    fclose(fp);
}

int main(int argc, char *argv[]) {
    if (argc < 4) {
        fprintf(stderr, "Usage: %s <mode> <iterations> <output_json> [num_ops] [value_size] [port]\n", argv[0]);
        fprintf(stderr, "  mode: kv | micro\n");
        fprintf(stderr, "  Defaults: num_ops=100000, value_size=256, port=16379\n");
        return 1;
    }

    const char *mode = argv[1];
    g_iterations = atoi(argv[2]);
    const char *output_path = argv[3];
    g_num_ops = (argc >= 5) ? atoi(argv[4]) : 100000;
    g_value_size = (argc >= 6) ? (size_t)atol(argv[5]) : 256;
    g_port = (argc >= 7) ? atoi(argv[6]) : 16379;

    const char* env_version = getenv("SOFTWARE_VERSION");
    const char* version_str = env_version ? env_version : "8.6.4";

    srand(42);

    redisContext *ctx = connect_redis(g_port);
    if (!ctx) {
        fprintf(stderr, "Cannot connect to Redis on port %d\n", g_port);
        return 1;
    }

    if (strcmp(mode, "kv") == 0) {
        flush_redis(ctx);

        struct KVWorkloadResult workloads[5];

        workloads[0] = run_set_only(ctx, g_num_ops, g_value_size);
        flush_redis(ctx);

        workloads[1] = run_get_only(ctx, g_num_ops, g_value_size);
        flush_redis(ctx);

        workloads[2] = run_mixed_workload(ctx, g_num_ops, g_value_size, 0.5, "mixed_50_50");
        flush_redis(ctx);

        workloads[3] = run_mixed_workload(ctx, g_num_ops, g_value_size, 0.8, "mixed_80_20");
        flush_redis(ctx);

        workloads[4] = run_mixed_workload(ctx, g_num_ops, g_value_size, 0.95, "mixed_95_5");
        flush_redis(ctx);

        write_kv_json(output_path, workloads, 5, g_num_ops, g_value_size, g_iterations);
        fprintf(stdout, "[KV] Benchmark complete, output: %s\n", output_path);

    } else if (strcmp(mode, "micro") == 0) {
        const char *cmds[] = {"SET", "GET", "DEL", "LPUSH", "LRANGE_100",
                              "HSET", "SADD", "ZADD", "INCR"};
        int num_cmds = 9;
        struct CmdResult cmd_results[9];

        for (int i = 0; i < num_cmds; i++) {
            cmd_results[i] = run_single_cmd(ctx, cmds[i], g_num_ops, g_value_size);
            fprintf(stdout, "[MICRO] %s: %.2f us, %.2f ops/s\n",
                    cmds[i], cmd_results[i].latency_us, cmd_results[i].ops_per_sec);
        }

        int pipe_sizes[] = {10, 50, 100, 500};
        int num_pipes = 4;
        struct PipelineResult pipe_results[4];

        for (int i = 0; i < num_pipes; i++) {
            pipe_results[i] = run_pipeline(ctx, g_num_ops, g_value_size, pipe_sizes[i]);
            fprintf(stdout, "[MICRO] Pipeline-%d: %.2f ops/s\n",
                    pipe_sizes[i], pipe_results[i].ops_per_sec);
        }

        int max_threads = (int)pthread_getconcurrency();
        if (max_threads == 0) max_threads = 4;
        long nproc = sysconf(_SC_NPROCESSORS_ONLN);
        if (nproc > 0) max_threads = (int)nproc;

        int client_counts[] = {1, 2, 4, 8, 16};
        int num_mt_counts = 5;
        if (max_threads >= 32) { client_counts[4] = 32; }
        else { client_counts[4] = max_threads; }

        int ops_per_client = g_num_ops / client_counts[4];
        if (ops_per_client < 1000) ops_per_client = 1000;

        struct MtResult mt_results[5];
        for (int i = 0; i < num_mt_counts; i++) {
            mt_results[i] = run_mt_bench(g_port, ops_per_client,
                                         client_counts[i], g_value_size);
            fprintf(stdout, "[MICRO] Clients-%d: %.2f write ops/s\n",
                    client_counts[i], mt_results[i].write_ops_per_sec);
        }

        write_micro_json(output_path, cmd_results, num_cmds,
                         pipe_results, num_pipes,
                         mt_results, num_mt_counts,
                         g_num_ops, g_value_size, g_iterations,
                         max_threads);
        fprintf(stdout, "[MICRO] Benchmark complete, output: %s\n", output_path);

    } else {
        fprintf(stderr, "Unknown mode: %s\n", mode);
        redisFree(ctx);
        return 1;
    }

    redisFree(ctx);
    return 0;
}