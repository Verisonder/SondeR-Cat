# Editing SondeR cat's animations 🎨

Every pose is a **plain-text pixel grid** in one file: `sprites.py`.
You don't need to be a programmer — if you can edit text, you can redraw
the cat.

## The 30-second workflow

1. Right-click the cat → **Animations → Open animations file** (opens
   `sprites.py` in your editor)
2. Right-click → **Animations → Auto-reload on save** (tick it once)
3. Edit pixels → press **Ctrl+S** → the cat updates **instantly**, live on
   your screen

No restarting, no reinstalling while you experiment. If you prefer manual
control, use **Reload animations now** instead of the auto toggle.

## You cannot break the cat

Every save is checked before it's used. If an edit has a problem, the cat
**keeps its current art** and a message tells you exactly what to fix, e.g.:

> `STRETCH, row 12: has 23 characters, needs 24`
> `SLEEP, row 5: illegal character 'Q'`
> `Syntax error at line 210`

Fix the line, save again, done.

## The pixel alphabet

| char | means | | char | means |
|---|---|---|---|---|
| `.` | empty (transparent) | | `N` | nose (pink) |
| `K` | dark outline | | `M` | mouth line |
| `B` | body fur | | `Z` | inner ear / blush |
| `S` | stripe (tabby) | | `H` | whisker |
| `W` | white — paws, patches | | `G` / `g` | keycap front / top |
| `E` | eye white | | | |

The thick **white halo** around the cat is computed automatically — never
draw it yourself.

## The two hard rules

1. Every row must be **exactly 24 characters**
2. Every frame must be **exactly 26 rows**

(The validator enforces both, so worst case you get a helpful message.)

## Which frame is which animation

| Frame(s) in `sprites.py` | Used for |
|---|---|
| `SIT_A` / `SIT_B` | idle sitting (B = tail flicked) |
| `BLINK` | blinking |
| `TYPE_A` / `TYPE_B` | keyboard kneading (alternating paws) |
| `KNEAD_A`–`KNEAD_C` | batting the paper while you scroll: strike, mid, raised |
| `SLEEP` | sleeping loaf |
| `RUN_A` / `RUN_B` | chasing the cursor + running to/from hiding |
| `STRETCH` | the grow-big stretch reminder |
| `DANGLE` | hanging from your cursor (mochi drag) |
| `PEEK` | hiding at the bottom screen edge |
| `SLEEP_B` | breathing (alternates with `SLEEP`) |
| `YAWN` | shown for a moment when falling asleep |
| `GROOM_A` / `GROOM_B` | licking a paw — plays occasionally while idle |

## Also editable in the same file

- **`PALETTES`** — all fur color themes (hex colors). Add a new entry and
  it appears in the Fur color menu automatically.
- **`EYE_CELLS`** — where the moving pupils sit in each frame, as `(x, y)`
  of each eye's top-left corner. **If you move a frame's eyes, update its
  entry here** or the pupils will float in the wrong place. Frames with
  closed eyes (`BLINK`, `SLEEP`, `STRETCH`) have no entry.
- **`apply_pattern()`** — the rules that paint tuxedo / spots / siamese
  over your base art.

## What is NOT in sprites.py

Anything that *moves or spawns* is drawn by code in `sondercat.py`:
pupils following your cursor, hearts, z's, steam puffs, the paper strip,
thought dots, jumping, wobble, the mochi stretch, running motion. Poses →
edit yourself; motion → open an issue or ask the developer.

## Keeping your art

Reinstalling (or updating) **overwrites** `sprites.py` with the official
version. When you make something you love, copy it somewhere safe — or
contribute it back so it becomes the official art.
