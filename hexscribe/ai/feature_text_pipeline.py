# hexscribe/ai/feature_text_pipeline.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from .feature_description_ai import generate_feature_description


def save_feature_text_with_ai(
    json_path: str | Path,
    diamond_uid: str,
    raw_text: str,
    *,
    model: str = "llama3.2:3b",
    tone: Optional[str] = None,
    use_ai: bool = True,
) -> dict:
    """
    Rewrites submitted feature text (for one diamond) via AI and saves the prose
    back into that diamond's 'text' field in the same JSON file.

    - No batch processing.
    - No extra fields.
    - If AI is disabled or errors, user text is saved as-is.

    Returns the updated diamond dict.
    """
    p = Path(json_path)
    data = _read_json(p)

    target = _find_diamond(data, diamond_uid)
    if target is None:
        raise ValueError(f"diamond uid not found: {diamond_uid}")

    submitted = (raw_text or "").strip()

    if use_ai and submitted:
        try:
            rewritten = generate_feature_description(
                submitted,
                model=model,
                tone=tone,
                stream=True,
            )
            target["text"] = rewritten if rewritten else submitted
        except Exception:
            # fail safe: never block save
            target["text"] = submitted
    else:
        target["text"] = submitted

    data["updated_at"] = _iso_now()
    _write_json(p, data)
    return target


# -----------------------------------------------------------------------------#
# Internals
# -----------------------------------------------------------------------------#
def _find_diamond(data: dict, uid: str) -> Optional[dict]:
    diamonds = data.get("diamonds", [])
    if not isinstance(diamonds, list):
        return None
    for d in diamonds:
        if isinstance(d, dict) and d.get("uid") == uid:
            return d
    return None


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
