import sprites
from PIL import Image, ImageDraw
pal = sprites.PALETTES["orange tabby"]
def hx(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def render(frame, scale=24, halo=True):
    if halo:
        frame = sprites.add_halo(frame) if hasattr(sprites,'add_halo') else frame
    W=sprites.GRID_W; H=sprites.GRID_H
    img=Image.new("RGBA",(W*scale,H*scale),(24,24,32,255)); px=img.load()
    for y,row in enumerate(frame):
        for x,ch in enumerate(row):
            if ch=='.': continue
            if ch in ('O','H'): col=(255,255,255)
            elif ch in pal: col=hx(pal[ch])
            else: col=(255,0,255)
            for dy in range(scale):
                for dx in range(scale): px[x*scale+dx,y*scale+dy]=(*col,255)
    return img.convert("RGB")
def show(a,b,path,labels=("RUN_A","RUN_B")):
    ia,ib=render(a),render(b); gap=50; W=ia.width;H=ia.height
    c=Image.new("RGB",(W*2+gap,H+50),(24,24,32)); c.paste(ia,(0,50)); c.paste(ib,(W+gap,50))
    d=ImageDraw.Draw(c); d.text((W//2-30,18),labels[0],fill=(255,255,255)); d.text((W+gap+W//2-30,18),labels[1],fill=(255,255,255))
    c.save(path); print("saved",path)
