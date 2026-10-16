"""
Spike: SQLite database initialization and operations.
Blueprint §9: WAL mode, foreign keys on, times in UTC ISO-8601.
"""

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables and indexes if they do not exist, and seed default records."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            name TEXT,
            role TEXT CHECK(role IN ('admin', 'member')) DEFAULT 'member',
            active INTEGER DEFAULT 1,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            external_id TEXT NOT NULL,
            display_name TEXT,
            permission TEXT DEFAULT 'none',
            permission_note TEXT,
            auto_process INTEGER DEFAULT 0,
            style_notes TEXT,
            language TEXT,
            layout TEXT DEFAULT 'split',
            facecam_box TEXT,
            caption_style TEXT DEFAULT 'bold_pop',
            caption_y REAL DEFAULT 0.85,
            music INTEGER DEFAULT 0,
            default_music_mood TEXT DEFAULT 'chill',
            silence_trim INTEGER DEFAULT 1,
            punch_in_zoom INTEGER DEFAULT 1,
            chat_offset_s REAL DEFAULT 12.0,
            chat_tokens TEXT,
            auto_post TEXT,
            created_at TEXT,
            UNIQUE(kind, external_id)
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
            origin TEXT NOT NULL,
            external_id TEXT,
            url TEXT,
            title TEXT,
            duration_s REAL,
            chat_offset_s REAL,
            status TEXT DEFAULT 'queued',
            stage TEXT DEFAULT 'fetch_meta',
            error TEXT,
            attempts INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 1,
            created_at TEXT,
            claimed_at TEXT,
            finished_at TEXT,
            submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE(origin, external_id)
        );

        CREATE INDEX IF NOT EXISTS idx_videos_status_priority
            ON videos(status, priority DESC, created_at);

        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            peak_t REAL,
            start_s REAL NOT NULL,
            end_s REAL NOT NULL,
            origin TEXT NOT NULL,
            chat_mood TEXT,
            signal_score INTEGER,
            llm_score INTEGER,
            final_score INTEGER,
            av_score INTEGER,
            punchline TEXT,
            features TEXT,
            title TEXT,
            hook_text TEXT,
            post_caption TEXT,
            hashtags TEXT,
            reason TEXT,
            mood TEXT,
            needs_context INTEGER DEFAULT 0,
            status TEXT DEFAULT 'proposed'
        );

        CREATE INDEX IF NOT EXISTS idx_candidates_video
            ON candidates(video_id, status, final_score DESC);

        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            version INTEGER DEFAULT 1,
            layout TEXT DEFAULT 'split',
            caption_style TEXT DEFAULT 'bold_pop',
            trim_start_s REAL,
            trim_end_s REAL,
            caption_overrides TEXT,
            music_track TEXT,
            silence_trim INTEGER DEFAULT 0,
            punch_in_zoom INTEGER DEFAULT 1,
            file_path TEXT,
            thumb_path TEXT,
            status TEXT DEFAULT 'ready',
            reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TEXT,
            reject_reason TEXT,
            created_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_clips_candidate
            ON clips(candidate_id, status);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
            level TEXT DEFAULT 'info',
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS claude_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            video_id INTEGER,
            label TEXT NOT NULL,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT CHECK(platform IN ('youtube', 'tiktok', 'instagram')),
            display_name TEXT,
            access_token_enc BLOB,
            refresh_token_enc BLOB,
            expires_at TEXT,
            connected_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            status TEXT CHECK(status IN ('scheduled', 'uploading', 'posted', 'sent_to_inbox', 'failed')) DEFAULT 'scheduled',
            scheduled_for TEXT,
            caption TEXT,
            hashtags TEXT,
            platform_post_id TEXT,
            url TEXT,
            error TEXT,
            posted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT,
            posted_at TEXT,
            UNIQUE(clip_id, account_id)
        );

        CREATE INDEX IF NOT EXISTS idx_posts_status_scheduled
            ON posts(status, scheduled_for);

        CREATE TABLE IF NOT EXISTS post_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            measured_at TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS clip_ai_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            comment TEXT NOT NULL,
            result_json TEXT,
            ok INTEGER DEFAULT 1,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS candidate_renders (
            candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
            status TEXT DEFAULT 'queued',
            error TEXT,
            requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS creator_profiles (
            channel_key TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS stage_timings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            stage TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );
        """)

        # Safely migrate existing tables if columns are missing
        migration_statements = [
            "ALTER TABLE videos ADD COLUMN submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE videos ADD COLUMN claimed_at TEXT",
            "ALTER TABLE videos ADD COLUMN finished_at TEXT",
            "ALTER TABLE sources ADD COLUMN default_music_mood TEXT DEFAULT 'chill'",
            "ALTER TABLE sources ADD COLUMN silence_trim INTEGER DEFAULT 0",
            "ALTER TABLE sources ADD COLUMN punch_in_zoom INTEGER DEFAULT 1",
            "ALTER TABLE clips ADD COLUMN silence_trim INTEGER DEFAULT 0",
            "ALTER TABLE clips ADD COLUMN punch_in_zoom INTEGER DEFAULT 1",
            "ALTER TABLE videos ADD COLUMN settings TEXT",  # JSON processing options chosen at submit
            "ALTER TABLE videos ADD COLUMN continue_count INTEGER DEFAULT 0",  # Continue presses; Retry shows once one failed again
            "ALTER TABLE clips ADD COLUMN show_hook INTEGER DEFAULT 0",  # hook title burned into the video
            "ALTER TABLE clips ADD COLUMN layout_changes TEXT",  # JSON [{t, layout}] mid-clip layout switches
            "ALTER TABLE clips ADD COLUMN letterbox_style TEXT DEFAULT 'blur'",
            "ALTER TABLE candidates ADD COLUMN cuts TEXT",  # JSON [[start_s, end_s]] removed from the clip (stream seconds)
            "ALTER TABLE candidates ADD COLUMN payoff_t REAL",  # stream second of the payoff line, the default zoom spot
            "ALTER TABLE clips ADD COLUMN cuts TEXT",  # JSON [[start_s, end_s]]; edited on the clip page and by "Ask the editor"
            "ALTER TABLE clips ADD COLUMN concept TEXT DEFAULT 'single'",  # single, story, pov, top3, top5
            "ALTER TABLE clips ADD COLUMN segments TEXT",  # JSON [{candidate_id, start_s, end_s, remove, rank, label}], stream seconds
            "ALTER TABLE clips ADD COLUMN overlay TEXT",   # JSON {pov_text, pov_options, emotion, skip_card, callback_quote, foreshadow}
            "ALTER TABLE clips ADD COLUMN theme TEXT",
            "ALTER TABLE clips ADD COLUMN concept_source TEXT",  # ai or user
            "ALTER TABLE candidates ADD COLUMN concept TEXT DEFAULT 'single'",
            "ALTER TABLE candidates ADD COLUMN concept_spec TEXT",  # JSON {segments, overlay, theme, concept_source}: what the worker renders
            "ALTER TABLE sources ADD COLUMN auto_concepts TEXT",  # JSON list of concepts the pipeline may propose
            "ALTER TABLE candidates ADD COLUMN segments TEXT",  # JSON [[start_s, end_s]] of a story clip (stream seconds)
            "ALTER TABLE candidates ADD COLUMN zooms TEXT",  # JSON [{t, scale, hold_s}]; t is clip time for stories
            "ALTER TABLE clips ADD COLUMN zooms TEXT",  # JSON [{t, scale, hold_s}]; an empty list means no zoom
            "ALTER TABLE candidates ADD COLUMN humor_type TEXT",
            "ALTER TABLE candidates ADD COLUMN why_funny TEXT",
            "ALTER TABLE candidates ADD COLUMN status_reason TEXT",  # why a candidate is low_score or rejected
            "ALTER TABLE sources ADD COLUMN creator_profile TEXT",  # JSON, see src/profile.py
            "ALTER TABLE sources ADD COLUMN learned_prefs TEXT",  # JSON list of up to 10 strings
            "ALTER TABLE sources ADD COLUMN letterbox_style TEXT DEFAULT 'title'",  # "title" (white bars + title) or "blur"
        ]
        for stmt in migration_statements:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

        # Seed default admin user if none exists
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            cur.execute(
                """
                INSERT INTO users (login, name, role, active, created_at)
                VALUES ('admin@local', 'Admin', 'admin', 1, ?)
                """,
                (now_utc_iso(),)
            )


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_login(login: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()


def create_user(login: str, name: str, role: str = "member") -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (login, name, role, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(login) DO UPDATE SET
                name = excluded.name,
                role = excluded.role,
                active = 1
            RETURNING id
            """,
            (login, name, role, now_utc_iso())
        )
        return cur.fetchone()[0]


def update_user_status(user_id: int, active: int):
    with get_connection() as conn:
        conn.execute("UPDATE users SET active = ? WHERE id = ?", (active, user_id))


# ── Videos / Jobs ─────────────────────────────────────────────────────────────

def register_video(
    origin: str,
    url_or_path: str,
    external_id: Optional[str] = None,
    title: Optional[str] = None,
    source_id: Optional[int] = None,
    submitted_by: Optional[int] = None,
    priority: int = 1,
    settings: Optional[Dict[str, Any]] = None,
) -> int:
    """Register or get a video in the videos table. settings: per-job processing options (JSON)."""
    now = now_utc_iso()
    settings_json = json.dumps(settings) if settings else None
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO videos (origin, external_id, url, title, source_id, submitted_by, priority, settings, status, stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'fetch_meta', ?)
            ON CONFLICT(origin, external_id) DO UPDATE SET
                status = CASE WHEN status = 'failed' OR error = 'Cancelled by user' THEN 'queued' ELSE status END,
                stage = CASE WHEN status = 'failed' OR error = 'Cancelled by user' THEN 'fetch_meta' ELSE stage END,
                error = CASE WHEN status = 'failed' OR error = 'Cancelled by user' THEN NULL ELSE error END,
                priority = MAX(priority, excluded.priority),
                settings = COALESCE(excluded.settings, settings)
            RETURNING id
            """,
            (origin, external_id or url_or_path, url_or_path, title or url_or_path, source_id, submitted_by, priority, settings_json, now)
        )
        row = cur.fetchone()
        return row[0]


def update_video_stage(video_id: int, stage: str, status: str = "running", error: Optional[str] = None):
    now = now_utc_iso()
    with get_connection() as conn:
        if stage == "fetch_meta":
            conn.execute("DELETE FROM stage_timings WHERE video_id = ?", (video_id,))
        if status == "failed":
            conn.execute("DELETE FROM stage_timings WHERE video_id = ? AND finished_at IS NULL", (video_id,))
        else:
            conn.execute("UPDATE stage_timings SET finished_at = ? WHERE video_id = ? AND finished_at IS NULL", (now, video_id))
            conn.execute("INSERT INTO stage_timings (video_id, stage, started_at) VALUES (?, ?, ?)", (video_id, stage, now))
        conn.execute(
            """
            UPDATE videos
            SET stage = ?, status = ?, error = ?, attempts = attempts + 1
            WHERE id = ?
            """,
            (stage, status, error, video_id)
        )


def finish_video(video_id: int, status: str = "ready"):
    now = now_utc_iso()
    with get_connection() as conn:
        conn.execute("UPDATE stage_timings SET finished_at = ? WHERE video_id = ? AND finished_at IS NULL", (now, video_id))
        conn.execute(
            """
            UPDATE videos
            SET status = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, now, video_id)
        )


def get_job(video_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT v.*, s.display_name as source_name, s.kind as source_kind
            FROM videos v
            LEFT JOIN sources s ON v.source_id = s.id
            WHERE v.id = ?
            """,
            (video_id,)
        ).fetchone()


def list_jobs(limit: int = 100) -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT v.*, s.display_name as source_name, s.kind as source_kind
            FROM videos v
            LEFT JOIN sources s ON v.source_id = s.id
            ORDER BY
                CASE v.status
                    WHEN 'running' THEN 1
                    WHEN 'queued' THEN 2
                    WHEN 'failed' THEN 3
                    WHEN 'ready' THEN 4
                    ELSE 5
                END,
                v.created_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()


def continue_job(video_id: int) -> bool:
    """Requeue a failed job. The pipeline skips every stage whose output is already on disk."""
    with get_connection() as conn:
        res = conn.execute(
            """
            UPDATE videos
            SET status = 'queued', stage = NULL, error = NULL, continue_count = COALESCE(continue_count, 0) + 1
            WHERE id = ? AND status = 'failed'
            """,
            (video_id,)
        )
        return res.rowcount > 0


def restart_job(video_id: int) -> bool:
    """Requeue a failed job to run from the first stage: its candidates, clips and renders are deleted here
    (the caller deletes the job's folder)."""
    with get_connection() as conn:
        failed = conn.execute("SELECT 1 FROM videos WHERE id = ? AND status = 'failed'", (video_id,)).fetchone()
        if not failed:
            return False
        conn.execute("DELETE FROM candidates WHERE video_id = ?", (video_id,))  # clips and renders cascade
        conn.execute(
            "UPDATE videos SET status = 'queued', stage = 'fetch_meta', error = NULL, continue_count = 0 WHERE id = ?", (video_id,)
        )
        return True


def cancel_job(video_id: int) -> bool:
    with get_connection() as conn:
        res = conn.execute(
            """
            UPDATE videos
            SET status = 'done', error = 'Cancelled by user'
            WHERE id = ? AND status IN ('queued', 'running')
            """,
            (video_id,)
        )
        return res.rowcount > 0


# ── Candidates & Clips ────────────────────────────────────────────────────────

def insert_candidate(video_id: int, cand: Dict[str, Any]) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO candidates (
                video_id, peak_t, start_s, end_s, origin, chat_mood,
                signal_score, llm_score, final_score, av_score,
                punchline, features, title, hook_text, post_caption,
                hashtags, reason, mood, needs_context, status, humor_type, why_funny, status_reason, cuts, payoff_t, segments, zooms, concept, concept_spec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                video_id,
                cand.get("peak_t"),
                cand["start_s"],
                cand["end_s"],
                cand.get("origin", "signal"),
                cand.get("chat_mood"),
                cand.get("signal_score"),
                cand.get("llm_score"),
                cand.get("final_score"),
                cand.get("av_score"),
                cand.get("punchline"),
                json.dumps(cand.get("features", {})),
                cand.get("title"),
                cand.get("hook_text"),
                cand.get("post_caption"),
                json.dumps(cand.get("hashtags", [])),
                cand.get("reason"),
                cand.get("mood"),
                1 if cand.get("needs_context") else 0,
                cand.get("status", "proposed"),
                cand.get("humor_type"),
                cand.get("why_funny"),
                cand.get("status_reason"),
                json.dumps(cand.get("cuts") or []),
                cand.get("payoff_t"),
                json.dumps(cand["segments"]) if cand.get("segments") else None,
                json.dumps(cand["zooms"]) if cand.get("zooms") is not None else None,
                cand.get("concept") or "single",
                json.dumps(cand["concept_spec"]) if cand.get("concept_spec") else None,
            )
        )
        return cur.fetchone()[0]


def get_candidates(video_id: int, status: Optional[str] = None) -> List[sqlite3.Row]:
    with get_connection() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM candidates WHERE video_id = ? AND status = ? ORDER BY final_score DESC",
                (video_id, status)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM candidates WHERE video_id = ? ORDER BY final_score DESC",
            (video_id,)
        ).fetchall()


def create_or_update_clip(
    candidate_id: int,
    file_path: str,
    thumb_path: str,
    layout: str = "split",
    caption_style: str = "bold_pop",
    trim_start_s: Optional[float] = None,
    trim_end_s: Optional[float] = None,
    music_track: Optional[str] = None,
    silence_trim: int = 0,
    punch_in_zoom: int = 1,
    status: str = "ready",
    show_hook: int = 0,
    letterbox_style: str = "title",
    cuts: Optional[str] = None,
    zooms: Optional[str] = None,
    concept: Optional[str] = None,
    segments: Optional[str] = None,
    overlay: Optional[str] = None,
    theme: Optional[str] = None,
    concept_source: Optional[str] = None,
) -> int:
    """Insert or update a clip for a candidate. `cuts` is JSON [[start_s, end_s]]; None keeps the stored cuts."""
    now = now_utc_iso()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, version FROM clips WHERE candidate_id = ?", (candidate_id,))
        row = cur.fetchone()
        if row:
            clip_id = row[0]
            new_version = row[1] + 1
            cur.execute(
                """
                UPDATE clips
                SET version = ?, layout = ?, caption_style = ?, trim_start_s = ?, trim_end_s = ?,
                    music_track = ?, silence_trim = ?, punch_in_zoom = ?, show_hook = ?,
                    letterbox_style = ?, file_path = ?, thumb_path = ?, status = ?, cuts = COALESCE(?, cuts), zooms = COALESCE(?, zooms),
                    concept = COALESCE(?, concept), segments = COALESCE(?, segments), overlay = COALESCE(?, overlay),
                    theme = COALESCE(?, theme), concept_source = COALESCE(?, concept_source)
                WHERE id = ?
                """,
                (
                    new_version, layout, caption_style, trim_start_s, trim_end_s,
                    music_track, silence_trim, punch_in_zoom, show_hook, letterbox_style,
                    file_path, thumb_path, status, cuts, zooms, concept, segments, overlay, theme, concept_source, clip_id
                )
            )
            return clip_id
        else:
            cur.execute(
                """
                INSERT INTO clips (
                    candidate_id, version, layout, caption_style, trim_start_s, trim_end_s,
                    music_track, silence_trim, punch_in_zoom, show_hook, letterbox_style,
                    file_path, thumb_path, status, created_at, cuts, zooms, concept, segments, overlay, theme, concept_source
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    candidate_id, layout, caption_style, trim_start_s, trim_end_s,
                    music_track, silence_trim, punch_in_zoom, show_hook, letterbox_style,
                    file_path, thumb_path, status, now, cuts, zooms, concept or "single", segments, overlay, theme, concept_source
                )
            )
            return cur.fetchone()[0]


def get_clip(clip_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()


def get_clip_with_details(clip_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.*,
                   cand.title as cand_title, cand.hook_text as cand_hook,
                   cand.punchline, cand.reason, cand.final_score, cand.signal_score,
                   cand.llm_score, cand.mood, cand.chat_mood, cand.features,
                   cand.needs_context, cand.post_caption as cand_caption,
                   cand.start_s as orig_start_s, cand.end_s as orig_end_s, cand.payoff_t, cand.segments AS cand_segments,
                   v.id as video_id, v.title as video_title, v.url as video_url,
                   s.id as source_id, s.display_name as source_name, s.kind as source_kind,
                   s.permission as source_permission
            FROM clips c
            JOIN candidates cand ON c.candidate_id = cand.id
            JOIN videos v ON cand.video_id = v.id
            LEFT JOIN sources s ON v.source_id = s.id
            WHERE c.id = ?
            """,
            (clip_id,)
        ).fetchone()


def list_review_clips(source_id: Optional[int] = None, status: str = "ready") -> List[sqlite3.Row]:
    """Clips grouped by job, highest score first."""
    with get_connection() as conn:
        query = """
            SELECT c.*,
                   cand.title as cand_title, cand.hook_text as cand_hook,
                   cand.reason, cand.final_score, cand.signal_score, cand.llm_score,
                   cand.mood, cand.chat_mood, cand.humor_type, cand.why_funny,
                   cand.start_s as orig_start_s, cand.end_s as orig_end_s,
                   v.id as video_id, v.title as video_title, v.url as video_url, v.created_at as video_created_at,
                   s.id as source_id, s.display_name as source_name
            FROM clips c
            JOIN candidates cand ON c.candidate_id = cand.id
            JOIN videos v ON cand.video_id = v.id
            LEFT JOIN sources s ON v.source_id = s.id
            WHERE c.status = ?
        """
        params = [status]
        if source_id:
            query += " AND s.id = ?"
            params.append(source_id)

        query += " ORDER BY v.created_at DESC, cand.final_score DESC"
        return conn.execute(query, tuple(params)).fetchall()


def update_clip_title(clip_id: int, title: str) -> bool:
    with get_connection() as conn:
        res = conn.execute(
            "UPDATE candidates SET title = ? WHERE id = (SELECT candidate_id FROM clips WHERE id = ?)",
            (title, clip_id),
        )
        return res.rowcount > 0


def update_candidate_hook(candidate_id: int, hook_text: str) -> bool:
    with get_connection() as conn:
        res = conn.execute("UPDATE candidates SET hook_text = ? WHERE id = ?", (hook_text, candidate_id))
        return res.rowcount > 0


def set_clip_render_state(clip_id: int, status: str) -> bool:
    """Flip only clips.status (rendering marker / restore); leaves review fields alone."""
    with get_connection() as conn:
        return conn.execute("UPDATE clips SET status = ? WHERE id = ?", (status, clip_id)).rowcount > 0


def set_clip_layout_changes(clip_id: int, layout_changes_json: Optional[str]) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE clips SET layout_changes = ? WHERE id = ?", (layout_changes_json, clip_id))


def reset_stuck_renders() -> int:
    """Called at web startup: no render can be in flight then, so 'rendering' means it was killed."""
    with get_connection() as conn:
        return conn.execute("UPDATE clips SET status = 'ready' WHERE status = 'rendering'").rowcount


def update_clip_status(
    clip_id: int,
    status: str,
    user_id: Optional[int] = None,
    reject_reason: Optional[str] = None
) -> bool:
    now = now_utc_iso()
    with get_connection() as conn:
        res = conn.execute(
            """
            UPDATE clips
            SET status = ?, reviewed_by = ?, reviewed_at = ?, reject_reason = ?
            WHERE id = ?
            """,
            (status, user_id, now, reject_reason, clip_id)
        )
        return res.rowcount > 0


# ── Sources ───────────────────────────────────────────────────────────────────

def list_sources() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT s.*,
                   COUNT(DISTINCT v.id) as video_count,
                   COUNT(DISTINCT c.id) as clip_count,
                   MAX(v.created_at) as last_vod_at
            FROM sources s
            LEFT JOIN videos v ON v.source_id = s.id
            LEFT JOIN candidates cand ON cand.video_id = v.id
            LEFT JOIN clips c ON c.candidate_id = cand.id
            GROUP BY s.id
            ORDER BY s.display_name ASC
            """
        ).fetchall()


def get_source(source_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()


def create_source(data: Dict[str, Any]) -> int:
    now = now_utc_iso()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sources (
                kind, external_id, display_name, permission, permission_note,
                auto_process, style_notes, language, layout, facecam_box,
                caption_style, caption_y, music, default_music_mood,
                silence_trim, punch_in_zoom, chat_offset_s, letterbox_style, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, external_id) DO UPDATE SET
                display_name = excluded.display_name,
                permission = excluded.permission,
                permission_note = excluded.permission_note,
                auto_process = excluded.auto_process,
                style_notes = excluded.style_notes,
                language = excluded.language,
                layout = excluded.layout,
                facecam_box = excluded.facecam_box,
                caption_style = excluded.caption_style,
                caption_y = excluded.caption_y,
                music = excluded.music,
                default_music_mood = excluded.default_music_mood,
                silence_trim = excluded.silence_trim,
                punch_in_zoom = excluded.punch_in_zoom,
                chat_offset_s = excluded.chat_offset_s,
                letterbox_style = excluded.letterbox_style
            RETURNING id
            """,
            (
                data.get("kind", "youtube"),
                data["external_id"],
                data.get("display_name", data["external_id"]),
                data.get("permission", "none"),
                data.get("permission_note"),
                1 if data.get("auto_process") else 0,
                data.get("style_notes"),
                data.get("language"),
                data.get("layout", "split"),
                data.get("facecam_box"),
                data.get("caption_style", "bold_pop"),
                data.get("caption_y", 0.85),
                1 if data.get("music") else 0,
                data.get("default_music_mood", "chill"),
                1 if data.get("silence_trim", 1) else 0,
                1 if data.get("punch_in_zoom", 1) else 0,
                data.get("chat_offset_s", 12.0),
                data.get("letterbox_style", "title"),
                now
            )
        )
        return cur.fetchone()[0]


def update_source(source_id: int, data: Dict[str, Any]) -> bool:
    with get_connection() as conn:
        res = conn.execute(
            """
            UPDATE sources
            SET display_name = ?, permission = ?, permission_note = ?,
                auto_process = ?, style_notes = ?, language = ?, layout = ?,
                facecam_box = ?, caption_style = ?, caption_y = ?, music = ?,
                default_music_mood = ?, silence_trim = ?, punch_in_zoom = ?,
                chat_offset_s = ?, letterbox_style = ?
            WHERE id = ?
            """,
            (
                data.get("display_name"),
                data.get("permission", "none"),
                data.get("permission_note"),
                1 if data.get("auto_process") else 0,
                data.get("style_notes"),
                data.get("language"),
                data.get("layout", "split"),
                data.get("facecam_box"),
                data.get("caption_style", "bold_pop"),
                data.get("caption_y", 0.85),
                1 if data.get("music") else 0,
                data.get("default_music_mood", "chill"),
                1 if data.get("silence_trim") else 0,
                1 if data.get("punch_in_zoom", 1) else 0,
                data.get("chat_offset_s", 12.0),
                data.get("letterbox_style", "title"),
                source_id
            )
        )
        return res.rowcount > 0


def get_json_column(source_id: int, column: str, default: Any) -> Any:
    """Read a JSON TEXT column of sources (creator_profile, learned_prefs)."""
    assert column in ("creator_profile", "learned_prefs", "auto_concepts")
    with get_connection() as conn:
        row = conn.execute(f"SELECT {column} FROM sources WHERE id = ?", (source_id,)).fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else default
    except (ValueError, TypeError):
        return default


def set_json_column(source_id: int, column: str, value: Any) -> None:
    assert column in ("creator_profile", "learned_prefs", "auto_concepts")
    with get_connection() as conn:
        conn.execute(f"UPDATE sources SET {column} = ? WHERE id = ?", (json.dumps(value), source_id))


def get_cached_profile(channel_key: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT profile_json FROM creator_profiles WHERE channel_key = ?", (channel_key,)).fetchone()
    return json.loads(row[0]) if row else None


def set_cached_profile(channel_key: str, profile: Dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO creator_profiles (channel_key, profile_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(channel_key) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at",
            (channel_key, json.dumps(profile), now_utc_iso()),
        )


# ── "Ask the editor" history ──────────────────────────────────────────────────

def add_clip_ai_edit(clip_id: int, comment: str, result: Dict[str, Any], ok: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO clip_ai_edits (clip_id, comment, result_json, ok, created_at) VALUES (?, ?, ?, ?, ?)",
            (clip_id, comment, json.dumps(result), 1 if ok else 0, now_utc_iso()),
        )


def list_clip_ai_edits(clip_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT comment, result_json, ok, created_at FROM clip_ai_edits WHERE clip_id = ? ORDER BY id DESC LIMIT 10",
            (clip_id,),
        ).fetchall()
    return [{"comment": r["comment"], "result": json.loads(r["result_json"] or "{}"), "ok": bool(r["ok"]), "created_at": r["created_at"]}
            for r in rows]


# ── Other moments: render a stored candidate on demand ───────────────────────

def list_other_moments(video_ids: Optional[List[int]] = None) -> Dict[int, List[Dict[str, Any]]]:
    """low_score and rejected candidates per video with their render job state, best score first.
    video_ids=None means every video."""
    if video_ids is not None and not video_ids:
        return {}
    marks = ",".join("?" * len(video_ids)) if video_ids else ""
    where_video = f"c.video_id IN ({marks}) AND " if video_ids else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.video_id, c.title, c.start_s, c.end_s, c.llm_score, c.status, c.status_reason, c.humor_type,
                   r.status AS render_status, r.error AS render_error
            FROM candidates c
            LEFT JOIN candidate_renders r ON r.candidate_id = c.id
            WHERE {where_video}c.status IN ('low_score', 'rejected')
            ORDER BY c.video_id, c.llm_score DESC, c.start_s
            """,
            tuple(video_ids or ()),
        ).fetchall()
    out: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["video_id"], []).append(dict(r))
    return out


def enqueue_candidate_render(candidate_id: int, user_id: Optional[int] = None) -> bool:
    """Queue a worker job that fetches the section and renders this candidate. False if it is already queued
    or running, or the candidate is gone."""
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM candidates WHERE id = ?", (candidate_id,)).fetchone():
            return False
        row = conn.execute("SELECT status FROM candidate_renders WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row and row["status"] in ("queued", "running"):
            return False
        conn.execute(
            "INSERT INTO candidate_renders (candidate_id, status, requested_by, created_at) VALUES (?, 'queued', ?, ?) "
            "ON CONFLICT(candidate_id) DO UPDATE SET status = 'queued', error = NULL, requested_by = excluded.requested_by, "
            "created_at = excluded.created_at, finished_at = NULL",
            (candidate_id, user_id, now_utc_iso()),
        )
    return True


def claim_candidate_render() -> Optional[int]:
    """Atomically take the oldest queued moment render. Returns the candidate id."""
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE candidate_renders SET status = 'running'
            WHERE candidate_id = (SELECT candidate_id FROM candidate_renders WHERE status = 'queued' ORDER BY created_at LIMIT 1)
            RETURNING candidate_id
            """
        ).fetchone()
    return row[0] if row else None


def finish_candidate_render(candidate_id: int, error: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE candidate_renders SET status = ?, error = ?, finished_at = ? WHERE candidate_id = ?",
            ("failed" if error else "done", error, now_utc_iso(), candidate_id),
        )
        if not error:  # it is a real pick now
            conn.execute("UPDATE candidates SET status = 'selected', status_reason = 'rendered by hand' WHERE id = ?", (candidate_id,))
        else:  # a clip that was waiting for this render keeps its old file
            conn.execute("UPDATE clips SET status = 'ready' WHERE candidate_id = ? AND status = 'rendering'", (candidate_id,))


def set_candidate_concept(candidate_id: int, concept: str, spec: Dict[str, Any], title: Optional[str], hook_text: Optional[str]) -> None:
    """Point a candidate at a concept spec (segments, overlay, theme). The worker renders it from this."""
    segs = spec.get("segments") or []
    with get_connection() as conn:
        conn.execute(
            "UPDATE candidates SET concept = ?, concept_spec = ?, title = COALESCE(?, title), hook_text = COALESCE(?, hook_text), "
            "start_s = ?, end_s = ?, segments = ?, status = 'selected' WHERE id = ?",
            (concept, json.dumps(spec), title, hook_text, min([s["start_s"] for s in segs] or [0]), max([s["end_s"] for s in segs] or [0]),
             json.dumps([[s["start_s"], s["end_s"]] for s in segs]) if concept != "single" else None, candidate_id),
        )


def set_clip_overlay(clip_id: int, overlay: Dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE clips SET overlay = ? WHERE id = ?", (json.dumps(overlay), clip_id))


def get_candidate(candidate_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()


def delete_source(source_id: int) -> bool:
    with get_connection() as conn:
        res = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return res.rowcount > 0


# ── Events & Settings ─────────────────────────────────────────────────────────

def log_event(level: str, message: str, video_id: Optional[int] = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO events (ts, video_id, level, message) VALUES (?, ?, ?, ?)",
            (now_utc_iso(), video_id, level, message)
        )


def add_claude_usage(label: str, tokens_in: int, tokens_out: int, cost_usd: Optional[float], video_id: Optional[int] = None) -> None:
    """One `claude -p` call. tokens_in counts cached input too."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO claude_usage (ts, video_id, label, tokens_in, tokens_out, cost_usd) VALUES (?, ?, ?, ?, ?, ?)",
            (now_utc_iso(), video_id, label, tokens_in, tokens_out, cost_usd),
        )


def claude_usage_summary() -> Dict[str, Any]:
    """Spike's own Claude usage: tokens and calls in the last 5 hours and 7 days (rolling), with the 7-day
    tokens per operation. Plan limits are not published, so this is a count, not a percentage of the plan."""
    now = datetime.now(timezone.utc)
    out: Dict[str, Any] = {}
    with get_connection() as conn:
        for name, delta in (("h5", timedelta(hours=5)), ("d7", timedelta(days=7))):
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), COALESCE(SUM(cost_usd), 0) "
                "FROM claude_usage WHERE ts >= ?", ((now - delta).isoformat(),),
            ).fetchone()
            out[name] = {"calls": row[0], "tokens_in": row[1], "tokens_out": row[2], "tokens": row[1] + row[2], "cost_usd": row[3]}
        rows = conn.execute(
            "SELECT label, COUNT(*), SUM(tokens_in + tokens_out) FROM claude_usage WHERE ts >= ? GROUP BY label ORDER BY 3 DESC",
            ((now - timedelta(days=7)).isoformat(),),
        ).fetchall()
    out["by_label"] = [{"label": r[0], "calls": r[1], "tokens": r[2]} for r in rows]
    return out


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )


# ── Accounts (Blueprint §8, §9) ────────────────────────────────────────────────

def create_account(
    platform: str,
    display_name: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[str] = None,
    connected_by: Optional[int] = None,
) -> int:
    """Create or update a connected platform account with tokens encrypted at rest."""
    from src.security import encrypt_token
    now = now_utc_iso()
    acc_enc = encrypt_token(access_token)
    ref_enc = encrypt_token(refresh_token) if refresh_token else None

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO accounts (platform, display_name, access_token_enc, refresh_token_enc, expires_at, connected_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (platform, display_name, acc_enc, ref_enc, expires_at, connected_by, now)
        )
        return cur.fetchone()[0]


def get_account(account_id: int, decrypt: bool = True) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        if decrypt:
            from src.security import decrypt_token
            res["access_token"] = decrypt_token(res.get("access_token_enc"))
            res["refresh_token"] = decrypt_token(res.get("refresh_token_enc"))
        return res


def list_accounts(decrypt: bool = False) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY created_at ASC").fetchall()
        accounts = []
        for r in rows:
            acc = dict(r)
            if decrypt:
                from src.security import decrypt_token
                acc["access_token"] = decrypt_token(acc.get("access_token_enc"))
                acc["refresh_token"] = decrypt_token(acc.get("refresh_token_enc"))
            else:
                acc.pop("access_token_enc", None)
                acc.pop("refresh_token_enc", None)
            accounts.append(acc)
        return accounts


def delete_account(account_id: int) -> bool:
    with get_connection() as conn:
        res = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return res.rowcount > 0


# ── Posts & Scheduling (Blueprint §8, §9) ─────────────────────────────────────

def create_post(
    clip_id: int,
    account_id: int,
    status: str = "scheduled",
    scheduled_for: Optional[str] = None,
    caption: Optional[str] = None,
    hashtags: Optional[str] = None,
    posted_by: Optional[int] = None,
) -> int:
    now = now_utc_iso()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO posts (clip_id, account_id, status, scheduled_for, caption, hashtags, posted_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(clip_id, account_id) DO UPDATE SET
                status = excluded.status,
                scheduled_for = excluded.scheduled_for,
                caption = excluded.caption,
                hashtags = excluded.hashtags,
                posted_by = excluded.posted_by,
                error = NULL
            RETURNING id
            """,
            (clip_id, account_id, status, scheduled_for or now, caption, hashtags, posted_by, now)
        )
        return cur.fetchone()[0]


def update_post_status(
    post_id: int,
    status: str,
    platform_post_id: Optional[str] = None,
    url: Optional[str] = None,
    error: Optional[str] = None,
):
    now = now_utc_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE posts
            SET status = ?, platform_post_id = COALESCE(?, platform_post_id),
                url = COALESCE(?, url), error = ?,
                posted_at = CASE WHEN ? IN ('posted', 'sent_to_inbox') THEN ? ELSE posted_at END
            WHERE id = ?
            """,
            (status, platform_post_id, url, error, status, now, post_id)
        )


def get_post(post_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()


def get_post_with_details(post_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT p.*,
                   a.platform as account_platform, a.display_name as account_name,
                   c.file_path as clip_file_path, c.thumb_path as clip_thumb_path,
                   c.layout as clip_layout, c.status as clip_status, c.music_track as clip_music_track,
                   cand.id as candidate_id, cand.title as clip_title, cand.hook_text as clip_hook,
                   cand.post_caption as cand_caption, cand.hashtags as cand_hashtags,
                   cand.final_score, cand.llm_score,
                   v.id as video_id, v.title as video_title,
                   s.id as source_id, s.display_name as source_name, s.permission as source_permission
            FROM posts p
            JOIN accounts a ON p.account_id = a.id
            JOIN clips c ON p.clip_id = c.id
            JOIN candidates cand ON c.candidate_id = cand.id
            JOIN videos v ON cand.video_id = v.id
            LEFT JOIN sources s ON v.source_id = s.id
            WHERE p.id = ?
            """,
            (post_id,)
        ).fetchone()


def list_posts(status: Optional[str] = None) -> List[sqlite3.Row]:
    with get_connection() as conn:
        query = """
            SELECT p.*,
                   a.platform as account_platform, a.display_name as account_name,
                   c.file_path as clip_file_path, c.thumb_path as clip_thumb_path,
                   cand.title as clip_title, cand.hook_text as clip_hook,
                   s.display_name as source_name
            FROM posts p
            JOIN accounts a ON p.account_id = a.id
            JOIN clips c ON p.clip_id = c.id
            JOIN candidates cand ON c.candidate_id = cand.id
            JOIN videos v ON cand.video_id = v.id
            LEFT JOIN sources s ON v.source_id = s.id
        """
        params = []
        if status:
            query += " WHERE p.status = ?"
            params.append(status)
        query += " ORDER BY COALESCE(p.scheduled_for, p.created_at) DESC"
        return conn.execute(query, tuple(params)).fetchall()


def get_due_posts(as_of: Optional[str] = None) -> List[sqlite3.Row]:
    now = as_of or now_utc_iso()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT p.*, a.platform as account_platform
            FROM posts p
            JOIN accounts a ON p.account_id = a.id
            WHERE p.status = 'scheduled' AND p.scheduled_for <= ?
            ORDER BY p.scheduled_for ASC
            """,
            (now,)
        ).fetchall()


def count_account_daily_posts(account_id: int, date_iso_prefix: str) -> int:
    """Count posts created/posted for an account today (Blueprint §8.3 cap)."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM posts
            WHERE account_id = ? AND (created_at LIKE ? OR posted_at LIKE ?)
              AND status IN ('scheduled', 'uploading', 'posted', 'sent_to_inbox')
            """,
            (account_id, f"{date_iso_prefix}%", f"{date_iso_prefix}%")
        ).fetchone()
        return row[0] if row else 0


# ── ETA ───────────────────────────────────────────────────────────────────────

PIPELINE_STAGES = ["fetch_meta", "fetch_audio", "fetch_chat", "fetch_crowd", "transcribe",
                   "signals", "moments", "fetch_sections", "render", "render_vertical"]


def estimate_remaining_seconds(jobs: List[Dict[str, Any]]) -> Dict[int, Optional[float]]:
    """Seconds left per active job id, from average past stage durations. None if no history."""
    with get_connection() as conn:
        avg = {r["stage"]: r["d"] for r in conn.execute(
            """SELECT stage, AVG((julianday(finished_at) - julianday(started_at)) * 86400) AS d
               FROM stage_timings WHERE finished_at IS NOT NULL GROUP BY stage""")}
        started = {r["video_id"]: r["started_at"] for r in conn.execute(
            "SELECT video_id, started_at FROM stage_timings WHERE finished_at IS NULL")}
    out: Dict[int, Optional[float]] = {}
    now = datetime.now(timezone.utc)
    for j in jobs:
        if j["status"] != "running" or j.get("stage") not in PIPELINE_STAGES:
            continue
        i = PIPELINE_STAGES.index(j["stage"])
        rest = PIPELINE_STAGES[i + 1:]
        if j["stage"] not in avg or any(st not in avg for st in rest):
            out[j["id"]] = None
            continue
        elapsed = 0.0
        if j["id"] in started:
            elapsed = (now - datetime.fromisoformat(started[j["id"]])).total_seconds()
        out[j["id"]] = max(avg[j["stage"]] - elapsed, 0) + sum(avg[st] for st in rest)
    return out
