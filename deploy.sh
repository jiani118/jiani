#!/usr/bin/env bash
# 用法：
#   sudo bash deploy.sh                 # 只用 IP:8000 访问
#   sudo bash deploy.sh 你的域名.com    # 同时配置 Caddy 自动 HTTPS（域名需先解析到本机 IP）
set -euo pipefail

DOMAIN="${1:-}"
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 或 sudo 运行：sudo bash deploy.sh" >&2
  exit 1
fi

echo "==> 检查 Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

if [ -n "$DOMAIN" ]; then
  echo "==> 安装并配置 Caddy（域名：$DOMAIN）"
  if ! command -v caddy >/dev/null 2>&1; then
    apt-get update
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update
    apt-get install -y caddy
  fi
  cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
    reverse_proxy localhost:8000
}
CADDY
  export BIND=127.0.0.1   # 有域名时只允许本机的 Caddy 访问 8000 端口
fi

echo "==> 构建并启动"
docker compose up -d --build

if [ -n "$DOMAIN" ]; then
  systemctl enable caddy >/dev/null 2>&1 || true
  systemctl restart caddy
  echo
  echo "完成！稍等片刻后访问：https://$DOMAIN"
  echo "请确认云服务商的安全组已放行 80 和 443 端口。"
else
  echo
  echo "完成！访问：http://服务器IP:8000"
  echo "打不开的话，请在云服务商的安全组/防火墙放行 8000 端口。"
fi
