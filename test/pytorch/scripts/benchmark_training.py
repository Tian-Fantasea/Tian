#!/usr/bin/env python3
import json
import time
import argparse
import datetime
import os
import torch
import torch.nn as nn
import torch.optim as optim

def load_or_create_json(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def write_results_section(filepath, section, data):
    results = load_or_create_json(filepath)
    results[section] = data
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)

SCALE_MAP = {
    "1M": 1000000,
    "10M": 10000000,
}

class SimpleMLP(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim),
        )
    def forward(self, x):
        return self.net(x)

class SimpleCNN(nn.Module):
    def __init__(self, channels=3):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(channels, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(128 * 4 * 4, 256),
            nn.ReLU(),
            nn.Linear(256, 10),
        )
    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)

class SimpleTransformer(nn.Module):
    def __init__(self, vocab_size=10000, d_model=256, nhead=4, num_layers=2, max_seq_len=64):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_encoding = nn.Parameter(torch.randn(1, max_seq_len, d_model) * 0.1)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Linear(d_model, vocab_size)
    def forward(self, x):
        x = self.embedding(x) + self.pos_encoding[:, :x.size(1)]
        x = self.transformer(x)
        return self.fc(x)

MODEL_CONFIGS = {
    "MLP_128_256": {
        "model_fn": lambda: SimpleMLP(128, 256, 10),
        "input_fn": lambda bs: (torch.randn(bs, 128), torch.randint(0, 10, (bs))),
        "loss_fn": nn.CrossEntropyLoss(),
        "description": "3-layer MLP: 128->256->256->10, CrossEntropy",
        "metric_unit": "samples/sec",
    },
    "CNN_ResNetLike_32x32": {
        "model_fn": lambda: SimpleCNN(channels=3),
        "input_fn": lambda bs: (torch.randn(bs, 3, 32, 32), torch.randint(0, 10, (bs))),
        "loss_fn": nn.CrossEntropyLoss(),
        "description": "Simple CNN on 32x32 images (CIFAR-like), CrossEntropy",
        "metric_unit": "images/sec",
    },
    "Transformer_4head_2layer": {
        "model_fn": lambda: SimpleTransformer(vocab_size=10000, d_model=256, nhead=4, num_layers=2, max_seq_len=64),
        "input_fn": lambda bs: (torch.randint(0, 10000, (bs, 64)), None),
        "loss_fn": None,
        "description": "2-layer Transformer encoder, d_model=256, 4 heads, seq_len=64",
        "metric_unit": "sequences/sec",
    },
}

BATCH_SIZES = [1, 8, 32, 64, 128]

def benchmark_model(config_name, config, batch_size, iterations):
    model = config["model_fn"]()
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = config["loss_fn"]

    inputs, targets = config["input_fn"](batch_size)
    if loss_fn is None and targets is None:
        output = model(inputs)
        loss = output.sum()

    warmup_steps = 10
    for _ in range(warmup_steps):
        optimizer.zero_grad()
        output = model(inputs)
        if loss_fn is not None and targets is not None:
            loss = loss_fn(output, targets)
        else:
            loss = output.sum()
        loss.backward()
        optimizer.step()

    torch.cpu.synchronize()

    times = []
    for i in range(iterations):
        optimizer.zero_grad()
        start = time.time()
        output = model(inputs)
        if loss_fn is not None and targets is not None:
            loss = loss_fn(output, targets)
        else:
            loss = output.sum()
        loss.backward()
        optimizer.step()
        torch.cpu.synchronize()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    throughput = batch_size / avg_time
    return round(avg_time * 1000, 4), round(throughput, 2)

def benchmark_model_inference(config_name, config, batch_size, iterations):
    model = config["model_fn"]()
    model.eval()

    inputs, _ = config["input_fn"](batch_size)

    warmup_steps = 10
    with torch.no_grad():
        for _ in range(warmup_steps):
            output = model(inputs)
    torch.cpu.synchronize()

    times = []
    with torch.no_grad():
        for i in range(iterations):
            start = time.time()
            output = model(inputs)
            torch.cpu.synchronize()
            elapsed = time.time() - start
            times.append(elapsed)

    avg_time = sum(times) / len(times)
    throughput = batch_size / avg_time
    return round(avg_time * 1000, 4), round(throughput, 2)

def main():
    parser = argparse.ArgumentParser(description='PyTorch Training & Inference Throughput Benchmark')
    parser.add_argument('--results-dir', required=True)
    parser.add_argument('--iterations', type=int, default=1)
    parser.add_argument('--data-scale', default='1M', choices=list(SCALE_MAP.keys()))
    parser.add_argument('--results-json', required=True)
    parser.add_argument('--section', default='training_benchmark')
    args = parser.parse_args()

    iterations = args.iterations

    print(f'[TRAINING] PyTorch training/inference throughput benchmark on ARM64 CPU...')
    print(f'[TRAINING] torch threads: {torch.get_num_threads()}')

    all_results = {}

    for config_name, config in MODEL_CONFIGS.items():
        print(f'[TRAINING] Model: {config_name}: {config["description"]}')

        for bs in BATCH_SIZES:
            label = f"{config_name}_batch{bs}_train"
            print(f'[TRAINING]   Training batch_size={bs}...')
            try:
                avg_ms, throughput = benchmark_model(config_name, config, bs, iterations)
                all_results[label] = {
                    "avg_time_ms": avg_ms,
                    "throughput": throughput,
                    "unit": config["metric_unit"],
                    "batch_size": bs,
                    "mode": "training",
                }
                print(f'[TRAINING]     time={avg_ms}ms, throughput={throughput} {config["metric_unit"]}')
            except Exception as e:
                print(f'[TRAINING]     ERROR: {e}')
                all_results[label] = {"error": str(e), "batch_size": bs, "mode": "training"}

            label_inf = f"{config_name}_batch{bs}_inference"
            print(f'[TRAINING]   Inference batch_size={bs}...')
            try:
                model = config["model_fn"]()
                model.eval()
                inputs, _ = config["input_fn"](bs)

                with torch.no_grad():
                    for _ in range(10):
                        output = model(inputs)
                torch.cpu.synchronize()

                inf_times = []
                with torch.no_grad():
                    for i in range(iterations):
                        start = time.time()
                        output = model(inputs)
                        torch.cpu.synchronize()
                        elapsed = time.time() - start
                        inf_times.append(elapsed)

                avg_inf_time = sum(inf_times) / len(inf_times)
                inf_throughput = bs / avg_inf_time
                all_results[label_inf] = {
                    "avg_time_ms": round(avg_inf_time * 1000, 4),
                    "throughput": round(inf_throughput, 2),
                    "unit": config["metric_unit"],
                    "batch_size": bs,
                    "mode": "inference",
                }
                print(f'[TRAINING]     time={round(avg_inf_time*1000,4)}ms, throughput={round(inf_throughput,2)} {config["metric_unit"]}')
            except Exception as e:
                print(f'[TRAINING]     ERROR: {e}')
                all_results[label_inf] = {"error": str(e), "batch_size": bs, "mode": "inference"}

    output = {
        "benchmark": "training_inference",
        "description": "PyTorch model training and inference throughput benchmark on ARM64 CPU (MLP, CNN, Transformer)",
        "reference": "PyTorch models following MLPerf methodology (https://mlcommons.org/en/mlperf-training)",
        "timestamp": datetime.datetime.now().isoformat(),
        "performance_metrics": {
            "training_throughput": {
                "unit": "samples/images/sequences per second",
                "description": "Training throughput (forward + backward + optimizer step)"
            },
            "inference_throughput": {
                "unit": "samples/images/sequences per second",
                "description": "Inference-only throughput"
            },
            "latency_per_batch": {
                "unit": "milliseconds",
                "description": "Time per batch iteration"
            }
        },
        "dataset_info": {
            "name": "synthetic_random_data",
            "size": "batch sizes 1-128",
            "source": "torch.randn / torch.randint"
        },
        "parameters": {
            "iterations": iterations,
            "batch_sizes": BATCH_SIZES,
            "torch_threads": torch.get_num_threads(),
            "device": "cpu",
        },
        "model_configs": {name: {"description": cfg["description"], "unit": cfg["metric_unit"]} for name, cfg in MODEL_CONFIGS.items()},
        "results": all_results
    }

    write_results_section(args.results_json, args.section, output)

    print(f'[TRAINING] Results saved to: {args.results_json} (section: {args.section})')
    print('[TRAINING] Benchmark complete')

if __name__ == '__main__':
    main()
