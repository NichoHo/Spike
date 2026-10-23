"""
Outreach database (data/outreach.db, OUTREACH.md §6.6).
Lead data is personal data (UU PDP), so it never goes into spike.db.
API fields (YouTube Developer Policy III.E.4) are refreshed or purged within 30 days; sales history is kept.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src import config

STATUSES = (
    "found", "approved", "needs_contact", "rejected", "clip_wanted",
    "clip_queued", "clip_ready", "clip_failed", "clip_approved", "email_ready",
    "sent", "followup_1", "followup_2", "replied", "bounced", "trial", "client", "opted_out",
)
# Statuses where a first email or follow-up is out and a reply is still awaited
AWAITING_REPLY = ("sent", "followup_1", "followup_2")

# Columns filled from YouTube API responses. Purged when api_fetched_at is older than 30 days.
API_COLUMNS = (
    "name", "handle", "thumbnail", "language_api", "country", "subscribers_or_viewers",
    "last_stream_at", "streams_14d", "avg_stream_h", "shorts_14d", "whop_flag",
    "vod_video_id", "vod_title", "vod_published_at", "vod_duration_s", "description_excerpt", "vod_views",
)
CONTACT_COLUMNS = ("email", "instagram", "x", "tiktok", "discord", "website", "twitch", "kick")
API_RETENTION_DAYS = 30

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Finder (OUTREACH.md §6.2 schedule table)
    "run_hour": 3,
    "max_searches_per_run": 20,
    "new_leads_per_day": 30,
    "lookback_days": 14,
    "min_long_streams_14d": 2,
    "min_stream_hours": 2.0,
    "min_fit_score": 0,
    "max_shorts_14d": 10,
    "youtube_enabled": 1,  # per-platform on/off for the finder (both on by default)
    "twitch_enabled": 1,
    # Twitch finder (§6.2 B, accepted risk). Runs next to YouTube for active Twitch searches. Sample hours are
    # this PC's time (WIB): Indonesian prime time 20:00 to 23:00, US evening 07:00 to 11:00.
    "twitch_sample_hours": "7,9,11,20,22",
    "twitch_new_leads_per_day": 15,
    # YouTube quota (verified 2026-10-14: search.list has its own bucket, 100 calls a day;
    # everything else shares 10,000 units). Spike's source lookup also uses search.list.
    "search_calls_per_day": 60,
    "units_per_day": 10000,
    "units_reserved_for_spike": 1000,
    # Trial clips (§6.3). trial_clips_per_day removed: unlimited (missing/blank/None means no daily cap).
    "trial_max_vod_s": 7200,
    # Email (§4.2, §6.3). emails_per_day removed: unlimited (missing/blank/None means no daily cap).
    "send_gap_min": 4,
    "followups_enabled": 1,
    "followup_1_days": 4,
    "followup_2_days": 11,
    "drive_retention_days": 30,
    "lead_retention_days": 180,
    # Offer (§2.1)
    "rate_default": "$1",
    "rate_sea": "$0.50",
    "min_views": 10000,
    "monthly_cap": "$300",
    # Sender. The first email offers the deal; a sample clip is made only after the streamer replies.
    "sender_name": "",
    "company_name": "Nexdev",
    "proof_url": "https://www.nexdevsoftware.com/",
    # Templates. Placeholders: {name} {day} {date} {rate} {min_views} {cap} {sender_name} {company}
    # {proof_url} {subject}
    "tpl_en_subject": "Clipping your streams, you only pay for views",
    "tpl_en_first": (
        "Hello {name},\n\n"
        "I hope you're having a great week!\n\n"
        "We've been watching your streams recently and genuinely find your content super entertaining.\n\n"
        "We run a content team specializing in editing and distributing stream highlights across TikTok, "
        "YouTube Shorts, and Instagram Reels. We want to partner with you to edit, format, and post videos "
        "using your content.\n\n"
        "Here is how our model works:\n\n"
        "Zero upfront cost and zero risk: we handle all the clipping, editing, optimization, and posting.\n\n"
        "{min_views} views first: if a video doesn't reach {min_views} views, you don't pay a single cent.\n\n"
        "Performance-based rate: you pay {rate} per 1,000 views only on videos that pass {min_views} views, "
        "with a {cap} monthly cap so the bill never surprises you.\n\n"
        "This makes it a complete win-win for you: you get free exposure, brand awareness, and new live-stream "
        "viewers across major platforms without taking any time away from streaming or risking money on "
        "unproven content. We are only paid when we bring actual, measurable reach to your channel.\n\n"
        "If you're open to it, reply and we'll make a free sample clip from one of your recent streams so you "
        "can see our work first.\n\n"
        "Best regards,\n\n"
        "{company}\n"
        "{proof_url}\n\n"
        "If you'd rather not hear from us, reply \"no\" and we won't email again."
    ),
    "tpl_en_followup_1": (
        "Hello {name},\n\n"
        "Bumping this in case it got buried. We'd love to clip your streams, and you pay nothing unless a "
        "video passes {min_views} views. Want a free sample clip from one of your recent streams?\n\n"
        "{company}\n"
        "If you'd rather not hear from us, reply \"no\" and we won't email again."
    ),
    "tpl_en_followup_2": (
        "Hello {name},\n\n"
        "Last note from us. If clips are not a priority right now, no problem. If that changes, just reply "
        "and we'll send a free sample clip.\n\n"
        "{company}\n"
        "Reply \"no\" and we won't email again."
    ),
    "tpl_id_subject": "Klip dari stream kamu, bayar hanya per view",
    "tpl_id_first": (
        "Halo {name},\n\n"
        "Semoga minggumu menyenangkan!\n\n"
        "Belakangan kami menonton stream kamu dan kontennya benar-benar seru.\n\n"
        "Kami tim konten yang mengedit dan menyebarkan highlight stream di TikTok, YouTube Shorts, dan "
        "Instagram Reels. Kami ingin bekerja sama untuk mengedit, memformat, dan memposting video dari "
        "konten kamu.\n\n"
        "Cara kerjanya:\n\n"
        "Tanpa biaya di depan dan tanpa risiko: semua klip, edit, optimasi, dan posting kami yang urus.\n\n"
        "{min_views} view dulu: kalau videonya tidak tembus {min_views} view, kamu tidak bayar sepeser pun.\n\n"
        "Bayar sesuai hasil: {rate} per 1.000 view, hanya untuk video yang tembus {min_views} view, dengan "
        "batas {cap} per bulan supaya tagihannya tidak bikin kaget.\n\n"
        "Jadi kamu dapat eksposur gratis dan penonton live baru tanpa mengurangi waktu streaming atau "
        "mempertaruhkan uang. Kami hanya dibayar kalau kami benar-benar mendatangkan jangkauan.\n\n"
        "Kalau tertarik, balas email ini dan kami buatkan satu klip contoh gratis dari stream kamu.\n\n"
        "Salam,\n\n"
        "{company}\n"
        "{proof_url}\n\n"
        "Kalau tidak mau dihubungi lagi, balas \"tidak\" dan kami tidak akan email lagi."
    ),
    "tpl_id_followup_1": (
        "Halo {name},\n\n"
        "Mengangkat email ini lagi, siapa tahu tertimbun. Kamu tidak bayar apa-apa kecuali videonya tembus "
        "{min_views} view. Mau kami buatkan satu klip contoh gratis dari stream kamu?\n\n"
        "{company}\n"
        "Kalau tidak mau dihubungi lagi, balas \"tidak\" dan kami tidak akan email lagi."
    ),
    "tpl_id_followup_2": (
        "Halo {name},\n\n"
        "Ini email terakhir dari kami. Kalau klip belum jadi prioritas, tidak apa-apa. Kalau nanti berubah "
        "pikiran, balas saja dan kami kirim klip contoh gratis.\n\n"
        "{company}\n"
        "Balas \"tidak\" dan kami tidak akan email lagi."
    ),
    # Internal state written by the daemon and the web app
    "run_now": 0,
    "last_run_date": "",
    "last_run_summary": "",
    "finder_status": "",  # running | done | failed, written by run_finders
    "finder_error": "",
    "finder_started_at": "",
    "finder_finished_at": "",
    "last_nightly_date": "",
    "twitch_sample_now": 0,
    "twitch_last_sample_slot": "",
    "twitch_last_summary": "",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'youtube',
    channel_id TEXT NOT NULL UNIQUE,  -- YouTube: the UC... id. Others: "<platform>:<login>", see channel_key()
    url TEXT,
    name TEXT,
    handle TEXT,
    thumbnail TEXT,
    description_excerpt TEXT,
    email TEXT,
    email_source TEXT,
    instagram TEXT,
    x TEXT,
    tiktok TEXT,
    discord TEXT,
    website TEXT,
    twitch TEXT,  -- login linked in the channel description: the streamer's main platform
    kick TEXT,    -- slug, same
    stream_source TEXT DEFAULT 'live',  -- 'live' (YouTube live streams) or 'reupload' (stream VODs uploaded later)
    contacts_manual INTEGER DEFAULT 0,
    language TEXT,
    language_api TEXT,
    country TEXT,
    subscribers_or_viewers INTEGER,
    last_stream_at TEXT,
    streams_14d INTEGER,
    avg_stream_h REAL,
    shorts_14d INTEGER,
    youtube TEXT,  -- Twitch/Kick leads: the streamer's YouTube channel URL for the Shorts count (found in the bio or typed in)
    vod_views INTEGER,  -- median views per stream in the look-back window (streams over a day old)
    whop_flag INTEGER DEFAULT 0,
    vod_video_id TEXT,
    vod_title TEXT,
    vod_published_at TEXT,
    vod_duration_s REAL,
    vod_url TEXT,
    vod_manual INTEGER DEFAULT 0,
    fit_score INTEGER,
    fit_reason TEXT,
    status TEXT NOT NULL DEFAULT 'found',
    reject_reason TEXT,
    snoozed_until TEXT,
    search_id INTEGER REFERENCES searches(id) ON DELETE SET NULL,
    twitch_search_id INTEGER,
    spike_source_id INTEGER,
    spike_video_id INTEGER,
    spike_clip_id INTEGER,
    clip_error TEXT,
    clip_queued_at TEXT,
    retry_after TEXT,
    followups_stopped INTEGER DEFAULT 0,
    clip_stream_at TEXT,  -- when the clipped stream ran; our own record, kept after API data is purged
    drive_file_id TEXT,
    drive_url TEXT,
    drive_uploaded_at TEXT,
    reply_sentiment TEXT,
    client_model TEXT,
    client_cap TEXT,         -- per-streamer offer terms; NULL means the default from Settings
    client_rate TEXT,
    client_min_views INTEGER,
    client_start TEXT,
    notes TEXT,
    api_fetched_at TEXT,
    status_at TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status, fit_score DESC);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'youtube' CHECK(platform = 'youtube'),
    query TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'live' CHECK(kind IN ('live', 'reupload')),
    language TEXT,
    region TEXT,
    min_size INTEGER DEFAULT 10000,
    max_size INTEGER DEFAULT 300000,
    min_views INTEGER DEFAULT 0,  -- median views per stream: the real size measure; subscribers only pre-filter
    max_views INTEGER,
    active INTEGER DEFAULT 1,
    last_run_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS twitch_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT,            -- null: every category
    game_name TEXT,
    language TEXT,           -- ISO 639-1, or null for every language
    min_viewers INTEGER NOT NULL DEFAULT 50,
    max_viewers INTEGER NOT NULL DEFAULT 1000,
    active INTEGER DEFAULT 1,
    last_sampled_at TEXT,
    created_at TEXT
);

-- Live viewer samples (Get Streams). Twitch content: deleted after 24 hours.
CREATE TABLE IF NOT EXISTS twitch_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    login TEXT NOT NULL,
    viewers INTEGER NOT NULL,
    language TEXT,
    category TEXT,
    title TEXT,
    sampled_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_twitch_samples_time ON twitch_samples(sampled_at);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('first', 'followup_1', 'followup_2')),
    to_email TEXT,
    subject TEXT,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'queued', 'sending', 'sent', 'failed', 'cancelled')),
    scheduled_for TEXT,
    gmail_message_id TEXT,
    gmail_thread_id TEXT,
    rfc_message_id TEXT,
    error TEXT,
    sent_at TEXT,
    reply_at TEXT,
    reply_snippet TEXT,
    reply_url TEXT,  -- set when a reply outside the thread is logged by hand
    created_at TEXT,
    UNIQUE(lead_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status, scheduled_for);

CREATE TABLE IF NOT EXISTS opt_outs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    channel_id TEXT UNIQUE,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS quota (
    day TEXT NOT NULL,
    bucket TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, bucket)
);

CREATE TABLE IF NOT EXISTS google_account (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    email TEXT,
    refresh_token_enc BLOB,
    scopes TEXT,
    connected_by INTEGER,
    connected_at TEXT,
    error TEXT
);

-- Channels the finder checked and dropped, skipped for 30 days so they do not cost quota every night.
-- Only the ID and our own reason; rows older than 30 days are deleted (Developer Policy III.E.4).
CREATE TABLE IF NOT EXISTS seen (
    platform TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    reason TEXT,
    checked_at TEXT NOT NULL,
    PRIMARY KEY (platform, channel_id)
);

CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL
);
"""

# Columns added after the first release. CREATE TABLE IF NOT EXISTS does not add them to an existing file.
_MIGRATIONS = (
    "ALTER TABLE leads ADD COLUMN vod_url TEXT",
    "ALTER TABLE leads ADD COLUMN vod_manual INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN twitch TEXT",
    "ALTER TABLE leads ADD COLUMN kick TEXT",
    "ALTER TABLE leads ADD COLUMN stream_source TEXT DEFAULT 'live'",
    "ALTER TABLE searches ADD COLUMN kind TEXT NOT NULL DEFAULT 'live'",
    "ALTER TABLE leads ADD COLUMN vod_views INTEGER",
    "ALTER TABLE searches ADD COLUMN min_views INTEGER DEFAULT 0",
    "ALTER TABLE searches ADD COLUMN max_views INTEGER",
    "ALTER TABLE leads ADD COLUMN twitch_search_id INTEGER",
    "ALTER TABLE leads ADD COLUMN clip_stream_at TEXT",
    "ALTER TABLE leads ADD COLUMN client_rate TEXT",
    "ALTER TABLE leads ADD COLUMN client_min_views INTEGER",
    "ALTER TABLE leads ADD COLUMN youtube TEXT",
    "ALTER TABLE messages ADD COLUMN reply_url TEXT",
)

_initialized_path: Optional[str] = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def days_ago_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def connect() -> sqlite3.Connection:
    """Open outreach.db, creating the schema once per path per process."""
    global _initialized_path
    conn = sqlite3.connect(config.OUTREACH_DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if _initialized_path != str(config.OUTREACH_DB_PATH):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already there
        conn.commit()
        _initialized_path = str(config.OUTREACH_DB_PATH)
    return conn


def _query(sql: str, params: Iterable = ()) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def _execute(sql: str, params: Iterable = ()) -> int:
    """Run one write. Returns rowcount."""
    with connect() as conn:
        return conn.execute(sql, tuple(params)).rowcount


def log(message: str, level: str = "info") -> None:
    with connect() as conn:
        conn.execute("INSERT INTO log (ts, level, message) VALUES (?, ?, ?)", (now_iso(), level, message[:1000]))
        conn.execute("DELETE FROM log WHERE ts < ?", (days_ago_iso(30),))
    print(f"  [outreach] {message}")


def recent_log(limit: int = 30) -> List[sqlite3.Row]:
    return _query("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,))


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings() -> Dict[str, Any]:
    """All settings, stored values cast to the type of their default."""
    stored = {r["key"]: r["value"] for r in _query("SELECT key, value FROM settings")}
    out: Dict[str, Any] = {}
    for key, default in DEFAULT_SETTINGS.items():
        raw = stored.get(key)
        if raw is None:
            out[key] = default
            continue
        try:
            out[key] = type(default)(raw) if not isinstance(default, str) else raw
        except (TypeError, ValueError):
            out[key] = default
    return out


def set_settings(values: Dict[str, Any]) -> None:
    unknown = set(values) - set(DEFAULT_SETTINGS)
    if unknown:
        raise KeyError(f"Unknown outreach settings: {sorted(unknown)}")
    with connect() as conn:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, str(v)) for k, v in values.items()],
        )


# ── Leads ─────────────────────────────────────────────────────────────────────

def get_lead(lead_id: int) -> Optional[Dict[str, Any]]:
    rows = _query("SELECT * FROM leads WHERE id = ?", (lead_id,))
    return dict(rows[0]) if rows else None


def get_leads(ids: Iterable[int]) -> List[Dict[str, Any]]:
    ids = [int(i) for i in ids]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return [dict(r) for r in _query(f"SELECT * FROM leads WHERE id IN ({marks})", ids)]


def list_leads(statuses: Iterable[str], order: str = "fit") -> List[Dict[str, Any]]:
    statuses = list(statuses)
    marks = ",".join("?" * len(statuses))
    order_sql = {
        "fit": "COALESCE(fit_score, -1) DESC, created_at DESC",
        "recent": "COALESCE(status_at, created_at) DESC",
    }[order]
    sql = f"SELECT * FROM leads WHERE status IN ({marks})"
    params: List[Any] = statuses
    if "found" in statuses:
        sql += " AND (snoozed_until IS NULL OR snoozed_until <= ?)"
        params = statuses + [now_iso()]
    return [dict(r) for r in _query(sql + f" ORDER BY {order_sql}", params)]


SEEN_DAYS = 30


def channel_key(platform: str, handle: str) -> str:
    """leads.channel_id and opt_outs.channel_id. YouTube ids (UC...) are globally unique as they are;
    Twitch logins and Kick slugs can collide across platforms, so they carry their platform."""
    return handle if platform == "youtube" else f"{platform}:{handle.lower()}"


def get_lead_by_channel(channel_id: str) -> Optional[Dict[str, Any]]:
    rows = _query("SELECT * FROM leads WHERE channel_id = ?", (channel_id,))
    return dict(rows[0]) if rows else None


def forget_seen(platform: str, channel_id: str) -> None:
    _execute("DELETE FROM seen WHERE platform = ? AND channel_id = ?", (platform, channel_id))


def known_channel_ids(platform: str) -> set:
    """Channels the finder must not fetch again: leads, opt-outs, and channels dropped in the last 30 days."""
    return {r[0] for r in _query(
        "SELECT channel_id FROM leads WHERE platform = ? "
        "UNION SELECT channel_id FROM opt_outs WHERE channel_id IS NOT NULL "
        "UNION SELECT channel_id FROM seen WHERE platform = ? AND checked_at >= ?",
        (platform, platform, days_ago_iso(SEEN_DAYS)))}


def mark_seen(platform: str, reasons: Dict[str, str]) -> None:
    """Record dropped channels. Checking one again later refreshes its row."""
    if not reasons:
        return
    now = now_iso()
    with connect() as conn:
        conn.executemany(
            "INSERT INTO seen (platform, channel_id, reason, checked_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(platform, channel_id) DO UPDATE SET reason = excluded.reason, checked_at = excluded.checked_at",
            [(platform, cid, reason[:200], now) for cid, reason in reasons.items()],
        )


def purge_seen(days: int = SEEN_DAYS) -> int:
    """Forget dropped channels after 30 days: they may qualify by now, and the row came from API data."""
    return _execute("DELETE FROM seen WHERE checked_at < ?", (days_ago_iso(days),))


def insert_lead(lead: Dict[str, Any]) -> Optional[int]:
    """Insert a found lead. Returns None when the channel is already known (UNIQUE channel_id)."""
    now = now_iso()
    row = {**lead, "status": lead.get("status", "found"), "created_at": now, "status_at": now}
    cols = ",".join(row)
    marks = ",".join("?" * len(row))
    with connect() as conn:
        cur = conn.execute(f"INSERT OR IGNORE INTO leads ({cols}) VALUES ({marks})", tuple(row.values()))
        return cur.lastrowid if cur.rowcount else None


_LEAD_COLUMNS: Optional[set] = None


def update_lead(lead_id: int, **fields: Any) -> bool:
    """Update lead columns by name. A status change also stamps status_at."""
    global _LEAD_COLUMNS
    if _LEAD_COLUMNS is None:
        _LEAD_COLUMNS = {r["name"] for r in _query("PRAGMA table_info(leads)")}
    bad = set(fields) - _LEAD_COLUMNS
    if bad:
        raise KeyError(f"Unknown lead columns: {sorted(bad)}")
    if "status" in fields:
        assert fields["status"] in STATUSES, fields["status"]
        fields.setdefault("status_at", now_iso())
    if not fields:
        return False
    sets = ",".join(f"{k} = ?" for k in fields)
    return _execute(f"UPDATE leads SET {sets} WHERE id = ?", (*fields.values(), lead_id)) > 0


def status_counts() -> Dict[str, int]:
    now = now_iso()
    rows = _query(
        "SELECT status, COUNT(*) FROM leads WHERE status != 'found' OR snoozed_until IS NULL OR snoozed_until <= ? "
        "GROUP BY status", (now,))
    return {r[0]: r[1] for r in rows}


def attention() -> Tuple[int, str]:
    """Leads waiting on a person (to review, email to send, reply, clip to review) and the newest change among
    them. The sidebar shows the count, and a dot when the newest change is after the viewer's last visit."""
    row = _query(
        """SELECT COUNT(*), MAX(COALESCE(status_at, created_at)) FROM leads l
           WHERE status IN ('replied', 'clip_ready')
              OR (status = 'found' AND (snoozed_until IS NULL OR snoozed_until <= ?))
              OR (status = 'email_ready' AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.lead_id = l.id
                                                         AND m.kind = 'first' AND m.status IN ('queued', 'sending')))""",
        (now_iso(),))[0]
    return row[0], row[1] or ""


def count_created_since(since_iso: str, platform: str) -> int:
    """Leads a finder added since a time, for its daily cap. Leads added by hand do not count."""
    return _query(
        "SELECT COUNT(*) FROM leads WHERE created_at >= ? AND platform = ? "
        "AND (search_id IS NOT NULL OR twitch_search_id IS NOT NULL)", (since_iso, platform))[0][0]


def count_clips_queued_since(since_iso: str) -> int:
    return _query("SELECT COUNT(*) FROM leads WHERE clip_queued_at >= ?", (since_iso,))[0][0]


def delete_lead(lead_id: int) -> None:
    _execute("DELETE FROM leads WHERE id = ?", (lead_id,))


# ── Searches ──────────────────────────────────────────────────────────────────

def list_searches(active_only: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM searches" + (" WHERE active = 1" if active_only else "")
    return [dict(r) for r in _query(sql + " ORDER BY COALESCE(last_run_at, '') ASC, id ASC")]


def add_search(query: str, language: Optional[str], region: Optional[str], min_size: int, max_size: int,
               kind: str = "live", min_views: int = 0, max_views: Optional[int] = None) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO searches (platform, query, kind, language, region, min_size, max_size, min_views, max_views, "
            "active, created_at) VALUES ('youtube', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (query, kind, language or None, region or None, min_size, max_size, min_views, max_views, now_iso()),
        ).lastrowid


def update_search(search_id: int, **fields: Any) -> None:
    allowed = {"query", "language", "region", "min_size", "max_size", "min_views", "max_views", "active", "last_run_at"}
    assert set(fields) <= allowed, set(fields) - allowed
    sets = ",".join(f"{k} = ?" for k in fields)
    _execute(f"UPDATE searches SET {sets} WHERE id = ?", (*fields.values(), search_id))


def delete_search(search_id: int) -> None:
    _execute("DELETE FROM searches WHERE id = ?", (search_id,))


# ── Twitch searches and samples ───────────────────────────────────────────────

def list_twitch_searches(active_only: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM twitch_searches" + (" WHERE active = 1" if active_only else "")
    return [dict(r) for r in _query(sql + " ORDER BY id ASC")]


def add_twitch_search(game_id: Optional[str], game_name: Optional[str], language: Optional[str],
                      min_viewers: int, max_viewers: int) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO twitch_searches (game_id, game_name, language, min_viewers, max_viewers, active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (game_id, game_name, language or None, min_viewers, max_viewers, now_iso())).lastrowid


def update_twitch_search(search_id: int, **fields: Any) -> None:
    assert set(fields) <= {"active", "last_sampled_at", "min_viewers", "max_viewers"}
    sets = ",".join(f"{k} = ?" for k in fields)
    _execute(f"UPDATE twitch_searches SET {sets} WHERE id = ?", (*fields.values(), search_id))


def delete_twitch_search(search_id: int) -> None:
    _execute("DELETE FROM twitch_searches WHERE id = ?", (search_id,))
    _execute("DELETE FROM twitch_samples WHERE search_id = ?", (search_id,))


def add_twitch_samples(search_id: int, streams: List[Dict[str, Any]], sampled_at: str) -> None:
    """Store only what sizing and scoring need from Get Streams rows."""
    if not streams:
        return
    with connect() as conn:
        conn.executemany(
            "INSERT INTO twitch_samples (search_id, user_id, login, viewers, language, category, title, sampled_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(search_id, s["user_id"], s["user_login"].lower(), int(s.get("viewer_count", 0)), s.get("language"),
              s.get("game_name"), (s.get("title") or "")[:200], sampled_at) for s in streams])


def purge_twitch_samples(hours: int = 24) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return _execute("DELETE FROM twitch_samples WHERE sampled_at < ?", (cutoff,))


def twitch_sample_summary(hours: int = 24) -> List[Dict[str, Any]]:
    """One row per channel sampled in the last `hours`: average viewers over distinct sample times, and the
    newest search, language, category and titles."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    by_user: Dict[str, Dict[str, Any]] = {}
    for r in _query("SELECT * FROM twitch_samples WHERE sampled_at >= ? ORDER BY sampled_at ASC", (cutoff,)):
        u = by_user.setdefault(r["user_id"], {"user_id": r["user_id"], "views": {}, "titles": []})
        u["views"][r["sampled_at"]] = r["viewers"]  # two searches can catch one stream at one time
        u.update(login=r["login"], search_id=r["search_id"], language=r["language"], category=r["category"])
        if r["title"] and r["title"] not in u["titles"]:
            u["titles"].append(r["title"])
    out = []
    for u in by_user.values():
        views = list(u.pop("views").values())
        out.append({**u, "avg_viewers": sum(views) / len(views), "samples": len(views),
                    "titles": "\n".join(u["titles"][-5:])})
    return out


# ── Messages ──────────────────────────────────────────────────────────────────

def get_message(lead_id: int, kind: str) -> Optional[Dict[str, Any]]:
    rows = _query("SELECT * FROM messages WHERE lead_id = ? AND kind = ?", (lead_id, kind))
    return dict(rows[0]) if rows else None


def messages_for(lead_ids: Iterable[int]) -> Dict[int, Dict[str, Dict[str, Any]]]:
    """{lead_id: {kind: message}} for the given leads."""
    ids = [int(i) for i in lead_ids]
    out: Dict[int, Dict[str, Dict[str, Any]]] = {}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    for r in _query(f"SELECT * FROM messages WHERE lead_id IN ({marks})", ids):
        out.setdefault(r["lead_id"], {})[r["kind"]] = dict(r)
    return out


def upsert_draft(lead_id: int, kind: str, to_email: str, subject: str, body: str) -> int:
    """Create or replace an unsent message. A message already sent is never overwritten."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (lead_id, kind, to_email, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'draft', ?)
            ON CONFLICT(lead_id, kind) DO UPDATE SET
                to_email = excluded.to_email, subject = excluded.subject, body = excluded.body,
                status = 'draft', error = NULL, scheduled_for = NULL
            WHERE messages.status IN ('draft', 'failed', 'cancelled')
            """,
            (lead_id, kind, to_email, subject, body, now_iso()),
        )
        return cur.rowcount


def update_message(message_id: int, **fields: Any) -> None:
    allowed = {"to_email", "subject", "body", "status", "scheduled_for", "gmail_message_id", "gmail_thread_id",
               "rfc_message_id", "error", "sent_at", "reply_at", "reply_snippet", "reply_url"}
    assert set(fields) <= allowed, set(fields) - allowed
    sets = ",".join(f"{k} = ?" for k in fields)
    _execute(f"UPDATE messages SET {sets} WHERE id = ?", (*fields.values(), message_id))


def due_messages(now: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in _query(
        "SELECT * FROM messages WHERE status = 'queued' AND scheduled_for <= ? ORDER BY scheduled_for ASC, id ASC",
        (now,))]


def last_scheduled_send() -> Optional[str]:
    rows = _query("SELECT MAX(scheduled_for) FROM messages WHERE status IN ('queued', 'sending')")
    return rows[0][0] if rows else None


def count_sent_since(since_iso: str) -> int:
    return _query("SELECT COUNT(*) FROM messages WHERE status = 'sent' AND sent_at >= ?", (since_iso,))[0][0]


def claim_message(message_id: int) -> bool:
    """queued -> sending, atomically, so one message is never sent twice."""
    return _execute("UPDATE messages SET status = 'sending' WHERE id = ? AND status = 'queued'", (message_id,)) > 0


# ── Opt-outs (never deleted) ──────────────────────────────────────────────────

def add_opt_out(email: Optional[str], channel_id: Optional[str]) -> None:
    with connect() as conn:
        if email:
            conn.execute("INSERT OR IGNORE INTO opt_outs (email, at) VALUES (?, ?)", (email.strip().lower(), now_iso()))
        if channel_id:
            conn.execute("INSERT OR IGNORE INTO opt_outs (channel_id, at) VALUES (?, ?)", (channel_id, now_iso()))


def is_opted_out(email: Optional[str], *channel_ids: Optional[str]) -> bool:
    """True when the address or any of the channel keys opted out. Pass lead_keys(lead) for a lead."""
    keys = [c for c in channel_ids if c] or [""]
    marks = ",".join("?" * len(keys))
    rows = _query(
        f"SELECT 1 FROM opt_outs WHERE (email IS NOT NULL AND email = ?) OR channel_id IN ({marks}) LIMIT 1",
        ((email or "").strip().lower(), *keys),
    )
    return bool(rows)


def lead_keys(lead: Dict[str, Any]) -> List[str]:
    """Every channel key one streamer is known by: the lead's own, plus Twitch/Kick linked in its description.
    An opt-out on any of them covers all."""
    keys = [lead["channel_id"]]
    for platform in ("twitch", "kick"):
        if lead.get(platform):
            keys.append(channel_key(platform, lead[platform]))
    return keys


def find_streamer(twitch: Optional[str], kick: Optional[str]) -> Optional[Dict[str, Any]]:
    """A lead that is already this Twitch/Kick streamer: added by hand under that key, or a YouTube channel
    that links to it. Stops one person from becoming two leads."""
    clauses, params = [], []
    for platform, handle in (("twitch", twitch), ("kick", kick)):
        if handle:
            clauses.append(f"channel_id = ? OR lower({platform}) = ?")
            params += [channel_key(platform, handle), handle.lower()]
    if not clauses:
        return None
    rows = _query(f"SELECT * FROM leads WHERE {' OR '.join(clauses)} LIMIT 1", params)
    return dict(rows[0]) if rows else None


# ── YouTube quota ledger ──────────────────────────────────────────────────────

def quota_day() -> str:
    """YouTube quota resets at midnight Pacific Time."""
    # ponytail: fixed UTC-8 (PST); during PDT the day flips an hour late. Install tzdata for exact DST.
    return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


def quota_used(bucket: str) -> int:
    rows = _query("SELECT used FROM quota WHERE day = ? AND bucket = ?", (quota_day(), bucket))
    return rows[0][0] if rows else 0


def add_quota(bucket: str, units: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO quota (day, bucket, used) VALUES (?, ?, ?) "
            "ON CONFLICT(day, bucket) DO UPDATE SET used = used + excluded.used",
            (quota_day(), bucket, units),
        )
        conn.execute("DELETE FROM quota WHERE day < ?", ((datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),))


# ── Google account (Gmail + Drive) ────────────────────────────────────────────

def get_google_account() -> Optional[Dict[str, Any]]:
    rows = _query("SELECT * FROM google_account WHERE id = 1")
    return dict(rows[0]) if rows else None


def save_google_account(email: str, refresh_token_enc: bytes, scopes: str, user_id: Optional[int]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO google_account (id, email, refresh_token_enc, scopes, connected_by, connected_at, error)
            VALUES (1, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET email = excluded.email, refresh_token_enc = excluded.refresh_token_enc,
                scopes = excluded.scopes, connected_by = excluded.connected_by,
                connected_at = excluded.connected_at, error = NULL
            """,
            (email, refresh_token_enc, scopes, user_id, now_iso()),
        )


def set_google_error(error: Optional[str]) -> None:
    _execute("UPDATE google_account SET error = ? WHERE id = 1", (error,))


def delete_google_account() -> None:
    _execute("DELETE FROM google_account WHERE id = 1")
