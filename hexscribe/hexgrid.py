from PIL import Image, ImageDraw, ImageOps
import math
from typing import List, Tuple, Dict
from .fonts import load_font

SQ3 = math.sqrt(3)

class HexGrid:
    """
    Flat-top hex grid clipped inside a big hex. Exposes:
      - centers: list[(x,y)] of usable small-hex centers (inside big hex)
      - nodes: list of dicts with {'q','r','x','y'}
      - node_lookup[(q,r)] -> (x,y)
      - neighbors(q,r) -> list[(q,r)] existing neighbors
      - diamond_r: last-used diamond radius (px) for edge anchoring
    """
    def __init__(self, cells_across=6, diamond_scale=0.55):
        self.cells_across = int(max(2, cells_across))
        self.diamond_scale = float(diamond_scale)
        self.diamond_r = 10
        self.centers: List[Tuple[int,int]] = []
        self.nodes: List[Dict] = []
        self.node_lookup: Dict[Tuple[int,int], Tuple[int,int]] = {}
        self.big_hex = (0, 0, 0)
        self.cell_size = 0.0
        self.font_num = load_font(16)

    # ----- math helpers (flat-top) -----
    def _hex_poly(self, xc, yc, r):
        return [(xc + r*math.cos(k), yc + r*math.sin(k))
                for k in (0, math.pi/3, 2*math.pi/3, math.pi, 4*math.pi/3, 5*math.pi/3)]

    def point_in_hex(self, cx, cy, R, x, y):
        px = abs(x - cx); py = abs(y - cy)
        if px > R or py > R * SQ3 / 2 + 1: 
            return False
        return (SQ3 * px + py) <= SQ3 * R + 1

    # axial neighbor deltas for flat-top layout
    AXIAL_DIRS = [(+1,0), (+1,-1), (0,-1), (-1,0), (-1,+1), (0,+1)]

    def neighbors(self, q, r):
        out = []
        for dq, dr in self.AXIAL_DIRS:
            qq, rr = q + dq, r + dr
            if (qq, rr) in self.node_lookup:
                out.append((qq, rr))
        return out

    # ----- grid draw (returns centers and big-hex tuple) -----
    def draw_grid(self, draw: ImageDraw.ImageDraw, *, left: int, top: int, right: int, bottom: int):
        cx = (left + right)//2
        cy = (top + bottom)//2
        R  = int(min(right-left, bottom-top)/2) - 6
        self.big_hex = (cx, cy, R)

        # derive small-hex size so ~cells_across fit across width
        C = self.cells_across
        s = (4.0 * R) / (3.0 * C + 1.0) * 0.985
        self.cell_size = s

        # axial scan window big enough, then filter to big hex
        q_max = int(R / (1.5 * s)) + 3
        r_max = int(R / (SQ3 * s)) + 3

        all_centers = []
        nodes = []
        for q in range(-q_max, q_max + 1):
            for r in range(-r_max, r_max + 1):
                x = cx + (1.5 * s) * q
                y = cy + (SQ3 * s) * (r + q / 2.0)
                all_centers.append((x, y, q, r))

        # build mask of the big hex
        mask = Image.new("1", draw.im.size, 0)
        md   = ImageDraw.Draw(mask)
        big  = self._hex_poly(cx, cy, R)
        md.polygon(big, fill=1, outline=1)

        # draw all small hex outlines on a temp layer
        grid = Image.new("1", draw.im.size, 1)
        gd   = ImageDraw.Draw(grid)
        for (x, y, _, _) in all_centers:
            gd.polygon(self._hex_poly(x, y, s), outline=0)

        # clip outlines & paint
        clipped = Image.new("L", draw.im.size, 255)
        clipped.paste(grid.convert("L"), (0, 0), mask.convert("L"))
        lines = ImageOps.invert(clipped).point(lambda p: 255 if p > 128 else 0)
        draw.bitmap((0, 0), lines.convert("1"), fill=0)
        draw.polygon(big, outline=0)

        # keep only centers truly inside (margin so diamonds/trails don't bleed)
        self.nodes.clear()
        self.node_lookup.clear()
        self.centers.clear()
        for (_, (x, y, q, r)) in enumerate(all_centers):
            if self.point_in_hex(cx, cy, R - s * 1.2, x, y):
                self.nodes.append({'q': q, 'r': r, 'x': int(x), 'y': int(y)})
                self.node_lookup[(q, r)] = (int(x), int(y))
                self.centers.append((int(x), int(y)))

        return self.centers, (cx, cy, R)

    # ----- render helpers -----
    def draw_diamond(self, draw: ImageDraw.ImageDraw, x: int, y: int, text):
        r = int(max(8, self.cell_size * self.diamond_scale))
        self.diamond_r = r
        draw.polygon([(x, y-r), (x+r, y), (x, y+r), (x-r, y)], fill=0, outline=0)
        label = str(text)
        bbox = draw.textbbox((0, 0), label, font=self.font_num)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x - tw/2, y - th/2), label, font=self.font_num, fill=1)

    def draw_compass(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, size=20, font=None):
        from .fonts import load_font
        w = max(3, size//3)
        draw.polygon([(cx,cy-size),(cx-w,cy-w),(cx+w,cy-w)], fill=0)
        draw.polygon([(cx,cy+size),(cx-w,cy+w),(cx+w,cy+w)], fill=0)
        draw.polygon([(cx-size,cy),(cx-w,cy-w),(cx-w,cy+w)], fill=0)
        draw.polygon([(cx+size,cy),(cx+w,cy-w),(cx+w,cy+w)], fill=0)
        f = font or load_font(14)
        draw.text((cx-5,cy-size-14),"N",font=f,fill=0)
        draw.text((cx-5,cy+size+2),"S",font=f,fill=0)
        draw.text((cx-size-12,cy-6),"W",font=f,fill=0)
        draw.text((cx+size+6, cy-6),"E",font=f,fill=0)
