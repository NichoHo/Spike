"""
Spike: Jinja2 custom template filters.
Blueprint §10 & DESIGN.md §12.2.
"""

from datetime import datetime, timezone
from typing import Optional, Union


def filter_timecode(seconds: Optional[Union[float, int]]) -> str:
    """Format seconds into video timecode (e.g., '1:02:03.4' or '2:03.4')."""
    if seconds is None:
        return "0:00.0"
    s = float(seconds)
    hours = int(s // 3600)
    minutes = int((s % 3600) // 60)
    secs = s % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:04.1f}"
    return f"{minutes}:{secs:04.1f}"


def filter_duration(seconds: Optional[Union[float, int]]) -> str:
    """Format seconds into tabular duration (e.g. '0:32', '12:05', '3:12:40')."""
    if seconds is None:
        return "0:00"
    s = int(round(float(seconds)))
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def filter_duration_words(seconds: Optional[Union[float, int]]) -> str:
    """Format seconds into words (e.g. '3 h 12 min', '45 min', '28 s')."""
    if seconds is None:
        return "0 s"
    s = int(round(float(seconds)))
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} h")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if not parts or (hours == 0 and minutes == 0):
        parts.append(f"{secs} s")
    return " ".join(parts)


def filter_relative_time(dt_input: Optional[Union[str, datetime]]) -> str:
    """Format UTC datetime into relative string (e.g. 'just now', '12 min ago', '3 h ago')."""
    if not dt_input:
        return ""
    try:
        if isinstance(dt_input, str):
            dt = datetime.fromisoformat(dt_input)
        else:
            dt = dt_input
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = (now - dt).total_seconds()

        if diff < 60:
            return "just now"
        elif diff < 3600:
            m = int(diff // 60)
            return f"{m} min ago"
        elif diff < 86400:
            h = int(diff // 3600)
            return f"{h} h ago"
        elif diff < 172800:
            return dt.strftime("Yesterday %H:%M")
        elif dt.year == now.year:
            return dt.strftime("%b %d, %H:%M")
        else:
            return dt.strftime("%b %d, %Y")
    except Exception:
        return str(dt_input)


def filter_local_time(dt_input: Optional[Union[str, datetime]]) -> str:
    """Format UTC datetime for tooltip (e.g. 'Sep 30, 2026, 19:00')."""
    if not dt_input:
        return ""
    try:
        if isinstance(dt_input, str):
            dt = datetime.fromisoformat(dt_input)
        else:
            dt = dt_input
        return dt.strftime("%b %d, %Y, %H:%M")
    except Exception:
        return str(dt_input)


def filter_filesize(num_bytes: Optional[int]) -> str:
    """Format bytes into readable size (e.g. '214 MB', '1.2 GB')."""
    if num_bytes is None:
        return "0 B"
    b = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024.0 or unit == "TB":
            if unit in ["B", "KB"]:
                return f"{int(b)} {unit}"
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} GB"


def filter_number(val: Optional[Union[int, float]]) -> str:
    """Format integer with thousands separator (e.g. '12,480')."""
    if val is None:
        return "0"
    return f"{int(val):,}"


def filter_compact_number(val: Optional[Union[int, float]]) -> str:
    """Format view counts into compact string (e.g. '12.5K', '1.2M')."""
    if val is None:
        return "0"
    n = float(val)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


def filter_percent(val: Optional[float]) -> str:
    """Format float into percentage string (e.g. '47%')."""
    if val is None:
        return "0%"
    pct = float(val) * 100.0 if float(val) <= 1.0 else float(val)
    if pct < 10:
        return f"{pct:.1f}%"
    return f"{int(round(pct))}%"


def register_filters(jinja_env):
    """Register all filters onto the Jinja2 environment."""
    jinja_env.filters["timecode"] = filter_timecode
    jinja_env.filters["duration"] = filter_duration
    jinja_env.filters["duration_words"] = filter_duration_words
    jinja_env.filters["relative_time"] = filter_relative_time
    jinja_env.filters["local_time"] = filter_local_time
    jinja_env.filters["filesize"] = filter_filesize
    jinja_env.filters["number"] = filter_number
    jinja_env.filters["compact_number"] = filter_compact_number
    jinja_env.filters["percent"] = filter_percent
