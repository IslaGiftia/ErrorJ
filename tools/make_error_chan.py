"""Generate original pixel-art assets for the Error-chan site mascot."""

from pathlib import Path

from PIL import Image


OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "site"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = {
    ".": None,
    "H": (255, 235, 240, 255),      # light pink hair
    "h": (255, 205, 216, 255),      # hair shadow
    "S": (255, 225, 210, 255),      # skin
    "s": (244, 196, 180, 255),      # skin shadow
    "E": (64, 138, 255, 255),       # bright blue eye
    "e": (32, 78, 210, 255),        # dark blue eye
    "W": (255, 255, 255, 255),      # white
    "T": (48, 54, 74, 255),         # dark teal outfit
    "t": (38, 44, 62, 255),         # outfit shadow
    "C": (29, 205, 195, 255),       # bright teal accent
    "P": (255, 108, 158, 255),      # heart pink
    "Y": (255, 205, 80, 255),       # warm yellow
    "G": (120, 222, 130, 255),      # ok green
    "R": (255, 110, 110, 255),      # error red
    "A": (152, 164, 190, 255),      # gray accent
}


AVATAR_GRID = [
    "........H.H.................",
    "........P.P.................",
    ".......HHHHHH................",
    "......HHHHHHHHHH.............",
    ".....HHHHHHHHHHHHH...........",
    "....HHHHHHHHHHHHHHH..........",
    "...HHHHHHHHHHHHHHHHH.........",
    "...HHHHhhhHHHHHhhhHHH........",
    "..HHHHHssSSSSSSSssHHHHH......",
    "..HHHHssSSSSSSSSSsHHHH.......",
    "..HHHHsSEeSSSSSSEeSsHHH......",
    "..HHHHsSEeSSSSSSEeSsHHH......",
    "..HHHHssSSSSSSSSSsHHHH.......",
    "...HHHsSSSSSSSSSsHHHH........",
    "....HHsSSSSSSSSSsHHH.........",
    ".....HHsSSSSSSSsHHH..........",
    ".....HHHsssssssHHH...........",
    "......HHhHHHHHhHH............",
    ".......HHHHHHHHH.............",
    ".......HHHHHHHHH.............",
    "......HHHHHhhhhHHH...........",
    "....HHHHHHHHHHHHHHHH.........",
    "...HHHHHHHHHHHHHHHHHH........",
    "...HHHhHHHHHHHHHhHHH.........",
    "..HHHHhhHHHHHHHhhHHHH........",
    "..HHHHHhhhhhhhhhHHHHH........",
    "..HHHHHHHHHHHHHHHHHHHH.......",
    "..HHHHHHHHHHHHHHHHHHHH.......",
]


def paint(pixels, grid, ox=0, oy=0):
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            color = PALETTE.get(ch)
            if color is None:
                continue
            pixels[ox + x, oy + y] = color


def apply_face_detail(px, ox=0, oy=0, blush=True, mouth="happy"):
    if blush:
        for x, y in [(9, 15), (10, 15), (17, 15), (18, 15)]:
            px[ox + x, oy + y] = (255, 178, 178, 255)
    if mouth == "happy":
        px[ox + 13, oy + 14] = (190, 70, 110, 255)
        px[ox + 14, oy + 14] = (190, 70, 110, 255)
        px[ox + 13, oy + 15] = (190, 70, 110, 255)
    elif mouth == "open":
        px[ox + 13, oy + 14] = (170, 55, 90, 255)
        px[ox + 14, oy + 14] = (170, 55, 90, 255)
        px[ox + 14, oy + 15] = (255, 150, 170, 255)
    elif mouth == "straight":
        px[ox + 13, oy + 14] = (150, 65, 95, 255)
        px[ox + 14, oy + 14] = (150, 65, 95, 255)


def antenna(px, ox=0, oy=0, kind="heart"):
    for x in range(13, 17):
        px[ox + x, oy + 3] = (176, 186, 210, 255)
    if kind == "heart":
        px[ox + 14, oy + 1] = (255, 108, 158, 255)
        px[ox + 15, oy + 1] = (255, 108, 158, 255)
        px[ox + 15, oy + 2] = (255, 108, 158, 255)
    else:
        px[ox + 15, oy + 1] = (255, 205, 80, 255)
        px[ox + 15, oy + 2] = (255, 205, 80, 255)


def make_avatar(size=256):
    """Standalone head-and-shoulders icon with happy expression."""
    img = Image.new("RGBA", (28, 28), (0, 0, 0, 0))
    px = img.load()
    paint(px, AVATAR_GRID)
    apply_face_detail(px)
    antenna(px)
    img = img.resize((size, size), Image.NEAREST)
    img.save(OUT_DIR / "error-chan-avatar.png")


def make_expressions():
    """4-up expression sheet: happy, thinking, error, ok."""
    cell = 28
    sheet = Image.new("RGBA", (cell * 4, cell), (0, 0, 0, 0))
    px = sheet.load()

    # happy
    paint(px, AVATAR_GRID, 0, 0)
    apply_face_detail(px)
    antenna(px)

    # thinking
    paint(px, AVATAR_GRID, cell, 0)
    apply_face_detail(px, cell, 0, mouth="open")
    antenna(px, cell, 0, kind="dot")
    for x in range(cell + 3, cell + 6):
        px[x, 3] = (204, 210, 228, 255)
    for x in range(cell + 2, cell + 5):
        px[x, 2] = (204, 210, 228, 255)

    # error: eyes closed, red badge above head
    paint(px, AVATAR_GRID, cell * 2, 0)
    apply_face_detail(px, cell * 2, 0, blush=False, mouth="straight")
    for x in range(cell * 2 + 11, cell * 2 + 17):
        px[x, 11] = (255, 110, 110, 255)
        px[x, 12] = (255, 110, 110, 255)
    px[cell * 2 + 14, 9] = (255, 110, 110, 255)
    px[cell * 2 + 14, 15] = (255, 110, 110, 255)

    # ok: wink, green badge
    paint(px, AVATAR_GRID, cell * 3, 0)
    apply_face_detail(px, cell * 3, 0, mouth="happy")
    antenna(px, cell * 3, 0, kind="dot")
    for x in range(cell * 3 + 11, cell * 3 + 17):
        px[x, 11] = (120, 222, 130, 255)
    px[cell * 3 + 14, 9] = (120, 222, 130, 255)
    px[cell * 3 + 14, 15] = (120, 222, 130, 255)
    # wink: close one eye
    for x in range(cell * 3 + 16, cell * 3 + 19):
        px[x, 11] = (64, 138, 255, 255)

    sheet = sheet.resize((cell * 8, cell * 2), Image.NEAREST)
    sheet.save(OUT_DIR / "error-chan-expressions.png")


MASCOT_GRID = [
    "................................",
    "...........H.H.................",
    "...........P.P.................",
    ".........HHHHHHHHH.............",
    "........HHHHHHHHHHH............",
    ".......HHHHHHHHHHHHH...........",
    "......HHHHHHHHHHHHHHH..........",
    "......HHHHhhhHHHHHhhhHHH.......",
    ".....HHHHHssSSSSSSssHHHHH......",
    ".....HHHHssSSSSSSSSSsHHHH......",
    ".....HHHHsSEeSSSSSSEeSsHHH.....",
    ".....HHHHsSEeSSSSSSEeSsHHH.....",
    ".....HHHHssSSSSSSSSSsHHHH......",
    "......HHHsSSSSSSSSSsHHHH.......",
    ".......HHsSSSSSSSSSsHHHH.......",
    "........HHssSSSSSSSssHHH.......",
    ".........HHsssssssssHHH........",
    "........HHHhHHHHHHHhHHH........",
    "........HHHHHHHHHHHHHHH........",
    ".......HHHHHHHHHHHHHHHHH.......",
    "......HHHHHHHHHHHHHHHHHHH......",
    "......HHHHHHhhhhhhhhhHHHH......",
    ".....HHHHHHHHHHHHHHHHHHHH......",
    "....HHHHHHHHHHHHHHHHHHHHH......",
    "....HHHhHHHHHHHHHHHHHhHHH......",
    "...HHHHhhHHHHHHHHHHHhhHHHH.....",
    "..HHHHHHHhhhhhhhhhhhHHHHHH.....",
    "..HHHHHHHHHHHHHHHHHHHHHHHH.....",
    "....TTTTTTTTTTTTTTTTTTTT.......",
    "...TTTTTTTTTTTTTTTTTTTTTT......",
    "...TTTTttTTTTTTTTTTttTTTT......",
    "...TTTTttTTTTTTTTTTttTTTT......",
    "..TTTTTTTTtttttttttTTTTTTT.....",
    "..TTTTTTTTTTTTTTTTTTTTTTTT.....",
    "..TTCCCCCCCCCCCCCCCCCCCTT......",
    ".TTTCCCCCCCCCCCCCCCCCCCTTT.....",
    ".TTTCCCCCCCCCCCCCCCCCCCTTT.....",
    ".TTTTTTTTTTTTTTTTTTTTTTTTT.....",
]


def make_mascot(size=384):
    """Half-body mascot: oversized head, shoulders and chest panel."""
    img = Image.new("RGBA", (32, 38), (0, 0, 0, 0))
    px = img.load()
    paint(px, MASCOT_GRID)
    apply_face_detail(px, 0, 0, mouth="happy")
    antenna(px, 0, 0, kind="heart")
    # chest heart LED
    px[16, 34] = (255, 108, 158, 255)
    px[17, 34] = (255, 255, 255, 255)
    px[18, 34] = (255, 108, 158, 255)
    px[15, 35] = (255, 108, 158, 255)
    px[19, 35] = (255, 108, 158, 255)
    px[16, 36] = (255, 108, 158, 255)
    px[18, 36] = (255, 108, 158, 255)
    # floating pixel bits
    for x, y in [(26, 9), (27, 9), (26, 10)]:
        px[x, y] = (29, 205, 195, 255)
    for x, y in [(4, 13), (5, 13), (4, 14)]:
        px[x, y] = (255, 205, 80, 255)
    img = img.resize((size, int(size * 38 / 32)), Image.NEAREST)
    img.save(OUT_DIR / "error-chan-mascot.png")


def make_mini_icon():
    """Tiny pixel window icon: terminal window with error-chan face."""
    grid = [
        "................",
        "..AAAAAAAAAAAA..",
        ".AAWWWWWWWWWWAA.",
        ".AWAAAAAAAAAAWA.",
        ".AWHHHHHHHHHHWA.",
        ".AWHHSSSSSSHHWA.",
        ".AWHSSEESSHHWA..",
        ".AWHSSEESSHHWA..",
        ".AWHHSSSSHHHWA..",
        ".AWHHHHHHHHHWA..",
        ".AWWWWWWWWWWWA..",
        "..AAAAAAAAAAAA..",
    ]
    img = Image.new("RGBA", (16, 12), (0, 0, 0, 0))
    px = img.load()
    paint(px, grid)
    px[2, 3] = (255, 110, 110, 255)
    px[3, 3] = (255, 205, 80, 255)
    px[4, 3] = (120, 222, 130, 255)
    img = img.resize((96, 72), Image.NEAREST)
    img.save(OUT_DIR / "error-chan-mini.png")


if __name__ == "__main__":
    make_avatar()
    make_expressions()
    make_mascot()
    make_mini_icon()
    print("saved to", OUT_DIR)
