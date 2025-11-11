#!/usr/bin/env python3
"""
HexScribe interactive runner + E-Ink output (UC8179 5.83" 648x480)
- Imports HexScreenRenderer, UILayout from hexscribe (your original API)
- Pygame preview window mirrors your UI
- E-ink uses minimal UC8179 init; vertical flip applied
- Manual full refresh: 'W' (wipe/push current frame)
- De-ghost scrub: 'G' (black then white)
- Partial updates: panel updates only the changed rectangle (cursor/menus) automatically
"""

import sys, time, math, pygame
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont

# ===========================  YOUR APP IMPORTS  ===========================
from hexscribe import HexScreenRenderer, UILayout
from hexscribe.state import load_hex, save_hex, delete_hex
from hexscribe.types import COLUMNS, KEY_TO_LABEL
from hexscribe.ai.feature_description_ai import generate_feature_description
# ==========================================================================

HEX_ID = "1106"

UNKNOWN_FEATURE = {
    "name": "Unknown",
    "type": "Unexplored",
    "text": "Press Enter to explore.",
    "category": "",
}

# ==========================  MINIMAL E-INK DRIVER  ========================
# Proven-good sequence: RESET → 0x06 → 0x04 → (write old/new) → 0x12 → SLEEP
import spidev, board, digitalio

PIN_DC, PIN_RST, PIN_BUSY = board.D22, board.D27, board.D17
W, H = 648, 480
BUF_BYTES = (W * H) // 8
SPI_MAX_CHUNK = 4096
BUSY_HIGH_IS_BUSY = False  # panel idles HIGH; LOW means "busy"

# Commands
POWER_ON                  = 0x04
BOOSTER_SOFT_START        = 0x06
DATA_START_TRANSMISSION_1 = 0x10  # old frame (full)
DATA_START_TRANSMISSION_2 = 0x13  # new frame (full/partial)
DISPLAY_REFRESH           = 0x12
DEEP_SLEEP                = 0x07
PARTIAL_IN                = 0x91
PARTIAL_OUT               = 0x92
PARTIAL_WINDOW            = 0x90   # x0 x1 y0 y0 y1 y1 follow

def _send_bytes(spi, b: bytes):
    for i in range(0, len(b), SPI_MAX_CHUNK):
        spi.xfer2(list(b[i:i+SPI_MAX_CHUNK]))

def _pil_to_panel_full(img1b: Image.Image) -> bytes:
    """img1b must be 1-bit, size (W,H), already vertically flipped for panel."""
    px = img1b.load()
    out = bytearray(BUF_BYTES); i = 0
    for y in range(H):
        b = 0
        for x in range(W):
            bit = 7 - (x & 7)
            if px[x, y] == 0:  # black pixel
                b |= (1 << bit)
            if (x & 7) == 7:
                out[i] = (~b) & 0xFF  # panel expects 1=white, 0=black
                i += 1
                b = 0
        if (W & 7) != 0:
            out[i] = (~b) & 0xFF; i += 1
    return bytes(out)

def _pack_region_bits(img1b: Image.Image, x0, y0, x1, y1) -> bytes:
    """Pack a 1bpp box [x0..x1],[y0..y1] into bytes row by row (left→right)."""
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    out = bytearray(((w + 7)//8) * h)
    px = img1b.load()
    i = 0
    for yy in range(y0, y1+1):
        byte = 0; bitpos = 7
        for xx in range(x0, x1+1):
            if px[xx, yy] == 0:  # black
                byte |= (1 << bitpos)
            bitpos -= 1
            if bitpos < 0:
                out[i] = (~byte) & 0xFF
                i += 1
                byte = 0; bitpos = 7
        if bitpos != 7:
            out[i] = (~byte) & 0xFF
            i += 1
    return bytes(out)

class EPD583:
    def __init__(self):
        self.dc   = digitalio.DigitalInOut(PIN_DC);   self.dc.direction   = digitalio.Direction.OUTPUT; self.dc.value = 1
        self.rst  = digitalio.DigitalInOut(PIN_RST);  self.rst.direction  = digitalio.Direction.OUTPUT; self.rst.value = 1
        self.busy = digitalio.DigitalInOut(PIN_BUSY); self.busy.direction = digitalio.Direction.INPUT
        self.spi  = spidev.SpiDev(); self.spi.open(0,0); self.spi.max_speed_hz = 4000000; self.spi.mode = 0

    def _cmd(self, c): self.dc.value = 0; self.spi.xfer2([c]); self.dc.value = 1
    def _data(self, b): self.dc.value = 1; _send_bytes(self.spi, b)

    def _wait(self, tag, to=45.0):
        t0 = time.time()
        while True:
            raw = self.busy.value
            busy = (raw if BUSY_HIGH_IS_BUSY else (not raw))
            if not busy: return True
            if time.time() - t0 > to:
                print(f"[warn] timeout {tag}")
                return False
            time.sleep(0.02)

    def _reset(self):
        self.rst.value = 1; time.sleep(0.02)
        self.rst.value = 0; time.sleep(0.01)
        self.rst.value = 1; time.sleep(0.02)

    def init(self):
        print("[epd] RESET → BOOST → POWER_ON")
        self._reset()
        self._cmd(BOOSTER_SOFT_START); self._data([0xCF, 0xCE, 0x8D])
        self._cmd(POWER_ON);           self._wait("POWER_ON", 15.0)

    def _show_buf_full(self, buf: bytes):
        white = bytes([0xFF]) * BUF_BYTES
        self._cmd(DATA_START_TRANSMISSION_1); self._data(white)
        self._cmd(DATA_START_TRANSMISSION_2); self._data(buf)
        self._cmd(DISPLAY_REFRESH);           self._wait("REFRESH", 45.0)

    def show_image(self, img: Image.Image):
        # full update with vertical flip for panel
        img1b = img.convert("1").resize((W, H)).transpose(Image.FLIP_TOP_BOTTOM)
        self._show_buf_full(_pil_to_panel_full(img1b))

    # ------------------- FIXED (bbox flip to panel space) -------------------
    def show_partial(self, img: Image.Image, bbox):
        """Partial window update; img is unflipped UI image, bbox is PIL (l,t,r,b)."""
        if not bbox:
            return
        x0, y0, x1, y1 = bbox          # right/bottom are exclusive
        x1 -= 1; y1 -= 1
        if x0 > x1 or y0 > y1:
            return

        # 1) Flip bbox because panel coordinates are vertically flipped vs UI.
        fy0 = H - 1 - y1                # UI bottom -> panel top
        fy1 = H - 1 - y0                # UI top    -> panel bottom
        if fy0 > fy1:
            fy0, fy1 = fy1, fy0

        # 2) Prepare flipped, 1bpp image (panel space)
        img1b = img.convert("1").resize((W, H)).transpose(Image.FLIP_TOP_BOTTOM)

        # 3) Align X to byte boundaries (controller wants full bytes)
        x0_al = max(0, x0 & ~7)
        x1_al = min(W-1, x1 | 7)
        y0_al = max(0, fy0)
        y1_al = min(H-1, fy1)
        if x1_al < x0_al or y1_al < y0_al:
            return

        payload = _pack_region_bits(img1b, x0_al, y0_al, x1_al, y1_al)

        # 4) Partial window sequence
        self._cmd(PARTIAL_IN)
        self._cmd(PARTIAL_WINDOW)
        self._data([
            x0_al & 0xFF, x1_al & 0xFF,          # X start/end (pixels)
            (y0_al >> 8) & 0xFF, y0_al & 0xFF,   # Y start
            (y1_al >> 8) & 0xFF, y1_al & 0xFF,   # Y end
            0x28                                  # follow bits; works on UC8179
        ])
        self._cmd(DATA_START_TRANSMISSION_2); self._data(payload)
        self._cmd(DISPLAY_REFRESH);           self._wait("PARTIAL_REFRESH", 45.0)
        self._cmd(PARTIAL_OUT)
    # -----------------------------------------------------------------------

    def fill(self, white=False):
        b = 0xFF if white else 0x00
        self._show_buf_full(bytes([b]) * BUF_BYTES)

    def deghost_cycle(self):
        self.fill(white=False); self.fill(white=True)

    def sleep(self):
        self._cmd(DEEP_SLEEP); self._data(0xA5)
# ==========================================================================


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
        if not hex_data or "diamonds" not in hex_data:
            return UNKNOWN_FEATURE
        if sel is None or sel < 0 or sel >= len(hex_data["diamonds"]):
            return UNKNOWN_FEATURE
        d = hex_data["diamonds"][sel]
        if d.get("status") != "discovered":
            return UNKNOWN_FEATURE
        return {
            "name": d.get("name") or "(unnamed)",
            "type": d.get("type") or "",
            "text": d.get("text") or "",
            "category": "",
        }
    return pick

def _ai_rewrite_text(raw_text: str, *, use_ai: bool = True, tone: str | None = None, model: str = "llama3.2:3b") -> str:
    raw_text = (raw_text or "").strip()
    if not raw_text or not use_ai:
        return raw_text
    try:
        return generate_feature_description(
            raw_text,
            model=model,
            tone=tone,
            stream=True,
            max_words=220,
        ) or raw_text
    except Exception as e:
        print(f"[AI fallback] {e}")
        return raw_text

# -------------------------- ExploreModal (restored) --------------------------
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
        Ww, Hh = self.screen.get_size()
        return pygame.Rect((Ww-500)//2, (Hh-300)//2, 500, 300)

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

        if len(wrapped) <= max_lines:
            lines = wrapped
        else:
            lines = wrapped[:max_lines]
            last = lines[-1].rstrip()
            if last and last[-1] not in ".!?…":
                last = (last + "…") if len(last) <= 3 else (last[:-1] + "…")
            lines[-1] = last

        x0 = box.x + pad
        for ln in lines:
            self.screen.blit(font.render(ln, False, (0,0,0)), (x0, ty))
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
                            return {
                                "name": self.name.strip(),
                                "type": KEY_TO_LABEL.get(self.type_key, ""),
                                "text": self.notes.strip(),
                                "icon": self.type_key
                            }
                        elif event.key == pygame.K_BACKSPACE: self.step = 3

            if self.step == 0:
                x, y, inner = self._draw_panel(f"Explore — Draw from Deck")
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
                    for ri, (_key, label) in enumerate(items):
                        if ci==self.col_idx and ri==self.row_idx:
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
# ------------------------------------------------------------------------------

def compute_lr_tb_order(diamonds_xy):
    idx_xy = [(i, x, y) for i, (x, y, _) in enumerate(diamonds_xy)]
    idx_xy.sort(key=lambda t: (t[1], t[2]))  # x asc, then y asc
    return [i for i, _x, _y in idx_xy]

# =============================  MAIN LOOP  =============================

PARTIAL_THROTTLE_S = 0.40     # don't spam the controller
PARTIAL_MAX_AREA   = 0.45     # partial only if <= 45% of screen changed

def main():
    pygame.init()
    L = UILayout()
    screen = pygame.display.set_mode((L.width, L.height))
    pygame.display.set_caption(f"HexScrawl — Hex {HEX_ID}")
    renderer = HexScreenRenderer(L)

    # E-Ink init + brief sanity so you know it’s alive
    epd = EPD583()
    epd.init()
    print("[sanity] white"); epd.fill(white=True)
    print("[sanity] black"); epd.fill(white=False)
    print("[info] Press W to push full frame, G to de-ghost.")

    hex_data = load_hex(HEX_ID)
    persisted_marks = None
    if hex_data and isinstance(hex_data.get("diamonds"), list):
        try:
            persisted_marks = [(int(d["center_index"]), int(d["value"])) for d in hex_data["diamonds"]]
        except Exception:
            persisted_marks = None

    marks = persisted_marks
    order, sel_ord, sel_actual = [], 0, 0
    clock = pygame.time.Clock()

    hex_data_ref = [hex_data]
    selected_index_ref = [sel_actual]
    picker = make_json_feature_picker(hex_data_ref, selected_index_ref)

    USE_AI_PROSE = True
    AI_TONE = None

    text_scroll = 0
    last_push_ts = 0.0
    last_epd_img = None

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
                        text_scroll = 0
                elif event.key in (pygame.K_RIGHT,):
                    if order:
                        sel_ord = (sel_ord + 1) % len(order)
                        sel_actual = order[sel_ord]
                        text_scroll = 0
                elif event.key == pygame.K_KP9:
                    text_scroll = max(0, text_scroll - 1)
                elif event.key == pygame.K_KP3:
                    text_scroll = text_scroll + 1
                elif event.key in (pygame.K_r,):
                    delete_hex(HEX_ID); hex_data=None; hex_data_ref[0]=None; marks=None; order=[]; sel_ord=0; sel_actual=0; text_scroll=0
                elif event.key in (pygame.K_w,):
                    img_for_epd = renderer.render(
                        hex_id=HEX_ID,
                        description=("Arrows/Numpad to move. Enter to explore. W=push full to e-ink. 9/3 scroll. G=deghost."),
                        features=[("keep","")],
                        marks=marks,
                        selected_idx=sel_actual,
                        feature_picker=picker,
                        text_scroll=text_scroll,
                    )
                    print("[epd] full wipe")
                    epd.show_image(img_for_epd)
                    last_epd_img = img_for_epd.copy()
                    last_push_ts = time.time()
                elif event.key in (pygame.K_g,):
                    print("[epd] deghost (black→white)")
                    epd.deghost_cycle()
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
                            rewritten_text = _ai_rewrite_text(result["text"], use_ai=USE_AI_PROSE, tone=AI_TONE)
                            d.update({
                                "status": "discovered",
                                "name": result["name"],
                                "type": result["type"],
                                "text": rewritten_text,
                                "icon": result["icon"],
                            })
                            hex_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                            save_hex(hex_data); hex_data_ref[0]=hex_data
                            text_scroll = 0

        if getattr(renderer, "last_diamonds", None):
            new_n = len(renderer.last_diamonds)
            new_order = compute_lr_tb_order(renderer.last_diamonds) if new_n > 0 else []
            if new_order != order:
                order = new_order
                sel_ord = 0
                sel_actual = order[0] if order else 0
                text_scroll = 0

        selected_index_ref[0] = sel_actual
        hex_data_ref[0] = hex_data

        img = renderer.render(
            hex_id=HEX_ID,
            description=("Arrows/Numpad to move. Enter to explore. W=push full to e-ink. 9/3 scroll. G=deghost."),
            features=[("keep","")],
            marks=marks,
            selected_idx=sel_actual,
            feature_picker=picker,
            text_scroll=text_scroll,
        )

        if marks is None and renderer.last_marks:
            marks = renderer.last_marks[:]
            hex_data = {
                "hex_id": HEX_ID,
                "seed": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
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

        # Preview window
        rgb = img.convert("RGB")
        pyg_img = pygame.image.fromstring(rgb.tobytes(), rgb.size, "RGB")
        screen.blit(pyg_img, (0, 0))
        pygame.display.flip()

        # --- Partial update to e-ink for small UI changes ---
        now = time.time()
        if last_epd_img is None:
            last_epd_img = img.copy()  # baseline; push later on 'W'
        else:
            if (now - last_push_ts) >= PARTIAL_THROTTLE_S:
                bbox = ImageChops.difference(img.convert("1"), last_epd_img.convert("1")).getbbox()
                if bbox:
                    bw, bh = (bbox[2]-bbox[0]), (bbox[3]-bbox[1])
                    area = (bw * bh) / (W * H)
                    if area <= PARTIAL_MAX_AREA:
                        print(f"[epd] partial {bbox}")
                        epd.show_partial(img, bbox)
                        last_epd_img.paste(img.crop(bbox), box=bbox)
                        last_push_ts = now
                    # big changes wait for manual W

        clock.tick(60)

    epd.sleep()
    pygame.quit(); sys.exit(0)

if __name__ == "__main__":
    main()
