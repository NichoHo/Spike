# Label Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every approve, reject (with reasons) and admired short as a durable label, and show a few of them to the transcript judge as examples.

**Architecture:** A `labels` table with no foreign keys (`src/db.py`) and one module, `src/labels.py`, that writes verdict and gold labels and builds the judge's examples block. The routes call it; stage 7 passes its block into `call_llm_judge`.

**Tech Stack:** Python 3.14, SQLite, FastAPI + Jinja2, yt-dlp, google-genai, pytest.

**Spec:** `docs/superpowers/specs/2026-11-07-label-store-design.md`

## Global Constraints

- Labels have no foreign keys. One verdict per clip (`clip_id` unique); a later verdict replaces it.
- `record_verdict` and `analyze_gold` never raise: a review or a background task must not fail because of a label.
- Form input is untrusted: reject tags filtered to `REJECT_TAGS`; gold links only from `youtube.com`, `youtu.be`, `tiktok.com`, `instagram.com` over http(s); uploads `.mp4 .mov .mkv .webm`, at most 200 MB.
- Example text goes inside `<untrusted_examples>` tags with a raw-DATA note.
- Gold intake keeps text only; the video file is deleted.
- Tests never call the real Gemini API, yt-dlp or Claude CLI.
- UI copy: no em or en dashes; reuse `chip--toggle`, `chip-field`, `card`, `field` classes.
- Test command: `py -m pytest -q` (355 passed before this plan).
- Commits as the user, no co-author lines; push to `main` at the end.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/db.py` | Modify | `labels` table; `save_label`, `update_label`, `get_label`, `list_labels`, `delete_label` |
| `src/labels.py` | Create | Reject tags, verdict snapshots, gold intake, examples block |
| `src/web/routes/clips.py`, `src/web/routes/posts.py` | Modify | Reject with tags; both approve paths save a label |
| `src/web/app.py`, `src/web/templates/pages/clip_detail.html` | Modify | Reason chips in the Reject dialog |
| `src/web/routes/settings.py`, `src/web/templates/pages/settings.html` | Modify | Standards card: add a gold short, list, delete |
| `src/pipeline/stage7_moments.py` | Modify | Examples block into every judge call |
| `tests/test_labels.py` | Create | All label tests |

---

### Task 1: The labels table and verdict snapshots

**Files:** `src/db.py`, `src/labels.py` (create), `tests/test_labels.py` (create)

**Interfaces produced:**
- `db.save_label(fields: Dict[str, Any]) -> int`, `db.update_label(label_id: int, **fields)`, `db.get_label(label_id) -> Row | None`, `db.list_labels(kind: str, channel: str | None = None, status: str | None = None, limit: int = 200) -> List[Row]` (newest first), `db.delete_label(label_id)`
- `labels.REJECT_TAGS: Dict[str, str]`, `labels.record_verdict(clip_id: int, verdict: str, tags: Sequence[str] = (), note: str = "") -> None`, `labels.examples_block(channel: str, category: Optional[str]) -> str`

- [ ] **Step 1: Write the failing tests** in `tests/test_labels.py`: a clip made from `register_video` + `insert_candidate` + `create_or_update_clip`, with `meta.json` and `transcript.json` in a temp video dir (`labels.VIDEOS_DIR` patched). Cases:
  - `record_verdict(clip, "rejected", ["needs_context", "routine"], "slow start")` stores one row with both tags, the clip's transcript text only, the channel key, the creator type and the scores.
  - `record_verdict` again with `"approved"` on the same clip leaves one row, now `approved`.
  - `DELETE FROM videos` keeps the label.
  - An unknown uploader stores `channel = ""`.
  - `examples_block`: with 4 ready gold (2 in the category, 1 `any`, 1 other category, 1 still `processing`) it shows the 2 same-category ones first, then the `any` one, and never the others; it shows only this channel's 2 newest approved and 2 newest rejected (with tag names); it is `""` with no labels; the block is wrapped in `<untrusted_examples>`.
- [ ] **Step 2:** `py -m pytest tests/test_labels.py -q` → fails (`No module named 'src.labels'`).
- [ ] **Step 3:** Add the table to `init_db`'s `executescript` and the five functions to `src/db.py`; create `src/labels.py` with `REJECT_TAGS`, `_clip_text`, `record_verdict`, `_cut`, `examples_block` (code as written in the repo at this commit).
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit "Add the label store: a labels table that outlives clips, verdict snapshots and the judge's examples block".

### Task 2: Reject reasons and approve labels

**Files:** `src/web/routes/clips.py`, `src/web/routes/posts.py`, `src/web/app.py`, `src/web/templates/pages/clip_detail.html`, `tests/test_labels.py`

- [ ] **Step 1: Failing tests:** `POST /clips/{id}/reject` with `tags=needs_context&tags=bogus&note=late` → one `rejected` label with `["needs_context"]` and note `late`; `clips.reject_reason` is `"Needs context; late"`. `POST /clips/{id}/approve` → one `approved` label. The clip page shows the chip `Needs context`.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Reject route takes `tags: List[str] = Form([])`, `note: str = Form("")` (and the old `reason` as a fallback note), filters tags, calls `record_verdict` before the files are deleted, stores `"; ".join(tag names + note)`. Approve route and the approve branch in `posts.py` call `record_verdict(clip_id, "approved")`. `app.py` adds `templates.env.globals["reject_tags"] = REJECT_TAGS`. The dialog gets a `chip-field` fieldset of `chip chip--toggle` checkboxes and an optional note textarea.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit "Ask why on Reject with one-tap reasons, and save every approve and reject as a label".

### Task 3: Gold shorts on Settings

**Files:** `src/labels.py`, `src/web/routes/settings.py`, `src/web/templates/pages/settings.html`, `tests/test_labels.py`

**Interfaces produced:** `labels.GOLD_CATEGORIES`, `labels.gold_url_ok(url) -> bool`, `labels.analyze_gold(label_id: int, upload_path: Optional[str] = None) -> None`; routes `POST /settings/standards` (form: `url`, `file`, `category`) and `POST /settings/standards/{id}/delete`.

- [ ] **Step 1: Failing tests** (`labels._download`, `stage7.clip_video_part`, `stage7.get_gemini_client`, `stage7.judge_generate` faked):
  - A TikTok link → the route answers 303, and the background task leaves a `ready` gold label with Gemini's title, transcript, why, humor type and hook, plus the view count.
  - A link on another host → refused, no label.
  - A download error → a `failed` label holding the error.
  - An uploaded `.mp4` → `ready`, and the uploaded file is deleted.
  - Delete removes the label. The Settings page lists the short.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Add `GoldRead`, `GOLD_PROMPT`, `_download` (yt-dlp, 720p cap, 200 MB cap), `analyze_gold`, `gold_url_ok` to `src/labels.py`; the two routes (upload streamed in 1 MB chunks with the size cap, as `new.py` does) and the Standards card.
- [ ] **Step 4:** Tests pass.
- [ ] **Step 5:** Commit "Add Standards on Settings: Gemini reads a short the team admires and keeps it as a gold label".

### Task 4: Examples in the judge prompt

**Files:** `src/pipeline/stage7_moments.py`, `tests/test_labels.py`

- [ ] **Step 1: Failing test:** `call_llm_judge([...], "", {}, examples="EXAMPLES HERE")` sends a prompt that contains `EXAMPLES HERE` (`generate_content_with_retry` captured).
- [ ] **Step 2:** Run → fail (unexpected keyword).
- [ ] **Step 3:** `call_llm_judge(..., examples: str = "")` puts the block after the creator context. `run_stage7_moments` builds `labels.examples_block(channel_key(meta), creator_type)` once and passes it in `judge_one`.
- [ ] **Step 4:** Test passes; `scripts/stage7_snapshot.py 2896358710` output equals `data/eval_rerun/snapshot_before.json`.
- [ ] **Step 5:** Commit "Show the team's gold shorts and recent verdicts to the transcript judge as examples".

### Task 5: Verify and ship

- [ ] Full suite passes (`py -m pytest -q`).
- [ ] Settings card and Reject dialog checked in the preview at desktop and 375 px; web-design-guidelines pass on the new markup.
- [ ] Cleanup scan of the diff; LEARNINGS.md entry; push `main`.
