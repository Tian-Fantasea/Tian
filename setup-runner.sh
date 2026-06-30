#!/bin/bash
set -e

REPO_URL="git@github.com:Tian-Fantasea/Tian.git"
INSTALL_DIR="/root/Tian"

echo "=== openEuler Image Monitor - Self-hosted Runner Setup ==="

echo "[1/6] Installing Docker..."
if command -v docker >/dev/null 2>&1; then
    echo "Docker already installed: $(docker --version)"
else
    yum install -y docker || apt-get install -y docker.io
    systemctl enable docker && systemctl start docker
    echo "Docker installed: $(docker --version)"
fi

echo "[2/6] Installing Python3 and dependencies..."
if command -v python3 >/dev/null 2>&1; then
    echo "Python3 already installed: $(python3 --version)"
else
    yum install -y python3 python3-pip || apt-get install -y python3 python3-pip python3-full
fi

VENV_DIR="${INSTALL_DIR}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
    echo "Created virtual environment at ${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
pip install requests pyyaml
echo "Dependencies installed in venv"

echo "[3/6] Cloning repository..."
if [ -d "${INSTALL_DIR}" ]; then
    echo "Repository already exists, pulling latest..."
    cd "${INSTALL_DIR}" && git pull || true
else
    git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

echo "[4/6] Checking project structure..."
cd "${INSTALL_DIR}"
ls openeuler-image-monitor/src/main.py || { echo "ERROR: openeuler-image-monitor not found"; exit 1; }
ls tests/faiss/scripts/json_helper.py || { echo "ERROR: tests reference not found"; exit 1; }
echo "Project structure OK"

echo "[5/6] Configuring for local execution..."
cd openeuler-image-monitor
if [ -f config.yaml ]; then
    python3 -c "
import yaml
with open('config.yaml') as f:
    c = yaml.safe_load(f)
c['verification']['enabled'] = True
c['test_generation']['docker_pull'] = True
c['test_runner']['enabled'] = True
with open('config.yaml', 'w') as f:
    yaml.dump(c, f, default_flow_style=False)
print('config.yaml updated for local execution')
"
fi

echo "[6/6] Setting up cron (every 30 minutes)..."
CRON_LINE="*/30 * * * * source ${INSTALL_DIR}/.venv/bin/activate && cd ${INSTALL_DIR}/openeuler-image-monitor && python3 -m src.main -c config.yaml >> ${INSTALL_DIR}/monitor.log 2>&1"
(crontab -l 2>/dev/null | grep -v "openeuler-image-monitor"; echo "${CRON_LINE}") | crontab -
echo "Cron job installed. Monitor will run every 30 minutes."

echo ""
echo "=== Setup Complete ==="
echo "Manual run:  cd ${INSTALL_DIR}/openeuler-image-monitor && source ${INSTALL_DIR}/.venv/bin/activate && python3 -m src.main -c config.yaml"
echo "Verbose run: cd ${INSTALL_DIR}/openeuler-image-monitor && source ${INSTALL_DIR}/.venv/bin/activate && python3 -m src.main -c config.yaml -v"
echo "View log:    tail -f ${INSTALL_DIR}/monitor.log"
echo "View DB:     sqlite3 ${INSTALL_DIR}/openeuler-image-monitor/state.db"
echo ""
echo "=== GitHub Actions Self-hosted Runner ==="
echo "To add this VM as a GitHub Actions runner:"
echo "  1. Go to https://github.com/Tian-Fantasea/Tian/settings/actions/runners/new"
echo "  2. Choose 'Self-hosted' + 'Linux' + 'ARM64'"
echo "  3. Run the configuration commands shown on the page"
echo "  4. Install as service: ./svc.sh install && ./svc.sh start"
