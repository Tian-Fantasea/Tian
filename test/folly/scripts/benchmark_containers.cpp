#include <folly/FBString.h>
#include <folly/container/F14Map.h>
#include <folly/dynamic.h>
#include <folly/json.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

using folly::fbstring;
using folly::F14FastMap;
using folly::dynamic;
using folly::toJson;

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
    std::cerr << "[CONTAINERS] Results saved to " << path << std::endl;
}

double bench_fbstring_append(int ops) {
    fbstring s;
    Timer t;
    for (int i = 0; i < ops; i++) {
        s.append("abcdefghij");
    }
    return ops / t.elapsed_s();
}

double bench_fbstring_find(int ops) {
    fbstring base;
    for (int i = 0; i < 100; i++) base.append("abcdefghij_");
    Timer t;
    for (int i = 0; i < ops; i++) {
        base.find("defg");
    }
    return ops / t.elapsed_s();
}

double bench_std_string_append(int ops) {
    std::string s;
    Timer t;
    for (int i = 0; i < ops; i++) {
        s.append("abcdefghij");
    }
    return ops / t.elapsed_s();
}

double bench_f14_insert(int ops) {
    F14FastMap<std::string, int> map;
    Timer t;
    for (int i = 0; i < ops; i++) {
        map.insert({"key_" + std::to_string(i), i});
    }
    return ops / t.elapsed_s();
}

double bench_f14_find(int ops) {
    F14FastMap<std::string, int> map;
    for (int i = 0; i < ops; i++) map.insert({"key_" + std::to_string(i), i});
    Timer t;
    for (int i = 0; i < ops; i++) {
        map.find("key_" + std::to_string(i % ops));
    }
    return ops / t.elapsed_s();
}

double bench_f14_erase(int ops) {
    F14FastMap<std::string, int> map;
    for (int i = 0; i < ops; i++) map.insert({"key_" + std::to_string(i), i});
    Timer t;
    for (int i = 0; i < ops; i++) {
        map.erase("key_" + std::to_string(i));
    }
    return ops / t.elapsed_s();
}

int main(int argc, char* argv[]) {
    std::string output_path = "results/benchmark_containers.json";
    int iterations = 1;
    int ops_per_iter = 100000;
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
        std::string container;
        double (*func)(int);
    };

    std::vector<BenchItem> benches = {
        {"fbstring_append", "fbstring", bench_fbstring_append},
        {"fbstring_find", "fbstring", bench_fbstring_find},
        {"std_string_append", "std::string", bench_std_string_append},
        {"f14fastmap_insert", "F14FastMap", bench_f14_insert},
        {"f14fastmap_find", "F14FastMap", bench_f14_find},
        {"f14fastmap_erase", "F14FastMap", bench_f14_erase},
    };

    for (auto& bench : benches) {
        std::cerr << "[CONTAINERS] Benchmarking " << bench.op_name << "..." << std::endl;
        double total_ops = 0;
        double total_lat = 0;
        for (int iter = 0; iter < iterations; iter++) {
            double ops_sec = bench.func(ops_per_iter);
            double avg_lat_ms = 1000.0 / ops_sec;
            total_ops += ops_sec;
            total_lat += avg_lat_ms;
        }
        double avg_ops = total_ops / iterations;
        double avg_lat = total_lat / iterations;

        dynamic item = dynamic::object;
        item("operation", bench.op_name);
        item("container_type", bench.container);
        item("ops_per_sec", avg_ops);
        item("avg_latency_ms", avg_lat);
        item("iterations", iterations);
        item("ops_per_iter", ops_per_iter);

        if (bench.container == "F14FastMap") {
            item("f14_ops_per_sec", avg_ops);
        }

        results.push_back(item);
    }

    dynamic output = dynamic::object;
    output("benchmark", "containers_throughput");
    output("description", "Folly core container performance: fbstring, F14FastMap vs std::string baseline");
    output("reference", "https://github.com/facebook/folly");
    output("software", "folly");
    output("version", version);
    output("architecture", architecture);
    output("timestamp", std::to_string(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now())));
    output("performance_metrics", dynamic::object
        ("ops_per_sec", dynamic::object("unit", "ops/sec")("description", "Operations per second"))
        ("f14_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "F14FastMap operations per second"))
    );
    output("dataset_info", dynamic::object
        ("name", "synthetic_strings_integers")
        ("size", "variable")
        ("source", "in-memory_generated")
    );
    output("results", results);

    write_results(output_path, output);
    return 0;
}
