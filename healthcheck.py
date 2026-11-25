import os, sys, traceback

app = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
libs = os.path.join(app, "libs")
sys.path.insert(0, libs)

print("python  :", sys.version)
print("exe     :", sys.executable)
print("bits    :", 64 if sys.maxsize > 2**32 else 32)
print("libs    :", libs, "exists" if os.path.isdir(libs) else "MISSING")
print("PATH has WindowsApps:", "WindowsApps" in os.environ.get("PATH", ""))

failed = False
for mod in ("six", "pynput.keyboard", "pynput.mouse", "shiboken6",
            "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
            "pynput.keyboard", "pynput.mouse"):
    try:
        __import__(mod)
        print("ok     ", mod)
    except BaseException:
        failed = True
        print("FAILED ", mod)
        traceback.print_exc()
        sys.stdout.flush()
sys.exit(1 if failed else 0)
