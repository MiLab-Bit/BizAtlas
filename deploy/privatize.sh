#!/usr/bin/env bash
# privatize.sh — BizAtlas 私有化部署一键准备
# 生成强随机 AUTH_SECRET / BOOTSTRAP_TOKEN / INTEGRITY_SECRET（若 .env 缺失），
# 并确认鉴权处于开启状态。幂等：已设值不覆盖。
set -euo pipefail

cd "$(dirname "$0")"
ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
  echo "[privatize] .env 不存在，从模板创建"
  cp .env.example "$ENV_FILE"
fi

gen() { python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

set_if_empty() {
  local key="$1"
  if ! grep -qE "^${key}=" "$ENV_FILE" || grep -qE "^${key}=$" "$ENV_FILE"; then
    local val; val="$(gen)"
    if grep -qE "^${key}=" "$ENV_FILE"; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
      echo "${key}=${val}" >> "$ENV_FILE"
    fi
    echo "[privatize] 生成 ${key}"
  else
    echo "[privatize] ${key} 已存在，保留"
  fi
}

set_if_empty BIZATLAS_AUTH_SECRET
set_if_empty BIZATLAS_BOOTSTRAP_TOKEN
set_if_empty BIZATLAS_INTEGRITY_SECRET

# 强制鉴权开启（私有化最小权限）
sed -i 's|^BIZATLAS_AUTH_DISABLED=.*|BIZATLAS_AUTH_DISABLED=false|' "$ENV_FILE"

echo "[privatize] 完成。下一步："
echo "  docker compose up -d"
echo "  首管理员引导：POST /v1/admin/bootstrap （带 BIZATLAS_BOOTSTRAP_TOKEN）"
