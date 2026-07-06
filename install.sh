#!/usr/bin/env bash
#  /\_/\    SondeR cat installer (Linux)
# ( o.o )   creates a venv, installs deps, adds menu entry, launches
set -e
cd "$(dirname "$0")"

echo
echo "   /\\_/\\     SondeR cat installer"
echo "  ( o.o )    ====================="
echo

DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$DIR/sondercat.py" ]; then
    echo "[!] Can't find sondercat.py next to this installer."
    echo "    Extract the whole zip, then run ./install.sh from inside it."
    exit 1
fi

if ! command -v python3 >/dev/null; then
    echo "[!] python3 not found. Install it first, e.g.:"
    echo "      sudo apt install python3 python3-venv     (Debian/Ubuntu)"
    echo "      sudo dnf install python3                  (Fedora)"
    exit 1
fi
echo "[1/4] Found $(python3 --version)"

echo "[2/4] Creating a private environment (.venv)..."
python3 -m venv "$DIR/.venv" 2>/dev/null || {
    echo "[!] venv module missing. On Debian/Ubuntu: sudo apt install python3-venv"
    exit 1
}

echo "[3/4] Installing dependencies (this can take a minute)..."
"$DIR/.venv/bin/pip" install --upgrade pip --quiet
if [ -f "$DIR/requirements.txt" ]; then
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt" --quiet
else
    "$DIR/.venv/bin/pip" install "PySide6>=6.5" "pynput>=1.7" --quiet
fi

echo "[4/4] Creating launcher + app-menu entry..."
cat > start_sondercat.sh << EOS
#!/usr/bin/env bash
cd "\$(dirname "\$0")"
exec .venv/bin/python sondercat.py
EOS
chmod +x start_sondercat.sh

mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/sondercat.desktop << EOS
[Desktop Entry]
Type=Application
Name=SondeR cat
Comment=A pixel cat for your desktop
Exec=$PWD/start_sondercat.sh
Path=$PWD
Terminal=false
Categories=Utility;
EOS

read -r -p "Start SondeR cat automatically at login? [y/N] " yn
if [[ "$yn" =~ ^[Yy] ]]; then
    mkdir -p ~/.config/autostart
    cp ~/.local/share/applications/sondercat.desktop ~/.config/autostart/
    echo "Autostart enabled."
fi

echo
echo "All done! Launching your cat..."
if [[ "${XDG_SESSION_TYPE,,}" == "wayland" ]]; then
    echo "(Wayland session detected — some reactions need X11; see README)"
fi
nohup "$DIR/.venv/bin/python" "$DIR/sondercat.py" >/dev/null 2>&1 &
echo "Quit any time: right-click the cat. Relaunch from your app menu."
