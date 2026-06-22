#include <folly/dynamic.h>
#include <folly/json.h>
#include <folly/io/IOBuf.h>
#include <folly/hash/Hash.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

using folly::dynamic;
using folly::toJson;
using folly::parseJson;
using folly::IOBuf;

struct Timer {
    std::chrono::high_resolution_clock::time_point start;
    Timer() : start(std::chrono::high_resolution_clock::now()) {}
    double elapsed_ns() {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double, std::nano>(end - start).count();
    }
    double elapsed_ms() { return elapsed_ns() / 1000000.0; }
    double elapsed_s() { return elapsed_ns() / 1000000000.0; }
};

void write_results(const std::string& path, const dynamic& data) {
    std::ofstream f(path);
    f << toJson(data);
    f.close();
    std::cerr << "[CODEC] Results saved to " << path << std::endl;
}

double bench_json_parse(int ops) {
    std::string json_str = "{\"name\":\"benchmark\",\"values\":[1,2,3,4,5],\"nested\":{\"key\":\"val\",\"num\":42}}";
    Timer t;
    for (int i = 0; i < ops; i++) {
        auto parsed = parseJson(json_str);
    }
    return ops / t.elapsed_s();
}

double bench_json_serialize(int ops) {
    std::string json_str = "{\"name\":\"benchmark\",\"values\":[1,2,3,4,5],\"nested\":{\"key\":\"val\",\"num\":42}}";
    auto parsed = parseJson(json_str);
    Timer t;
    for (int i = 0; i < ops; i++) {
        std::string out = toJson(parsed);
    }
    return ops / t.elapsed_s();
}

double bench_iobuf_create_append(int ops) {
    Timer t;
    for (int i = 0; i < ops; i++) {
        auto buf = IOBuf::create(1024);
        buf->append("abcdefghij", 10);
    }
    return ops / t.elapsed_s();
}

double bench_iobuf_clone(int ops) {
    auto buf = IOBuf::create(1024);
    buf->append("abcdefghij_data_for_clone_benchmark", 34);
    Timer t;
    for (int i = 0; i < ops; i++) {
        auto clone = buf->clone();
    }
    return ops / t.elapsed_s();
}

double bench_hash_fnv32(int ops) {
    std::string data = "benchmark_hash_input_string_for_folly_hash_test";
    Timer t;
    for (int i = 0; i < ops; i++) {
        folly::hash::fnv32_buf(data.data(), data.size());
    }
    return ops / t.elapsed_s();
}

double bench_hash_spooky128(int ops) {
    std::string data = "benchmark_hash_input_string_for_folly_spooky_hash";
    Timer t;
    for (int i = 0; i < ops; i++) {
        folly::hash::spookyHashV128(data.data(), data.size(), 0, 0);
    }
    return ops / t.elapsed_s();
}

int main(int argc, char* argv[]) {
    std::string output_path = "results/benchmark_codec.json";
    int iterations = 1;
    int ops_per_iter = 10000;
    std::string version = "unknown";
    std::string architecture = "unknown";

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--output" && i + 1 < argc) { output_path = argv[++i]; }
        else if (arg == "--iterations" && i + 1 < argc) { iterations = std::stoi(argv[++i]); }
        else if (arg == "--ops-per-iter" && i + 1 < argc) { ops_per_iter = std::stoi(argv[++i]); }
        else if (arg == "--version" && i + 1 < argc) { version = argv[++i]; }
        else if (arg == "--architecture" && i + 1 < argc) { architecture = argv[++i]; }
    }

    dynamic results = dynamic::array;

    struct BenchItem {
        std::string op_name;
        std::string category;
        double (*func)(int);
        std::string result_key;
    };

    std::vector<BenchItem> benches = {
        {"json_parse", "codec", bench_json_parse, "json_parse_ops_per_sec"},
        {"json_serialize", "codec", bench_json_serialize, "json_serialize_ops_per_sec"},
        {"iobuf_create_append", "buffer", bench_iobuf_create_append, "iobuf_ops_per_sec"},
        {"iobuf_clone", "buffer", bench_iobuf_clone, "iobuf_clone_ops_per_sec"},
        {"hash_fnv32", "hash", bench_hash_fnv32, "hash_fnv32_ops_per_sec"},
        {"hash_spooky128", "hash", bench_hash_spooky128, "hash_spooky_ops_per_sec"},
    };

    for (auto& bench : benches) {
        std::cerr << "[CODEC] Benchmarking " << bench.op_name << "..." << std::endl;
        double total_ops = 0;
        for (int iter = 0; iter < iterations; iter++) {
            double ops_sec = bench.func(ops_per_iter);
            total_ops += ops_sec;
        }
        double avg_ops = total_ops / iterations;
        double avg_lat = 1000.0 / avg_ops;

        dynamic item = dynamic::object;
        item("operation", bench.op_name);
        item("category", bench.category);
        item("ops_per_sec", avg_ops);
        item("avg_latency_ms", avg_lat);
        item(bench.result_key, avg_ops);
        item("iterations", iterations);
        item("ops_per_iter", ops_per_iter);
        results.push_back(item);
    }

    dynamic output = dynamic::object;
    output("benchmark", "codec_micro_operations");
    output("description", "Folly serialization/codec micro benchmarks: JSON parse/serialize, IOBuf, hash functions");
    output("reference", "https://github.com/facebook/folly");
    output("software", "folly");
    output("version", version);
    output("architecture", architecture);
    output("timestamp", std::to_string(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now())));
    output("performance_metrics", dynamic::object
        ("json_parse_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "JSON parsing throughput"))
        ("json_serialize_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "JSON serialization throughput"))
        ("iobuf_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "IOBuf create+append throughput"))
        ("iobuf_clone_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "IOBuf clone throughput"))
        ("hash_fnv32_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "FNV32 hash throughput"))
        ("hash_spooky_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "SpookyHash128 throughput"))
    );
    output("dataset_info", dynamic::object
        ("name", "synthetic_json_buffers_strings")
        ("size", "variable (JSON ~80 bytes, buffer 1024 bytes)")
        ("source", "in-memory_generated")
    );
    output("results", results);

    write_results(output_path, output);
    return 0;
}
