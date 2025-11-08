from PIL import ImageDraw
from .fonts import load_font

FONT_SM = load_font(14)

def draw_feature_icon(draw: ImageDraw.ImageDraw, name: str, xy):
    """Tiny 16x16-ish monochrome icons used in the Features list."""
    x, y = xy
    n = (name or "").lower()

    if n in ("skull", "undead", "undead activity"):
        # skull
        draw.ellipse([x+2, y+2, x+14, y+14], outline=0, width=2)
        draw.rectangle([x+6, y+9, x+10, y+12], fill=0)
        draw.point((x+6, y+6), 0); draw.point((x+10, y+6), 0)

    elif n in ("anchor", "smuggling", "smuggling ring", "dock"):
        # anchor
        draw.line([(x+8, y+2), (x+8, y+11)], fill=0, width=2)
        draw.arc([x+1, y+8, x+15, y+16], 10, 170, fill=0, width=2)
        draw.ellipse([x+6, y, x+10, y+4], outline=0, width=2)

    elif n in ("cross", "templar", "temple", "orphanage"):
        # templar cross
        draw.rectangle([x+6, y+2, x+10, y+14], fill=0)
        draw.rectangle([x+3, y+6, x+13, y+9], fill=0)

    elif n in ("keep", "tower", "fort", "old river keep"):
        # keep / tower
        draw.rectangle([x+3, y+6, x+13, y+14], outline=0, width=2)
        draw.rectangle([x+6, y+9, x+10, y+14], fill=0)
        draw.polygon([(x+3, y+6), (x+8, y+2), (x+13, y+6)], outline=0)

    else:
        # fallback: simple square
        draw.rectangle([x+4, y+4, x+12, y+12], outline=0, width=2)
