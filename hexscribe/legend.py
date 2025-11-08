# hexscribe/legend.py
from PIL import ImageDraw

class TrailLegend:
    """
    Compact legend rendered on the left panel near the right edge.
    Rows: Path, Difficult, Dangerous, Special (dashed).
    """

    def __init__(self):
        self.icon_w = 22
        self.icon_h = 22
        self.row_gap = 8
        self.icon_gap = 8   # space between text and icon

    # --- icon helpers ---
    def _draw_icon_box(self, d: ImageDraw.ImageDraw, x, y, w, h):
        d.rectangle([x, y, x + w, y + h], outline=0, width=2)

    def _dash_line(self, d: ImageDraw.ImageDraw, a, b, dash=6, gap=5, width=2):
        (x1, y1), (x2, y2) = a, b
        dx, dy = x2 - x1, y2 - y1
        dist = (dx*dx + dy*dy) ** 0.5
        if dist <= 1e-6:
            return
        ux, uy = dx / dist, dy / dist
        pos = 0.0
        draw_on = True
        while pos < dist:
            seg = min(dash if draw_on else gap, dist - pos)
            if draw_on:
                sx, sy = x1 + ux * pos, y1 + uy * pos
                ex, ey = x1 + ux * (pos + seg), y1 + uy * (pos + seg)
                d.line([(sx, sy), (ex, ey)], fill=0, width=width)
            pos += seg
            draw_on = not draw_on

    def _draw_path_icon(self, d, x, y, w, h):
        cy = y + h // 2
        d.line([(x + 4, cy), (x + w - 4, cy)], fill=0, width=2)

    def _draw_difficult_icon(self, d, x, y, w, h):
        cy = y + h // 2
        d.line([(x + 4, cy), (x + w - 4, cy)], fill=0, width=2)
        step = 6
        t = x + 7
        while t <= x + w - 7:
            d.line([(t, cy - 5), (t, cy + 5)], fill=0, width=2)
            t += step

    def _draw_danger_icon(self, d, x, y, w, h):
        cy = y + h // 2
        d.line([(x + 4, cy), (x + w - 4, cy)], fill=0, width=2)
        step = 10
        t = x + 9
        barb = 5
        while t <= x + w - 9:
            left  = (t - barb, cy - barb)
            tip   = (t, cy)
            right = (t - barb, cy + barb)
            d.line([left, tip, right], fill=0, width=2)
            t += step

    def _draw_special_icon(self, d, x, y, w, h):
        cy = y + h // 2
        self._dash_line(d, (x + 4, cy), (x + w - 4, cy), dash=8, gap=6, width=2)

    # --- public ---
    def draw(self,
             d: ImageDraw.ImageDraw,
             panel_right_inner: int,
             hex_right_edge: int,
             panel_bottom: int,
             hex_center_y: int,
             hex_R: int,
             push_from_hex: int = 8,
             top_min_above_hex: int = 24):
        """
        Places legend near the right edge of the left panel, respecting hex clearance.
        panel_right_inner : x-position we want to hug (distance from split side)
        hex_right_edge    : rightmost pixel of the big hex
        push_from_hex     : min pixels to keep off the hex
        """
        # Horizontal position
        right_target = max(panel_right_inner, hex_right_edge + push_from_hex)
        x_icon = right_target - self.icon_w

        labels  = ["Path", "Difficult", "Dangerous", "Special"]
        drawers = [self._draw_path_icon,
                   self._draw_difficult_icon,
                   self._draw_danger_icon,
                   self._draw_special_icon]

        # Vertical placement
        needed_h = self.icon_h * 4 + self.row_gap * 3
        top_y = min(panel_bottom - needed_h,
                    hex_center_y + hex_R - self.icon_h - 18)
        top_y = max(top_y, hex_center_y - hex_R + top_min_above_hex)

        y = top_y
        for label, draw_icon in zip(labels, drawers):
            tw = d.textbbox((0, 0), label)[2]
            th = d.textbbox((0, 0), label)[3]
            tx = x_icon - self.icon_gap - tw
            ty = y + (self.icon_h - th) // 2
            d.text((tx, ty), label, fill=0)
            self._draw_icon_box(d, x_icon, y, self.icon_w, self.icon_h)
            draw_icon(d, x_icon, y, self.icon_w, self.icon_h)
            y += self.icon_h + self.row_gap
