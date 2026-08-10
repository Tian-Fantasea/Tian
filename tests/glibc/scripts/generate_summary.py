#!/usr/bin/env python3
import sys
import json
from datetime import datetime, timezone


def generate_summary(input_json, output_file):
    with open(input_json) as f:
        data = json.load(f)

    lines = []
    lines.append("=" * 70)
    lines.append("  glibc benchtests Performance Benchmark Report")
    lines.append("=" * 70)
    lines.append(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"  Test Time: {data.get('test_time', data.get('timestamp', 'N/A'))}")
    lines.append("")

    env = data.get("environment", {})
    if env:
        lines.append("  --- Environment ---")
        lines.append(f"  Architecture:      {env.get('architecture', 'N/A')}")
        lines.append(f"  Model:             {env.get('Model', 'N/A')}")
        lines.append(f"  CPU Model:         {env.get('cpu_model', 'N/A')}")
        lines.append(f"  CPU Cores:         {env.get('cpu_cores', 'N/A')}")
        lines.append(f"  glibc Version:     {env.get('software_version', 'N/A')}")
        lines.append(f"  OS:                {env.get('os', 'N/A')}")
        lines.append(f"  Kernel:           {env.get('kernel', 'N/A')}")
        lines.append("")

    benchmarks = data.get("benchmarks", {})
    primary = benchmarks.get("primary", {})
    if primary:
        lines.append("  --- glibc benchtests (Primary) ---")
        lines.append(f"  Description:       {primary.get('description', 'N/A')}")
        lines.append(f"  Timing method:     {primary.get('parameters', {}).get('timing_method', 'N/A')}")
        lines.append(f"  Benchsets:         {primary.get('parameters', {}).get('benchsets', 'N/A')}")
        lines.append("")
        rs = primary.get("results_summary", {})
        for benchset_name in sorted(rs.keys()):
            benchset_data = rs[benchset_name]
            if not isinstance(benchset_data, dict):
                continue
            if "error" in benchset_data:
                lines.append(f"  [{benchset_name}]: ERROR - {benchset_data['error']}")
                continue
            timing_type = benchset_data.get("timing_type", "N/A")
            functions = benchset_data.get("functions", {})
            lines.append(f"  [{benchset_name}] ({timing_type}, {len(functions)} functions)")
            sorted_funcs = sorted(functions.keys())
            for func_name in sorted_funcs[:20]:
                func_data = functions[func_name]
                if isinstance(func_data, dict) and func_data:
                    lines.append(f"    {func_name:<30}: mean={func_data.get('mean_ns', 'N/A')} ns")
            if len(functions) > 20:
                lines.append(f"    ... and {len(functions) - 20} more functions")
            lines.append("")

    micro = benchmarks.get("micro", {})
    if micro:
        lines.append("  --- Micro Benchmarks ---")
        mresults = micro.get("results", {})
        if isinstance(mresults, dict):
            pthread = mresults.get("pthread_scaling", {})
            if isinstance(pthread, dict) and pthread:
                lines.append(f"  pthread lock/mutex scaling ({len(pthread)} functions):")
                for fn in sorted(pthread.keys())[:15]:
                    e = pthread[fn]
                    if isinstance(e, dict) and e:
                        lines.append(f"    {fn:<30}: mean={e.get('mean_ns', 'N/A')} ns")
                if len(pthread) > 15:
                    lines.append(f"    ... and {len(pthread) - 15} more")
            malloc = mresults.get("malloc_scaling", {})
            if isinstance(malloc, dict) and malloc:
                lines.append(f"  malloc thread scaling ({len(malloc)} functions):")
                for fn in sorted(malloc.keys())[:15]:
                    e = malloc[fn]
                    if isinstance(e, dict) and e:
                        lines.append(f"    {fn:<30}: mean={e.get('mean_ns', 'N/A')} ns")
        lines.append("")

    summary = data.get("summary", {})
    if summary:
        lines.append("  --- Overall Summary ---")
        if "benchset_count" in summary:
            lines.append(f"    Benchsets run:        {summary['benchset_count']}")
        if "function_count" in summary:
            lines.append(f"    Functions measured:   {summary['function_count']}")
        if "avg_mean_ns" in summary:
            lines.append(f"    Avg mean timing:      {summary['avg_mean_ns']} ns")
        if "max_mean_ns" in summary:
            lines.append(f"    Max mean timing:      {summary['max_mean_ns']} ns")
        if "min_timing_ns" in summary:
            lines.append(f"    Min timing (fastest): {summary['min_timing_ns']} ns")
        if "pthread_count" in summary:
            lines.append(f"    pthread functions:    {summary['pthread_count']}")
        if "pthread_avg_mean_ns" in summary:
            lines.append(f"    pthread avg timing:   {summary['pthread_avg_mean_ns']} ns")
        if "malloc_count" in summary:
            lines.append(f"    malloc functions:     {summary['malloc_count']}")
        if "malloc_avg_mean_ns" in summary:
            lines.append(f"    malloc avg timing:    {summary['malloc_avg_mean_ns']} ns")
        lines.append("")

    lines.append("=" * 70)
    lines.append("  Report generated by glibc benchtests Performance Benchmark Workflow")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    with open(output_file, "w") as f:
        f.write(summary_text)
    print(summary_text)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_summary.py <input_json> <output_file>")
        sys.exit(1)
    generate_summary(sys.argv[1], sys.argv[2])
