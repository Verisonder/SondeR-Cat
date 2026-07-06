#!/usr/bin/env python3
"""
sonder_agent.py — tell SondeR cat what your AI agent is doing.

The cat watches ~/.sondercat_agent. Write "working|Label" while an agent
runs and "done|Label" when it finishes; the cat "thinks along" and does a
happy jump when work completes.

Usage:
  python sonder_agent.py working [label]      # cat starts thinking along
  python sonder_agent.py done    [label]      # cat celebrates
  python sonder_agent.py clear                # reset

  # Wrap ANY command (Codex CLI, aider, scripts, builds, tests...):
  python sonder_agent.py run [label] -- <command> [args...]
  e.g.  python sonder_agent.py run "Codex" -- codex "fix the tests"
        python sonder_agent.py run "Build" -- npm run build

For Claude Code, use hooks instead (see README.md).
"""

import os
import subprocess
import sys

AGENT_FILE = os.path.join(os.path.expanduser("~"), ".sondercat_agent")


def write(text):
    with open(AGENT_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 1
    cmd = argv[0].lower()

    if cmd in ("working", "done"):
        label = argv[1] if len(argv) > 1 and argv[1] != "--" else "Agent"
        write(f"{cmd}|{label}")
        return 0

    if cmd == "clear":
        write("")
        return 0

    if cmd == "run":
        rest = argv[1:]
        label = "Agent"
        if rest and rest[0] != "--":
            label = rest.pop(0)
        if rest and rest[0] == "--":
            rest.pop(0)
        if not rest:
            print("run: no command given after --")
            return 1
        write(f"working|{label}")
        try:
            code = subprocess.call(rest)
        finally:
            write(f"done|{label}")
        return code

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
