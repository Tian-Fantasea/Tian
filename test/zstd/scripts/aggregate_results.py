#!/usr/bin/env python3
import json
import os
import sys
import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: aggregate_results.py <results_dir> <output_file>")
        sys.exit(1)

    results_dir = sys.argv[1]
    output_file = sys.argv[2]

    all_data = {}
    json_files = {
        'version_info.json': 'version_info',
        'benchmark_primary.json': 'primary_benchmark',
        'benchmark_secondary.json': 'secondary_benchmark',
        'micro_benchmark.json': 'micro_benchmark',
    }

    for filename, key in json_files.items():
        filepath = os.path.join(results_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
            all_data[key] = data
            print('[AGGREGATE] Loaded %s as %s' % (filename, key))
        else:
            print('[AGGREGATE] WARNING: %s not found, skipping' % filename)

    all_data["aggregation_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    all_data["software"] = "zstd"
    all_data["architecture"] = "arm64"

    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)

    print('[AGGREGATE] Results saved to: %s' % output_file)


if __name__ == '__main__':
    main()
