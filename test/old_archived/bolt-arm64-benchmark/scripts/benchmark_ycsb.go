package main

import (
	"encoding/json"
	"fmt"
	"flag"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"time"

	bolt "go.etcd.io/bbolt"
)

var (
	keyCount    = flag.Int("key-count", 100000, "Number of keys")
	iterations  = flag.Int("iterations", 3, "Iterations per workload")
	resultsDir  = flag.String("results-dir", "results", "Results directory")
	valueSize   = flag.Int("value-size", 256, "Value size in bytes")
)

type BenchmarkResult struct {
	Benchmark        string                 `json:"benchmark"`
	Description      string                 `json:"description"`
	Reference        string                 `json:"reference"`
	Timestamp        string                 `json:"timestamp"`
	PerformanceMetrics map[string]MetricInfo `json:"performance_metrics"`
	DatasetInfo      DatasetInfo            `json:"dataset_info"`
	Results          []WorkloadResult       `json:"results"`
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

type WorkloadResult struct {
	Workload      string  `json:"workload"`
	ReadRatio     float64 `json:"read_ratio"`
	WriteRatio    float64 `json:"write_ratio"`
	OpsPerSec     float64 `json:"ops_per_sec"`
	AvgLatencyMs  float64 `json:"avg_latency_ms"`
	P50LatencyMs  float64 `json:"p50_latency_ms"`
	P99LatencyMs  float64 `json:"p99_latency_ms"`
	TotalOps      int     `json:"total_ops"`
	DurationSec   float64 `json:"duration_sec"`
	Iteration     int     `json:"iteration"`
}

func generateValue(size int) []byte {
	val := make([]byte, size)
	for i := range val {
		val[i] = byte(rand.Intn(256))
	}
	return val
}

func loadKeys(dbPath string, count int, vSize int) error {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		return err
	}
	defer db.Close()

	batchSize := 1000
	for i := 0; i < count; i += batchSize {
		end := i + batchSize
		if end > count {
			end = count
		}
		err = db.Update(func(tx *bolt.Tx) error {
			b, err2 := tx.CreateBucketIfNotExists([]byte("ycsb"))
			if err2 != nil {
				return err2
			}
			for j := i; j < end; j++ {
				key := fmt.Sprintf("key_%010d", j)
				val := generateValue(vSize)
				if err3 := b.Put([]byte(key), val); err3 != nil {
					return err3
				}
			}
			return nil
		})
		if err != nil {
			return err
		}
	}
	return nil
}

func runWorkload(dbPath string, workload string, readRatio float64, count int, vSize int, iter int) WorkloadResult {
	db, err := bolt.Open(dbPath, 0600, nil)
	if err != nil {
		log.Fatalf("Failed to open db for workload %s: %v", workload, err)
	}
	defer db.Close()

	opsPerIter := 50000
	latencies := make([]float64, 0, opsPerIter)
	start := time.Now()

	for i := 0; i < opsPerIter; i++ {
		keyIdx := rand.Intn(count)
		key := fmt.Sprintf("key_%010d", keyIdx)
		isRead := rand.Float64() < readRatio

		opStart := time.Now()
		if isRead {
			db.View(func(tx *bolt.Tx) error {
				b := tx.Bucket([]byte("ycsb"))
				if b != nil {
					_ = b.Get([]byte(key))
				}
				return nil
			})
		} else {
			db.Update(func(tx *bolt.Tx) error {
				b, _ := tx.CreateBucketIfNotExists([]byte("ycsb"))
				return b.Put([]byte(key), generateValue(vSize))
			})
		}
		latencies = append(latencies, float64(time.Since(opStart).Microseconds())/1000.0)
	}

	duration := time.Since(start).Seconds()
	opsPerSec := float64(opsPerIter) / duration

	sortFloats(latencies)
	p50 := percentile(latencies, 50)
	p99 := percentile(latencies, 99)
	avg := avgFloats(latencies)

	return WorkloadResult{
		Workload:      workload,
		ReadRatio:     readRatio,
		WriteRatio:    1.0 - readRatio,
		OpsPerSec:     opsPerSec,
		AvgLatencyMs:  avg,
		P50LatencyMs:  p50,
		P99LatencyMs:  p99,
		TotalOps:      opsPerIter,
		DurationSec:   duration,
		Iteration:     iter,
	}
}

func sortFloats(arr []float64) {
	for i := 0; i < len(arr)-1; i++ {
		for j := i + 1; j < len(arr); j++ {
			if arr[j] < arr[i] {
				arr[i], arr[j] = arr[j], arr[i]
			}
		}
	}
}

func percentile(arr []float64, p float64) float64 {
	if len(arr) == 0 {
		return 0
	}
	idx := int(p / 100.0 * float64(len(arr)))
	if idx >= len(arr) {
		idx = len(arr) - 1
	}
	return arr[idx]
}

func avgFloats(arr []float64) float64 {
	if len(arr) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range arr {
		sum += v
	}
	return sum / float64(len(arr))
}

func main() {
	flag.Parse()

	os.MkdirAll(*resultsDir, 0755)
	dbPath := filepath.Join(*resultsDir, "ycsb_bench.db")
	os.Remove(dbPath)

	log.Printf("[YCSB] Loading %d keys with %d byte values...", *keyCount, *valueSize)
	if err := loadKeys(dbPath, *keyCount, *valueSize); err != nil {
		log.Fatalf("[YCSB] Load failed: %v", err)
	}

	workloads := []struct {
		name      string
		readRatio float64
	}{
		{"workload_a", 0.50},
		{"workload_b", 0.95},
		{"workload_c", 1.00},
	}

	allResults := make([]WorkloadResult, 0)
	for _, wl := range workloads {
		for i := 0; i < *iterations; i++ {
			log.Printf("[YCSB] Running %s iteration %d...", wl.name, i+1)
			r := runWorkload(dbPath, wl.name, wl.readRatio, *keyCount, *valueSize, i+1)
			allResults = append(allResults, r)
			os.Remove(dbPath)
			loadKeys(dbPath, *keyCount, *valueSize)
		}
	}

	bench := BenchmarkResult{
		Benchmark:   "ycsb",
		Description: "YCSB-like workload benchmark for bbolt on ARM64",
		Reference:   "YCSB - Yahoo Cloud Serving Benchmark",
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
		PerformanceMetrics: map[string]MetricInfo{
			"ops_per_sec":    {Unit: "ops/s", Description: "Operations per second"},
			"avg_latency_ms": {Unit: "ms", Description: "Average operation latency"},
			"p50_latency_ms": {Unit: "ms", Description: "50th percentile latency"},
			"p99_latency_ms": {Unit: "ms", Description: "99th percentile latency"},
		},
		DatasetInfo: DatasetInfo{
			Name:   fmt.Sprintf("ycsb_%d_keys_%dB_values", *keyCount, *valueSize),
			Size:   fmt.Sprintf("%d keys, %dB values", *keyCount, *valueSize),
			Source: "Generated randomly",
		},
		Results: allResults,
	}

	outPath := filepath.Join(*resultsDir, "benchmark_ycsb.json")
	data, _ := json.MarshalIndent(bench, "", "  ")
	os.WriteFile(outPath, data, 0644)
	log.Printf("[YCSB] Results saved to %s", outPath)
	os.Remove(dbPath)
}
