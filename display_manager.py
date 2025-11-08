from PIL import Image, ImageDraw, ImageFont, ImageOps
import math, os, random
from typing import List, Tuple, Optional, Dict, Set
from settings import WIDTH, HEIGHT, MARGIN, SPLIT_X, FONT_CANDIDATES

# ====== TWEAK ME ======
CELLS_ACROSS     = 6
LEFT_PAD_INNER   = 16
RIGHT_PAD_INNER  = 16
TOP_PAD_INNER    = 8
LINE_SPACING_PX  = 4
MAX_TRAILS       = 8
NO_OVERLAP_DIST  = 16     # min spacing between trails (px)
DIAMOND_SCALE    = 0.55
SPECIAL_FREQ     = 2.6
SPECIAL_AMP      = 3.2

# Legend tuning
LEGEND_SIZE      = 20      # square sample size
LEGEND_GAP       = 6
LEGEND_BOX_PAD_R = 4       # extra padding from the left-panel border
LEGEND_TXT_GAP   = 4       # gap between label and sample box
LEGEND_MIN_GAP_HEX = 14    # min pixels between legend and hex map
# ======================

# ---------- TEXT ----------
def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)

def wrap_to_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_px: int):
    words = (text or "").split()
    lines, line = [], []
    for w in words:
        cand = (" ".join(line + [w])).strip()
        if not cand:
            line = [w]; continue
        tw, _ = measure_text(draw, cand, font)
        if tw <= max_px or not line:
            line = cand.split()
        else:
            lines.append(" ".join(line)); line = [w]
    if line: lines.append(" ".join(line))
    return lines or ["(description placeholder)"]

# ---------- FONTS ----------
def load_font(size: int = 16) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def load_blackletter(size: int = 34) -> ImageFont.FreeTypeFont:
    candidates = [
        "Berkahi Blackletter.ttf","./Berkahi Blackletter.ttf","./fonts/Berkahi Blackletter.ttf",
        "/usr/share/fonts/truetype/Berkahi Blackletter.ttf","/usr/local/share/fonts/Berkahi Blackletter.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return load_font(size)

FONT_GOTHIC = load_blackletter(34)
FONT_MED    = load_font(18)
FONT_SM     = load_font(14)
FONT_NUM    = load_font(16)

# ---------- GEOM ----------
def lerp(a: Tuple[float,float], b: Tuple[float,float], t: float) -> Tuple[float,float]:
    return (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)

def perp_unit(a: Tuple[float,float], b: Tuple[float,float]) -> Tuple[float,float]:
    dx, dy = b[0]-a[0], b[1]-a[1]
    L = math.hypot(dx, dy) or 1.0
    return (-dy/L, dx/L)

def dot(a,b): return a[0]*b[0] + a[1]*b[1]
def dist2(p,q): return (p[0]-q[0])**2 + (p[1]-q[1])**2
def clamp(v,a,b): return max(a, min(b, v))

def seg_dist_to_point_sq(a: Tuple[float,float], b: Tuple[float,float], p: Tuple[float,float]) -> float:
    ap = (p[0]-a[0], p[1]-a[1])
    ab = (b[0]-a[0], b[1]-a[1])
    ab2 = ab[0]*ab[0] + ab[1]*ab[1]
    if ab2 == 0: return dist2(a,p)
    t = clamp(dot(ap,ab)/ab2, 0.0, 1.0)
    proj = (a[0] + ab[0]*t, a[1] + ab[1]*t)
    return dist2(proj, p)

def draw_diamond_label(d: ImageDraw.ImageDraw, cx: int, cy: int, size_px: int,
                       text: str, font: ImageFont.FreeTypeFont):
    pts = [(cx, cy - size_px), (cx + size_px, cy), (cx, cy + size_px), (cx - size_px, cy)]
    d.polygon(pts, fill=0, outline=0)
    tw, th = measure_text(d, text, font)
    d.text((cx - tw/2, cy - th/2), text, font=font, fill=1)

# ---------- DISPLAY ----------
class DisplayManager:
    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.W, self.H = width, height
        self.last_trails = []
        self._diamond_r = 10
        self._area_centers: List[Tuple[int,int]] = []
        self._hex_geom = None  # (CX, CY, R)

    def render_hex_screen(
        self, hex_id: str, subtitle: str, description: str,
        features: List[Tuple[str, str]], marks: Optional[List[object]] = None
    ) -> Image.Image:

        img = Image.new("1", (self.W, self.H), 1)
        d = ImageDraw.Draw(img)

        # Frame + split
        d.rectangle([MARGIN, MARGIN, self.W - MARGIN, self.H - MARGIN], outline=0, width=2)
        d.line([(SPLIT_X, MARGIN), (SPLIT_X, self.H - MARGIN)], fill=0, width=2)

        grid_top = self._draw_left_header_fullwidth(d, hex_id, description)
        area_centers = self._draw_left_hex_with_clip(d, marks, grid_top)
        self._area_centers = area_centers[:]
        self._draw_right_features(d, features)

        self.last_trails = []
        if area_centers:
            self._draw_trails(d, area_centers)

        self._draw_left_panel_vertical_legend(d)  # vertical legend in left pane
        return img

    # ----- header
    def _draw_left_header_fullwidth(self, d: ImageDraw.ImageDraw, hex_id: str, description: str) -> int:
        left_x   = MARGIN + LEFT_PAD_INNER
        right_x  = SPLIT_X - RIGHT_PAD_INNER
        max_px   = right_x - left_x
        title = f"HEX: {hex_id}"
        d.text((left_x, MARGIN + TOP_PAD_INNER), title, font=FONT_GOTHIC, fill=0)
        _, th = measure_text(d, title, FONT_GOTHIC)
        desc_y = MARGIN + TOP_PAD_INNER + th + 6
        lines  = wrap_to_pixels(d, description, FONT_SM, max_px)
        y = desc_y
        _, lh = measure_text(d, "Ag", FONT_SM)
        for line in lines:
            d.text((left_x, y), line, font=FONT_SM, fill=0)
            y += lh + LINE_SPACING_PX
        return y + 6

    # ----- right features
    def _draw_right_features(self, d: ImageDraw.ImageDraw, features: List[Tuple[str, str]]):
        header_y = MARGIN + 8
        d.text((SPLIT_X + 16, header_y), "Features", font=FONT_MED, fill=0)
        d.line([(SPLIT_X + 16, header_y + 20), (self.W - MARGIN - 8, header_y + 20)], fill=0, width=2)
        y = header_y + 30
        for icon_name, label in features:
            self._draw_icon(d, icon_name, (SPLIT_X + 16, y))
            d.text((SPLIT_X + 38, y + 1), label, font=FONT_SM, fill=0)
        # no extra y increment needed here; list is short

    # ----- left grid
    def _draw_left_hex_with_clip(self, d, marks=None, grid_top=None):
        left_pad   = MARGIN + LEFT_PAD_INNER
        right_pad  = SPLIT_X - RIGHT_PAD_INNER
        if grid_top is None: grid_top = MARGIN + TOP_PAD_INNER
        bottom_pad = self.H - MARGIN - 8
        hex_w      = right_pad - left_pad
        hex_h      = bottom_pad - grid_top
        CX         = left_pad + hex_w // 2
        CY         = grid_top + hex_h // 2
        R          = int(min(hex_w, hex_h) / 2) - 6
        SQ3        = math.sqrt(3)

        self._hex_geom = (CX, CY, R)

        C = max(2, int(CELLS_ACROSS))
        s = (4.0 * R) / (3.0 * C + 1.0) * 0.985

        def hex_poly(xc, yc, rad):
            return [(xc + rad * math.cos(k), yc + rad * math.sin(k))
                    for k in (0, math.pi/3, 2*math.pi/3, math.pi, 4*math.pi/3, 5*math.pi/3)]

        def axial_centers():
            q_max = int(R / (1.5 * s)) + 3
            r_max = int(R / (SQ3 * s)) + 3
            pts = []
            for q in range(-q_max, q_max + 1):
                for r in range(-r_max, r_max + 1):
                    x = CX + (1.5 * s) * q
                    y = CY + (SQ3 * s) * (r + q / 2.0)
                    pts.append((x, y))
            return pts

        centers_f = axial_centers()

        # clip to big hex
        mask = Image.new("1", (self.W, self.H), 0)
        md   = ImageDraw.Draw(mask)
        big_hex_pts = hex_poly(CX, CY, R)
        md.polygon(big_hex_pts, fill=1, outline=1)

        grid = Image.new("1", (self.W, self.H), 1)
        gd   = ImageDraw.Draw(grid)
        for (x, y) in centers_f:
            gd.polygon(hex_poly(x, y, s), outline=0)

        gridL = grid.convert("L"); maskL = mask.convert("L")
        clipped = Image.new("L", (self.W, self.H), 255)
        clipped.paste(gridL, (0, 0), maskL)
        lines_mask = ImageOps.invert(clipped).point(lambda p: 255 if p > 128 else 0)
        d.bitmap((0, 0), lines_mask.convert("1"), fill=0)
        d.polygon(big_hex_pts, outline=0)

        # diamonds
        interior = [(i, c) for i, c in enumerate(centers_f) if self._point_in_hex(CX, CY, R - s * 1.2, c[0], c[1])]
        mark_pairs = []
        if marks:
            for m in marks:
                if isinstance(m, int):
                    mark_pairs.append((m, random.randint(1, 5)))
                elif isinstance(m, (tuple, list)):
                    if len(m) == 2 and isinstance(m[0], int) and isinstance(m[1], int):
                        idx, lab = m; lab = max(1, min(5, lab))
                        mark_pairs.append((idx, lab))
                    elif len(m) == 2 and all(isinstance(v, (int, float)) for v in m):
                        fx, fy = m
                        px = left_pad + fx * (right_pad - left_pad)
                        py = grid_top + fy * (bottom_pad - grid_top)
                        nearest = min(range(len(centers_f)),
                                      key=lambda k: (centers_f[k][0]-px)**2 + (centers_f[k][1]-py)**2)
                        mark_pairs.append((nearest, random.randint(1, 5)))

        if not mark_pairs:
            random.shuffle(interior)
            k = random.randint(1, min(MAX_TRAILS, len(interior)))
            picks = random.sample(interior, k)
            mark_pairs = [(i, random.randint(1, 5)) for i, _ in picks]

        area_centers: List[Tuple[int,int]] = []
        diamond_size = int(max(8, s * DIAMOND_SCALE))
        self._diamond_r = diamond_size
        for idx, lab in mark_pairs:
            if 0 <= idx < len(centers_f):
                cx_f, cy_f = centers_f[idx]
                cx, cy = int(round(cx_f)), int(round(cy_f))
                if not self._point_in_hex(CX, CY, R - s * 0.9, cx, cy):
                    continue
                area_centers.append((cx, cy))
                draw_diamond_label(d, cx, cy, diamond_size, str(lab), FONT_NUM)

        # Compass
        compass_cx = MARGIN + 52
        compass_cy = self.H - MARGIN - 48
        self._draw_compass(d, compass_cx, compass_cy, size=20)

        return area_centers

    def _point_in_hex(self, cx, cy, R, x, y):
        px = abs(x - cx); py = abs(y - cy)
        if px > R or py > R * math.sqrt(3) / 2 + 1: return False
        return (math.sqrt(3) * px + py) <= math.sqrt(3) * R + 1

    # ----- TRAILS: detours + unique edges + avoid overlap
    def _draw_trails(self, d: ImageDraw.ImageDraw, centers: List[Tuple[int,int]]):
        if len(centers) < 2: return
        pts = centers[:]
        random.shuffle(pts)
        segs = random.randint(1, min(MAX_TRAILS, len(pts) - 1))

        used_edges: Dict[Tuple[int,int], Set[str]] = {c:set() for c in pts}
        existing_samples: List[Tuple[float, float]] = []

        def trail_style() -> str:
            roll = random.randint(1, 8)
            if   1 <= roll <= 4: return "path"
            elif 5 <= roll <= 6: return "difficult"
            elif roll == 7:      return "dangerous"
            else:                return "special"

        for i in range(segs):
            a, b = pts[i], pts[i+1]
            style = trail_style()
            pa, ea = self._attach_point_on_diamond(a, b, used_edges[a]); used_edges[a].add(ea)
            pb, eb = self._attach_point_on_diamond(b, a, used_edges[b]); used_edges[b].add(eb)

            route_pts = self._route_with_detours(pa, pb, exclude={a,b}, clearance=self._diamond_r+4)

            hop_samples: List[Tuple[float,float]] = []
            for h in range(len(route_pts)-1):
                best = None
                for attempt in range(8):
                    seg = self._sample_curve(route_pts[h], route_pts[h+1], style, attempt)
                    if self._far_from_existing(seg, existing_samples, NO_OVERLAP_DIST):
                        best = seg; break
                hop_samples.extend(best or seg)

            self._stroke_trail(d, hop_samples, style)
            existing_samples.extend(hop_samples)
            self.last_trails.append((style, hop_samples))

    def _edge_for_direction(self, vec: Tuple[float,float], taken: Set[str]) -> str:
        dx, dy = vec
        primary = 'E' if abs(dx) >= abs(dy) and dx >= 0 else \
                  'W' if abs(dx) >= abs(dy) else \
                  'S' if dy >= 0 else 'N'
        order = ['N','E','S','W']
        idx = order.index(primary)
        for k in range(4):
            e = order[(idx + k) % 4]
            if e not in taken:
                return e
        return primary

    def _attach_point_on_diamond(self, c: Tuple[int,int], other: Tuple[int,int], taken: Set[str]) -> Tuple[Tuple[float,float], str]:
        r = self._diamond_r / math.sqrt(2)
        dx, dy = other[0] - c[0], other[1] - c[1]
        edge = self._edge_for_direction((dx, dy), taken)
        if edge == 'E':  p = (c[0] + r, c[1])
        elif edge == 'W': p = (c[0] - r, c[1])
        elif edge == 'N': p = (c[0], c[1] - r)
        else:             p = (c[0], c[1] + r)
        off = 1.8
        if edge == 'E':  p = (p[0] + off, p[1])
        elif edge == 'W': p = (p[0] - off, p[1])
        elif edge == 'N': p = (p[0], p[1] - off)
        else:             p = (p[0], p[1] + off)
        return p, edge

    def _route_with_detours(self, a: Tuple[float,float], b: Tuple[float,float],
                            exclude: Set[Tuple[int,int]], clearance: float):
        pts = [a, b]
        if random.random() < 0.35:
            mid = lerp(a, b, random.uniform(0.35, 0.65))
            nx, ny = perp_unit(a, b)
            amp = random.uniform(clearance*0.6, clearance*1.2)
            mid = (mid[0] + nx*amp*(1 if random.random()<0.5 else -1),
                   mid[1] + ny*amp*(1 if random.random()<0.5 else -1))
            pts = [a, mid, b]

        changed = True
        max_loops = 6
        loops = 0
        while changed and loops < max_loops:
            changed = False
            loops += 1
            out = [pts[0]]
            for i in range(len(pts)-1):
                p, q = pts[i], pts[i+1]
                if not self._segment_hits_any_diamond(p, q, exclude, clearance):
                    out.append(q); continue
                c = self._nearest_blocking_center(p, q, exclude, clearance)
                if c is None:
                    out.append(q); continue
                left_way  = self._tangent_waypoint(p, q, c, clearance, side=+1)
                right_way = self._tangent_waypoint(p, q, c, clearance, side=-1)
                wp = left_way if random.random() < 0.5 else right_way
                out.append(wp); out.append(q)
                changed = True
            pts = out
        return pts

    def _segment_hits_any_diamond(self, p, q, exclude, clearance) -> bool:
        clear2 = clearance*clearance
        for c in self._area_centers:
            if c in exclude: continue
            if seg_dist_to_point_sq(p, q, c) < clear2:
                return True
        return False

    def _nearest_blocking_center(self, p, q, exclude, clearance):
        clear2 = clearance*clearance
        best_c, best_d = None, 1e18
        for c in self._area_centers:
            if c in exclude: continue
            d2 = seg_dist_to_point_sq(p, q, c)
            if d2 < clear2 and d2 < best_d:
                best_d, best_c = d2, c
        return best_c

    def _tangent_waypoint(self, p, q, c, clearance, side=+1):
        ab = (q[0]-p[0], q[1]-p[1])
        ap = (c[0]-p[0], c[1]-p[1])
        ab2= ab[0]*ab[0] + ab[1]*ab[1] or 1.0
        t  = clamp(dot(ap,ab)/ab2, 0.0, 1.0)
        closest = (p[0] + ab[0]*t, p[1] + ab[1]*t)
        vx, vy = closest[0]-c[0], closest[1]-c[1]
        L = math.hypot(vx, vy) or 1.0
        ux, uy = vx/L, vy/L
        nx, ny = -uy, ux
        phi = clearance + 3.0
        return (c[0] + ux*clearance + nx*phi*side,
                c[1] + uy*clearance + ny*phi*side)

    def _sample_curve(self, a: Tuple[float,float], b: Tuple[float,float], style: str, attempt: int):
        mid = lerp(a, b, 0.5)
        nx, ny = perp_unit(a, b)
        base_amp = 10 if style != "special" else 16
        sign = -1 if attempt % 2 else 1
        amp = base_amp * (1.0 + 0.35 * (attempt // 2))
        ctrl = (mid[0] + nx * amp * sign, mid[1] + ny * amp * sign)

        def quad(t):
            p0, p1, p2 = a, ctrl, b
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            return (x, y)

        samples = [quad(t/30.0) for t in range(31)]

        if style == "special":
            wob_pts = []
            for idx in range(len(samples)):
                p = samples[idx]
                q = samples[min(idx+1, len(samples)-1)]
                n = perp_unit(p, q)
                wob = math.sin(idx * SPECIAL_FREQ) * SPECIAL_AMP
                wob_pts.append((p[0] + n[0]*wob, p[1] + n[1]*wob))
            samples = wob_pts
        return samples

    def _far_from_existing(self, samples, existing, min_dist_px: int) -> bool:
        if not existing: return True
        md2 = float(min_dist_px) ** 2
        for x, y in samples:
            for ex, ey in existing:
                if (x-ex)*(x-ex) + (y-ey)*(y-ey) < md2:
                    return False
        return True

    def _stroke_trail(self, d: ImageDraw.ImageDraw, samples, style: str):
        d.line(samples, fill=0, width=2)
        if style == "difficult":
            for t in range(3, len(samples)-2, 4):
                p = samples[t-1]; q = samples[t+1]
                n = perp_unit(p, q); tick = 5
                d.line([(samples[t][0]-n[0]*tick, samples[t][1]-n[1]*tick),
                        (samples[t][0]+n[0]*tick, samples[t][1]+n[1]*tick)], fill=0, width=2)
        elif style == "dangerous":
            for t in range(4, len(samples)-3, 5):
                p = samples[t-2]; q = samples[t+2]
                n = perp_unit(p, q)
                dirx, diry = (q[0]-p[0], q[1]-p[1])
                L = math.hypot(dirx, diry) or 1.0
                ux, uy = dirx/L, diry/L
                base = samples[t]; barb = 6
                left  = (base[0] - ux*barb + n[0]*barb, base[1] - uy*barb + n[1]*barb)
                right = (base[0] - ux*barb - n[0]*barb, base[1] - uy*barb - n[1]*barb)
                d.line([left, base, right], fill=0, width=2)

    # ----- Icons (feature list)
    def _draw_icon(self, draw: ImageDraw.ImageDraw, name: str, xy: Tuple[int, int]):
        x, y = xy
        n = name.lower()
        if n in ("skull", "undead"):
            draw.ellipse([x + 2, y + 2, x + 14, y + 14], outline=0, width=2)
            draw.rectangle([x + 6, y + 9, x + 10, y + 12], fill=0)
            draw.point((x + 6, y + 6), 0); draw.point((x + 10, y + 6), 0)
        elif n in ("anchor", "smuggling", "dock"):
            draw.line([(x + 8, y + 2), (x + 8, y + 11)], fill=0, width=2)
            draw.arc([x + 1, y + 8, x + 15, y + 16], 10, 170, fill=0, width=2)
            draw.ellipse([x + 6, y, x + 10, y + 4], outline=0, width=2)
        elif n in ("cross", "templar", "church"):
            draw.rectangle([x + 6, y + 2, x + 10, y + 14], fill=0)
            draw.rectangle([x + 3, y + 6, x + 13, y + 9], fill=0)
        elif n in ("keep", "tower", "fort"):
            draw.rectangle([x + 3, y + 6, x + 13, y + 14], outline=0, width=2)
            draw.rectangle([x + 6, y + 9, x + 10, y + 14], fill=0)
            draw.polygon([(x + 3, y + 6), (x + 8, y + 2), (x + 13, y + 6)], outline=0)
        else:
            draw.rectangle([x + 4, y + 4, x + 12, y + 12], outline=0, width=2)

    # ----- Compass
    def _draw_compass(self, d: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 20):
        arrow_len = size
        arrow_wid = max(3, size // 3)
        font = FONT_SM
        d.polygon([(cx, cy - arrow_len), (cx - arrow_wid, cy - arrow_wid),
                   (cx + arrow_wid, cy - arrow_wid)], fill=0)
        d.polygon([(cx, cy + arrow_len), (cx - arrow_wid, cy + arrow_wid),
                   (cx + arrow_wid, cy + arrow_wid)], fill=0)
        d.polygon([(cx - arrow_len, cy), (cx - arrow_wid, cy - arrow_wid),
                   (cx - arrow_wid, cy + arrow_wid)], fill=0)
        d.polygon([(cx + arrow_len, cy), (cx + arrow_wid, cy - arrow_wid),
                   (cx + arrow_wid, cy + arrow_wid)], fill=0)
        d.text((cx - 5, cy - arrow_len - 14), "N", font=font, fill=0)
        d.text((cx - 5, cy + arrow_len + 2),  "S", font=font, fill=0)
        d.text((cx - arrow_len - 12, cy - 6), "W", font=font, fill=0)
        d.text((cx + arrow_len + 6,  cy - 6), "E", font=font, fill=0)

    # ----- Vertical legend in left panel (right-aligned labels close to boxes)
    def _draw_left_panel_vertical_legend(self, d: ImageDraw.ImageDraw):
        if not self._hex_geom: return
        CX, CY, R = self._hex_geom
        box = LEGEND_SIZE
        gap = LEGEND_GAP

        # Target the legend near the right border of the left panel.
        desired_right = SPLIT_X - RIGHT_PAD_INNER - LEGEND_BOX_PAD_R
        hex_right     = CX + R

        # Ensure a minimum spacing from the hex map.
        min_left_for_legend = hex_right + LEGEND_MIN_GAP_HEX
        # Compute where the sample box would start if we anchor to desired_right:
        sample_left = desired_right - box
        if sample_left < min_left_for_legend:
            # Push the legend rightwards (toward split) until it clears the hex.
            desired_right = min_left_for_legend + box
            sample_left   = desired_right - box

        # Vertical placement: below the hex, but keep inside panel.
        pane_bottom = self.H - MARGIN - 10
        total_h = 4*box + 3*gap
        y_min = int(CY + R * 0.18)
        y0 = max(y_min, pane_bottom - total_h)

        kinds = [("path","Path"), ("difficult","Difficult"), ("dangerous","Dangerous"), ("special","Special")]

        for i, (kind_key, text_label) in enumerate(kinds):
            by = y0 + i*(box + gap)

            # sample square (right-aligned to desired_right)
            left = sample_left
            right = desired_right
            d.rectangle([left, by, right, by + box], outline=0, width=1)

            # right-justified label, tucked close to the box
            tw, th = measure_text(d, text_label, FONT_SM)
            tx = left - LEGEND_TXT_GAP - tw
            ty = by + (box - th)//2
            d.text((tx, ty), text_label, font=FONT_SM, fill=0)

            # sample stroke inside square
            start = (left + 4, by + box - 4)
            end   = (right - 4, by + 4)
            samples = []
            n = 16
            for k in range(n+1):
                t = k/n
                px = start[0] + (end[0]-start[0]) * t
                py = start[1] + (end[1]-start[1]) * t
                if kind_key == "special":
                    py += math.sin(t * 10.0) * 2.0
                samples.append((px, py))
            self._stroke_trail(d, samples, kind_key)
