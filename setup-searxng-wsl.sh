#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y git python3-dev python3-venv python-is-python3 build-essential libxslt1-dev zlib1g-dev libffi-dev libssl-dev

ROOT="$HOME/searxng"
SOURCE="$ROOT/searxng-src"
VENV="$ROOT/searx-pyenv"
CONFIG="$HOME/.config/searxng/settings.yml"
CONTROL="$HOME/.local/bin/kittysearch-searxng"

mkdir -p "$ROOT" "$(dirname "$CONFIG")" "$(dirname "$CONTROL")"
if [ ! -d "$SOURCE/.git" ]; then
    git clone https://github.com/searxng/searxng.git "$SOURCE"
fi

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install --upgrade pyyaml msgspec typing-extensions pybind11
"$VENV/bin/python" -m pip install --use-pep517 --no-build-isolation -e "$SOURCE"

if [ ! -f "$CONFIG" ]; then
    SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    cat > "$CONFIG" <<EOF
use_default_settings: true
server:
  secret_key: "$SECRET"
  bind_address: 127.0.0.1
  port: 8080
  limiter: false
search:
  formats:
    - html
    - json
EOF
    chmod 600 "$CONFIG"
fi

cat > "$CONTROL" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$HOME/searxng"
VENV="$ROOT/searx-pyenv"
CONFIG="$HOME/.config/searxng/settings.yml"
PID="$ROOT/kittysearch-searxng.pid"
LOG="$ROOT/kittysearch-searxng.log"

case "${1:-}" in
  start)
    if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
      exit 0
    fi
    rm -f "$PID"
    cd "$ROOT/searxng-src"
    export SEARXNG_SETTINGS_PATH="$CONFIG"
    nohup "$VENV/bin/python" -m searx.webapp >> "$LOG" 2>&1 </dev/null &
    echo $! > "$PID"
    ;;
  stop)
    if [ -f "$PID" ]; then
      pid="$(cat "$PID")"
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
      fi
      rm -f "$PID"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop}" >&2
    exit 2
    ;;
esac
EOF
chmod 700 "$CONTROL"

echo 'SearXNG installed. Start it from KittySearch using the WSL2 mode.'
