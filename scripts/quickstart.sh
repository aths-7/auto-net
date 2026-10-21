#!/usr/bin/env bash
# 一键：认证 -> 开自启动（Linux/macOS）
set -euo pipefail

cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}

echo "[1/3] 认证测试..."
"$PY" -m campusnet login || {
    echo
    echo "认证失败，先排障：$PY -m campusnet doctor"
    exit 1
}

echo
echo "[2/3] 开启开机自启动..."
"$PY" -m campusnet autostart on

echo
echo "[3/3] 启动守护进程..."
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user restart campusnet.service
    echo "已由 systemd 托管：systemctl --user status campusnet"
else
    nohup "$PY" -m campusnet daemon --quiet >/dev/null 2>&1 &
    echo "已后台启动，pid $!"
fi

echo
echo "完成。状态：$PY -m campusnet status"
