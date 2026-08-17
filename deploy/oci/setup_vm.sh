#!/usr/bin/env bash
set -Eeuo pipefail

exec 9>/tmp/factuality-ai-assessor-deploy.lock
if ! flock -n 9; then
    echo "ERROR: another deploy is already running on this VM." >&2
    exit 1
fi

APP_NAME="factuality-ai-assessor"
APP_DIR="/opt/${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}.env"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
REPO_ARCHIVE="https://github.com/lsotavio/challenge-alura-agente-factuality-ai-assessor/archive/refs/heads/main.tar.gz"
TEMP_DIR="$(mktemp -d /tmp/${APP_NAME}.XXXXXX)"

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT
trap 'echo "ERROR: deploy failed at line $LINENO" >&2' ERR

step() {
    echo
    echo "[$1/7] $2"
}

if [[ -z "${GEMINI_API_KEY_B64:-}" ]]; then
    echo "ERROR: Gemini API key was not supplied." >&2
    exit 1
fi

step 1 "Preparing 2 GB swap for the 1 GB VM"
sudo systemctl disable --now docker containerd 2>/dev/null || true
if sudo swapon --noheadings --show=NAME | grep -qx '/swapfile'; then
    echo "Swap is already active; keeping the existing swapfile."
else
    if [[ ! -f /swapfile ]]; then
        sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
    fi
    sudo swapon /swapfile
fi
if ! grep -q '^/swapfile ' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi
free -h

step 2 "Installing a lightweight managed Python 3.11 runtime"
UV_BIN="$HOME/.local/bin/uv"
if [[ ! -x "$UV_BIN" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
UV_PYTHON_DIR="/opt/${APP_NAME}-python"
sudo mkdir -p "$UV_PYTHON_DIR"
sudo chown opc:opc "$UV_PYTHON_DIR"
export UV_PYTHON_INSTALL_DIR="$UV_PYTHON_DIR"
"$UV_BIN" python install 3.11
"$UV_BIN" python find 3.11
if command -v restorecon >/dev/null 2>&1; then
    sudo restorecon -RF "$UV_PYTHON_DIR"
fi

step 3 "Downloading the current GitHub main branch"
mkdir -p "$TEMP_DIR/release"
curl --fail --location --retry 3 --connect-timeout 15 "$REPO_ARCHIVE" -o "$TEMP_DIR/repo.tar.gz"
tar -xzf "$TEMP_DIR/repo.tar.gz" --strip-components=1 -C "$TEMP_DIR/release"

step 4 "Creating the virtual environment and installing dependencies"
cd "$TEMP_DIR/release"
"$UV_BIN" venv --python 3.11 .venv
if [[ -f requirements-deploy.txt ]]; then
    "$UV_BIN" pip install --python .venv/bin/python --no-cache -r requirements-deploy.txt
else
    "$UV_BIN" pip install --python .venv/bin/python --no-cache \
        'streamlit>=1.36,<2' 'pypdf>=4,<7' 'pydantic>=2,<3' 'ddgs>=9,<10' 'google-genai>=2.0'
fi
./.venv/bin/python scripts/build_guidelines_index.py || echo "Warning: guideline index could not be generated; app will still start."

step 5 "Installing the application release"
sudo systemctl stop "$APP_NAME" 2>/dev/null || true
sudo rm -rf "${APP_DIR}.previous"
if [[ -d "$APP_DIR" ]]; then
    sudo mv "$APP_DIR" "${APP_DIR}.previous"
fi
sudo mv "$TEMP_DIR/release" "$APP_DIR"
sudo chown -R opc:opc "$APP_DIR"
sudo chmod 755 "$APP_DIR"
sudo chmod -R u+rwX,go+rX "$APP_DIR"
if command -v restorecon >/dev/null 2>&1; then
    sudo restorecon -RF "$APP_DIR"
fi

step 6 "Saving the secret and configuring the system service"
decoded_key="$(printf '%s' "$GEMINI_API_KEY_B64" | base64 --decode)"
sudo install -o root -g opc -m 640 /dev/null "$ENV_FILE"
printf 'GEMINI_API_KEY=%s\nGEMINI_MODEL=gemini-3.6-flash\nPERSIST_TASK_HISTORY=false\n' "$decoded_key" | sudo tee "$ENV_FILE" >/dev/null
sudo chown root:opc "$ENV_FILE"
sudo chmod 640 "$ENV_FILE"
unset decoded_key GEMINI_API_KEY_B64

sudo tee "$SERVICE_FILE" >/dev/null <<'SERVICE'
[Unit]
Description=Factuality AI Assessor Streamlit App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opc
Group=opc
WorkingDirectory=/opt/factuality-ai-assessor
EnvironmentFile=/etc/factuality-ai-assessor.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/factuality-ai-assessor/.venv/bin/python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

if command -v firewall-cmd >/dev/null 2>&1; then
    sudo firewall-cmd --zone=public --add-port=8501/tcp --permanent || true
    sudo firewall-cmd --reload || true
fi
sudo systemctl daemon-reload
sudo systemctl enable --now "$APP_NAME"

step 7 "Checking Streamlit health"
for attempt in {1..12}; do
    if curl --fail --silent http://127.0.0.1:8501/_stcore/health >/dev/null; then
        echo "Service is healthy on port 8501."
        sudo systemctl --no-pager --full status "$APP_NAME" | head -20
        exit 0
    fi
    sleep 5
done

sudo systemctl --no-pager --full status "$APP_NAME" || true
sudo journalctl -u "$APP_NAME" --no-pager -n 80 || true
echo "ERROR: Streamlit did not become healthy within 60 seconds." >&2
exit 1
