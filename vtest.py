import sprites
SC=set(".KBSWENMZHGgOP");W,H=sprites.GRID_W,sprites.GRID_H;F=sprites.FRAMES
for n in ["sit_a","peek","sleep"]:
    g=F[n]; assert len(g)==H and all(len(r)==W for r in g)
src=open("sondercat.py").read()
assert "0.91 + 0.09 * math.sin(2 * math.pi * 6 * t)" in src   # shallow slow tremolo
assert "dur = 2.4" in src
assert "now - self._last_purr > 2.5" in src
i=src.index("if guarding or self.duck_gunner:"); j=src.index("pp.end()", i)
assert "jy = 0" in src[j:j+300]
print("VALIDATE_OK")
