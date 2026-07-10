import sprites, os
SC=set(".KBSWENMZHGgOP");W,H=sprites.GRID_W,sprites.GRID_H;F=sprites.FRAMES
for n in ["sit_a","peek","sleep","dangle"]:
    g=F[n]; assert len(g)==H and all(len(r)==W for r in g)
src=open("sondercat.py").read()
# real purr files wired
assert 'pet = os.path.join(snd_dir, "purr_pet.wav")' in src
assert 'self._paths["purr"] = pet' in src
assert "def purr_sleep" in src and "def stop_purr" in src
# no synth purr leftover
assert "machine-gun" not in src and "1-pole low-pass" not in src
# pet cooldown long, sleep purr wired
assert "now - self._last_purr > 11.0" in src
assert "self._last_sleep_purr = 0.0" in src
assert "self.mgr._sfx.purr_sleep()" in src
# update whitelist + mkdirs
assert '"sounds/purr_pet.wav", "sounds/purr_sleep.wav"' in src
assert "os.makedirs(os.path.dirname(dest), exist_ok=True)" in src
# files present
assert os.path.exists("sounds/purr_pet.wav") and os.path.exists("sounds/purr_sleep.wav")
i=src.index("if guarding or self.duck_gunner:"); j=src.index("pp.end()", i)
assert "jy = 0" in src[j:j+300]
print("VALIDATE_OK")
