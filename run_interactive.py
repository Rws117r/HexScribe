# run_interactive.py (ordered LR / TB navigation)
import sys, math, pygame
from datetime import datetime
from pathlib import Path

from hexscribe import HexScreenRenderer, UILayout
from hexscribe.state import load_hex, save_hex, delete_hex
from hexscribe.types import COLUMNS, KEY_TO_LABEL

HEX_ID = "1106"

UNKNOWN_FEATURE = {
    "name": "Unknown",
    "type": "Unexplored",
    "text": "Press Enter to explore.",
    "category": "",
}

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

def make_json_feature_picker(hex_data_ref, selected_index_ref):
    def pick(_ignored):
        hex_data = hex_data_ref[0]
        sel = selected_index_ref[0]
        if not hex_data or "diamonds" not in hex_data: return {
            "name":"Unknown","type":"Unexplored","text":"Press Enter to explore.","category":""
        }
        if sel is None or sel < 0 or sel >= len(hex_data["diamonds"]):
            return {"name":"Unknown","type":"Unexplored","text":"Press Enter to explore.","category":""}
        d = hex_data["diamonds"][sel]
        if d.get("status") != "discovered":
            return {"name":"Unknown","type":"Unexplored","text":"Press Enter to explore.","category":""}
        return {
            "name": d.get("name") or "(unnamed)",
            "type": d.get("type") or "",
            "text": d.get("text") or "",
            "category": "",
        }
    return pick

# ---------- Modal ----------
class ExploreModal:
    def __init__(self, screen, ui, deck_value: int, initial=None):
        self.screen = screen
        self.ui = ui
        self.deck_value = deck_value
        self.initial = initial or {}
        self.active = True
        self.step = 0
        self.name = self.initial.get("name", "")
        init_key = self.initial.get("icon") or ""
        self.type_key = init_key if init_key in KEY_TO_LABEL else None
        self.notes = self.initial.get("text", "")
        self.col_idx = 0
        self.row_idx = 0

        pygame.font.init()
        self.font_title = load_pygame_font("Jost-VariableFont_wght.ttf", 22, bold=True)
        self.font_cat   = load_pygame_font("LibreCaslonText-Bold.ttf", 18)
        self.font_item  = load_pygame_font("LibreCaslonText-Regular.ttf", 16)
        self.font_hint  = load_pygame_font("LibreCaslonText-Italic.ttf", 14, italic=True)
        self.font_text  = load_pygame_font("LibreCaslonText-Regular.ttf", 16)

        self.pad = 10
        self.line_gap = 6

        for ci, (_title, items) in enumerate(COLUMNS):
            for ri, (key, _label) in enumerate(items):
                if key == self.type_key:
                    self.col_idx, self.row_idx = ci, ri

    def _wrap(self, text, font, max_w):
        out, cur = [], ""
        for para in text.split("\n"):
            cur = ""
            for w in para.split(" "):
                test = (cur + " " + w).strip()
                if font.size(test)[0] <= max_w:
                    cur = test
                else:
                    if cur: out.append(cur)
                    cur = w
            out.append(cur)
        return out or [""]

    def _panel_rect(self):
        W, H = self.screen.get_size()
        return pygame.Rect((W-500)//2, (H-300)//2, 500, 300)

    def _draw_panel(self, title):
        rect = self._panel_rect()
        self.rect = rect
        pygame.draw.rect(self.screen, (0,0,0), rect, 3)
        inner = rect.inflate(-6, -6)
        pygame.draw.rect(self.screen, (255,255,255), inner)
        bar = pygame.Rect(inner.x, inner.y, inner.w, 44)
        pygame.draw.rect(self.screen, (0,0,0), bar)
        tx = bar.x + 12
        ty = bar.y + (bar.h - self.font_title.get_height())//2
        self.screen.blit(self.font_title.render(title, False, (255,255,255)), (tx, ty))
        return inner.x + self.pad, bar.bottom + self.pad, inner

    def _blit(self, txt, x, y, font, color=(0,0,0)):
        surf = font.render(txt, False, color)
        self.screen.blit(surf, (x, y)); return surf.get_width(), surf.get_height()

    def _blit_in_box(self, text, box, font):
        pad = 8
        wrapped = self._wrap(text, font, box.w - 2*pad)
        ty = box.y + pad
        line_h = font.get_height() + 3
        max_lines = max(1, (box.h - 2*pad) // line_h)
        for ln in wrapped[-max_lines:]:
            self.screen.blit(font.render(ln, False, (0,0,0)), (box.x + pad, ty))
            ty += line_h

    def _handle_text_input(self, current, event, limit):
        if event.key == pygame.K_BACKSPACE: return current[:-1]
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER): return current + "\n"
        if event.unicode and len(current) < limit and (31 < ord(event.unicode) or event.unicode in "\n\t"):
            return current + event.unicode
        return current

    def run(self):
        clock = pygame.time.Clock()
        while self.active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.active=False; return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: self.active=False; return None
                    if self.step == 0 and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER): self.step = 1
                    elif self.step == 1:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            if self.name.strip(): self.step = 2
                        elif event.key == pygame.K_BACKSPACE: self.name = self.name[:-1]
                        elif event.unicode and len(self.name) < 80: self.name += event.unicode
                    elif self.step == 2:
                        cols = COLUMNS
                        if event.key in (pygame.K_LEFT, pygame.K_a):
                            self.col_idx = (self.col_idx - 1) % len(cols); self.row_idx = min(self.row_idx, len(cols[self.col_idx][1]) - 1)
                        elif event.key in (pygame.K_RIGHT, pygame.K_d):
                            self.col_idx = (self.col_idx + 1) % len(cols); self.row_idx = min(self.row_idx, len(cols[self.col_idx][1]) - 1)
                        elif event.key in (pygame.K_UP, pygame.K_w): self.row_idx = (self.row_idx - 1) % len(cols[self.col_idx][1])
                        elif event.key in (pygame.K_DOWN, pygame.K_s): self.row_idx = (self.row_idx + 1) % len(cols[self.col_idx][1])
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.type_key = cols[self.col_idx][1][self.row_idx][0]; self.step = 3
                    elif self.step == 3:
                        if (event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)) and (pygame.key.get_mods() & pygame.KMOD_CTRL): self.step = 4
                        else: self.notes = self._handle_text_input(self.notes, event, 4000)
                    elif self.step == 4:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            return {"name": self.name.strip(), "type": KEY_TO_LABEL.get(self.type_key, ""), "text": self.notes.strip(), "icon": self.type_key}
                        elif event.key == pygame.K_BACKSPACE: self.step = 3

            # draw
            if self.step == 0:
                x, y, inner = self._draw_panel(f"Explore — Draw from Deck {self.deck_value}")
                self._blit("Draw a card for this diamond's deck.", x, y, self.font_item); y += self.font_item.get_height() + self.line_gap
                self._blit("Press Enter to continue.", x, y, self.font_hint)
            elif self.step == 1:
                x, y, inner = self._draw_panel("Name this location")
                underline_w = inner.w - 2*self.pad
                name_y = y + self.font_item.get_height() + 3
                pygame.draw.line(self.screen, (0,0,0), (inner.x + self.pad, name_y), (inner.x + self.pad + underline_w, name_y), 2)
                self._blit(self.name or "", inner.x + self.pad, y, self.font_item)
            elif self.step == 2:
                x, y, inner = self._draw_panel("Choose a Feature Type")
                cols_area_x = inner.x + self.pad
                cols_area_w = inner.w - 2*self.pad
                col_w = cols_area_w // 3
                for ci, (title, items) in enumerate(COLUMNS):
                    cx = cols_area_x + ci*col_w + 6
                    self._blit(title, cx, y, self.font_cat)
                    iy = y + self.font_cat.get_height() + 6
                    for ri, (key, label) in enumerate(items):
                        if ci==self.col_idx and ri==self.row_idx:
                            # Draw black triangle cursor
                            tri_size = 8
                            tri_y = iy + self.font_item.get_height()//2
                            tri_points = [(cx, tri_y), (cx, tri_y - tri_size), (cx + tri_size, tri_y - tri_size//2)]
                            pygame.draw.polygon(self.screen, (0,0,0), tri_points)
                            label_x = cx + tri_size + 4
                        else:
                            label_x = cx + 12
                        self._blit(label, label_x, iy, self.font_item)
                        iy += self.font_item.get_height() + 6
            elif self.step == 3:
                x, y, inner = self._draw_panel("Notes / Features")
                box = pygame.Rect(inner.x + self.pad, y, inner.w - 2*self.pad, inner.h - (y - inner.y) - 46)
                pygame.draw.rect(self.screen, (255,255,255), box); pygame.draw.rect(self.screen, (0,0,0), box, 2)
                self._blit_in_box(self.notes, box, self.font_text)
                self._blit("Ctrl+Enter to continue", inner.x + self.pad, box.bottom + 6, self.font_hint)
            elif self.step == 4:
                x, y, inner = self._draw_panel("Confirm")
                self._blit(f"Name: {self.name}", x, y, self.font_item); y += self.font_item.get_height() + 4
                from hexscribe.types import KEY_TO_LABEL as K2L
                self._blit(f"Type: {K2L.get(self.type_key,'')}", x, y, self.font_item)

            pygame.display.flip(); clock.tick(60)
        return None

# ---------- main loop with LR/TB traversal ----------
def compute_lr_tb_order(diamonds_xy):
    # diamonds_xy: list of (x,y,whatever)
    idx_xy = [(i, x, y) for i, (x, y, _) in enumerate(diamonds_xy)]
    # Sort by x ascending, then y ascending (top to bottom)
    idx_xy.sort(key=lambda t: (t[1], t[2]))
    return [i for i, _x, _y in idx_xy]

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
    order = []          # ordered list of diamond indices (left->right, top->bottom)
    sel_ord = 0         # selection index in 'order'
    sel_actual = 0      # actual renderer index
    clock = pygame.time.Clock()

    hex_data_ref = [hex_data]
    selected_index_ref = [sel_actual]
    picker = make_json_feature_picker(hex_data_ref, selected_index_ref)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in (pygame.K_LEFT,):
                    if order:
                        sel_ord = (sel_ord - 1) % len(order)
                        sel_actual = order[sel_ord]
                elif event.key in (pygame.K_RIGHT,):
                    if order:
                        sel_ord = (sel_ord + 1) % len(order)
                        sel_actual = order[sel_ord]
                elif event.key in (pygame.K_r,):
                    delete_hex(HEX_ID); hex_data=None; hex_data_ref[0]=None; marks=None; order=[]; sel_ord=0; sel_actual=0
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if hex_data and order:
                        d = hex_data["diamonds"][sel_actual]
                        deck_value = int(d.get("value", 1))
                        initial = None
                        if d.get("status") == "discovered":
                            initial = {"name": d.get("name") or "", "text": d.get("text") or "", "icon": d.get("icon")}
                        modal = ExploreModal(screen, L, deck_value, initial=initial)
                        result = modal.run()
                        if result:
                            d.update({"status":"discovered","name":result["name"],"type":result["type"],
                                      "text":result["text"],"icon":result["icon"]})
                            hex_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                            save_hex(hex_data); hex_data_ref[0]=hex_data
                elif event.key in (pygame.K_e,):
                    if hex_data and order:
                        d = hex_data["diamonds"][sel_actual]
                        if d.get("status") == "discovered":
                            deck_value = int(d.get("value", 1))
                            initial = {"name": d.get("name") or "", "text": d.get("text") or "", "icon": d.get("icon")}
                            modal = ExploreModal(screen, L, deck_value, initial=initial)
                            result = modal.run()
                            if result:
                                d.update({"name":result["name"],"type":result["type"],"text":result["text"],"icon":result["icon"]})
                                hex_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                                save_hex(hex_data); hex_data_ref[0]=hex_data

        # Update order whenever diamonds change
        if getattr(renderer, "last_diamonds", None):
            new_n = len(renderer.last_diamonds)
            new_order = compute_lr_tb_order(renderer.last_diamonds) if new_n > 0 else []
            if new_order != order:
                order = new_order
                sel_ord = 0
                sel_actual = order[0] if order else 0

        selected_index_ref[0] = sel_actual
        hex_data_ref[0] = hex_data

        img = renderer.render(
            hex_id=HEX_ID,
            description=("Arrows/Numpad to move. Enter to explore. R resets this hex."),
            features=[("keep","")],
            marks=marks,
            selected_idx=sel_actual,
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
                    {"uid": f"d{i:02d}","center_index": int(ci),"value": int(val),
                     "status": "unknown","name": None,"type": None,"text": None,"icon": None,"tags": []}
                    for i, (ci, val) in enumerate(marks)
                ],
                "trails": []
            }
            save_hex(hex_data); hex_data_ref[0] = hex_data

        if getattr(renderer, "last_diamonds", None):
            if order:
                sel_ord = max(0, min(sel_ord, len(order)-1))
                sel_actual = order[sel_ord]
            else:
                sel_ord = 0; sel_actual = 0
        else:
            sel_ord = 0; sel_actual = 0

        rgb = img.convert("RGB")
        pyg_img = pygame.image.fromstring(rgb.tobytes(), rgb.size, "RGB")
        screen.blit(pyg_img, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit(); sys.exit(0)

if __name__ == "__main__":
    main()