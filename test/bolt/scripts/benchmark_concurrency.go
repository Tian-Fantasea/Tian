package main

import (
	"encoding/json"
	"fmt"
	"flag"
	"log"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	bolt "go.etcd.io/bbolt"
)

var (
	keyCount   = flag.Int("key-count", 100000, "Number of keys")
	iterations = flag.Int("iterations", 3, "Iterations per test")
	resultsDir = flag.String("results-dir", "results", "Results directory")
)

type BenchmarkResult struct {
	Benchmark          string                 `json:"benchmark"`
	Description        string                 `json:"description"`
	Reference          string                 `json:"reference"`
	Timestamp          string                 `json:"timestamp"`
	PerformanceMetrics map[string]MetricInfo  `json:"performance_metrics"`
	DatasetInfo        DatasetInfo            `json:"dataset_info"`
	Results            []ConcurrencyResult    `json:"results"`
}

type MetricInfo struct {
	Unit        string `json:"unit"`
	Description string `json:"description"`
}

type DatasetInfo struct {
	Name   string `json:"name"`
	Size   string `json:"size"`
	Source string `json:"source"`
}

type ConcurrencyResult struct {
	Goroutines    int     `json:"goroutines"`
	OpsPerSec     float64 `json:"ops_per_sec"`
	AvgLatencyMs  float64 `json:"avg_latency_ms"`
	TotalOps      int64   `json:"total_ops"`
	DurationSec   float64 `json:"duration_sec"`
	Iteration     int     `json:"iteration"`
	Mode          string  `json:"mode"`
}

func benchConcurrency(dbPath string, goroutines int, count int, iter int) ConcurrencyResult {
	os.Remove(dbPath)
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Concurrency: open failed: %v", err)
	}
	defer db.Close()

	db.Update(func(tx *bolt.Tx) error {
		tx.CreateBucketIfNotExists([]byte("concurrent"))
		return nil
	})

	var totalOps int64
	start := time.Now()

	var wg sync.WaitGroup
	keysPerGoroutine := count / goroutines

	for g := 0; g < goroutines; g++ {
		wg.Add(1)
		go func(goroutineID int) {
			defer wg.Done()
			localOps := 0
			for i := 0; i < keysPerGoroutine; i++ {
				key := fmt.Sprintf("key_%010d_%d", goroutineID, i)
				val := fmt.Sprintf("val_%010d_%d", goroutineID, i)
				db.Batch(func(tx *bolt.Tx) error {
					b, _ := tx.CreateBucketIfNotExists([]byte("concurrent"))
					b.Put([]byte(key), []byte(val))
					localOps++
					return nil
				})
			}
			atomic.AddInt64(&totalOps, int64(localOps))
		}(g)
	}
	wg.Wait()

	duration := time.Since(start).Seconds()
	ops := atomic.LoadInt64(&totalOps)

	return ConcurrencyResult{
		Goroutines:   goroutines,
		OpsPerSec:    float64(ops) / duration,
		AvgLatencyMs: (duration / float64(ops)) * 1000,
		TotalOps:     ops,
		DurationSec:  duration,
		Iteration:    iter,
		Mode:         "batch_write",
	}
}

func benchConcurrentRead(dbPath string, goroutines int, count int, iter int) ConcurrencyResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("ConcurrentRead: open failed: %v", err)
	}
	defer db.Close()

	var totalOps int64
	start := time.Now()

	var wg sync.WaitGroup
	keysPerGoroutine := count / goroutines

	for g := 0; g < goroutines; g++ {
		wg.Add(1)
		go func(goroutineID int) {
			defer wg.Done()
			localOps := 0
			for i := 0; i < keysPerGoroutine; i++ {
				key := fmt.Sprintf("key_%010d_%d", goroutineID, i)
				db.View(func(tx *bolt.Tx) error {
					b := tx.Bucket([]byte("concurrent"))
					_ = b.Get([]byte(key))
					localOps++
					return nil
				})
			}
			atomic.AddInt64(&totalOps, int64(localOps))
		}(g)
	}
	wg.Wait()

	duration := time.Since(start).Seconds()
	ops := atomic.LoadInt64(&totalOps)

	return ConcurrencyResult{
		Goroutines:   goroutines,
		OpsPerSec:    float64(ops) / duration,
		AvgLatencyMs: (duration / float64(ops)) * 1000,
		TotalOps:     ops,
		DurationSec:  duration,
		Iteration:    iter,
		Mode:         "concurrent_read",
	}
}

func main() {
	flag.Parse()
	os.MkdirAll(*resultsDir, 0755)

	goroutineLevels := []int{1, 2, 4, 8, 16}
	allResults := make([]ConcurrencyResult, 0)

	for _, gr := range goroutineLevels {
		for i := 0; i < *iterations; i++ {
			dbPath := filepath.Join(*resultsDir, fmt.Sprintf("concurrency_%d.db", gr))
			log.Printf("[CONCURRENCY] Batch write: %d goroutines, iteration %d...", gr, i+1)
			r := benchConcurrency(dbPath, gr, *keyCount, i+1)
			allResults = append(allResults, r)
			os.Remove(dbPath)
		}
	}

	preloadPath := filepath.Join(*resultsDir, "concurrency_preload.db")
	os.Remove(preloadPath)
	db, err := bolt.Open(preloadPath, 0600, nil)
	if err != nil {
		log.Fatalf("Preload: open failed: %v", err)
	}
	db.Update(func(tx *bolt.Tx) error {
		b, e := tx.CreateBucketIfNotExists([]byte("concurrent"))
		if e != nil {
			return e
		}
		for g := 0; g < 16; g++ {
			for i := 0; i < *keyCount/16; i++ {
				key := fmt.Sprintf("key_%010d_%d", g, i)
				val := fmt.Sprintf("val_%010d_%d", g, i)
				b.Put([]byte(key), []byte(val))
			}
		}
		return nil
	})
	db.Close()

	for _, gr := range goroutineLevels {
		for i := 0; i < *iterations; i++ {
			log.Printf("[CONCURRENCY] Concurrent read: %d goroutines, iteration %d...", gr, i+1)
			r := benchConcurrentRead(preloadPath, gr, *keyCount, i+1)
			allResults = append(allResults, r)
		}
	}

	bench := BenchmarkResult{
		Benchmark:   "concurrency_scaling",
		Description: "bbolt concurrency scaling benchmark on ARM64",
		Reference:   "bbolt Batch/View concurrent patterns",
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
		PerformanceMetrics: map[string]MetricInfo{
			"ops_per_sec":    {Unit: "ops/s", Description: "Operations per second at given concurrency"},
			"avg_latency_ms": {Unit: "ms", Description: "Average latency at given concurrency"},
		},
		DatasetInfo: DatasetInfo{
			Name:   fmt.Sprintf("concurrency_%d_keys", *keyCount),
			Size:   fmt.Sprintf("%d keys across goroutines, 128B values", *keyCount),
			Source: "Generated per goroutine",
		},
		Results: allResults,
	}

	outPath := filepath.Join(*resultsDir, "benchmark_concurrency.json")
	data, _ := json.MarshalIndent(bench, "", "  ")
	os.WriteFile(outPath, data, 0644)
	log.Printf("[CONCURRENCY] Results saved to %s", outPath)
	os.Remove(preloadPath)
}