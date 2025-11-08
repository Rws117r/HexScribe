# hexscribe/renderer.py
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple, Optional, Callable
import random
from pathlib import Path

from .hexgrid import HexGrid
from .trails import TrailRouter
from .legend import TrailLegend
from .layout import UILayout


# ---------- Font helpers ----------
def _fonts_root() -> Path:
    # HEXSCRIBE/fonts/
    return Path(__file__).resolve().parents[1] / "fonts"

def _load_var_font(name: str, size: int):
    p = _fonts_root() / name
    if p.exists():
        try:
            return ImageFont.truetype(str(p), size=size)
        except Exception:
            return None
    return None

def _jost(size: int, weight: int):
    """
    Load Jost variable font at a specific wght (100–900).
    Title / diamond numbers use 850 (ExtraBold).
    """
    f = _load_var_font("Jost-VariableFont_wght.ttf", size)
    if not f:
        return ImageFont.load_default()
    try:
        if hasattr(f, "set_variation_by_axes"):
            f.set_variation_by_axes([max(100, min(900, weight))])
    except Exception:
        pass
    return f

def _libre_caslon(size: int):
    f = _load_var_font("LibreCaslonText-Regular.ttf", size)
    return f or ImageFont.load_default()


class HexScreenRenderer:
    """
    Renders the Hex Scrawl screen with interactivity.
    - Title/Type: Jost variable (ExtraBold/SemiBold), dynamic width fit
    - Body: Libre Caslon Text (left-aligned, 1.5x line spacing)
    - Diamonds: numbers in Jost ExtraBold (white), perfectly centered
    - Trails: drawn FIRST; diamonds/numbers redrawn ON TOP to prevent overlap
    """

    def __init__(self, layout: UILayout = UILayout()):
        self.L = layout
        self.W, self.H = self.L.width, self.L.height

        # fonts
        self.font_body = _libre_caslon(self.L.body_size)
        self.font_left_title_size = self.L.title_size
        self.font_right_title_size = self.L.title_size
        self.font_type_size = max(self.L.feature_size, 12)

        # subsystems
        self.grid   = HexGrid(cells_across=self.L.cells_across,
                              diamond_scale=self.L.diamond_scale)
        self.router = TrailRouter()
        self.legend = TrailLegend()

        # last-frame state
        self.last_diamonds: List[Tuple[int, int, int]] = []
        self.last_marks: List[Tuple[int, int]] = []

    # ---------- text helpers ----------
    def _measure(self, d: ImageDraw.ImageDraw, text: str, font):
        b = d.textbbox((0, 0), text, font=font)
        return b[2] - b[0], b[3] - b[1]

    def _wrap(self, d: ImageDraw.ImageDraw, text: str, font, max_px: int):
        words = (text or "").split()
        lines, cur = [], []
        for w in words:
            cand = (" ".join(cur + [w])).strip()
            if not cand:
                cur = [w]; continue
            tw, _ = self._measure(d, cand, font)
            if tw <= max_px or not cur:
                cur = cand.split()
            else:
                lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines or ["(description placeholder)"]

    def _fit_font(self, d: ImageDraw.ImageDraw, text: str, maker, max_width: int, max_size: int, min_size: int):
        size = max_size
        while size > min_size:
            f = maker(size)
            w, _ = self._measure(d, text, f)
            if w <= max_width:
                return f
            size -= 1
        return maker(min_size)

    # ---------- draw helpers ----------
    def _draw_cursor(self, d: ImageDraw.ImageDraw, x: int, y: int, r: int):
        R = int(r + 6)
        d.ellipse([x - R, y - R, x + R, y + R], outline=0, width=2)

    def _draw_centered_diamond_number(self, d: ImageDraw.ImageDraw, x: int, y: int, r: int, text: str, font):
        # Mask interior (remove any previous label) and redraw outline for crisp edges
        poly = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
        d.polygon(poly, fill=0)
        d.line(poly + [poly[0]], fill=0, width=2)
        # Centered white number
        try:
            d.text((x, y), text, font=font, fill=1, anchor="mm")
        except TypeError:
            tw, th = self._measure(d, text, font)
            d.text((x - tw//2, y - th//2), text, font=font, fill=1)

    # ---------- main render ----------
    def render(self,
               hex_id: str,
               description: str,
               features,  # kept for API compat (unused)
               marks: Optional[List[Tuple[int, int]]] = None,
               selected_idx: Optional[int] = None,
               feature_picker: Optional[Callable[[int], dict]] = None):
        L = self.L
        img = Image.new("1", (self.W, self.H), 1)
        d   = ImageDraw.Draw(img)

        # frame + split
        d.rectangle([L.margin, L.margin, self.W - L.margin, self.H - L.margin], outline=0, width=2)
        d.line([(L.split_x, L.margin), (L.split_x, self.H - L.margin)], fill=0, width=2)

        # left header (Jost ExtraBold, fitted to column)
        left_x  = L.margin + L.left_pad
        right_x = L.split_x - L.right_pad
        max_px  = right_x - left_x
        left_title_font = self._fit_font(d, f"HEX:{hex_id}", lambda s: _jost(s, 850), max_width=max_px, max_size=self.font_left_title_size, min_size=14)
        title = f"HEX:{hex_id}"
        d.text((left_x, L.margin + L.top_pad), title, font=left_title_font, fill=0)
        _, th = self._measure(d, title, left_title_font)

        # left description
        y = L.margin + L.top_pad + th + 6
        line_gap = 1.4
        for line in self._wrap(d, description, self.font_body, max_px):
            d.text((left_x, y), line, font=self.font_body, fill=0)
            y += int(self._measure(d, "Ag", self.font_body)[1] * line_gap)

        grid_top = y + L.hex_inset_top

        # hex grid
        centers, (cx, cy, R) = self.grid.draw_grid(
            d,
            left=L.margin + L.left_pad + L.hex_inset_sides,
            top=grid_top,
            right=L.split_x - L.right_pad - L.hex_inset_sides,
            bottom=self.H - L.margin - L.hex_inset_bottom
        )

        # diamonds (layout)
        diamond_centers: List[Tuple[int, int]] = []
        labels: List[int] = []
        chosen_marks: List[Tuple[int, int]] = []  # (center_index, label)

        if marks:
            for idx, label in marks:
                if 0 <= idx < len(centers):
                    x, y = centers[idx]
                    # initial draw (will be redrawn on top after trails)
                    self.grid.draw_diamond(d, int(x), int(y), int(label))
                    diamond_centers.append((int(x), int(y)))
                    labels.append(int(label))
                    chosen_marks.append((int(idx), int(label)))
        else:
            k = random.randint(3, min(6, len(centers)))
            picked = random.sample(range(len(centers)), k)
            for idx in picked:
                x, y = centers[idx]
                label = random.randint(1, 5)
                self.grid.draw_diamond(d, int(x), int(y), label)
                diamond_centers.append((int(x), int(y)))
                labels.append(label)
                chosen_marks.append((idx, label))

        # remember
        self.last_diamonds = [(x, y, lab) for (x, y), lab in zip(diamond_centers, labels)]
        self.last_marks = chosen_marks[:]

        # TRAILS FIRST (deterministic per layout)
        import random as _random
        _state = _random.getstate()
        try:
            _seed = hash(tuple(chosen_marks)) & 0xFFFFFFFF
            _random.seed(_seed)
            self.router._grid_ref = self.grid
            self.router.draw_trails(
                d,
                diamond_centers=diamond_centers,
                diamond_radius=self.grid.diamond_r,  # geometry radius
                max_trails=4,
            )
        finally:
            _random.setstate(_state)

        # Bring diamonds back on TOP so trails never overlap them
        for (x, y), lab in zip(diamond_centers, labels):
            self.grid.draw_diamond(d, int(x), int(y), int(lab))

        # Numbers (white) centered on top
        num_font = _jost(int(self.grid.diamond_r * 1.2), 850)
        for (x, y), lab in zip(diamond_centers, labels):
            self._draw_centered_diamond_number(d, int(x), int(y), int(self.grid.diamond_r), str(lab), num_font)

        # cursor highlight
        if selected_idx is not None and 0 <= selected_idx < len(diamond_centers):
            sx, sy = diamond_centers[selected_idx]
            self._draw_cursor(d, sx, sy, self.grid.diamond_r)

        # compass
        self.grid.draw_compass(
            d,
            L.margin + L.compass_offset_x,
            self.H - L.margin - L.compass_offset_y,
            size=20,
            font=self.font_body
        )

        # ---------- Right panel: centered title/type, left-aligned body ----------
        header_y = L.margin + 8
        panel_left = L.split_x + 16
        panel_right = self.W - L.margin - 8
        panel_width = panel_right - panel_left

        # feature dict from picker (JSON-driven in your runner)
        feature_dict = None
        if feature_picker and selected_idx is not None and 0 <= selected_idx < len(labels):
            try:
                feature_dict = feature_picker(int(labels[selected_idx]))
            except Exception:
                feature_dict = None
        if not feature_dict:
            feature_dict = {"name":"Feature Name","type":"Feature Type","text":"text box with feature info","category":""}

        name_text = feature_dict.get("name","Feature")
        type_text = feature_dict.get("type","")
        body_text = feature_dict.get("text","")

        # Fit and draw centered title/type using Jost weights
        name_font = self._fit_font(d, name_text, lambda s: _jost(s, 850), panel_width, self.font_right_title_size, 14)
        type_font = self._fit_font(d, type_text, lambda s: _jost(s, 600), panel_width, self.font_type_size, 10)

        # Title
        name_w, name_h = self._measure(d, name_text, name_font)
        name_x = panel_left + (panel_width - name_w)//2
        d.text((name_x, header_y), name_text, font=name_font, fill=0)

        # Type with spacing
        type_y = header_y + name_h + 6
        type_w, type_h = self._measure(d, type_text, type_font)
        type_x = panel_left + (panel_width - type_w)//2
        d.text((type_x, type_y), type_text, font=type_font, fill=0)

        # Text box
        box_top = type_y + type_h + 12
        box_h   = int(self.H - L.margin - box_top - 8)
        box_rect = [panel_left, box_top, panel_left + panel_width, box_top + box_h]
        d.rectangle(box_rect, outline=0, width=2)

        # Body text LEFT-aligned with comfortable line gap
        pad = 10
        tx = box_rect[0] + pad
        ty = box_top + pad
        usable_w = panel_width - 2*pad
        body_lines = self._wrap(d, body_text, self.font_body, usable_w)
        lh = self._measure(d, "Ag", self.font_body)[1]
        for line in body_lines:
            d.text((tx, ty), line, font=self.font_body, fill=0)
            ty += int(lh * 1.5)

        # legend
        panel_right_inner = L.split_x - L.legend_right_margin - L.legend_safe_from_split
        panel_bottom      = self.H - L.margin - L.legend_bottom_margin
        self.legend.draw(
            d,
            panel_right_inner=panel_right_inner,
            hex_right_edge=int(cx + R),
            panel_bottom=panel_bottom,
            hex_center_y=cy,
            hex_R=R,
            push_from_hex=L.legend_push_from_hex,
            top_min_above_hex=L.legend_top_min_above_hex
        )

        return img
