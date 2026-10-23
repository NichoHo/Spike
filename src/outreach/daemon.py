"""
Outreach process (OUTREACH.md §6.1: its own process, like the watcher).

Every minute: follow sample clips in Spike, queue requested ones, write drafts, share approved clips, send due emails.
Every hour: check replies, queue follow-ups.
Once a day at run_hour (or the first minute after, if the PC was off): refresh API data, purge data
older than 30 days, apply retention, then run the finder. "Run now" in the dashboard runs the finder only.
"""

import socket
import sys
import time
import traceback
from datetime import datetime
from typing import Callable, Dict

from src.outreach import db, service, twitch, youtube

LOCK_PORT = 47812
TICK_S = 60
HOURLY_S = 3600


def _step(name: str, fn: Callable, *args):
    try:
        result = fn(*args)
        if result and (not isinstance(result, dict) or any(result.values())):
            db.log(f"{name}: {result}")
        return result
    except Exception as e:
        db.log(f"{name} failed: {e}", "error")
        traceback.print_exc()
        return None


def is_running() -> bool:
    """True when an outreach process holds the lock. Lets the dashboard tell 'running' from 'stuck'."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


def run_finders(settings: Dict) -> None:
    """YouTube, then Twitch. Records running, done or failed for the dashboard."""
    db.set_settings({"finder_status": "running", "finder_error": "", "finder_started_at": db.now_iso()})
    errors = []
    for name, fn in (("YouTube finder", run_finder_now), ("Twitch finder", run_twitch_finder_now)):
        if not settings[name.split()[0].lower() + "_enabled"]:
            continue
        try:
            fn(settings)
        except Exception as e:
            db.log(f"{name} failed: {e}", "error")
            traceback.print_exc()
            errors.append(f"{name}: {e}")
    db.set_settings({"finder_status": "failed" if errors else "done", "finder_error": "; ".join(errors)[:500],
                     "finder_finished_at": db.now_iso(), "run_now": 0})


def run_finder_now(settings: Dict) -> None:
    summary = youtube.run_finder(settings)
    db.log(f"Finder: {summary}")
    db.set_settings({"last_run_summary": (
        f"{summary['searches']} topics searched, {summary['candidates']} new channels, "
        f"{summary['qualified']} passed filters, {summary['added']} streamers added, "
        f"{summary['skipped_seen']} skipped (checked in the last 30 days)"
        + (f". Stopped early: {summary['stopped']}" if summary["stopped"] else "")
    )})


def run_twitch_finder_now(settings: Dict) -> None:
    if not any(s["active"] for s in db.list_twitch_searches()):
        return
    summary = twitch.run_finder(settings)
    db.log(f"Twitch finder: {summary}")
    db.set_settings({"twitch_last_summary": (
        f"{datetime.now():%Y-%m-%d %H:%M}: {summary['sampled_channels']} channels sampled in 24 h, "
        f"{summary['candidates']} in range and new, {summary['qualified']} passed filters, {summary['added']} leads added"
        + (f". Stopped: {summary['stopped']}" if summary["stopped"] else "")
    )})


def sample_twitch(settings: Dict, force: bool = False) -> None:
    """Sample live Twitch channels once per listed hour (this PC's time), or now when asked."""
    if not settings["twitch_enabled"] or twitch.credentials_problem():
        return
    now = datetime.now()
    slot = f"{now:%Y-%m-%d} {now.hour}"
    hours = {int(h) for h in settings["twitch_sample_hours"].split(",") if h.strip().isdigit()}
    if force or (now.hour in hours and settings["twitch_last_sample_slot"] != slot):
        db.set_settings({"twitch_last_sample_slot": slot})
        _step("Twitch sample", twitch.sample_live, settings)


def nightly(settings: Dict) -> None:
    _step("Refresh", youtube.refresh_leads, settings)
    _step("Twitch refresh", twitch.refresh_leads, settings)
    _step("Purge API data older than 30 days", youtube.purge_stale)
    _step("Forget channels checked over 30 days ago", db.purge_seen)
    _step("Retention", service.apply_retention, settings)
    _step("Forget Twitch samples over 24 hours old", db.purge_twitch_samples)
    run_finders(settings)


def tick(state: Dict[str, float]) -> None:
    settings = db.get_settings()
    now = time.time()
    _step("Clip sync", service.sync_clips)
    _step("Trial clips queued", service.queue_trial_clips, settings)
    _step("Drafts", service.draft_emails, settings)
    _step("Sample clips shared", service.share_clips)
    if now - state.get("hourly", 0) >= HOURLY_S:
        state["hourly"] = now
        _step("Replies", service.check_replies)
        _step("Follow-ups queued", service.schedule_followups, settings)
    _step("Send", service.send_due, settings)

    today = datetime.now().strftime("%Y-%m-%d")
    if datetime.now().hour >= settings["run_hour"] and settings["last_nightly_date"] != today:
        db.set_settings({"last_nightly_date": today})
        nightly(settings)
    elif settings["run_now"]:  # cleared by run_finders when done, so the dashboard can show "starting"
        run_finders(settings)
    if settings["twitch_sample_now"]:
        db.set_settings({"twitch_sample_now": 0})
        sample_twitch(settings, force=True)
    else:
        sample_twitch(settings)


def run_daemon() -> None:
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))  # the OS frees it when this process dies
    except OSError:
        print(f"[outreach] Already running (port {LOCK_PORT} taken). Exiting.")
        sys.exit(1)
    print("[outreach] Outreach process running. Ctrl+C to stop.")
    state: Dict[str, float] = {}
    while True:
        try:
            tick(state)
        except Exception as e:  # never die: the web app restarts us, but a crash loop helps nobody
            print(f"[outreach] Tick error: {e}")
            traceback.print_exc()
        time.sleep(TICK_S)
