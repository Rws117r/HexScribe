# render_demo.py
from hexscribe import HexScreenRenderer, UILayout
from demo_data import HEX_ID, DESCRIPTION, FEATURES

# Use the defaults from hexscribe/layout.py — single source of truth
layout = UILayout()
renderer = HexScreenRenderer(layout)

img = renderer.render(HEX_ID, DESCRIPTION, FEATURES, marks=None)
img.save("hexscribe_preview.png")
print("Saved hexscribe_preview.png")
