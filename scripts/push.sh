#!/usr/bin/env bash
# 推到 GitHub。用法：
#   ./scripts/push.sh                         # 用默认 SSH 地址
#   ./scripts/push.sh git@github.com:me/repo.git
set -euo pipefail

cd "$(dirname "$0")/.."

REMOTE_URL=${1:-git@github.com:aths-7/campus-net-autologin.git}
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)

if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL"
else
    git remote add origin "$REMOTE_URL"
fi

echo "远程: $REMOTE_URL"
echo "分支: $BRANCH"
echo "测试 SSH 连通性..."
if ! ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "SSH 认证没通过 —— 先把公钥加到 GitHub，或者改用 HTTPS + PAT。"
    echo "生成密钥：ssh-keygen -t ed25519 -C \"your@email\""
    echo "公钥内容：cat ~/.ssh/id_ed25519.pub"
    exit 1
fi

git push -u origin "$BRANCH"
echo "✓ 已推送到 $REMOTE_URL"
