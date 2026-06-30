# Tian

openEuler Docker 镜像监控 + 性能测试自动生成与执行平台。

## 项目结构

```
Tian/
├── .github/workflows/          # GitHub Actions 自动化
│   └── monitor-and-test.yml    # 定时监控+测试流水线
├── openeuler-image-monitor/    # 监控核心代码
│   ├── config.yaml             # 配置文件
│   ├── src/                    # Python 源码
│   └── results/                # 监控报告输出
├── tests/                      # 测试脚手架和结果
│   ├── faiss/                  # 参考软件（模板）
│   ├── hnswlib/                # 已有测试软件
│   └── <new_software>/         # 自动生成的测试
├── setup-runner.sh             # ARM64 VM 部署脚本
└── README.md
```

## 部署方式

### 方式1：本地 VM 部署（推荐测试）

在 ARM64 Linux VM（有 Docker）上运行：

```bash
bash setup-runner.sh
```

手动运行一次：

```bash
cd openeuler-image-monitor
python3 -m src.main -c config.yaml -v
```

### 方式2：GitHub Actions 部署

1. 在 ARM64 VM 上注册 self-hosted runner：
   - 打开 https://github.com/Tian-Fantasea/Tian/settings/actions/runners/new
   - 选择 Self-hosted + Linux + ARM64
   - 按页面指引执行配置命令

2. 配置 GitHub Secrets：
   - `GITCODE_ACCESS_TOKEN`: GitCode API token（可选）

3. Actions 会每 2 小时自动运行，或手动触发

### 环境变量覆盖

以下环境变量会自动覆盖 config.yaml 中的对应配置：

| 环境变量 | 覆盖字段 |
|----------|----------|
| `GITCODE_ACCESS_TOKEN` | gitcode.access_token |
| `VM_SSH_HOST` | verification.ssh_host |
| `VM_SSH_USER` | verification.ssh_user |
| `LOOKBACK_HOURS` | schedule.lookback_hours |
| `TEST_GENERATION_ENABLED` | test_generation.enabled |
| `TEST_RUNNER_ENABLED` | test_runner.enabled |
| `DOCKER_PULL_ENABLED` | test_generation.docker_pull |

## 流程说明

1. **监控** → 扫描 GitCode merged PR，提取软件名/版本/OS
2. **生成** → 对已推送到 DockerHub 的软件，批量生成测试脚手架
3. **执行** → 在 ARM64 VM 上 docker pull + benchmark + 汇报结果