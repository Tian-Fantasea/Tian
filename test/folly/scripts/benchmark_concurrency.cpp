#include <folly/futures/Future.h>
#include <folly/Baton.h>
#include <folly/dynamic.h>
#include <folly/json.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <atomic>

using folly::Promise;
using folly::Future;
using folly::Baton;
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
    std::cerr << "[CONCURRENCY] Results saved to " << path << std::endl;
}

struct LatencyStats {
    double avg;
    double p50;
    double p90;
    double p99;
    double min_val;
    double max_val;
};

LatencyStats compute_stats(std::vector<double>& latencies) {
    std::sort(latencies.begin(), latencies.end());
    size_t n = latencies.size();
    LatencyStats s;
    s.avg = 0;
    for (auto v : latencies) s.avg += v;
    s.avg /= n;
    s.p50 = latencies[n / 2];
    s.p90 = latencies[static_cast<size_t>(n * 0.9)];
    s.p99 = n >= 100 ? latencies[static_cast<size_t>(n * 0.99)] : latencies[n - 1];
    s.min_val = latencies[0];
    s.max_val = latencies[n - 1];
    return s;
}

std::vector<double> bench_future_chain(int ops) {
    std::vector<double> lats;
    lats.reserve(ops);
    for (int i = 0; i < ops; i++) {
        Promise<int> p;
        Future<int> f = p.getFuture();
        auto t = Timer();
        auto f2 = f.then([](int val) { return val + 1; });
        p.setValue(i);
        f2.wait();
        lats.push_back(t.elapsed_ms());
    }
    return lats;
}

std::vector<double> bench_baton_wait(int ops) {
    std::vector<double> lats;
    lats.reserve(ops);
    for (int i = 0; i < ops; i++) {
        Baton<> baton;
        std::thread setter([&baton]() {
            std::this_thread::sleep_for(std::chrono::microseconds(1));
            baton.post();
        });
        auto t = Timer();
        baton.wait();
        lats.push_back(t.elapsed_ms());
        setter.join();
    }
    return lats;
}

std::vector<double> bench_atomic_load(int ops) {
    std::atomic<int> val{0};
    std::vector<double> lats;
    lats.reserve(ops);
    for (int i = 0; i < ops; i++) {
        auto t = Timer();
        val.load();
        lats.push_back(t.elapsed_ms());
    }
    return lats;
}

int main(int argc, char* argv[]) {
    std::string output_path = "results/benchmark_concurrency.json";
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
        std::vector<double> (*func)(int);
    };

    int future_ops = std::min(ops_per_iter, 10000);
    int baton_ops = std::min(ops_per_iter, 5000);
    int atomic_ops = ops_per_iter;

    std::cerr << "[CONCURRENCY] Benchmarking future_then_chain..." << std::endl;
    std::vector<double> future_lats;
    for (int iter = 0; iter < iterations; iter++) {
        auto lats = bench_future_chain(future_ops);
        future_lats.insert(future_lats.end(), lats.begin(), lats.end());
    }
    auto future_stats = compute_stats(future_lats);
    dynamic future_item = dynamic::object;
    future_item("operation", "future_then_chain");
    future_item("avg_latency_ms", future_stats.avg);
    future_item("p50_latency_ms", future_stats.p50);
    future_item("p90_latency_ms", future_stats.p90);
    future_item("p99_latency_ms", future_stats.p99);
    future_item("min_latency_ms", future_stats.min_val);
    future_item("max_latency_ms", future_stats.max_val);
    future_item("total_ops", static_cast<int64_t>(future_lats.size()));
    future_item("iterations", iterations);
    results.push_back(future_item);

    std::cerr << "[CONCURRENCY] Benchmarking baton_wait_post..." << std::endl;
    std::vector<double> baton_lats;
    for (int iter = 0; iter < iterations; iter++) {
        auto lats = bench_baton_wait(baton_ops);
        baton_lats.insert(baton_lats.end(), lats.begin(), lats.end());
    }
    auto baton_stats = compute_stats(baton_lats);
    dynamic baton_item = dynamic::object;
    baton_item("operation", "baton_wait_post");
    baton_item("avg_latency_ms", baton_stats.avg);
    baton_item("p50_latency_ms", baton_stats.p50);
    baton_item("p90_latency_ms", baton_stats.p90);
    baton_item("p99_latency_ms", baton_stats.p99);
    baton_item("min_latency_ms", baton_stats.min_val);
    baton_item("max_latency_ms", baton_stats.max_val);
    baton_item("total_ops", static_cast<int64_t>(baton_lats.size()));
    baton_item("iterations", iterations);
    results.push_back(baton_item);

    std::cerr << "[CONCURRENCY] Benchmarking atomic_load..." << std::endl;
    std::vector<double> atomic_lats;
    for (int iter = 0; iter < iterations; iter++) {
        auto lats = bench_atomic_load(atomic_ops);
        atomic_lats.insert(atomic_lats.end(), lats.begin(), lats.end());
    }
    auto atomic_stats = compute_stats(atomic_lats);
    dynamic atomic_item = dynamic::object;
    atomic_item("operation", "atomic_load");
    atomic_item("avg_latency_ms", atomic_stats.avg);
    atomic_item("p50_latency_ms", atomic_stats.p50);
    atomic_item("p90_latency_ms", atomic_stats.p90);
    atomic_item("p99_latency_ms", atomic_stats.p99);
    atomic_item("min_latency_ms", atomic_stats.min_val);
    atomic_item("max_latency_ms", atomic_stats.max_val);
    atomic_item("total_ops", static_cast<int64_t>(atomic_lats.size()));
    atomic_item("iterations", iterations);
    results.push_back(atomic_item);

    dynamic output = dynamic::object;
    output("benchmark", "concurrency_latency");
    output("description", "Folly concurrency primitives latency: Future/Promise, Baton, std::atomic");
    output("reference", "https://github.com/facebook/folly");
    output("software", "folly");
    output("version", version);
    output("architecture", architecture);
    output("timestamp", std::to_string(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now())));
    output("performance_metrics", dynamic::object
        ("avg_latency_ms", dynamic::object("unit", "ms")("description", "Average latency per operation"))
        ("p99_latency_ms", dynamic::object("unit", "ms")("description", "99th percentile latency per operation"))
    );
    output("dataset_info", dynamic::object
        ("name", "in_memory_synthetic")
        ("size", "single_operation")
        ("source", "generated_in_process")
    );
    output("results", results);

    write_results(output_path, output);
    return 0;
}
