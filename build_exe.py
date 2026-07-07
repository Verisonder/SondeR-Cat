#!/usr/bin/env python3
"""Build SondeR_cat_setup.exe: payload as an RCDATA resource (no overlay).
Needs mingw-w64:  apt install gcc-mingw-w64-x86-64 binutils-mingw-w64-x86-64
and miniz sources in ./miniz or /home/claude/miniz-master.
"""
import io, zipfile, subprocess, os, sys

FILES = ["sondercat.py", "sprites.py", "sonder_agent.py", "requirements.txt",
         "install.bat", "debug.bat", "run.bat", "run.sh", "install.sh",
         "README.md", "ANIMATIONS.md", "sondercat.ico", "meow.wav"]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(f, f"sondercat/{f}")
    nlibs = 0
    for root, _dirs, files in os.walk("libs"):
        for fn in files:
            p = os.path.join(root, fn)
            z.write(p, p.replace(os.sep, "/"))
            nlibs += 1
    assert nlibs > 100, "libs/ tree missing — extract wheels first"
open("payload.zip", "wb").write(buf.getvalue())
print(f"payload: {len(FILES)} app files + {nlibs} bundled library files")

mz = "miniz" if os.path.isdir("miniz") else "/home/claude/miniz-master"
subprocess.check_call(["x86_64-w64-mingw32-windres", "setup_stub.rc",
                       "-O", "coff", "-o", "setup_stub_res.o"])
subprocess.check_call(["x86_64-w64-mingw32-gcc", "-municode", "-mwindows",
    "-Os", "-s", "-static", "-o", "SondeR_cat_setup.exe",
    "setup_stub.c", "setup_stub_res.o",
    f"{mz}/miniz.c", f"{mz}/miniz_zip.c", f"{mz}/miniz_tinfl.c",
    f"{mz}/miniz_tdef.c", "-I", mz,
    "-luser32", "-lshell32", "-lcomctl32", "-lole32", "-luuid",
    "-lurlmon", "-ladvapi32"])
os.remove("payload.zip")
print("built SondeR_cat_setup.exe (resource payload)")
