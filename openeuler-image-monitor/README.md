# openEuler Docker Image Monitor

自动监控 openEuler/openeuler-docker-images 仓库的 PR 合入情况，检查对应镜像是否已推送到 DockerHub，并可选地在 Linux VM 上执行 docker pull 验证。

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

- JSON 报告：`report_YYYYMMDD_HHMMSS.json`
- 状态数据库：`state.db`（增量追踪，已处理的 PR 下次自动跳过）

```bash
# 查看最新报告
cat report_*.json | python3 -m json.tool

# 查看未推送的镜像
sqlite3 state.db "SELECT pr_number, software, reason FROM dockerhub_status WHERE pushed=0"

# 查看最近处理的 PR
sqlite3 state.db "SELECT pr_number, software, version, os_version, source FROM pr_tracking ORDER BY pr_number DESC LIMIT 10"
```

## 配置说明 (config.yaml)

### GitCode API

```yaml
gitcode:
  base_url: "https://gitcode.com/api/v5"   # GitCode API 地址
  repo_owner: "openeuler"                    # 仓库所属组织
  repo_name: "openeuler-docker-images"       # 仓库名
  access_token: ""                           # 可选，私有仓库或有速率限制时填写
```

### DockerHub API

```yaml
dockerhub:
  base_url: "https://hub.docker.com/v2"      # DockerHub API 地址
  namespace: "openeuler"                      # 镜像组织名 (openeuler/xxx)
```

### Docker Pull 验证

```yaml
verification:
  enabled: false                # 是否启用 docker pull 验证
  ssh_host: ""                  # Linux VM 的 IP 地址
  ssh_user: ""                  # SSH 用户名
  ssh_port: 22                  # SSH 端口
  ssh_key_path: ""              # SSH 密钥路径
  docker_pull_timeout: 600      # 单个镜像拉取超时秒数
```

**远程验证（SSH）**：脚本通过 SSH 连接到 VM 执行 `docker pull`，验证后自动 `docker rmi` 清理。

**本地验证**：如果脚本直接运行在有 Docker 的本机上，修改 `src/main.py` 行 185：

```python
verification = verifier.verify_local_pull(dh_cfg["namespace"], software, tag)
```

### 定时策略

```yaml
schedule:
  interval_minutes: 60          # 定时运行间隔（用于 cron）
  lookback_hours: 168           # 每次回溯多少小时的已合并 PR (168=7天)
```

### 状态存储

```yaml
state:
  db_path: "state.db"           # SQLite 数据库路径
```

## 定时运行 (cron)

```bash
crontab -e
# 每小时执行一次
0 * * * * cd /path/to/openeuler-image-monitor && python3 -m src.main -c config.yaml >> monitor.log 2>&1
```

## 清理重新运行

```bash
rm state.db report_*.json
python3 -m src.main -c config.yaml
```

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
│   └── docker_verifier.py      # SSH 远程 / 本地 docker pull 验证
├── state.db                    # SQLite 状态库（自动生成）
└── report_*.json               # JSON 报告（每次运行自动生成）
```

## 部署到 Linux VM

```bash
# 从本机复制到 VM
scp -r /Users/zhang/openeuler-image-monitor root@<VM_IP>:/root/

# 在 VM 上
cd /root/openeuler-image-monitor
pip3 install requests pyyaml
python3 -m src.main -c config.yaml
```
