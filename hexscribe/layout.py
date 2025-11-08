# hexscribe/layout.py
from dataclasses import dataclass

@dataclass(frozen=True)
class UILayout:
    # Canvas
    width: int = 648
    height: int = 480

    # Outer frame
    margin: int = 12

    # Panel split (x position of the vertical divider)
    split_x: int = 400

    # Left panel padding inside the frame
    left_pad: int = 16
    right_pad: int = 16
    top_pad: int = 8
    bottom_pad: int = 10

    # Hex grid box inside left panel
    # (grid is auto-fit between text header and bottom; these are extra insets)
    hex_inset_top: int = 6
    hex_inset_sides: int = 0
    hex_inset_bottom: int = 8

    # Legend placement (LEFT PANEL)
    legend_push_from_hex: int = 16   # min px to keep legend away from hex
    legend_safe_from_split: int = 6  # min px from split line (border side)
    legend_right_margin: int = 1    # right padding inside left panel (before split)
    legend_top_min_above_hex: int = 24
    legend_bottom_margin: int = 10   # bottom padding inside left panel

    # Compass
    compass_offset_x: int = 52
    compass_offset_y: int = 48

    # Fonts (sizes only; actual font objects live in fonts.py)
    title_size: int = 34
    body_size: int = 14
    feature_size: int = 18

    # Hex grid detail
    cells_across: int = 6            # number of small hexes horizontally
    diamond_scale: float = 0.55      # black diamond size inside a small hex
