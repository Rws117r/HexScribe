from PIL import ImageFont
import os

# fallback list from your previous runs
FONT_CANDIDATES = [
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "arial.ttf",
]

BLACKLETTER_CANDIDATES = [
    "Berkahi Blackletter.ttf",
    "./Berkahi Blackletter.ttf",
    "./fonts/Berkahi Blackletter.ttf",
    "/usr/share/fonts/truetype/Berkahi Blackletter.ttf",
    "/usr/local/share/fonts/Berkahi Blackletter.ttf",
]

def load_font(size: int):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def load_blackletter(size: int):
    for p in BLACKLETTER_CANDIDATES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return load_font(size)
