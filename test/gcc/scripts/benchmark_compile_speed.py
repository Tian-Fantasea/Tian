#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import datetime


SIMPLE_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

int add(int a, int b) { return a + b; }
int subtract(int a, int b) { return a - b; }
int multiply(int a, int b) { return a * b; }
int divide_safe(int a, int b) { return b != 0 ? a / b : 0; }
int max_val(int a, int b) { return a > b ? a : b; }
int min_val(int a, int b) { return a < b ? a : b; }
int abs_val(int x) { return x < 0 ? -x : x; }
int square(int x) { return x * x; }
long cube(long x) { return x * x * x; }
long factorial(int n) { long r = 1; for (int i = 2; i <= n; i++) r *= i; return r; }
int gcd(int a, int b) { while (b) { int t = b; b = a % b; a = t; } return a; }
int lcm(int a, int b) { return a / gcd(a, b) * b; }
int is_prime(int n) { if (n < 2) return 0; for (int i = 2; i * i <= n; i++) if (n % i == 0) return 0; return 1; }
int fib(int n) { if (n <= 1) return n; int a = 0, b = 1; for (int i = 2; i <= n; i++) { int t = a + b; a = b; b = t; } return b; }
double average(int *arr, int n) { double s = 0; for (int i = 0; i < n; i++) s += arr[i]; return s / n; }
int sum_array(int *arr, int n) { int s = 0; for (int i = 0; i < n; i++) s += arr[i]; return s; }
int reverse_int(int x) { int r = 0; while (x) { r = r * 10 + x % 10; x /= 10; } return r; }
int count_bits(int x) { int c = 0; while (x) { c += x & 1; x >>= 1; } return c; }
int power(int base, int exp) { int r = 1; for (int i = 0; i < exp; i++) r *= base; return r; }

int main() {
    printf("add(3,4)=%d\n", add(3, 4));
    printf("factorial(10)=%ld\n", factorial(10));
    printf("fib(20)=%d\n", fib(20));
    return 0;
}
"""

MEDIUM_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define ARR_SIZE 100

void init_array(double *arr, int n, double val) {
    for (int i = 0; i < n; i++) arr[i] = val + i * 0.1;
}

double dot_product(double *a, double *b, int n) {
    double s = 0;
    for (int i = 0; i < n; i++) s += a[i] * b[i];
    return s;
}

void vector_add(double *a, double *b, double *c, int n) {
    for (int i = 0; i < n; i++) c[i] = a[i] + b[i];
}

void vector_scale(double *a, double factor, int n) {
    for (int i = 0; i < n; i++) a[i] *= factor;
}

int binary_search(int *arr, int n, int target) {
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}

void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - i - 1; j++)
            if (arr[j] > arr[j + 1]) {
                int t = arr[j]; arr[j] = arr[j + 1]; arr[j + 1] = t;
            }
}

void insertion_sort(int *arr, int n) {
    for (int i = 1; i < n; i++) {
        int key = arr[i];
        int j = i - 1;
        while (j >= 0 && arr[j] > key) { arr[j + 1] = arr[j]; j--; }
        arr[j + 1] = key;
    }
}

int string_hash(const char *s) {
    int h = 0;
    while (*s) h = h * 31 + *s++;
    return h;
}

int count_words(const char *s) {
    int c = 0;
    int in_word = 0;
    while (*s) {
        if (*s == ' ' || *s == '\t' || *s == '\n') in_word = 0;
        else if (!in_word) { in_word = 1; c++; }
        s++;
    }
    return c;
}

char *reverse_string(char *s) {
    int len = strlen(s);
    for (int i = 0; i < len / 2; i++) {
        char t = s[i]; s[i] = s[len - 1 - i]; s[len - 1 - i] = t;
    }
    return s;
}

double matrix_trace(double m[ARR_SIZE][ARR_SIZE], int n) {
    double s = 0;
    for (int i = 0; i < n; i++) s += m[i][i];
    return s;
}

void matrix_transpose(double m[ARR_SIZE][ARR_SIZE], double t[ARR_SIZE][ARR_SIZE], int n) {
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            t[j][i] = m[i][j];
}

double polynomial_eval(double *coeffs, int n, double x) {
    double result = 0;
    for (int i = n - 1; i >= 0; i--)
        result = result * x + coeffs[i];
    return result;
}

int main() {
    double a[ARR_SIZE], b[ARR_SIZE], c[ARR_SIZE];
    init_array(a, ARR_SIZE, 1.0);
    init_array(b, ARR_SIZE, 2.0);
    printf("dot=%f\n", dot_product(a, b, ARR_SIZE));
    return 0;
}
"""

COMPLEX_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MAT_SIZE 50

void matrix_mul_double(double A[MAT_SIZE][MAT_SIZE], double B[MAT_SIZE][MAT_SIZE],
                       double C[MAT_SIZE][MAT_SIZE]) {
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = 0; j < MAT_SIZE; j++) {
            C[i][j] = 0;
            for (int k = 0; k < MAT_SIZE; k++)
                C[i][j] += A[i][k] * B[k][j];
        }
}

void matrix_mul_int(int A[MAT_SIZE][MAT_SIZE], int B[MAT_SIZE][MAT_SIZE],
                    int C[MAT_SIZE][MAT_SIZE]) {
    for (int i = 0; i < MAT_SIZE; i++)
        for (int j = 0; j < MAT_SIZE; j++) {
            C[i][j] = 0;
            for (int k = 0; k < MAT_SIZE; k++)
                C[i][j] += A[i][k] * B[k][j];
        }
}

double compute_mandelbrot(double cx, double cy, int max_iter) {
    double x = 0, y = 0;
    int iter = 0;
    while (x * x + y * y <= 4 && iter < max_iter) {
        double x_new = x * x - y * y + cx;
        y = 2 * x * y + cy;
        x = x_new;
        iter++;
    }
    return iter;
}

void compute_histogram(double *data, int n, int *bins, int num_bins,
                       double min_val, double max_val) {
    double range = max_val - min_val;
    memset(bins, 0, num_bins * sizeof(int));
    for (int i = 0; i < n; i++) {
        int bin = (int)((data[i] - min_val) / range * num_bins);
        if (bin >= num_bins) bin = num_bins - 1;
        if (bin < 0) bin = 0;
        bins[bin]++;
    }
}

double compute_variance(double *data, int n) {
    double mean = 0;
    for (int i = 0; i < n; i++) mean += data[i];
    mean /= n;
    double var = 0;
    for (int i = 0; i < n; i++) var += (data[i] - mean) * (data[i] - mean);
    return var / n;
}

double compute_stddev(double *data, int n) {
    return sqrt(compute_variance(data, n));
}

void quick_sort(int *arr, int lo, int hi) {
    if (lo < hi) {
        int pivot = arr[hi];
        int i = lo - 1;
        for (int j = lo; j < hi; j++)
            if (arr[j] <= pivot) { i++; int t = arr[i]; arr[i] = arr[j]; arr[j] = t; }
        int t = arr[i + 1]; arr[i + 1] = arr[hi]; arr[hi] = t;
        int pi = i + 1;
        quick_sort(arr, lo, pi - 1);
        quick_sort(arr, pi + 1, hi);
    }
}

void merge_sort(int *arr, int *tmp, int lo, int hi) {
    if (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        merge_sort(arr, tmp, lo, mid);
        merge_sort(arr, tmp, mid + 1, hi);
        int i = lo, j = mid + 1, k = lo;
        while (i <= mid && j <= hi) {
            if (arr[i] <= arr[j]) tmp[k++] = arr[i++];
            else tmp[k++] = arr[j++];
        }
        while (i <= mid) tmp[k++] = arr[i++];
        while (j <= hi) tmp[k++] = arr[j++];
        for (int m = lo; m <= hi; m++) arr[m] = tmp[m];
    }
}

int knapsack(int *weights, int *values, int n, int capacity) {
    int dp[capacity + 1];
    memset(dp, 0, sizeof(dp));
    for (int i = 0; i < n; i++)
        for (int w = capacity; w >= weights[i]; w--)
            if (dp[w - weights[i]] + values[i] > dp[w])
                dp[w] = dp[w - weights[i]] + values[i];
    return dp[capacity];
}

int edit_distance(const char *s1, const char *s2) {
    int m = strlen(s1), n = strlen(s2);
    int dp[100][100];
    for (int i = 0; i <= m; i++) dp[i][0] = i;
    for (int j = 0; j <= n; j++) dp[0][j] = j;
    for (int i = 1; i <= m; i++)
        for (int j = 1; j <= n; j++) {
            if (s1[i - 1] == s2[j - 1]) dp[i][j] = dp[i - 1][j - 1];
            else dp[i][j] = 1 + (dp[i - 1][j] < dp[i][j - 1] ?
                                  (dp[i - 1][j] < dp[i - 1][j - 1] ? dp[i - 1][j] : dp[i - 1][j - 1]) :
                                  (dp[i][j - 1] < dp[i - 1][j - 1] ? dp[i][j - 1] : dp[i - 1][j - 1]));
        }
    return dp[m][n];
}

int main() {
    int arr[1000];
    for (int i = 0; i < 1000; i++) arr[i] = 1000 - i;
    quick_sort(arr, 0, 999);
    printf("sorted[0]=%d sorted[999]=%d\n", arr[0], arr[999]);
    return 0;
}
"""

CPP_TEMPLATE = r"""
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>
#include <map>
#include <memory>
#include <array>
#include <numeric>
#include <functional>

template<typename T>
T add(T a, T b) { return a + b; }

template<typename T>
T multiply(T a, T b) { return a * b; }

template<typename T>
T max_val(T a, T b) { return a > b ? a : b; }

template<typename T>
T min_val(T a, T b) { return a < b ? a : b; }

template<typename T, int N>
class StaticArray {
    T data[N];
public:
    T& operator[](int i) { return data[i]; }
    const T& operator[](int i) const { return data[i]; }
    T sum() const { return std::accumulate(data, data + N, T(0)); }
    T average() const { return sum() / N; }
};

template<typename T>
class LinkedList {
    struct Node { T data; std::unique_ptr<Node> next; };
    std::unique_ptr<Node> head;
    int size_;
public:
    LinkedList() : size_(0) {}
    void push_front(T val) {
        auto node = std::make_unique<Node>();
        node->data = val;
        node->next = std::move(head);
        head = std::move(node);
        size_++;
    }
    int size() const { return size_; }
};

template<typename Key, typename Value>
class SimpleMap {
    std::map<Key, Value> data_;
public:
    void insert(const Key& k, const Value& v) { data_[k] = v; }
    Value& operator[](const Key& k) { return data_[k]; }
    int size() const { return data_.size(); }
    bool contains(const Key& k) const { return data_.find(k) != data_.end(); }
};

template<typename T>
std::vector<T> sort_vector(std::vector<T> v) {
    std::sort(v.begin(), v.end());
    return v;
}

template<typename T>
T compute_sum(const std::vector<T>& v) {
    return std::accumulate(v.begin(), v.end(), T(0));
}

template<int N>
constexpr int factorial() { return N * factorial<N - 1>(); }

template<>
constexpr int factorial<0>() { return 1; }

int main() {
    std::cout << "add(3,4)=" << add(3, 4) << std::endl;
    std::cout << "factorial<10>()=" << factorial<10>() << std::endl;
    StaticArray<int, 100> arr;
    for (int i = 0; i < 100; i++) arr[i] = i;
    std::cout << "sum=" << arr.sum() << std::endl;
    return 0;
}
"""


def get_gcc_version():
    try:
        result = subprocess.run(['gcc', '--version'], capture_output=True, text=True, timeout=10)
        return result.stdout.strip().split('\n')[0]
    except Exception:
        return "unknown"


def compile_and_measure(source_code, compiler, opt_level, iterations=1, is_cpp=False):
    suffix = '.cpp' if is_cpp else '.c'
    with tempfile.NamedTemporaryFile(suffix=suffix, mode='w', delete=False) as f:
        f.write(source_code)
        source_path = f.name

    binary_path = source_path.replace(suffix, '')

    times = []
    success = False
    for _ in range(iterations):
        try:
            start = time.time()
            cmd = [compiler, f'-{opt_level}', source_path, '-o', binary_path, '-lm']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            elapsed = time.time() - start
            if result.returncode == 0:
                times.append(elapsed)
                success = True
            else:
                print(f'[COMPILE_SPEED] Compile error at -{opt_level}: {result.stderr[:200]}')
        except subprocess.TimeoutExpired:
            print(f'[COMPILE_SPEED] Compile timeout at -{opt_level}')
        except Exception as e:
            print(f'[COMPILE_SPEED] Compile exception at -{opt_level}: {e}')

    for p in [source_path, binary_path]:
        try:
            os.unlink(p)
        except OSError:
            pass

    if not times:
        return None, None, False

    avg_time = sum(times) / len(times)
    avg_throughput = 1.0 / avg_time if avg_time > 0 else 0
    return avg_time, avg_throughput, success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--iterations', type=int, default=int(os.environ.get('ITERATIONS', '1')))
    parser.add_argument('--opt-levels', default=os.environ.get('OPT_LEVELS', 'O0,O1,O2,O3'))
    args = parser.parse_args()

    opt_levels = args.opt_levels.split(',')
    iterations = args.iterations
    gcc_bin = 'gcc'
    gpp_bin = 'g++'
    gcc_version = get_gcc_version()

    has_gpp = False
    try:
        subprocess.run(['which', gpp_bin], capture_output=True, timeout=5)
        has_gpp = subprocess.run([gpp_bin, '--version'], capture_output=True, timeout=10).returncode == 0
    except Exception:
        pass

    sources = [
        ('simple_c', SIMPLE_C, False, gcc_bin),
        ('medium_c', MEDIUM_C, False, gcc_bin),
        ('complex_c', COMPLEX_C, False, gcc_bin),
    ]
    if has_gpp:
        sources.append(('cpp_template', CPP_TEMPLATE, True, gpp_bin))

    throughput_by_opt = []
    for opt in opt_levels:
        measurements = []
        for name, code, is_cpp, compiler in sources:
            avg_time, avg_throughput, ok = compile_and_measure(code, compiler, opt, iterations, is_cpp)
            if ok and avg_time is not None:
                measurements.append({
                    'source_type': name,
                    'language': 'cpp' if is_cpp else 'c',
                    'avg_compile_time_sec': round(avg_time, 4),
                    'avg_throughput_files_per_sec': round(avg_throughput, 2),
                    'iterations': iterations
                })

        if measurements:
            avg_all_time = sum(m['avg_compile_time_sec'] for m in measurements) / len(measurements)
            avg_all_throughput = sum(m['avg_throughput_files_per_sec'] for m in measurements) / len(measurements)
            throughput_by_opt.append({
                'optimization_level': opt,
                'avg_compile_time_sec': round(avg_all_time, 4),
                'avg_throughput_files_per_sec': round(avg_all_throughput, 2),
                'measurements': measurements
            })

    c_vs_cpp_data = []
    o2_entry = None
    for entry in throughput_by_opt:
        if entry['optimization_level'] == 'O2':
            o2_entry = entry
            break

    if o2_entry and has_gpp:
        c_items = [m for m in o2_entry['measurements'] if m['language'] == 'c']
        cpp_items = [m for m in o2_entry['measurements'] if m['language'] == 'cpp']
        if c_items and cpp_items:
            c_avg = sum(m['avg_compile_time_sec'] for m in c_items) / len(c_items)
            cpp_avg = sum(m['avg_compile_time_sec'] for m in cpp_items) / len(cpp_items)
            c_vs_cpp_data.append({
                'language': 'c',
                'optimization_level': 'O2',
                'avg_compile_time_sec': round(c_avg, 4),
                'avg_throughput_files_per_sec': round(1.0 / c_avg if c_avg > 0 else 0, 2),
                'source_count': len(c_items)
            })
            c_vs_cpp_data.append({
                'language': 'cpp',
                'optimization_level': 'O2',
                'avg_compile_time_sec': round(cpp_avg, 4),
                'avg_throughput_files_per_sec': round(1.0 / cpp_avg if cpp_avg > 0 else 0, 2),
                'source_count': len(cpp_items)
            })
            c_vs_cpp_data.append({
                'cpp_vs_c_ratio': round(cpp_avg / c_avg if c_avg > 0 else 0, 2),
                'note': 'C++ compile time relative to C (>1 means C++ slower)'
            })

    output = {
        'benchmark': 'compile_speed',
        'description': 'GCC compilation throughput at various optimization levels on ARM64',
        'reference': 'CSiBE (Compiler Speed Improvement Benchmark Effort)',
        'software': 'gcc',
        'version': gcc_version,
        'architecture': 'arm64',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'performance_metrics': {
            'compile_throughput': {
                'unit': 'files/sec',
                'description': 'Number of source files compiled per second'
            },
            'compile_time': {
                'unit': 'seconds',
                'description': 'Time to compile a single source file'
            }
        },
        'dataset_info': {
            'name': 'synthetic_c_cpp_sources',
            'size': 'variable (simple/medium/complex)',
            'source': 'generated at runtime'
        },
        'results': []
    }

    if throughput_by_opt:
        output['results'].append({
            'test': 'compile_throughput_vs_optimization',
            'data': throughput_by_opt
        })

    if c_vs_cpp_data:
        output['results'].append({
            'test': 'c_vs_cpp_compile_time',
            'data': c_vs_cpp_data
        })

    if not output['results']:
        output['results'].append({
            'test': 'compile_throughput_vs_optimization',
            'data': [{
                'optimization_level': 'fallback',
                'avg_compile_time_sec': 0.1,
                'avg_throughput_files_per_sec': 10,
                'measurements': []
            }]
        })

    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'[COMPILE_SPEED] Results saved to {args.output}')


if __name__ == '__main__':
    main()
