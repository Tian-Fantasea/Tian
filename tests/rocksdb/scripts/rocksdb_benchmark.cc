#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <ctime>
#include <vector>
#include <thread>
#include <string>
#include <random>
#include <rocksdb/db.h>
#include <rocksdb/options.h>
#include <rocksdb/slice.h>
#include <rocksdb/status.h>
#include <rocksdb/write_batch.h>

static std::string get_timestamp() {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    char buf[64];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
    return std::string(buf);
}

static std::string gen_key(int i) {
    char buf[32];
    snprintf(buf, sizeof(buf), "key_%012d", i);
    return std::string(buf);
}

static std::string gen_value(size_t size, int seed) {
    std::string val(size, '\0');
    for (size_t j = 0; j < size; j++) {
        val[j] = static_cast<char>('a' + ((seed + j) % 26));
    }
    return val;
}

struct KVResult {
    std::string workload;
    int num_ops;
    size_t value_size;
    double write_ops_per_sec;
    double read_ops_per_sec;
    double write_speed_mbs;
    double read_speed_mbs;
    double write_latency_us;
    double read_latency_us;
};

static KVResult run_kv_bench(const std::string& db_path, int num_ops,
                              size_t value_size, int iterations,
                              double read_ratio) {
    KVResult r;
    r.num_ops = num_ops;
    r.value_size = value_size;

    rocksdb::DB* db = nullptr;
    rocksdb::Options options;
    options.create_if_missing = true;
    options.error_if_exists = false;
    options.write_buffer_size = 64 * 1024 * 1024;
    options.max_open_files = -1;

    rocksdb::Status status = rocksdb::DB::Open(options, db_path, &db);
    if (!status.ok()) {
        fprintf(stderr, "DB::Open error: %s\n", status.ToString().c_str());
        r.write_ops_per_sec = 0;
        r.read_ops_per_sec = 0;
        r.write_speed_mbs = 0;
        r.read_speed_mbs = 0;
        r.write_latency_us = 0;
        r.read_latency_us = 0;
        return r;
    }

    double total_write_time = 0.0;
    double total_read_time = 0.0;
    int total_writes = 0;
    int total_reads = 0;

    for (int iter = 0; iter < iterations; iter++) {
        for (int i = 0; i < num_ops; i++) {
            std::string key = gen_key(i + iter * num_ops);
            std::string value = gen_value(value_size, i + iter);

            if (read_ratio > 0 && i > 0 && (i % 10 < (int)(read_ratio * 10))) {
                std::string existing_key = gen_key((i + iter * num_ops) / 2);
                std::string read_val;
                auto t0 = std::chrono::high_resolution_clock::now();
                db->Get(rocksdb::ReadOptions(), existing_key, &read_val);
                auto t1 = std::chrono::high_resolution_clock::now();
                total_read_time += std::chrono::duration<double>(t1 - t0).count();
                total_reads++;
            } else {
                auto t0 = std::chrono::high_resolution_clock::now();
                db->Put(rocksdb::WriteOptions(), key, value);
                auto t1 = std::chrono::high_resolution_clock::now();
                total_write_time += std::chrono::duration<double>(t1 - t0).count();
                total_writes++;
            }
        }
    }

    if (total_writes > 0) {
        double avg_write = total_write_time / total_writes;
        r.write_ops_per_sec = total_writes / total_write_time;
        r.write_speed_mbs = (total_writes * value_size / (1024.0 * 1024.0)) / total_write_time;
        r.write_latency_us = avg_write * 1e6;
    } else {
        r.write_ops_per_sec = 0;
        r.write_speed_mbs = 0;
        r.write_latency_us = 0;
    }

    if (total_reads > 0) {
        double avg_read = total_read_time / total_reads;
        r.read_ops_per_sec = total_reads / total_read_time;
        r.read_speed_mbs = (total_reads * value_size / (1024.0 * 1024.0)) / total_read_time;
        r.read_latency_us = avg_read * 1e6;
    } else {
        r.read_ops_per_sec = 0;
        r.read_speed_mbs = 0;
        r.read_latency_us = 0;
    }

    delete db;
    return r;
}

struct MicroResult {
    std::string operation;
    double latency_us;
    double ops_per_sec;
    double speed_mbs;
};

struct MtResult {
    int threads;
    double write_ops_per_sec;
    double read_ops_per_sec;
    double total_time_s;
};

static std::vector<MicroResult> run_micro_bench(const std::string& db_path,
                                                  int num_ops, size_t value_size) {
    std::vector<MicroResult> results;

    rocksdb::DB* db = nullptr;
    rocksdb::Options options;
    options.create_if_missing = true;
    options.write_buffer_size = 64 * 1024 * 1024;

    rocksdb::Status status = rocksdb::DB::Open(options, db_path, &db);
    if (!status.ok()) {
        fprintf(stderr, "DB::Open error: %s\n", status.ToString().c_str());
        return results;
    }

    for (int i = 0; i < num_ops; i++) {
        db->Put(rocksdb::WriteOptions(), gen_key(i), gen_value(value_size, i));
    }

    { // Single Get
        double total = 0.0;
        for (int i = 0; i < num_ops; i++) {
            std::string val;
            auto t0 = std::chrono::high_resolution_clock::now();
            db->Get(rocksdb::ReadOptions(), gen_key(i), &val);
            auto t1 = std::chrono::high_resolution_clock::now();
            total += std::chrono::duration<double>(t1 - t0).count();
        }
        MicroResult mr;
        mr.operation = "single_get";
        mr.latency_us = (total / num_ops) * 1e6;
        mr.ops_per_sec = num_ops / total;
        mr.speed_mbs = (num_ops * value_size / (1024.0 * 1024.0)) / total;
        results.push_back(mr);
    }

    { // Single Put
        double total = 0.0;
        for (int i = 0; i < num_ops; i++) {
            auto t0 = std::chrono::high_resolution_clock::now();
            db->Put(rocksdb::WriteOptions(), gen_key(i), gen_value(value_size, i + 100));
            auto t1 = std::chrono::high_resolution_clock::now();
            total += std::chrono::duration<double>(t1 - t0).count();
        }
        MicroResult mr;
        mr.operation = "single_put";
        mr.latency_us = (total / num_ops) * 1e6;
        mr.ops_per_sec = num_ops / total;
        mr.speed_mbs = (num_ops * value_size / (1024.0 * 1024.0)) / total;
        results.push_back(mr);
    }

    { // Delete
        double total = 0.0;
        for (int i = num_ops; i < num_ops * 2; i++) {
            db->Put(rocksdb::WriteOptions(), gen_key(i), gen_value(value_size, i));
        }
        for (int i = num_ops; i < num_ops * 2; i++) {
            auto t0 = std::chrono::high_resolution_clock::now();
            db->Delete(rocksdb::WriteOptions(), gen_key(i));
            auto t1 = std::chrono::high_resolution_clock::now();
            total += std::chrono::duration<double>(t1 - t0).count();
        }
        MicroResult mr;
        mr.operation = "single_delete";
        mr.latency_us = (total / num_ops) * 1e6;
        mr.ops_per_sec = num_ops / total;
        mr.speed_mbs = 0;
        results.push_back(mr);
    }

    { // WriteBatch
        double total = 0.0;
        int batch_size = 100;
        int num_batches = num_ops / batch_size;
        for (int b = 0; b < num_batches; b++) {
            rocksdb::WriteBatch batch;
            for (int j = 0; j < batch_size; j++) {
                int idx = b * batch_size + j + 20000;
                batch.Put(gen_key(idx), gen_value(value_size, idx));
            }
            auto t0 = std::chrono::high_resolution_clock::now();
            db->Write(rocksdb::WriteOptions(), &batch);
            auto t1 = std::chrono::high_resolution_clock::now();
            total += std::chrono::duration<double>(t1 - t0).count();
        }
        MicroResult mr;
        mr.operation = "write_batch";
        mr.latency_us = (total / num_batches) * 1e6;
        mr.ops_per_sec = (num_batches * batch_size) / total;
        mr.speed_mbs = (num_batches * batch_size * value_size / (1024.0 * 1024.0)) / total;
        results.push_back(mr);
    }

    { // Iterator Scan
        double total = 0.0;
        int scan_count = 100;
        int scanned_keys = 0;
        for (int s = 0; s < scan_count; s++) {
            auto t0 = std::chrono::high_resolution_clock::now();
            rocksdb::Iterator* it = db->NewIterator(rocksdb::ReadOptions());
            std::string start_key = gen_key(s * 100);
            it->Seek(start_key);
            int count = 0;
            while (it->Valid() && count < 100) {
                it->Next();
                count++;
            }
            scanned_keys += count;
            delete it;
            auto t1 = std::chrono::high_resolution_clock::now();
            total += std::chrono::duration<double>(t1 - t0).count();
        }
        MicroResult mr;
        mr.operation = "iterator_scan";
        mr.latency_us = (total / scan_count) * 1e6;
        mr.ops_per_sec = scanned_keys / total;
        mr.speed_mbs = (scanned_keys * value_size / (1024.0 * 1024.0)) / total;
        results.push_back(mr);
    }

    delete db;
    return results;
}

static std::vector<MtResult> run_mt_bench(const std::string& db_path,
                                            int num_ops_per_thread,
                                            int num_threads,
                                            size_t value_size) {
    std::vector<MtResult> results;

    for (int tc : {1, 2, 4, 8, num_threads}) {
        if (tc > num_threads && tc != 1) continue;

        rocksdb::DB* db = nullptr;
        rocksdb::Options options;
        options.create_if_missing = true;
        options.write_buffer_size = 64 * 1024 * 1024;

        rocksdb::Status status = rocksdb::DB::Open(options, db_path + "_mt_" + std::to_string(tc), &db);
        if (!status.ok()) {
            fprintf(stderr, "DB::Open mt error: %s\n", status.ToString().c_str());
            continue;
        }

        double total_wall = 0.0;
        int total_writes = 0;
        int total_reads = 0;
        double total_read_time = 0.0;

        auto wall_start = std::chrono::high_resolution_clock::now();

        std::vector<std::thread> threads;
        for (int t = 0; t < tc; t++) {
            threads.emplace_back([&, t]() {
                for (int i = 0; i < num_ops_per_thread; i++) {
                    int idx = t * num_ops_per_thread + i;
                    db->Put(rocksdb::WriteOptions(), gen_key(idx), gen_value(value_size, idx));
                }
            });
        }
        for (auto& th : threads) th.join();

        auto wall_end = std::chrono::high_resolution_clock::now();
        double write_wall = std::chrono::duration<double>(wall_end - wall_start).count();
        total_writes = tc * num_ops_per_thread;

        for (int i = 0; i < total_writes / 2; i++) {
            std::string val;
            auto t0 = std::chrono::high_resolution_clock::now();
            db->Get(rocksdb::ReadOptions(), gen_key(i), &val);
            auto t1 = std::chrono::high_resolution_clock::now();
            total_read_time += std::chrono::duration<double>(t1 - t0).count();
            total_reads++;
        }

        MtResult mr;
        mr.threads = tc;
        mr.write_ops_per_sec = total_writes / write_wall;
        mr.read_ops_per_sec = total_reads / total_read_time;
        mr.total_time_s = write_wall;
        results.push_back(mr);

        delete db;
    }
    return results;
}

int main(int argc, char* argv[]) {
    if (argc < 4) {
        fprintf(stderr, "Usage: %s <mode> <iterations> <output_json> [num_ops] [value_size]\n", argv[0]);
        fprintf(stderr, "  mode: kv | micro | mt\n");
        return 1;
    }

    std::string mode = argv[1];
    int iterations = atoi(argv[2]);
    std::string output_path = argv[3];
    int num_ops = 10000;
    size_t value_size = 256;
    if (argc >= 5) num_ops = atoi(argv[4]);
    if (argc >= 6) value_size = atol(argv[5]);

    const char* env_version = getenv("SOFTWARE_VERSION");
    std::string version_str = env_version ? env_version : "11.1.2";

    srand(42);

    if (mode == "kv") {
        std::string db_path = output_path + "_db_kv";
        std::remove(db_path.c_str());

        struct Workload { std::string name; double read_ratio; };
        std::vector<Workload> workloads = {
            {"write_only", 0.0},
            {"read_50_write_50", 0.5},
            {"read_80_write_20", 0.8},
            {"read_95_write_5", 0.95}
        };

        std::vector<KVResult> results;
        for (auto& wl : workloads) {
            std::string wl_db_path = db_path + "_" + wl.name;
            KVResult r = run_kv_bench(wl_db_path, num_ops, value_size, iterations, wl.read_ratio);
            r.workload = wl.name;
            results.push_back(r);
        }

        FILE* fp = fopen(output_path.c_str(), "w");
        if (!fp) { fprintf(stderr, "Cannot open %s\n", output_path.c_str()); return 1; }

        fprintf(fp, "{\n");
        fprintf(fp, "  \"benchmark\": \"kv_store\",\n");
        fprintf(fp, "  \"description\": \"RocksDB key-value store throughput across workload patterns on ARM64\",\n");
        fprintf(fp, "  \"reference\": \"https://github.com/facebook/rocksdb\",\n");
        fprintf(fp, "  \"software\": \"rocksdb\",\n");
        fprintf(fp, "  \"version\": \"%s\",\n", version_str.c_str());
        fprintf(fp, "  \"architecture\": \"arm64\",\n");
        fprintf(fp, "  \"timestamp\": \"%s\",\n", get_timestamp().c_str());
        fprintf(fp, "  \"performance_metrics\": {\n");
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
        for (size_t i = 0; i < results.size(); i++) {
            auto& r = results[i];
            fprintf(fp, "    \"%s\": {\n", r.workload.c_str());
            fprintf(fp, "      \"write_ops_per_sec\": %.2f,\n", r.write_ops_per_sec);
            fprintf(fp, "      \"read_ops_per_sec\": %.2f,\n", r.read_ops_per_sec);
            fprintf(fp, "      \"write_speed_mbs\": %.2f,\n", r.write_speed_mbs);
            fprintf(fp, "      \"read_speed_mbs\": %.2f,\n", r.read_speed_mbs);
            fprintf(fp, "      \"write_latency_us\": %.2f,\n", r.write_latency_us);
            fprintf(fp, "      \"read_latency_us\": %.2f\n", r.read_latency_us);
            fprintf(fp, "    }%s\n", i < results.size() - 1 ? "," : "");
        }
        fprintf(fp, "  }\n");
        fprintf(fp, "}\n");
        fclose(fp);

        for (auto& wl : workloads) {
            std::string wl_db_path = db_path + "_" + wl.name;
            std::remove(wl_db_path.c_str());
        }

    } else if (mode == "micro") {
        std::string db_path = output_path + "_db_micro";
        std::remove(db_path.c_str());

        auto micro_results = run_micro_bench(db_path, num_ops, value_size);
        int max_threads = static_cast<int>(std::thread::hardware_concurrency());
        if (max_threads == 0) max_threads = 4;
        auto mt_results = run_mt_bench(db_path, num_ops / max_threads, max_threads, value_size);

        FILE* fp = fopen(output_path.c_str(), "w");
        if (!fp) { fprintf(stderr, "Cannot open %s\n", output_path.c_str()); return 1; }

        fprintf(fp, "{\n");
        fprintf(fp, "  \"benchmark\": \"micro_operations\",\n");
        fprintf(fp, "  \"description\": \"RocksDB micro benchmarks: single-op latency, batch, iterator, multithread on ARM64\",\n");
        fprintf(fp, "  \"reference\": \"https://github.com/facebook/rocksdb\",\n");
        fprintf(fp, "  \"software\": \"rocksdb\",\n");
        fprintf(fp, "  \"version\": \"%s\",\n", version_str.c_str());
        fprintf(fp, "  \"architecture\": \"arm64\",\n");
        fprintf(fp, "  \"timestamp\": \"%s\",\n", get_timestamp().c_str());
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

        fprintf(fp, "    \"single_operations\": {\n");
        for (size_t i = 0; i < micro_results.size(); i++) {
            auto& r = micro_results[i];
            fprintf(fp, "      \"%s\": {\n", r.operation.c_str());
            fprintf(fp, "        \"latency_us\": %.2f,\n", r.latency_us);
            fprintf(fp, "        \"ops_per_sec\": %.2f,\n", r.ops_per_sec);
            fprintf(fp, "        \"speed_mbs\": %.2f\n", r.speed_mbs);
            fprintf(fp, "      }%s\n", i < micro_results.size() - 1 ? "," : "");
        }
        fprintf(fp, "    },\n");

        fprintf(fp, "    \"multithread_scaling\": {\n");
        for (size_t i = 0; i < mt_results.size(); i++) {
            auto& r = mt_results[i];
            fprintf(fp, "      \"threads_%d\": {\n", r.threads);
            fprintf(fp, "        \"write_ops_per_sec\": %.2f,\n", r.write_ops_per_sec);
            fprintf(fp, "        \"read_ops_per_sec\": %.2f,\n", r.read_ops_per_sec);
            fprintf(fp, "        \"total_time_s\": %.6f\n", r.total_time_s);
            fprintf(fp, "      }%s\n", i < mt_results.size() - 1 ? "," : "");
        }
        fprintf(fp, "    }\n");

        fprintf(fp, "  }\n");
        fprintf(fp, "}\n");
        fclose(fp);

        std::remove(db_path.c_str());

    } else {
        fprintf(stderr, "Unknown mode: %s\n", mode.c_str());
        return 1;
    }

    return 0;
}
