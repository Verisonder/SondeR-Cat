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
                               QPainterPath, QPixmap)
    from PySide6.QtWidgets import (QApplication, QColorDialog, QInputDialog,
                                   QMenu, QMessageBox, QSystemTrayIcon,
                                   QWidget)
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
APP_VERSION = "2.9.0"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".sondercat.json")
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
                   "window_perch": True}

(IDLE, KNEAD, SLEEP, CHASE, DRAG, STRETCH,
 OVERHEAT, SCROLLPLAY, PEEK, THINK) = range(10)


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
        self.key_times = deque(maxlen=80)
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
        except Exception:
            pass

    def _on_press(self, key):
        try:
            if key in self._down:
                return                 # OS auto-repeat while held: count once
            self._down.add(key)
            if len(self._down) > 24:   # safety net for missed releases
                self._down.clear()
        except Exception:
            pass
        now = time.time()
        self.last_key = now
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
        return (rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)

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


# ---------------------------------------------------------------- manager ----

class _InputBridge(QObject):
    poked = Signal()


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
        QTimer.singleShot(20000, lambda: self.check_updates(manual=False))
        self.sprites_reloads = 0
        self._watch = None
        self._watch_timer = None
        if self.cfg["global"].get("watch_sprites"):
            QTimer.singleShot(500, self._start_watch)
        self._bridge = _InputBridge()
        self._bridge.poked.connect(self._on_input_event)
        self.inputs = InputWatcher(on_event=self._bridge.poked.emit)
        self.fs_detect = FullscreenDetector()
        self.meow = Meow()

        self.fullscreen_active = False
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

        # fullscreen (auto-peek)
        self.fullscreen_active = (self.cfg["global"]["auto_peek"]
                                  and self.fs_detect.check())

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

    def check_updates(self, manual=True):
        """Runs in a worker thread; UI messages go through the bridge."""
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
                if not getattr(self, "first_run", False):
                    ui(lambda: self.say_primary(
                        f"{label} is available! menu → Check for updates",
                        6))
                    return
                # first run after a fresh install: bring it fully current
                ui(lambda: self.say_primary(
                    "getting the freshest version… ⤓", 6))
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

    def toggle_window_perch(self):
        g = self.cfg["global"]
        g["window_perch"] = not g.get("window_perch", True)
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

    def add_reminder(self):
        when, ok = QInputDialog.getText(
            None, "Set a reminder",
            "When?  (a time like 21:30, or minutes from now like 45)")
        if not ok or not when.strip():
            return
        t = self.parse_when(when)
        if t is None:
            self.say_primary("I didn't understand that time…", 3)
            return
        msg, ok = QInputDialog.getText(None, "Set a reminder",
                                       "What should I say?")
        if not ok or not msg.strip():
            return
        self.cfg["global"].setdefault("reminders", []).append([t, msg.strip()])
        save_config(self.cfg)
        mins = max(1, int((t - time.time()) / 60))
        self.say_primary(f"Okay! I'll meow in ~{mins} min", 3)

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
        self.pet_accum = 0.0
        self.last_pet_heart = 0.0
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
        self.next_perch_try = time.time() + random.uniform(120, 360)
        self._perch_miss = 0
        self._perch_hist = deque(maxlen=40)
        self._shake_quiet_until = 0.0
        self._shake_strikes = 0
        self._falling = False
        self._cover_miss = 0
        self.perch_asleep = False
        self.wobble = 0.0
        self._last_drag_x = 0
        self._last_drag_dir = 0

        # smooth movement (float position)
        self._fx = self._fy = 0.0
        self.chase_cooldown = time.time() + random.uniform(0, 3)
        self.prev_cursor = QCursor.pos()
        self.prev_tick_t = time.time()
        self.cursor_speed = 0.0

        # peek
        self.manual_peek = False
        self.peeking = False
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
        thm = cust.addMenu("Themes ✨")
        lil = QAction("Lilly 🧡", menu)
        lil.setCheckable(True)
        lil.setChecked(self.ccfg["palette"] == "lilly")
        lil.triggered.connect(lambda _=False: self.set_palette("lilly"))
        thm.addAction(lil)
        jjt = QAction("JJ 💚", menu)
        jjt.setCheckable(True)
        jjt.setChecked(self.ccfg["palette"] == "jj")
        jjt.triggered.connect(lambda _=False: self.set_palette("jj"))
        thm.addAction(jjt)
        more = QAction("more coming…", menu)
        more.setEnabled(False)
        thm.addAction(more)

        fur = cust.addMenu("Fur color")
        for name in sprites.PALETTES:
            if name in ("lilly", "jj"):
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

        pomo = menu.addMenu("Pomodoro")
        for label, mins, kind in (("Focus 25 min", 25, "focus"),
                                  ("Focus 50 min", 50, "focus"),
                                  ("Break 5 min", 5, "break")):
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, m=mins, k=kind:
                                  mgr.start_pomodoro(m, k))
            pomo.addAction(act)
        for label, f, b in (("Loop 25 / 5", 25, 5), ("Loop 50 / 10", 50, 10)):
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, ff=f, bb=b:
                                  mgr.start_pomodoro(ff, "focus", loop=(ff, bb)))
            pomo.addAction(act)
        stop = QAction("Stop timer", menu)
        stop.triggered.connect(mgr.stop_pomodoro)
        pomo.addAction(stop)

        stretch = menu.addMenu("Stretch reminder")
        for label, mins in (("Every 30 min", 30), ("Every 50 min", 50),
                            ("Every 90 min", 90), ("Off", 0)):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(self.gcfg["stretch_minutes"] == mins)
            act.triggered.connect(lambda _=False, m=mins: mgr.set_stretch(m))
            stretch.addAction(act)

        beh = menu.addMenu("Behavior")
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
        prc = QAction("Sometimes sit on top of windows 🪟", menu)
        prc.setCheckable(True)
        prc.setChecked(self.gcfg.get("window_perch", True))
        prc.triggered.connect(mgr.toggle_window_perch)
        beh.addAction(prc)
        snd = QAction("Meow sounds", menu)
        snd.setCheckable(True)
        snd.setChecked(self.gcfg.get("sounds", True))
        snd.triggered.connect(mgr.toggle_sounds)
        beh.addAction(snd)
        auto = QAction("Auto-hide during fullscreen video", menu)
        auto.setCheckable(True)
        auto.setChecked(self.gcfg["auto_peek"])
        auto.triggered.connect(mgr.toggle_auto_peek)
        beh.addAction(auto)
        manual = QAction("Come back out" if self.manual_peek
                         else "Hide at the bottom now", menu)
        manual.triggered.connect(self.toggle_manual_peek)
        beh.addAction(manual)

        agent = menu.addMenu("AI agent reactions")
        info = QAction("How to hook up (see README)", menu)
        info.triggered.connect(self.show_agent_help)
        agent.addAction(info)
        t1 = QAction("Test: agent working", menu)
        t1.triggered.connect(lambda: self._write_agent("working|Test agent"))
        agent.addAction(t1)
        t2 = QAction("Test: agent done", menu)
        t2.triggered.connect(lambda: self._write_agent("done|Test agent"))
        agent.addAction(t2)

        msgs = menu.addMenu("Messages")
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

        anim = menu.addMenu("Animations")
        aopen = QAction("Open animations file (sprites.py)…", menu)
        aopen.triggered.connect(mgr.open_sprites)
        anim.addAction(aopen)
        areload = QAction("Reload animations now", menu)
        areload.triggered.connect(lambda _=False: mgr.do_reload_sprites())
        anim.addAction(areload)
        awatch = QAction("Auto-reload on save", menu)
        awatch.setCheckable(True)
        awatch.setChecked(self.gcfg.get("watch_sprites", False))
        awatch.triggered.connect(mgr.toggle_watch_sprites)
        anim.addAction(awatch)

        about = QAction("About", menu)
        about.triggered.connect(self.show_about)
        menu.addAction(about)
        upd = QAction("Check for updates ⤓", menu)
        upd.triggered.connect(lambda _=False: mgr.check_updates(manual=True))
        menu.addAction(upd)
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
                            ("Peek pose", "peek")):
            act = QAction(label, menu)
            act.triggered.connect(
                lambda _=False, k=kind: mgr.start_anim_test(k))
            tst.addAction(act)
        wtest = QAction("Walk onto a window 🪟", menu)
        wtest.triggered.connect(
            lambda _=False: mgr.primary().try_perch(announce=True))
        tst.addAction(wtest)
        tst.addSeparator()
        doctor = QAction("Scroll doctor (5s live test)", menu)
        doctor.triggered.connect(mgr.scroll_doctor)
        tst.addAction(doctor)

        slp = QAction("Deep sleep 💤", menu)
        slp.setCheckable(True)
        slp.setChecked(self.gcfg.get("force_sleep", False))
        slp.triggered.connect(mgr.toggle_force_sleep)
        menu.addAction(slp)
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
        if name in ("lilly", "jj"):
            self.ccfg["pattern"] = name      # theme cats bring their pattern
        save_config(self.mgr.cfg)
        self._frame_cache = {}
        if self.index == 0:
            self.mgr._make_tray()
        self.say({"lilly": "Lilly! 🧡", "jj": "JJ! 💚"}.get(
            name, f"New fur: {name}!"))

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
                self._wigv_times.append(now)
            self._wigv_dir = dirv
        while self._wigv_times and now - self._wigv_times[0] > 1.5:
            self._wigv_times.popleft()
        # wiggle up-down near the bottom edge -> the cat goes to hide
        if self.gcfg.get("wiggle_hide", True) and not self.dragging \
                and not self.peeking and now > self._hide_wig_cd:
            scr_c = QGuiApplication.screenAt(cur) \
                or QGuiApplication.primaryScreen()
            if (cur.y() > scr_c.geometry().bottom() - 90
                    and len(self._wigv_times) >= flips_req):
                self._wigv_times.clear()
                self._hide_wig_cd = now + 4.0
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

        # deep sleep: stays asleep no matter what, until toggled off
        if self.gcfg.get("force_sleep"):
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

        want_peek = self.manual_peek or mgr.fullscreen_active
        typing_now = inputs.typing(0.30 if self.knead_hyst else 0.25)
        self.knead_hyst = typing_now
        overheat = (inputs.keys_per_sec() > 5.5 and typing_now)

        # --- startle ---
        d_cur = self._dist_to_cursor(cur)
        if (self.state == IDLE and d_cur < 130 and self.cursor_speed > 3200
                and now > self.startle_cooldown):
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
        if now < mgr.stretch_until:
            self.state = STRETCH
            pass
        elif overheat:
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
        elif (inputs.scrolling()
              and inputs.last_scroll >= inputs.last_key):
            if self.state != SCROLLPLAY and now - self.last_scroll_say > 10:
                self.last_scroll_say = now
                self.say("paper!!", 1.2)
            self.state = SCROLLPLAY
        elif typing_now:
            self.state = KNEAD
        elif inputs.scrolling():
            if self.state != SCROLLPLAY and now - self.last_scroll_say > 10:
                self.last_scroll_say = now
                self.say("paper!!", 1.2)
            self.state = SCROLLPLAY
        elif self.state == CHASE:
            self._chase_step(cur, now, dt)
        elif start_chase:
            if self.perch_hwnd is not None:
                self._end_perch(go_home=False)
            self.state = CHASE
            self._wig_times.clear()
            self.glide_target = None
            if self.peeking:                 # hunt straight from the edge
                self.peeking = False
                self._saved_pos = None
            self.manual_peek = False         # done hiding once we're playing
            self._sync_float()
            self.say("!", 1)
        elif want_peek:
            if not self.peeking:
                self._peek()
            self.state = PEEK
        elif mgr.agent_working:
            self.state = THINK
            if self.index == 0 and now > self.next_think_bubble:
                self.next_think_bubble = now + random.uniform(6, 12)
                self.say(random.choice(["…", "thinking along…", "hmmm",
                                        f"go {mgr.agent_label}!"]), 1.8)
        elif now > self.sleep_at:
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
            if now > self.next_groom and now > self.groom_until:
                self.groom_until = now + 2.6
                self.next_groom = now + random.uniform(30, 80)
            if (self.gcfg.get("window_perch", True)
                    and now > self.next_perch_try
                    and self.perch_hwnd is None
                    and self.perch_pending is None
                    and self.glide_target is None
                    and not self.peeking
                    and not mgr.fullscreen_active):
                self.next_perch_try = now + random.uniform(180, 420)
                self.try_perch()

        if self.state != PEEK and self.peeking:
            self._unpeek(cancel=True)
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
        scr = self.screen() or QGuiApplication.primaryScreen()
        g = scr.geometry()
        x = max(g.left(), min(self.x(), g.right() - self.width()))
        self._glide_to(QPoint(x, g.bottom() - self.height() + 1))

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
                self._unpeek()
                return
            self.dragging = True
            self.glide_target = None
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
                if self.pet_accum > 14 and now - self.last_pet_heart > 0.45:
                    self.last_pet_heart = now
                    self.pet_accum = 0
                    r = self.cat_rect()
                    self.hearts.append({
                        "x": r.left() + random.randint(20, r.width() - 20),
                        "y": r.top() + 8, "vy": 1.1, "life": 1.6,
                        "seed": random.random() * 6})
                    if random.random() < 0.3:
                        self.say(random.choice(["purrr…", "prrrp", "♥"]), 1.2)
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
            try:
                g = self._ground_point()
                if abs(g.y() - self.y()) > 4 or abs(g.x() - self.x()) > 4:
                    self._glide_to(g, speed=300)
            except Exception:
                pass
            self.sleep_at = time.time()
            self.next_perch_try = time.time() + random.uniform(240, 480)
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

    def _fall_off(self, now):
        self._end_perch(go_home=False)
        try:
            self._glide_to(self._ground_point(), speed=1900)  # drop!
            self._falling = True
        except Exception:
            pass
        self.next_perch_try = now + random.uniform(240, 480)

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
            self.wobble = max(self.wobble, 3.0)
            self.say(random.choice(["oouch!!", "oof.", "😾 rude.",
                                    "I meant to do that."]), 2.2)
        if self.perch_pending is not None and self.glide_target is None:
            self.perch_hwnd = self.perch_pending
            self.perch_pending = None
            self.perch_until = now + random.uniform(90, 240)
            self._shake_strikes = 0
            self._cover_miss = 0
            if random.random() < 0.5:
                # nap half: commits to sleeping until physically disturbed
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
            self.next_perch_try = now + random.uniform(180, 420)
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
                self.next_perch_try = now + random.uniform(180, 420)
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
            self.next_perch_try = now + random.uniform(180, 420)

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
            return "type_a" if fast else "type_b"
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
            grid = sprites.apply_pattern(base, self.ccfg["pattern"])
            pal = sprites.OVERHEAT_PALETTE if hot else self.palette()
            img = sprites.render_frame(grid, pal, self.scale, flip)
            self._frame_cache[key] = img
        return img

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        now = time.time()
        s = self.scale

        name = self._frame_name()
        hot = (self.state == OVERHEAT)
        img = self._frame_image(name, False, hot).copy()

        eyes = sprites.EYE_CELLS.get(name)
        if eyes:
            if self.state == THINK:
                offx, offy = -s // 3, -s // 2
            elif self.state == SCROLLPLAY:
                offx, offy = -(s * 3) // 4, (s * 3) // 4
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
            for (ex, ey) in eyes:
                bx, by = ex * s, ey * s
                px = max(bx, min(bx + offx + (ew_x - pw) // 2, bx + ew_x - pw))
                py = max(by, min(by + offy + (ew_y - pw) // 2, by + ew_y - pw))
                pp.fillRect(px, py, pw, pw, pc)
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
        if self.state == CHASE or self.glide_target is not None:
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
        elif self.state == STRETCH:          # reach up: taller, feet planted
            th_ = int(r.height() * 1.14)
            tw_ = int(r.width() * 0.96)
            tx = r.center().x() - tw_ // 2
            ty = r.top() + jy + (r.height() - th_)
        p.drawImage(QRect(tx, ty, tw_, th_), img)
        p.restore()

        # paper roll + unspooling strip, drawn ON TOP so it's always visible
        if self.state == SCROLLPLAY:
            rx, ry = sprites.SCROLL_ROLL
            cx = r.left() + int((rx + 1.4) * s * self.grow)
            cy = r.top() + int((ry - 2.0) * s * self.grow)
            rr = int(s * 2.2)
            ln = min(int(self.mgr.inputs.scroll_accum) * 2 + 4 * s,
                     self.height() - cy - 6)
            paper = QColor("#f7f5ef")
            edge = QColor("#5a5148")
            w2 = int(s * 1.6)
            zig = max(3, s // 2)
            sway = math.sin(now * 2.6) * min(4, s * 0.5)
            if ln > 2:
                path = QPainterPath()
                path.moveTo(cx - w2, cy)
                path.lineTo(cx - w2 + sway, cy + ln)
                x = cx - w2
                up = True
                while x < cx + w2:
                    x2 = min(x + zig, cx + w2)
                    path.lineTo((x + x2) / 2 + sway,
                                cy + ln + (zig if up else 0))
                    path.lineTo(x2 + sway, cy + ln)
                    x = x2
                    up = not up
                path.lineTo(cx + w2, cy)
                path.closeSubpath()
                p.setPen(edge)
                p.setBrush(paper)
                p.drawPath(path)
                p.setPen(QColor("#ddd8cc"))
                for i, ly in enumerate(range(cy + 6, cy + ln - 3, 7)):
                    off = sway * (ly - cy) / max(ln, 1)
                    p.drawLine(int(cx - w2 + 3 + off), ly,
                               int(cx + w2 - 3 + off), ly)
            p.setPen(edge)
            p.setBrush(paper)
            p.drawEllipse(QPoint(cx, cy), rr, rr)
            p.setBrush(QColor("#dcd6c8"))
            p.drawEllipse(QPoint(cx, cy), int(rr * 0.45), int(rr * 0.45))
            # a mark that spins as you scroll
            ang = self.mgr.inputs.scroll_accum * 0.35 + now * 0.8
            mx = cx + int(math.cos(ang) * rr * 0.72)
            my = cy + int(math.sin(ang) * rr * 0.72)
            p.setBrush(QColor("#c9c2b2"))
            p.drawEllipse(QPoint(mx, my), max(2, s // 3), max(2, s // 3))

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
        p.setPen(Qt.NoPen)
        for st in self.steam:                      # rising steam puffs
            grow_p = 1.0 - max(0.0, min(1.0, st["life"]))
            col = QColor("#ef6a5a")
            col.setAlphaF(max(0.0, min(0.85, st["life"])))
            p.setBrush(col)
            rad = s * (0.45 + grow_p * 0.55)
            p.drawEllipse(QPointF(st["x"], st["y"]), rad, rad)

        # speech bubble (temporary) or pinned note (persistent)
        text, bg, fg = None, QColor(255, 253, 246, 235), QColor("#40342a")
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
                br = fm.boundingRect(QRect(0, 0, maxw - 18, 1000),
                                     Qt.TextWordWrap | Qt.AlignCenter, text)
                th = br.height() + 10
                if th <= TOP_MARGIN - 10:
                    break
            tw = min(maxw, br.width() + 18)
            th = min(th, TOP_MARGIN - 10)
            bx = max(2, min(self.width() - tw - 2, r.center().x() - tw // 2))
            by = 2
            path = QPainterPath()
            path.addRoundedRect(bx, by, tw, th, 8, 8)
            path.moveTo(r.center().x() - 5, by + th)
            path.lineTo(r.center().x() + 5, by + th)
            path.lineTo(r.center().x(), by + th + 6)
            path.closeSubpath()
            p.setPen(QColor("#40342a") if not self.bubble_color
                     or now >= self.bubble_until else QColor("#7e1408"))
            p.setBrush(bg)
            p.drawPath(path)
            p.setPen(fg)
            p.drawText(QRect(int(bx), int(by), int(tw), int(th)),
                       Qt.AlignCenter | Qt.TextWordWrap, text)

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
