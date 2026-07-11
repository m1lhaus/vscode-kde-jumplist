#!/usr/bin/env python3
"""
Updates ~/.local/share/applications/code.desktop with recently opened
VSCode workspaces as jump-list Actions for KDE Plasma.

Sources: profileAssociations in VSCode's storage.json (includes local and
SSH-remote workspaces), sorted by workspace storage directory mtime.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

MAX_ENTRIES = 10  # how many recent workspaces to include in the jump list

HOME = Path.home()
STORAGE_JSON = HOME / '.config/Code/User/globalStorage/storage.json'
WS_STORAGE = HOME / '.config/Code/User/workspaceStorage'
LOCAL_DESKTOP = HOME / '.local/share/applications/code.desktop'

# Standard install locations for the system VSCode desktop file.
# /usr/share       — package manager installs (dnf, apt, …)
# /usr/local/share — manual / tarball installs
# A single ~/.local/share/applications/code.desktop shadows all of these per
# the XDG spec, so we only ever need to write one local override file.
_SYSTEM_DESKTOP_CANDIDATES = [
    Path('/usr/share/applications/code.desktop'),
    Path('/usr/local/share/applications/code.desktop'),
]
SYSTEM_DESKTOP = next((p for p in _SYSTEM_DESKTOP_CANDIDATES if p.exists()), None)

# ── helpers ──────────────────────────────────────────────────────────────────


def workspace_mtime(uri: str) -> float:
    """Return mtime of the workspace storage dir, or 0.0 if not found.

    VSCode computes the storage dir name differently by URI scheme:
    - file://  (local): md5(fsPath + str(inode))  — inode makes it Linux-specific
    - anything else:    md5(uri)
    """
    if uri.startswith('file://'):
        fspath = unquote(uri[len('file://'):])
        try:
            ino = os.stat(fspath).st_ino
        except OSError:
            return 0.0
        h = hashlib.md5((fspath + str(ino)).encode()).hexdigest()
    else:
        h = hashlib.md5(uri.encode()).hexdigest()
    try:
        return (WS_STORAGE / h).stat().st_mtime
    except OSError:
        return 0.0


def _desktop_quote(s: str) -> str:
    """
    Quote a string for use inside a double-quoted argument in a .desktop Exec=
    field, per the XDG Desktop Entry spec (escapes \\ \" ` $).
    """
    s = s.replace('\\', '\\\\')
    s = s.replace('"',  '\\"')
    s = s.replace('`',  '\\`')
    s = s.replace('$',  '\\$')
    return f'"{s}"'


def _sanitize_name(s: str) -> str:
    """
    Remove characters that would corrupt a .desktop Name= field:
    newlines, carriage returns, and the structural characters = [ ].
    """
    return re.sub(r'[\r\n=\[\]]', '_', s).strip() or 'Unknown'


def display_name(uri: str) -> str:
    """Human-readable label for the jump-list entry."""
    if uri.startswith('file://'):
        path = unquote(uri[len('file://'):])
        label = ('~' + path[len(str(HOME)):]) if path.startswith(str(HOME)) else path
        return _sanitize_name(label)

    if uri.startswith('vscode-remote://ssh-remote'):
        without_scheme = uri[len('vscode-remote://ssh-remote'):]
        decoded = unquote(without_scheme)          # e.g. "+hostname/path"
        if decoded.startswith('+'):
            decoded = decoded[1:]
        host, _, path = decoded.partition('/')
        if not path:
            return _sanitize_name(host)
        abs_path = '/' + path
        short = ('~' + abs_path[len(str(HOME)):]) if abs_path.startswith(str(HOME)) else abs_path
        return _sanitize_name(f'{host}: {short}')

    # dev-container or other unknown remote — best-effort decode, truncate
    return _sanitize_name(unquote(uri)[:80])


def exec_cmd(uri: str) -> str:
    """Exec= value to open the workspace (XDG desktop file format)."""
    if uri.startswith('file://'):
        path = unquote(uri[len('file://'):])
        return f'/usr/share/code/code {_desktop_quote(path)}'
    # Remote URIs: pass as --folder-uri; quote per XDG spec
    return f'/usr/share/code/code --folder-uri {_desktop_quote(uri)}'


def make_action_id(uri: str) -> str:
    return 'ws-' + hashlib.md5(uri.encode()).hexdigest()[:16]

# ── main ─────────────────────────────────────────────────────────────────────


def get_recent_workspaces() -> list[tuple[float, str]]:
    if not STORAGE_JSON.exists():
        return []
    try:
        with open(STORAGE_JSON, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f'Warning: could not read {STORAGE_JSON}: {e}', file=sys.stderr)
        return []

    workspaces = data.get('profileAssociations', {}).get('workspaces', {})
    if not isinstance(workspaces, dict):
        return []

    with_mtime = [(workspace_mtime(u), u) for u in workspaces]
    with_mtime.sort(key=lambda x: x[0], reverse=True)
    return [(mt, u) for mt, u in with_mtime if mt > 0][:MAX_ENTRIES]


def build_desktop(recent: list[tuple[float, str]], base_text: str) -> str:
    # Strip any existing Actions= line and all existing Desktop Action blocks
    text = re.sub(r'^Actions=.*\n', '', base_text, flags=re.MULTILINE)
    # Split off everything from the first Desktop Action header onward
    text = re.split(r'\n\[Desktop Action\b', text)[0]
    text = text.rstrip('\n')

    if not recent:
        text += '\nActions=new-empty-window;\n'
        text += '\n[Desktop Action new-empty-window]\nName=New Empty Window\n'
        text += 'Exec=/usr/share/code/code --new-window %F\nIcon=vscode\n'
        return text

    ids = [make_action_id(u) for _, u in recent]
    text += '\nActions=new-empty-window;' + ';'.join(ids) + ';\n'
    text += '\n[Desktop Action new-empty-window]\nName=New Empty Window\n'
    text += 'Exec=/usr/share/code/code --new-window %F\nIcon=vscode\n'

    for (_, uri), aid in zip(recent, ids):
        text += f'\n[Desktop Action {aid}]\n'
        text += f'Name={display_name(uri)}\n'
        text += f'Exec={exec_cmd(uri)}\n'
        text += 'Icon=vscode\n'

    return text


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    if SYSTEM_DESKTOP is None:
        print('Error: VSCode .desktop file not found in any of:\n' +
              '\n'.join(f'  {p}' for p in _SYSTEM_DESKTOP_CANDIDATES),
              file=sys.stderr)
        sys.exit(1)

    try:
        base_text = SYSTEM_DESKTOP.read_text(encoding='utf-8')
    except OSError as e:
        print(f'Error: could not read {SYSTEM_DESKTOP}: {e}', file=sys.stderr)
        sys.exit(1)

    recent = get_recent_workspaces()
    print(f'Recent workspaces ({len(recent)}):')
    for mt, uri in recent:
        print(f'  {time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))}  {display_name(uri)}')

    content = build_desktop(recent, base_text)

    # Atomic write: write to a temp file in the same directory, then rename.
    LOCAL_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=LOCAL_DESKTOP.parent, suffix='.desktop.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmp_path, LOCAL_DESKTOP)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        print(f'Error: could not write {LOCAL_DESKTOP}: {e}', file=sys.stderr)
        sys.exit(1)

    print(f'\nWrote {LOCAL_DESKTOP}')
    subprocess.run(['update-desktop-database', str(LOCAL_DESKTOP.parent)],
                   capture_output=True)
    print('Done. Right-click the VSCode taskbar icon to see the jump list.')


if __name__ == '__main__':
    main()
