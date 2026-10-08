#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── destinations ─────────────────────────────────────────────────────────────
BIN_DIR="$HOME/.local/bin"
SYSTEMD_DIR="$HOME/.config/systemd/user"
APPLICATIONS_DIR="$HOME/.local/share/applications"

# ── checks ───────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found." >&2
    exit 1
fi

if [[ ! -f /usr/share/applications/com.microsoft.VSCode.desktop && \
      ! -f /usr/share/applications/code.desktop && \
      ! -f /usr/local/share/applications/com.microsoft.VSCode.desktop && \
      ! -f /usr/local/share/applications/code.desktop ]]; then
    echo "Error: VSCode does not appear to be installed (no code.desktop found)." >&2
    exit 1
fi

# ── install ───────────────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR" "$SYSTEMD_DIR" "$APPLICATIONS_DIR"

install -m 755 "$SCRIPT_DIR/update-vscode-jumplist.py" "$BIN_DIR/update-vscode-jumplist.py"
install -m 644 "$SCRIPT_DIR/vscode-jumplist.service"   "$SYSTEMD_DIR/vscode-jumplist.service"
install -m 644 "$SCRIPT_DIR/vscode-jumplist.timer"     "$SYSTEMD_DIR/vscode-jumplist.timer"

# ── enable & run ─────────────────────────────────────────────────────────────
systemctl --user daemon-reload
systemctl --user enable --now vscode-jumplist.timer

# Run once immediately so the jump list is populated right away
python3 "$BIN_DIR/update-vscode-jumplist.py"

echo
echo "Installed. The jump list will refresh periodically based on vscode-jumplist.timer config automatically."
echo "To uninstall, run: ./uninstall.sh"
