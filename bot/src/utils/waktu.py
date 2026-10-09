"""Helper waktu bersama — parse ISO-8601 dengan fallback aman."""
import datetime


def parse_iso(iso: str | None) -> datetime.datetime | None:
    """Parse string ISO-8601 → datetime UTC. Return None bila kosong/rusak."""
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt
