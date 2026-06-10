package main

import (
	"encoding/json"
	"fmt"
	"flag"
	"log"
	"os"
	"path/filepath"
	"time"

	bolt "go.etcd.io/bbolt"
)

var (
	mode       = flag.String("mode", "full", "Mode: verify or full")
	dbPath     = flag.String("db-path", "", "Database file path")
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
	Results            []MicroResult          `json:"results"`
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

type MicroResult struct {
	Operation     string  `json:"operation"`
	OpsPerSec     float64 `json:"ops_per_sec"`
	AvgLatencyMs  float64 `json:"avg_latency_ms"`
	TotalOps      int     `json:"total_ops"`
	DurationSec   float64 `json:"duration_sec"`
	Iteration     int     `json:"iteration"`
}

func verifyMode() {
	p := *dbPath
	if p == "" {
		p = filepath.Join(*resultsDir, "verify_test.db")
	}
	db, err := bolt.Open(p, 0600, nil)
	if err != nil {
		log.Fatalf("Verify: open failed: %v", err)
	}
	defer db.Close()

	err = db.Update(func(tx *bolt.Tx) error {
		b, e := tx.CreateBucketIfNotExists([]byte("verify"))
		if e != nil {
			return e
		}
		for i := 0; i < 100; i++ {
			key := fmt.Sprintf("verify_key_%d", i)
			val := fmt.Sprintf("verify_val_%d", i)
			if e2 := b.Put([]byte(key), []byte(val)); e2 != nil {
				return e2
			}
		}
		return nil
	})
	if err != nil {
		log.Fatalf("Verify: write failed: %v", err)
	}

	count := 0
	db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("verify"))
		c := b.Cursor()
		for k, _ := c.First(); k != nil; k, _ = c.Next() {
			count++
		}
		return nil
	})
	log.Printf("[VERIFY] bbolt works: wrote and read %d keys", count)
}

func benchPut(dbPath string, count int, iter int) MicroResult {
	os.Remove(dbPath)
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Put: open failed: %v", err)
	}
	defer db.Close()

	db.Update(func(tx *bolt.Tx) error {
		tx.CreateBucketIfNotExists([]byte("micro"))
		return nil
	})

	totalOps := 0
	start := time.Now()
	for i := 0; i < count; i++ {
		db.Update(func(tx *bolt.Tx) error {
			b := tx.Bucket([]byte("micro"))
			key := fmt.Sprintf("key_%010d", i)
			val := fmt.Sprintf("val_%010d", i)
			b.Put([]byte(key), []byte(val))
			totalOps++
			return nil
		})
	}
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "put",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func benchGet(dbPath string, count int, iter int) MicroResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Get: open failed: %v", err)
	}
	defer db.Close()

	totalOps := 0
	start := time.Now()
	db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("micro"))
		for i := 0; i < count; i++ {
			key := fmt.Sprintf("key_%010d", i)
			_ = b.Get([]byte(key))
			totalOps++
		}
		return nil
	})
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "get",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func benchDelete(dbPath string, count int, iter int) MicroResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Delete: open failed: %v", err)
	}
	defer db.Close()

	totalOps := 0
	start := time.Now()
	for i := 0; i < count/2; i++ {
		db.Update(func(tx *bolt.Tx) error {
			b := tx.Bucket([]byte("micro"))
			key := fmt.Sprintf("key_%010d", i)
			b.Delete([]byte(key))
			totalOps++
			return nil
		})
	}
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "delete",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func benchCursorScan(dbPath string, count int, iter int) MicroResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Scan: open failed: %v", err)
	}
	defer db.Close()

	totalOps := 0
	start := time.Now()
	db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("micro"))
		c := b.Cursor()
		for k, _ := c.First(); k != nil; k, _ = c.Next() {
			totalOps++
		}
		return nil
	})
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "cursor_scan",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func benchBatchWrite(dbPath string, count int, iter int) MicroResult {
	os.Remove(dbPath)
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Batch: open failed: %v", err)
	}
	defer db.Close()

	batchSize := 1000
	totalOps := 0
	start := time.Now()
	for i := 0; i < count; i += batchSize {
		end := i + batchSize
		if end > count {
			end = count
		}
		db.Update(func(tx *bolt.Tx) error {
			b, e := tx.CreateBucketIfNotExists([]byte("batch"))
			if e != nil {
				return e
			}
			for j := i; j < end; j++ {
				key := fmt.Sprintf("key_%010d", j)
				val := fmt.Sprintf("val_%010d", j)
				b.Put([]byte(key), []byte(val))
				totalOps++
			}
			return nil
		})
	}
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "batch_write",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func benchForEach(dbPath string, count int, iter int) MicroResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("ForEach: open failed: %v", err)
	}
	defer db.Close()

	totalOps := 0
	start := time.Now()
	db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("batch"))
		b.ForEach(func(k, v []byte) error {
			totalOps++
			return nil
		})
		return nil
	})
	duration := time.Since(start).Seconds()

	return MicroResult{
		Operation:    "foreach",
		OpsPerSec:    float64(totalOps) / duration,
		AvgLatencyMs: (duration / float64(totalOps)) * 1000,
		TotalOps:     totalOps,
		DurationSec:  duration,
		Iteration:    iter,
	}
}

func main() {
	flag.Parse()

	if *mode == "verify" {
		verifyMode()
		return
	}

	os.MkdirAll(*resultsDir, 0755)
	allResults := make([]MicroResult, 0)

	ops := []struct {
		name string
		fn   func(string, int, int) MicroResult
	}{
		{"put", benchPut},
		{"get", benchGet},
		{"delete", benchDelete},
		{"cursor_scan", benchCursorScan},
		{"batch_write", benchBatchWrite},
		{"foreach", benchForEach},
	}

	dbPath := filepath.Join(*resultsDir, "micro_preload.db")
	os.Remove(dbPath)

	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Preload: open failed: %v", err)
	}
	db.Update(func(tx *bolt.Tx) error {
		b, e := tx.CreateBucketIfNotExists([]byte("micro"))
		if e != nil {
			return e
		}
		for i := 0; i < *keyCount; i++ {
			key := fmt.Sprintf("key_%010d", i)
			val := fmt.Sprintf("val_%010d", i)
			b.Put([]byte(key), []byte(val))
		}
		b2, e2 := tx.CreateBucketIfNotExists([]byte("batch"))
		if e2 != nil {
			return e2
		}
		for i := 0; i < *keyCount; i++ {
			key := fmt.Sprintf("key_%010d", i)
			val := fmt.Sprintf("val_%010d", i)
			b2.Put([]byte(key), []byte(val))
		}
		return nil
	})
	db.Close()

	for _, op := range ops {
		for i := 0; i < *iterations; i++ {
			log.Printf("[MICRO] %s iteration %d...", op.name, i+1)
			r := op.fn(dbPath, *keyCount, i+1)
			allResults = append(allResults, r)
		}
	}

	bench := BenchmarkResult{
		Benchmark:   "micro",
		Description: "bbolt micro operation benchmarks on ARM64",
		Reference:   "bbolt built-in Go benchmarks",
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
		PerformanceMetrics: map[string]MetricInfo{
			"ops_per_sec":    {Unit: "ops/s", Description: "Operations per second"},
			"avg_latency_ms": {Unit: "ms", Description: "Average latency per operation"},
		},
		DatasetInfo: DatasetInfo{
			Name:   fmt.Sprintf("micro_%d_keys", *keyCount),
			Size:   fmt.Sprintf("%d keys, 128B values", *keyCount),
			Source: "Generated sequentially",
		},
		Results: allResults,
	}

	outPath := filepath.Join(*resultsDir, "micro_benchmark.json")
	data, _ := json.MarshalIndent(bench, "", "  ")
	os.WriteFile(outPath, data, 0644)
	log.Printf("[MICRO] Results saved to %s", outPath)
	os.Remove(dbPath)
}