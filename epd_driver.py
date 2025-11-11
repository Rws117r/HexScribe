# epd_driver.py — UC8179 5.83" (648x480) for Adafruit 24-pin bonnet
# Minimal sequence ONLY: RESET → BOOSTER_SOFT_START → POWER_ON → (write) → REFRESH → SLEEP
# No PANEL_SETTING/PLL/RES/VCOM (those broke visuals on your glass).

import time, spidev, board, digitalio
from PIL import Image

# Pins (bonnet defaults)
PIN_DC, PIN_RST, PIN_BUSY = board.D22, board.D27, board.D17

# Geometry
W, H = 648, 480
BUF_BYTES = (W * H) // 8
SPI_MAX_CHUNK = 4096

# Minimal command set
POWER_ON                  = 0x04
BOOSTER_SOFT_START        = 0x06
DATA_START_TRANSMISSION_1 = 0x10  # old frame
DATA_START_TRANSMISSION_2 = 0x13  # new frame
DISPLAY_REFRESH           = 0x12
DEEP_SLEEP                = 0x07

# Your panel idles BUSY=HIGH ⇒ LOW means “busy”
BUSY_HIGH_IS_BUSY = False

def pil_to_panel(img: Image.Image) -> bytes:
    """Convert PIL image to 1bpp packed buffer; panel expects 1=white, 0=black (so we invert)."""
    img = img.convert("1").resize((W, H))
    # If the image appears upside-down on your panel, uncomment this:
    # img = img.transpose(Image.FLIP_TOP_BOTTOM)
    pix = img.load()
    out = bytearray(BUF_BYTES); i = 0
    for y in range(H):
        b = 0
        for x in range(W):
            bit = 7 - (x & 7)
            if pix[x, y] == 0:           # black pixel
                b |= (1 << bit)
            if (x & 7) == 7:
                out[i] = (~b) & 0xFF     # invert: 1=white, 0=black
                i += 1
                b = 0
        if (W & 7) != 0:
            out[i] = (~b) & 0xFF; i += 1
    return bytes(out)

class EPD583:
    def __init__(self):
        # GPIO
        self.dc   = digitalio.DigitalInOut(PIN_DC);   self.dc.direction   = digitalio.Direction.OUTPUT; self.dc.value = 1
        self.rst  = digitalio.DigitalInOut(PIN_RST);  self.rst.direction  = digitalio.Direction.OUTPUT; self.rst.value = 1
        self.busy = digitalio.DigitalInOut(PIN_BUSY); self.busy.direction = digitalio.Direction.INPUT
        # SPI
        self.spi = spidev.SpiDev(); self.spi.open(0, 0); self.spi.max_speed_hz = 4000000; self.spi.mode = 0

    def _cmd(self, c: int):
        self.dc.value = 0
        self.spi.xfer2([c])
        self.dc.value = 1

    def _data(self, b):
        self.dc.value = 1
        if isinstance(b, int):
            b = [b]
        for i in range(0, len(b), SPI_MAX_CHUNK):
            self.spi.xfer2(list(b[i:i+SPI_MAX_CHUNK]))

    def _wait(self, tag: str, timeout=45.0):
        t0 = time.time()
        while True:
            raw = self.busy.value
            busy = (raw if BUSY_HIGH_IS_BUSY else (not raw))
            if not busy: return True
            if time.time() - t0 > timeout:
                print(f"[warn] timeout {tag}")
                return False
            time.sleep(0.02)

    def _reset(self):
        self.rst.value = 1; time.sleep(0.02)
        self.rst.value = 0; time.sleep(0.01)
        self.rst.value = 1; time.sleep(0.02)

    def init(self):
        # EXACT sequence that worked on your panel
        self._reset()
        self._cmd(BOOSTER_SOFT_START); self._data([0xCF, 0xCE, 0x8D])
        self._cmd(POWER_ON);           self._wait("POWER_ON", 15.0)

    def show(self, img: Image.Image):
        buf   = pil_to_panel(img)
        white = bytes([0xFF]) * BUF_BYTES
        # old = white, new = image (this ordering matches your working tests)
        self._cmd(DATA_START_TRANSMISSION_1); self._data(white)
        self._cmd(DATA_START_TRANSMISSION_2); self._data(buf)
        self._cmd(DISPLAY_REFRESH);           self._wait("REFRESH", 45.0)

    def sleep(self):
        self._cmd(DEEP_SLEEP); self._data(0xA5)
