#!/usr/bin/env python3
"""Build SondeR_cat_setup.exe — the ONLINE installer.

This exe carries NO app payload: at install time it downloads the latest
repo zip from GitHub and unpacks it. That means it NEVER needs rebuilding
for app changes — its hash stays permanently stable so Smart App Control /
SmartScreen reputation can accumulate. Rebuild ONLY if setup_stub.* change.

Needs mingw-w64:  apt install gcc-mingw-w64-x86-64 binutils-mingw-w64-x86-64
and miniz sources in ./miniz or /home/claude/miniz-master.
"""
import subprocess, os

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
sz = os.path.getsize("SondeR_cat_setup.exe")
print(f"built SondeR_cat_setup.exe (online installer, {sz//1024} KB)")
