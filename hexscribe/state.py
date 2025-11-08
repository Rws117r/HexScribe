# hexscribe/state.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

def project_root() -> Path:
    # Root of your project (one level above the hexscribe package)
    return Path(__file__).resolve().parents[1]

def data_dir() -> Path:
    p = project_root() / "data" / "hexes"
    p.mkdir(parents=True, exist_ok=True)
    return p

def hex_path(hex_id: str) -> Path:
    return data_dir() / f"{hex_id}.json"

def load_hex(hex_id: str) -> Dict[str, Any] | None:
    p = hex_path(hex_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_hex(hex_data: Dict[str, Any]) -> None:
    hex_id = hex_data.get("hex_id", "UNKNOWN")
    p = hex_path(hex_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(hex_data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)

def delete_hex(hex_id: str) -> None:
    p = hex_path(hex_id)
    if p.exists():
        p.unlink()
