#!/usr/bin/env python3
"""
MINIMAL TEST - Your probe + image upload ONLY
NO panel settings, NO PLL, NO resolution, NO VCOM
Just: Reset -> Booster -> Power -> Upload -> Refresh
"""
import time, spidev, board, digitalio
from PIL import Image, ImageDraw, ImageFont

PIN_DC, PIN_RST, PIN_BUSY = board.D22, board.D27, board.D17
W, H = 648, 480
BUF_BYTES = (W*H)//8
SPI_MAX_CHUNK = 4096

# ONLY commands your working probe uses
POWER_ON                       = 0x04
BOOSTER_SOFT_START             = 0x06
DATA_START_TRANSMISSION_1      = 0x10  # Adding these for image
DATA_START_TRANSMISSION_2      = 0x13  # Adding these for image
DISPLAY_REFRESH                = 0x12
DEEP_SLEEP                     = 0x07

def pil_to_panel(img):
    """Convert image to buffer"""
    img = img.convert("1").resize((W, H))
    pix = img.load()
    out = bytearray(BUF_BYTES)
    i = 0
    for y in range(H):
        b = 0
        for x in range(W):
            bit = 7 - (x & 7)
            if pix[x, y] == 0:  # black
                b |= (1 << bit)
            if (x & 7) == 7:
                out[i] = (~b) & 0xFF
                i += 1
                b = 0
        if (W & 7) != 0:
            out[i] = (~b) & 0xFF
            i += 1
    return bytes(out)

class EPD:
    def __init__(self):
        self.dc   = digitalio.DigitalInOut(PIN_DC)
        self.dc.direction   = digitalio.Direction.OUTPUT
        self.dc.value = 1
        
        self.rst  = digitalio.DigitalInOut(PIN_RST)
        self.rst.direction  = digitalio.Direction.OUTPUT
        self.rst.value = 1
        
        self.busy = digitalio.DigitalInOut(PIN_BUSY)
        self.busy.direction = digitalio.Direction.INPUT
        
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4000000
        self.spi.mode = 0
    
    def _cmd(self, c):
        self.dc.value = 0
        self.spi.xfer2([c])
        self.dc.value = 1
    
    def _data(self, b):
        self.dc.value = 1
        if isinstance(b, int):
            b = [b]
        if isinstance(b, (list, tuple)):
            for i in range(0, len(b), SPI_MAX_CHUNK):
                self.spi.xfer2(list(b[i:i+SPI_MAX_CHUNK]))
        else:  # bytes
            for i in range(0, len(b), SPI_MAX_CHUNK):
                self.spi.xfer2(list(b[i:i+SPI_MAX_CHUNK]))
    
    def wait_idle(self, busy_high_is_busy, tag, timeout_s=45.0):
        t0 = time.time()
        while True:
            v = self.busy.value
            is_busy = (v if busy_high_is_busy else (not v))
            if not is_busy:
                elapsed = time.time() - t0
                print(f"  ✓ {tag} done ({elapsed:.2f}s)")
                return True
            if time.time() - t0 > timeout_s:
                print(f"  ✗ {tag} timeout")
                return False
            time.sleep(0.02)
    
    def reset(self):
        print("[i] HW reset pulse")
        self.rst.value = 1; time.sleep(0.02)
        self.rst.value = 0; time.sleep(0.01)
        self.rst.value = 1; time.sleep(0.02)
    
    def show_minimal(self, img, busy_high_is_busy):
        """EXACTLY your probe sequence + image upload"""
        print(f"\n{'='*60}")
        print(f"MINIMAL SEQUENCE (BUSY_HIGH={busy_high_is_busy})")
        print(f"{'='*60}")
        
        # EXACT probe sequence
        self.reset()
        
        print("[1] Booster soft-start (0xCF, 0xCE, 0x8D)")
        self._cmd(BOOSTER_SOFT_START)
        self._data([0xCF, 0xCE, 0x8D])
        
        print("[2] Power ON")
        self._cmd(POWER_ON)
        if not self.wait_idle(busy_high_is_busy, "POWER_ON", 15.0):
            print("⚠ Power ON timeout")
            return False
        
        # NOW add image upload (only addition to probe)
        print("[3] Upload image data")
        buf = pil_to_panel(img)
        white = bytes([0xFF]) * BUF_BYTES
        
        print("  - Old frame (white)")
        self._cmd(DATA_START_TRANSMISSION_1)
        self._data(white)
        
        print("  - New frame (test image)")
        self._cmd(DATA_START_TRANSMISSION_2)
        self._data(buf)
        
        print("[4] DISPLAY REFRESH")
        self._cmd(DISPLAY_REFRESH)
        self.wait_idle(busy_high_is_busy, "REFRESH", 45.0)
        
        print("[5] Sleep")
        self._cmd(DEEP_SLEEP)
        self._data(0xA5)
        
        return True

def create_test_image():
    """Super simple high-contrast test"""
    img = Image.new("1", (W, H), 1)  # white
    d = ImageDraw.Draw(img)
    
    # Just 4 big black squares in corners - unmistakable
    size = 150
    d.rectangle([0, 0, size, size], fill=0)
    d.rectangle([W-size, 0, W, size], fill=0)
    d.rectangle([0, H-size, size, H], fill=0)
    d.rectangle([W-size, H-size, W, H], fill=0)
    
    # Big X through middle
    d.line([(0, 0), (W, H)], fill=0, width=20)
    d.line([(W, 0), (0, H)], fill=0, width=20)
    
    return img

def main():
    print("="*60)
    print("MINIMAL TEST - Based on your working probe")
    print("="*60)
    print("Your probe works because it uses ONLY:")
    print("  Reset -> Booster -> Power ON -> Refresh")
    print()
    print("This test adds ONLY image upload commands:")
    print("  Reset -> Booster -> Power ON -> Upload -> Refresh")
    print()
    print("NO panel settings, NO PLL, NO resolution, NO VCOM")
    print("="*60)
    
    epd = EPD()
    img = create_test_image()
    
    # Try both BUSY polarities like your probe does
    for sense in (False, True):
        epd.show_minimal(img, busy_high_is_busy=sense)
        
        print("\n" + "="*60)
        print("CHECK DISPLAY NOW!")
        print("You should see:")
        print("  - 4 black squares in corners")
        print("  - Big X through center")
        print("="*60)
        
        response = input(f"\nDid BUSY_HIGH={sense} work? (y/n): ").lower()
        if response == 'y':
            print(f"\n✓✓✓ SUCCESS! Use BUSY_HIGH_IS_BUSY = {sense}")
            break
        
        time.sleep(1)
    
    print("\n" + "="*60)
    print("If NEITHER worked, the DATA commands might not be")
    print("supported without additional init (panel settings, etc)")
    print("="*60)

if __name__ == "__main__":
    main()