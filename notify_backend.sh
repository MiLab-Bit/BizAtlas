#!/bin/bash
CF_TOKEN=$(cat /opt/bizatlas/.cf_token)
ACCT="1ca517964ac0b2a7e6eb56e651c6b817"
NS="a15720a5a4514907ad25db0f919a2150"
LOG=/tmp/bizatlas_tunnel.log
rm -f "$LOG"
nohup /usr/local/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8080 > "$LOG" 2>&1 &
PID=$!
URL=""
for i in $(seq 1 40); do
  sleep 1
  U=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | tail -1)
  if [ -n "$U" ]; then URL="$U"; break; fi
done
if [ -n "$URL" ]; then
  curl -sS -X PUT -H "Authorization: Bearer $CF_TOKEN" --data "$URL" \
    "https://api.cloudflare.com/client/v4/accounts/$ACCT/storage/kv/namespaces/$NS/values/bizatlas_backend_url" || true
  echo "NOTIFY: wrote $URL to KV"
fi
wait $PID
