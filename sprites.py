"""
SondeR cat sprites.

What the reference actually shows (and v1-v3 got wrong):
  * the sitting cat is TALLER than wide — an upright cat, not a blob
  * distinct head -> chest -> two visible FRONT LEGS down to paws
  * haunches bulge at the sides; tail lies on the ground beside the paws
  * small triangle ears, big eyes, whiskers, thick white outline around all

Legend: . empty | K dark outline | B body | S stripe | W white/paws
        E eye white | N nose | M mouth | Z inner ear | H whisker
        G keycap front | g keycap top | O halo (computed, never authored)
"""

GRID_W, GRID_H = 26, 28
EYE_W, EYE_H = 3, 3

# ----------------------------------------------------------------- sitting ---
# upright sit: head / chest / front legs+paws / haunches / ground tail
SIT_A = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    ".HHKBEEEBBBNNBBBEEEBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKWWBKKBWWKBBKBBBK..",
    "..KBBBBKWWBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

# tail tip flicked up
SIT_B = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    ".HHKBEEEBBBNNBBBEEEBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK.K..",
    "..KBBBBKBBBBBBBBKBBBBKKBK.",
    "..KBBBBKBBBBBBBBKBBBKKBK..",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKWWBKKBWWKBBKBBK...",
    "..KBBBBKWWBKKBWWKBKBBK....",
    "...KKKKKKKKKKKKKKKKKK.....",
    "..........................",
    "..........................",
]

BLINK = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBBBBBBBBBBBBBBBBKHH...",
    "...KBKKKBBBBBBBBKKKBK.....",
    ".HHKBBBBBBBNNBBBBBBBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKWWBKKBWWKBBKBBBK..",
    "..KBBBBKWWBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

# --------------------------------------- typing at two 3D keycaps (3/4) ------
TYPE_A = [
    "..........................",
    ".....KK........KK.........",
    "....KBBK......KBBK........",
    "....KBZBK....KBZBK........",
    "...KBBBBBKKKKBBBBBK.......",
    "...KBBBBBBBBBBBBBBK.......",
    "..KBBBBBBBBBBBBBBBBK......",
    ".HKBEEEBBBBBBBBEEEBK......",
    "..KBEEEBBBBBBBBEEEBK......",
    ".HKBEEEBBBNNBBBEEEBKKK....",
    "..KBBBBBBBMMBBBBBBKKBBK...",
    "..KBBBBBBBBBBBBBBBKKBBK...",
    "..KBBBBBBBBBBBBBBBBKBBK...",
    "...KBBBBBBBBBBBBBBBKBK....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBKBBBBKBBBBBBBK.....",
    "....KBBKBBBBKWWKBBBBK.....",
    "....KBBKBBBBKWWKBBBBK.....",
    "....KBBKBBBBKKKKBBBBK.....",
    "....KWWKBBBBBBKBBBBBK.....",
    "....KWWKBBBBBBKWWBBBK.....",
    "...KKKKKKKBBBBKKKKKKK.....",
    "...KggggggKKKKKggggggK....",
    "..KggggggGGKKKggggggGGK...",
    "..KGGGGGGGGK.KGGGGGGGGK...",
    "...KKKKKKKK...KKKKKKKK....",
    "..........................",
    "..........................",
]

TYPE_B = [
    "..........................",
    ".....KK........KK.........",
    "....KBBK......KBBK........",
    "....KBZBK....KBZBK........",
    "...KBBBBBKKKKBBBBBK.......",
    "...KBBBBBBBBBBBBBBK.......",
    "..KBBBBBBBBBBBBBBBBK......",
    ".HKBEEEBBBBBBBBEEEBK......",
    "..KBEEEBBBBBBBBEEEBK......",
    ".HKBEEEBBBNNBBBEEEBKKK....",
    "..KBBBBBBBMMBBBBBBKKBBK...",
    "..KBBBBBBBBBBBBBBBKKBBK...",
    "..KBBBBBBBBBBBBBBBBKBBK...",
    "...KBBBBBBBBBBBBBBBKBK....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBKBBBBKBBBBBBBK.....",
    "....KWWKBBBBKBBKBBBBK.....",
    "....KWWKBBBBKBBKBBBBK.....",
    "....KKKKBBBBKBBKBBBBK.....",
    ".....KBBBBBBKWWKBBBBK.....",
    ".....KBBBBBBKWWKWWBBK.....",
    "...KKKKKKKBBKKKKKKKKK.....",
    "...KggggggKKKKKggggggK....",
    "..KggggggGGKKKggggggGGK...",
    "..KGGGGGGGGK.KGGGGGGGGK...",
    "...KKKKKKKK...KKKKKKKK....",
    "..........................",
    "..........................",
]

# ------------------------------------- reaching for the paper roll (scroll) --
KNEAD_A = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBEEEBBBNNBBBEEEBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    ".KKKKBBBBBBBBBBBBBBK......",
    ".KWWBBBBBBBBBBBBBBBBK.....",
    ".KWWBBKBBBBBBBBBBBBBK.....",
    ".KKKKBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKBBBKKBWWKBBKBBBK..",
    "..KBBBBKBBBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

KNEAD_B = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBEEEBBBNNBBBEEEBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    ".KKKKBBBBBBBBBBBBBBBK.....",
    ".KWWBBBBBBBBBBBBBBBBK.....",
    ".KWWBBKBBBBBBBBBBBBBBK....",
    ".KKKKBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKBBBKKBWWKBBKBBBK..",
    "..KBBBBKBBBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

# ---------------------------------------------------------------- sleeping ---
SLEEP = [
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    ".......KK........KK.......",
    "......KBBK......KBBK......",
    "......KBZBK....KBZBK......",
    ".....KBBBBBKKKKBBBBBK.....",
    ".....KBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBBBK....",
    "....KBKKKBBBBBBBBKKKBK....",
    ".HHKBBBBBBBNNBBBBBBBBBK...",
    "...KBBBBBBBMMBBBBBBBBBKK..",
    ".HHKBBBBBBBBBBBBBBBBBBBBK.",
    "..KBBBBBBBBBBBBBBBBBBBBBK.",
    "..KBBBBBBBBBBBBBBBBBBBBBK.",
    "..KBBBBBBBBBBBBBBBBBBBBK..",
    "..KBBBBBBBBBBBBBBBBBBBK...",
    "..KBKKKBBBBBBBBBBBBBBBK...",
    "..KKBBBKKBBBBBBBBBBBBK....",
    "...KBBBBBKKKKKKKKKKKK.....",
    "....KKKKKKKKKKKKKKK.......",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
]

# ------------------------------------------------ hunting run (chase) -------
# compact happy gallop: two front paws reaching, two back feet — NOT a spider
RUN_A = [
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "....KK....................",
    "...KZZK...................",
    "..KBBBBK...........KKK....",
    "..KBBBBBK.........KBSBK...",
    ".KBBKBBBBK........KBSBK...",
    ".KBBKBBBBK.......KBSBK....",
    "KNBBBBBBBBKKKKK.KBSBK.....",
    ".KWWBBBBBBBBBBKKBSBK......",
    ".KWWWBBBBBBBBBBBBBK.......",
    "..KWWBBBBBBBBBBBBK........",
    "..KWBBBBBBBBBBBBBK........",
    "..KBBBWWWWWWBBBBBK........",
    "..KBBKBWWWWBBKBBBK........",
    "..KBBK.KBBBK..KBBK........",
    "..KBWK..KBWK..KBWK........",
    "...KK....KK....KK.........",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
]

RUN_B = [
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "....KK....................",
    "...KZZK...................",
    "..KBBBBK..................",
    "..KBBBBBK.......KKKKKK....",
    ".KBBKBBBBK....KKBSSSSBK...",
    ".KBBKBBBBK...KBSSBKKKK....",
    "KNBBBBBBBBKKKBSBKK........",
    ".KWWBBBBBBBBBBBK..........",
    ".KWWWBBBBBBBBBBBK.........",
    "..KWWBBBBBBBBBBBBK........",
    "..KWBBBWWWWWBBBBBBK.......",
    ".KBBBKBWWWWBBBKBBBBK......",
    "KBBK..KBBBBK...KBBBBK.....",
    "KBWK...KKKK.....KBBBWK....",
    ".KK..............KBWK.....",
    "..................KK......",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
]

# --------------------------------------------------------------- stretching --
STRETCH = [
    "..........................",
    "...........KWWK...........",
    "..........KWWWWK..........",
    "..........KBKKBK..........",
    "..........KBKKBK..........",
    ".....KK...KBKKBK..KK......",
    "....KBBK..KBKKBK.KBBK.....",
    "....KBZBKKKBKKBKKBZBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBBBBBBBBBBBBBBBBKHH...",
    "...KBKKKBBBBBBBBKKKBK.....",
    "...KBBBBBBBNNBBBBBBBK.....",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.KK....",
    ".....KBBBBBBBBBBBBKKBBK...",
    ".....KBBBBBBBBBBBBKKBK....",
    ".....KBBBBBBBBBBBKKBK.....",
    ".....KWWBKBBBBKWWKKK......",
    "......KWWK....KWWK........",
    ".......KK......KK.........",
    "..........................",
]

# ------------------------------------------------------- dangling (drag) -----
DANGLE = [
    "..........................",
    "...........KWWK...........",
    "..........KWWWWK..........",
    "..........KBKKBK..........",
    "..........KBKKBK..........",
    ".....KK...KBKKBK..KK......",
    "....KBBK..KBKKBK.KBBK.....",
    "....KBZBKKKBKKBKKBZBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBEEEBBBNNBBBEEEBK.....",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.......",
    ".....KBBBBBBBBBBBBK.KK....",
    ".....KBBBBBBBBBBBBKKBBK...",
    ".....KBBBBBBBBBBBBKKBK....",
    ".....KBBBBBBBBBBBKKBK.....",
    ".....KWWBKBBBBKWWKKK......",
    "......KWWK....KWWK........",
    ".......KK......KK.........",
    "..........................",
    "..........................",
]

# ------------------------------------------------------------- peeking -------
PEEK = [
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KWWKBBBBBBBBBBBBKWWK....",
    "..KKKKKKKKKKKKKKKKKKKK....",
    "..........................",
    "..........................",
]

YAWN = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBBBBBBBBBBBBBBBBKHH...",
    "...KBKKKBBBBBBBBKKKBK.....",
    ".HHKBBBBBBBNNBBBBBBBKHH...",
    "...KBBBBBBBKMMKBBBBBK.....",
    "...KBBBBBBBKMMKBBBBBK.....",
    "....KBBBBBBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKWWBKKBWWKBBKBBBK..",
    "..KBBBBKWWBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

GROOM_A = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBBBBBBBBBBBBBBBBKHH...",
    "...KBKKKBBBBBBBBKKKBK.....",
    ".HHKBBBBBBBNNBBBBBBBKHH...",
    "...KBBBBBZBMMBBBBBBBK.....",
    "...KBBKWWKBBBBBBBBBBK.....",
    "....KBKWWKBBBBBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKBBBKKBWWKBBKBBBK..",
    "..KBBBBKBBBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

GROOM_B = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    ".HHKBBBBBBBBBBBBBBBBKHH...",
    "...KBKKKBBBBBBBBKKKBK.....",
    ".HHKBBBBBBBNNBBBBBBBKHH...",
    "...KBBBBBBBMMBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "....KBKWWKBBBBBBBBBK......",
    "....KBKWWKBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBBBBBBBBBBBBBBBBK.....",
    "..KBBBBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKBBBKKBWWKBBKBBBK..",
    "..KBBBBKBBBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

KNEAD_C = [
    "..........................",
    "..........................",
    "......KK........KK........",
    ".....KBBK......KBBK.......",
    ".....KBZBK....KBZBK.......",
    "....KBBBBBKKKKBBBBBK......",
    "....KBBBBBBBBBBBBBBK......",
    "...KBBBBBBBBBBBBBBBBK.....",
    "...KBEEEBBBBBBBBEEEBKHH...",
    "...KBEEEBBBBBBBBEEEBK.....",
    "...KBEEEBBBNNBBBEEEBKHH...",
    ".KWWKBBBBBBMMBBBBBBBK.....",
    ".KWWKBBBBBBBBBBBBBBBK.....",
    "..KBBKBBBBBBBBBBBBBK......",
    "...KBKBBBBBBBBBBBBBK......",
    ".....KBBBBBBBBBBBBBBK.....",
    "......KBBBBBBBBBBBBBK.....",
    ".....KBBBBBBBBBBBBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBBK....",
    "..KBBBBKBBBBBBBBKBBBKK....",
    "..KBBBBKBBBKKBBBKBBKBBK...",
    "..KBBBBKBBBKKBWWKBBKBBBK..",
    "..KBBBBKBBBKKBWWKBKBBBBK..",
    "...KKKKKKKKKKKKKKKKKKKK...",
    "..........................",
    "..........................",
]

FRAMES = {
    "sit_a": SIT_A, "sit_b": SIT_B, "blink": BLINK,
    "type_a": TYPE_A, "type_b": TYPE_B,
    "knead_a": KNEAD_A, "knead_b": KNEAD_B,
    "sleep": SLEEP, "run_a": RUN_A, "run_b": RUN_B,
    "stretch": STRETCH, "dangle": DANGLE, "peek": PEEK,
    "yawn": YAWN,
    "groom_a": GROOM_A, "groom_b": GROOM_B, "knead_c": KNEAD_C,
}

EYE_CELLS = {
    "sit_a": [(5, 8), (16, 8)], "sit_b": [(5, 8), (16, 8)],
    "type_a": [(4, 7), (15, 7)], "type_b": [(4, 7), (15, 7)],
    "knead_a": [(5, 8), (16, 8)], "knead_b": [(5, 8), (16, 8)],
    "knead_c": [(5, 8), (16, 8)],
    "dangle": [(5, 10), (16, 10)], "peek": [(5, 20), (16, 20)],
}

HEAD_RECT = (3, 2, 22, 13)
SCROLL_ROLL = (2, 18)           # roll sits under the reaching paw
SIT_A_REF = SIT_A
SIT_A = SIT_A                   # tray icon uses this

PALETTES = {
    "mimi": {"B": "#ded5c6", "S": "#8a7c68", "W": "#f7f3ea",
             "K": "#4a4238", "E": "#f8f8f4", "N": "#b5744f",
             "M": "#4a4238", "Z": "#d9b09a", "P": "#4f7da8"},
    "jj": {"B": "#96896e", "S": "#453e32", "W": "#f1ebdd",
           "K": "#2f2a24", "E": "#f8f8f4", "N": "#c06a3f",
           "M": "#2f2a24", "Z": "#d9a58f", "P": "#4f7d42"},
    "lilly": {"B": "#efa75a", "S": "#d8853a", "W": "#f7f2e8",
              "K": "#503219", "E": "#f8f8f4", "N": "#e78a8a",
              "M": "#503219", "Z": "#f2b8ac", "P": "#3c5240"},
    "orange tabby": {"B": "#e8963c", "S": "#c9752a", "W": "#f6ead8", "K": "#4a2f1a",
                     "E": "#f8f8f4", "N": "#e06a7c", "M": "#4a2f1a", "Z": "#eeb0a0", "P": "#2c3138"},
    "gray":         {"B": "#8b8f98", "S": "#6e727c", "W": "#e8e8ea", "K": "#33353b",
                     "E": "#f8f8f4", "N": "#d98794", "M": "#33353b", "Z": "#d9a8a8", "P": "#26282e"},
    "black":        {"B": "#26262b", "S": "#1e1e22", "W": "#e8e8ea", "K": "#0f0f12",
                     "E": "#f8f8f4", "N": "#d98794", "M": "#0e0e10", "Z": "#a87d7d", "P": "#101013"},
    "white":        {"B": "#f2efe8", "S": "#e0dacd", "W": "#ffffff", "K": "#8a8378",
                     "E": "#fbfbf8", "N": "#e79aa6", "M": "#8a8378", "Z": "#efb9b0", "P": "#33383f"},
    "calico":       {"B": "#efe6d6", "S": "#d88a3a", "W": "#ffffff", "K": "#584134",
                     "E": "#f8f8f4", "N": "#e06a7c", "M": "#584134", "Z": "#eeb0a0", "P": "#2c3138"},
    "cream":        {"B": "#f0dfc0", "S": "#dcc49a", "W": "#fdf8ee", "K": "#6e5a42",
                     "E": "#f8f8f4", "N": "#e79aa6", "M": "#6e5a42", "Z": "#f0bcae", "P": "#33383f"},
    "chocolate":    {"B": "#6b4a35", "S": "#583b28", "W": "#e9ddd0", "K": "#2e1e13",
                     "E": "#f8f8f4", "N": "#d98794", "M": "#2e1e13", "Z": "#c99486", "P": "#1c1d21"},
    "lilac":        {"B": "#b7a8c4", "S": "#a08fb1", "W": "#f0ecf4", "K": "#4c4058",
                     "E": "#f8f8f4", "N": "#e096a4", "M": "#4c4058", "Z": "#e3b6c0", "P": "#2b2e34"},
    "pink":         {"B": "#f2b9c6", "S": "#e5a0b2", "W": "#fdf1f4", "K": "#7e4454",
                     "E": "#f8f8f4", "N": "#e06a7c", "M": "#7e4454", "Z": "#f6cfd8", "P": "#33383f"},
    "mint":         {"B": "#b4dcc8", "S": "#9ccab4", "W": "#f0faf5", "K": "#3c5f4f",
                     "E": "#f8f8f4", "N": "#e096a4", "M": "#3c5f4f", "Z": "#e0b8b2", "P": "#2b2e34"},
}

EXTRA_COLORS = {"G": "#8a8f98", "g": "#d4d8de", "O": "#ffffff", "H": "#f2f4f6"}

OVERHEAT_PALETTE = {
    "B": "#e6483a", "S": "#d13527", "W": "#ffd9d2", "K": "#8e1a0c",
    "E": "#fdf3f1", "N": "#a41d10", "M": "#8e1a0c", "Z": "#ff9a8c", "P": "#54100a",
}

PATTERNS = ["tabby", "solid", "tuxedo", "spots", "siamese", "lilly", "jj", "mimi"]


def _spot_hash(x, y):
    return ((x * 73856093) ^ (y * 19349663)) % 100


def apply_pattern(grid, pattern):
    if pattern in (None, "tabby"):
        return grid
    h, w = len(grid), len(grid[0])
    out = []
    for y, row in enumerate(grid):
        new = []
        for x, ch in enumerate(row):
            c = ch
            if pattern == "solid":
                if c == "S":
                    c = "B"
            elif pattern == "spots":
                if c == "S":
                    c = "B"
                if c == "B" and _spot_hash(x, y) < 16:
                    c = "S"
            elif pattern == "tuxedo":
                if c == "S":
                    c = "B"
                if c == "B" and y >= int(h * 0.55) and w * 0.30 <= x <= w * 0.70:
                    c = "W"
                if c == "B" and h * 0.36 <= y <= h * 0.46 and w * 0.36 <= x <= w * 0.64:
                    c = "W"
            elif pattern == "lilly":
                if c == "B" and y >= int(h * 0.52) \
                        and w * 0.28 <= x <= w * 0.72:
                    c = "W"
                if c == "B" and h * 0.36 <= y <= h * 0.47 \
                        and w * 0.36 <= x <= w * 0.64:
                    c = "W"
            elif pattern == "jj":
                if c == "B" and h * 0.38 <= y <= h * 0.47 \
                        and w * 0.40 <= x <= w * 0.60:
                    c = "W"                      # white chin/muzzle
                elif c == "B" and y >= int(h * 0.58) \
                        and w * 0.40 <= x <= w * 0.60:
                    c = "W"                      # chest bib
                elif c == "B":
                    on_line = (x + (y // 3)) % 3 == 0
                    if y < h * 0.46:
                        # head: only short forehead lines, cheeks clear
                        if on_line and y < h * 0.30 \
                                and w * 0.32 <= x <= w * 0.68 \
                                and _spot_hash(x, y) > 8:
                            c = "S"
                    else:
                        # body: broken, irregular mackerel stripes
                        if on_line and _spot_hash(x, y) > 7:
                            c = "S"
            elif pattern == "mimi":
                if c == "B" and y <= int(h * 0.22):
                    c = "S"                      # dusky crown and ears
                elif c == "B" and h * 0.38 <= y <= h * 0.47 \
                        and w * 0.40 <= x <= w * 0.60:
                    c = "W"                      # white chin
                elif c == "B" and h * 0.52 <= y <= h * 0.75 \
                        and w * 0.34 <= x <= w * 0.66:
                    c = "W"                      # white chest
                elif c == "B" and y >= int(h * 0.78) and y % 3 == 1:
                    c = "S"                      # ringed paws
            elif pattern == "siamese":
                if c == "S":
                    c = "B"
                if c == "B" and (y <= 4 or y >= h - 4 or x >= w - 4):
                    c = "S"
            new.append(c)
        out.append("".join(new))
    return out


def add_halo(grid):
    h, w = len(grid), len(grid[0])
    out = [list(r) for r in grid]
    solid = set("KBSWEZNMGg")
    for y in range(h):
        for x in range(w):
            if grid[y][x] != ".":
                continue
            hit = False
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and grid[ny][nx] in solid:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out[y][x] = "O"
    return ["".join(r) for r in out]


def render_frame(grid, palette, scale=6, flip=False, halo=True):
    from PySide6.QtGui import QImage, QColor, QPainter
    if halo:
        grid = add_halo(grid)
    img = QImage(GRID_W * scale, GRID_H * scale, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    cache = {}
    for gy, row in enumerate(grid):
        for gx, ch in enumerate(row):
            if ch == ".":
                continue
            col = cache.get(ch)
            if col is None:
                col = QColor(palette.get(ch)
                             or EXTRA_COLORS.get(ch, "#ff00ff"))
                cache[ch] = col
            x = (GRID_W - 1 - gx) if flip else gx
            p.fillRect(x * scale, gy * scale, scale, scale, col)
    p.end()
    return img


def render_icon(palette, pattern="tabby", scale=12, frame="sit_a"):
    """Frame render + baked-in pupils (they're normally drawn at runtime)."""
    from PySide6.QtGui import QPainter, QColor
    grid = apply_pattern(FRAMES[frame], pattern)
    img = render_frame(grid, palette, scale)
    cells = EYE_CELLS.get(frame, [])
    p = QPainter(img)
    pc = QColor(palette["P"])
    pw = 2 * scale
    for (ex, ey) in cells:
        bx = ex * scale + (EYE_W * scale - pw) // 2
        by = ey * scale + (EYE_H * scale - pw) // 2 + scale // 3
        p.fillRect(bx, by, pw, pw, pc)
    p.end()
    return img

