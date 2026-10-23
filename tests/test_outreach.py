"""
Outreach (OUTREACH.md §6): finder filters and quota, the lead lifecycle through Spike, sending caps,
follow-ups, reply handling, 30-day purge and retention. All network calls are faked.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from urllib.parse import unquote_plus as urllib_unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.config as config
import src.db as spike_db
from src.outreach import db, google, service, youtube


def ago(days=0, hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(spike_db, "DB_PATH", tmp_path / "spike.db")
    monkeypatch.setattr(config, "OUTREACH_DB_PATH", tmp_path / "outreach.db")
    monkeypatch.setattr(db, "_initialized_path", None)
    monkeypatch.setattr(db, "_LEAD_COLUMNS", None)
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    spike_db.init_db()
    return tmp_path


def add_lead(**kw):
    base = {"channel_id": kw.pop("channel_id", "UC" + "x" * 22), "name": "Rafi", "email": "rafi@studio.id",
            "email_source": "api", "vod_video_id": "vid1", "vod_title": "Main bareng 4 jam",
            "vod_published_at": ago(2), "language": "id", "country": "ID", "fit_score": 80, "api_fetched_at": db.now_iso()}
    base.update(kw)
    return db.insert_lead(base)


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_parsing_helpers():
    assert youtube.parse_duration("PT2H3M4S") == 7384
    assert youtube.parse_duration("P0D") == 0
    assert youtube.parse_duration("P1DT1H") == 90000
    c = youtube.extract_contacts(
        "Business: Collab.Rafi@Gmail.com\nIG instagram.com/rafi.games https://x.com/rafi_gg "
        "tiktok.com/@rafi discord.gg/abc https://linktr.ee/rafi https://rafi.studio/shop")
    assert c == {"email": "collab.rafi@gmail.com", "instagram": "https://instagram.com/rafi.games",
                 "x": "https://x.com/rafi_gg", "tiktok": "https://tiktok.com/@rafi",
                 "discord": "https://discord.gg/abc", "website": "https://rafi.studio/shop", "twitch": None, "kick": None}
    c = youtube.extract_contacts("Live on https://www.twitch.tv/videos/1 and twitch.tv/Rafi_GG/ and kick.com/rafi-id")
    assert (c["twitch"], c["kick"]) == ("rafi_gg", "rafi-id")  # reserved paths skipped, trailing slash fine
    assert youtube.extract_contacts("mail me at you@example.com")["email"] is None


def test_stream_stats_counts_long_streams_and_shorts():
    now = datetime.now(timezone.utc)
    def vid(i, dur, days, live=True):
        v = {"id": f"v{i}", "contentDetails": {"duration": dur}, "snippet": {"title": f"t{i}", "publishedAt": (now - timedelta(days=days)).isoformat()}}
        if live:
            v["liveStreamingDetails"] = {"actualStartTime": (now - timedelta(days=days)).isoformat(), "actualEndTime": now.isoformat()}
        return v
    st = youtube.stream_stats([vid(1, "PT3H", 1), vid(2, "PT2H30M", 5), vid(3, "PT1H", 2), vid(4, "PT40S", 1, live=False),
                               vid(5, "PT4H", 30), vid(6, "PT10M", 1, live=False)], 14, 2.0)
    assert st["streams_14d"] == 2 and st["shorts_14d"] == 1
    assert st["vod_video_id"] == "v1" and st["vod_duration_s"] == 10800.0
    settings = {**db.DEFAULT_SETTINGS}
    row = {**st, "subscribers_or_viewers": 50000, "name": "n", "_description": "", "_titles": []}
    assert youtube.qualifies(row, {"min_size": 1, "max_size": 10 ** 6}, settings) is None
    assert youtube.qualifies({**row, "shorts_14d": 11}, {"min_size": 1, "max_size": 10 ** 6}, settings) == "already posts many Shorts"


# ── Finder ────────────────────────────────────────────────────────────────────

def fake_api(channels, videos_by_channel):
    def call(endpoint, settings, **p):
        bucket = "search" if endpoint == "search" else "units"
        if not youtube._budget_ok(bucket, 1, settings):
            raise youtube.QuotaExhausted("budget")
        db.add_quota(bucket, 1)
        if endpoint == "search":
            return {"items": [{"snippet": {"channelId": cid}} for cid in channels]}
        if endpoint == "channels":
            return {"items": [{"id": cid, "snippet": {"title": cid, "description": ch.get("desc", "")},
                               "statistics": {"subscriberCount": str(ch["subs"])},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid}}}
                              for cid, ch in channels.items()
                              if cid in p.get("id", "").split(",") or "@" + ch.get("handle", "-") == p.get("forHandle")]}
        if endpoint == "playlistItems":
            cid = p["playlistId"][2:]
            return {"items": [{"contentDetails": {"videoId": v["id"], "videoPublishedAt": ago(1)}} for v in videos_by_channel.get(cid, [])]}
        if endpoint == "videos":
            ids = p["id"].split(",")
            return {"items": [v for vs in videos_by_channel.values() for v in vs if v["id"] in ids]}
        raise AssertionError(endpoint)
    return call


def streams(prefix, n, hours=3):
    now = datetime.now(timezone.utc)
    return [{"id": f"{prefix}{i}", "contentDetails": {"duration": f"PT{hours}H"}, "snippet": {"title": "talk show", "publishedAt": ago(i + 1)},
             "liveStreamingDetails": {"actualStartTime": (now - timedelta(days=i + 1)).isoformat(), "actualEndTime": now.isoformat()}}
            for i in range(n)]


def test_finder_filters_scores_and_caps(env, monkeypatch):
    channels = {
        "UCgood": {"subs": 50000, "desc": "biz: good@creator.com"},
        "UCbig": {"subs": 2000000},
        "UCrare": {"subs": 40000},
        "UCslots": {"subs": 60000, "desc": "casino slots every night"},
        "UCgood2": {"subs": 20000},
        "UCknown": {"subs": 30000},
    }
    vids = {"UCgood": streams("g", 3), "UCbig": streams("b", 3), "UCrare": streams("r", 1), "UCslots": streams("s", 3),
            "UCgood2": streams("h", 4)}
    monkeypatch.setattr(youtube, "call", fake_api(channels, vids))
    monkeypatch.setattr(youtube, "score_fit", lambda rows: {r["channel_id"]: youtube.FitResult(
        channel_id=r["channel_id"], fit_score=90 if r["channel_id"] == "UCgood" else 70,
        language="id" if r["channel_id"] == "UCgood" else "pt", reason="loud") for r in rows})
    db.add_opt_out(None, "UCknown")
    db.add_search("podcast", "id", "ID", 10000, 300000)
    db.set_settings({"new_leads_per_day": 5})

    s = youtube.run_finder()
    assert s["candidates"] == 5  # opted-out channel skipped before any enrichment
    assert s["qualified"] == 2  # too big, too few streams, and gambling filtered
    assert s["added"] == 1  # UCgood2 speaks Portuguese, the search asked for Indonesian
    lead = db.list_leads(["found"])[0]
    assert lead["channel_id"] == "UCgood" and lead["email"] == "good@creator.com" and lead["email_source"] == "api"
    assert lead["streams_14d"] == 3 and lead["vod_video_id"] == "g0" and lead["search_id"] == 1
    assert db.quota_used("search") == 1 and db.quota_used("units") >= 3
    db.set_settings({"new_leads_per_day": 1})
    assert youtube.run_finder()["stopped"] == "daily lead cap reached"


def test_finder_stops_at_quota(env, monkeypatch):
    monkeypatch.setattr(youtube, "call", fake_api({}, {}))
    db.add_search("x", None, None, 0, 10)
    db.set_settings({"search_calls_per_day": 0})
    assert youtube.run_finder()["stopped"]


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def make_clip(video_id, status="ready", tmp=None):
    cand = spike_db.insert_candidate(video_id, {"start_s": 4000, "end_s": 4030, "title": "Rage quit", "hook_text": "he loses it",
                                                "punchline": "NO WAY", "final_score": 90, "status": "selected"})
    f = (tmp / f"clip{cand}.mp4")
    f.write_bytes(b"0" * 10)
    clip = spike_db.create_or_update_clip(cand, str(f), "", trim_start_s=4000, trim_end_s=4030, status=status)
    return clip


def configure_sending(monkeypatch):
    db.set_settings({"sender_name": "Nico", "proof_url": "https://youtube.com/@clips"})
    db.save_google_account("me@team.com", b"enc", " ".join(google.SCOPES), 1)


def test_lifecycle_to_sent(env, monkeypatch):
    a = add_lead(channel_id="UCa" + "a" * 21)
    b = add_lead(channel_id="UCb" + "b" * 21, email=None, email_source=None)
    c = add_lead(channel_id="UCc" + "c" * 21, vod_video_id="vid3", fit_score=60)
    # A channel that is already a Spike source with written permission must stay untouched
    spike_db.create_source({"kind": "youtube", "external_id": "UCc" + "c" * 21, "display_name": "C", "permission": "written"})

    r = service.approve([a, b, c])
    assert r == {"approved": 2, "needs_contact": 1, "opted_out": 0}
    assert service.queue_trial_clips() == 0  # no clip before a reply

    # needs_contact moves on once an email is added by hand
    assert service.save_contact(b, "Booking@Rafi.ID")["status"] == "approved"
    with pytest.raises(service.OutreachError):
        service.save_contact(b, "not-an-email")

    # The first email carries the offer, no clip
    db.set_settings({"proof_url": ""})
    assert service.draft_emails()["drafted"] == 0  # no website yet: waits, and the dashboard says why
    assert "website" in " ".join(service.sending_blockers(db.get_settings()))
    db.set_settings({"proof_url": "https://example.com/"})
    assert service.draft_emails()["drafted"] == 3
    msg = db.get_message(a, "first")
    assert db.get_lead(a)["status"] == "email_ready" and db.get_lead(a)["drive_file_id"] is None
    assert "$0.50 per 1.000 view" in msg["body"] and "10.000 view" in msg["body"] and "https://example.com/" in msg["body"]
    assert msg["subject"] == "Klip dari stream kamu, bayar hanya per view" and "{" not in msg["body"]

    # Sending is blocked until a Google account is connected
    with pytest.raises(service.OutreachError):
        service.queue_send([a])
    configure_sending(monkeypatch)
    service.save_draft(a, msg["to_email"], msg["subject"], msg["body"] + " {moment}")
    assert service.queue_send([a])["queued"] == 0  # an unfilled placeholder blocks sending
    service.save_draft(a, msg["to_email"], msg["subject"], msg["body"])
    assert service.queue_send([a, c])["queued"] == 2

    sent = []
    monkeypatch.setattr(google, "send_email", lambda *args, **kw: sent.append((args, kw)) or {"id": "m1", "thread_id": "t1", "rfc_message_id": "<x@y>"})
    with db.connect() as conn:  # both due now
        conn.execute("UPDATE messages SET scheduled_for = ?", (ago(hours=1),))
    assert service.send_due()["sent"] == 2
    assert db.get_lead(a)["status"] == "sent" and db.get_message(a, "first")["gmail_thread_id"] == "t1"
    assert sent[0][0][0] == "rafi@studio.id" and sent[0][1]["thread_id"] is None

    # A reply unlocks the sample clip
    assert service.request_clips([a, c]) == 0  # not replied yet
    db.update_lead(a, status="replied")
    db.update_lead(c, status="replied")
    assert service.request_clips([a, c]) == 2
    # trial_clips_per_day was removed: there is no daily cap, so every requested clip queues at once.
    assert service.queue_trial_clips() == 2 and service.queue_trial_clips() == 0  # nothing left to queue
    la = db.get_lead(a)
    assert la["status"] == "clip_queued"
    job = spike_db.get_job(la["spike_video_id"])
    assert job["priority"] == 0 and job["url"].endswith("vid1")
    assert json.loads(job["settings"]) == {"target_clips": 1, "max_process_s": 7200, "prospect": True}
    assert spike_db.get_source(la["spike_source_id"])["permission"] == "none"
    assert spike_db.get_source(db.get_lead(c)["spike_source_id"])["permission"] == "written"

    # Spike renders the clip; the reviewer approves it; it is shared for the Gmail reply
    clip = make_clip(la["spike_video_id"], tmp=env)
    spike_db.finish_video(la["spike_video_id"], "ready")
    service.sync_clips()
    assert db.get_lead(a)["status"] == "clip_ready" and db.get_lead(a)["spike_clip_id"] == clip
    spike_db.update_clip_status(clip, "approved")
    service.sync_clips()
    assert db.get_lead(a)["status"] == "clip_approved"
    uploads = []
    monkeypatch.setattr(google, "upload_shared_file", lambda path, name: uploads.append(name) or {"id": "f1", "url": "https://drive/f1"})
    assert service.share_clips() == 1 and service.share_clips() == 0
    assert db.get_lead(a)["drive_url"] == "https://drive/f1" and len(uploads) == 1
    assert service.mark([a], "trial") == 1


def test_per_streamer_terms_override_defaults_and_freeze_on_signing(env):
    db.set_settings({"proof_url": "https://example.com/"})
    a = add_lead(language="en", country="US")
    service.approve([a])
    service.draft_emails()
    assert "$1 per 1,000" in db.get_message(a, "first")["body"]  # defaults

    assert service.save_terms(a, "$2", "50.000", "$800") is True
    assert service.save_terms(a, "$2", "50000", "$800") is False  # unchanged
    with pytest.raises(service.OutreachError):
        service.save_terms(a, "", "lots", "")
    service.draft_emails(None, [a])
    body = db.get_message(a, "first")["body"]
    assert "$2 per 1,000" in body and "50,000 views" in body and "$800 monthly cap" in body

    service.save_terms(a, "", "", "$900")  # blank rate and views fall back to the defaults again
    db.update_lead(a, status="replied")
    service.mark([a], "client")
    db.set_settings({"monthly_cap": "$5", "rate_default": "$9"})  # a later default change leaves the deal alone
    lead = db.get_lead(a)
    assert service.terms(lead, db.get_settings()) == {"rate": "$1", "min_views": 10000, "cap": "$900"}


def test_terms_edit_from_ready_and_clients_tabs(env):
    from fastapi.testclient import TestClient
    from src.web.app import app
    db.set_settings({"proof_url": "https://example.com/"})
    a = add_lead()  # Indonesian: defaults to the Southeast Asia rate
    service.approve([a])
    service.draft_emails()
    client = TestClient(app)
    page = client.get("/outreach?tab=email").text
    assert f'name="rate_{a}"' in page and 'placeholder="$0.50"' in page and 'placeholder="10000"' in page

    form = {"action": "save_drafts", "tab": "email", f"to_{a}": "rafi@studio.id", f"subject_{a}": "s",
            f"body_{a}": "edited", f"rate_{a}": "$0.75", f"min_views_{a}": "", f"cap_{a}": ""}
    r = client.post("/outreach/leads/bulk", data=form, headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert "rewritten" in urllib_unquote(r.headers["location"])
    assert "$0.75 per 1.000 view" in db.get_message(a, "first")["body"]
    r = client.post("/outreach/leads/bulk", data={**form, f"body_{a}": "edited again"},  # same terms: edits kept
                    headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert db.get_message(a, "first")["body"] == "edited again"

    db.update_lead(a, status="client")
    assert 'value="$0.75"' in client.get("/outreach?tab=clients").text
    client.post(f"/outreach/leads/{a}/client", data={"model": "A", "rate": "", "min_views": "20000", "cap": "$1,000", "start": ""},
                headers={"Origin": "http://testserver"})
    lead = db.get_lead(a)
    assert (lead["client_rate"], lead["client_min_views"], lead["client_cap"]) == (None, 20000, "$1,000")


def test_draft_shows_placeholder_check(env):
    assert service.render_template("Hi {name}, {unknown} {name.__class__}", {"name": "Rafi"}) == "Hi Rafi, {unknown} {name.__class__}"


def test_send_respects_stagger_and_opt_out(env, monkeypatch):
    configure_sending(monkeypatch)
    ids = [add_lead(channel_id=f"UC{i:022d}", email=f"c{i}@x.io") for i in range(3)]
    for i in ids:
        db.update_lead(i, status="email_ready")
        db.upsert_draft(i, "first", db.get_lead(i)["email"], "Hello", "Body")
    db.set_settings({"send_gap_min": 5})  # emails_per_day removed: no daily cap
    assert service.queue_send(ids)["queued"] == 3
    times = sorted(db.get_message(i, "first")["scheduled_for"] for i in ids)
    assert datetime.fromisoformat(times[1]) - datetime.fromisoformat(times[0]) == timedelta(minutes=5)

    with db.connect() as conn:  # everything is due now
        conn.execute("UPDATE messages SET scheduled_for = ?", (ago(hours=1),))
    db.add_opt_out(db.get_lead(ids[0])["email"], None)
    monkeypatch.setattr(google, "send_email", lambda *a, **k: {"id": "m", "thread_id": "t", "rfc_message_id": ""})
    r = service.send_due()
    assert r["sent"] == 2 and r["held"] == 0  # opted-out one cancelled, no cap so the rest all send
    assert db.get_message(ids[0], "first")["status"] == "cancelled"
    assert sorted(db.get_message(i, "first")["status"] for i in ids[1:]) == ["sent", "sent"]

    # An auth failure keeps the message queued instead of failing it
    for i in ids[1:]:  # re-queue the two that just sent, so the auth-failure path has due mail
        db.update_message(db.get_message(i, "first")["id"], status="queued")
    with db.connect() as conn:
        conn.execute("UPDATE messages SET scheduled_for = ?", (ago(hours=1),))
    def boom(*a, **k):
        raise google.GoogleAuthError("revoked")
    monkeypatch.setattr(google, "send_email", boom)
    service.send_due()
    assert [db.get_message(i, "first")["status"] for i in ids[1:]].count("queued") >= 1


def test_followups_replies_bounces_and_opt_outs(env, monkeypatch):
    configure_sending(monkeypatch)
    ids = [add_lead(channel_id=f"UC{i:022d}", email=f"c{i}@x.io") for i in range(3)]
    for n, i in enumerate(ids):
        db.update_lead(i, status="sent", drive_url="https://drive/x")
        db.upsert_draft(i, "first", f"c{n}@x.io", "A clip", "Body")
        m = db.get_message(i, "first")
        db.update_message(m["id"], status="sent", sent_at=ago(5), gmail_thread_id=f"t{n}", rfc_message_id="<r@x>")

    assert service.schedule_followups() == 3
    f = db.get_message(ids[0], "followup_1")
    assert f["status"] == "queued" and f["subject"] == "Re: A clip" and "klip contoh gratis" in f["body"] and "{" not in f["body"]
    assert service.schedule_followups() == 0  # never twice

    replies = {
        "t0": [{"at_ms": 1, "from": "a", "snippet": "Out of office", "auto": True, "bounce": False}],
        "t1": [{"at_ms": 2, "from": "Mail Delivery <mailer-daemon@google.com>", "snippet": "not found", "auto": False, "bounce": True}],
        "t2": [{"at_ms": 3, "from": "c2", "snippet": "No thanks, please unsubscribe me", "auto": False, "bounce": False}],
    }
    monkeypatch.setattr(google, "thread_inbound", lambda tid: replies[tid])
    assert service.check_replies() == 2
    assert db.get_lead(ids[0])["status"] == "sent"  # auto-reply ignored
    assert db.get_lead(ids[1])["status"] == "bounced"
    assert db.get_lead(ids[2])["status"] == "opted_out" and db.is_opted_out("c2@x.io", None)
    assert db.get_message(ids[1], "followup_1")["status"] == "cancelled"

    replies["t0"].append({"at_ms": 9, "from": "c0", "snippet": "Sounds good, how do we start?", "auto": False, "bounce": False})
    monkeypatch.setattr(service, "classify_reply", lambda s: "positive")
    service.check_replies()
    lead = db.get_lead(ids[0])
    assert lead["status"] == "replied" and lead["reply_sentiment"] == "positive"
    assert service.mark([ids[0]], "client") == 1 and db.get_lead(ids[0])["client_start"]


def test_opt_out_regex():
    for s in ("no", "No.", "tidak", "please unsubscribe", "Not interested, thanks", "stop emailing me"):
        assert service.OPT_OUT_RE.search(s), s
    for s in ("no problem, let's do it", "No worries, send more", "sure"):
        assert not service.OPT_OUT_RE.search(s), s


def test_purge_and_retention(env, monkeypatch):
    stale = add_lead(channel_id="UC" + "s" * 22, api_fetched_at=ago(31), subscribers_or_viewers=5, email="old@x.io")
    manual = add_lead(channel_id="UC" + "m" * 22, api_fetched_at=ago(31), email="keep@x.io", email_source="manual", contacts_manual=1)
    fresh = add_lead(channel_id="UC" + "f" * 22)
    assert youtube.purge_stale() == 2
    s, m = db.get_lead(stale), db.get_lead(manual)
    assert s["name"] is None and s["email"] is None and s["subscribers_or_viewers"] is None and s["api_fetched_at"] is None
    assert m["email"] == "keep@x.io" and m["name"] is None
    assert db.get_lead(fresh)["name"] == "Rafi"

    deleted = []
    monkeypatch.setattr(google, "delete_file", lambda fid: deleted.append(fid))
    db.update_lead(fresh, status="sent", status_at=ago(200), drive_file_id="d1", drive_url="u", drive_uploaded_at=ago(31))
    db.upsert_draft(fresh, "first", "c@x.io", "s", "b")
    db.update_message(db.get_message(fresh, "first")["id"], status="sent", sent_at=ago(200))
    db.add_opt_out("gone@x.io", None)
    r = service.apply_retention()
    assert deleted == ["d1"] and r["leads_deleted"] == 1 and db.get_lead(fresh) is None
    assert db.is_opted_out("gone@x.io", None)


def test_refresh_drops_stats_after_approval(env, monkeypatch):
    lead = add_lead(channel_id="UCgood", streams_14d=3, shorts_14d=1)
    db.update_lead(lead, status="sent")
    monkeypatch.setattr(youtube, "call", fake_api({"UCgood": {"subs": 51000}}, {}))
    def videos(ids, settings):
        return {"vid1": {"vod_video_id": "vid1", "vod_title": "new", "vod_published_at": ago(3), "vod_duration_s": 9000.0}}
    monkeypatch.setattr(youtube, "fetch_vods", videos)
    youtube.refresh_leads()
    l = db.get_lead(lead)
    assert l["subscribers_or_viewers"] == 51000 and l["streams_14d"] is None and l["vod_title"] == "new"
    assert l["api_fetched_at"] > ago(0, 1)


# ── Pipeline cap (first 2 hours) ──────────────────────────────────────────────

def test_stage1_caps_duration(tmp_path, monkeypatch):
    from src.pipeline import stage1_meta
    monkeypatch.setattr(stage1_meta, "get_remote_video_meta", lambda url: {"duration": 13 * 3600.0, "title": "t"})
    meta = stage1_meta.run_stage1_meta(tmp_path, "https://www.youtube.com/watch?v=x", max_process_s=7200)
    assert meta["duration"] == 7200 and meta["process_limit_s"] == 7200 and meta["full_duration"] == 13 * 3600
    with pytest.raises(ValueError):  # without the cap, a 13 h stream is still rejected
        stage1_meta.run_stage1_meta(tmp_path / "other", "https://www.youtube.com/watch?v=x")


# ── Routes ────────────────────────────────────────────────────────────────────

def test_routes_render_and_block_cross_site_posts(env):
    from fastapi.testclient import TestClient
    from src.web.app import app
    add_lead()
    client = TestClient(app)
    for tab in ("review", "contact", "progress", "email", "sent", "replies", "clients", "stats", "settings"):
        r = client.get(f"/outreach?tab={tab}")
        assert r.status_code == 200, tab
        assert chr(0x2014) not in r.text  # no em dashes in UI copy
    assert "Rafi" in client.get("/outreach?tab=review").text
    r = client.post("/outreach/leads/bulk", data={"action": "approve", "ids": "1", "tab": "review"},
                    headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/outreach/leads/bulk", data={"action": "approve", "ids": "1", "tab": "review"},
                    headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303 and db.get_lead(1)["status"] == "approved"


# ── Seen cache and rate limiter ───────────────────────────────────────────────

def test_dropped_channels_are_skipped_for_30_days(env, monkeypatch):
    channels = {"UCbig": {"subs": 5_000_000}, "UCfew": {"subs": 40000}, "UCok": {"subs": 50000}}
    calls = []
    api = fake_api(channels, {"UCfew": streams("f", 1), "UCok": streams("o", 3)})
    monkeypatch.setattr(youtube, "call", lambda ep, st, **p: calls.append(ep) or api(ep, st, **p))
    monkeypatch.setattr(youtube, "score_fit", lambda rows: {})
    db.add_search("podcast", None, None, 10000, 300000)
    db.set_settings({"new_leads_per_day": 10})

    first = youtube.run_finder()
    assert first["added"] == 1 and first["skipped_seen"] == 0
    with db.connect() as conn:
        seen = dict(conn.execute("SELECT channel_id, reason FROM seen").fetchall())
    assert seen == {"UCbig": "size out of range or hidden", "UCfew": "too few long streams"}

    calls.clear()
    second = youtube.run_finder()
    assert second["candidates"] == 0 and second["skipped_seen"] == 3  # 2 dropped + 1 lead
    assert calls == ["search"]  # no channels/videos quota spent on known channels

    with db.connect() as conn:
        conn.execute("UPDATE seen SET checked_at = ?", (ago(31),))
    assert db.purge_seen() == 2
    assert "UCbig" not in db.known_channel_ids("youtube")


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def monotonic(self):
        return self.t

    def time(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def test_rate_limiter_spaces_and_obeys_headers(monkeypatch):
    from src.outreach import net
    clock = FakeClock()
    monkeypatch.setattr(net, "time", clock)
    lim = net.RateLimiter(per_minute=60)
    lim.wait(); lim.wait(); lim.wait()
    assert clock.slept == [1.0, 1.0]  # evenly spaced, no jitter
    lim.observe({"Ratelimit-Remaining": "0", "Ratelimit-Reset": str(clock.t + 30)})
    lim.wait()
    assert clock.slept[-1] == 31.0  # waits out the window (+1 s margin)
    lim.observe({"Ratelimit-Remaining": "0", "Ratelimit-Reset": str(clock.t + 9999)})
    lim.wait()
    assert clock.slept[-1] == net.MAX_WAIT_S  # never trusts an absurd reset
    lim.observe({"Ratelimit-Remaining": "nan?"})  # malformed header ignored


def test_get_json_retries_429_and_charges_each_attempt(monkeypatch):
    import io, urllib.error
    from email.message import Message
    from src.outreach import net
    clock = FakeClock()
    monkeypatch.setattr(net, "time", clock)
    hdrs = Message(); hdrs["Retry-After"] = "7"
    replies = [urllib.error.HTTPError("u", 429, "slow down", hdrs, io.BytesIO(b"{}"))]

    class Ok(io.BytesIO):
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def urlopen(req, timeout):
        if replies:
            raise replies.pop(0)
        return Ok(b'{"items": [1]}')
    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    attempts = []
    out = net.get_json("https://api/x", net.RateLimiter(60), on_attempt=lambda: attempts.append(1))
    assert out == {"items": [1]} and len(attempts) == 2 and 7.0 in clock.slept

    replies.append(urllib.error.HTTPError("u", 400, "bad", Message(), io.BytesIO(b"bad request")))
    with pytest.raises(net.HttpError) as e:
        net.get_json("https://api/x", net.RateLimiter(60))
    assert e.value.status == 400  # not retried


def test_youtube_call_maps_quota_errors(env, monkeypatch):
    import io, urllib.error
    from email.message import Message
    from src.outreach import net
    monkeypatch.setattr(net, "time", FakeClock())
    body = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
    monkeypatch.setattr(net.urllib.request, "urlopen",
                        lambda req, timeout: (_ for _ in ()).throw(urllib.error.HTTPError("u", 403, "q", Message(), io.BytesIO(body))))
    with pytest.raises(youtube.QuotaExhausted):
        youtube.call("channels", db.get_settings(), id="UCx")
    assert not youtube._budget_ok("units", 1, db.get_settings())  # Google said it is out, so the key counts as full


def test_second_key_takes_over_and_fan_shorts_counts_other_channels(env, monkeypatch):
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "k1, k2")
    settings = {**db.DEFAULT_SETTINGS, "search_calls_per_day": 1}
    used = []
    def get_json(url, limiter, on_attempt=None):
        on_attempt()
        used.append(url.split("key=")[1].split("&")[0])
        return {"items": [{"snippet": {"channelTitle": "Rafi", "title": "Rafi own short"}},
                          {"snippet": {"channelTitle": "Clips", "title": "Rafi rage moment", "description": ""}},
                          {"snippet": {"channelTitle": "Other", "title": "Rafiq is unrelated"}}]}
    monkeypatch.setattr(youtube.net, "get_json", get_json)
    lead = {"name": "Rafi", "handle": "@rafilive"}
    assert youtube.fan_shorts(lead, settings) == (1, 3) and youtube.fan_shorts(lead, settings) == (1, 3)
    assert used == ["k1", "k2"]  # the first key's one search is spent, so the second answers
    with pytest.raises(youtube.QuotaExhausted):
        for _ in range(200):
            youtube.fan_shorts(lead, settings)


# ── Add lead by hand ──────────────────────────────────────────────────────────

def test_parse_lead_url():
    p = service.parse_lead_url
    assert p("https://www.youtube.com/@Rafi.Games") == {"platform": "youtube", "kind": "handle", "value": "Rafi.Games"}
    assert p("youtube.com/channel/UC" + "a" * 22)["kind"] == "id"
    assert p("https://youtu.be/abc123")["kind"] == "video"
    assert p("https://www.youtube.com/watch?v=abc&t=5")["value"] == "abc"
    assert p("https://www.youtube.com/live/xyz")["value"] == "xyz"
    assert p("https://www.youtube.com/user/oldname")["kind"] == "username"
    assert p("https://www.twitch.tv/Rafi_GG") == {"platform": "twitch", "kind": "login", "value": "rafi_gg"}
    assert p("https://www.twitch.tv/videos/2233445566") == {"platform": "twitch", "kind": "vod", "value": "2233445566"}
    assert p("https://kick.com/rafi/videos/9f1c-22") == {"platform": "kick", "kind": "vod", "value": "9f1c-22", "slug": "rafi"}
    assert p("https://kick.com/rafi")["kind"] == "slug"
    for bad in ("", "https://www.twitch.tv/directory", "https://example.com/rafi", "https://www.youtube.com/"):
        assert p(bad) is None, bad


def test_add_youtube_lead_by_hand(env, monkeypatch):
    talk = streams("t", 2)
    pod = [{"id": "p1", "contentDetails": {"duration": "PT1H10M"}, "snippet": {"title": "Episode 12", "publishedAt": ago(3)}}]
    api = fake_api({"UCrafi": {"subs": 2_000_000, "handle": "rafi", "desc": "biz: rafi@studio.id"},
                    "UCpod": {"subs": 900, "handle": "pod"}}, {"UCrafi": talk, "UCpod": pod})
    monkeypatch.setattr(youtube, "call", api)
    db.mark_seen("youtube", {"UCrafi": "size out of range or hidden"})

    lead = service.add_lead("https://www.youtube.com/@rafi", notes="Whop campaign", whop=True)
    assert lead["status"] == "approved" and lead["email"] == "rafi@studio.id" and lead["email_source"] == "api"
    assert lead["vod_video_id"] == "t0" and lead["whop_flag"] == 1 and lead["notes"] == "Whop campaign"
    assert lead["subscribers_or_viewers"] == 2_000_000  # no size filter for hand-added leads
    assert "UCrafi" not in db.known_channel_ids("youtube") - {l["channel_id"] for l in db.list_leads(db.STATUSES)}
    with pytest.raises(service.OutreachError, match="already a lead"):
        service.add_lead("https://www.youtube.com/@rafi")

    # A podcast with no live streams falls back to its newest long upload; a chosen stream is pinned
    pod_lead = service.add_lead("https://www.youtube.com/@pod", email="Host@Pod.fm", language="id")
    assert pod_lead["vod_video_id"] == "p1" and pod_lead["email"] == "host@pod.fm" and pod_lead["contacts_manual"] == 1
    assert pod_lead["language"] == "id" and pod_lead["status"] == "approved"

    db.delete_lead(lead["id"])
    pinned = service.add_lead("https://www.youtube.com/@rafi", stream_url="https://youtu.be/t1")
    assert pinned["vod_video_id"] == "t1" and pinned["vod_manual"] == 1
    youtube.refresh_leads()  # the nightly refresh must not swap a stream a person chose
    assert db.get_lead(pinned["id"])["vod_video_id"] == "t1"

    db.add_opt_out(None, "UCpod")
    db.delete_lead(pod_lead["id"])
    with pytest.raises(service.OutreachError, match="opted out"):
        service.add_lead("https://www.youtube.com/@pod")
    monkeypatch.setattr(youtube, "call", fake_api({"UCquiet": {"subs": 5000, "handle": "quiet"}}, {}))
    with pytest.raises(service.OutreachError, match="Paste a stream link"):
        service.add_lead("https://www.youtube.com/@quiet")
    with pytest.raises(service.OutreachError, match="YouTube video"):
        service.add_lead("https://www.youtube.com/@rafi", stream_url="https://www.twitch.tv/videos/1")


def test_add_twitch_and_kick_leads_by_hand(env, monkeypatch):
    def meta(url):
        return {"vod_video_id": url.rsplit("/", 1)[-1], "vod_url": url, "vod_title": "Late night", "vod_duration_s": 9000.0,
                "vod_published_at": ago(1), "_channel": "rafi_gg", "_live": False}
    monkeypatch.setattr(service, "_vod_meta", meta)
    monkeypatch.setattr(service, "_latest_twitch_vod", lambda login: meta("https://www.twitch.tv/videos/555"))

    tw = service.add_lead("https://www.twitch.tv/Rafi_GG", email="r@gg.io")
    assert tw["channel_id"] == "twitch:rafi_gg" and tw["platform"] == "twitch" and tw["vod_url"].endswith("/555")
    assert tw["status"] == "approved" and tw["api_fetched_at"] is None  # no API data to purge
    with pytest.raises(service.OutreachError, match="already a lead"):
        service.add_lead("https://www.twitch.tv/videos/777")  # a VOD link resolves to the same channel

    with pytest.raises(service.OutreachError, match="Kick channels need a stream link"):
        service.add_lead("https://kick.com/rafi")
    kick = service.add_lead("https://kick.com/rafi", stream_url="https://kick.com/rafi/videos/abc-1")
    assert kick["channel_id"] == "kick:rafi" and kick["status"] == "needs_contact"
    assert kick["vod_url"] == "https://kick.com/rafi/videos/abc-1"

    # The sample clip uses the platform's own VOD URL and a Spike source of the same kind
    db.update_lead(tw["id"], status="replied")
    assert service.request_clips([tw["id"]]) == 1 and service.queue_trial_clips() == 1
    t = db.get_lead(tw["id"])
    job, src = spike_db.get_job(t["spike_video_id"]), spike_db.get_source(t["spike_source_id"])
    assert job["url"] == "https://www.twitch.tv/videos/555" and job["external_id"] == "555"
    assert (src["kind"], src["external_id"], src["permission"]) == ("twitch", "rafi_gg", "none")


def test_add_lead_route_keeps_input_on_error(env):
    from fastapi.testclient import TestClient
    from src.web.app import app
    r = TestClient(app).post("/outreach/leads/add", data={"url": "https://example.com/x", "email": "a@b.co", "tab": "review"},
                             headers={"Origin": "http://testserver"})
    assert r.status_code == 400 and "data-open-on-load" in r.text and 'value="a@b.co"' in r.text
    assert "Paste a YouTube, Twitch, or Kick channel link" in r.text


# ── Re-upload pass (Twitch/Kick streamers on YouTube) ─────────────────────────

def uploads(prefix, n, hours=3):
    return [{"id": f"{prefix}{i}", "contentDetails": {"duration": f"PT{hours}H"},
             "snippet": {"title": f"FULL STREAM {i}", "publishedAt": ago(i + 1)}} for i in range(n)]


def test_reuploads_count_as_streams_only_when_asked():
    vids = uploads("u", 3)
    assert youtube.stream_stats(vids, 14, 2.0)["streams_14d"] == 0
    st = youtube.stream_stats(vids, 14, 2.0, reuploads=True)
    assert st["streams_14d"] == 3 and st["vod_video_id"] == "u0" and st["avg_stream_h"] == 3.0


def test_reupload_search_finds_twitch_streamers_once(env, monkeypatch):
    channels = {
        "UCvods": {"subs": 30000, "desc": "VODs of my streams. LIVE at https://twitch.tv/RafiLive/ biz: rafi@studio.id"},
        "UCfan": {"subs": 40000, "desc": "Fan channel, all credit to twitch.tv/rafilive"},
        "UCpod": {"subs": 50000, "desc": "A podcast with no stream link"},
        "UCkick": {"subs": 20000, "desc": "kick.com/budi-id"},
    }
    vids = {cid: uploads(cid, 3) for cid in channels}
    api = fake_api(channels, vids)
    searches = []
    monkeypatch.setattr(youtube, "call", lambda ep, st, **p: (searches.append(p) if ep == "search" else None) or api(ep, st, **p))
    monkeypatch.setattr(youtube, "score_fit", lambda rows: {r["channel_id"]: youtube.FitResult(
        channel_id=r["channel_id"], fit_score={"UCvods": 90, "UCfan": 60, "UCkick": 80}[r["channel_id"]],
        language="en", reason="r") for r in rows})
    db.add_search("twitch vod", None, None, 10000, 300000, kind="reupload")
    db.set_settings({"new_leads_per_day": 10})
    # A hand-added Kick lead for the same person as UCkick
    db.insert_lead({"channel_id": "kick:budi-id", "platform": "kick", "name": "budi", "status": "needs_contact"})

    s = youtube.run_finder()
    assert "eventType" not in searches[0] or searches[0]["eventType"] is None
    assert s["qualified"] == 3 and s["added"] == 1  # podcast has no link; fan channel and Kick twin are duplicates
    lead = db.get_lead_by_channel("UCvods")
    assert lead["twitch"] == "rafilive" and lead["stream_source"] == "reupload" and lead["streams_14d"] == 3
    with db.connect() as conn:
        seen = dict(conn.execute("SELECT channel_id, reason FROM seen").fetchall())
    assert seen["UCpod"] == "re-uploads without a Twitch or Kick link"
    assert seen["UCfan"].startswith("same streamer as lead #") and seen["UCkick"].startswith("same streamer as lead #")

    # Hand-adding the same streamer on Twitch is refused; an opt-out on YouTube covers Twitch too
    with pytest.raises(service.OutreachError, match="already a lead"):
        service.add_lead("https://www.twitch.tv/RafiLive")
    service.opt_out([lead["id"]])
    assert db.is_opted_out(None, "twitch:rafilive") and db.is_opted_out("rafi@studio.id", None)


def test_live_search_still_uses_event_type(env, monkeypatch):
    seen_params = []
    monkeypatch.setattr(youtube, "call", lambda ep, st, **p: seen_params.append(p) or {"items": []})
    youtube.search_channels({"query": "q", "kind": "live"}, db.get_settings())
    youtube.search_channels({"query": "q", "kind": "reupload"}, db.get_settings())
    assert seen_params[0]["eventType"] == "completed" and seen_params[1]["eventType"] is None


def test_old_outreach_db_gets_new_columns(tmp_path, monkeypatch):
    import sqlite3
    old = tmp_path / "old.db"
    added = ("vod_url ", "vod_manual ", "twitch ", "kick ", "stream_source ", "kind TEXT NOT NULL DEFAULT 'live'", "vod_views ", "min_views ", "max_views ")
    first_release = chr(10).join(l for l in db._SCHEMA.splitlines() if not l.strip().startswith(added))
    with sqlite3.connect(old) as conn:  # the schema as first released, before these columns existed
        conn.executescript(first_release)
        assert "twitch" not in {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
    monkeypatch.setattr(config, "OUTREACH_DB_PATH", old)
    monkeypatch.setattr(db, "_initialized_path", None)
    with db.connect() as conn:
        lead_cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
        search_cols = {r[1] for r in conn.execute("PRAGMA table_info(searches)")}
    assert {"twitch", "kick", "stream_source", "vod_url", "vod_manual", "vod_views"} <= lead_cols
    assert {"kind", "min_views", "max_views"} <= search_cols



# ── Views per stream (size measure) ───────────────────────────────────────────

def test_views_per_stream_is_a_settled_median():
    now = datetime.now(timezone.utc)
    def live(i, days, views):
        return {"id": f"s{i}", "contentDetails": {"duration": "PT3H"}, "snippet": {"title": "t", "publishedAt": (now - timedelta(days=days)).isoformat()},
                "liveStreamingDetails": {"actualStartTime": (now - timedelta(days=days)).isoformat(), "actualEndTime": now.isoformat()},
                "statistics": {"viewCount": str(views)}}
    # 3 settled streams (2k, 3k, one viral 900k) and one from 3 hours ago with 40 views
    vids = [live(1, 2, 2000), live(2, 4, 3000), live(3, 6, 900000), live(4, 0.12, 40)]
    assert youtube.stream_stats(vids, 14, 2.0)["vod_views"] == 3000
    assert youtube.stream_stats([live(5, 0.1, 40)], 14, 2.0)["vod_views"] == 40  # only fresh ones: use them
    assert youtube.stream_stats(uploads("u", 2), 14, 2.0, reuploads=True)["vod_views"] is None  # no statistics part

    settings = {**db.DEFAULT_SETTINGS}
    row = {**youtube.stream_stats(vids, 14, 2.0), "subscribers_or_viewers": 50000, "name": "n", "_description": "", "_titles": []}
    search = {"min_size": 0, "max_size": 10 ** 6, "min_views": 1000, "max_views": 100000}
    assert youtube.qualifies(row, search, settings) is None
    assert youtube.qualifies({**row, "vod_views": 500}, search, settings) == "too few views per stream"
    assert youtube.qualifies({**row, "vod_views": 250000}, search, settings) == "too many views per stream"
    assert youtube.qualifies({**row, "vod_views": None}, search, settings) is None  # no data: not judged on it


def test_saved_search_keeps_view_range(env):
    from fastapi.testclient import TestClient
    from src.web.app import app
    r = TestClient(app).post("/outreach/searches", data={
        "query": "valorant twitch vod", "kind": "reupload", "min_size": "0", "max_size": "300000",
        "min_views": "100", "max_views": "20000"}, headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303
    s = db.list_searches()[0]
    assert (s["kind"], s["min_size"], s["min_views"], s["max_views"]) == ("reupload", 0, 100, 20000)


# ── Twitch finder (separate app, 24-hour data) ────────────────────────────────

@pytest.fixture
def tw(env, monkeypatch):
    from src.outreach import twitch
    monkeypatch.setattr(config, "TWITCH_CLIENT_ID", "spike-app")
    monkeypatch.setattr(config, "TWITCH_CLIENT_SECRET", "s")
    return twitch


def test_twitch_finder_needs_spike_twitch_credentials(env, monkeypatch):
    from src.outreach import twitch
    monkeypatch.setattr(config, "TWITCH_CLIENT_ID", "")
    assert "TWITCH_CLIENT_ID" in twitch.credentials_problem()
    with pytest.raises(twitch.TwitchError):
        twitch.helix("streams", [])
    assert twitch.run_finder()["stopped"].startswith("Set TWITCH_CLIENT_ID")
    monkeypatch.setattr(config, "TWITCH_CLIENT_ID", "spike-app")
    monkeypatch.setattr(config, "TWITCH_CLIENT_SECRET", "s")
    assert twitch.credentials_problem() is None
    assert twitch.parse_duration("3h2m10s") == 10930 and twitch.parse_duration("3m21s") == 201
    assert twitch.parse_duration("") == 0


def test_twitch_sampling_pages_until_below_range(tw, monkeypatch):
    sid = db.add_twitch_search("509658", "Just Chatting", "id", 50, 1000)

    def page(ids, views, cursor):
        return {"data": [{"user_id": str(i), "user_login": f"U{i}", "viewer_count": v, "language": "id",
                          "game_name": "Just Chatting", "title": f"t{i}"} for i, v in zip(ids, views)],
                "pagination": {"cursor": cursor}}
    pages = [page(range(4), [5000, 3000, 900, 600], "c1"), page(range(4, 8), [400, 120, 30, 10], "c2"),
             AssertionError("paged past the range")]
    calls = []

    def helix(ep, params):
        calls.append(dict(params))
        nxt = pages.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt
    monkeypatch.setattr(tw, "helix", helix)
    assert tw.sample_live() == {"searches": 1, "pages": 2, "samples": 5}  # 900..30 kept: half to twice 50-1000
    assert calls[0]["game_id"] == "509658" and calls[0]["language"] == "id" and calls[1]["after"] == "c1"
    assert db.list_twitch_searches()[0]["last_sampled_at"]

    # A second sample an hour earlier: the average is per distinct sample time, logins are lowercased
    db.add_twitch_samples(sid, [{"user_id": "2", "user_login": "U2", "viewer_count": 700, "title": "t2"}], ago(hours=1))
    summary = {r["login"]: r for r in db.twitch_sample_summary()}
    assert summary["u2"]["avg_viewers"] == 800 and summary["u2"]["samples"] == 2
    with db.connect() as conn:
        conn.execute("UPDATE twitch_samples SET sampled_at = ?", (ago(hours=25),))
    assert db.purge_twitch_samples() == 6 and db.twitch_sample_summary() == []


def test_twitch_finder_makes_leads_from_samples(tw, monkeypatch):
    sid = db.add_twitch_search(None, None, "id", 50, 1000)
    now = db.now_iso()

    def sample(uid, login, viewers, category="Just Chatting"):
        db.add_twitch_samples(sid, [{"user_id": uid, "user_login": login, "viewer_count": viewers, "language": "id",
                                     "game_name": category, "title": "ngobrol santai"}], now)
    sample("1", "rafi", 300)
    sample("2", "tiny", 20)
    sample("3", "dupe", 400)
    sample("4", "slotter", 500, "Slots & Casino")
    sample("5", "rare", 200)
    # dupe is already a lead: a YouTube channel that links twitch.tv/dupe
    db.insert_lead({"channel_id": "UCdupe", "name": "Dupe VODs", "twitch": "dupe", "status": "found"})

    users = {l: {"id": str(i), "login": l, "display_name": l.title(), "description": f"biz {l}@mail.id",
                 "profile_image_url": "p.png"} for i, l in enumerate(["rafi", "dupe", "slotter", "rare"], 1)}
    now_dt = datetime.now(timezone.utc)

    def archives(n):
        return [{"id": f"9{i}", "type": "archive", "created_at": (now_dt - timedelta(days=i + 2)).isoformat(),
                 "duration": "3h0m0s", "view_count": 1000 * (i + 1), "title": f"stream {i}",
                 "url": f"https://www.twitch.tv/videos/9{i}"} for i in range(n)]

    def helix(ep, params):
        if ep == "users":
            return {"data": [users[v] for k, v in params if k == "login" and v in users]}
        if ep == "videos":
            return {"data": archives(1 if dict(params)["user_id"] == users["rare"]["id"] else 3)}
        raise AssertionError(ep)
    monkeypatch.setattr(tw, "helix", helix)
    monkeypatch.setattr(youtube, "score_fit", lambda rows: {r["channel_id"]: youtube.FitResult(
        channel_id=r["channel_id"], fit_score=80, language="id", reason="chatty") for r in rows})

    s = tw.run_finder()
    assert (s["sampled_channels"], s["candidates"], s["qualified"], s["added"]) == (5, 4, 2, 1)
    lead = db.get_lead_by_channel("twitch:rafi")
    assert lead["platform"] == "twitch" and lead["subscribers_or_viewers"] == 300 and lead["language"] == "id"
    assert lead["email"] == "rafi@mail.id" and lead["email_source"] == "api" and lead["twitch"] == "rafi"
    assert lead["vod_url"] == "https://www.twitch.tv/videos/90" and lead["streams_14d"] == 3 and lead["vod_views"] == 2000
    assert lead["twitch_search_id"] == sid and lead["api_fetched_at"]
    with db.connect() as conn:
        seen = dict(conn.execute("SELECT channel_id, reason FROM seen WHERE platform = 'twitch'").fetchall())
    assert seen["twitch:slotter"] == "gambling" and seen["twitch:rare"] == "too few long streams"
    assert seen["twitch:dupe"].startswith("same streamer as lead #")
    assert "twitch:tiny" not in seen  # out of range is not remembered: its average can still move

    # Twitch data lives 24 hours; YouTube data 30 days. The clipped stream's date survives as our own record.
    db.update_lead(lead["id"], status="sent", clip_stream_at=lead["vod_published_at"], api_fetched_at=ago(hours=25))
    yt = add_lead(channel_id="UC" + "y" * 22, api_fetched_at=ago(hours=25))
    assert youtube.purge_stale() == 1
    gone = db.get_lead(lead["id"])
    assert gone["name"] is None and gone["subscribers_or_viewers"] is None and gone["vod_published_at"] is None
    assert gone["clip_stream_at"] and db.get_lead(yt)["name"] == "Rafi"
    stream_day = datetime.fromisoformat(gone["clip_stream_at"]).astimezone().weekday()
    assert service.template_values(gone, db.get_settings())["day"] == service.ID_DAYS[stream_day]


def test_twitch_sample_schedule_runs_once_per_listed_hour(tw, monkeypatch):
    from src.outreach import daemon
    calls = []
    monkeypatch.setattr(tw, "sample_live", lambda settings=None: calls.append(1) or {"searches": 0})
    hour = datetime.now().hour
    db.set_settings({"twitch_sample_hours": str(hour)})
    daemon.sample_twitch(db.get_settings())
    daemon.sample_twitch(db.get_settings())  # same hour: no second sample
    assert len(calls) == 1
    db.set_settings({"twitch_sample_hours": str((hour + 1) % 24)})
    daemon.sample_twitch(db.get_settings())
    daemon.sample_twitch(db.get_settings(), force=True)  # what Run finder now does first
    assert len(calls) == 2
    monkeypatch.setattr(config, "TWITCH_CLIENT_SECRET", "")  # no Twitch app: no sampling
    daemon.sample_twitch(db.get_settings(), force=True)
    assert len(calls) == 2


def test_twitch_routes(tw, monkeypatch):
    from fastapi.testclient import TestClient
    from src.web.app import app
    client = TestClient(app)
    h = {"Origin": "http://testserver"}
    monkeypatch.setattr(tw, "find_category",
                        lambda name: {"id": "509658", "name": "Just Chatting"} if name.lower() == "just chatting" else None)
    r = client.post("/outreach/twitch/searches", data={"category": "Just chatting", "language": "id"}, headers=h,
                    follow_redirects=False)
    assert r.status_code == 303 and db.list_twitch_searches()[0]["game_name"] == "Just Chatting"
    r = client.post("/outreach/twitch/searches", data={"category": "Nope"}, headers=h, follow_redirects=False)
    assert "No+Twitch+category" in r.headers["location"]
    page = client.get("/outreach?tab=settings").text
    assert "Just Chatting" in page and 'name="twitch_sample_hours" value="22" checked' in page
    assert '<select class="select" id="s-region"' in page and 'value="ID">Indonesia' in page
    client.post("/outreach/settings", data={"form": "twitch", "twitch_sample_hours": "22, 7,9"},
                headers=h, follow_redirects=False)
    assert db.get_settings()["twitch_sample_hours"] == "7,9,22"
    client.post("/outreach/settings", content="form=twitch&twitch_sample_hours=20&twitch_sample_hours=8",
                headers={**h, "content-type": "application/x-www-form-urlencoded"}, follow_redirects=False)
    assert db.get_settings()["twitch_sample_hours"] == "8,20"  # one value per ticked hour chip


def test_finder_records_done_and_failed(env, monkeypatch):
    from src.outreach import daemon
    db.set_settings({"run_now": 1})
    daemon.run_finders(db.get_settings())
    s = db.get_settings()
    assert s["finder_status"] == "done" and s["run_now"] == 0 and s["finder_finished_at"]
    def boom(settings):
        raise RuntimeError("quota API down")
    monkeypatch.setattr(youtube, "run_finder", boom)
    daemon.run_finders(db.get_settings())
    s = db.get_settings()
    assert s["finder_status"] == "failed" and "quota API down" in s["finder_error"]
