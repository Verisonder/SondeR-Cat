# SondeR cat 🐾

A pixel cat that lives on your desktop — naps on your windows, vibes to your music, and can even answer questions with a Gemini brain.
For **Windows** and **Linux**. Free, open source, no telemetry, no accounts.

![SondeR cats](assets/preview.png)

## Features

**Reacts to you**
- 👀 **Eye follow** — pupils track your cursor anywhere on screen
- 🔴 **Laser hunt** — wiggle the cursor side-to-side like a laser dot and the cat gallops after it (adjustable sensitivity); wiggle up-down at the bottom edge to send it to hide
- 🐾 **Purring pets** — rub its head with the mouse → hearts + "purrr…"
- 🍡 **Mochi drag** — grab it and it hangs from your cursor by its paws, stretching like mochi as you swing it; shake for wobble
- 😾 **Startle** — buzz the cursor past it and it jumps
- ⌨️ **Keyboard kneading** — types along with you on tiny 3D keycaps, stops the moment you do
- 🔥 **Overheat mode** — type too fast and the whole cat turns red with steam puffing over its head
- 📜 **Paper unroll** — scroll and it unspools a paper roll with a torn edge

**Being a good coworker**
- 😴 Naps when you're idle; wakes with a "mrrp?"
- 🪟 **Climbs on your windows** — occasionally walks over and sits on top of an open window, riding along if you move it. It even naps up there, grumbles if you shake the window, and slides down if you minimize it (toggleable)
- 💤 **Deep sleep** toggle — sleeps until YOU say otherwise; nothing wakes it
- 🫣 **Hide at the bottom** — tuck the cat away at the screen edge, or wiggle your cursor up-down at the bottom to send it there. It stays hidden — ignoring typing, scrolling and mouse wiggles — until you **click** it, then it stands up right where it is
- 📺 Also auto-hides during fullscreen video
- 🎧 **Listens to your music** — when any sound plays, the cat puts on little pixel headphones and vibes along with whatever it's doing. Flip on *Dance + music notes* and it bounces to the beat with floating ♪♫
- 🧘 **Stretch reminders** every 30/50/90 min — or set your own interval
- 🍅 **Pomodoro** — focus/break **loops** with a pixel timer floating next to the cat; custom focus/break lengths too
- ⏰ **Message reminders** — pick a clock time or a countdown with a real time-spinner, and the cat meows to remind you
- 📌 **Pinned note** — keep an important message above its head
- 🗣️ **Tell it your name** — it calls you by name in reminders and breaks

**🧠 Ask your cat anything (Gemini AI)**
- Give the cat a name, paste a free **Google Gemini API key**, and press **Ctrl+Space** anywhere
- A little pixel speech-bubble opens above the cat — type your question and it answers *as your cat, by name*, remembering the conversation
- Its eyes glow an all-seeing electric blue while it thinks 🔵
- Your key is stored only on your PC and sent nowhere but Google

**AI agent reactions** (Claude Code, Codex CLI, or any command)
- 🤔 **Thinking along** — thought bubbles + upward gaze while your agent works
- 🎉 **Agent done jump** — happy hop + meow when the task finishes
- Hook up via `sonder_agent.py` (wrap any command) or Claude Code hooks — see below

**Make it yours**
- 🐱 **Real-cat themes** — one-click looks modeled on real cats: **Lilly** (orange, white chest), **JJ** (striped tabby, green eyes), **Mimi** (lynx-point, blue eyes), with more to come
- 🎨 10 fur colors + any custom color, patterns (tabby / solid / tuxedo / spots / siamese), and **custom eye color** (presets or any color you pick)
- 🐈🐈 **Multiple cats**, each with its own name, look and eyes
- 📏 7 sizes from tiny 2× to chunky 10×; positions and settings remembered
- 🔄 **Updates itself** — new versions install automatically in the background (toggleable); the installer never changes

## Install

> **Requires 64-bit Windows 10/11** (or Linux). 32-bit systems can't run the Qt6 framework the cat is built on.

### Windows — one tiny installer

**[Download SondeR_cat_setup.exe](https://github.com/Verisonder/SondeR-Cat/raw/main/SondeR_cat_setup.exe)** (140 KB) and double-click it.

A small graphical installer (no terminal, ever) does the rest:
- downloads the **latest** version of the cat straight from this repo and
  unpacks it — always current, the moment you install
- if your PC has no Python at all, it fetches that one piece automatically
  (via Windows' package manager)
- creates a Desktop shortcut with the cat icon, offers start-with-Windows,
  and launches your cat

Because the installer carries no app code of its own, **it never changes** —
which lets Windows' reputation systems gradually learn to trust it. After the
first install, the cat keeps **itself** up to date automatically.

SmartScreen may warn about a new app — click *More info → Run anyway*. The
installer's full source code is right here in this repo (`setup_stub.c`),
built by `build_exe.py`.

**If Smart App Control / antivirus blocks the exe** (or you just prefer no
exe): click the green **Code** button above → **Download ZIP** → right-click
the downloaded zip → *Properties* → tick **Unblock** → OK → *Extract All* →
double-click **`CLICK_ME_TO_INSTALL.bat`**. Everything is included in the
zip — no pip, no downloads — and it only runs Windows' own signed programs,
so it works even where the exe is blocked.

### Linux

```bash
git clone https://github.com/Verisonder/SondeR-Cat.git
cd SondeR-Cat && ./install.sh
```

`install.sh` detects your package manager (apt / dnf / pacman / zypper /
apk), checks system libraries, and offers to fix anything missing.

Requires Python 3.9+ · Dependencies: PySide6 (Essentials), pynput

### Code signing

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

## Hooking up AI agents

The cat watches `~/.sondercat_agent`. Write `working|Label` while an agent
runs and `done|Label` when it finishes.

Wrap any command:
```bash
python sonder_agent.py run "Codex" -- codex "fix the failing tests"
```

Claude Code hooks (`~/.claude/settings.json`):
```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command",
        "command": "python /path/to/sonder_agent.py working \"Claude Code\"" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command",
        "command": "python /path/to/sonder_agent.py done \"Claude Code\"" } ] }
    ]
  }
}
```


## Linux support

| Environment | Status |
|---|---|
| **X11 / Xorg** (any distro) | ✅ Everything works |
| **Wayland with XWayland** (default on Ubuntu, Fedora, etc.) | ✅ Auto-detected — the cat routes itself through XWayland for full features |
| **Pure Wayland** (no XWayland) | ⚠️ Runs, but global cursor tracking / hooks / self-positioning are restricted by Wayland's security model — the cat tells you at startup |
| **GNOME** | ✅ Note: GNOME hides system trays — just right-click the *cat* for the full menu |

Tested package managers: **apt** (Debian/Ubuntu/Mint), **dnf** (Fedora),
**pacman** (Arch), **zypper** (openSUSE), **apk** (Alpine). `install.sh`
detects yours, checks for the Qt system libraries (`xcb-cursor`,
`xkbcommon-x11`, GL), and offers to install anything missing with the right
command for your distro. If the window ever fails to open:

```bash
# Debian/Ubuntu        sudo apt install libxcb-cursor0 libgl1 libxkbcommon-x11-0 libegl1
# Fedora               sudo dnf install xcb-util-cursor libxkbcommon-x11
# Arch                 sudo pacman -S xcb-util-cursor libxkbcommon-x11
# openSUSE             sudo zypper install libxcb-cursor0 libxkbcommon-x11-0
# Alpine               sudo apk add xcb-util-cursor mesa-gl libxkbcommon
```

## Troubleshooting

- **The graphical installer failed** → it saves logs you can send to the
  developer: `%TEMP%\SondeRcat_setup.log` (steps) and
  `%TEMP%\SondeRcat_pip.log` (component details). Paste `%TEMP%` into the
  Explorer address bar to get there.
- **Shortcut does nothing** → run `debug.bat` from the install folder
  (`%LOCALAPPDATA%\SondeRcat\sondercat`) to see the error; crashes are also
  logged to `sondercat_error.log` in your home folder.
- **No reaction to scrolling** → right-click the cat → *Behavior → Scroll
  doctor* runs a 5-second live test and tells you whether global mouse hooks
  are being blocked (usually antivirus). Scrolling while hovering the cat
  always works.
- **Linux** — see the support matrix above; `install.sh` diagnoses most
  issues, and the app prints exact package commands if display libraries
  are missing.

## Customizing the art

Every animation frame is a plain-text pixel grid in `sprites.py` — one
character per pixel, **live-editable**: right-click the cat → *Animations →
Open animations file*, tick *Auto-reload on save*, and the cat updates the
moment you hit Ctrl+S. Bad edits can't crash it — they're rejected with a
message telling you exactly which line to fix.

**Full guide: [ANIMATIONS.md](ANIMATIONS.md)**

## Support SondeR cat 💛

SondeR cat is free and always will be. If it brightens your desktop and you'd
like to help it grow, you can chip in:

- ❤️ **[GitHub Sponsors](https://github.com/sponsors/Verisonder)**
- ☕ Or use the **Sponsor** button at the top of the repo

Every bit is appreciated and goes straight into building more cat. 🐾

## Using this project / credit 📜

SondeR cat is open source under **Apache-2.0**, and it's the original work of
**Verisonder**. You're very welcome to use it, learn from it, and build on it —
with three simple, legally-binding conditions (see `LICENSE` and `NOTICE`):

- ✅ **Keep the credit** — leave the copyright and `NOTICE` in place
- 🚫 **Don't claim it as your own** — don't pass SondeR cat off as something you
  created; if you build on it, say it's based on SondeR cat by Verisonder
- 🚫 **Don't imply endorsement** — the *SondeR cat* name and the cat characters
  (Lilly, JJ, Mimi) are the author's; name them only to credit the origin

Want to do something beyond that? Just ask first. 🐾

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Free to use with attribution; you may not claim it as your own or imply the author's endorsement.
