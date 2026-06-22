#include <folly/container/F14Map.h>
#include <folly/dynamic.h>
#include <folly/json.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <mutex>

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
    std::cerr << "[SCALING] Results saved to " << path << std::endl;
}

void worker_insert(F14FastMap<std::string, int>* map, std::mutex* mtx, int ops, int thread_id, int offset) {
    for (int i = 0; i < ops; i++) {
        std::string key = "key_" + std::to_string(offset + i);
        std::lock_guard<std::mutex> lock(*mtx);
        map->insert({key, thread_id});
    }
}

void worker_find(F14FastMap<std::string, int>* map, std::mutex* mtx, int ops, int total_keys) {
    for (int i = 0; i < ops; i++) {
        std::string key = "key_" + std::to_string(i % total_keys);
        std::lock_guard<std::mutex> lock(*mtx);
        map->find(key);
    }
}

int main(int argc, char* argv[]) {
    std::string output_path = "results/benchmark_scaling.json";
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

    int thread_counts[] = {1, 2, 4, 8};

    for (int tc : thread_counts) {
        int ops_per_thread = ops_per_iter / tc;
        if (ops_per_thread < 100) ops_per_thread = 100;

        std::cerr << "[SCALING] Benchmarking insert with " << tc << " threads..." << std::endl;

        double total_ops_sec = 0;
        double total_lat = 0;

        for (int iter = 0; iter < iterations; iter++) {
            F14FastMap<std::string, int> map;
            std::mutex mtx;
            Timer t;
            std::vector<std::thread> threads;
            for (int th = 0; th < tc; th++) {
                threads.emplace_back(worker_insert, &map, &mtx, ops_per_thread, th, th * ops_per_thread);
            }
            for (auto& th : threads) th.join();
            double elapsed = t.elapsed_s();
            double ops_sec = (tc * ops_per_thread) / elapsed;
            double avg_lat = elapsed * 1000.0 / (tc * ops_per_thread);
            total_ops_sec += ops_sec;
            total_lat += avg_lat;
        }

        dynamic insert_item = dynamic::object;
        insert_item("thread_count", tc);
        insert_item("mode", "insert");
        insert_item("ops_per_thread", ops_per_thread);
        insert_item("total_ops", tc * ops_per_thread * iterations);
        insert_item("total_ops_per_sec", total_ops_sec / iterations);
        insert_item("avg_latency_ms", total_lat / iterations);
        insert_item("iterations", iterations);
        results.push_back(insert_item);
    }

    int prefill = ops_per_iter * 4;
    for (int tc : thread_counts) {
        int ops_per_thread = ops_per_iter / tc;
        if (ops_per_thread < 100) ops_per_thread = 100;

        std::cerr << "[SCALING] Benchmarking find with " << tc << " threads..." << std::endl;

        double total_ops_sec = 0;
        double total_lat = 0;

        for (int iter = 0; iter < iterations; iter++) {
            F14FastMap<std::string, int> map;
            for (int i = 0; i < prefill; i++) map.insert({"key_" + std::to_string(i), i});
            std::mutex mtx;
            Timer t;
            std::vector<std::thread> threads;
            for (int th = 0; th < tc; th++) {
                threads.emplace_back(worker_find, &map, &mtx, ops_per_thread, prefill);
            }
            for (auto& th : threads) th.join();
            double elapsed = t.elapsed_s();
            double ops_sec = (tc * ops_per_thread) / elapsed;
            double avg_lat = elapsed * 1000.0 / (tc * ops_per_thread);
            total_ops_sec += ops_sec;
            total_lat += avg_lat;
        }

        dynamic find_item = dynamic::object;
        find_item("thread_count", tc);
        find_item("mode", "find");
        find_item("ops_per_thread", ops_per_thread);
        find_item("total_ops", tc * ops_per_thread * iterations);
        find_item("total_ops_per_sec", total_ops_sec / iterations);
        find_item("avg_latency_ms", total_lat / iterations);
        find_item("iterations", iterations);
        results.push_back(find_item);
    }

    dynamic output = dynamic::object;
    output("benchmark", "concurrency_scaling");
    output("description", "Folly F14FastMap concurrent operation throughput scaling with thread count");
    output("reference", "https://github.com/facebook/folly");
    output("software", "folly");
    output("version", version);
    output("architecture", architecture);
    output("timestamp", std::to_string(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now())));
    output("performance_metrics", dynamic::object
        ("total_ops_per_sec", dynamic::object("unit", "ops/sec")("description", "Total throughput across all threads"))
        ("avg_latency_ms", dynamic::object("unit", "ms")("description", "Average latency per operation"))
    );
    output("dataset_info", dynamic::object
        ("name", "synthetic_string_integer_map")
        ("size", "variable (prefill " + std::to_string(prefill) + " entries)")
        ("source", "in-memory_generated")
    );
    output("results", results);

    write_results(output_path, output);
    return 0;
}
