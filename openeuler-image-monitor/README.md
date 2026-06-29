# openEuler Docker Image Monitor

自动监控 openEuler/openeuler-docker-images 仓库的 PR 合入情况，检查对应镜像是否已推送到 DockerHub，并根据 SKILL.md 模板为已推送的软件自动生成性能测试脚手架，可选地在 Linux VM 上执行测试脚本。

## 快速开始

### 1. 安装依赖

```bash
pip3 install requests pyyaml
```

### 2. 运行

```bash
cd openeuler-image-monitor
python3 -m src.main -c config.yaml
```

加 `-v` 开启详细日志：

```bash
python3 -m src.main -c config.yaml -v
```

### 3. 查看结果

报告统一存放在 `results/<执行时间>/` 目录下：

```
results/
  20260629_11123/
    report.json               ← PR 监控 JSON 报告
    report.txt                ← PR 监控文本报告
    test_generation.json      ← 脚手架生成报告（如启用）
    test_generation.txt       ← 脑手架生成文本报告（如启用）
    test_execution.json       ← 测试执行报告（如启用）
    test_execution.txt        ← 测试执行文本报告（如启用）
```

```bash
# 查看最新报告
ls -t results/ | head -1

# 查看未推送的镜像
sqlite3 state.db "SELECT pr_number, software, reason FROM dockerhub_status WHERE pushed=0"

# 查看最近处理的 PR
sqlite3 state.db "SELECT pr_number, software, version, os_version, source FROM pr_tracking ORDER BY pr_number DESC LIMIT 10"
```

## 配置说明 (config.yaml)

```yaml
gitcode:
  base_url: "https://gitcode.com/api/v5"
  repo_owner: "openeuler"
  repo_name: "openeuler-docker-images"
  access_token: ""                           # 可选，私有仓库或有速率限制时填写

dockerhub:
  base_url: "https://hub.docker.com/v2"
  namespace: "openeuler"
  image_prefix: "openeuler"

verification:
  enabled: false                # 是否启用 docker pull 验证
  ssh_host: ""                  # Linux VM 的 IP 地址
  ssh_user: ""                  # SSH 用户名
  ssh_port: 22                  # SSH 端口
  ssh_key_path: ""              # SSH 密钥路径
  docker_pull_timeout: 600      # 单个镜像拉取超时秒数

schedule:
  interval_minutes: 60          # 定时运行间隔（用于 cron）
  lookback_hours: 168           # 每次回溯多少小时的已合并 PR (168=7天)

test_generation:
  enabled: true                 # 是否启用测试脚手架生成
  tests_dir: "../tests"         # tests 目录路径（相对于项目根目录）
  reference_software: "faiss"   # 参考软件，复制其通用脚本作为模板
  docker_pull: false            # 是否在生成脚手架前 docker pull 验证镜像

test_runner:
  enabled: false                # 是否启用测试执行（在 Linux VM 上改为 true）
  timeout: 3600                 # 单个软件最长执行时间（秒）

state:
  db_path: "state.db"           # SQLite 数据库路径
```

### Docker Pull 验证 (verification)

**远程验证（SSH）**：脚本通过 SSH 连接到 VM 执行 `docker pull`，验证后自动 `docker rmi` 清理。

**本地验证**：如果脚本直接运行在有 Docker 的本机上，修改 `src/main.py` 行 185：

```python
verification = verifier.verify_local_pull(dh_cfg["namespace"], software, tag)
```

### 测试脚手架生成 (test_generation)

当 `enabled: true` 时，对每个已推送到 DockerHub 但尚未在 tests 目录有测试的软件：

1. 从参考软件（默认 faiss）复制通用脚本：`json_helper.py`、`aggregate_results.py`、`generate_summary.py`
2. 根据软件类别生成对应的基准脚本：
   - ANN/vector_search 类 → `benchmark_ann.py`
   - database/kv_store/cache 类 → `benchmark_kv.py`
   - 其他 → `benchmark_generic.py`
3. 生成 `micro_benchmark.py` 骨架
4. 生成 `<software>_test.sh` 主测试脚本（4阶段生命周期 + shUnit2 断言）
5. 创建 `results/<version>/` 目录

已有测试的软件自动跳过，不会覆盖。

### 测试执行 (test_runner)

当 `enabled: true` 时（建议在 Linux VM 上启用），对每个已推送到 DockerHub 的软件：

1. 检查 `results/<version>/` 是否已有完整6个产物文件，有则跳过
2. 执行 `bash <software>_test.sh`，设置 `SOFTWARE_VERSION` 环境变量
3. 超时自动终止（默认3600秒）
4. 执行完成后检查产物完整性，标记状态：completed / partial / timeout / error

## 软件信息提取策略

脚本按优先级提取软件名、版本和 OS 信息：

| 优先级 | 策略 | 说明 | 示例 |
|--------|------|------|------|
| 1 | Dockerfile 路径解析 | 从变更文件路径 `{分类}/{软件}/{版本}/{OS}/Dockerfile` 中提取 | `HPC/seissol/202103_Sumatra/24.03-lts-sp3/Dockerfile` |
| 2 | tests 路径解析 | 对纯测试脚本 PR，从 `tests/{软件}/` 中提取 | `tests/openviking/results/0.4.4/` |
| 3 | PR 标题解析 | 从标题正则匹配 `【自动升级】xxx容器镜像升级至yyy` 等 | `【自动升级】lucene容器镜像升级至10.5.0版本.` |
| 4 | PR 正文表格 | 从 body 中匹配 `| Application version | ... |` 表格 | `| 10.5.0 | 24.03-lts-sp3 |` |

## DockerHub Tag 匹配

仓内 OS 版本与 DockerHub tag 后缀的映射：

| 仓内 OS 版本 | DockerHub tag 后缀 |
|--------------|--------------------|
| 24.03-lts-sp3 | oe2403sp3 |
| 24.03-lts-sp2 | oe2403sp2 |
| 24.03-lts-sp1 | oe2403sp1 |
| 24.03-lts | oe2403lts |
| 22.03-lts-sp3 | oe2203sp3 |
| 22.03-lts-sp2 | oe2203sp2 |
| 22.03-lts-sp1 | oe2203sp1 |
| 22.03-lts | oe2203lts |
| 20.03-lts-sp3 | oe2003sp3 |
| 20.03-lts-sp1 | oe2003sp1 |
| 20.03-lts | oe2003lts |

完整 tag 格式：`{软件版本}-{OS后缀}`，例如 `7.22-oe2403sp3`。

## 项目结构

```
openeuler-image-monitor/
├── config.yaml                 # 配置文件
├── requirements.txt            # Python 依赖
├── __main__.py                 # 模块入口
├── src/
│   ├── main.py                 # 主流程编排、数据库、报告生成
│   ├── gitcode_client.py       # GitCode API 客户端 + 软件信息提取
│   ├── dockerhub_client.py     # DockerHub API 客户端 + tag 匹配
│   ├── docker_verifier.py      # SSH 远程 / 本地 docker pull 验证
│   ├── test_generator.py       # 测试脚手架生成（基于 SKILL.md 模板）
│   └── test_runner.py          # 测试脚本本地执行 + 结果检查
├── results/                     # 报告输出目录
│   └── <执行时间>/             # 如 20260629_1112/
│       ├── report.json          # PR 监控报告
│       ├── report.txt           # PR 监控文本报告
│       ├── test_generation.json # 脚手架生成报告（可选）
│       ├── test_generation.txt  # 脚手架生成文本报告（可选）
│       ├── test_execution.json  # 测试执行报告（可选）
│       └── test_execution.txt   # 测试执行文本报告（可选）
└── state.db                     # SQLite 状态库（自动生成）
```

## 定时运行 (cron)

```bash
crontab -e
# 每30分钟执行一次
*/30 * * * * cd /path/to/openeuler-image-monitor && python3 -m src.main -c config.yaml >> monitor.log 2>&1
```

## 清理重新运行

```bash
rm state.db
python3 -m src.main -c config.yaml
```

## 部署到 Linux VM

```bash
# 复制项目和 tests 目录到 VM
scp -r /path/to/openeuler-image-monitor root@<VM_IP>:/root/
scp -r /path/to/tests root@<VM_IP>:/root/

# 在 VM 上
cd /root/openeuler-image-monitor
pip3 install requests pyyaml

# 启用测试执行
# 编辑 config.yaml，将 test_runner.enabled 改为 true
python3 -m src.main -c config.yaml
```
