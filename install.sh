#!/usr/bin/env bash
#  /\_/\    SondeR cat installer (Linux — all major distros)
# ( o.o )   venv + deps + system-library check + menu entry + launch
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo
echo "   /\\_/\\     SondeR cat installer"
echo "  ( o.o )    ====================="
echo

if [ ! -f "$DIR/sondercat.py" ]; then
    echo "[!] Can't find sondercat.py next to this installer."
    echo "    Extract the whole download, then run ./install.sh from inside it."
    exit 1
fi

# ---------------------------------------------------------- detect distro ---
PKG=""
command -v apt-get >/dev/null 2>&1 && PKG="apt"
[ -z "$PKG" ] && command -v dnf     >/dev/null 2>&1 && PKG="dnf"
[ -z "$PKG" ] && command -v pacman  >/dev/null 2>&1 && PKG="pacman"
[ -z "$PKG" ] && command -v zypper  >/dev/null 2>&1 && PKG="zypper"
[ -z "$PKG" ] && command -v apk     >/dev/null 2>&1 && PKG="apk"

venv_hint() {
    case "$PKG" in
        apt)    echo "sudo apt install python3 python3-venv python3-pip" ;;
        dnf)    echo "sudo dnf install python3" ;;
        pacman) echo "sudo pacman -S python" ;;
        zypper) echo "sudo zypper install python3 python3-pip" ;;
        apk)    echo "sudo apk add python3 py3-pip" ;;
        *)      echo "install python3 + venv with your package manager" ;;
    esac
}

syslibs_cmd() {
    case "$PKG" in
        apt)    echo "sudo apt install -y libxcb-cursor0 libgl1 libxkbcommon-x11-0 libegl1" ;;
        dnf)    echo "sudo dnf install -y xcb-util-cursor libxkbcommon-x11 libglvnd-egl" ;;
        pacman) echo "sudo pacman -S --noconfirm xcb-util-cursor libxkbcommon-x11" ;;
        zypper) echo "sudo zypper install -y libxcb-cursor0 libxkbcommon-x11-0" ;;
        apk)    echo "sudo apk add xcb-util-cursor mesa-gl libxkbcommon" ;;
        *)      echo "" ;;
    esac
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] python3 not found. Install it first:"
    echo "      $(venv_hint)"
    exit 1
fi
echo "[1/5] Found $(python3 --version)  (package manager: ${PKG:-unknown})"

echo "[2/5] Creating a private environment (.venv)..."
if ! python3 -m venv "$DIR/.venv" 2>/dev/null; then
    echo "[!] The venv module is missing. Fix with:"
    echo "      $(venv_hint)"
    exit 1
fi

echo "[3/5] Installing dependencies (this can take a minute)..."
"$DIR/.venv/bin/pip" install --upgrade pip --quiet
if [ -f "$DIR/requirements.txt" ]; then
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt" --quiet
else
    "$DIR/.venv/bin/pip" install "PySide6>=6.5" "pynput>=1.7" --quiet
fi

echo "[4/5] Checking system display libraries..."
MISSING=""
if command -v ldconfig >/dev/null 2>&1; then
    ldconfig -p 2>/dev/null | grep -q libxcb-cursor      || MISSING="$MISSING libxcb-cursor"
    ldconfig -p 2>/dev/null | grep -q libxkbcommon-x11   || MISSING="$MISSING libxkbcommon-x11"
    ldconfig -p 2>/dev/null | grep -q 'libGL\.so'        || MISSING="$MISSING libGL"
fi
if [ -n "$MISSING" ]; then
    echo "    Missing:$MISSING"
    CMD="$(syslibs_cmd)"
    if [ -n "$CMD" ] && [ -t 0 ] && [ "${SONDER_CHECK_ONLY:-0}" != "1" ]; then
        printf "    Install them now? [Y/n] "
        read -r yn
        case "$yn" in
            [Nn]*) echo "    Skipped — the cat may not start until you run:"; echo "      $CMD" ;;
            *)     $CMD || { echo "    Couldn't install automatically. Run manually:"; echo "      $CMD"; } ;;
        esac
    else
        echo "    Install them with:"
        echo "      ${CMD:-xcb-cursor + xkbcommon-x11 + GL packages for your distro}"
    fi
else
    echo "    All good."
fi

# session type info
SESSION="${XDG_SESSION_TYPE:-unknown}"
case "$SESSION" in
    wayland)
        if [ -n "${DISPLAY:-}" ]; then
            echo "    Wayland + XWayland detected — the cat will use XWayland (full features)."
        else
            echo "    Pure Wayland (no XWayland) — the cat runs with limited tricks."
            echo "    For everything to work, log into an 'Xorg / X11' session."
        fi ;;
    x11) echo "    X11 session — full features." ;;
esac
command -v gnome-shell >/dev/null 2>&1 && \
    echo "    GNOME note: no system tray by default — right-click the CAT for the menu."

if [ "${SONDER_CHECK_ONLY:-0}" = "1" ]; then
    echo "(check-only mode: stopping before launch)"
    exit 0
fi

echo "[5/5] Creating launcher + app-menu entry..."
cat > "$DIR/start_sondercat.sh" << EOS
#!/usr/bin/env bash
cd "\$(dirname "\$0")"
exec "$DIR/.venv/bin/python" "$DIR/sondercat.py"
EOS
chmod +x "$DIR/start_sondercat.sh"

mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/sondercat.desktop << EOS
[Desktop Entry]
Type=Application
Name=SondeR cat
Comment=A pixel cat for your desktop
Exec=$DIR/start_sondercat.sh
Path=$DIR
Terminal=false
Categories=Utility;
EOS

if [ -t 0 ]; then
    printf "Start SondeR cat automatically at login? [y/N] "
    read -r yn
    case "$yn" in
        [Yy]*) mkdir -p ~/.config/autostart
               cp ~/.local/share/applications/sondercat.desktop ~/.config/autostart/
               echo "Autostart enabled." ;;
    esac
fi

echo
echo "All done! Launching your cat..."
nohup "$DIR/.venv/bin/python" "$DIR/sondercat.py" >/dev/null 2>&1 &
echo "Quit any time: right-click the cat. Relaunch from your app menu."
