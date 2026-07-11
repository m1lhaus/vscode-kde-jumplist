#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now vscode-jumplist.timer 2>/dev/null || true
systemctl --user daemon-reload

rm -f "$HOME/.local/bin/update-vscode-jumplist.py"
rm -f "$HOME/.config/systemd/user/vscode-jumplist.service"
rm -f "$HOME/.config/systemd/user/vscode-jumplist.timer"
rm -f "$HOME/.local/share/applications/code.desktop"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Uninstalled."
