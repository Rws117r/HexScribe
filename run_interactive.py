# run_interactive.py
import sys, math, pygame
from datetime import datetime
from pathlib import Path

from hexscribe import HexScreenRenderer, UILayout
from hexscribe.state import load_hex, save_hex, delete_hex
from hexscribe.types import COLUMNS, FEATURE_TYPES, KEY_TO_LABEL

HEX_ID = "1106"

UNKNOWN_FEATURE = {
    "name": "Unknown",
    "type": "Unexplored",
    "text": "Press Enter to explore.",
    "category": "",
}

# ---------- utils ----------
def fonts_root() -> Path:
    return Path(__file__).resolve().parent / "fonts"

def load_pygame_font(name: str, size: int, bold=False, italic=False) -> "pygame.font.Font":
    path = fonts_root() / name
    if path.exists():
        f = pygame.font.Font(str(path), size)
        f.set_bold(bold)
        f.set_italic(italic)
        return f
    f = pygame.font.SysFont("arial", size, bold=bold, italic=italic)
    return f

def _unit(dx, dy):
    m = math.hypot(dx, dy)
    if m == 0: return (0.0, 0.0)
    return (dx/m, dy/m)

def _pick_best(cands):
    cands.sort(key=lambda t: (-t[0], t[1]))
    return cands[0][2] if cands else None

def _next_index_by_direction(diamonds, sel, dx, dy):
    if not diamonds or sel < 0 or sel >= len(diamonds):
        return sel
    ox, oy, _ = diamonds[sel]
    ux, uy = _unit(dx, dy)
    forward, fallback = [], []
    for i, (x, y, _) in enumerate(diamonds):
        if i == sel: continue
        vx, vy = (x-ox), (y-oy)
        dist2 = vx*vx + vy*vy
        if dist2 == 0: continue
        dot = vx*ux + vy*uy
        angle_score = dot / math.sqrt(dist2)
        tup = (angle_score, dist2, i)
        (forward if dot>0 else fallback).append(tup)
    idx = _pick_best(forward) or _pick_best(fallback)
    return idx if idx is not None else sel

def make_json_feature_picker(hex_data_ref, selected_index_ref):
    def pick(_ignored):
        hex_data = hex_data_ref[0]
        sel = selected_index_ref[0]
        if not hex_data or "diamonds" not in hex_data: return UNKNOWN_FEATURE
        if sel is None or sel < 0 or sel >= len(hex_data["diamonds"]): return UNKNOWN_FEATURE
        d = hex_data["diamonds"][sel]
        if d.get("status") != "discovered": return UNKNOWN_FEATURE
        return {
            "name": d.get("name") or "(unnamed)",
            "type": d.get("type") or "",
            "text": d.get("text") or "",
            "category": "",
        }
    return pick

# ---------- Modal ----------
class ExploreModal:
    """Blocking modal with crisp fonts, overlay panel, columns picker, and wrapped notes."""
    def __init__(self, screen, ui, deck_value: int, initial=None):
        self.screen = screen
        self.ui = ui
        self.deck_value = deck_value
        self.initial = initial or {}
        self.active = True
        self.step = 0  # 0 draw, 1 name, 2 type, 3 notes, 4 confirm
        self.name = self.initial.get("name", "")
        init_key = self.initial.get("icon") or ""
        self.type_key = init_key if init_key in KEY_TO_LABEL else None
        self.notes = self.initial.get("text", "")
        # selection state for columns (col index, row index)
        self.col_idx = 0
        self.row_idx = 0

        # fonts (anti-aliasing OFF when rendering)
        pygame.font.init()
        self.font_header = load_pygame_font("Jost-VariableFont_wght.ttf", 30, bold=True)
        self.font_label  = load_pygame_font("Jost-VariableFont_wght.ttf", 20, bold=True)
        self.font_hint   = load_pygame_font("LibreCaslonText-Italic.ttf", 16, italic=True)
        self.font_text   = load_pygame_font("LibreCaslonText-Regular.ttf", 18)

        # layout
        W, H = ui.width, ui.height
        self.rect = pygame.Rect(W//2 - 320, H//2 - 220, 640, 440)
        self.pad = 18
        self.line_gap = 8

        # Build flat list for preselect if editing
        flat = [(c, r, key) for c, (_, items) in enumerate(COLUMNS) for r, (key, _label) in enumerate(items)]
        if self.type_key:
            for c, r, k in flat:
                if k == self.type_key:
                    self.col_idx, self.row_idx = c, r; break

    # --- text wrapping ---
    def _wrap(self, text: str, font: "pygame.font.Font", max_w: int):
        lines = []
        for para in text.split("\n"):
            words, cur = para.split(" "), ""
            for w in words:
                test = (cur + " " + w).strip()
                if font.size(test)[0] <= max_w:
                    cur = test
                else:
                    if cur: lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines or [""]

    # --- drawing helpers ---
    def _draw_overlay(self):
        # Do NOT blank the whole screen; draw only the panel so map shows behind.
        pygame.draw.rect(self.screen, (0,0,0), self.rect)           # black fill
        pygame.draw.rect(self.screen, (255,255,255), self.rect, 2)   # white border

    def _blit(self, txt, x, y, font, color=(255,255,255)):
        # anti-alias False for crisp edges
        surf = font.render(txt, False, color)
        self.screen.blit(surf, (x, y))
        return surf.get_width(), surf.get_height()

    def _blit_in_box(self, text, box, font):
        pad = 10
        wrapped = self._wrap(text, font, box.w - 2*pad)
        ty = box.y + pad
        line_h = font.get_height() + 4
        max_lines = (box.h - 2*pad) // line_h
        for ln in wrapped[-max_lines:]:
            surf = font.render(ln, False, (0,0,0))  # crisp, black
            self.screen.blit(surf, (box.x + pad, ty))
            ty += line_h

    # --- input handling ---
    def _handle_text_input(self, current: str, event, limit: int) -> str:
        if event.key == pygame.K_BACKSPACE:
            return current[:-1]
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return current + "\n"
        if event.unicode:
            ch = event.unicode
            if len(current) < limit and (31 < ord(ch) or ch in "\n\t"):
                return current + ch
        return current

    # --- modal main ---
    def run(self):
        clock = pygame.time.Clock()
        while self.active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.active = False
                    return None
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.active = False
                        return None

                    if self.step == 0:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.step = 1

                    elif self.step == 1:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            if self.name.strip():
                                self.step = 2
                        elif event.key == pygame.K_BACKSPACE:
                            self.name = self.name[:-1]
                        else:
                            if event.unicode and len(self.name) < 80:
                                self.name += event.unicode

                    elif self.step == 2:
                        # 3-column navigation
                        cols = COLUMNS
                        if event.key in (pygame.K_LEFT, pygame.K_a):
                            self.col_idx = (self.col_idx - 1) % len(cols)
                            self.row_idx = min(self.row_idx, len(cols[self.col_idx][1]) - 1)
                        elif event.key in (pygame.K_RIGHT, pygame.K_d):
                            self.col_idx = (self.col_idx + 1) % len(cols)
                            self.row_idx = min(self.row_idx, len(cols[self.col_idx][1]) - 1)
                        elif event.key in (pygame.K_UP, pygame.K_w):
                            self.row_idx = (self.row_idx - 1) % len(cols[self.col_idx][1])
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            self.row_idx = (self.row_idx + 1) % len(cols[self.col_idx][1])
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.type_key = cols[self.col_idx][1][self.row_idx][0]
                            self.step = 3

                    elif self.step == 3:
                        # Ctrl+Enter to confirm
                        if (event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)) and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                            self.step = 4
                        else:
                            self.notes = self._handle_text_input(self.notes, event, 4000)

                    elif self.step == 4:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            return {
                                "name": self.name.strip(),
                                "type": KEY_TO_LABEL.get(self.type_key, ""),
                                "text": self.notes.strip(),
                                "icon": self.type_key,
                            }
                        elif event.key == pygame.K_BACKSPACE:
                            self.step = 3

            # draw panel only (overlay)
            self._draw_overlay()
            x = self.rect.x + self.pad
            y = self.rect.y + self.pad

            if self.step == 0:
                _, h = self._blit(f"Explore — Draw from Deck {self.deck_value}", x, y, self.font_header); y += h + self.line_gap + 6
                _, h = self._blit("Draw a card for this diamond's deck.", x, y, self.font_label); y += h + self.line_gap
                self._blit("Press Enter to continue.", x, y, self.font_hint)

            elif self.step == 1:
                _, h = self._blit("Name this location", x, y, self.font_header); y += h + self.line_gap + 6
                box = pygame.Rect(x, y, self.rect.w - 2*self.pad, 42)
                pygame.draw.rect(self.screen, (255,255,255), box, 2)
                tx_y = box.y + (box.h - self.font_text.get_height())//2
                self._blit(self.name or "", box.x + 10, tx_y, self.font_text, (255,255,255))
                y = box.bottom + self.line_gap + 6
                self._blit("Enter to continue", x, y, self.font_hint)

            elif self.step == 2:
                # Column headers and lists
                _, h = self._blit("Choose a Feature Type", x, y, self.font_header); y += h + self.line_gap
                # columns area
                col_w = (self.rect.w - 2*self.pad) // 3
                col_x = [self.rect.x + self.pad + i*col_w for i in range(3)]
                top_y = y
                for ci, (title, items) in enumerate(COLUMNS):
                    # title
                    self._blit(title, col_x[ci], top_y, self.font_label)
                    # items
                    yy = top_y + self.font_label.get_height() + 6
                    for ri, (key, label) in enumerate(items):
                        arrow = "→ " if (ci == self.col_idx and ri == self.row_idx) else "  "
                        self._blit(f"{arrow}{label}", col_x[ci], yy, self.font_label)
                        yy += self.font_label.get_height() + 6

            elif self.step == 3:
                _, h = self._blit("Notes / Features", x, y, self.font_header); y += h + self.line_gap
                # white textarea box (so black text is visible)
                box_h = self.rect.h - (y - self.rect.y) - 60
                box = pygame.Rect(x, y, self.rect.w - 2*self.pad, box_h)
                pygame.draw.rect(self.screen, (255,255,255), box)       # fill white
                pygame.draw.rect(self.screen, (255,255,255), box, 2)     # border white (keeps shape on black panel)
                self._blit_in_box(self.notes, box, self.font_text)
                self._blit("Ctrl+Enter to continue", x, box.bottom + 8, self.font_hint)

            elif self.step == 4:
                _, h = self._blit("Confirm", x, y, self.font_header); y += h + self.line_gap
                _, h = self._blit(f"Name: {self.name}", x, y, self.font_label); y += h + 2
                _, h = self._blit(f"Type: {KEY_TO_LABEL.get(self.type_key,'')}", x, y, self.font_label); y += h + 8
                self._blit("Press Enter to Save, Backspace to edit notes", x, y, self.font_hint)

            pygame.display.flip()
            clock.tick(60)
        return None

# ---------- main loop ----------
def main():
    pygame.init()
    L = UILayout()
    screen = pygame.display.set_mode((L.width, L.height))
    pygame.display.set_caption(f"HexScrawl — Hex {HEX_ID}")
    renderer = HexScreenRenderer(L)

    hex_data = load_hex(HEX_ID)
    persisted_marks = None
    if hex_data and isinstance(hex_data.get("diamonds"), list):
        try:
            persisted_marks = [(int(d["center_index"]), int(d["value"])) for d in hex_data["diamonds"]]
        except Exception:
            persisted_marks = None

    marks = persisted_marks
    sel = 0
    clock = pygame.time.Clock()

    hex_data_ref = [hex_data]
    selected_index_ref = [sel]
    picker = make_json_feature_picker(hex_data_ref, selected_index_ref)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in (pygame.K_LEFT, pygame.K_KP4):
                    sel = _next_index_by_direction(getattr(renderer, "last_diamonds", []), sel, -1, 0)
                elif event.key in (pygame.K_RIGHT, pygame.K_KP6):
                    sel = _next_index_by_direction(getattr(renderer, "last_diamonds", []), sel, 1, 0)
                elif event.key in (pygame.K_UP, pygame.K_KP8):
                    sel = _next_index_by_direction(getattr(renderer, "last_diamonds", []), sel, 0, -1)
                elif event.key in (pygame.K_DOWN, pygame.K_KP2):
                    sel = _next_index_by_direction(getattr(renderer, "last_diamonds", []), sel, 0, 1)
                elif event.key in (pygame.K_r,):
                    delete_hex(HEX_ID)
                    hex_data = None
                    hex_data_ref[0] = None
                    marks = None
                    sel = 0
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if hex_data and 0 <= sel < len(hex_data.get("diamonds", [])):
                        d = hex_data["diamonds"][sel]
                        deck_value = int(d.get("value", 1))
                        initial = None
                        if d.get("status") == "discovered":
                            initial = {"name": d.get("name") or "", "text": d.get("text") or "", "icon": d.get("icon")}
                        modal = ExploreModal(screen, L, deck_value, initial=initial)
                        result = modal.run()
                        if result:
                            d["status"] = "discovered"
                            d["name"] = result["name"]
                            d["type"] = result["type"]
                            d["text"] = result["text"]
                            d["icon"] = result["icon"]
                            hex_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                            save_hex(hex_data)
                            hex_data_ref[0] = hex_data
                elif event.key in (pygame.K_e,):
                    if hex_data and 0 <= sel < len(hex_data.get("diamonds", [])):
                        d = hex_data["diamonds"][sel]
                        if d.get("status") == "discovered":
                            deck_value = int(d.get("value", 1))
                            initial = {"name": d.get("name") or "", "text": d.get("text") or "", "icon": d.get("icon")}
                            modal = ExploreModal(screen, L, deck_value, initial=initial)
                            result = modal.run()
                            if result:
                                d["name"] = result["name"]
                                d["type"] = result["type"]
                                d["text"] = result["text"]
                                d["icon"] = result["icon"]
                                hex_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                                save_hex(hex_data)
                                hex_data_ref[0] = hex_data

        selected_index_ref[0] = sel
        hex_data_ref[0] = hex_data

        img = renderer.render(
            hex_id=HEX_ID,
            description=("Arrows/Numpad to move. Enter to explore. R resets this hex."),
            features=[("keep","")],
            marks=marks,
            selected_idx=sel,
            feature_picker=picker
        )

        if marks is None and renderer.last_marks:
            marks = renderer.last_marks[:]
            hex_data = {
                "hex_id": HEX_ID,
                "seed": 0,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "diamonds": [
                    {
                        "uid": f"d{i:02d}",
                        "center_index": int(ci),
                        "value": int(val),
                        "status": "unknown",
                        "name": None,
                        "type": None,
                        "text": None,
                        "icon": None,
                        "tags": [],
                    } for i, (ci, val) in enumerate(marks)
                ],
                "trails": []
            }
            save_hex(hex_data)
            hex_data_ref[0] = hex_data

        if renderer.last_diamonds:
            sel = max(0, min(sel, len(renderer.last_diamonds)-1))
        else:
            sel = 0

        rgb = img.convert("RGB")
        data = rgb.tobytes()
        pyg_img = pygame.image.fromstring(data, rgb.size, "RGB")
        screen.blit(pyg_img, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
