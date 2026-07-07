#!/usr/bin/env python3
"""Rebuild SondeR_cat_setup.exe: compiled setup_stub.exe + zip payload.
Cross-compile the stub first (Linux):
  x86_64-w64-mingw32-gcc -municode -mwindows -Os -s -static \
      -o setup_stub.exe setup_stub.c miniz/miniz.c miniz/miniz_zip.c \
      miniz/miniz_tinfl.c miniz/miniz_tdef.c -I miniz -luser32 -lshell32
"""
import io, zipfile, struct

FILES = ["sondercat.py", "sprites.py", "sonder_agent.py", "requirements.txt",
         "install.bat", "debug.bat", "run.bat", "run.sh", "install.sh",
         "README.md", "sondercat.ico", "meow.wav"]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(f, f"sondercat/{f}")
zdata = buf.getvalue()
stub = open("setup_stub.exe", "rb").read()
open("SondeR_cat_setup.exe", "wb").write(
    stub + zdata + struct.pack("<Q", len(zdata)) + b"SNDRCAT1")
print("built SondeR_cat_setup.exe")
