# hexscribe/types.py
from typing import List, Tuple, Dict

FEATURE_TYPES: List[Tuple[str, str]] = [
    ("place_of_power",    "Place of Power"),
    ("mystical_meddling", "Mystical Meddling"),
    ("hazard",            "Hazard"),
    ("village",           "Village"),
    ("outpost",           "Outpost"),
    ("passage",           "Passage"),
    ("portal",            "Portal"),
    ("town",              "Town"),
    ("city",              "City"),
    ("attraction",        "Attraction"),
    ("landmark",          "Landmark"),
    ("dungeon",           "Dungeon"),
    ("lair",              "Lair"),
]

LABEL_TO_KEY: Dict[str, str] = {label: key for key, label in FEATURE_TYPES}
KEY_TO_LABEL: Dict[str, str] = {key: label for key, label in FEATURE_TYPES}

COLUMNS = [
    ("Mystic", [
        ("place_of_power",    "Place of Power"),
        ("mystical_meddling", "Mystical Meddling"),
        ("portal",            "Portal"),
        ("passage",           "Passage"),
    ]),
    ("Danger", [
        ("hazard",   "Hazard"),
        ("dungeon",  "Dungeon"),
        ("lair",     "Lair"),
    ]),
    ("Civilization", [
        ("outpost",   "Outpost"),
        ("village",   "Village"),
        ("town",      "Town"),
        ("city",      "City"),
        ("landmark",  "Landmark"),
        ("attraction","Attraction"),
    ]),
]
