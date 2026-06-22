#!/usr/bin/env python3
import json
import os
import argparse
import datetime


def main():
    parser = argparse.ArgumentParser(description="Generate text summary of benchmark results")
    parser.add_argument("--input", required=True, help="Input results.json file")
    parser.add_argument("--output", required=True, help="Output results.txt file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("[SUMMARY] results.json not found")
        return

    with open(args.input, 'r') as f:
        data = json.load(f)

    summary = data.get("summary", {})
    env = data.get("environment", {})
    benchmarks = data.get("benchmarks", {})

    lines = []
    lines.append("=" * 70)
    lines.append("OpenViking ARM64 Performance Benchmark Summary")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
    lines.append("")

    if env:
        lines.append("--- Environment ---")
        lines.append(f"Architecture:          {env.get('architecture', 'N/A')}")
        lines.append(f"OS:                    {env.get('os', 'N/A')}")
        lines.append(f"Kernel:                {env.get('kernel', 'N/A')}")
        lines.append(f"CPU:                   {env.get('cpu_model', 'N/A')} ({env.get('cores', 'N/A')} cores)")
        lines.append(f"Memory:                {env.get('memory_mb', 'N/A')} MB")
        lines.append(f"OpenViking Version:    {env.get('software_version', 'N/A')}")
        lines.append(f"Python Version:        {env.get('python_version', 'N/A')}")
        lines.append(f"NEON/ASIMD:            {env.get('neon_asimd_available', 'N/A')}")
        lines.append(f"Install Method:        {env.get('install_method', 'N/A')}")
        lines.append(f"Max Concurrent Emb:    {env.get('max_concurrent_embedding', 'N/A')}")
        lines.append(f"Max Concurrent VLM:    {env.get('max_concurrent_vlm', 'N/A')}")
        lines.append("")

    locomo = benchmarks.get("locomo", {})
    if locomo:
        lines.append("--- LoCoMo User Memory (Phase 3a) ---")
        lines.append(f"Reference: {locomo.get('reference', 'N/A')}")
        lines.append(f"Description: {locomo.get('description', 'N/A')}")
        lines.append("")
        if "locomo_avg_accuracy_pct" in summary:
            slo_met = summary.get("locomo_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Avg accuracy: {summary['locomo_avg_accuracy_pct']}%  [Threshold: >= 80%]  [{status}]")
        if "locomo_avg_latency_ms" in summary:
            lines.append(f"  Avg latency: {summary['locomo_avg_latency_ms']} ms  [Threshold: <= 500ms]")
        lines.append("")

    hotpotqa = benchmarks.get("hotpotqa", {})
    if hotpotqa:
        lines.append("--- HotpotQA Knowledge Base (Phase 3b) ---")
        lines.append(f"Reference: {hotpotqa.get('reference', 'N/A')}")
        lines.append(f"Description: {hotpotqa.get('description', 'N/A')}")
        lines.append("")
        if "hotpotqa_avg_accuracy_pct" in summary:
            slo_met = summary.get("hotpotqa_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Avg accuracy: {summary['hotpotqa_avg_accuracy_pct']}%  [Threshold: >= 72%]  [{status}]")
        if "hotpotqa_avg_latency_ms" in summary:
            lines.append(f"  Avg latency: {summary['hotpotqa_avg_latency_ms']} ms")
        lines.append("")

    micro = benchmarks.get("micro", {})
    if micro:
        lines.append("--- Micro Benchmarks (Phase 3c) ---")
        lines.append(f"Reference: {micro.get('reference', 'N/A')}")
        lines.append("")
        if "embedding_throughput_per_sec" in summary:
            slo_met = summary.get("embedding_throughput_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Embedding throughput: {summary['embedding_throughput_per_sec']} ops/sec  [Threshold: >= 50]  [{status}]")
        if "retrieval_qps" in summary:
            slo_met = summary.get("retrieval_qps_slo_met", False)
            status = "PASS" if slo_met else "FAIL"
            lines.append(f"  Retrieval QPS: {summary['retrieval_qps']} queries/sec  [Threshold: >= 10]  [{status}]")
        if "retrieval_avg_latency_ms" in summary:
            lines.append(f"  Retrieval avg latency: {summary['retrieval_avg_latency_ms']} ms")
        if "context_L0_avg_ms" in summary:
            lines.append(f"  Context tier L0: {summary['context_L0_avg_ms']} ms")
            lines.append(f"  Context tier L1: {summary['context_L1_avg_ms']} ms")
            lines.append(f"  Context tier L2: {summary['context_L2_avg_ms']} ms")
        lines.append("")

    if summary:
        lines.append("--- Overall Summary ---")
        if "max_throughput" in summary:
            mt = summary["max_throughput"]
            lines.append(f"  Max throughput: {mt['value']} {mt['unit']} ({mt['name']})")
        if "avg_throughput" in summary:
            lines.append(f"  Avg throughput: {summary['avg_throughput']} ops/sec")
        if "max_latency" in summary:
            ml = summary["max_latency"]
            lines.append(f"  Max latency: {ml['value']} {ml['unit']} ({ml['name']})")
        if "avg_latency" in summary:
            lines.append(f"  Avg latency: {summary['avg_latency']} ms")

    lines.append("")
    lines.append("=" * 70)
    lines.append("End of Summary")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    with open(args.output, 'w') as f:
        f.write(summary_text)
    print(f"[SUMMARY] Saved to {args.output}")


if __name__ == "__main__":
    main()