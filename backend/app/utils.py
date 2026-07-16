"""Utility helpers used across the app."""
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize(doc: Any) -> Any:
    """Recursively convert MongoDB documents / datetimes to JSON-safe types."""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize(d) for d in doc]
    if isinstance(doc, dict):
        out: dict[str, Any] = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            out[k] = serialize(v)
        return out
    if isinstance(doc, datetime):
        if doc.tzinfo is None:
            doc = doc.replace(tzinfo=timezone.utc)
        return doc.isoformat()
    return doc


def parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
