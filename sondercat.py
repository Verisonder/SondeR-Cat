#!/usr/bin/env python3
"""
SondeR cat v2 — pixel cats that live on your desktop. Windows + Linux.

What's new in v2:
  * buttery-smooth animation (25 fps, time-based frames, sub-pixel movement)
  * fixed drag glitches (the cat now keeps up even with very fast drags)
  * fixed typing-reaction flicker (hysteresis on the kneading state)
  * MULTIPLE CATS — add as many as you like, each with its own color,
    pattern and size (right-click -> Cats -> Add a cat)
  * 10 fur colors + custom color picker + 5 patterns
  * cats remember where you left them

Everything else from v1: eye tracking, cursor hunting, kneading, overheat,
scroll paper play, naps, petting, mochi drag + wobble, startle, peek mode
during fullscreen video, stretch reminders, Pomodoro, AI-agent reactions.

Run:  python sondercat.py       Quit: right-click a cat -> Quit
"""

import json
import re
import math
import os
import platform
import random
import subprocess
import sys
import time
import traceback
from collections import deque

ERROR_LOG = os.path.join(os.path.expanduser("~"), "sondercat_error.log")


def _fatal(title, details):
    """Never fail silently: log the error and show a native dialog."""
    msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {title}\n{details}\n"
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n" + "-" * 60 + "\n")
    except Exception:
        pass
    shown = False
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"{title}\n\n{details[-900:]}\n\n"
                   f"Full details saved to:\n{ERROR_LOG}",
                "SondeR cat couldn't start", 0x10)
            shown = True
        except Exception:
            pass
    if not shown:
        sys.stderr.write(msg)


# bundled-libraries mode: the Windows installer ships PySide6/pynput
# pre-extracted next to the app — no pip involved, ever
if platform.system() == "Windows":
    _here = os.path.dirname(os.path.abspath(__file__))
    for _cand in (os.path.join(_here, "libs"),
                  os.path.join(_here, "..", "libs")):
        _cand = os.path.abspath(_cand)
        if os.path.isdir(_cand) and _cand not in sys.path:
            sys.path.insert(0, _cand)
            break

LINUX_DEPS_HINT = (
    "  Debian/Ubuntu:  sudo apt install libxcb-cursor0 libgl1 "
    "libxkbcommon-x11-0 libegl1\n"
    "  Fedora:         sudo dnf install xcb-util-cursor libxkbcommon-x11\n"
    "  Arch:           sudo pacman -S xcb-util-cursor libxkbcommon-x11\n"
    "  openSUSE:       sudo zypper install libxcb-cursor0 libxkbcommon-x11-0\n"
    "  Alpine:         sudo apk add xcb-util-cursor mesa-gl libxkbcommon"
)


def _linux_platform_shim():
    """Make the cat behave the same everywhere:
    - pure X11: nothing to do (full features)
    - Wayland WITH XWayland: force Qt onto xcb so window positioning,
      always-on-top, and cursor tracking keep working
    - pure Wayland (no XWayland): run natively, warn about limits"""
    if platform.system() != "Linux":
        return None
    if os.environ.get("QT_QPA_PLATFORM"):
        return "user-set"
    wayland = (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
               or bool(os.environ.get("WAYLAND_DISPLAY")))
    if wayland:
        if os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"     # XWayland bridge
            return "xwayland"
        return "wayland"
    return None


def _linux_preflight_warn():
    """Warn (never block) if display libraries Qt commonly needs look
    absent — the message lands above Qt's own error if startup fails."""
    if platform.system() != "Linux":
        return
    try:
        import ctypes.util
        if ctypes.util.find_library("c") is None:
            return                       # ldconfig unusable (e.g. musl)
        missing = [n for n in ("xcb-cursor", "xkbcommon-x11")
                   if ctypes.util.find_library(n) is None]
        if missing:
            sys.stderr.write(
                "[SondeR cat] Heads-up: system libraries possibly missing: "
                + ", ".join(missing) + "\nIf the window fails to open, "
                "install them:\n" + LINUX_DEPS_HINT + "\n")
    except Exception:
        pass


PLATFORM_NOTE = _linux_platform_shim()
_linux_preflight_warn()

try:
    from PySide6.QtCore import (Qt, QTimer, QObject, QPoint, QPointF, QRect,
                            Signal)
    from PySide6.QtGui import (QAction, QColor, QCursor, QFont,
                               QGuiApplication, QIcon, QPainter,
                               QPainterPath, QPixmap, QFontMetrics, QPolygonF, QPen)
    from PySide6.QtWidgets import (QApplication, QColorDialog, QInputDialog,
                                   QLineEdit, QMenu, QMessageBox,
                                   QSystemTrayIcon, QVBoxLayout, QWidget)
except Exception:
    _fatal("PySide6 (the GUI library) isn't installed correctly.",
           "Fix: run install.bat again (Windows) or ./install.sh (Linux).\n"
           "On Linux, also make sure system display libraries exist:\n"
           + LINUX_DEPS_HINT + "\n\n" + traceback.format_exc())
    sys.exit(1)

try:
    import sprites
except Exception:
    _fatal("sprites.py is missing or broken.",
           "sondercat.py and sprites.py must be in the same folder.\n"
           "Re-extract the whole zip, then run the installer again.\n\n"
           + traceback.format_exc())
    sys.exit(1)

APP_NAME = "SondeR cat"
APP_VERSION = "9.8.0"
APP_BUILD = "0715g"

# Distribution channel. The GitHub build self-updates from the repo; the
# Microsoft Store build is packaged as MSIX (read-only, Microsoft handles
# updates), so its self-updater is disabled. The Store packaging step drops
# a "STORE_BUILD" marker file next to this script to flip the channel — the
# source file itself is identical in both builds.
def _detect_channel():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(here, "STORE_BUILD")):
            return "store"
        # MSIX apps install under ...\WindowsApps\... — treat as store too
        if "windowsapps" in here.replace("/", "\\").lower():
            return "store"
    except Exception:
        pass
    return "github"


APP_CHANNEL = _detect_channel()
IS_STORE_BUILD = (APP_CHANNEL == "store")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".sondercat.json")
# Ko-fi donation page (0% fees on donations). Replace "verisonder" with your
# Ko-fi username once your page is live: https://ko-fi.com/<username>
KOFI_URL = "https://ko-fi.com/verisonder"
AGENT_FILE = os.path.join(os.path.expanduser("~"), ".sondercat_agent")

TOP_MARGIN = 68
TICK_MS = 33                    # ~30 fps
WIGGLE_SENS = {"high": (3, 12), "medium": (4, 20), "low": (6, 30)}

CAT_DEFAULTS = {"palette": "orange tabby", "pattern": "tabby",
                "custom_body": None, "scale": 6, "pos": None}
GLOBAL_DEFAULTS = {"stretch_minutes": 50, "sleep_seconds": 180,
                   "auto_peek": True, "chase_enabled": True,
                   "name": "", "pinned": "", "reminders": [], "sounds": True, "laser_only": True, "wiggle_hide": True,
                   "wiggle_sens": "medium",
                   "force_sleep": False, "watch_sprites": False,
                   "window_perch": True, "perch_freq": "instant",
                   "perch_nap_chance": 0.3,
                   "corner_stand": False, "corner_freq": "sometimes",
                   "auto_update": True,
                   "dance_music": True, "dance_on_sound": False,
                   "gemini_key": "", "screen_vision": False,
                   "vision_consent": False,
                   "guide_mode": False, "guide_consent": False,
                   "guide_quality": "fast",
                   "duck_high_score": 0, "sound_volume": 0.6,
                   "guard_mode": False, "guard_timer_min": 0,
                   "hide_mode": False}

(IDLE, KNEAD, SLEEP, CHASE, DRAG, STRETCH,
 OVERHEAT, SCROLLPLAY, PEEK, THINK, DANCE) = range(11)


# ----------------------------------------------------------------- config ----

def load_config():
    cfg = {"global": dict(GLOBAL_DEFAULTS), "cats": [dict(CAT_DEFAULTS)]}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if "cats" in raw:                                   # v2 format
            cfg["global"].update(raw.get("global", {}))
            cats = []
            for c in raw["cats"]:
                d = dict(CAT_DEFAULTS)
                d.update(c)
                cats.append(d)
            if cats:
                cfg["cats"] = cats
        else:                                               # migrate v1
            for k in GLOBAL_DEFAULTS:
                if k in raw:
                    cfg["global"][k] = raw[k]
            for k in CAT_DEFAULTS:
                if k in raw:
                    cfg["cats"][0][k] = raw[k]
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def custom_palette(body_hex):
    base = QColor(body_hex)
    return {
        "B": base.name(), "S": base.darker(140).name(), "W": "#f6f2e9",
        "K": base.darker(300).name(), "E": "#f8f8f4", "N": "#e06a7c",
        "M": base.darker(300).name(), "Z": "#eeb0a0", "P": "#2c5a34",
    }


# --------------------------------------------------- global input watchers ---

class WinScrollHook:
    """Low-level WH_MOUSE_LL wheel hook via ctypes with PROPER Win64 types
    (restype/argtypes declared — without them, pointer-sized values get
    truncated to 32-bit and the hook fails or crashes silently)."""

    def __init__(self, on_scroll):
        import threading
        self.on_scroll = on_scroll
        self.ok = False
        self.count = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def alive(self):
        return self._thread.is_alive()

    def _run(self):
        try:
            import ctypes
            from ctypes import wintypes as wt
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            WM_MOUSEWHEEL, WM_MOUSEHWHEEL, WH_MOUSE_LL = 0x020A, 0x020E, 14
            is64 = ctypes.sizeof(ctypes.c_void_p) == 8
            ULONG_PTR = ctypes.c_uint64 if is64 else ctypes.c_ulong
            LRESULT = ctypes.c_int64 if is64 else ctypes.c_long

            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD),
                            ("flags", wt.DWORD), ("time", wt.DWORD),
                            ("dwExtraInfo", ULONG_PTR)]

            HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int,
                                          wt.WPARAM, wt.LPARAM)
            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC,
                                                 wt.HINSTANCE, wt.DWORD)
            user32.CallNextHookEx.restype = LRESULT
            user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int,
                                              wt.WPARAM, wt.LPARAM)
            user32.GetMessageW.restype = ctypes.c_int
            user32.GetMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND,
                                           wt.UINT, wt.UINT)
            user32.TranslateMessage.argtypes = (ctypes.POINTER(wt.MSG),)
            user32.DispatchMessageW.restype = LRESULT
            user32.DispatchMessageW.argtypes = (ctypes.POINTER(wt.MSG),)
            kernel32.GetModuleHandleW.restype = wt.HMODULE
            kernel32.GetModuleHandleW.argtypes = (wt.LPCWSTR,)

            def proc(nCode, wParam, lParam):
                if nCode >= 0 and wParam in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                    try:
                        ms = ctypes.cast(
                            lParam,
                            ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        delta = ctypes.c_short(
                            (ms.mouseData >> 16) & 0xFFFF).value / 120.0
                        self.count += 1
                        self.on_scroll(abs(delta) or 1.0)
                    except Exception:
                        pass
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._proc_ref = HOOKPROC(proc)          # must stay referenced
            hmod = kernel32.GetModuleHandleW(None)
            hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc_ref,
                                            hmod, 0)
            if not hook:
                return
            self.ok = True
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            self.ok = False


class InputWatcher:
    """Global keyboard + scroll watcher via pynput (shared by all cats).
    Degrades gracefully (e.g. Wayland): cats just won't react to typing."""

    def __init__(self, on_event=None):
        self.on_event = on_event
        self.last_key = 0.0
        self.last_any_key = 0.0     # ANY key incl. modifiers (phantom check)
        self.key_count = 0            # increments per real keypress
        self.key_times = deque(maxlen=80)
        self._MODS = {"ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l",
                      "shift_r", "alt", "alt_l", "alt_r", "alt_gr",
                      "cmd", "cmd_l", "cmd_r"}
        # keys that should NOT make the cat "type along" — modifiers and
        # navigation/function keys. Space, backspace, enter, delete, arrows
        # etc. are NOT here, so they still count as writing.
        self._NO_TYPE_KEYS = self._MODS | {
            "tab", "esc", "caps_lock", "num_lock", "scroll_lock",
            "cmd", "cmd_l", "cmd_r",                     # Win key
            "menu", "print_screen", "pause", "insert",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9",
            "f10", "f11", "f12", "f13", "f14", "f15", "f16", "f17",
            "f18", "f19", "f20",
        }
        self.last_scroll = 0.0
        self.scroll_accum = 0.0
        self.kb_ok = self.mouse_ok = False
        self._down = set()
        try:
            from pynput import keyboard
            self._kb = keyboard.Listener(on_press=self._on_press,
                                             on_release=self._on_release)
            self._kb.daemon = True
            self._kb.start()
            self.kb_ok = True
        except Exception:
            pass
        self.pyn_count = 0
        self.on_ask = None
        self.on_esc = None
        self.on_update = None
        self.on_restart = None
        self._native = None
        if platform.system() == "Windows":
            try:
                self._native = WinScrollHook(self._native_scroll)
            except Exception:
                self._native = None
        # pynput runs AS WELL — belt and braces (double counts are harmless)
        self._ms = None
        try:
            from pynput import mouse
            self._ms = mouse.Listener(on_scroll=self._on_scroll)
            self._ms.daemon = True
            self._ms.start()
        except Exception:
            self._ms = None
        self.mouse_ok = bool(self._native or self._ms)

    def _on_release(self, key):
        try:
            self._down.discard(key)
            if hasattr(self, "_typed_down"):
                self._typed_down.discard(key)
        except Exception:
            pass

    def _on_press(self, key):
        # --- global shortcuts FIRST, before any filtering, so nothing can
        # block them (Ctrl+Space ask, Ctrl+Shift+Alt+P update / +R restart) ---
        try:
            self.last_any_key = time.time()   # modifiers count here — keeps
                                              # the phantom-purge honest
            self._down.add(key)
            if len(self._down) > 24:
                self._down.clear()
            names = {getattr(k, "name", None) for k in self._down}
            kn = getattr(key, "name", None)
            ch = getattr(key, "char", None)
            vk = getattr(key, "vk", None)
            if kn == "space" and self.on_ask is not None \
                    and (names & {"ctrl", "ctrl_l", "ctrl_r"}):
                self.on_ask()
            elif kn == "esc" and self.on_esc is not None:
                self.on_esc()
            has_ctrl = bool(names & {"ctrl", "ctrl_l", "ctrl_r"})
            has_shift = bool(names & {"shift", "shift_l", "shift_r"})
            has_alt = bool(names & {"alt", "alt_l", "alt_r", "alt_gr"})
            if has_ctrl and has_shift and has_alt:
                is_p = (vk == 0x50
                        or (isinstance(ch, str) and ch.lower() == "p")
                        or ch == "\x10")
                is_r = (vk == 0x52
                        or (isinstance(ch, str) and ch.lower() == "r")
                        or ch == "\x12")
                if is_p and self.on_update is not None:
                    self.on_update()
                if is_r and self.on_restart is not None:
                    self.on_restart()
        except Exception:
            pass

        # --- typing reaction (skip modifier/nav keys, handle auto-repeat) ---
        try:
            if getattr(key, "name", None) in self._NO_TYPE_KEYS:
                return                       # don't count AND don't refresh
        except Exception:
            pass
        now = time.time()
        if key in getattr(self, "_typed_down", set()):
            self.last_key = now              # held real key: keep pose, no count
            return
        try:
            if not hasattr(self, "_typed_down"):
                self._typed_down = set()
            self._typed_down.add(key)
            if len(self._typed_down) > 24:
                self._typed_down.clear()
        except Exception:
            pass
        self.last_key = now
        self.key_count += 1          # drives the typing-paw alternation
        self.key_times.append(now)
        if self.on_event:
            try:
                self.on_event()
            except Exception:
                pass

    def _native_scroll(self, amount):
        self.last_scroll = time.time()
        self.scroll_accum = min(self.scroll_accum + abs(amount) * 6, 60)
        if self.on_event:
            try:
                self.on_event()
            except Exception:
                pass

    def _on_scroll(self, _x, _y, dx, dy):
        amt = abs(dy) if dy else abs(dx)
        if not amt:
            return
        self.pyn_count += 1
        self.last_scroll = time.time()
        self.scroll_accum = min(self.scroll_accum + amt * 6, 60)
        if self.on_event:
            try:
                self.on_event()
            except Exception:
                pass

    def key_held(self):
        """True while a non-modifier key is genuinely held down. Guarded by
        recent key activity so a MISSED release (stale _down entry) can't
        freeze the paw forever: a real hold produces OS auto-repeat, which
        keeps last_key fresh."""
        if time.time() - max(self.last_key,
                             getattr(self, "last_any_key", 0.0)) > 1.2:
            # no key events AT ALL lately -> _down entries are phantoms.
            # (uses last_any_key, which modifiers DO refresh, so holding
            # Ctrl/Shift/Alt for a shortcut never gets purged mid-combo)
            if self._down:
                self._down.clear()
            return False
        try:
            for k in self._down:
                if getattr(k, "name", None) not in self._NO_TYPE_KEYS:
                    return True
        except Exception:
            pass
        return False

    def typing(self, window):
        return (time.time() - self.last_key) < window

    def keys_per_sec(self, window=4.0):
        now = time.time()
        return sum(1 for t in self.key_times if now - t < window) / window

    def scrolling(self, window=1.2):
        return (time.time() - self.last_scroll) < window

    def ensure_alive(self):
        """pynput listener threads can die silently — resurrect them."""
        try:
            if self.kb_ok and (self._kb is None or not self._kb.is_alive()):
                from pynput import keyboard
                self._kb = keyboard.Listener(on_press=self._on_press,
                                             on_release=self._on_release)
                self._kb.daemon = True
                self._kb.start()
        except Exception:
            pass
        try:
            if self._native is not None and not self._native.alive():
                self._native = WinScrollHook(self._native_scroll)
        except Exception:
            pass
        try:
            if self._ms is not None and not self._ms.is_alive():
                from pynput import mouse
                self._ms = mouse.Listener(on_scroll=self._on_scroll)
                self._ms.daemon = True
                self._ms.start()
        except Exception:
            pass


class FullscreenDetector:
    """Best-effort 'is the foreground window fullscreen?'."""

    def __init__(self):
        self.system = platform.system()
        self._x_display = None

    def check(self):
        try:
            if self.system == "Windows":
                return self._check_windows()
            if self.system == "Linux":
                return self._check_x11()
        except Exception:
            pass
        return False

    def _check_windows(self):
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        # never count our OWN windows (the cat, the full-screen guard-beam
        # overlay, the ask box…) as "fullscreen video" — that would make the
        # cat hide from itself
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        rect = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                        ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

        mon = u.MonitorFromWindow(hwnd, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        u.GetMonitorInfoW(mon, ctypes.byref(mi))
        m = mi.rcMonitor
        rect_fs = (rect.left <= m.left and rect.top <= m.top
                   and rect.right >= m.right and rect.bottom >= m.bottom)
        if not rect_fs:
            return False
        # belt + suspenders: ask Windows itself. SHQueryUserNotificationState
        # reports BUSY / D3D_FULL_SCREEN / PRESENTATION only for genuinely
        # fullscreen apps — a maximized/borderless window that merely covers
        # the monitor doesn't set these, which was causing phantom hides.
        try:
            state = ctypes.c_int(0)
            if ctypes.windll.shell32.SHQueryUserNotificationState(
                    ctypes.byref(state)) == 0:      # S_OK
                return state.value in (2, 3, 4)     # BUSY / D3D FS / PRESENT
        except Exception:
            pass
        return True                                  # API unavailable: rect only

    def _check_x11(self):
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" \
                and not os.environ.get("DISPLAY"):
            return False
        from Xlib import display, X
        if self._x_display is None:
            self._x_display = display.Display()
        d = self._x_display
        root = d.screen().root
        active = root.get_full_property(
            d.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if not active or not active.value:
            return False
        win = d.create_resource_object("window", active.value[0])
        state = win.get_full_property(d.intern_atom("_NET_WM_STATE"), 4)
        fs = d.intern_atom("_NET_WM_STATE_FULLSCREEN")
        return bool(state and fs in state.value)


def read_agent_status():
    try:
        with open(AGENT_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if raw:
            parts = raw.split("|", 1)
            kind = parts[0].strip().lower()
            label = parts[1].strip() if len(parts) > 1 else "Agent"
            if kind in ("working", "done"):
                return kind, label or "Agent"
    except Exception:
        pass
    return None, ""


def clear_agent_status():
    try:
        with open(AGENT_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


# ------------------------------------------------- live sprite reloading -----

SPRITE_CHARS = set(".KBSWENMZHGgO")
REQUIRED_FRAMES = ["sit_a", "sit_b", "blink", "type_a", "type_b",
                   "knead_a", "knead_b", "sleep", "run_a", "run_b",
                   "stretch", "dangle", "peek"]


def validate_sprites(ns):
    """Return (ok, message). Checks a freshly-executed sprites namespace so a
    bad edit can NEVER crash the app — worst case is a precise error."""
    try:
        W, H = int(ns["GRID_W"]), int(ns["GRID_H"])
        frames = ns["FRAMES"]
        for name in REQUIRED_FRAMES:
            if name not in frames:
                return False, f"Missing frame: {name.upper()}"
            g = frames[name]
            if len(g) != H:
                return False, (f"{name.upper()}: has {len(g)} rows, "
                               f"needs {H}")
            for i, row in enumerate(g):
                if len(row) != W:
                    return False, (f"{name.upper()}, row {i}: has "
                                   f"{len(row)} characters, needs {W}")
                bad = set(row) - SPRITE_CHARS
                if bad:
                    return False, (f"{name.upper()}, row {i}: illegal "
                                   f"character {sorted(bad)[0]!r}")
        ew, eh = int(ns["EYE_W"]), int(ns["EYE_H"])
        for name, cells in ns["EYE_CELLS"].items():
            if name not in frames:
                return False, f"EYE_CELLS points at unknown frame: {name}"
            g = frames[name]
            for (x, y) in cells:
                if not (0 <= x <= W - ew and 0 <= y <= H - eh):
                    return False, (f"EYE_CELLS for {name.upper()}: "
                                   f"({x},{y}) is outside the grid")
                blk = {g[y + yy][x + xx]
                       for yy in range(eh) for xx in range(ew)}
                if blk - {"E", "B", "K"}:
                    return False, (f"EYE_CELLS for {name.upper()}: "
                                   f"({x},{y}) isn't on an eye (E block)")
        for pname, pal in ns["PALETTES"].items():
            for key in "BSWKENMZP":
                if key not in pal:
                    return False, (f"Palette '{pname}' is missing "
                                   f"color {key!r}")
        for fn in ("apply_pattern", "add_halo", "render_frame",
                   "render_icon"):
            if not callable(ns.get(fn)):
                return False, f"Function {fn}() is missing"
        # dry-run one render to be extra safe
        img = ns["render_frame"](frames["sit_a"],
                                 ns["PALETTES"]["orange tabby"], 2)
        if img.width() != W * 2:
            return False, "render_frame produced a wrong-sized image"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return True, "ok"


def reload_sprites():
    """Re-read sprites.py from disk; swap it in only if fully valid."""
    path = os.path.abspath(sprites.__file__)
    try:
        src = open(path, encoding="utf-8").read()
    except Exception as e:
        return False, f"Couldn't read sprites.py: {e}"
    ns = {"__file__": path, "__name__": "sprites"}
    try:
        exec(compile(src, path, "exec"), ns)
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    ok, msg = validate_sprites(ns)
    if not ok:
        return False, msg
    for k, v in ns.items():
        if not k.startswith("__"):
            setattr(sprites, k, v)
    return True, "ok"


# ------------------------------------------------------------------ meow -----

class Meow:
    def __init__(self):
        self.fx = None
        self.wav = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "meow.wav")
        self.use_winsound = (platform.system() == "Windows"
                             and os.path.exists(self.wav))
        if self.use_winsound:
            return
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "meow.wav")
            if os.path.exists(path):
                self.fx = QSoundEffect()
                self.fx.setSource(QUrl.fromLocalFile(path))
                self.fx.setVolume(0.5)
        except Exception:
            self.fx = None

    def play(self):
        try:
            if self.use_winsound:
                import winsound
                winsound.PlaySound(self.wav,
                                   winsound.SND_FILENAME
                                   | winsound.SND_ASYNC
                                   | winsound.SND_NODEFAULT)
            elif self.fx:
                self.fx.play()
        except Exception:
            pass


# ------------------------------------------------------------- sound fx -----

class SoundFX:
    """Procedural 8-bit sound effects + music for the cat and minigames.
    Everything is synthesized at runtime into WAV files (square waves and
    shaped noise) — nothing copyrighted, no audio files shipped.

    Windows playback uses the built-in winmm MCI API via ctypes (the bundled
    PySide6 is Essentials-only, so QtMultimedia does NOT exist there). MCI
    can play several sounds at once — music keeps looping while shots play.
    Non-Windows falls back to QtMultimedia's QSoundEffect if available."""

    SR = 22050

    def __init__(self, volume=0.6):
        self._ok = False
        self._is_win = (platform.system() == "Windows")
        self._fx = {}                # non-Windows QSoundEffect cache
        self._open_aliases = set()   # MCI aliases opened
        self._music_on = False
        self._volume = max(0.0, min(1.0, volume))
        try:
            self._paths = {}
            self._build()
            self._ok = True
        except Exception:
            self._ok = False

    # ---- synthesis -------------------------------------------------------
    def _sq(self, freq, ms, vol=0.28, duty=0.5):
        n = int(self.SR * ms / 1000.0)
        if freq <= 0:
            return [0] * n
        period = self.SR / freq
        out = []
        for i in range(n):
            phase = (i % period) / period
            s = vol if phase < duty else -vol
            env = min(1.0, i / 80.0, (n - i) / 80.0)
            out.append(int(s * env * 32767))
        return out

    def _wav(self, samples, name):
        import wave, struct, tempfile
        path = os.path.join(tempfile.gettempdir(), name)
        w = wave.open(path, "w")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(self.SR)
        clip = lambda v: max(-32767, min(32767, int(v)))
        w.writeframes(b"".join(struct.pack("<h", clip(s)) for s in samples))
        w.close()
        return path

    def _build(self):
        import math, random
        # --- looping game music: bouncy square-wave riff + soft bass ---
        A3, C4, D4, E4, G4, A4, C5, E5 = (220, 262, 294, 330, 392, 440,
                                          523, 659)
        beat = 140
        riff = [A4, E4, A4, C5, A4, E4, G4, E4,
                A4, E4, A4, C5, E5, C5, A4, E4,
                D4, A3, D4, E4, D4, A3, C4, A3,
                G4, D4, G4, A4, C5, A4, G4, E4]
        bass = [A3, 0, A3, 0, 196, 0, 196, 0,
                D4, 0, D4, 0, E4, 0, E4, 0]
        music = []
        for i, f in enumerate(riff):
            lead = self._sq(f, beat, vol=0.20)
            b = self._sq(bass[i % len(bass)], beat, vol=0.14, duty=0.25)
            music.extend(lead[j] + (b[j] if j < len(b) else 0)
                         for j in range(len(lead)))
        self._paths["music"] = self._wav(music, "sonder_music.wav")
        # --- pew: descending square laser + noise crackle ---
        pew = []
        n = int(self.SR * 0.13)
        for i in range(n):
            t = i / n
            period = self.SR / (1400 - 1050 * t)
            s = 0.30 if (i % period) / period < 0.5 else -0.30
            pew.append(int(s * ((1 - t) ** 1.5) * 32767))
        for i in range(int(self.SR * 0.04)):                # crackle tail
            env = 1 - i / (self.SR * 0.04)
            pew.append(int(random.uniform(-1, 1) * 0.18 * env * 32767))
        self._paths["shot"] = self._wav(pew, "sonder_shot.wav")
        # --- purr: low rumble with a gentle ~20 Hz tremolo ---
        purr = []
        dur = 2.2
        n = int(self.SR * dur)
        for i in range(n):
            t = i / self.SR
            base = (math.sin(2 * math.pi * 50 * t) * 0.5
                    + math.sin(2 * math.pi * 100 * t) * 0.22
                    + random.uniform(-1, 1) * 0.12)        # breathy texture
            trem = 0.6 + 0.4 * math.sin(2 * math.pi * 20 * t)
            fade = min(1.0, i / 1500.0, (n - i) / 4000.0)  # soft in/out
            purr.append(int(base * trem * fade * 0.45 * 32767))
        self._paths["purr"] = self._wav(purr, "sonder_purr.wav")
        # --- bloop: duck hit — quick falling thunk ---
        bl = []
        n = int(self.SR * 0.16)
        for i in range(n):
            t = i / n
            period = self.SR / (620 - 420 * t)
            s = 0.32 if (i % period) / period < 0.5 else -0.32
            bl.append(int(s * (1 - t) * 32767))
        self._paths["hit"] = self._wav(bl, "sonder_hit.wav")

    # ---- Windows MCI backend (built into winmm.dll, plays concurrently) --
    def _mci(self, cmd):
        import ctypes
        buf = ctypes.create_unicode_buffer(255)
        ctypes.windll.winmm.mciSendStringW(cmd, buf, 254, 0)
        return buf.value

    def _mci_reopen(self, key):
        """Close then reopen the alias so MCI binds to whatever output
        device is CURRENT (default) right now — this is how switching
        between speakers and earphones mid-session is picked up."""
        alias = f"sonder_{key}"
        if alias in self._open_aliases:
            self._mci(f"close {alias}")
            self._open_aliases.discard(alias)
        self._mci(f'open "{self._paths[key]}" type mpegvideo alias {alias}')
        self._open_aliases.add(alias)
        # apply the current volume (MCI scale is 0..1000)
        vol = int(max(0.0, min(1.0, self._volume)) * 1000)
        self._mci(f"setaudio {alias} volume to {vol}")
        return alias

    def _play(self, key, loop=False):
        if not self._ok:
            return
        try:
            if self._is_win:
                # reopen every time → always targets the live default device
                alias = self._mci_reopen(key)
                self._mci(f"play {alias} from 0" + (" repeat" if loop else ""))
            else:
                fx = self._fx.get(key)
                if fx is None:
                    from PySide6.QtCore import QUrl
                    from PySide6.QtMultimedia import QSoundEffect
                    fx = QSoundEffect()
                    fx.setSource(QUrl.fromLocalFile(self._paths[key]))
                    self._fx[key] = fx
                fx.setVolume(self._volume)
                if loop:
                    from PySide6.QtMultimedia import QSoundEffect as _QSE
                    fx.setLoopCount(_QSE.Infinite)
                fx.play()
        except Exception:
            pass

    def _stop(self, key):
        try:
            if self._is_win:
                alias = f"sonder_{key}"
                if alias in self._open_aliases:
                    self._mci(f"stop {alias}")
            else:
                fx = self._fx.get(key)
                if fx:
                    fx.stop()
        except Exception:
            pass

    def set_volume(self, v):
        """v in 0.0..1.0. Applies live to any playing MCI aliases."""
        self._volume = max(0.0, min(1.0, v))
        try:
            if self._is_win:
                mv = int(self._volume * 1000)
                for alias in list(self._open_aliases):
                    self._mci(f"setaudio {alias} volume to {mv}")
            else:
                for fx in self._fx.values():
                    fx.setVolume(self._volume)
        except Exception:
            pass

    # ---- public one-liners ----------------------------------------------
    def music_start(self):
        self._music_on = True
        self._play("music", loop=True)

    def music_stop(self):
        self._music_on = False
        self._stop("music")

    def shot(self):
        self._play("shot")

    def purr(self):
        self._play("purr")

    def hit(self):
        self._play("hit")


# ---------------------------------------------------------------- manager ----

class _InputBridge(QObject):
    poked = Signal()




def pick_minutes(title, label, initial_min=25):
    """Duration picker with a real HH:MM spinner. Returns minutes or None."""
    from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                   QTimeEdit, QVBoxLayout)
    from PySide6.QtCore import QTime
    dlg = QDialog()
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(label))
    t = QTimeEdit()
    t.setDisplayFormat("HH:mm")
    t.setTime(QTime(initial_min // 60, initial_min % 60))
    t.setCurrentSection(QTimeEdit.MinuteSection)
    lay.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    if dlg.exec() != QDialog.Accepted:
        return None
    qt = t.time()
    return qt.hour() * 60 + qt.minute()


class _AudioMeter:
    """System output level 0..1 via WASAPI IAudioMeterInformation."""
    def __init__(self):
        self._meter = None
        self._dead_until = 0.0

    def _init_com(self):
        import ctypes
        from ctypes import POINTER, byref, c_void_p, c_float, c_uint

        class GUID(ctypes.Structure):
            _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                        ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]

        def guid(txt):
            g = GUID()
            ole = ctypes.windll.ole32
            ole.CLSIDFromString(ctypes.c_wchar_p(txt), byref(g))
            return g

        ole = ctypes.windll.ole32
        ole.CoInitialize(None)
        CLSID_ENUM = guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        IID_ENUM = guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        IID_METER = guid("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        enum = c_void_p()
        if ole.CoCreateInstance(byref(CLSID_ENUM), None, 1,
                                byref(IID_ENUM), byref(enum)) != 0:
            raise OSError("no device enumerator")

        def vtbl(obj, idx, restype, *argtypes):
            vt = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
            fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vt[idx])
            return fn

        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eConsole)
        get_ep = vtbl(enum, 4, ctypes.c_long, c_uint, c_uint,
                      POINTER(c_void_p))
        dev = c_void_p()
        if get_ep(enum, 0, 0, byref(dev)) != 0:
            raise OSError("no default endpoint")
        # IMMDevice::Activate(iid, CLSCTX_ALL, NULL, &meter)
        activate = vtbl(dev, 3, ctypes.c_long, POINTER(GUID), c_uint,
                        c_void_p, POINTER(c_void_p))
        meter = c_void_p()
        if activate(dev, byref(IID_METER), 23, None, byref(meter)) != 0:
            raise OSError("no meter")
        # IAudioMeterInformation::GetPeakValue(&float)
        self._peak_fn = vtbl(meter, 3, ctypes.c_long,
                             POINTER(c_float))
        self._meter = meter
        self._c_float = c_float
        self._byref = byref

    def peak(self):
        if platform.system() != "Windows":
            return 0.0
        now = time.time()
        if self._meter is None:
            if now < self._dead_until:
                return 0.0
            try:
                self._init_com()
            except Exception:
                self._dead_until = now + 30
                return 0.0
        try:
            v = self._c_float(0.0)
            if self._peak_fn(self._meter, self._byref(v)) != 0:
                raise OSError
            return max(0.0, min(1.0, v.value))
        except Exception:
            self._meter = None          # device changed: re-init later
            self._dead_until = now + 5
            return 0.0


class GuideGlow(QWidget):
    """Small click-through overlay that softly pulses a blue glow around
    the UI element the guide is pointing at — same electric blue as the
    cat's power-eyes. Purely visual; never blocks input."""

    SIZE = 84                               # widget is a square this big

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(self.SIZE, self.SIZE)
        self.until = 0.0

    def show_at(self, x, y, secs=30.0):
        """Center the glow on screen point (x, y)."""
        self.move(int(x) - self.SIZE // 2, int(y) - self.SIZE // 2)
        self.until = time.time() + secs
        if not self.isVisible():
            self.show()
        self.update()

    def tick(self):
        if not self.isVisible():
            return
        if time.time() > self.until:
            self.hide()
            return
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = cy = self.SIZE / 2.0
        t = time.time()
        pulse = 0.5 + 0.5 * math.sin(t * 3.2)       # slow breathe 0..1
        base_r = self.SIZE * 0.19
        r = base_r * (1.0 + 0.16 * pulse)
        # layered soft rings, brightest in the middle — the power-eye blues
        for mult, alpha in ((2.1, 26), (1.65, 44), (1.3, 66), (1.0, 92)):
            col = QColor("#56d9ff")
            col.setAlpha(int(alpha * (0.65 + 0.35 * pulse)))
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(cx, cy), r * mult, r * mult)
        core = QColor("#3ec8ff")
        core.setAlpha(150)
        p.setBrush(core)
        p.drawEllipse(QPointF(cx, cy), r * 0.5, r * 0.5)


class DuckHuntGame(QWidget):
    """Hidden easter-egg minigame: ducks fly across the whole screen, click
    to shoot them. A full-screen, frameless, transparent overlay. The cat
    itself stands in the corner with a gun (drawn by the CatWindow); this
    window handles the ducks, score, crosshair and hits."""

    def __init__(self, mgr):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.mgr = mgr
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        scr = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(scr)
        self.sw, self.sh = scr.width(), scr.height()
        self.ducks = []          # each: dict(x,y,vx,vy,color,pts,alive,fall,flap)
        self.pops = []           # hit puffs: dict(x,y,t)
        self.score = 0
        self.shots = 0
        self.hits = 0
        self.high = int(mgr.cfg["global"].get("duck_high_score", 0))
        # HUD panel bounds (fixed size, centered at top) — ducks steer clear
        # of this rectangle so they never fly behind the score and become
        # un-clickable. A bit of margin included.
        _pw, _ph = 320, 118
        _px0 = (self.sw - _pw) // 2
        self.panel_rect = (_px0 - 30, 22, _px0 + _pw + 30, 22 + _ph + 46)
        self.spawn_at = 0.0
        self.frame = 0
        self.running = True
        import time as _t0
        self.start_t = _t0.time()
        self.countdown = 3.0            # 3-2-1-GO before ducks appear
        self._img_cache = {}     # (wing_down,color,flip) -> QImage (12 max)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._step)
        self._tick.start(33)     # ~30 fps
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ---- duck lifecycle ------------------------------------------------
    def _spawn(self):
        import random
        # spawn rates: brown 70% (common), blue 20%, red 10% (rare).
        # points: brown 1, blue 2, red 3. base speeds: brown normal,
        # blue slightly faster, red fastest.
        roll = random.random()
        if roll < 0.70:
            color, pts, spd = "brown", 1, 5.5
        elif roll < 0.90:
            color, pts, spd = "blue", 2, 8.0
        else:
            color, pts, spd = "red", 3, 11.5
        # difficulty ramp (like Chrome dino): everything speeds up the longer
        # you play — +6% per 10s, capped at 2.2x
        import time as _t
        played = max(0.0, _t.time() - self.start_t - self.countdown)
        diff = min(2.2, 1.0 + played * 0.006)
        spd *= diff
        from_left = random.random() < 0.5
        # keep ducks BELOW the score panel so they're always clickable
        top_limit = max(int(self.sh * 0.08), self.panel_rect[3] + 10)
        y = random.randint(top_limit, int(self.sh * 0.62))
        vx = spd * (1 if from_left else -1) * random.uniform(0.85, 1.25)
        vy = random.uniform(-1.4, -0.4)
        x = -40 if from_left else self.sw + 40
        self.ducks.append(dict(x=float(x), y=float(y), vx=vx, vy=vy,
                               color=color, pts=pts, alive=True,
                               fall=False, flap=0.0))

    def _step(self):
        import time as _t
        if not self.running:
            return
        now = _t.time()
        self.frame += 1
        # 3-2-1-GO! hold everything until the countdown finishes
        if now - self.start_t < self.countdown:
            self.update()
            return
        # keep 2–4 ducks alive
        alive = [d for d in self.ducks if d["alive"] and not d["fall"]]
        # difficulty ramp: more ducks on screen + quicker spawns over time
        played = max(0.0, now - self.start_t - self.countdown)
        max_ducks = 3 + int(played // 20)          # +1 every 20s
        max_ducks = min(max_ducks, 7)
        gap = max(0.28, 0.7 - played * 0.004)      # spawns speed up
        if len(alive) < max_ducks and now >= self.spawn_at:
            self._spawn()
            self.spawn_at = now + gap
        for d in self.ducks:
            d["flap"] = (d["flap"] + 0.35)
            if d["fall"]:
                d["vy"] += 0.9          # gravity after being shot
                d["y"] += d["vy"]
                d["x"] += d["vx"] * 0.3
            else:
                d["x"] += d["vx"]
                d["y"] += d["vy"]
                d["vy"] += 0.02         # gentle bob/gravity
                d["vy"] = min(d["vy"], 1.2)   # never nose-dive
                # if a duck is horizontally under the score panel, keep it
                # BELOW the panel so it can't hide behind it
                px1, _, px2, py2 = self.panel_rect
                dw = sprites.DUCK_W * 4
                over_panel = (d["x"] + dw > px1 and d["x"] < px2)
                ceil = (py2 + 6) if over_panel else self.sh * 0.05
                if d["y"] < ceil:
                    d["y"] = ceil
                    d["vy"] = abs(d["vy"])   # bounce back down
                elif d["y"] > self.sh * 0.70:
                    d["vy"] = -abs(d["vy"])   # bounce back up into the sky
        # cull off-screen
        self.ducks = [d for d in self.ducks
                      if -80 < d["x"] < self.sw + 80 and d["y"] < self.sh + 90]
        self.pops = [p for p in self.pops if now - p["t"] < 0.25]
        self.update()

    # ---- input ---------------------------------------------------------
    def mousePressEvent(self, ev):
        import time as _t
        if _t.time() - self.start_t < self.countdown:
            return                       # not started yet — no shooting
        mx, my = ev.position().x(), ev.position().y()
        self.shots += 1
        # pew! (respects the general Sounds toggle)
        if self.mgr.cfg["global"].get("sounds", True):
            sfx = getattr(self.mgr, "_sfx", None)
            if sfx is not None:
                sfx.shot()
        hit = None
        for d in reversed(self.ducks):
            if not d["alive"] or d["fall"]:
                continue
            w = sprites.DUCK_W * 4
            h = sprites.DUCK_H * 4
            if d["x"] <= mx <= d["x"] + w and d["y"] <= my <= d["y"] + h:
                hit = d
                break
        if hit:
            hit["fall"] = True
            hit["alive"] = False
            hit["vy"] = 2.0
            hit["vx"] = 0.0
            self.score += hit["pts"]
            self.hits += 1
            if self.score > self.high:
                self.high = self.score          # live high-score climb
            # satisfying bloop on a hit (Sounds toggle respected)
            if self.mgr.cfg["global"].get("sounds", True):
                sfx = getattr(self.mgr, "_sfx", None)
                if sfx is not None:
                    sfx.hit()
            self.pops.append(dict(x=mx, y=my, t=_t.time()))
        else:
            self.pops.append(dict(x=mx, y=my, t=_t.time(), miss=True))
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.stop()

    def stop(self):
        self.running = False
        self._tick.stop()
        # save the high score across sessions
        if self.high > int(self.mgr.cfg["global"].get("duck_high_score", 0)):
            self.mgr.cfg["global"]["duck_high_score"] = int(self.high)
            save_config(self.mgr.cfg)
        self.hide()
        self.mgr._end_duck_hunt()

    # ---- painting ------------------------------------------------------
    def paintEvent(self, _ev):
        from PySide6.QtGui import QPainter, QColor, QFont, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        # faint dim so ducks read against any desktop
        p.fillRect(self.rect(), QColor(10, 12, 20, 40))
        for d in self.ducks:
            wing_down = (int(d["flap"]) % 2 == 1)
            flip = d["vx"] < 0
            key = (wing_down, d["color"], flip)
            img = self._img_cache.get(key)
            if img is None:
                img = sprites.render_duck(wing_down, d["color"], 4, flip)
                self._img_cache[key] = img
            if d["fall"]:
                # tip over when shot
                p.save()
                cx = d["x"] + img.width() / 2
                cy = d["y"] + img.height() / 2
                p.translate(cx, cy)
                p.rotate(180)
                p.translate(-cx, -cy)
                p.drawImage(int(d["x"]), int(d["y"]), img)
                p.restore()
            else:
                p.drawImage(int(d["x"]), int(d["y"]), img)
        # hit/miss puffs
        for pop in self.pops:
            col = QColor(255, 90, 60, 180) if pop.get("miss") \
                else QColor(255, 220, 90, 220)
            r = 10
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(pop["x"], pop["y"]), r, r)
        # HUD — retro arcade score panel, CENTERED at the top, drawn with
        # chunky 3x5 pixel glyphs (no smooth font) so it reads as pixel-art.
        # Black box + white stroke so it never blends into a dark wallpaper.
        from PySide6.QtCore import QRectF
        # arcade layout: the CURRENT score big on top, HIGH SCORE small below
        score_s = f"{self.score:06d}"
        hi_s = f"HIGH {self.high:06d}"
        tp, np_, sp = 3, 6, 3          # title / big-score / high-score cell px
        title = "SCORE"
        tw = sprites.pixel_text_width(title, tp)
        nw = sprites.pixel_text_width(score_s, np_)
        hw = sprites.pixel_text_width(hi_s, sp)
        pw_, ph_ = 320, 118
        pw_ = max(pw_, max(tw, nw, hw) + 44)
        px0 = (self.sw - pw_) // 2     # CENTER horizontally
        py0 = 22
        panel = QRectF(px0, py0, pw_, ph_)
        p.setBrush(QColor(6, 8, 12, 235))
        p.setPen(QPen(QColor(210, 210, 215), 3))    # off-white border
        p.drawRoundedRect(panel, 12, 12)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(70, 80, 100), 1))      # inner accent line
        p.drawRoundedRect(QRectF(px0 + 6, py0 + 6, pw_ - 12, ph_ - 12), 8, 8)
        shadow = QColor(0, 0, 0, 170)
        sprites.draw_pixel_text(
            p, title, px0 + (pw_ - tw) // 2, py0 + 18, tp,
            QColor("#6bb8c7"), shadow)          # soft cyan title
        sprites.draw_pixel_text(
            p, score_s, px0 + (pw_ - nw) // 2, py0 + 40, np_,
            QColor("#e6e6e0"), shadow)          # big current score (off-white)
        sprites.draw_pixel_text(
            p, hi_s, px0 + (pw_ - hw) // 2, py0 + 90, sp,
            QColor("#d9a94a"), shadow)          # small high score (amber)
        # tier legend, also pixelated, centered under the panel
        legend = "BROWN 1  BLUE 2  RED 3   CLICK DUCKS  ESC TO QUIT"
        lp = 2
        lw = sprites.pixel_text_width(legend, lp)
        sprites.draw_pixel_text(
            p, legend, (self.sw - lw) // 2, py0 + ph_ + 10, lp,
            QColor("#9aa0ac"), shadow)
        # 3-2-1-GO! countdown, big and centered — in the pixel font
        import time as _t2
        elapsed = _t2.time() - self.start_t
        if elapsed < self.countdown + 0.6:
            remain = self.countdown - elapsed
            txt = str(int(remain) + 1) if remain > 0 else "GO!"
            cpx = 26                       # big pixel cells for the count
            cw = sprites.pixel_text_width(txt, cpx)
            ch = 5 * cpx
            sprites.draw_pixel_text(
                p, txt, (self.sw - cw) // 2, (self.sh - ch) // 2, cpx,
                QColor(255, 255, 255, 240), QColor(0, 0, 0, 150))
            ready = "GET READY!"
            rpx = 5
            rw = sprites.pixel_text_width(ready, rpx)
            sprites.draw_pixel_text(
                p, ready, (self.sw - rw) // 2, int(self.sh * 0.62), rpx,
                QColor(220, 220, 225, 220), QColor(0, 0, 0, 140))


class GuardBeam(QWidget):
    """Full-screen click-through overlay: a red search beam that sweeps
    around while guard mode is on. Purely visual; never blocks input."""

    def __init__(self, mgr):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.mgr = mgr
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._phase = 0.0

    def _apply_geometry(self):
        scr = (self.mgr.primary().screen()
               or QGuiApplication.primaryScreen())
        self.setGeometry(scr.geometry())

    def tick(self):
        if not self.mgr.cfg["global"].get("guard_mode", False):
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self._apply_geometry()
            self.show()
        self._phase = time.time()
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        # beam originates from a flashlight in the cat's paw (lower part of
        # the sprite), sweeping across the desktop at a shallow angle
        cat = self.mgr.primary()
        try:
            cr = cat.geometry()
            scale = max(1, cat.scale)
            lens = getattr(cat, "_torch_lens", (24, 21))
            # the sprite is drawn at (side, TOP_MARGIN) inside the window,
            # scaled by grow — the lens position must include all of that
            ox = (cr.left() + cat.side
                  + int((lens[0] + 0.5) * scale * cat.grow) - self.x())
            oy = (cr.top() + TOP_MARGIN
                  + int((lens[1] + 1.0) * scale * cat.grow) - self.y())
        except Exception:
            ox, oy = w // 2, h // 2
        t = self._phase
        # sweep like a held flashlight: aim outward-and-down toward the
        # side the torch is held on, panning a moderate arc around it
        try:
            ang = cat._guard_beam_angle(t)
        except Exception:
            ang = 0.62
        length = math.hypot(w, h)
        spread = 0.11
        a1, a2 = ang - spread, ang + spread
        p1 = QPointF(ox + math.cos(a1) * length, oy + math.sin(a1) * length)
        p2 = QPointF(ox + math.cos(a2) * length, oy + math.sin(a2) * length)
        cone = QPolygonF([QPointF(ox, oy), p1, p2])
        # soft red glow cone
        flick = 0.5 + 0.5 * abs(math.sin(t * 9))
        col = QColor(255, 40, 40)
        col.setAlphaF(0.10 + 0.06 * flick)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(cone)
        # brighter inner core line
        core = QColor(255, 80, 80)
        core.setAlphaF(0.22 + 0.12 * flick)
        p.setBrush(core)
        inner = QPolygonF([QPointF(ox, oy),
                           QPointF(ox + math.cos(ang - 0.05) * length,
                                   oy + math.sin(ang - 0.05) * length),
                           QPointF(ox + math.cos(ang + 0.05) * length,
                                   oy + math.sin(ang + 0.05) * length)])
        p.drawPolygon(inner)
        # a red dot where the beam "lands" (near the bottom / cursor area)
        land_r = min(h * 0.7, length * 0.7)
        lx = ox + math.cos(ang) * land_r
        ly = oy + math.sin(ang) * land_r
        dot = QColor(255, 30, 30)
        dot.setAlphaF(0.5 + 0.4 * flick)
        p.setBrush(dot)
        p.drawEllipse(QPointF(lx, ly), 10, 10)


class BubbleWindow(QWidget):
    """A speech bubble in its own window: stretches to fit long text
    (AI answers), floats above the cat, follows it, ignores the mouse."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text = ""
        self.full_text = ""
        self._chars = 0
        self._type_done = True
        self._type_start = 0.0
        self.color = None
        self.until = 0.0
        self.cat = None
        self._pad = 14
        self._tail = 10
        self._margin = 8                   # room for a soft drop shadow

    def show_for(self, cat, text, secs, color=None):
        self.cat = cat
        self.full_text = text
        self.text = ""
        self._chars = 0
        self._type_done = False
        self._type_start = time.time()
        self.color = color
        # the bubble stays up long enough to type out AND then be read
        type_secs = min(2.6, len(text) * 0.022)
        self.until = time.time() + secs + type_secs
        scr = (cat.screen() or QGuiApplication.primaryScreen()).geometry()
        # a comfortable reading width — not so narrow that a short sentence
        # gets crammed onto many stubby lines
        maxtext = max(240, min(460, scr.width() // 2))
        fm = QFontMetrics(QFont("Arial", 10))
        # size to the FULL text so the box doesn't jump while typing; the
        # extra width keeps words off the rounded corners
        br = fm.boundingRect(QRect(0, 0, maxtext, 2000),
                             Qt.TextWordWrap | Qt.AlignLeft, text)
        m = self._margin
        tw = br.width() + 6
        self._tr = QRect(self._pad + m, self._pad + m, tw, br.height() + 2)
        self.resize(tw + self._pad * 2 + m * 2,
                    br.height() + 2 + self._pad * 2 + self._tail + m * 2)
        self.reposition()
        self.show()
        self.update()

    def _advance_type(self):
        if self._type_done:
            return
        # ~45 chars/sec, revealing whole words feels nicer than char-by-char
        elapsed = time.time() - self._type_start
        target = int(elapsed * 48)
        if target >= len(self.full_text):
            self.text = self.full_text
            self._type_done = True
        else:
            # extend to the next space so words pop in whole
            n = target
            ft = self.full_text
            while n < len(ft) and ft[n] not in " \n":
                n += 1
            self.text = ft[:n]
        self._chars = len(self.text)

    def reposition(self):
        c = self.cat
        if c is None:
            return
        scr = (c.screen() or QGuiApplication.primaryScreen()).geometry()
        x = c.x() + c.width() // 2 - self.width() // 2
        x = max(scr.left() + 2, min(x, scr.right() - self.width() - 2))
        y = c.y() - self.height() + int(TOP_MARGIN * 0.8) + self._margin
        y = max(scr.top() + 2, y)
        self.move(x, y)

    def tick(self):
        if not self.isVisible():
            return
        if not self._type_done:
            self._advance_type()
            self.update()
        if time.time() > self.until or self.cat is None:
            self.hide()
            self.cat = None
            return
        self.reposition()

    def paintEvent(self, _ev):
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = self._margin
        w = self.width() - m * 2
        h = self.height() - self._tail - m * 2
        r = 12                                     # corner radius
        cx = m + w // 2
        by = m + h                                 # bubble bottom (tail base)

        # one path = rounded body + a tail merged into the bottom edge, so
        # there's no seam where they meet
        path = QPainterPath()
        path.addRoundedRect(m, m, w, h, r, r)
        tail = QPainterPath()
        tw = 9
        tail.moveTo(cx - tw, by - 1)
        tail.lineTo(cx + tw, by - 1)
        tail.lineTo(cx + 1, by + self._tail)
        tail.lineTo(cx - 1, by + self._tail)
        tail.closeSubpath()
        path = path.united(tail)

        # soft drop shadow: a few offset, fading fills behind the shape
        for i, a in ((6, 22), (4, 34), (2, 44)):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.save()
            p.translate(0, i)
            p.drawPath(path)
            p.restore()

        bg = QColor(self.color) if self.color \
            else QColor(255, 253, 246, 252)
        fg = QColor("#ffffff") if self.color else QColor("#3a2f26")
        border = QColor(255, 255, 255, 90) if self.color \
            else QColor(70, 52, 40, 60)
        p.setPen(QPen(border, 1.5))
        p.setBrush(bg)
        p.drawPath(path)

        p.setPen(fg)
        p.setFont(QFont("Arial", 10))
        shown = self.text
        if not self._type_done and (int(time.time() * 2) & 1):
            shown = shown + "▏"                    # slim blinking caret
        p.drawText(self._tr, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                   shown)


class AskBox(QWidget):
    """A speech-bubble-styled prompt that floats above the cat: cream
    paper, rounded, with a tail pointing down at the cat (Ctrl+Space)."""

    _PAD = 13
    _TAIL = 15
    _GLOW = 10                             # transparent halo margin

    def __init__(self, mgr):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.mgr = mgr
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.cat = None
        # a paper-colored line edit with no chrome — the bubble is the frame
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setStyleSheet(
            "QLineEdit{background:transparent;border:none;"
            "color:#40342a;font-family:Arial;font-size:13px;"
            "font-weight:bold;selection-background-color:#f0c891;"
            "selection-color:#40342a;}")
        self.edit.returnPressed.connect(self._send)

    def open_above(self, cat, name):
        self.cat = cat
        self.edit.setPlaceholderText(f"🐾  Ask {name}…   (Esc to close)")
        self.edit.clear()
        fm = QFontMetrics(QFont("Arial", 13))
        w = max(268, fm.horizontalAdvance(
            self.edit.placeholderText()) + 46)
        eh = fm.height() + 12
        g = self._GLOW
        self.resize(w + self._PAD * 2 + g * 2,
                    eh + self._PAD * 2 + self._TAIL + g * 2)
        self.edit.setGeometry(g + self._PAD + 4, g + self._PAD,
                              w - 8, eh)
        self.reposition()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)
        self.edit.setFocus(Qt.OtherFocusReason)
        self._force_foreground()
        # some window managers hand focus to a brand-new tool window late;
        # re-grab on the next event-loop turns so the first keystroke lands
        for delay in (0, 30, 90, 180):
            QTimer.singleShot(delay, self._grab_focus)

    def _grab_focus(self):
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self._force_foreground()
        self.edit.setFocus(Qt.OtherFocusReason)
        self.edit.setCursorPosition(len(self.edit.text()))

    def _force_foreground(self):
        """On Windows, a background app can't just steal focus — the OS
        foreground lock ignores SetForegroundWindow. Attaching our input
        thread to the current foreground window's thread lets it through,
        so the ask box truly grabs the keyboard and the first keystroke
        lands in it (no click needed)."""
        if platform.system() != "Windows":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            k = ctypes.windll.kernel32
            hwnd = int(self.winId())
            fg = u.GetForegroundWindow()
            cur = k.GetCurrentThreadId()
            fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
            attached = False
            if fg_thread and fg_thread != cur:
                attached = bool(u.AttachThreadInput(fg_thread, cur, True))
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
            if attached:
                u.AttachThreadInput(fg_thread, cur, False)
        except Exception:
            pass

    def reposition(self):
        cat = self.cat
        if cat is None:
            return
        scr = (cat.screen() or QGuiApplication.primaryScreen()).geometry()
        x = cat.x() + cat.width() // 2 - self.width() // 2
        y = cat.y() - self.height() + int(TOP_MARGIN * 0.8) + self._GLOW
        x = max(scr.left() + 4, min(x, scr.right() - self.width() - 4))
        y = max(scr.top() + 4, y)
        self.move(x, y)

    def follow_tick(self):
        if self.isVisible() and self.cat is not None:
            self.reposition()

    _PX = 5                                # bubble pixel size (chunky)

    def paintEvent(self, _ev):
        p = QPainter(self)
        paper = QColor("#fbf6ea")
        edge = QColor("#1c1c22")           # thin near-black border
        px = self._PX
        g = self._GLOW
        W = self.width() - g * 2
        H = self.height() - self._TAIL - g * 2
        gw, gh = W // px, H // px
        cxg = gw // 2
        corner = 3

        def inside(gx, gy):
            if corner <= gx < gw - corner or corner <= gy < gh - corner:
                return 0 <= gx < gw and 0 <= gy < gh
            cxr = corner if gx < corner else gw - 1 - corner
            cyr = corner if gy < corner else gh - 1 - corner
            return (gx - cxr) ** 2 + (gy - cyr) ** 2 <= corner ** 2 + 1

        def is_edge(gx, gy):
            return inside(gx, gy) and not (
                inside(gx - 1, gy) and inside(gx + 1, gy)
                and inside(gx, gy - 1) and inside(gx, gy + 1))

        # 1) soft blue glow: smooth rounded halo behind the box (like eyes)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        for i, a in ((5, 26), (3, 40), (1, 70)):
            gl = QColor("#3ec8ff"); gl.setAlpha(a)
            p.setBrush(gl)
            p.drawRoundedRect(g - i, g - i,
                              W + i * 2, H + i * 2,
                              corner * px + i, corner * px + i)
        # 2) crisp pixel box on top
        p.setRenderHint(QPainter.Antialiasing, False)
        tail_cells = []
        for gy in range(gh):
            for gx in range(gw):
                if not inside(gx, gy):
                    continue
                p.fillRect(g + gx * px, g + gy * px, px, px,
                           edge if is_edge(gx, gy) else paper)
        # thin blocky tail (near-black sides), same grid
        for i, half in enumerate((3, 2, 1)):
            gy = gh + i
            for gx in range(cxg - half, cxg + half + 1):
                onedge = gx in (cxg - half, cxg + half) or i == 2
                p.fillRect(g + gx * px, g + gy * px, px, px,
                           edge if onedge else paper)

    def _send(self):
        t = self.edit.text().strip()
        self.hide()
        if t:
            self.mgr.ask_ai(t)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(ev)


class _CallBridge(QObject):
    """Marshal callables from worker threads onto the GUI thread."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda fn: fn())


class Manager(QObject):
    """Shared services + global state for all cats: input hooks, fullscreen
    detection, agent status, Pomodoro, stretch reminders, tray icon."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cfg = load_config()
        self.anim_test = None
        self.first_run = not os.path.exists(CONFIG_PATH)
        self._call_bridge = _CallBridge()
        if not IS_STORE_BUILD:      # Store build: Microsoft handles updates
            QTimer.singleShot(20000, lambda: self.check_updates(manual=False))
        self._audio = _AudioMeter()
        self.music_mode = "off"
        self.ai_busy = False
        self.guide_active = False        # 🧭 mid guided-tour session
        self._guide_task = None          # the original "how do I…" question
        self._guide_done = []            # labels of completed steps
        self._ai_hist = []
        self._ask_box = None
        self._music_hist = deque(maxlen=24)
        self.music_on = False
        self._music_timer = QTimer()
        self._music_timer.timeout.connect(self._poll_music)
        self._music_timer.start(120)
        self._guard_beam = None
        self._duck_game = None          # easter-egg minigame window
        self._sfx = None                # lazily-built sound engine
        self._guard_timer = QTimer()
        self._guard_timer.timeout.connect(self._tick_guard)
        self._guard_timer.start(33)
        self._guard_say = 0.0
        self._guard_posted = False
        self._guard_off_at = 0.0
        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(
            lambda: self.check_updates(manual=False))
        if not IS_STORE_BUILD:      # Store build updates via Microsoft Store
            self._auto_timer.start(1 * 3600 * 1000)   # hourly
        self.sprites_reloads = 0
        self._watch = None
        self._watch_timer = None
        if self.cfg["global"].get("watch_sprites"):
            QTimer.singleShot(500, self._start_watch)
        self._bridge = _InputBridge()
        self._bridge.poked.connect(self._on_input_event)
        self.inputs = InputWatcher(on_event=self._bridge.poked.emit)
        self.inputs.on_ask = lambda: self._call_bridge.call.emit(
            self.open_ask_box)
        self.inputs.on_esc = lambda: self._call_bridge.call.emit(
            self.dismiss_bubble)
        self.inputs.on_update = lambda: self._call_bridge.call.emit(
            lambda: self.check_updates(manual=True))
        self.inputs.on_restart = lambda: self._call_bridge.call.emit(
            self._restart)
        self.fs_detect = FullscreenDetector()
        self.meow = Meow()

        self.fullscreen_active = False
        self._fs_streak = 0
        self.stretch_until = 0.0
        mins = self.cfg["global"]["stretch_minutes"]
        self.next_stretch = time.time() + mins * 60 if mins > 0 else None

        self.pomo_end = None
        self.pomo_kind = None
        self.pomo_loop = None      # (focus_min, break_min) when looping

        self.agent_working = False
        self.agent_label = ""
        self.celebrate_until = 0.0

        self.cats = []
        for i, ccfg in enumerate(self.cfg["cats"]):
            self.cats.append(CatWindow(self, i))

        self.tray = None
        self._make_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)

        app.aboutToQuit.connect(self.save_all)

    # ------------------------------------------------------------- shared ---
    def primary(self):
        return self.cats[0] if self.cats else None

    def say_primary(self, text, secs=3.0, color=None):
        if self.primary():
            self.primary().say(text, secs, color)

    def _named(self, text):
        n = self.cfg["global"].get("name", "")
        return f"{n}, {text}" if n else text

    def tick(self):
        now = time.time()

        # keep the global input hooks alive
        self.inputs.ensure_alive()

        # fullscreen (auto-peek) — debounced so a single stray reading can't
        # tuck the cat; needs the fullscreen state to hold across two checks
        # (~1s) before hiding, but drops the moment it's no longer fullscreen
        raw_fs = (self.cfg["global"]["auto_peek"] and self.fs_detect.check())
        self._fs_streak = (self._fs_streak + 1) if raw_fs else 0
        self.fullscreen_active = self._fs_streak >= 2

        # scroll accumulation decay
        self.inputs.scroll_accum = max(0.0, self.inputs.scroll_accum - 3.0)

        # pomodoro
        if self.pomo_end is not None:
            remaining = self.pomo_end - now
            if self.tray:
                m, s = divmod(max(0, int(remaining)), 60)
                self.tray.setToolTip(
                    f"{APP_NAME} — {self.pomo_kind} {m:02d}:{s:02d}")
            if remaining <= 0:
                kind = self.pomo_kind
                self.pomo_end = self.pomo_kind = None
                if self.pomo_loop:
                    f, b = self.pomo_loop
                    if kind == "focus":
                        self.pomo_kind, self.pomo_end = "break", now + b * 60
                        self.celebrate(self._named(
                            f"focus done! {b} min break 🎉"))
                    else:
                        self.pomo_kind, self.pomo_end = "focus", now + f * 60
                        self.celebrate(self._named(
                            f"break's over — {f} min focus!"))
                else:
                    self.celebrate(self._named("focus done! Break time? 🎉"
                                               if kind == "focus"
                                               else "break's over — let's go!"))
        elif self.tray and not self.agent_working:
            self.tray.setToolTip(APP_NAME)

        # stretch reminder
        if self.next_stretch and now >= self.next_stretch:
            mins = self.cfg["global"]["stretch_minutes"]
            self.next_stretch = now + mins * 60
            self.stretch_until = now + 6
            for c in self.cats:
                c._unpeek()
            self.say_primary("Stretch time! 🐾  Roll those shoulders", 6)

        # message reminders (persisted)
        rems = self.cfg["global"].get("reminders", [])
        due = [r for r in rems if r[0] <= now]
        if due:
            self.cfg["global"]["reminders"] = [r for r in rems if r[0] > now]
            save_config(self.cfg)
            for (_t, text) in due:
                self.celebrate(self._named(text))
                if self.primary():
                    self.primary().say(self._named(text), 12, "#d9453a")

        # agent status
        kind, label = read_agent_status()
        if kind == "working":
            if not self.agent_working:
                self.agent_working = True
                self.agent_label = label
                self.say_primary(f"{label} is thinking…", 2.5)
            if self.tray:
                self.tray.setToolTip(f"{APP_NAME} — {label} working…")
        elif kind == "done":
            clear_agent_status()
            self.agent_working = False
            self.celebrate(self._named(f"{label} is done! 🎉"))
        elif self.agent_working:
            self.agent_working = False

    # ------------------------------------------------------ self updater --
    UPDATE_BASE = ("https://raw.githubusercontent.com/"
                   "Verisonder/SondeR-Cat/main/")
    UPDATE_FILES = ["sondercat.py", "sprites.py", "sonder_agent.py",
                    "ANIMATIONS.md", "README.md", "requirements.txt",
                    "meow.wav", "sondercat_gray.ico"]

    def _fetch(self, name):
        import urllib.request, urllib.error
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    self.UPDATE_BASE + name,
                    headers={"User-Agent": "SondeRcat"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 429 or e.code >= 500:
                    time.sleep(4 * (attempt + 1))   # back off, then retry
                    continue
                raise
        raise last

    def _local(self, name):
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             name)
            with open(p, "rb") as f:
                return f.read()
        except Exception:
            return b""

    def _remote_version(self):
        import re
        src = self._fetch("sondercat.py").decode("utf-8")
        m = re.search(r'APP_VERSION = "([^"]+)"', src)
        return (m.group(1) if m else None), src

    @staticmethod
    def _version_tuple(v):
        """'8.10.0' -> (8, 10, 0). Non-numeric parts ignored, missing → 0."""
        parts = []
        for p in str(v or "").split("."):
            digits = "".join(ch for ch in p if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts) or (0,)

    def _is_newer_version(self, remote_ver):
        """True only when the remote APP_VERSION is a HIGHER numbered version
        than what's installed (e.g. 8.8.0 -> 8.9.0 / 9.0.0). Build-tag-only
        pushes (same version, new build like 0712k) are NOT 'newer'."""
        if not remote_ver:
            return False
        return self._version_tuple(remote_ver) > self._version_tuple(APP_VERSION)

    def check_updates(self, manual=True):
        """Runs in a worker thread; UI messages go through the bridge."""
        if IS_STORE_BUILD:
            # the Microsoft Store keeps this build up to date automatically
            if manual:
                self.say_primary(
                    "the Microsoft Store keeps me updated automatically 🛍️",
                    3)
            return
        if getattr(self, "_update_busy", False):
            if manual:
                self.say_primary("still checking… 🐾", 3)
            return
        self._update_busy = True
        if manual:
            self.say_primary("checking for updates… 🌐", 4)

        def ui(fn):
            self._call_bridge.call.emit(fn)

        def work():
            try:
                self._work_updates(manual, ui)
            finally:
                self._update_busy = False

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _work_updates(self, manual, ui):
            try:
                ver, remote_main = self._remote_version()
            except Exception as e:
                if manual:
                    msg = ("GitHub is rate-limiting — wait a few minutes "
                           "and try again 🐢") if "429" in str(e) \
                        else "couldn't reach GitHub — try later 🌐"
                    ui(lambda: self.say_primary(msg, 5))
                return
            main_bytes = remote_main.encode("utf-8")
            label = f"v{ver}" if ver and ver != APP_VERSION \
                else f"v{APP_VERSION} refresh"
            if not manual:
                # quiet startup probe: compare the two files that change
                changed = main_bytes != self._local("sondercat.py")
                if not changed:
                    try:
                        changed = (self._fetch("sprites.py")
                                   != self._local("sprites.py"))
                    except Exception:
                        return
                if not changed:
                    return
                # AUTO-UPDATE ONLY FOR A NEW NUMBERED VERSION (8.9, 9.0, …).
                # A build-tag-only refresh (same APP_VERSION, new build like
                # 0712k) is NOT auto-installed — the cat stays quiet about it.
                # (first run always pulls the latest to start fresh.)
                is_new_ver = self._is_newer_version(ver)
                if not (is_new_ver or getattr(self, "first_run", False)):
                    return
                auto = self.cfg["global"].get("auto_update", True)
                if not (auto or getattr(self, "first_run", False)):
                    ui(lambda: self.say_primary(
                        f"{label} is available! menu → Updates",
                        6))
                    return
                ui(lambda: self.say_primary(
                    "getting the freshest version… ⤓"
                    if getattr(self, "first_run", False)
                    else f"auto-updating to {label}… ⤓", 6))
            try:
                # cheap verdict first: the two files every update touches
                blobs = {"sondercat.py": main_bytes,
                         "sprites.py": self._fetch("sprites.py")}
                if all(blobs[n] == self._local(n) for n in blobs):
                    ui(lambda: self.say_primary(
                        f"you're up to date! (v{APP_VERSION})", 4))
                    return
                # something changed: now fetch the rest and diff everything
                for name in self.UPDATE_FILES:
                    if name not in blobs:
                        blobs[name] = self._fetch(name)
                changed = {n: d for n, d in blobs.items()
                           if d != self._local(n)}
                ui(lambda: self.say_primary(
                    f"found {label}! downloading… ⤓", 8))
                # validate BEFORE touching anything
                compile(blobs["sondercat.py"], "sondercat.py", "exec")
                ns = {"__file__": "sprites.py", "__name__": "sprites"}
                exec(compile(blobs["sprites.py"], "sprites.py", "exec"), ns)
                ok, msg = validate_sprites(ns)
                if not ok:
                    raise ValueError(f"bad sprites in update: {msg}")
                app_dir = os.path.dirname(os.path.abspath(__file__))
                for name, data in changed.items():
                    with open(os.path.join(app_dir, name), "wb") as f:
                        f.write(data)
            except Exception as e:
                err = str(e)[:120]
                ui(lambda: self.say_primary(
                    f"update failed, nothing changed ({err})", 6))
                return
            ui(lambda: self.say_primary(
                f"installed {label}! restarting ✨", 3))
            ui(lambda: QTimer.singleShot(1200, self._restart))

    def _restart(self):
        save_config(self.cfg)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sondercat.py")
        try:
            subprocess.Popen([sys.executable, script],
                             cwd=os.path.dirname(script))
        except Exception:
            self.say_primary("updated! restart me to finish 🐾", 8)
            return
        QApplication.instance().quit()

    # --------------------------------------------------- animation tests --
    def test_parachute(self):
        """Demo the parachute: teleport the cat up near the top of the screen,
        then let it float back down under the canopy."""
        c = self.primary()
        try:
            if c.perch_hwnd is not None or c.perch_pending is not None:
                c._end_perch(go_home=False)
            if c.peeking:
                c._unpeek(cancel=True)
            scr = c.screen() or QGuiApplication.primaryScreen()
            g = scr.availableGeometry()
            c.move(c.x(), g.top() + 4)
            c._sync_float()
            c._parachute_to_ground()
        except Exception:
            pass

    def start_anim_test(self, kind, secs=4.0):
        if kind == "paper":
            self.test_scroll()
            return
        self.anim_test = {"kind": kind, "until": time.time() + secs}
        for c in self.cats:
            if kind == "sleep":
                c.yawn_until = time.time() + 0.9


    # ------------------------------------------- live animation editing --
    def sprites_path(self):
        return os.path.abspath(sprites.__file__)

    def open_donate(self):
        """Open the Ko-fi tip page in the browser — SondeR cat is free; this
        is a fully optional way for happy users to chip in."""
        try:
            import webbrowser
            if not webbrowser.open(KOFI_URL):
                raise RuntimeError("no browser")
            self.say_primary("thank you!! every tip helps 🐾💛", 4)
        except Exception:
            try:
                if platform.system() == "Windows":
                    os.startfile(KOFI_URL)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", KOFI_URL])
                else:
                    subprocess.Popen(["xdg-open", KOFI_URL])
                self.say_primary("thank you!! every tip helps 🐾💛", 4)
            except Exception:
                self.say_primary(f"support me here: {KOFI_URL}", 8)

    def open_sprites(self):
        path = self.sprites_path()
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.say_primary("Edit me! Save the file and I'll update 🎨", 4)
        except Exception:
            self.say_primary(f"My art lives at: {path}", 8)

    def do_reload_sprites(self, announce=True):
        ok, msg = reload_sprites()
        if ok:
            self.sprites_reloads += 1
            for c in self.cats:
                c._frame_cache = {}
                c._resize_to_sprite()
                c.update()
            self._make_tray()
            if announce:
                self.say_primary("Animations reloaded! 🎨", 3)
        else:
            QMessageBox.warning(
                None, "SondeR cat — animation edit rejected",
                "Your last edit to sprites.py has a problem, so I'm "
                "keeping the previous art (nothing crashed!).\n\n"
                f"Problem: {msg}\n\n"
                "Fix that line, save again, and I'll retry.")
        return ok

    def _start_watch(self):
        try:
            from PySide6.QtCore import QFileSystemWatcher
            if self._watch is None:
                self._watch = QFileSystemWatcher()
                self._watch.fileChanged.connect(self._sprites_changed)
            if self.sprites_path() not in self._watch.files():
                self._watch.addPath(self.sprites_path())
        except Exception:
            pass

    def _stop_watch(self):
        try:
            if self._watch:
                for f in self._watch.files():
                    self._watch.removePath(f)
        except Exception:
            pass

    def _sprites_changed(self, _path):
        # editors replace the file on save: debounce, reload, re-arm watch
        if self._watch_timer is None:
            self._watch_timer = QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.timeout.connect(self._watched_reload)
        self._watch_timer.start(350)

    def _watched_reload(self):
        self.do_reload_sprites(announce=True)
        self._start_watch()

    def toggle_watch_sprites(self):
        g = self.cfg["global"]
        g["watch_sprites"] = not g.get("watch_sprites", False)
        save_config(self.cfg)
        if g["watch_sprites"]:
            self._start_watch()
            self.say_primary("Watching sprites.py — save to update me!", 4)
        else:
            self._stop_watch()

    def _on_input_event(self):
        """A key/scroll just happened — react NOW, don't wait for the timer."""
        for c in self.cats:
            if not c.dragging:
                c.tick()

    def celebrate(self, text):
        if self.cfg["global"].get("sounds", True):
            self.meow.play()
        now = time.time()
        self.celebrate_until = now + 1.2
        for c in self.cats:
            c._unpeek()
            c.jump_until = now + 1.2
        self.say_primary(text, 6)

    # -------------------------------------------------------------- cats ----
    def add_cat(self):
        src = dict(CAT_DEFAULTS)
        if self.cats:
            src.update(self.cfg["cats"][0])
        used = {c["palette"] for c in self.cfg["cats"]}
        free = [p for p in sprites.PALETTES if p not in used]
        src["palette"] = random.choice(free or list(sprites.PALETTES))
        src["custom_body"] = None
        src["pattern"] = random.choice(sprites.PATTERNS)
        src["pos"] = None
        self.cfg["cats"].append(src)
        cat = CatWindow(self, len(self.cfg["cats"]) - 1)
        self.cats.append(cat)
        cat.say("nyang! 🐾", 2.5)
        self.save_all()

    def remove_cat(self, cat):
        if len(self.cats) <= 1:
            cat.say("I live here now.", 2.5)
            return
        idx = self.cats.index(cat)
        self.cats.pop(idx)
        self.cfg["cats"].pop(idx)
        for i, c in enumerate(self.cats):
            c.index = i
        cat.timer.stop()
        cat.close()
        cat.deleteLater()
        self._make_tray()
        self.save_all()

    def save_all(self):
        for c in self.cats:
            if not c.peeking:
                self.cfg["cats"][c.index]["pos"] = [c.x(), c.y()]
        save_config(self.cfg)

    # -------------------------------------------------------------- tray ----
    def _make_tray(self):
        try:
            p = self.primary()
            icon = QIcon(QPixmap.fromImage(sprites.render_icon(
                p.palette() if p else sprites.PALETTES["orange tabby"],
                p.ccfg["pattern"] if p else "tabby", 4)))
            if self.tray is None:
                self.tray = QSystemTrayIcon(icon)
                self.tray.show()
            else:
                self.tray.setIcon(icon)
            self.tray.setToolTip(APP_NAME)
            if self.primary():
                self._tray_menu = self.primary().build_menu()
                self.tray.setContextMenu(self._tray_menu)
        except Exception:
            self.tray = None

    # ------------------------------------------------------- global actions -
    def start_pomodoro(self, mins, kind, loop=None):
        self.pomo_loop = loop
        self.pomo_end = time.time() + mins * 60
        self.pomo_kind = kind
        self.say_primary(("Focus time! " if kind == "focus" else "Break time! ")
                         + f"{mins}:00 🐾", 4)

    def stop_pomodoro(self):
        self.pomo_end = self.pomo_kind = None
        self.pomo_loop = None
        self.say_primary("Timer stopped")

    def set_stretch(self, mins):
        self.cfg["global"]["stretch_minutes"] = mins
        save_config(self.cfg)
        self.next_stretch = time.time() + mins * 60 if mins > 0 else None
        self.say_primary("Stretch reminders off" if mins == 0
                         else f"I'll remind you every {mins} min")

    def set_wiggle_sens(self, key):
        self.cfg["global"]["wiggle_sens"] = key
        save_config(self.cfg)
        self.say_primary(f"Wiggle sensitivity: {key}", 2.5)

    def scroll_doctor(self):
        iw = self.inputs
        n0 = iw._native.count if iw._native else -1
        p0 = iw.pyn_count
        self.say_primary("SCROLL NOW for 5 seconds!", 5)

        def report():
            n = (iw._native.count - n0) if iw._native else -1
            pc = iw.pyn_count - p0
            nat = ("not installed" if n < 0
                   else f"{n} events" + ("" if (iw._native and iw._native.ok)
                                         else " (hook FAILED to install)"))
            QMessageBox.information(
                None, "Scroll doctor",
                f"During the 5-second window I saw:\n\n"
                f"  Native Windows hook:  {nat}\n"
                f"  pynput listener:      {pc} events\n\n"
                + ("Scroll detection is WORKING — if you don't see the "
                   "paper, tell me." if (n > 0 or pc > 0) else
                   "NO scroll events reached me from either hook. "
                   "Something on this PC (antivirus / security software) "
                   "is blocking global mouse hooks. Screenshot this box "
                   "for me."))
        QTimer.singleShot(5200, report)

    def test_scroll(self):
        """Fake a scroll so the user can see the paper animation exists,
        independent of whether the global scroll hook works."""
        self.inputs.last_scroll = time.time() + 3     # hold it for a bit
        self.inputs.scroll_accum = 35
        if not self.inputs.mouse_ok:
            self.say_primary("(my scroll hook is OFF — see About)", 4)

    def toggle_wiggle_hide(self):
        g = self.cfg["global"]
        g["wiggle_hide"] = not g.get("wiggle_hide", True)
        save_config(self.cfg)

    def toggle_laser(self):
        g = self.cfg["global"]
        g["laser_only"] = not g.get("laser_only", True)
        save_config(self.cfg)
        self.say_primary("I only hunt wiggles now!" if g["laser_only"]
                         else "I'll chase any fast cursor!", 2.5)

    def _poll_music(self):
        if not self.cfg["global"].get("dance_music", True):
            self.music_on = False
            self.music_mode = "off"
            return
        self._music_hist.append(self._audio.peak())
        h = list(self._music_hist)
        if len(h) < 12:
            return
        loud = sum(1 for v in h if v > 0.015)
        meter_on = getattr(self, "_meter_on", False)
        if not meter_on and loud >= int(len(h) * 0.7):
            meter_on = True
        elif meter_on and loud <= int(len(h) * 0.15):
            meter_on = False
        self._meter_on = meter_on
        # sound playing -> headphones on; the full dance-with-notes show
        # only if the user enabled it in Behavior
        if not meter_on:
            self.music_mode = "off"
        elif self.cfg["global"].get("dance_on_sound", False):
            self.music_mode = "dance"
        else:
            self.music_mode = "listen"
        self.music_on = self.music_mode == "dance"

    def music_doctor(self):
        t_end = time.time() + 5

        def step():
            if time.time() > t_end:
                self.say_primary("music doctor done 🎧", 2)
                return
            pk = self._audio.peak()
            c = self.primary()
            self.say_primary(
                f"peak {pk:.3f} | sound "
                f"{'ON' if getattr(self, '_meter_on', False) else 'off'}"
                f" | mode {self.music_mode} | state {c.state}",
                0.6)
            QTimer.singleShot(250, step)
        step()

    def _tick_guard(self):
        on = self.cfg["global"].get("guard_mode", False)
        if on and self._guard_off_at and time.time() >= self._guard_off_at:
            # patrol timer elapsed — stand down automatically
            self._guard_off_at = 0.0
            self._guard_timed_out = True
            self.toggle_guard_mode()
            return
        if on and not self._guard_posted:
            # take up position: top-center of the screen, best view 🔭
            self._guard_posted = True
            for c in self.cats:
                try:
                    c.go_to_guard_post()
                except Exception:
                    pass
        elif not on:
            self._guard_posted = False
        if on and self._guard_beam is None:
            self._guard_beam = GuardBeam(self)
        if self._guard_beam is not None:
            self._guard_beam.tick()
        gg = getattr(self, "_guide_glow", None)
        if gg is not None:
            gg.tick()                     # pulse/expire the guide highlight
        if on:
            now = time.time()
            if now - self._guard_say > 6 and random.random() < 0.02:
                self._guard_say = now
                self.say_primary(random.choice([
                    "HALT. who goes there? 🔦", "identify yourself!",
                    "🚨 intruder scan…", "state your business.",
                    "eyes on you. 👁", "perimeter secure… for now."]), 2.5)

    def toggle_guard_mode(self):
        g = self.cfg["global"]
        g["guard_mode"] = not g.get("guard_mode", False)
        save_config(self.cfg)
        CatWindow._HELMET_CACHE.clear()
        if g["guard_mode"]:
            self._end_guide(walk_home=False, quiet=True)   # duty calls
            for c in self.cats:
                c.groom_until = 0.0     # no grooming on duty — focus.
            mins = int(g.get("guard_timer_min", 0) or 0)
            if mins > 0:
                self._guard_off_at = time.time() + mins * 60
                self.say_primary(
                    f"GUARD MODE ENGAGED — {mins} min patrol. 🫡🔦", 3)
            else:
                self._guard_off_at = 0.0
                self.say_primary("GUARD MODE ENGAGED. 🫡🔦", 3)
        else:
            self._guard_off_at = 0.0
            if getattr(self, "_guard_timed_out", False):
                self._guard_timed_out = False
                self.say_primary("patrol over — standing down. 😌🔦", 3)
            else:
                self.say_primary("at ease. 😌", 3)
            if self._guard_beam is not None:
                self._guard_beam.hide()
            for c in self.cats:         # ☂ float back down off the post
                try:
                    if c.glide_target is None and c.perch_hwnd is None \
                            and not c.peeking:
                        c._parachute_to_ground()
                except Exception:
                    pass

    def set_guard_timer(self, minutes):
        """Set the auto-off duration (0 = manual). If guard mode is already
        on, (re)arm the countdown from now."""
        minutes = max(0, int(minutes))
        self.cfg["global"]["guard_timer_min"] = minutes
        save_config(self.cfg)
        if self.cfg["global"].get("guard_mode", False):
            self._guard_off_at = (time.time() + minutes * 60) if minutes else 0.0
            if minutes:
                self.say_primary(f"patrol timer set: {minutes} min. ⏱", 2.5)
            else:
                self.say_primary("patrol timer off — on duty until dismissed.",
                                 2.5)
        else:
            if minutes:
                self.say_primary(
                    f"guard auto-off set to {minutes} min (next patrol). ⏱",
                    2.5)

    def pick_guard_timer(self):
        try:
            from PySide6.QtWidgets import QInputDialog
        except Exception:
            return
        cur = int(self.cfg["global"].get("guard_timer_min", 0) or 0)
        mins, ok = QInputDialog.getInt(
            None, "Guard auto-off timer",
            "Minutes on patrol before standing down\n(0 = stay on until "
            "you switch it off):",
            cur, 0, 720, 1)
        if ok:
            self.set_guard_timer(mins)

    def toggle_hide_mode(self):
        g = self.cfg["global"]
        g["hide_mode"] = not g.get("hide_mode", False)
        save_config(self.cfg)
        if g["hide_mode"]:
            self.say_primary("hiding! untoggle me in the menu to come out 🫣",
                             3)
        else:
            self.exit_hide_mode()

    def exit_hide_mode(self):
        self.cfg["global"]["hide_mode"] = False
        save_config(self.cfg)
        for c in self.cats:
            c.manual_peek = False
            if c.peeking:
                c.peeking = False
                c._saved_pos = None          # no going back: stand here
                try:
                    g = c._ground_point()
                    c.move(g)
                    c._sync_float()
                except Exception:
                    pass
                c.state = IDLE
        self.say_primary("mrrp! 🐾", 2)

    def toggle_dance_on_sound(self):
        g = self.cfg["global"]
        g["dance_on_sound"] = not g.get("dance_on_sound", False)
        save_config(self.cfg)

    def toggle_dance_music(self):
        g = self.cfg["global"]
        g["dance_music"] = not g.get("dance_music", True)
        save_config(self.cfg)

    def toggle_auto_update(self):
        g = self.cfg["global"]
        g["auto_update"] = not g.get("auto_update", True)
        save_config(self.cfg)

    PERCH_FREQS = {
        "rarely":    (300, 600),
        "sometimes": (180, 420),
        "often":     (90, 210),
        "very":      (35, 90),
        "instant":   (2, 5),
    }

    def perch_interval(self):
        key = self.cfg["global"].get("perch_freq", "instant")
        return self.PERCH_FREQS.get(key, self.PERCH_FREQS["often"])

    def set_perch_nap(self, chance):
        self.cfg["global"]["perch_nap_chance"] = chance
        save_config(self.cfg)
        labels = {0.0: "I'll always keep watch up there 👀",
                  0.3: "mostly watching, sometimes napping 👀",
                  0.6: "a balanced mix of naps and watching",
                  0.9: "mostly napping up there 💤"}
        self.say_primary(labels.get(chance, ""), 3)

    def set_perch_freq(self, key):
        g = self.cfg["global"]
        g["perch_freq"] = key
        g["window_perch"] = (key != "off")
        save_config(self.cfg)
        labels = {"off": "I'll stay off your windows",
                  "rarely": "I'll rarely climb up",
                  "sometimes": "I'll sometimes climb up",
                  "often": "I'll often climb your windows 🪟",
                  "very": "I'll climb up a lot! 🪟",
                  "instant": "I'll hop on windows the moment I can! 🪟"}
        self.say_primary(labels.get(key, ""), 3)
        # make the change take effect soon, not after the old long wait
        if key != "off":
            lo, hi = self.perch_interval()
            for c in self.cats:
                c.next_perch_try = time.time() + random.uniform(
                    min(8, lo), min(20, hi))

    def toggle_window_perch(self):
        g = self.cfg["global"]
        g["window_perch"] = not g.get("window_perch", True)

    CORNER_FREQS = {
        "rarely":    (420, 900),
        "sometimes": (180, 420),
        "often":     (90, 210),
        "very":      (40, 100),
    }

    # guide-mode speed/accuracy profiles:
    # (thinking budget, run zoom pass?, web-search grounding?, shot width).
    # Grounding is the slowest + most rate-limited part on free keys, so
    # only Accurate pays for it; smaller screenshots cost fewer input
    # tokens per request.
    GUIDE_QUALITY = {
        "fast":     (0,   False, False, 1280),
        "balanced": (128, True,  False, 1280),
        "accurate": (512, True,  True,  1600),
    }

    def guide_profile(self):
        key = self.cfg["global"].get("guide_quality", "fast")
        return self.GUIDE_QUALITY.get(key, self.GUIDE_QUALITY["fast"])

    def set_guide_quality(self, key):
        self.cfg["global"]["guide_quality"] = key
        save_config(self.cfg)
        nice = {"fast": "Fast", "balanced": "Balanced",
                "accurate": "Accurate"}.get(key, key)
        self.say_primary(f"guide speed set to {nice} 🧭", 3)

    def corner_interval(self):
        key = self.cfg["global"].get("corner_freq", "sometimes")
        return self.CORNER_FREQS.get(key, self.CORNER_FREQS["sometimes"])

    def toggle_corner_stand(self):
        g = self.cfg["global"]
        g["corner_stand"] = not g.get("corner_stand", False)
        save_config(self.cfg)
        if g["corner_stand"]:
            self.say_primary("I'll go chill in a corner now and then. 🧍",
                             3)
            lo, hi = self.corner_interval()
            for c in self.cats:
                c.next_corner_at = time.time() + random.uniform(
                    min(10, lo), min(30, hi))
        else:
            self.say_primary("okay, no more corner-standing.", 3)

    def set_corner_freq(self, key):
        g = self.cfg["global"]
        if key == "never":
            g["corner_stand"] = False
            save_config(self.cfg)
            self.say_primary("okay, no more corner-standing.", 3)
            return
        g["corner_freq"] = key
        g["corner_stand"] = True
        save_config(self.cfg)
        labels = {"rarely": "I'll rarely go stand in a corner",
                  "sometimes": "I'll sometimes go stand in a corner",
                  "often": "I'll often go stand in a corner 🧍",
                  "very": "I'll go corner-standing a lot! 🧍"}
        self.say_primary(labels.get(key, ""), 3)
        lo, hi = self.corner_interval()
        for c in self.cats:
            c.next_corner_at = time.time() + random.uniform(
                min(10, lo), min(30, hi))
        save_config(self.cfg)
        if not g["window_perch"]:
            for c in self.cats:
                if c.perch_hwnd is not None or c.perch_pending is not None:
                    c._end_perch(go_home=True)

    def toggle_force_sleep(self):
        g = self.cfg["global"]
        g["force_sleep"] = not g.get("force_sleep", False)
        save_config(self.cfg)
        if g["force_sleep"]:
            self.say_primary("zzz… (untick Deep sleep 💤 in my menu)", 4)
        else:
            for c in self.cats:
                c.sleep_at = time.time() + g["sleep_seconds"]
                c.state = IDLE
            self.say_primary("mrrp! I'm awake 🐾", 3)

    def toggle_sounds(self):
        g = self.cfg["global"]
        g["sounds"] = not g.get("sounds", True)
        save_config(self.cfg)
        if g["sounds"]:
            self.meow.play()
            if self._duck_game is not None and self._sfx is not None:
                self._sfx.music_start()
        elif self._sfx is not None:
            self._sfx.music_stop()

    def set_sound_volume(self, v):
        self.cfg["global"]["sound_volume"] = round(max(0.0, min(1.0, v)), 2)
        save_config(self.cfg)
        if self._sfx is not None:
            self._sfx.set_volume(v)

    def toggle_auto_peek(self):
        self.cfg["global"]["auto_peek"] = not self.cfg["global"]["auto_peek"]
        save_config(self.cfg)

    @staticmethod
    def parse_when(text):
        """'21:30' -> today/tomorrow at that time; '45' -> minutes from now."""
        text = text.strip()
        import re as _re
        m = _re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh > 23 or mm > 59:
                return None
            lt = time.localtime()
            target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                  hh, mm, 0, 0, 0, -1))
            if target <= time.time():
                target += 24 * 3600
            return target
        if text.isdigit():
            return time.time() + int(text) * 60
        return None

    def dismiss_bubble(self):
        # Esc means "I'm done" — end any guided tour so the glowing
        # power-eyes switch back off.
        if self.guide_active or self._guide_task is not None:
            self._end_guide(walk_home=True, quiet=True)
        bw = getattr(self, "_bubble_win", None)
        if bw is not None and bw.isVisible():
            bw.hide()
            bw.cat = None
        ab = getattr(self, "_ask_box", None)
        if ab is not None and ab.isVisible():
            ab.clearFocus()
            ab.hide()
            ab.setVisible(False)
        # also clear a short inline answer, if one is showing
        p = self.primary()
        if p.bubble_text and time.time() < p.bubble_until:
            p.bubble_until = 0
            p.bubble_text = ""
            p.update()

    def show_big_bubble(self, cat, text, secs, color=None):
        if getattr(self, "_bubble_win", None) is None:
            self._bubble_win = BubbleWindow()
        self._bubble_win.show_for(cat, text, secs, color)

    def open_ask_box(self):
        p = self.primary()
        if self.cfg["global"].get("guard_mode", False):
            # on patrol — no chit-chat
            p.say(random.choice([
                "not now — I'm on duty. 🫡", "busy guarding! ask me later.",
                "can't talk, patrolling. 🔦", "at my post — off duty for Q&A."
            ]), 2.5)
            return
        name = (p.ccfg.get("name") or "").strip()
        if not name:
            p.say("I need a name first! ✏️", 3)
            p.rename_cat()
            name = (p.ccfg.get("name") or "").strip()
            if not name:
                return
        if not self.cfg["global"].get("gemini_key", "").strip():
            p.say("add a Gemini API key first 🔑 (menu → AI)", 5)
            return
        if self._ask_box is None:
            self._ask_box = AskBox(self)
        self._ask_box.open_above(p, name)

    def toggle_screen_vision(self):
        g = self.cfg["global"]
        if not g.get("screen_vision", False):
            # one-time privacy acknowledgement — this feature sends a
            # screenshot to Google, and the free Gemini tier may train on it.
            if not g.get("vision_consent", False):
                ok = QMessageBox.question(
                    None, f"{APP_NAME} — Let me check your screen",
                    "With this on, when you ask the cat about something on "
                    "your screen (\"what's this error?\", \"what does this "
                    "mean?\"), it takes a picture of your screen and sends "
                    "it to Google's Gemini to answer.\n\n"
                    "On the free Gemini tier, Google may use what you send "
                    "to improve their models. So please DON'T ask about "
                    "passwords, private messages, or confidential "
                    "information on screen.\n\n"
                    "The cat only looks when you actually ask about the "
                    "screen — never on its own.\n\n"
                    "Do you understand and want to turn it on?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ok != QMessageBox.Yes:
                    return
                g["vision_consent"] = True
            g["screen_vision"] = True
            save_config(self.cfg)
            self.say_primary(
                "I can peek at your screen when you ask about it now 👀", 4)
        else:
            g["screen_vision"] = False
            # guide mode can't work without screen vision — turning vision
            # off while guide is on would leave it in a broken state, so
            # switch guide off (and end any active tour) too.
            if g.get("guide_mode", False):
                g["guide_mode"] = False
                self._end_guide(walk_home=True, quiet=True)
                save_config(self.cfg)
                self.say_primary(
                    "screen peeking off — guide mode turned off too 👀", 5)
            else:
                save_config(self.cfg)
                self.say_primary("screen peeking off", 4)

    # ------------------------------------------------ guide mode 🧭 --------
    def toggle_guide_mode(self):
        g = self.cfg["global"]
        if not g.get("guide_mode", False):
            if not g.get("screen_vision", False):
                self.say_primary(
                    "guide mode needs 'Let me check your screen 👀' — "
                    "turn that on first!", 5)
                return
            # one-time data-collection acknowledgement: guide mode sends a
            # screenshot of your screen to Google, and the free Gemini tier
            # may use those requests to improve its models.
            if not g.get("guide_consent", False):
                ok = QMessageBox.question(
                    None, f"{APP_NAME} — Guide me on screen (beta)",
                    "Guide mode takes a picture of your screen and sends it "
                    "to Google's Gemini to find what you asked about.\n\n"
                    "On the free Gemini tier, Google may use what you send "
                    "to improve their models. So please DON'T guide over "
                    "passwords, private messages, personal or confidential "
                    "information on screen.\n\n"
                    "It also uses more of your Gemini quota than normal "
                    "chat — each step makes a couple of requests to find "
                    "things accurately — but for personal use you won't get "
                    "near the free-tier limits.\n\n"
                    "This feature is in beta and may not always be accurate.\n\n"
                    "Do you understand and want to turn it on?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ok != QMessageBox.Yes:
                    return
                g["guide_consent"] = True
            g["guide_mode"] = True
            save_config(self.cfg)
            self.say_primary(
                "guide mode ON 🧭 — ask me how to do something "
                "(Ctrl+Space) and I'll walk you there! say 'next' between "
                "steps, 'stop' to end.", 7)
        else:
            g["guide_mode"] = False
            save_config(self.cfg)
            self._end_guide(walk_home=True, quiet=True)
            self.say_primary("guide mode off.", 3)

    def _grab_screen_for_guide(self, maxw=1280):
        """Screenshot as base64 JPEG + the LOGICAL screen geometry, so
        Gemini's normalized coordinates can be mapped back to real window
        positions. Returns (b64, QRect) or (None, None)."""
        try:
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            # hide our own glow first — it must not photobomb the screenshot
            # (the model could mistake the blue blob for a UI element)
            gg = getattr(self, "_guide_glow", None)
            if gg is not None and gg.isVisible():
                gg.hide()
                QApplication.processEvents()
            # capture the screen the ACTIVE window is on (multi-monitor):
            # the thing being asked about is almost always in the foreground
            scr = None
            if platform.system() == "Windows":
                try:
                    import ctypes
                    from ctypes import wintypes
                    u = ctypes.windll.user32
                    hwnd = u.GetForegroundWindow()
                    rct = wintypes.RECT()
                    if hwnd and u.GetWindowRect(hwnd, ctypes.byref(rct)):
                        mid = QPoint((rct.left + rct.right) // 2,
                                     (rct.top + rct.bottom) // 2)
                        scr = QGuiApplication.screenAt(mid)
                except Exception:
                    scr = None
            if scr is None:
                scr = (self.primary().screen()
                       or QGuiApplication.primaryScreen())
            geom = scr.geometry()
            pm = scr.grabWindow(0)
            # width comes from the speed profile: bigger = sharper for the
            # model but more input tokens per request
            if pm.width() > maxw:
                pm = pm.scaledToWidth(maxw, Qt.SmoothTransformation)
            # keep the exact image we send, for the zoom-refine pass
            # (QImage is safe to crop/save from the worker thread)
            self._guide_img = pm.toImage()
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            pm.save(buf, "JPEG", 88)       # higher quality → sharper text/icons
            buf.close()
            import base64
            return base64.b64encode(bytes(ba)).decode(), geom
        except Exception:
            return None, None

    def start_minigame(self, which="duckhunt"):
        """Launch a minigame from the Minigames menu."""
        if which == "duckhunt":
            self._start_duck_hunt()

    def _start_duck_hunt(self):
        if self._duck_game is not None:
            return
        c = self.primary()
        # end anything that owns the cat, then strike the gunner pose in the
        # bottom-left corner
        self._end_guide(walk_home=False, quiet=True)
        if self.cfg["global"].get("guard_mode"):
            self.cfg["global"]["guard_mode"] = False
            save_config(self.cfg)
        c.duck_gunner = True
        c._enter_duck_corner()
        c.say("🦆 DUCK HUNT! click the ducks — Esc to quit", 5)
        self._duck_game = DuckHuntGame(self)
        # optional 8-bit soundtrack (general Sounds toggle)
        if self.cfg["global"].get("sounds", True):
            try:
                if self._sfx is None:
                    self._sfx = SoundFX(
                        self.cfg["global"].get("sound_volume", 0.6))
                self._sfx.music_start()
            except Exception:
                pass

    def _end_duck_hunt(self):
        self._duck_game = None
        if self._sfx is not None:
            self._sfx.music_stop()
        c = self.primary()
        c.duck_gunner = False
        try:
            c._parachute_to_ground()
        except Exception:
            pass

    def _end_guide(self, walk_home=True, quiet=False):
        """Close the guided-tour session (glowy eyes off, cat back home)."""
        if not self.guide_active and self._guide_task is None:
            return
        self.guide_active = False
        self._guide_task = None
        self._guide_done = []
        self.ai_busy = False             # in case Esc landed mid-request
        gg = getattr(self, "_guide_glow", None)
        if gg is not None:
            gg.hide()                    # highlight off with the tour
        if not quiet:
            self.say_primary("tour's over! 🐾", 3)
        if walk_home:
            try:
                c = self.primary()
                if c.perch_hwnd is None and not c.peeking:
                    # float down under the parachute for a cute exit (it
                    # only actually deploys if the cat is up high; otherwise
                    # it just walks down)
                    c._parachute_to_ground()
            except Exception:
                pass

    def _guide_zoom_refine(self, label, box, _json, clean, think_budget=128):
        """Second-pass localization: crop the region around the first box,
        zoom in, and re-ask (ungrounded, image-only) for a tight box in the
        crop. Returns refined (nx, ny) normalized to the FULL image, or
        None to keep the first-pass center. Runs on the worker thread —
        QImage ops are thread-safe."""
        img = getattr(self, "_guide_img", None)
        if img is None or img.isNull():
            return None
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        W, H = img.width(), img.height()
        bt, bl, bb, br = box
        # box → pixels, expand to ~3x with a floor so tiny boxes get context
        x0, x1 = bl / 1000.0 * W, br / 1000.0 * W
        y0, y1 = bt / 1000.0 * H, bb / 1000.0 * H
        bw, bh = max(20.0, x1 - x0), max(16.0, y1 - y0)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rw = min(W, max(bw * 3.0, 260.0))
        rh = min(H, max(bh * 3.0, 200.0))
        rx = max(0, min(int(cx - rw / 2), W - int(rw)))
        ry = max(0, min(int(cy - rh / 2), H - int(rh)))
        rw, rh = int(rw), int(rh)
        crop = img.copy(rx, ry, rw, rh)
        if crop.width() < 640:                    # zoom small crops up
            crop = crop.scaledToWidth(640, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        crop.save(buf, "JPEG", 90)
        buf.close()
        import base64
        b64 = base64.b64encode(bytes(ba)).decode()
        persona2 = (
            "This is a zoomed-in crop of a screenshot. Locate the element "
            f"described as: {label!r}. Respond with ONLY minified JSON: "
            '{"found":true,"box":[112,204,146,318]} where box is the TIGHT '
            "bounding box [top,left,bottom,right], each an INTEGER "
            "normalized 0-1000 of THIS image's height/width. If it isn't "
            'in this crop, reply {"found":false}.')
        contents2 = [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}]
        raw = clean(self._gemini_call(contents2, persona2,
                                      ground_with_image=False,
                                      max_tokens=768, think=think_budget))
        d2 = _json.loads(raw)
        if not d2.get("found"):
            return None
        zt, zl, zb, zr = [float(v) for v in d2.get("box")]
        czx = (zl + zr) / 2.0 / 1000.0            # crop-relative 0..1
        czy = (zt + zb) / 2.0 / 1000.0
        fx = (rx + czx * rw) / W * 1000.0         # back to full-image 0-1000
        fy = (ry + czy * rh) / H * 1000.0
        # distrust a refinement that jumped outside the crop region
        if not (0 <= fx <= 1000 and 0 <= fy <= 1000):
            return None
        return fx, fy

    def _guide_step_run(self, task, first):
        """One step of the guided tour: screenshot → Gemini locates the next
        UI element → the cat walks there and points. Worker-threaded."""
        import threading, json as _json
        p = self.primary()
        if self.ai_busy:
            p.say("one sec… 🤔", 2)
            return
        think_budget, do_zoom, do_ground, shot_w = self.guide_profile()
        shot, geom = self._grab_screen_for_guide(maxw=shot_w)
        if not shot:
            p.say("I couldn't grab the screen 😿", 4)
            return
        self.ai_busy = True
        self.guide_active = True
        self._guide_task = task
        p.say("let me look… 👀" if first else "checking what's next… 👀", 8)
        step_no = len(self._guide_done) + 1
        done_txt = ("Steps ALREADY completed by the user: "
                    + "; ".join(f"{i+1}) {d}"
                                for i, d in enumerate(self._guide_done))
                    if self._guide_done else "This is the FIRST step.")
        persona = (
            "You are an on-screen guide inside a desktop-pet app. The user "
            "asked how to do something in the app shown in the screenshot. "
            "Figure out the ACTUAL correct way to do it using what you know "
            "and Google Search when useful — do NOT guess from the "
            "screenshot alone. Then find the SINGLE next UI element the "
            "user must interact with, and locate it PRECISELY in the "
            "screenshot. Respond with ONLY minified JSON, no markdown, no "
            "code fences, exactly this shape: "
            '{"found":true,"box":[100,200,140,320],"label":"element name",'
            '"say":"short friendly instruction","last":false,"done":false}'
            " . box is the TIGHT bounding box of just that ONE element (not "
            "its whole row, toolbar or panel), in the order top, left, "
            "bottom, right, each normalized 0-1000 of the image height (y) "
            "and width (x). box MUST contain four plain INTEGERS like "
            "[112,204,146,318] — NEVER letters or placeholder words. Hug "
            "the element's real edges — a small button gives a small box. "
            "Keep 'say' under 22 "
            "words and make it match how the app actually works. Set "
            "\"last\":true when THIS element is the FINAL step that "
            "completes the whole task (a simple one-click task is last:true "
            "on the very first step) — do NOT set last:true if the user "
            "will still need another step after this one. Set done=true "
            "(and make 'say' a short wrap-up) only when the task is ALREADY "
            "fully complete in the screenshot with nothing left to point "
            "at. Set found=false if the needed element isn't on screen yet "
            "(then 'say' explains what to open or click first to get "
            "there).")
        contents = [{"role": "user", "parts": [
            {"text": f"Task: {task}\nStep number: {step_no}\n{done_txt}"},
            {"inline_data": {"mime_type": "image/jpeg", "data": shot}}]}]

        def ui(fn):
            self._call_bridge.call.emit(fn)

        def work():
            try:
                def clean(raw):
                    raw = raw.strip()
                    if raw.startswith("```"):
                        raw = raw.strip("`")
                        if raw.lower().startswith("json"):
                            raw = raw[4:]
                    raw = raw.strip()
                    if not raw.startswith("{"):
                        # grounding can prepend/append citation text — pull
                        # out the JSON object itself
                        i, j = raw.find("{"), raw.rfind("}")
                        if i != -1 and j != -1 and j > i:
                            raw = raw[i:j + 1]
                    return raw

                raw = clean(self._gemini_call(contents, persona,
                                              ground_with_image=(first
                                                                 and do_ground),
                                              max_tokens=1024,
                                              think=think_budget))
                try:
                    d = _json.loads(raw)
                except Exception:
                    # salvage 1: quote bare words (e.g. a literal
                    # [ymin,xmin,...] the model echoed) so it parses, then
                    # the box logic falls back gracefully
                    try:
                        fixed = re.sub(
                            r'(?<=[\[,:])\s*'
                            r'(?!true\b|false\b|null\b)'
                            r'([A-Za-z_][A-Za-z_0-9]*)'
                            r'\s*(?=[,\]\}])', r'"\1"', raw)
                        d = _json.loads(fixed)
                    except Exception:
                        # salvage 2: one UNGROUNDED retry — grounded replies
                        # can carry citation markup that corrupts JSON, the
                        # plain image-only call returns much cleaner JSON
                        retry = contents + [
                            {"role": "model", "parts": [{"text": raw[:500]}]},
                            {"role": "user", "parts": [{"text":
                                "That was INVALID JSON. Reply again with "
                                "ONLY valid minified JSON in the exact "
                                "shape requested. box must be four plain "
                                "integers like [112,204,146,318] — no "
                                "letters, no placeholder words, no "
                                "comments."}]}]
                        raw = clean(self._gemini_call(
                            retry, persona, ground_with_image=False,
                            max_tokens=1024, think=think_budget))
                        try:
                            d = _json.loads(raw)
                        except Exception as je:
                            # keep a snippet so the error actually tells us
                            # what the model sent
                            raise RuntimeError(
                                f"{je} — reply began: {raw[:80]!r}") from None

                # coordinate extraction + accuracy passes happen HERE in the
                # worker (network calls must stay off the UI thread)
                nx = ny = None
                hedge = False
                if d.get("found") and not d.get("done"):
                    box = d.get("box")
                    try:
                        bt, bl, bb, br = [float(v) for v in box]
                        nx = (bl + br) / 2.0
                        ny = (bt + bb) / 2.0
                        area = max(0.0, (bb - bt)) * max(0.0, (br - bl)) / 1e6
                        if area > 0.40:
                            # boxed a whole panel, not the element — hedge
                            hedge = True
                        elif area < 0.0015 or not do_zoom:
                            # already a tiny, tight box (precise enough), or
                            # the speed profile skips zoom → keep first pass
                            pass
                        else:
                            # ZOOM PASS: crop around the box, re-ask on the
                            # zoomed crop for a precise fix. Any failure →
                            # keep the first-pass center.
                            try:
                                zoomed = self._guide_zoom_refine(
                                    str(d.get("label") or "the element"),
                                    (bt, bl, bb, br), _json, clean,
                                    think_budget)
                                if zoomed is not None:
                                    nx, ny = zoomed
                            except Exception:
                                pass
                    except Exception:              # fallback: a center point
                        try:
                            nx = float(d.get("x", 500))
                            ny = float(d.get("y", 500))
                        except Exception:
                            nx, ny = 500.0, 500.0
                            hedge = True
                    nx = max(0, min(1000, int(round(nx))))
                    ny = max(0, min(1000, int(round(ny))))

                def apply():
                    self.ai_busy = False
                    say = str(d.get("say") or "").strip()
                    if d.get("done"):
                        self.primary().say(
                            (say or "all done!") + " 🎉", 8)
                        self._end_guide(walk_home=True, quiet=True)
                        return
                    if not d.get("found"):
                        gg = getattr(self, "_guide_glow", None)
                        if gg is not None:
                            gg.hide()    # don't leave a stale highlight
                        self.primary().say(
                            say or "hmm, I can't spot it from here… 🤔", 8)
                        return
                    label = str(d.get("label") or "here").strip()
                    if hedge:
                        say = ("somewhere around here — " + say) if say \
                            else "somewhere around here!"
                    tx = geom.left() + nx * geom.width() // 1000
                    ty = geom.top() + ny * geom.height() // 1000
                    c = self.primary()
                    # stand BESIDE the target (whichever side has room), so
                    # the cat never covers the thing you need to click; the
                    # blue glow marks the exact spot instead.
                    gapx = c.width() // 2 + 40
                    if tx - geom.left() > geom.right() - tx:
                        wx = tx - gapx - c.width() // 2   # room on the left
                    else:
                        wx = tx + gapx - c.width() // 2   # room on the right
                    wx = max(geom.left(), min(wx, geom.right() - c.width()))
                    wy = max(geom.top(),
                             min(ty - c.height() // 2,
                                 geom.bottom() - c.height()))
                    if c.perch_hwnd is not None:
                        c._end_perch(go_home=False)
                    c.manual_peek = False
                    c._sync_float()
                    c._glide_to(QPoint(wx, wy), speed=800)
                    # soft power-eye-blue glow on the exact target
                    if getattr(self, "_guide_glow", None) is None:
                        self._guide_glow = GuideGlow()
                    self._guide_glow.show_at(tx, ty, secs=45.0)
                    self._guide_done.append(label)
                    if d.get("last"):
                        # final (or only) step — point it out, then wrap up
                        # on its own; no "next" needed.
                        c.say(f"here — {label}! {say} 👇  "
                              "that's the last step! 🎉", 11)
                        import threading as _th
                        _t = _th.Timer(
                            6.5, lambda: self._call_bridge.call.emit(
                                lambda: self._end_guide(walk_home=True,
                                                        quiet=True)))
                        _t.daemon = True
                        _t.start()
                    else:
                        c.say(f"here — {label}! {say} 👇  "
                              "(say 'next' when done)", 12)
                ui(apply)
            except Exception as e:
                msg = str(e)[:140]

                def fail():
                    self.ai_busy = False
                    # end the session so the power-eyes and glow switch off
                    # instead of glowing forever at a dead tour
                    self._end_guide(walk_home=False, quiet=True)
                    if "429" in msg:
                        self.primary().say(
                            "Google says I'm thinking too fast 😅 — wait "
                            "a few seconds and ask me again!", 8)
                    else:
                        self.primary().say(
                            f"my guide-brain glitched… ({msg}) — "
                            "ask me again to retry!", 8)
                ui(fail)
        threading.Thread(target=work, daemon=True).start()

    def set_gemini_key(self):
        cur = self.cfg["global"].get("gemini_key", "")
        key, ok = QInputDialog.getText(
            None, "Gemini API key",
            "Paste your Google Gemini API key\n"
            "(free at aistudio.google.com — stored only on this PC):",
            QLineEdit.Password, cur)
        if not ok:
            return
        self.cfg["global"]["gemini_key"] = key.strip()
        save_config(self.cfg)
        self.say_primary("brain installed! 🧠 Ctrl+Space to ask me"
                         if key.strip() else "API key removed", 4)

    @staticmethod
    def _gemini_parse(data):
        parts = data["candidates"][0]["content"]["parts"]
        text = " ".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise RuntimeError("empty answer")
        return text

    def _gemini_call(self, contents, persona, ground_with_image=False,
                     max_tokens=400, think=None):
        import urllib.request
        import urllib.error
        key = self.cfg["global"].get("gemini_key", "").strip()
        models = []
        if getattr(self, "_gemini_model", None):
            models.append(self._gemini_model)
        # Current Gemini lineup (as of mid-2026). Gemini 1.5 and 2.0 are shut
        # down (they 404), so they're gone. Ordered fast→fallback; the
        # "-latest" aliases auto-track Google's current pick so this list
        # keeps working as models roll over (2.5-flash retires Oct 2026).
        for m in ("gemini-flash-latest",       # → current GA flash (3.5)
                  "gemini-3.5-flash",
                  "gemini-3.1-flash-lite",
                  "gemini-flash-lite-latest",
                  "gemini-2.5-flash",           # still live today; older
                  "gemini-2.5-flash-lite"):
            if m not in models:
                models.append(m)
        has_image = any("inline_data" in pt
                        for msg in contents for pt in msg.get("parts", []))
        # current models (3.x + -latest aliases) CAN combine google_search
        # grounding with an image; older ones can't. When ground_with_image
        # is set we still try grounded first, then fall back to image-only if
        # a given model rejects the combo.
        want_ground = (not has_image) or ground_with_image

        def make_body(model, grounded, use_think):
            b = {
                "contents": contents,
                "systemInstruction": {"parts": [{"text": persona}]},
                "generationConfig": {"maxOutputTokens": max_tokens,
                                     "temperature": 0.8},
            }
            if use_think and think is not None:
                # cap the model's internal reasoning to `think` tokens (0
                # disables thinking entirely for max speed). Thinking counts
                # as output tokens, so unbounded reasoning is slow + quota-
                # hungry. If a model 400s on the cap the caller retries it
                # uncapped.
                if model.startswith("gemini-2.5"):
                    b["generationConfig"]["thinkingConfig"] = {
                        "thinkingBudget": think}
                else:                     # 3.x and the -latest aliases
                    tc = {"thinkingBudget": think}
                    if think == 0:
                        tc["thinkingLevel"] = "none"
                    else:
                        tc["thinkingLevel"] = "low" if think <= 256 \
                            else "medium"
                    b["generationConfig"]["thinkingConfig"] = tc
            if grounded:
                # live Google Search. All current models (3.x, 2.5, and the
                # -latest aliases) use the new google_search tool; only the
                # long-gone 1.x used google_search_retrieval.
                if model.startswith("gemini-1"):
                    b["tools"] = [{"google_search_retrieval": {}}]
                else:
                    b["tools"] = [{"google_search": {}}]
            return json.dumps(b).encode()

        import time as _time
        last = "no reply"
        transient = False
        saw_429 = False
        # Try the whole model list up to 3 times — a 404/503 from Google is
        # often transient (endpoint hiccup, alias rolling over), so a short
        # wait and a fresh pass usually succeeds.
        for attempt in range(3):
            transient = False
            for m in models:
                url = ("https://generativelanguage.googleapis.com/v1beta/"
                       f"models/{m}:generateContent?key={key}")
                # grounded first (web + knowledge), then a raw fallback;
                # the thinking cap is dropped ONLY if a model 400s on it
                capping = think is not None      # 0 is a valid cap (disable)
                gseq = (True, False) if want_ground else (False,)
                variants = []
                for gr in gseq:
                    if capping:
                        variants.append((gr, True))
                    variants.append((gr, False))
                skip_no_think = capping
                for grounded, use_think in variants:
                    if skip_no_think and capping and not use_think:
                        continue          # only reached via a 400 below
                    body = make_body(m, grounded, use_think)
                    req = urllib.request.Request(
                        url, data=body,
                        headers={"Content-Type": "application/json"})
                    try:
                        with urllib.request.urlopen(req, timeout=35) as r:
                            self._gemini_model = m   # worked → prefer it next
                            return self._gemini_parse(
                                json.loads(r.read().decode()))
                    except urllib.error.HTTPError as e:
                        last = f"HTTP {e.code}"
                        if e.code in (401, 403):
                            raise RuntimeError(
                                "the API key was rejected") from None
                        if e.code == 400:
                            if use_think:
                                # this model rejects the thinking cap —
                                # allow its no-think variants
                                skip_no_think = False
                                continue
                            if grounded:
                                continue  # won't ground: retry raw
                        if e.code == 429:
                            saw_429 = True
                        if e.code in (404, 429, 500, 502, 503, 504):
                            transient = True   # worth another pass
                        break             # try the NEXT model
                    except Exception as ex:
                        last = str(ex)[:60]
                        transient = True
                        break
                # a cached preferred model that keeps failing: stop trusting it
                if getattr(self, "_gemini_model", None) == m:
                    self._gemini_model = None
            if not transient:
                break                     # a real error (not transient): stop
            if saw_429 and attempt >= 1:
                break                     # rate-limited: don't grind 3 passes
            _time.sleep(3.0 if saw_429 else 1.2 * (attempt + 1))
        raise RuntimeError(last)

    _SCREEN_HINTS = re.compile(
        r"\bthis\b|\bscreen\b|\bhere\b|on (my|the) (screen|display)|"
        r"\bshown?\b|\bshowing\b|what('?s| is) (this|on|that)|"
        r"is (this|that) (true|real|correct|right|fake)|"
        r"read (this|it|my)|look at|\bselected\b|\bhighlighted\b|"
        r"\babove\b|\bbelow\b|\bpage\b|translate (this|it)", re.I)

    def _wants_screen(self, q):
        return bool(self._SCREEN_HINTS.search(q))

    _GUIDE_HINTS = re.compile(
        r"how (do|can|would|to|d) i\b|how do you\b|how to\b|"
        r"\bwhere('?s| is| do| can| are)\b|\bwhere'?s\b|"
        r"show me (how|where)|walk me through|guide me\b|"
        r"help me (find|do|make|set|create|add|change|enable|turn|open|get)|"
        r"which (button|menu|option|setting|tab|icon)|"
        r"\bfind the\b|how would i\b|steps to\b|"
        r"i (want|need) to\b.*\?|can you (show|guide|walk)", re.I)

    def _is_guide_request(self, q):
        """True for genuine 'how do I / where is …' help questions — NOT for
        greetings, thanks, or plain chit-chat (those answer normally so guide
        mode doesn't screenshot the screen for a 'hi')."""
        q = q.strip()
        if len(q) < 5:                     # 'hi', 'hey', 'yo' → chat
            return False
        return bool(self._GUIDE_HINTS.search(q))

    def _grab_screen_b64(self):
        """Fast full-screen JPEG as base64, via Qt. None on failure."""
        try:
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            scr = (self.primary().screen()
                   or QGuiApplication.primaryScreen())
            pm = scr.grabWindow(0)
            # downscale big screens so the upload stays fast
            maxw = 1280
            if pm.width() > maxw:
                pm = pm.scaledToWidth(maxw, Qt.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            pm.save(buf, "JPEG", 72)
            buf.close()
            import base64
            return base64.b64encode(bytes(ba)).decode()
        except Exception:
            return None

    def ask_ai(self, question):
        import threading
        p = self.primary()
        # 🧭 guide mode: "how do I…" questions become guided tours; 'next'
        # advances, 'stop'/'done'/'cancel' ends. Greetings and plain chit-chat
        # fall through to normal chat instead of screenshotting the screen.
        if self.cfg["global"].get("guide_mode", False) \
                and self.cfg["global"].get("screen_vision", False):
            q = question.strip().lower().rstrip(".!?")
            if self.guide_active and q in ("stop", "cancel", "done",
                                           "end", "quit", "exit"):
                self._end_guide(walk_home=True)
                return
            if self.ai_busy and (self.guide_active
                                 or self._is_guide_request(question)):
                p.say("one sec, still working on this step… 🤔", 2)
                return
            if self.guide_active and q in ("next", "next step", "ok",
                                           "okay", "continue", "go on",
                                           "what's next", "whats next"):
                self._guide_step_run(self._guide_task, first=False)
                return
            if self._is_guide_request(question):
                self._guide_done = []
                self._guide_step_run(question, first=True)
                return
            # not a how-to — let it answer normally (no screenshot)
        if self.ai_busy:
            p.say("one sec, still thinking… 🤔", 2)
            return
        name = (p.ccfg.get("name") or "the cat").strip()
        persona = (
            f"You are {name}, a tiny pixel-art desktop pet cat living at "
            f"the bottom of the user's screen. Your name is {name} and you "
            "know it. Be helpful, warm and a little playful, like a clever "
            "cat. You CAN look things up on Google in real time, so you "
            "can answer questions about current events, live scores, "
            "weather and today's news — just do it, never say you can't "
            "reach the internet. Keep answers under 70 words unless the "
            "question clearly needs more. Plain text only: no markdown, "
            "no lists, no asterisks.")
        shot = None
        if self.cfg["global"].get("screen_vision", False) \
                and self._wants_screen(question):
            shot = self._grab_screen_b64()
        user_parts = [{"text": question}]
        if shot:
            user_parts.append({"inline_data": {
                "mime_type": "image/jpeg", "data": shot}})
            p.say("looking at your screen… 👀", 8)
        else:
            p.say("hmm… 🤔", 8)
        self._ai_hist.append({"role": "user", "parts": user_parts})
        hist = list(self._ai_hist[-10:])
        self.ai_busy = True

        def ui(fn):
            self._call_bridge.call.emit(fn)

        def work():
            try:
                ans = self._gemini_call(hist, persona).strip()
                if len(ans) > 600:
                    # trim at a sentence end near the limit, not mid-word
                    cut = ans[:600]
                    for stop in (". ", "! ", "? "):
                        i = cut.rfind(stop)
                        if i > 400:
                            cut = cut[:i + 1]
                            break
                    ans = cut.rstrip() + ("…" if len(ans) > len(cut) else "")

                def done():
                    self.ai_busy = False
                    self._ai_hist.append(
                        {"role": "model", "parts": [{"text": ans}]})
                    del self._ai_hist[:-12]
                    for h in self._ai_hist[:-1]:
                        h["parts"] = [pt for pt in h["parts"]
                                      if "inline_data" not in pt] or \
                            [{"text": ""}]
                    self.primary().say(ans,
                                       min(30.0, max(7.0, len(ans) / 9)))
                ui(done)
            except Exception as e:
                msg = str(e)[:60]

                def fail():
                    self.ai_busy = False
                    if self._ai_hist:
                        self._ai_hist.pop()
                    self.primary().say(
                        f"my brain won't connect… 🔑 ({msg})", 6)
                ui(fail)
        threading.Thread(target=work, daemon=True).start()

    def custom_stretch(self):
        m = pick_minutes("Stretch reminder", "Remind me to stretch every:",
                         max(1, self.cfg["global"].get("stretch_minutes",
                                                       50) or 50))
        if m is not None and m > 0:
            self.set_stretch(m)

    def custom_pomodoro(self, kind):
        m = pick_minutes("Pomodoro",
                         "Focus for:" if kind == "focus" else "Break for:",
                         25 if kind == "focus" else 5)
        if m is not None and m > 0:
            self.start_pomodoro(m, kind)

    def add_reminder(self):
        t = self.pick_reminder_time()
        if t is None:
            return
        msg, ok = QInputDialog.getText(None, "Set a reminder",
                                       "What should I say?")
        if not ok or not msg.strip():
            return
        self.cfg["global"].setdefault("reminders", []).append([t, msg.strip()])
        save_config(self.cfg)
        mins = max(1, int((t - time.time()) / 60))
        self.say_primary(f"Okay! I'll meow in ~{mins} min", 3)

    @staticmethod
    def pick_reminder_time():
        """Reminder time with real spinners: at a clock time, or in a
        duration from now. Returns a unix timestamp or None."""
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                       QRadioButton, QTimeEdit, QVBoxLayout)
        from PySide6.QtCore import QTime
        dlg = QDialog()
        dlg.setWindowTitle("Set a reminder")
        lay = QVBoxLayout(dlg)
        r_at = QRadioButton("At this time:")
        r_at.setChecked(True)
        lay.addWidget(r_at)
        at = QTimeEdit()
        at.setDisplayFormat("HH:mm")
        at.setTime(QTime.currentTime().addSecs(3600))
        lay.addWidget(at)
        r_in = QRadioButton("Or in (from now):")
        lay.addWidget(r_in)
        dur = QTimeEdit()
        dur.setDisplayFormat("HH:mm")
        dur.setTime(QTime(0, 30))
        lay.addWidget(dur)
        at.timeChanged.connect(lambda _t: r_at.setChecked(True))
        dur.timeChanged.connect(lambda _t: r_in.setChecked(True))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.Accepted:
            return None
        now = time.time()
        if r_in.isChecked():
            q = dur.time()
            secs = q.hour() * 3600 + q.minute() * 60
            return now + max(60, secs)
        q = at.time()
        lt = time.localtime(now)
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                              q.hour(), q.minute(), 0,
                              lt.tm_wday, lt.tm_yday, -1))
        if target <= now:
            target += 86400                  # that time tomorrow
        return target

    def clear_reminders(self):
        self.cfg["global"]["reminders"] = []
        save_config(self.cfg)
        self.say_primary("Reminders cleared")

    def set_pinned(self):
        cur = self.cfg["global"].get("pinned", "")
        msg, ok = QInputDialog.getText(None, "Pin a note",
                                       "Note to keep above my head:", text=cur)
        if ok:
            self.cfg["global"]["pinned"] = msg.strip()
            save_config(self.cfg)

    def set_name(self):
        cur = self.cfg["global"].get("name", "")
        msg, ok = QInputDialog.getText(None, "Tell the cat your name",
                                       "What should I call you?", text=cur)
        if ok:
            self.cfg["global"]["name"] = msg.strip()
            save_config(self.cfg)
            if msg.strip():
                self.say_primary(f"nyang, {msg.strip()}! 🐾", 3)

    def toggle_chase(self):
        g = self.cfg["global"]
        g["chase_enabled"] = not g["chase_enabled"]
        save_config(self.cfg)
        self.say_primary("I'll chase your cursor!" if g["chase_enabled"]
                         else "Fine, no chasing.", 2.5)


# ------------------------------------------------------------------- cat -----

class CatWindow(QWidget):
    def __init__(self, mgr, index):
        super().__init__()
        self.mgr = mgr
        self.index = index
        self.scale = int(self.ccfg.get("scale", 6))
        self.grow = 1.0
        self.mochi = 1.0

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowTitle(APP_NAME)
        self._frame_cache = {}
        self._resize_to_sprite()

        # animation / state
        self.state = IDLE
        self.flip = False
        self.blink_until = 0.0
        self.yawn_until = 0.0
        self.groom_until = 0.0
        self.next_groom = time.time() + random.uniform(25, 70)
        self.next_blink = time.time() + random.uniform(2, 6)
        self.sleep_at = time.time() + self.gcfg["sleep_seconds"]
        self.zzz, self.hearts, self.steam = [], [], []
        self.notes = []
        self.next_note = 0.0
        self.pet_accum = 0.0
        self.last_pet_heart = 0.0
        self._last_purr = 0.0
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.bubble_color = None
        self.jump_until = 0.0
        self.startle_cooldown = 0.0
        self.knead_hyst = False
        self.last_overheat_say = 0.0
        self.last_scroll_say = 0.0
        self.next_zzz = 0.0
        self.next_think_bubble = 0.0

        # dragging / wobble
        self.dragging = False
        self.duck_gunner = False        # easter-egg: holding a gun, angry
        self.drag_offset = QPoint()
        self.mochi = 1.0
        self._drag_target_offset = QPoint()
        self._drag_prev_cursor = QPoint()
        self._drag_room = 0
        self._wig_dir = 0
        self._wig_times = deque(maxlen=12)
        self._wigv_dir = 0
        self._wigv_times = deque(maxlen=12)
        self._hide_wig_cd = 0.0
        self.glide_target = None
        self.perch_hwnd = None
        self.perch_offx = 0
        self.perch_pending = None
        self.perch_until = 0.0
        self.perch_home = None
        self.next_perch_try = time.time() + random.uniform(30, 90)
        self.next_corner_at = time.time() + random.uniform(60, 180)
        self._corner_until = 0.0         # sitting in the corner until this time
        self._corner_going = False       # currently walking to the corner
        self._perch_miss = 0
        self._perch_hist = deque(maxlen=40)
        self._shake_quiet_until = 0.0
        self._shake_strikes = 0
        self._falling = False
        self._parachute = False          # ☂ drifting down after a lost perch
        self._cover_miss = 0
        self.perch_asleep = False
        self.wobble = 0.0
        self._last_drag_x = 0
        self._last_drag_dir = 0

        # smooth movement (float position)
        self._fx = self._fy = 0.0
        self.chase_cooldown = time.time() + random.uniform(0, 3)
        self._guard_return_at = 0.0
        self.prev_cursor = QCursor.pos()
        self.prev_tick_t = time.time()
        self.cursor_speed = 0.0

        # peek
        self.manual_peek = False
        self._peek_x = None
        self.peeking = False
        self._peek_was_fs = False
        self._saved_pos = None
        self.grow = 1.0
        self._pre_grow = None

        # position: saved, or staggered along the bottom-right
        pos = self.ccfg.get("pos")
        geo = QGuiApplication.primaryScreen().availableGeometry()
        if pos and len(pos) == 2:
            self.move(int(pos[0]), int(pos[1]))
        else:
            self.move(geo.right() - self.width() - 80 - index * 140,
                      geo.bottom() - self.height() - 60)
        self._sync_float()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        QTimer.singleShot(300 + index * 150, self._warm_cache)
        self.show()

    def _warm_cache(self):
        try:
            for name in sprites.FRAMES:
                self._frame_image(name, False)
            self._frame_image("type_a", False, hot=True)
            self._frame_image("type_b", False, hot=True)
        except Exception:
            pass

    # -------------------------------------------------------------- config --
    @property
    def ccfg(self):
        return self.mgr.cfg["cats"][self.index]

    @property
    def gcfg(self):
        return self.mgr.cfg["global"]

    # ------------------------------------------------------------ helpers ---
    def _sync_float(self):
        self._fx, self._fy = float(self.x()), float(self.y())

    def _resize_to_sprite(self):
        self._frame_cache = {}
        self.side = max(14, 3 * self.scale)
        self.setFixedSize(int(sprites.GRID_W * self.scale * self.grow)
                          + 2 * self.side,
                          int(sprites.GRID_H * self.scale * self.grow)
                          + TOP_MARGIN)

    def cat_rect(self):
        return QRect(self.side, TOP_MARGIN,
                     int(sprites.GRID_W * self.scale * self.grow),
                     int(sprites.GRID_H * self.scale * self.grow))

    def _set_grow(self, big):
        f = 1.8 if big else 1.0
        if abs(self.grow - f) < 0.01:
            return
        old_w, old_h = self.width(), self.height()
        old_pos = self.pos()
        self.grow = f
        self._resize_to_sprite()
        # keep the cat's bottom-center anchored
        dx = (self.width() - old_w) // 2
        dy = self.height() - old_h
        self.move(old_pos.x() - dx, old_pos.y() - dy)
        self._sync_float()

    def palette(self):
        if self.ccfg.get("custom_body"):
            pal = custom_palette(self.ccfg["custom_body"])
        else:
            pal = sprites.PALETTES.get(self.ccfg["palette"],
                                       sprites.PALETTES["orange tabby"])
        eye = self.ccfg.get("eye_color")
        if eye:
            pal = dict(pal)
            pal["P"] = eye
        return pal

    def say(self, text, secs=3.0, color=None):
        if len(text) > 60:
            self.bubble_text = ""
            self.bubble_until = 0
            self.mgr.show_big_bubble(self, text, secs, color)
            self.update()
            return
        self.bubble_text = text
        self.bubble_until = time.time() + secs
        self.bubble_color = color
        self.update()

    def nameof(self):
        return self.gcfg.get("name", "")

    # -------------------------------------------------------------- menu ----
    def build_menu(self):
        menu = QMenu(self)
        mgr = self.mgr

        cust = menu.addMenu("Customization 🎨")
        fur = cust.addMenu("Fur color")
        for name in sprites.PALETTES:
            if name in ("lilly", "jj", "mimi"):
                continue                     # they live under Themes
            act = QAction(name.title(), menu)
            act.setCheckable(True)
            act.setChecked(self.ccfg["palette"] == name
                           and not self.ccfg["custom_body"])
            act.triggered.connect(lambda _=False, n=name: self.set_palette(n))
            fur.addAction(act)
        pick = QAction("Custom color…", menu)
        pick.triggered.connect(self.pick_color)
        fur.addAction(pick)

        pat = cust.addMenu("Pattern")
        for name in sprites.PATTERNS:
            act = QAction(name.title(), menu)
            act.setCheckable(True)
            act.setChecked(self.ccfg["pattern"] == name)
            act.triggered.connect(lambda _=False, n=name: self.set_pattern(n))
            pat.addAction(act)

        eye = cust.addMenu("Eye color 👁")
        for label, hexv in (("Palette default", None),
                            ("Midnight", "#2c3138"),
                            ("Green", "#3c5240"),
                            ("Hazel", "#6a5a2e"),
                            ("Blue", "#3a5a7c"),
                            ("Amber", "#8a5a20"),
                            ("Pink", "#b06a7c")):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.ccfg.get("eye_color") == hexv)
            act.triggered.connect(
                lambda _=False, h=hexv: self.set_eye_color(h))
            eye.addAction(act)
        ceye = QAction("Custom…", menu)
        ceye.triggered.connect(self.pick_eye_color)
        eye.addAction(ceye)

        size = cust.addMenu("Size")
        for s in (2, 3, 4, 5, 6, 8, 10):
            act = QAction(f"{s}×", menu)
            act.setCheckable(True)
            act.setChecked(self.scale == s)
            act.triggered.connect(lambda _=False, v=s: self.set_scale(v))
            size.addAction(act)

        cats = menu.addMenu("Cats")
        add = QAction("Add a cat 🐈", menu)
        add.triggered.connect(mgr.add_cat)
        cats.addAction(add)
        rem = QAction("Remove this cat", menu)
        rem.triggered.connect(lambda: mgr.remove_cat(self))
        cats.addAction(rem)
        thm = cats.addMenu("Themes ✨")
        lil = QAction("Lilly", menu)
        lil.setCheckable(True)
        lil.setChecked(self.ccfg["palette"] == "lilly")
        lil.triggered.connect(lambda _=False: self.set_palette("lilly"))
        thm.addAction(lil)
        jjt = QAction("JJ", menu)
        jjt.setCheckable(True)
        jjt.setChecked(self.ccfg["palette"] == "jj")
        jjt.triggered.connect(lambda _=False: self.set_palette("jj"))
        thm.addAction(jjt)
        mmt = QAction("Mimi", menu)
        mmt.setCheckable(True)
        mmt.setChecked(self.ccfg["palette"] == "mimi")
        mmt.triggered.connect(lambda _=False: self.set_palette("mimi"))
        thm.addAction(mmt)
        more = QAction("more coming…", menu)
        more.setEnabled(False)
        thm.addAction(more)


        remm = menu.addMenu("Reminders ⏰")
        pomo = remm.addMenu("Pomodoro")
        for label, mins, kind in (("Focus 25 min", 25, "focus"),
                                  ("Focus 50 min", 50, "focus"),
                                  ("Break 5 min", 5, "break")):
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, m=mins, k=kind:
                                  mgr.start_pomodoro(m, k))
            pomo.addAction(act)
        pcus = QAction("Custom focus ⏱…", menu)
        pcus.triggered.connect(lambda _=False: mgr.custom_pomodoro("focus"))
        pomo.addAction(pcus)
        bcus = QAction("Custom break ⏱…", menu)
        bcus.triggered.connect(lambda _=False: mgr.custom_pomodoro("break"))
        pomo.addAction(bcus)
        for label, f, b in (("Loop 25 / 5", 25, 5), ("Loop 50 / 10", 50, 10)):
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, ff=f, bb=b:
                                  mgr.start_pomodoro(ff, "focus", loop=(ff, bb)))
            pomo.addAction(act)
        stop = QAction("Stop timer", menu)
        stop.triggered.connect(mgr.stop_pomodoro)
        pomo.addAction(stop)

        stretch = remm.addMenu("Stretch reminder")
        for label, mins in (("Every 30 min", 30), ("Every 50 min", 50),
                            ("Every 90 min", 90), ("Off", 0)):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.gcfg["stretch_minutes"] == mins)
            act.triggered.connect(lambda _=False, m=mins: mgr.set_stretch(m))
            stretch.addAction(act)
        scus = QAction("Custom interval ⏱…", menu)
        scus.triggered.connect(mgr.custom_stretch)
        stretch.addAction(scus)

        mini = menu.addMenu("Minigames 🎮")
        dh = QAction("Duck Hunt 🦆", menu)
        dh.triggered.connect(lambda: mgr.start_minigame("duckhunt"))
        mini.addAction(dh)
        mini.addSeparator()
        soon = QAction("more coming soon…", menu)
        soon.setEnabled(False)
        mini.addAction(soon)

        beh = menu.addMenu("Behavior")
        # --- checkable toggles first ---
        chase = QAction("Chase the cursor", menu)
        chase.setCheckable(True)
        chase.setChecked(self.gcfg["chase_enabled"])
        chase.triggered.connect(mgr.toggle_chase)
        beh.addAction(chase)
        laser = QAction("Hunt only laser wiggles (side-to-side)", menu)
        laser.setCheckable(True)
        laser.setChecked(self.gcfg.get("laser_only", True))
        laser.triggered.connect(mgr.toggle_laser)
        beh.addAction(laser)
        wigh = QAction("Hide when I wiggle at the bottom edge", menu)
        wigh.setCheckable(True)
        wigh.setChecked(self.gcfg.get("wiggle_hide", True))
        wigh.triggered.connect(mgr.toggle_wiggle_hide)
        beh.addAction(wigh)
        dnc = QAction("Headphones when sound plays 🎧", menu)
        dnc.setCheckable(True)
        dnc.setChecked(self.gcfg.get("dance_music", True))
        dnc.triggered.connect(mgr.toggle_dance_music)
        beh.addAction(dnc)
        dps = QAction("Dance + music notes 💃", menu)
        dps.setCheckable(True)
        dps.setChecked(self.gcfg.get("dance_on_sound", False))
        dps.triggered.connect(mgr.toggle_dance_on_sound)
        beh.addAction(dps)
        snd = QAction("Sounds 🔊", menu)
        snd.setCheckable(True)
        snd.setChecked(self.gcfg.get("sounds", True))
        snd.triggered.connect(mgr.toggle_sounds)
        beh.addAction(snd)
        # volume slider (0–100%) as an embedded widget in the menu
        from PySide6.QtWidgets import QWidgetAction, QSlider, QWidget, QHBoxLayout, QLabel
        vol_wrap = QWidget()
        vlay = QHBoxLayout(vol_wrap)
        vlay.setContentsMargins(22, 2, 12, 4)
        vlay.setSpacing(8)
        vlab = QLabel("🔈")
        vsl = QSlider(Qt.Horizontal)
        vsl.setMinimum(0)
        vsl.setMaximum(100)
        vsl.setValue(int(self.gcfg.get("sound_volume", 0.6) * 100))
        vsl.setFixedWidth(120)
        vsl.valueChanged.connect(lambda v: mgr.set_sound_volume(v / 100.0))
        vlay.addWidget(vlab)
        vlay.addWidget(vsl)
        vol_act = QWidgetAction(menu)
        vol_act.setDefaultWidget(vol_wrap)
        beh.addAction(vol_act)
        auto = QAction("Auto-hide during fullscreen video", menu)
        auto.setCheckable(True)
        auto.setChecked(self.gcfg["auto_peek"])
        auto.triggered.connect(mgr.toggle_auto_peek)
        beh.addAction(auto)
        # --- sub-menus at the bottom ---
        beh.addSeparator()
        sens = beh.addMenu("Wiggle sensitivity")
        for label, key in (("High (easy to trigger)", "high"),
                           ("Medium", "medium"),
                           ("Low (deliberate wiggles only)", "low")):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.gcfg.get("wiggle_sens", "medium") == key)
            act.triggered.connect(lambda _=False, k=key:
                                  mgr.set_wiggle_sens(k))
            sens.addAction(act)
        perchm = beh.addMenu("Sit on top of windows 🪟")
        cur_freq = self.gcfg.get("perch_freq", "instant")
        if not self.gcfg.get("window_perch", True):
            cur_freq = "off"
        for key, label in (("off", "Off"),
                           ("rarely", "Rarely"),
                           ("sometimes", "Sometimes"),
                           ("often", "Often"),
                           ("very", "Very often"),
                           ("instant", "Instant")):
            a = QAction(label, menu)
            a.setCheckable(True)
            a.setChecked(cur_freq == key)
            a.triggered.connect(
                lambda _=False, k=key: mgr.set_perch_freq(k))
            perchm.addAction(a)
        perchm.addSeparator()
        napm = perchm.addMenu("While perched 👀")
        cur_nap = self.gcfg.get("perch_nap_chance", 0.3)
        for chance, label in ((0.0, "Always watch"),
                              (0.3, "Mostly watch"),
                              (0.6, "Balanced"),
                              (0.9, "Mostly nap")):
            na = QAction(label, menu)
            na.setCheckable(True)
            na.setChecked(abs(cur_nap - chance) < 0.01)
            na.triggered.connect(
                lambda _=False, ch=chance: mgr.set_perch_nap(ch))
            napm.addAction(na)
        cfm = beh.addMenu("Stand in a corner 🧍")
        cur_cf = self.gcfg.get("corner_freq", "sometimes")
        corner_on = self.gcfg.get("corner_stand", False)
        for key, label in (("never", "Never"),
                           ("rarely", "Rarely"),
                           ("sometimes", "Sometimes"),
                           ("often", "Often"),
                           ("very", "Very often")):
            a = QAction(label, menu)
            a.setCheckable(True)
            if key == "never":
                a.setChecked(not corner_on)
            else:
                a.setChecked(corner_on and cur_cf == key)
            a.triggered.connect(
                lambda _=False, k=key: mgr.set_corner_freq(k))
            cfm.addAction(a)
        agent = menu.addMenu("AI 🤖")
        pnm = (mgr.primary().ccfg.get("name") or "").strip()
        ask = QAction(f"Ask {pnm or 'me'} 💬 (Ctrl+Space)", menu)
        ask.triggered.connect(lambda _=False: mgr.open_ask_box())
        agent.addAction(ask)
        gkey = QAction("Set Gemini API key 🔑…", menu)
        gkey.triggered.connect(mgr.set_gemini_key)
        agent.addAction(gkey)
        sv = QAction("Let me check your screen 👀", menu)
        sv.setCheckable(True)
        sv.setChecked(self.gcfg.get("screen_vision", False))
        sv.triggered.connect(mgr.toggle_screen_vision)
        agent.addAction(sv)
        gm = QAction("Guide me on screen 🧭 (beta)", menu)
        gm.setCheckable(True)
        gm.setChecked(self.gcfg.get("guide_mode", False))
        gm.triggered.connect(mgr.toggle_guide_mode)
        agent.addAction(gm)
        gqm = agent.addMenu("Guide speed ⚡")
        cur_gq = self.gcfg.get("guide_quality", "fast")
        for key, label in (("fast", "Fast — snappy, less precise"),
                           ("balanced", "Balanced"),
                           ("accurate",
                            "Accurate — slower, tighter, checks the web")):
            a = QAction(label, menu)
            a.setCheckable(True)
            a.setChecked(cur_gq == key)
            a.triggered.connect(
                lambda _=False, k=key: mgr.set_guide_quality(k))
            gqm.addAction(a)
        nmai = QAction("Name this cat ✏️", menu)
        nmai.triggered.connect(self.rename_cat)
        agent.addAction(nmai)
        agent.addSeparator()
        info = QAction("How to hook up (see README)", menu)
        info.triggered.connect(self.show_agent_help)
        agent.addAction(info)

        msgs = remm.addMenu("Messages")
        rem = QAction("Set a reminder…", menu)
        rem.triggered.connect(mgr.add_reminder)
        msgs.addAction(rem)
        crem = QAction("Clear reminders", menu)
        crem.triggered.connect(mgr.clear_reminders)
        msgs.addAction(crem)
        pin = QAction("Pin a note above my head…", menu)
        pin.triggered.connect(mgr.set_pinned)
        msgs.addAction(pin)
        nm = QAction("Tell the cat your name…", menu)
        nm.triggered.connect(mgr.set_name)
        msgs.addAction(nm)

        tst = menu.addMenu("Test animations")
        for label, kind in (("Blink", "blink"),
                            ("Typing (kneading)", "knead"),
                            ("Overheat 🔥", "overheat"),
                            ("Paper scroll play 📜", "paper"),
                            ("Grooming 🐾", "groom"),
                            ("Yawn + sleep 💤", "sleep"),
                            ("Running", "run"),
                            ("Stretch", "stretch"),
                            ("Dangle (hanging)", "dangle"),
                            ("Peek pose", "peek"),
                            ("Dance 🎧", "dance")):
            act = QAction(label, menu)
            act.triggered.connect(
                lambda _=False, k=kind: mgr.start_anim_test(k))
            tst.addAction(act)
        wtest = QAction("Walk onto a window 🪟", menu)
        wtest.triggered.connect(
            lambda _=False: mgr.primary().try_perch(announce=True))
        tst.addAction(wtest)
        para = QAction("Parachute drop ☂️", menu)
        para.triggered.connect(lambda _=False: mgr.test_parachute())
        tst.addAction(para)

        hidden = self.gcfg.get("hide_mode", False)
        hid = QAction("Come back out 🫣" if hidden
                      else "Hide at the bottom 🫣", menu)
        hid.setCheckable(True)
        hid.setChecked(hidden)
        hid.triggered.connect(mgr.toggle_hide_mode)
        menu.addAction(hid)
        slp = QAction("Deep sleep 💤", menu)
        slp.setCheckable(True)
        slp.setChecked(self.gcfg.get("force_sleep", False))
        slp.triggered.connect(mgr.toggle_force_sleep)
        menu.addAction(slp)
        gmenu = menu.addMenu("Guard mode 🔦")
        guard = QAction("Guard mode 🔦", gmenu)
        guard.setCheckable(True)
        guard.setChecked(self.gcfg.get("guard_mode", False))
        guard.triggered.connect(mgr.toggle_guard_mode)
        gmenu.addAction(guard)
        gmenu.addSeparator()
        gtimer = gmenu.addMenu("Auto-off ⏱")
        cur_min = int(self.gcfg.get("guard_timer_min", 0) or 0)
        presets = [("No timer (manual)", 0), ("5 minutes", 5),
                   ("15 minutes", 15), ("30 minutes", 30),
                   ("1 hour", 60), ("2 hours", 120)]
        for label, m in presets:
            a = QAction(label, gtimer)
            a.setCheckable(True)
            a.setChecked(cur_min == m)
            a.triggered.connect(lambda _=False, mm=m: mgr.set_guard_timer(mm))
            gtimer.addAction(a)
        custom = QAction(
            f"Custom…{f'  ({cur_min} min)' if cur_min and cur_min not in [p[1] for p in presets] else ''}",
            gtimer)
        custom.triggered.connect(lambda _=False: mgr.pick_guard_timer())
        gtimer.addAction(custom)
        menu.addSeparator()
        donate = QAction("Support the cat 💛 (Ko-fi)", menu)
        donate.triggered.connect(lambda _=False: mgr.open_donate())
        menu.addAction(donate)

        upds = menu.addMenu("Updates ⤓")
        if IS_STORE_BUILD:
            managed = QAction("Updates managed by Microsoft Store 🛍️", menu)
            managed.setEnabled(False)
            upds.addAction(managed)
        else:
            unow = QAction("Check for updates now  (Ctrl+Shift+Alt+P)", menu)
            unow.triggered.connect(
                lambda _=False: mgr.check_updates(manual=True))
            upds.addAction(unow)
            aup = QAction("Install updates automatically", menu)
            aup.setCheckable(True)
            aup.setChecked(self.gcfg.get("auto_update", True))
            aup.triggered.connect(mgr.toggle_auto_update)
            upds.addAction(aup)
        rst = QAction("Restart the cat 🔄  (Ctrl+Shift+Alt+R)", menu)
        rst.triggered.connect(mgr._restart)
        upds.addAction(rst)
        upds.addSeparator()
        chan = " · Store" if IS_STORE_BUILD else ""
        uinf = QAction(
            f"Installed: v{APP_VERSION} · build {APP_BUILD}{chan}", menu)
        uinf.setEnabled(False)
        upds.addAction(uinf)

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_act)
        return menu

    @staticmethod
    def _write_agent(text):
        try:
            with open(AGENT_FILE, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    # --------------------------------------------------------- menu actions -
    def set_palette(self, name):
        self.ccfg["palette"] = name
        self.ccfg["custom_body"] = None
        if name in ("lilly", "jj", "mimi"):
            self.ccfg["pattern"] = name      # theme cats bring their pattern
        save_config(self.mgr.cfg)
        self._frame_cache = {}
        if self.index == 0:
            self.mgr._make_tray()
        self.say({"lilly": "Lilly! 🧡", "jj": "JJ! 💚",
                  "mimi": "Mimi! 💙"}.get(name, f"New fur: {name}!"))

    def set_pattern(self, name):
        self.ccfg["pattern"] = name
        save_config(self.mgr.cfg)
        self._frame_cache = {}
        if self.index == 0:
            self.mgr._make_tray()
        self.say(f"{name.title()} pattern!")

    def set_eye_color(self, hexv):
        self.ccfg["eye_color"] = hexv
        save_config(self.mgr.cfg)
        self._frame_cache = {}
        if self.index == 0:
            self.mgr._make_tray()
        self.say("new eyes! 👁" if hexv else "eyes back to normal")
        self.update()

    def pick_eye_color(self):
        col = QColorDialog.getColor(QColor(self.palette()["P"]), None,
                                    "Eye color")
        if col.isValid():
            self.set_eye_color(col.name())

    def pick_color(self):
        col = QColorDialog.getColor(QColor(self.palette()["B"]), None,
                                    "Pick a fur color")
        if col.isValid():
            self.ccfg["custom_body"] = col.name()
            save_config(self.mgr.cfg)
            self._frame_cache = {}
            if self.index == 0:
                self.mgr._make_tray()
            self.say("Fancy new fur!")

    def set_scale(self, s):
        self.scale = s
        self.ccfg["scale"] = s
        save_config(self.mgr.cfg)
        self._resize_to_sprite()
        self.update()

    def rename_cat(self):
        cur = self.ccfg.get("name", "")
        name, ok = QInputDialog.getText(
            None, "Name this cat", "This cat's name:", text=cur)
        if not ok:
            return
        name = name.strip()[:24]
        self.ccfg["name"] = name
        save_config(self.mgr.cfg)
        if self.index == 0:
            self.mgr._make_tray()
        self.say(f"I'm {name}! 🐾" if name else "no name, just cat 🐾", 3)

    def toggle_manual_peek(self):
        self.manual_peek = not self.manual_peek

    def show_about(self):
        QMessageBox.information(
            None, APP_NAME,
            f"Version {APP_VERSION}\n"
            "Pixel cats for your desktop.\n\n"
            "• Eyes follow your cursor; they chase fast moves\n"
            "• Kneading when you type; overheat when you type FAST\n"
            "• Paper play when you scroll; naps when idle\n"
            "• Pet their heads! Drag = mochi dangle; shake = wobble\n"
            "• Peek from the screen edge during fullscreen video\n"
            "• Stretch reminders, Pomodoro, AI-agent reactions\n"
            "• Add more cats from the right-click menu!")

    def show_agent_help(self):
        QMessageBox.information(
            None, "AI agent reactions",
            "The cats watch this file:\n\n  " + AGENT_FILE + "\n\n"
            'Write "working|Label" while an agent runs and "done|Label" when '
            "it finishes.\n\nEasiest ways:\n"
            "  • python sonder_agent.py run \"Codex\" -- codex <args>\n"
            "  • Claude Code hooks (snippet in README.md)\n"
            "  • Test it right now from this menu!")

    # ------------------------------------------------------------ main tick -
    def tick(self):
        now = time.time()
        bw = getattr(self.mgr, "_bubble_win", None)
        if bw is not None and bw.cat is self:
            bw.tick()
        ab = getattr(self.mgr, "_ask_box", None)
        if ab is not None and ab.cat is self:
            ab.follow_tick()
        dt = min(0.2, max(1e-3, now - self.prev_tick_t))
        self.prev_tick_t = now
        mgr = self.mgr
        inputs = mgr.inputs

        # --- cursor speed (global), wake from sleep ---
        cur = QCursor.pos()
        dist_moved = math.hypot(cur.x() - self.prev_cursor.x(),
                                cur.y() - self.prev_cursor.y())
        self.cursor_speed = 0.7 * self.cursor_speed + 0.3 * (dist_moved / dt)
        flips_req, amp = WIGGLE_SENS.get(
            self.gcfg.get("wiggle_sens", "medium"), (4, 20))
        dxc = cur.x() - self.prev_cursor.x()
        if abs(dxc) > amp:
            dirc = 1 if dxc > 0 else -1
            if dirc != self._wig_dir and self._wig_dir != 0:
                self._wig_times.append(now)
            self._wig_dir = dirc
        while self._wig_times and now - self._wig_times[0] > 1.5:
            self._wig_times.popleft()
        dyc = cur.y() - self.prev_cursor.y()
        if abs(dyc) > amp:
            dirv = 1 if dyc > 0 else -1
            if dirv != self._wigv_dir and self._wigv_dir != 0:
                # count a flip ONLY if it happens down in the bottom band —
                # otherwise ordinary up-down mouse work anywhere on screen
                # followed by a move toward the taskbar kept hiding the cat
                scr_v = QGuiApplication.screenAt(cur) \
                    or QGuiApplication.primaryScreen()
                if cur.y() > scr_v.geometry().bottom() - 90:
                    self._wigv_times.append(now)
            self._wigv_dir = dirv
        while self._wigv_times and now - self._wigv_times[0] > 1.5:
            self._wigv_times.popleft()
        # wiggle up-down near the bottom edge -> the cat goes to hide
        if self.gcfg.get("wiggle_hide", True) and not self.dragging \
                and not self.peeking and now > self._hide_wig_cd \
                and not self.gcfg.get("guard_mode", False) \
                and not mgr.guide_active:
            scr_c = QGuiApplication.screenAt(cur) \
                or QGuiApplication.primaryScreen()
            if (cur.y() > scr_c.geometry().bottom() - 90
                    and len(self._wigv_times) >= flips_req):
                self._wigv_times.clear()
                self._hide_wig_cd = now + 4.0
                self._peek_x = cur.x()          # hide where the wiggle was
                self.manual_peek = True

        if dist_moved > 2 or inputs.typing(1.2):
            self.sleep_at = now + self.gcfg["sleep_seconds"]
            if self.state == SLEEP and not self.gcfg.get("force_sleep") \
                    and not self.perch_asleep:
                self.state = IDLE
                self.say("mrrp?", 1.5)
        self.prev_cursor = cur

        # --- particles ---
        for p in self.hearts + self.zzz + self.steam:
            p["y"] -= p["vy"] * dt * 25
            p["x"] += math.sin(now * 3 + p["seed"]) * 0.5
            p["life"] -= dt
        self.hearts = [p for p in self.hearts if p["life"] > 0]
        self.zzz = [p for p in self.zzz if p["life"] > 0]
        self.steam = [p for p in self.steam if p["life"] > 0]
        for p in self.notes:
            p["y"] -= p["vy"]
            p["x"] += math.sin(time.time() * 3 + p["seed"]) * 0.6
            p["life"] -= 0.016
        self.notes = [p for p in self.notes if p["life"] > 0]

        # --- drag: follow the cursor from the tick too, so the cat never
        #     falls behind even when mouse events are missed ---
        if self.dragging:
            # ease the grab point up to the paws so the cursor "holds" them
            d = self._drag_target_offset - self.drag_offset
            if d.manhattanLength() > 2:
                self.drag_offset += QPoint(int(d.x() * 0.35),
                                           int(d.y() * 0.35))
            curp = QCursor.pos()
            target = curp - self.drag_offset
            if target != self.pos():
                self.move(target)
                self._sync_float()
            # mochi: hangs slightly stretched, pulls longer with speed
            speed = (curp - self._drag_prev_cursor).manhattanLength()
            self._drag_prev_cursor = curp
            want = min(1.40, 1.06 + speed / 180.0)
            self.mochi += (want - self.mochi) * 0.30
            self.state = DRAG
            if self.perch_hwnd is not None or self.perch_pending is not None:
                self._end_perch(go_home=False)
            self.wobble *= 0.92
            self.update()
            return

        if self.glide_target is not None:
            self._glide_step(dt)
        self._perch_tick(now)

        # manual animation test (from the Test menu) overrides everything
        t = mgr.anim_test
        if t is not None:
            if now < t["until"]:
                kind = t["kind"]
                self.state = {"blink": IDLE, "groom": IDLE,
                              "dance": DANCE,
                              "knead": KNEAD, "overheat": OVERHEAT,
                              "sleep": SLEEP, "run": CHASE,
                              "stretch": STRETCH, "dangle": DRAG,
                              "peek": PEEK}.get(kind, IDLE)
                if kind == "blink":
                    self.blink_until = now + 0.4
                elif kind == "groom":
                    self.groom_until = t["until"]
                elif kind == "sleep":
                    if now > self.next_zzz and len(self.zzz) < 3:
                        self.next_zzz = now + 1.4
                        r = self.cat_rect()
                        self.zzz.append({"x": r.center().x() + 20,
                                         "y": r.top() + 10, "vy": 0.7,
                                         "life": 2.5,
                                         "seed": random.random() * 6})
                elif kind == "dance":
                    if now > self.next_note and len(self.notes) < 4:
                        self.next_note = now + random.uniform(0.5, 1.1)
                        r = self.cat_rect()
                        self.notes.append({
                            "x": r.center().x() + random.randint(-14, 22),
                            "y": r.top() + 4, "vy": 0.9, "life": 2.2,
                            "seed": random.random() * 6})
                elif kind == "overheat" and random.random() < 0.25:
                    r = self.cat_rect()
                    self.steam.append({
                        "x": r.left() + random.randint(20, r.width() - 20),
                        "y": r.top() + 6, "vy": 1.3, "life": 1.2,
                        "seed": random.random() * 6})
                self.wobble *= 0.92
                self.mochi += (1.0 - self.mochi) * 0.35
                self.update()
                return
            mgr.anim_test = None
            self.state = IDLE
            self.groom_until = 0
            if self.grow > 1.0:
                self._set_grow(False)

        # deep sleep: stays asleep no matter what, until toggled off —
        # but guard duty overrides it (a sleeping sentry is no sentry)
        if self.gcfg.get("force_sleep") \
                and not self.mgr.cfg["global"].get("guard_mode", False):
            if self.peeking:
                self._unpeek(cancel=False)
            if self.state != SLEEP:
                self.yawn_until = now + 0.9
            self.state = SLEEP
            if now > self.next_zzz and len(self.zzz) < 3:
                self.next_zzz = now + 1.4
                r = self.cat_rect()
                self.zzz.append({"x": r.center().x() + 20, "y": r.top() + 10,
                                 "vy": 0.7, "life": 2.5,
                                 "seed": random.random() * 6})
            self.wobble *= 0.92
            self.mochi += (1.0 - self.mochi) * 0.35
            self.update()
            return

        # committed window nap: only shake/close/maximize (or grabbing
        # the cat) can end it
        if self.perch_asleep and self.perch_hwnd is not None:
            if self.state != SLEEP:
                self.yawn_until = max(self.yawn_until, now + 0.9)
            self.state = SLEEP
            if now > self.next_zzz and len(self.zzz) < 3:
                self.next_zzz = now + 1.4
                r = self.cat_rect()
                self.zzz.append({"x": r.center().x() + 20, "y": r.top() + 10,
                                 "vy": 0.7, "life": 2.5,
                                 "seed": random.random() * 6})
            self.wobble *= 0.92
            self.mochi += (1.0 - self.mochi) * 0.35
            self.update()
            return

        want_peek = (self.manual_peek or mgr.fullscreen_active
                     or self.gcfg.get("hide_mode", False))
        if self.mgr.cfg["global"].get("guard_mode", False):
            want_peek = False              # on duty: no hiding/peeking
            self.sleep_at = now + self.gcfg["sleep_seconds"]  # never doze off
        # snappy to start (0.25s); once typing, hold the pose ~1s past the
        # last key. And while a key is physically HELD, stay typing the whole
        # time so the paw stays pressed on it until you let go.
        typing_now = (inputs.key_held()
                      or inputs.typing(1.0 if self.knead_hyst else 0.25))
        self.knead_hyst = typing_now
        overheat = (inputs.keys_per_sec() > 5.5 and typing_now)

        # --- startle ---
        d_cur = self._dist_to_cursor(cur)
        if (self.state == IDLE and d_cur < 130 and self.cursor_speed > 3200
                and now > self.startle_cooldown
                and not mgr.guide_active):
            self.startle_cooldown = now + 6
            self.jump_until = now + 0.7
            self.wobble = 10
            self.say("!!!", 1.2)

        # chase trigger (works from idle, thinking, AND while hidden)
        wiggling = len(self._wig_times) >= flips_req
        if self.gcfg.get("laser_only", True):
            chase_trigger = wiggling and d_cur > 120
        else:
            chase_trigger = self.cursor_speed > 900 and d_cur > 220
        start_chase = (self.gcfg["chase_enabled"] and chase_trigger
                       and now > self.chase_cooldown
                       and self.state in (IDLE, PEEK, THINK))

        # --- state selection (priority order) ---
        if getattr(self, "duck_gunner", False):
            # 🦆 DUCK HUNT LOCK: cat stays put in its corner, gun ready — no
            # wandering, sleeping, grooming, perching, chasing or hiding.
            self.groom_until = 0.0
            self.sleep_at = now + self.gcfg["sleep_seconds"]
            self.next_perch_try = now + 999
            self.next_corner_at = now + 999
            self._corner_until = 0.0
            if self.state not in (IDLE,) and self.glide_target is None:
                self.state = IDLE
        elif mgr.guide_active:
            # 🧭 GUIDED TOUR LOCK: nothing interrupts the tour — no stretch,
            # overheat, scroll-play, typing, chase, hide, sleep, groom,
            # perch or corner-standing. The cat only glides to the spot it's
            # pointing at (its _glide_to is driven by the guide step) and
            # otherwise stands idle until the task finishes.
            self.groom_until = 0.0
            self.sleep_at = now + self.gcfg["sleep_seconds"]
            self.next_perch_try = now + 999
            self.next_corner_at = now + 999
            self._corner_until = 0.0
            if self.state not in (IDLE,):
                self.state = IDLE
        elif now < mgr.stretch_until:
            self.state = STRETCH
            pass
        elif overheat and not want_peek:
            if self.state != OVERHEAT and now - self.last_overheat_say > 8:
                self.last_overheat_say = now
                self.say(random.choice(["so much typing!!", "*tak tak tak*",
                                        "slow down!!"]), 2)
            self.state = OVERHEAT
            if random.random() < 0.25:
                r = self.cat_rect()
                self.steam.append({
                    "x": r.left() + random.randint(20, r.width() - 20),
                    "y": r.top() + 6, "vy": 1.3, "life": 1.2,
                    "seed": random.random() * 6})
        elif (inputs.scrolling() and not want_peek
              and inputs.last_scroll >= inputs.last_key
              and not self.mgr.cfg["global"].get("guard_mode", False)):
            if self.state != SCROLLPLAY and now - self.last_scroll_say > 10:
                self.last_scroll_say = now
                self.say("paper!!", 1.2)
            self.state = SCROLLPLAY
        elif typing_now and not want_peek \
                and not self.mgr.cfg["global"].get("guard_mode", False):
            self.state = KNEAD
        elif inputs.scrolling() and not want_peek \
                and not self.mgr.cfg["global"].get("guard_mode", False):
            if self.state != SCROLLPLAY and now - self.last_scroll_say > 10:
                self.last_scroll_say = now
                self.say("paper!!", 1.2)
            self.state = SCROLLPLAY
        elif self.state == CHASE:
            self._chase_step(cur, now, dt)
        elif start_chase and (not want_peek or
                              (self.manual_peek
                               and not self.gcfg.get("hide_mode", False)
                               and not mgr.fullscreen_active)):
            if self.peeking:
                # hidden by a wiggle — a laser wiggle lures it back out!
                self.manual_peek = False
                self.peeking = False
                self._peek_was_fs = False
                self._saved_pos = None       # no going back; the chase is on
            if self.perch_hwnd is not None:
                self._end_perch(go_home=False)
            self.state = CHASE
            self._wig_times.clear()
            self.glide_target = None
            self._sync_float()
            self.say("!", 1)
        elif want_peek:
            if not self.peeking:
                self._peek()
            self.state = PEEK
            if (mgr.fullscreen_active and not self.manual_peek
                    and not self.gcfg.get("hide_mode", False)):
                self._peek_was_fs = True
        elif mgr.ai_busy:
            self.state = THINK
        elif mgr.agent_working:
            self.state = THINK
            if self.index == 0 and now > self.next_think_bubble:
                self.next_think_bubble = now + random.uniform(6, 12)
                self.say(random.choice(["…", "thinking along…", "hmmm",
                                        f"go {mgr.agent_label}!"]), 1.8)
        elif mgr.music_on and self.gcfg.get("dance_music", True):
            self.state = DANCE
            if now > self.next_note and len(self.notes) < 4:
                self.next_note = now + random.uniform(0.5, 1.1)
                r = self.cat_rect()
                self.notes.append({
                    "x": r.center().x() + random.randint(-14, 22),
                    "y": r.top() + 4, "vy": 0.9, "life": 2.2,
                    "seed": random.random() * 6})
        elif now > self.sleep_at \
                and not self.mgr.cfg["global"].get("guard_mode", False):
            if self.state != SLEEP:
                self.yawn_until = now + 0.9
            self.state = SLEEP
            if now > self.next_zzz and len(self.zzz) < 3:
                self.next_zzz = now + 1.4
                r = self.cat_rect()
                self.zzz.append({"x": r.center().x() + 20, "y": r.top() + 10,
                                 "vy": 0.7, "life": 2.5,
                                 "seed": random.random() * 6})
        else:
            self.state = IDLE
            if now > self.next_blink:
                self.blink_until = now + 0.18
                self.next_blink = now + random.uniform(2.5, 7)
            guarding = self.gcfg.get("guard_mode", False)
            if guarding and self._guard_return_at \
                    and now >= self._guard_return_at \
                    and self.glide_target is None:
                # the hold-over-the-intruder pause is done: back to post
                self._guard_return_at = 0.0
                post = self._guard_post_point()
                if abs(self.x() - post.x()) > 30 \
                        or abs(self.y() - post.y()) > 30:
                    self.say("back to my post. 🫡", 1.6)
                    self._sync_float()
                    self._glide_to(post, speed=700)
            if (now > self.next_groom and now > self.groom_until
                    and not guarding):        # no grooming on duty — focus.
                self.groom_until = now + 2.6
                self.next_groom = now + random.uniform(30, 80)
            if (self.gcfg.get("window_perch", True)
                    and not guarding          # stay at the guard post
                    and not mgr.guide_active  # not while showing you around
                    and now > self.next_perch_try
                    and self.perch_hwnd is None
                    and self.perch_pending is None
                    and self.glide_target is None
                    and not self.peeking
                    and not mgr.fullscreen_active):
                lo, hi = mgr.perch_interval()
                self.next_perch_try = now + random.uniform(lo, hi)
                self.try_perch()

            # go stand in a corner now and then (opt-in, Behavior menu)
            if self._corner_going:
                # walking to the corner — when we arrive, start standing
                self.sleep_at = now + self.gcfg["sleep_seconds"]
                if self.glide_target is None:
                    self._corner_going = False
                    self._corner_until = now + random.uniform(15, 45)
            elif now < self._corner_until:
                # standing in the corner: just stay put, don't re-trigger
                self.sleep_at = now + self.gcfg["sleep_seconds"]
            elif (self.gcfg.get("corner_stand", False)
                    and not guarding
                    and not mgr.guide_active
                    and now > self.next_corner_at
                    and self.perch_hwnd is None
                    and self.perch_pending is None
                    and self.glide_target is None
                    and not self.peeking
                    and not mgr.fullscreen_active):
                lo, hi = mgr.corner_interval()
                self.next_corner_at = now + random.uniform(lo, hi)
                self._go_to_corner(now)

        if self.state != PEEK and self.peeking:
            was_fs = self._peek_was_fs
            self._peek_was_fs = False
            self._unpeek(cancel=True)
            if was_fs:                       # fullscreen ended — pop back up
                self.state = IDLE
                self.say(random.choice(
                    ["mrrp! is it over? 👀", "back! 😺", "phew, that's better."
                     ]), 1.8)
        if self.state != STRETCH and self.grow > 1.0:
            self._set_grow(False)

        self.wobble *= 0.92
        self.mochi += (1.0 - self.mochi) * 0.35   # spring back after drag
        self.update()

    # ------------------------------------------------------------- peeking --
    def _glide_to(self, pt, speed=1100):
        self.glide_target = QPoint(pt)
        self.glide_speed = speed
        self._sync_float()

    def _glide_step(self, dt):
        tx, ty = self.glide_target.x(), self.glide_target.y()
        dx, dy = tx - self._fx, ty - self._fy
        d = math.hypot(dx, dy)
        if d < 8:
            self.move(self.glide_target)
            self._sync_float()
            self.glide_target = None
            return
        step = min(d, getattr(self, 'glide_speed', 1100) * dt)
        self._fx += step * dx / d
        self._fy += step * dy / d
        if dx > 24:
            self.flip = False
        elif dx < -24:
            self.flip = True
        self.move(int(round(self._fx)), int(round(self._fy)))

    def _peek(self):
        if self.peeking:
            return
        self.peeking = True
        self._saved_pos = self.pos()
        tx = self._peek_x
        self._peek_x = None
        if tx is not None:
            scr = QGuiApplication.screenAt(QPoint(tx, 0)) \
                or self.screen() or QGuiApplication.primaryScreen()
            g = scr.geometry()
            x = max(g.left(), min(tx - self.width() // 2,
                                  g.right() - self.width()))
        else:
            scr = self.screen() or QGuiApplication.primaryScreen()
            g = scr.geometry()
            x = max(g.left(), min(self.x(), g.right() - self.width()))
        self._glide_to(QPoint(x, g.bottom() - self.height() + 1))

    def _stand_up_here(self):
        """Exit hiding by standing up at the bottom — no gliding home."""
        self.manual_peek = False
        self.peeking = False
        self._saved_pos = None
        try:
            g = self._ground_point()
            self.move(g)
            self._sync_float()
        except Exception:
            pass
        self.state = IDLE
        self.update()

    def _unpeek(self, cancel=True):
        if cancel:
            self.manual_peek = False
        if not self.peeking:
            return
        self.peeking = False
        if self._saved_pos is not None:
            self._glide_to(self._saved_pos)
            self._saved_pos = None

    # ------------------------------------------------------------- chasing --
    def _dist_to_cursor(self, cur):
        c = self.mapToGlobal(self.cat_rect().center())
        return math.hypot(cur.x() - c.x(), cur.y() - c.y())

    def _chase_step(self, cur, now, dt):
        c = self.mapToGlobal(self.cat_rect().center())
        dx, dy = cur.x() - c.x(), cur.y() - c.y()
        d = math.hypot(dx, dy)
        if d < 70:
            self.state = IDLE
            self.chase_cooldown = now + 4
            if self.gcfg.get("guard_mode", False):
                # intruder neutralised — stand over it a moment, THEN march
                # back to the watchtower (don't teleport back instantly)
                self.say(random.choice([
                    "intruder caught! 😼", "got you. hold still…",
                    "perimeter breach — detained. 🫡"]), 2.0)
                hold = random.uniform(3.0, 5.0)
                self._guard_return_at = now + hold
                self.chase_cooldown = now + hold + 0.5   # no re-pounce yet
            else:
                self.say(random.choice(["gotcha!", "hmph.", ":3"]), 1.5)
            return
        speed = 340.0                       # px / second, smooth
        step = min(speed * dt, d)
        self._fx += step * dx / d
        self._fy += step * dy / d
        # direction (with hysteresis) — used to lean into the run
        if dx > 24:
            self.flip = False
        elif dx < -24:
            self.flip = True
        scr = self.screen() or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        self._fx = max(g.left() - 20.0,
                       min(self._fx, float(g.right() - self.width() + 20)))
        self._fy = max(float(g.top()),
                       min(self._fy, float(g.bottom() - self.height() + 10)))
        nx, ny = int(round(self._fx)), int(round(self._fy))
        if (nx, ny) != (self.x(), self.y()):
            self.move(nx, ny)

    # -------------------------------------------------------- mouse events --
    def wheelEvent(self, ev):
        amt = abs(ev.angleDelta().y()) / 120.0 or 1.0
        self.mgr.inputs._native_scroll(amt)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self.peeking:
                if self.gcfg.get("hide_mode", False):
                    return              # firm hide: only the menu wakes it
                self._stand_up_here()
                return
            if self.mgr.cfg["global"].get("guard_mode", False):
                self.jump_until = max(self.jump_until, time.time() + 0.5)
                self.wobble = min(self.wobble + 5, 16)
                self.say(random.choice([
                    "HEY! hands off! 😾", "do NOT grab the guard!",
                    "hsss!! 😾", "I'm ARMED, you know.",
                    "unauthorized touch!!"]), 1.6)
            self.dragging = True
            self.glide_target = None
            self._parachute = False       # grabbed mid-air: chute packed away
            self._falling = False
            self.drag_offset = ev.globalPosition().toPoint() - self.pos()
            # the cat should hang from its raised paws (top-center of sprite)
            self._drag_target_offset = QPoint(
                self.width() // 2,
                TOP_MARGIN + int(1.5 * self.scale))
            self._drag_prev_cursor = ev.globalPosition().toPoint()
            self._drag_room = int(0.42 * sprites.GRID_H * self.scale)
            self.setFixedSize(self.width(), self.height() + self._drag_room)
            self._last_drag_x = ev.globalPosition().toPoint().x()
            self._last_drag_dir = 0
        elif ev.button() == Qt.RightButton:
            self.build_menu().exec(ev.globalPosition().toPoint())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self._drag_room = 0
            self._resize_to_sprite()
            if self.state == DRAG:
                self.state = IDLE
            self._sync_float()
            if self.gcfg.get("guard_mode", False):
                post = self._guard_post_point()
                if (abs(self.x() - post.x()) > 40
                        or abs(self.y() - post.y()) > 40):
                    self.say(random.choice(
                        ["back to my post. 😾", "I have a JOB to do.",
                         "nice try. resuming patrol."]), 2.2)
                    self._glide_to(post, speed=600)
            self.mgr.save_all()

    def mouseMoveEvent(self, ev):
        gp = ev.globalPosition().toPoint()
        if self.dragging:
            self.move(gp - self.drag_offset)
            self._sync_float()
            dx = gp.x() - self._last_drag_x
            if abs(dx) > 3:
                direction = 1 if dx > 0 else -1
                if direction != self._last_drag_dir and self._last_drag_dir:
                    self.wobble = min(self.wobble + 4.5, 16)
                self._last_drag_dir = direction
            self._last_drag_x = gp.x()
            return
        if self.state in (IDLE, KNEAD, SLEEP, THINK):
            x0, y0, x1, y1 = sprites.HEAD_RECT
            head = QRect(self.side + x0 * self.scale,
                         TOP_MARGIN + y0 * self.scale,
                         (x1 - x0) * self.scale, (y1 - y0) * self.scale)
            if head.contains(ev.position().toPoint()):
                self.pet_accum += 1
                now = time.time()
                guarding = self.mgr.cfg["global"].get("guard_mode", False)
                if self.pet_accum > 14 and now - self.last_pet_heart > 0.45:
                    self.last_pet_heart = now
                    self.pet_accum = 0
                    if guarding:
                        # no petting on duty — it gets MAD
                        self.jump_until = max(self.jump_until, now + 0.5)
                        if random.random() < 0.6:
                            self.say(random.choice([
                                "don't touch me! 😾", "HANDS OFF.",
                                "I'm on duty!", "grrr… 😾", "hsss!"]), 1.4)
                    else:
                        r = self.cat_rect()
                        self.hearts.append({
                            "x": r.left() + random.randint(20, r.width() - 20),
                            "y": r.top() + 8, "vy": 1.1, "life": 1.6,
                            "seed": random.random() * 6})
                        # purr ♥ once at a time (its own cooldown ≈ the purr
                        # length so it doesn't retrigger every tick and garble)
                        if self.gcfg.get("sounds", True) \
                                and now - self._last_purr > 2.3:
                            self._last_purr = now
                            try:
                                if self.mgr._sfx is None:
                                    self.mgr._sfx = SoundFX(
                                        self.mgr.cfg["global"].get("sound_volume", 0.6))
                                self.mgr._sfx.purr()
                            except Exception:
                                pass
                        if random.random() < 0.3:
                            self.say(random.choice(
                                ["purrr…", "prrrp", "♥"]), 1.2)
                    if self.state == SLEEP \
                            and not self.gcfg.get("force_sleep") \
                            and not self.perch_asleep:
                        self.sleep_at = now + self.gcfg["sleep_seconds"]
                        self.state = IDLE

    # ------------------------------------------------- window perching ------
    _WIN32 = None

    @classmethod
    def _win32(cls):
        if cls._WIN32 is not None:
            return cls._WIN32
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindow.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsIconic.restype = wintypes.BOOL
        u.IsZoomed.argtypes = [wintypes.HWND]
        u.IsZoomed.restype = wintypes.BOOL
        try:
            u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.getlong = u.GetWindowLongPtrW
        except AttributeError:
            u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.GetWindowLongW.restype = ctypes.c_long
            u.getlong = u.GetWindowLongW
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                    ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowRect.argtypes = [wintypes.HWND,
                                    ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.WindowFromPoint.argtypes = [wintypes.POINT]
        u.WindowFromPoint.restype = wintypes.HWND
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetAncestor.restype = wintypes.HWND
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                         wintypes.LPARAM)
        u.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL
        try:
            d = ctypes.WinDLL("dwmapi")
            d.DwmGetWindowAttribute.argtypes = [wintypes.HWND,
                                                wintypes.DWORD,
                                                ctypes.c_void_p,
                                                wintypes.DWORD]
            d.DwmGetWindowAttribute.restype = ctypes.c_long
        except Exception:
            d = None
        cls._WIN32 = (ctypes, wintypes, u, d, WNDENUMPROC)
        return cls._WIN32

    def _win_cloaked(self, hwnd):
        ctypes, wintypes, u, d, _ = self._win32()
        if d is None:
            return False
        val = wintypes.DWORD(0)
        if d.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(val),
                                   ctypes.sizeof(val)) == 0:
            return val.value != 0
        return False

    def _win_rect_raw(self, hwnd):
        ctypes, wintypes, u, d, _ = self._win32()
        r = wintypes.RECT()
        ok = False
        if d is not None:
            ok = d.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r),
                                         ctypes.sizeof(r)) == 0
        if not ok and not u.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        return (r.left, r.top, r.right, r.bottom)

    def _win_rect(self, hwnd):
        raw = self._win_rect_raw(hwnd)
        if raw is None:
            return None
        dpr = self._dpr()
        return tuple(int(v / dpr) for v in raw)

    def _showing_at(self, hwnd, px, py):
        """Is `hwnd` the window actually visible at physical point (px,py)?
        Returns True/False, or None when our own cat covers the point."""
        try:
            ctypes, wintypes, u, d, _ = self._win32()
            pt = wintypes.POINT(int(px), int(py))
            top = u.WindowFromPoint(pt)
            if not top:
                return False
            root = u.GetAncestor(top, 2) or top
            if int(root) in {int(c.winId()) for c in self.mgr.cats}:
                return None
            return int(root) == int(hwnd)
        except Exception:
            return True          # never evict on probe errors

    def _visible_top_xs(self, hwnd, raw):
        """Logical x positions along the window top that are truly showing."""
        l, t, r, b = raw
        dpr = self._dpr()
        out = []
        for frac in (0.2, 0.5, 0.8):
            px = l + (r - l) * frac
            if self._showing_at(hwnd, px, t + 8 * max(1, dpr)):
                out.append(int(px / dpr))
        return out
    def _feet_offset(self):
        return TOP_MARGIN + int((sprites.GRID_H - 2) * self.scale)

    def _dpr(self):
        try:
            return float(self.screen().devicePixelRatio()) or 1.0
        except Exception:
            return 1.0

    def _perch_targets(self):
        """Visible, non-minimized, decent-sized top-level windows."""
        if platform.system() != "Windows":
            return []
        try:
            ctypes, wintypes, u, d, WNDENUMPROC = self._win32()
            own = {int(c.winId()) for c in self.mgr.cats}
            out = []

            def cb(hwnd, _l):
                try:
                    if int(hwnd) in own or not u.IsWindowVisible(hwnd) \
                            or u.IsIconic(hwnd):
                        return True
                    if u.GetWindowTextLengthW(hwnd) == 0:
                        return True
                    cls = ctypes.create_unicode_buffer(64)
                    u.GetClassNameW(hwnd, cls, 64)
                    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd",
                                     "SondeRcatSetup"):
                        return True
                    if self._win_cloaked(hwnd):
                        return True          # ghost: not really on screen
                    if u.getlong(hwnd, -20) & 0x00000080:
                        return True          # WS_EX_TOOLWINDOW
                    raw = self._win_rect_raw(hwnd)
                    if raw is None:
                        return True
                    dpr = self._dpr()
                    rect = tuple(int(v / dpr) for v in raw)
                    l_, t_, r_, b_ = rect
                    if r_ - l_ < 380 or b_ - t_ < 260:
                        return True
                    if t_ - self._feet_offset() < 8:
                        return True          # no headroom for the cat
                    xs = self._visible_top_xs(hwnd, raw)
                    if not xs:
                        return True          # buried under other windows
                    out.append((int(hwnd), rect, xs))
                except Exception:
                    pass
                return True

            u.EnumWindows(WNDENUMPROC(cb), 0)
            return out
        except Exception:
            return []

    def _perch_query(self, hwnd):
        """('ok', rect) while perchable; 'minimized'; 'gone'."""
        if platform.system() != "Windows":
            return "gone"
        try:
            _c, _w, u, _d, _p = self._win32()
            if not u.IsWindow(hwnd) or not u.IsWindowVisible(hwnd):
                return "gone"
            if u.IsIconic(hwnd):
                return "minimized"
            if u.IsZoomed(hwnd):
                return "maximized"
            if self._win_cloaked(hwnd):
                return "minimized"
            rect = self._win_rect(hwnd)
            if rect is None:
                return "gone"
            return ("ok", rect)
        except Exception:
            return "gone"

    def _ground_point(self):
        scr = self.screen().availableGeometry()
        gx = max(scr.left() + 8,
                 min(self.x(), scr.right() - self.width() - 8))
        gy = scr.bottom() - self._feet_offset()
        return QPoint(gx, gy)

    def _enter_duck_corner(self):
        """Easter-egg: plant the cat in the bottom-LEFT corner as the gunner."""
        if self.perch_hwnd is not None:
            self._end_perch(go_home=False)
        self.state = IDLE
        self.manual_peek = False
        self.groom_until = 0.0
        self._corner_going = False
        self._corner_until = 0.0
        self._sync_float()
        scr = self.screen().availableGeometry()
        gy = scr.bottom() - self._feet_offset()
        gx = scr.left() + 8
        self._glide_to(QPoint(gx, gy), speed=600)

    def _corner_point(self):
        """The bottom corner the cat is currently CLOSEST to (left or right),
        so it doesn't cross the whole screen or keep switching sides."""
        scr = self.screen().availableGeometry()
        gy = scr.bottom() - self._feet_offset()
        left_x = scr.left() + 6
        right_x = scr.right() - self.width() - 6
        cat_cx = self.x() + self.width() // 2
        screen_mid = (scr.left() + scr.right()) // 2
        gx = left_x if cat_cx <= screen_mid else right_x
        return QPoint(gx, gy)

    def _go_to_corner(self, now):
        """Amble over to the nearest screen corner and hang out there a while.
        The 'stand here' timer starts only once it ARRIVES (set in tick), so
        the walk doesn't eat into the standing time and it can't re-pick a
        corner mid-trip."""
        if self.perch_hwnd is not None:
            self._end_perch(go_home=False)
        self.state = IDLE
        self.groom_until = 0.0
        self._sync_float()
        self._glide_to(self._corner_point(), speed=260)
        self._corner_going = True          # en route to the corner
        self._corner_until = 0.0
        if random.random() < 0.6:
            self.say(random.choice(["off to my corner 🧍", "corner time.",
                                    "just gonna stand here.", "🧍"]), 2.0)

    def _guard_post_point(self):
        """Top-center of the current screen — the watchtower spot.
        Extra cats fan out left/right so they don't stack."""
        scr = self.screen().availableGeometry()
        i = self.index
        shift = ((i + 1) // 2) * (self.width() + 24) * (1 if i % 2 else -1)
        x = scr.center().x() - self.width() // 2 + shift
        x = max(scr.left() + 8, min(x, scr.right() - self.width() - 8))
        return QPoint(x, scr.top())

    def go_to_guard_post(self):
        """Guard mode ON: abandon whatever we're doing and take position
        at the top-center of the screen for the best view."""
        try:
            if self.perch_hwnd is not None or self.perch_pending is not None:
                self._end_perch(go_home=False)
            if self.peeking:
                self._unpeek(cancel=True)
        except Exception:
            pass
        self.manual_peek = False
        self.groom_until = 0.0
        self._corner_until = 0.0          # abandon any corner-standing
        self._corner_going = False
        self._glide_to(self._guard_post_point(), speed=600)

    def _perch_covered(self, l, t, r, b):
        """Probe beside the cat: is our window's top edge still showing?"""
        if platform.system() != "Windows" or self.perch_hwnd is None:
            return False
        dpr = self._dpr()
        # a point next to the cat (never under it), just inside the top edge
        px = self.x() - 50
        if px < l + 10:
            px = self.x() + self.width() + 50
        px = max(l + 10, min(px, r - 10))
        res = self._showing_at(self.perch_hwnd, px * dpr,
                               (t + 8) * dpr)
        return res is False          # None (our own cat) never counts

    def try_perch(self, announce=False):
        targets = self._perch_targets()
        if not targets:
            if announce:
                self.say("no window… nap time then 💤", 2.5)
            # only walk to the floor if we're actually perched and need to
            # come down; if already on the ground, stay put and just wait
            # (crucial for "Instant" — otherwise it paces down endlessly)
            if self.perch_hwnd is not None:
                try:
                    self._end_perch(go_home=True)
                except Exception:
                    pass
            lo, hi = self.mgr.perch_interval()
            self.next_perch_try = time.time() + random.uniform(lo, hi * 1.3)
            return False
        choice = random.choice(targets)
        hwnd, (l, t, r, b) = choice[0], choice[1]
        xs = choice[2] if len(choice) > 2 else None
        if xs:
            x = random.choice(xs) + random.randint(-30, 30)
            x = max(l + 20, min(x, r - self.width() - 20))
        else:
            x = random.randint(l + 20, max(l + 20, r - self.width() - 20))
        y = t - self._feet_offset()
        self.perch_home = self.pos()
        self.perch_pending = hwnd
        self.perch_offx = x - l
        self._glide_to(QPoint(x, y), speed=300)   # walk, don't run
        return True


    def _draw_parachute(self, p, now):
        """Big pixel-art parachute above the cat while it drifts down.
        Canopy spans the full cat width (26 cells x 8 rows). Cell width
        always matches the sprite scale; cell HEIGHT flattens slightly at
        very large cat sizes where the fixed top margin runs out of room."""
        from PySide6.QtGui import QColor, QPen
        s = max(2, int(self.scale))
        top_row = getattr(CatWindow, "_DANGLE_TOP", None)
        if top_row is None:
            g = sprites.FRAMES.get("dangle", [])
            top_row = next((y for y, row in enumerate(g)
                            if any(c != "." for c in row)), 2)
            CatWindow._DANGLE_TOP = top_row
        head_top = TOP_MARGIN + top_row * s
        cx = self.cat_rect().center().x()
        rows_n = 8
        half_cells = 13                    # 26 cells: as wide as the cat
        strings_h = min(max(2 * s, 8), max(6, head_top // 4))
        cell_w = s
        cell_h = min(s, max(2, (head_top - strings_h - 2) // rows_n))
        max_half = (self.width() // 2 - 2) // cell_w
        half_cells = max(6, min(half_cells, max_half))
        canopy_h = rows_n * cell_h
        y0 = head_top - strings_h - canopy_h
        red = QColor("#d9534f"); cream = QColor("#f6ead8")
        dark = QColor("#4a2f1a")
        for ry in range(rows_n):
            frac = (ry + 1) / rows_n
            hw = max(3, int(round(half_cells * math.sqrt(frac * (2 - frac)))))
            yy = y0 + ry * cell_h
            for k in range(-hw, hw):
                col = red if ((k + 130) // 4) % 2 == 0 else cream
                if ry == 0 or k in (-hw, hw - 1):
                    col = dark             # outline: crown row + side edges
                p.fillRect(cx + k * cell_w, yy, cell_w, cell_h, col)
            if ry == rows_n - 1:           # scalloped dark rim on the bottom
                for k in range(-hw, hw, 4):
                    p.fillRect(cx + k * cell_w, yy + cell_h,
                               cell_w, max(2, cell_h // 2), dark)
        # strings: 4 of them, from the canopy edge down to the raised paws
        pen = QPen(dark); pen.setWidth(max(2, s // 2)); p.setPen(pen)
        yb = y0 + canopy_h
        paw_y = head_top + int(1.5 * s)
        p.drawLine(cx - (half_cells - 1) * cell_w, yb,
                   cx - int(2.5 * s), paw_y)
        p.drawLine(cx - (half_cells // 2) * cell_w, yb,
                   cx - int(1.2 * s), head_top + s)
        p.drawLine(cx + (half_cells // 2) * cell_w, yb,
                   cx + int(1.2 * s), head_top + s)
        p.drawLine(cx + (half_cells - 1) * cell_w, yb,
                   cx + int(2.5 * s), paw_y)

    def _parachute_to_ground(self):
        """Deploy the parachute and drift down to the floor from wherever the
        cat is (guard-post stand-down, lost perch, …). Only floats if there's
        actually height to fall; otherwise just walks down."""
        try:
            g = self._ground_point()
            if g.y() - self.y() > 3 * self.scale:      # high enough to float
                self._glide_to(g, speed=160)
                self._falling = True
                self._parachute = True
                self.say("\u2602\ufe0f!", 1.4)
            else:
                self._glide_to(g, speed=400)
        except Exception:
            pass

    def _fall_off(self, now):
        self._end_perch(go_home=False)
        try:
            # ☂ deploy the parachute: a slow, swaying drift to the ground
            # (instead of plummeting) — the cat hangs in its pickup pose
            # under a little canopy the whole way down.
            self._glide_to(self._ground_point(), speed=160)
            self._falling = True
            self._parachute = True
            self.say("☂️!", 1.4)
        except Exception:
            pass
        lo, hi = self.mgr.perch_interval()
        self.next_perch_try = now + random.uniform(lo, hi * 1.3)

    def _end_perch(self, go_home):
        self.perch_asleep = False
        self.perch_hwnd = None
        self.perch_pending = None
        if go_home and self.perch_home is not None:
            self._glide_to(self.perch_home, speed=300)
        self.perch_home = None

    def _perch_tick(self, now):
        if self._falling and self.glide_target is None:
            self._falling = False
            if getattr(self, "_parachute", False):
                self._parachute = False        # ☂ packed away
                self.say(random.choice(["☂️ smooth landing.", "phew. ☂️",
                                        "touchdown 🪂", "nailed it. 😌"]), 2.2)
            else:
                self.wobble = max(self.wobble, 3.0)
                self.say(random.choice(["oouch!!", "oof.", "😾 rude.",
                                        "I meant to do that."]), 2.2)
        if self.perch_pending is not None and self.glide_target is None:
            self.perch_hwnd = self.perch_pending
            self.perch_pending = None
            self.perch_until = now + random.uniform(90, 240)
            self._shake_strikes = 0
            self._cover_miss = 0
            nap_chance = self.mgr.cfg["global"].get(
                "perch_nap_chance", 0.3)
            if random.random() < nap_chance:
                # nap: commits to sleeping until physically disturbed
                self.perch_asleep = True
                self.yawn_until = now + 0.9
                if random.random() < 0.7:
                    self.say(random.choice(["perfect nap spot 💤",
                                            "zzz spot acquired",
                                            "mine now. 💤"]), 2.5)
            else:
                # watch half: stays alert up there, keeping an eye on you
                self.sleep_at = now + self.gcfg["sleep_seconds"]
                if random.random() < 0.7:
                    self.say(random.choice(["nice view up here",
                                            "mine now.", "👀",
                                            "supervising."]), 2.5)
        if self.perch_hwnd is None:
            return
        q = self._perch_query(self.perch_hwnd)
        if q == "gone":
            self._perch_miss += 1
            if self._perch_miss < 3:
                return                      # transient hiccup: hold on
        else:
            self._perch_miss = 0
        if q == "gone" or q == "maximized":
            self._fall_off(now)              # dropped! (closed / maximized)
            return
        if q == "minimized":
            self._end_perch(go_home=False)
            # walk down to the bottom of the screen and settle for a nap
            try:
                g = self._ground_point()
                if abs(g.y() - self.y()) > 4:
                    self._glide_to(g, speed=300)
            except Exception:
                pass
            self.sleep_at = now               # doze off once settled
            lo, hi = self.mgr.perch_interval()
            self.next_perch_try = now + random.uniform(lo, hi)
            return
        _, (l, t, r, b) = q
        if self._perch_covered(l, t, r, b):
            self._cover_miss += 1
            if self._cover_miss > 22:        # ~0.7s: not just a menu popup
                self._end_perch(go_home=False)
                try:
                    g = self._ground_point()
                    if abs(g.y() - self.y()) > 4:
                        self._glide_to(g, speed=300)
                except Exception:
                    pass
                self.sleep_at = now
                lo, hi = self.mgr.perch_interval()
                self.next_perch_try = now + random.uniform(lo, hi)
                return
        else:
            self._cover_miss = 0
        x = max(l + 6, min(l + self.perch_offx, r - self.width() - 6))
        y = t - self._feet_offset()
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
            self._sync_float()
        # shaking the window under the cat: it objects
        self._perch_hist.append((now, l))
        pts = [(t_, l_) for (t_, l_) in self._perch_hist if now - t_ < 0.8]
        flips = 0
        last_dir = 0
        for i in range(1, len(pts)):
            d = pts[i][1] - pts[i - 1][1]
            if abs(d) < 12:
                continue
            direc = 1 if d > 0 else -1
            if last_dir and direc != last_dir:
                flips += 1
            last_dir = direc
        if flips >= 3 and now > self._shake_quiet_until:
            self._shake_quiet_until = now + 5
            self._perch_hist.clear()
            self._shake_strikes += 1
            if self._shake_strikes >= 2:     # shaken again: loses its grip
                self._fall_off(now)
                return
            self.perch_asleep = False        # rude awakening
            self.perch_until = max(self.perch_until,
                                   now + random.uniform(20, 60))
            self.wobble = max(self.wobble, 3.0)
            self.say(random.choice(["stop shaking!!", "hey!! stop moving",
                                    "woOoOah", "earthquake!! 🙀"]), 2.2)
        if now > self.perch_until and not self.perch_asleep:
            self._end_perch(go_home=True)
            lo, hi = self.mgr.perch_interval()
            self.next_perch_try = now + random.uniform(lo, hi)

    # -------------------------------------------------------------- render --
    def _frame_name(self):
        now = time.time()
        slow = int(now / 0.36) % 2          # time-based: smooth at any fps
        fast = int(now / 0.18) % 2
        if getattr(self, "_falling", False) and self.glide_target is not None:
            return "dangle"
        if self.glide_target is not None and self.state != DRAG:
            if getattr(self, "glide_speed", 1100) <= 600:
                return "run_a" if int(now / 0.34) % 2 else "run_b"
            return "run_a" if fast else "run_b"
        if self.state == DANCE:
            return "sit_a" if int(now / 0.24) % 2 else "sit_b"
        if self.state == SLEEP:
            if now < self.yawn_until:
                return "yawn"
            return "sleep"
        if self.state == STRETCH:
            return "stretch"
        if self.state == PEEK:
            return "peek"
        if self.state == DRAG:
            return "dangle"
        if self.state in (KNEAD, OVERHEAT):
            # paws tap in lockstep with your keystrokes: each key press flips
            # the frame (key #1 -> a, key #2 -> b, ...). Holding a key keeps
            # that paw pressed down until you release. A brief pause after
            # the last key holds the frame ~1s before settling.
            return "type_a" if (self.mgr.inputs.key_count & 1) else "type_b"
        if self.state == SCROLLPLAY:
            return ("knead_c", "knead_b", "knead_a",
                    "knead_b")[int(now / 0.14) % 4]
        if self.state == CHASE:
            return "run_a" if fast else "run_b"
        if self.state == THINK:
            return "sit_a" if fast else "sit_b"
        if now < self.groom_until:
            return "groom_a" if fast else "groom_b"
        if now < self.blink_until:
            return "blink"
        return "sit_a" if slow else "sit_b"

    def _frame_image(self, name, flip, hot=False):
        key = (name, flip, hot, self.ccfg["pattern"], self.ccfg["palette"],
               self.ccfg.get("custom_body"), self.scale)
        img = self._frame_cache.get(key)
        if img is None:
            fallback = {"yawn": "blink",
                        "groom_a": "sit_a", "groom_b": "sit_a",
                        "knead_c": "knead_b"}
            base = sprites.FRAMES.get(name)
            if base is None:
                base = sprites.FRAMES[fallback.get(name, "sit_a")]
            grid = sprites.apply_pattern(base, self.ccfg["pattern"],
                                         head_only=(name == "peek"))
            pal = sprites.OVERHEAT_PALETTE if hot else self.palette()
            img = sprites.render_frame(grid, pal, self.scale, flip)
            self._frame_cache[key] = img
        return img

    _HELMET_CACHE = {}

    def _helmet_cells(self, name):
        """Camo helmet dome + brim, sitting ON the head crown."""
        cached = CatWindow._HELMET_CACHE.get(name)
        if cached is not None:
            return cached
        g = sprites.FRAMES.get(name)
        if not g:
            CatWindow._HELMET_CACHE[name] = ([], [], [])
            return ([], [], [])
        H = len(g)
        # the "crown" is the first FULL-WIDTH head row (below the ear gap):
        # scan down for the row where the head becomes solid across its width
        crown_y, L, R = None, 4, 21
        for y in range(1, min(12, H)):
            xs = [x for x, c in enumerate(g[y]) if c != "."]
            if not xs:
                continue
            span = max(xs) - min(xs)
            # a wide, mostly-filled row = the top of the skull (not ears)
            filled = sum(1 for c in g[y] if c != ".")
            if span >= 12 and filled >= span - 1:
                crown_y, L, R = y, min(xs), max(xs)
                break
        if crown_y is None:
            CatWindow._HELMET_CACHE[name] = ([], [], [])
            return ([], [], [])
        dome, brim, camo = [], [], []
        cx = (L + R) / 2.0
        half = (R - L) / 2.0
        # dome: 3 rows curving over the crown (rows crown_y-1 .. crown_y+1),
        # narrowing toward the top for a rounded helmet silhouette
        for row_i, dy in enumerate((crown_y - 1, crown_y, crown_y + 1)):
            # curvature: top row inset most, lower rows wider
            inset = (2 - row_i)
            for x in range(int(L + inset), int(R - inset) + 1):
                if 0 <= x < sprites.GRID_W and 0 <= dy < H:
                    dome.append((x, dy))
        # brim: one row below the dome, full head width, slight forward jut
        by = crown_y + 2
        for x in range(L, R + 1):
            if 0 <= x < sprites.GRID_W and 0 <= by < H:
                brim.append((x, by))
        # camo: deterministic sparse patches on the dome
        for (x, y) in dome:
            if ((x * 5 + y * 11) % 4) == 0:
                camo.append((x, y))
        cached = (dome, brim, camo)
        CatWindow._HELMET_CACHE[name] = cached
        return cached

    def _guard_side(self, now=None):
        """0 = torch in right paw looking right, 1 = left. Flips ~4.5s."""
        if now is None:
            now = time.time()
        return int(now / 4.5) % 2

    def _guard_beam_angle(self, now=None):
        """The direction the patrol beam (and the flashlight) points, in
        radians (y-down). Shared by the beam overlay and the torch sprite
        so they always aim the same way. Sweeps an arc, biased outward-and-
        down toward whichever paw currently holds the torch."""
        if now is None:
            now = time.time()
        left = self._guard_side(now) == 1
        base = (math.pi - 0.62) if left else 0.62
        return base + math.sin(now * 0.8) * 0.7 * (-1 if left else 1)

    def _draw_flashlight(self, p, name, s):
        # a chunky handheld flashlight held out at the right FOREPAW,
        # pointing right; the red beam emerges from its lens
        g = sprites.FRAMES.get(name)
        W = sprites.GRID_W
        H = len(g) if g else sprites.GRID_H
        # anchor: rightmost sprite content near the paw line (bottom rows)
        fy = H - 7
        left = self._guard_side() == 1
        edge_x = (W - 1) if not left else 0
        if g:
            found = None
            for y in range(max(0, H - 9), H - 2):
                xs = [x for x, c in enumerate(g[y]) if c != "."]
                if xs:
                    v = max(xs) if not left else min(xs)
                    if found is None:
                        found = v
                    else:
                        found = max(found, v) if not left \
                            else min(found, v)
            if found is not None:
                edge_x = found
        if not left:
            rpaw = min(max(edge_x, 12), W - 6)   # torch extends right
        else:
            rpaw = max(min(edge_x, W - 13), 5)   # torch extends LEFT
        body = QColor("#33373f")
        band = QColor("#20232a")
        headc = QColor("#c8ccd2")            # metal head ring
        lensc = QColor("#fff4be")
        edge = QColor("#15171c")
        # the torch ROTATES to point along the beam. Pivot at the grip
        # (the paw); the 5-cell torch (grip, body×2, head, lens) is drawn
        # along +x in a rotated frame, so it always aims where the beam does
        ang = self._guard_beam_angle()
        px, py = rpaw + 0.5, fy + 1.0        # grip pivot (cell coords)
        p.save()
        aa_was = p.testRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.translate(px * s, py * s)
        p.rotate(math.degrees(ang))
        # local +x = along the beam; cell i center at local x = i*s, the
        # torch is 2 cells tall centred on the axis (y in [-s, +s])
        def cell(i, col):
            p.fillRect(int(i * s - 0.5 * s), int(-s), int(s), int(2 * s), col)
        # warm glow just past the lens, painted first so solids stay clean
        glow = QColor(255, 130, 100); glow.setAlpha(140)
        p.setPen(Qt.NoPen); p.setBrush(glow)
        p.drawEllipse(QPointF(4.6 * s, 0), s * 1.8, s * 1.8)
        # outline behind the barrel for pop
        p.fillRect(int(-0.5 * s - 1), int(-s - 1),
                   int(5 * s + 2), int(2 * s + 2), edge)
        cell(0, band)                        # grip (at the paw)
        cell(1, body)
        cell(2, body)
        cell(3, headc)                       # metal head
        cell(4, lensc)                       # bright lens
        p.setRenderHint(QPainter.Antialiasing, aa_was)
        p.restore()
        # beam origin = the rotated lens centre (cell coords). The overlay
        # adds (+0.5, +1.0) when it reads this, so subtract them here.
        lens_x = px + 4.0 * math.cos(ang)
        lens_y = py + 4.0 * math.sin(ang)
        self._torch_lens = (lens_x - 0.5, lens_y - 1.0)

    def _draw_helmet(self, p, name, s):
        dome, rim, camo = self._helmet_cells(name)
        base = QColor("#5a6348")       # olive drab
        camo_c = QColor("#3f4632")     # darker camo patch
        rim_c = QColor("#40472f")      # brim
        edge = QColor("#2c3122")       # outline
        # outline pass (draw a ring under the dome)
        for (x, y) in dome:
            p.fillRect(x * s - 1, y * s - 1, s + 2, s + 2, edge)
        for (x, y) in dome:
            p.fillRect(x * s, y * s, s, s, base)
        for (x, y) in camo:
            p.fillRect(x * s, y * s, s, s, camo_c)
        for (x, y) in rim:
            p.fillRect(x * s, y * s, s, max(2, s // 2), rim_c)

    _HEADSET_CACHE = {}

    def _headset_cells(self, name):
        cached = CatWindow._HEADSET_CACHE.get(name)
        if cached is not None:
            return cached
        g = sprites.FRAMES.get(name, sprites.FRAMES["sit_a"])
        rows = [y for y, row in enumerate(g)
                if any(c != "." for c in row)]
        top = rows[0] if rows else 1
        cols = [x for y in range(top, min(top + 3, len(g)))
                for x, c in enumerate(g[y]) if c != "."]
        L, R = (min(cols), max(cols)) if cols else (4, 21)
        dark, lite = [], []
        OUT = 1              # nudge cups outward so they clear the eyes
        if L > 8 and R < 17:
            # topmost content is raised paws (dangle/stretch): anchor on
            # the ears at the sides instead, and skip the band — it would
            # cross the raised arms
            side = [y for y, row in enumerate(g)
                    if any(c != "." for x, c in enumerate(row)
                           if x <= 8 or x >= 17)]
            t2 = side[0] if side else top
            sc = [x for y in range(t2, min(t2 + 3, len(g)))
                  for x, c in enumerate(g[y])
                  if c != "." and (x <= 8 or x >= 17)]
            L2, R2 = (min(sc), max(sc)) if sc else (4, 21)
            RIN = 1          # dangle/stretch: right cup 1 closer to the face
            Lcup = [L2 - 3 - OUT, L2 - 2 - OUT, L2 - 1 - OUT]
            Rcup = [R2 + 1 + OUT - RIN, R2 + 2 + OUT - RIN, R2 + 3 + OUT - RIN]
            # keep a 1-cell margin from the sprite edges so the white outline
            # (drawn just outside the cup) never falls off-canvas and breaks.
            # the right side gets an extra cell of margin because the drag
            # mochi-squish compresses the far-right columns and was clipping
            # the right cup's outline on real displays.
            Lcup = [x + max(0, 1 - min(Lcup)) for x in Lcup]
            Rcup = [x + min(0, (sprites.GRID_W - 4) - max(Rcup)) for x in Rcup]
            for cy in range(t2 + 3, t2 + 8):
                for cx in Lcup + Rcup:
                    dark.append((cx, cy))
            lite += [(Lcup[1], t2 + 4), (Rcup[1], t2 + 4),
                     (Lcup[1], t2 + 5), (Rcup[1], t2 + 5)]
            W, H = sprites.GRID_W, sprites.GRID_H
            dark = [(x, y) for (x, y) in dark if 0 <= x < W and 0 <= y < H]
            lite = [(x, y) for (x, y) in lite if 0 <= x < W and 0 <= y < H]
            cached = (dark, lite)
            CatWindow._HEADSET_CACHE[name] = cached
            return cached
        # typing/kneading poses look sideways: far cup tucks behind the
        # head; front-facing poses (dancing) wear both cups fully
        tucked = name.startswith(("type_", "knead_"))
        Wc = sprites.GRID_W
        Rcup = [R + 1 + OUT, R + 2 + OUT, R + 3 + OUT]
        Rcup = [x + min(0, (Wc - 2) - max(Rcup)) for x in Rcup]  # edge margin
        for cy in range(top + 5, top + 10):
            for cx in Rcup:
                dark.append((cx, cy))
        if tucked:
            fc = max(1, L - 1 - OUT)                 # keep off the left edge
            for cy in range(top + 6, top + 10):
                dark.append((fc, cy))
        else:
            Lcup = [L - 3 - OUT, L - 2 - OUT, L - 1 - OUT]
            Lcup = [x + max(0, 1 - min(Lcup)) for x in Lcup]     # edge margin
            for cy in range(top + 5, top + 10):
                for cx in Lcup:
                    dark.append((cx, cy))
            lite += [(Lcup[1], top + 6), (Lcup[1], top + 7)]
        lite += [(Rcup[1], top + 6), (Rcup[1], top + 7)]
        # band arcs between the cups
        mid = (L + R) / 2.0
        for x in range(L - 1, R + 2):
            t = abs(x - mid) / max(1.0, mid - (L - 1))
            y = top + int(round(t * t * 3))
            dark.append((x, y))
            dark.append((x, y + 1))
        lite += [(L, top + 3), (R, top + 3)]
        W, H = sprites.GRID_W, sprites.GRID_H
        dark = [(x, y) for (x, y) in dark if 0 <= x < W and 0 <= y < H]
        lite = [(x, y) for (x, y) in lite if 0 <= x < W and 0 <= y < H]
        cached = (dark, lite)
        CatWindow._HEADSET_CACHE[name] = cached
        return cached

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        now = time.time()
        s = self.scale

        name = self._frame_name()
        hot = (self.state == OVERHEAT)
        # face the CENTER of the screen while typing AND while just standing
        # around (idle/thinking): cat on the right half looks left, cat on
        # the left half looks right (art faces left by default, so flip when
        # the cat is on the LEFT half). Only while standing still — a cat
        # mid-walk would visibly pop-flip crossing the middle — and never on
        # guard duty (the helmet/flashlight overlays aren't mirrored).
        face_flip = False
        flip_state = (self.state in (KNEAD, OVERHEAT)
                      or (self.state in (IDLE, THINK)
                          and self.glide_target is None
                          and not self.dragging
                          and not self.mgr.cfg["global"].get(
                              "guard_mode", False)))
        if flip_state:
            scr = (self.screen() or QGuiApplication.primaryScreen()).geometry()
            cat_cx = self.x() + self.width() // 2
            screen_mid = (scr.left() + scr.right()) // 2
            face_flip = cat_cx < screen_mid       # left half → face right
        img = self._frame_image(name, face_flip, hot).copy()

        # headphones: music app playing = worn while dancing; browser
        # audio = worn quietly on whatever the cat is doing
        wearing = (self.gcfg.get("dance_music", True)
                   and self.mgr.music_mode in ("listen", "dance")
                   and not self.mgr.cfg["global"].get("guard_mode", False))
        if wearing:
            hp = QPainter(img)
            dkc = QColor("#2a2a33")
            ltc = QColor("#7d7d94")
            whc = QColor("#ffffff")           # matches the cat-body outline
            # NOTE: the base sprite is never mirrored (facing is shown by
            # the run tilt), so the headset must not mirror either
            dcells, lcells = self._headset_cells(name)
            if face_flip:                      # frame is mirrored → mirror cups
                W0 = sprites.GRID_W - 1
                dcells = [(W0 - hx, hy) for (hx, hy) in dcells]
                lcells = [(W0 - hx, hy) for (hx, hy) in lcells]
            # white outline ONLY on the small outer edge of each cup (the bit
            # that sticks out into the background) — never the band. The band
            # is a short 2-cell-tall arc; the cups are tall (4-5 cell) vertical
            # runs, so we outline only cells that sit in a tall column.
            solid = set(dcells) | set(lcells)
            W, H = sprites.GRID_W, sprites.GRID_H
            col_h = {}
            for (hx, hy) in dcells:
                col_h[hx] = col_h.get(hx, 0) + 1
            xs = [x for x, _ in dcells]
            midx = (min(xs) + max(xs)) / 2.0 if xs else W / 2.0
            halo = set()
            for (hx, hy) in dcells:
                if col_h.get(hx, 0) < 4:
                    continue                 # band cell -> no outline
                out = -1 if hx < midx else 1
                if (hx + out, hy) in solid:
                    continue                 # inner column -> not an edge
                for nb in ((hx + out, hy),           # outer face
                           (hx, hy - 1), (hx, hy + 1),        # top/bottom cap
                           (hx + out, hy - 1), (hx + out, hy + 1)):  # corners
                    if nb not in solid and 0 <= nb[0] < W and 0 <= nb[1] < H:
                        halo.add(nb)
            # no outline in the typing/kneading (side) poses — it caused
            # rendering trouble there; just draw the cups cleanly
            if not name.startswith(("type_", "knead_")):
                for (hx, hy) in halo:
                    hp.fillRect(hx * s, hy * s, s, s, whc)
            for (hx, hy) in dcells:
                hp.fillRect(hx * s, hy * s, s, s, dkc)
            for (hx, hy) in lcells:
                hp.fillRect(hx * s, hy * s, s, s, ltc)
            hp.end()

        # guard mode: tactical helmet on the head + flashlight in paw
        if self.mgr.cfg["global"].get("guard_mode", False):
            gp = QPainter(img)
            self._draw_helmet(gp, name, s)
            self._draw_flashlight(gp, name, s)
            gp.end()

        eyes = sprites.EYE_CELLS.get(name)
        if eyes:
            if face_flip:                      # frame mirrored → mirror eyes
                W0 = sprites.GRID_W - 1
                eyes = [(W0 - sprites.EYE_W + 1 - ex, ey) for (ex, ey) in eyes]
            guarding = self.mgr.cfg["global"].get("guard_mode", False)
            power = (self.index == 0
                     and (self.mgr.ai_busy
                          or self.mgr.guide_active
                          or (self.mgr._ask_box is not None
                              and self.mgr._ask_box.isVisible())))
            if self.state == THINK and not power:
                offx, offy = -s // 3, -s // 2
            elif self.state == SCROLLPLAY:
                offx, offy = -(s * 3) // 4, (s * 3) // 4
            elif guarding:
                # patrol gaze: look toward the side the torch points,
                # with a slow scanning drift
                left_side = self._guard_side() == 1
                drift = math.sin(now * 1.7) * (s * 0.3)
                offx = int((-1 if left_side else 1) * (s * 0.7) + drift)
                offy = s // 4
            else:
                cur = QCursor.pos()
                c = self.mapToGlobal(self.cat_rect().center())
                ang = math.atan2(cur.y() - c.y(), cur.x() - c.x())
                f = min(1.0, self._dist_to_cursor(cur) / 300)
                offx = int(round(math.cos(ang) * f * (s * 0.75)))
                offy = int(round(math.sin(ang) * f * (s * 0.75)))
            pal = (sprites.OVERHEAT_PALETTE if self.state == OVERHEAT
                   else self.palette())
            pc = QColor(pal["P"])
            ew_x, ew_y = sprites.EYE_W * s, sprites.EYE_H * s
            pw = 2 * s                     # pupil size (px)
            pp = QPainter(img)
            if power:
                # all-seeing mode: glowing blue eyes while the brain works
                pc = QColor("#3ec8ff")
                pulse = 0.38 + 0.26 * math.sin(now * 6.0)
                halo = QColor("#56d9ff")
                halo.setAlphaF(max(0.0, min(1.0, pulse)))
                pp.setPen(Qt.NoPen)
                pp.setBrush(halo)
                grid = sprites.FRAMES.get(name)
                tint = QColor("#b8ecff")
                for (ex, ey) in eyes:
                    cxp = ex * s + ew_x / 2.0
                    cyp = ey * s + ew_y / 2.0
                    pp.drawEllipse(QPointF(cxp, cyp),
                                   ew_x * 1.15, ew_y * 1.15)
                if grid:
                    W0 = sprites.GRID_W - 1
                    for gy, row in enumerate(grid):
                        for gx, c in enumerate(row):
                            if c == "E":
                                dx = (W0 - gx) if face_flip else gx
                                pp.fillRect(dx * s, gy * s, s, s, tint)
            for (ex, ey) in eyes:
                bx, by = ex * s, ey * s
                px = max(bx, min(bx + offx + (ew_x - pw) // 2, bx + ew_x - pw))
                py = max(by, min(by + offy + (ew_y - pw) // 2, by + ew_y - pw))
                pp.fillRect(px, py, pw, pw, pc)
                if power:                  # white spark in the pupil core
                    pp.fillRect(px + pw // 4, py + pw // 4,
                                max(1, pw // 3), max(1, pw // 3),
                                QColor("#f2ffff"))
            if guarding or self.duck_gunner:
                # ANGRY scowl: thick brow bars sitting ABOVE the eyes, inner
                # ends dipping toward the nose (a hard \  / shape) without
                # covering the pupils. Mirror-correct via eye x.
                brow = QColor("#1e150e")
                bw = sprites.EYE_W + 2          # a bit wider than the eye
                xs = [ex for (ex, ey) in eyes]
                left_ex = min(xs) if xs else 0
                for (ex, ey) in eyes:
                    is_left_eye = (ex == left_ex)
                    for k in range(bw):
                        # outer edge high, inner edge (toward nose) lower
                        step = k if is_left_eye else (bw - 1 - k)
                        bx = (ex - 1 + k) * s
                        # base ~2 cells above the eye so brows sit on the brow
                        # ridge, not on the eyeball
                        by = int((ey - 1.9) * s) + step * (s * 2 // 3)
                        pp.fillRect(bx, by, s, int(s * 1.25), brow)
            pp.end()

        jy = 0
        if now < self.jump_until:
            t = (self.jump_until - now) / 1.2
            jy = -int(abs(math.sin(t * math.pi * 3)) * 18)
        if self.state == CHASE or self.glide_target is not None:
            jy -= int(abs(math.sin(now * 11)) * max(4, self.scale))

        r = self.cat_rect()

        p.save()
        tilt = 0.0
        if self.wobble > 0.5:
            tilt += math.sin(now * 18) * self.wobble
        if getattr(self, "_parachute", False) and self.glide_target is not None:
            # ☂ gentle pendulum swing under the canopy
            tilt += math.sin(now * 2.0) * 6.0
        elif self.state == CHASE or self.glide_target is not None:
            tilt += -9.0 if self.flip else 9.0
        if abs(tilt) > 0.3:
            p.translate(r.center())
            p.rotate(tilt)
            p.translate(-r.center())
        tw_, th_ = r.width(), r.height()
        tx, ty = r.left(), r.top() + jy
        if self.mochi > 1.02:                # mochi: sag down from the paws
            m = self.mochi
            th_ = int(r.height() * m)
            tw_ = int(r.width() / (m ** 0.5))
            tx = r.center().x() - tw_ // 2
            ty = r.top() + jy
        elif self.state == DANCE:            # groove: bounce + sway
            ph = math.sin(time.time() * 2 * math.pi * 1.9)
            th_ = int(r.height() * (0.955 + 0.045 * ph))
            tw_ = int(r.width() * (1.0 + 0.05 * (1.0 - th_ / r.height())))
            tx = r.center().x() - tw_ // 2 \
                + int(math.sin(time.time() * 2 * math.pi * 0.95) * s * 0.8)
            ty = r.top() + jy + (r.height() - th_)
        elif self.state == STRETCH:          # reach up: taller, feet planted
            th_ = int(r.height() * 1.14)
            tw_ = int(r.width() * 0.96)
            tx = r.center().x() - tw_ // 2
            ty = r.top() + jy + (r.height() - th_)
        p.drawImage(QRect(tx, ty, tw_, th_), img)
        p.restore()

        # 🔫 duck-hunt blaster: drawn in screen space, pivoting at the cat's
        # paw and pointing at the cursor (where you're about to shoot).
        if self.duck_gunner:
            cur = QCursor.pos()
            paw = self.mapToGlobal(self.cat_rect().center())
            paw_local = self.cat_rect().center()
            ang = math.atan2(cur.y() - paw.y(), cur.x() - paw.x())
            p.save()
            # pivot well out to the RIGHT of the body so the gun is clearly
            # in front of the cat, not overlapping it
            p.translate(paw_local.x() + int(s * 7.5),
                        paw_local.y() + int(s * 2.5))
            p.rotate(math.degrees(ang))
            gun = QColor("#3a3f47")
            barrel = QColor("#2a2e34")
            tip = QColor("#e8912e")
            # body sits at the pivot; barrel extends along +x (toward cursor)
            p.fillRect(-s * 2, -s, s * 4, s * 2, gun)            # body
            p.fillRect(s * 2, -(s // 2), s * 6, s, barrel)       # barrel
            p.fillRect(s * 8, -(s // 2), s, s, tip)              # muzzle
            p.fillRect(-s, s, s * 2, int(s * 1.8), gun)          # grip
            p.restore()

        # ☂ parachute canopy: drawn level (unrotated) above the cat, so the
        # cat pendulums beneath it. Drawn AFTER restore so the swing tilt
        # doesn't rotate the canopy.
        if getattr(self, "_parachute", False) and self.glide_target is not None:
            self._draw_parachute(p, now)

        # paper roll + unrolling strip — chunky pixel-art style, ON TOP
        if self.state == SCROLLPLAY:
            rx, ry = sprites.SCROLL_ROLL
            cx = r.left() + int((rx + 1.4) * s * self.grow)
            cy = r.top() + int((ry - 2.6) * s * self.grow)
            rr = int(s * 2.4)
            px = max(2, s // 2)              # paper "pixel" size
            paper = QColor("#fbfaf5")
            shade = QColor("#e3ddcf")
            edge = QColor("#4c463e")
            core = QColor("#b8b0a0")
            hole = QColor("#8d8577")
            p.setRenderHint(QPainter.Antialiasing, False)
            p.setPen(Qt.NoPen)
            w2 = int(s * 1.8)
            ln = min(int(self.mgr.inputs.scroll_accum) * 2 + 5 * s,
                     self.height() - cy - rr - 6)
            sway = math.sin(now * 2.2) * min(3.0, s * 0.4)
            top = cy + rr - px               # strip starts under the roll
            if ln > px * 2:
                seg_h = px * 3               # TP squares
                y = top
                i = 0
                while y < top + ln:
                    h = min(seg_h, top + ln - y)
                    off = int(sway * (y - top) / max(ln, 1) * 2)
                    # outline block then paper block inside = crisp border
                    p.fillRect(cx - w2 - px + off, y, (w2 + px) * 2, h,
                               edge)
                    p.fillRect(cx - w2 + off, y, w2 * 2, h, paper)
                    # right-side shading strip for depth
                    p.fillRect(cx + w2 - px + off, y, px, h, shade)
                    # perforation dashes between squares
                    if i > 0:
                        for dx in range(-w2 + px, w2 - px, px * 2):
                            p.fillRect(cx + dx + off, y, px,
                                       max(1, px // 2), shade)
                    y += seg_h
                    i += 1
                # torn end: staggered pixel teeth
                endy = top + ln
                off = int(sway * 2)
                tooth = px
                tx = cx - w2 + off
                k = 0
                while tx < cx + w2 + off:
                    th = tooth if (k % 2 == 0) else tooth * 2
                    p.fillRect(int(tx), endy, tooth, th, edge)
                    p.fillRect(int(tx), endy, tooth, max(1, th - px // 2),
                               paper if k % 2 else shade)
                    tx += tooth
                    k += 1
            # the roll: pixel cylinder with outline, sheet wrap + core
            p.fillRect(cx - rr - px, cy - rr - px, (rr + px) * 2,
                       (rr + px) * 2, edge)
            p.fillRect(cx - rr, cy - rr, rr * 2, rr * 2, paper)
            p.fillRect(cx + rr - px * 2, cy - rr, px * 2, rr * 2, shade)
            # winding line: the sheet's outer edge on the roll
            p.fillRect(cx - rr, cy + rr - px * 2, rr * 2, px, shade)
            # core hole
            ch = max(px * 2, rr // 2)
            p.fillRect(cx - ch // 1 + ch // 2 - ch // 2, cy - ch // 2,
                       ch, ch, core)
            p.fillRect(cx - ch // 4, cy - ch // 4, ch // 2, ch // 2, hole)
            # spinning tick so the roll visibly turns as you scroll
            ang = self.mgr.inputs.scroll_accum * 0.5 + now * 1.2
            mx = cx + int(math.cos(ang) * (rr - px * 1.5))
            my = cy + int(math.sin(ang) * (rr - px * 1.5))
            p.fillRect(mx - px // 2, my - px // 2, px, px, shade)
            p.setRenderHint(QPainter.Antialiasing, True)

        # thinking face: thought dots drifting above the head
        if self.state == THINK:
            p.setPen(Qt.NoPen)
            bx0 = r.center().x() + r.width() // 5
            for i in range(3):
                ph = (now * 1.6 + i * 0.45) % 1.4
                col = QColor("#8a93a3")
                col.setAlphaF(max(0.15, 1.0 - ph / 1.4))
                p.setBrush(col)
                rad = (i + 2) * s * 0.26
                p.drawEllipse(QPointF(bx0 + i * s * 1.2,
                                      r.top() - 6 - i * s * 0.9 - ph * 3),
                              rad, rad)

        p.setFont(QFont("Arial", max(9, s * 2)))
        for h in self.hearts:
            col = QColor("#e56a8a")
            col.setAlphaF(max(0.0, min(1.0, h["life"])))
            p.setPen(col)
            p.drawText(QPointF(h["x"], h["y"]), "♥")
        p.setFont(QFont("Arial", max(8, int(s * 1.6)), QFont.Bold))
        for z in self.zzz:
            col = QColor("#7d8aa5")
            col.setAlphaF(max(0.0, min(1.0, z["life"] / 2)))
            p.setPen(col)
            p.drawText(QPointF(z["x"], z["y"]), "z")
        for nt in self.notes:                      # floating music notes
            col = QColor("#b48ae0")
            col.setAlphaF(max(0.0, min(1.0, nt["life"])))
            p.setPen(col)
            p.drawText(QPointF(nt["x"], nt["y"]),
                       "♪" if int(nt["seed"] * 7) % 2 else "♫")
        p.setPen(Qt.NoPen)
        for st in self.steam:                      # rising steam puffs
            grow_p = 1.0 - max(0.0, min(1.0, st["life"]))
            col = QColor("#ef6a5a")
            col.setAlphaF(max(0.0, min(0.85, st["life"])))
            p.setBrush(col)
            rad = s * (0.45 + grow_p * 0.55)
            p.drawEllipse(QPointF(st["x"], st["y"]), rad, rad)

        # speech bubble (temporary) or pinned note (persistent)
        text, bg, fg = None, QColor(255, 253, 246, 252), QColor("#3a2f26")
        if now < self.bubble_until and self.bubble_text:
            text = self.bubble_text
            if self.bubble_color:
                bg = QColor(self.bubble_color)
                fg = QColor("#ffffff")
        elif self.index == 0 and self.gcfg.get("pinned"):
            text = "📌 " + self.gcfg["pinned"]
        if text:
            maxw = self.width() - 6           # the window is wider now
            fnt = QFont("Arial", 10)
            for pt in (10, 9, 8):             # wrap first; shrink only if huge
                fnt.setPointSize(pt)
                p.setFont(fnt)
                fm = p.fontMetrics()
                br = fm.boundingRect(QRect(0, 0, maxw - 20, 1000),
                                     Qt.TextWordWrap | Qt.AlignLeft, text)
                th = br.height() + 12
                if th <= TOP_MARGIN - 10:
                    break
            tw = min(maxw, br.width() + 20)
            th = min(th, TOP_MARGIN - 10)
            bx = max(2, min(self.width() - tw - 2, r.center().x() - tw // 2))
            by = 3
            path = QPainterPath()
            path.addRoundedRect(bx, by, tw, th, 10, 10)
            tailx = min(max(r.center().x(), bx + 12), bx + tw - 12)
            tail = QPainterPath()
            tail.moveTo(tailx - 6, by + th - 1)
            tail.lineTo(tailx + 6, by + th - 1)
            tail.lineTo(tailx + 1, by + th + 7)
            tail.lineTo(tailx - 1, by + th + 7)
            tail.closeSubpath()
            path = path.united(tail)
            # subtle shadow (limited headroom, so keep it light)
            for off, a in ((3, 22), (1, 30)):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, a))
                p.save(); p.translate(0, off); p.drawPath(path); p.restore()
            border = (QColor(70, 52, 40, 60) if not self.bubble_color
                      or now >= self.bubble_until
                      else QColor(255, 255, 255, 90))
            p.setPen(QPen(border, 1.5))
            p.setBrush(bg)
            p.drawPath(path)
            p.setPen(fg)
            p.drawText(QRect(int(bx + 8), int(by), int(tw - 16), int(th)),
                       Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, text)

        # floating pixel Pomodoro timer next to the cat (primary only)
        if self.index == 0 and self.mgr.pomo_end is not None:
            remaining = max(0, int(self.mgr.pomo_end - now))
            mm, ss = divmod(remaining, 60)
            kind = self.mgr.pomo_kind
            chip = f"{'Focus' if kind == 'focus' else 'Break'} {mm:02d}:{ss:02d}"
            p.setFont(QFont("Consolas", 8, QFont.Bold))
            fm = p.fontMetrics()
            cw = fm.horizontalAdvance(chip) + 10
            chh = fm.height() + 4
            cx0, cy0 = 2, self.height() - chh - 2
            p.setPen(QColor("#1e3b1e") if kind != "focus" else QColor("#5c1512"))
            p.setBrush(QColor("#4caf50") if kind != "focus"
                       else QColor("#e05a4e"))
            p.drawRoundedRect(cx0, cy0, cw, chh, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(cx0, cy0, cw, chh), Qt.AlignCenter, chip)
        p.end()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sondercat_gray.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    mgr = Manager(app)
    if PLATFORM_NOTE == "wayland":
        mgr.say_primary("Pure Wayland session: some tricks are limited — "
                        "an X11/Xorg login gives me superpowers!", 8)
    else:
        mgr.say_primary("nyang! 🐾", 3)
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _fatal("SondeR cat crashed while starting.",
               traceback.format_exc())
        sys.exit(1)
