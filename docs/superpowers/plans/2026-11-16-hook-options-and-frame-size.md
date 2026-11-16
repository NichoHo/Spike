# Hook Options and Frame Size Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every new anime clip gets three hook captions to choose from and a 4:3 frame by default, and the team can change both on the clip page.

**Architecture:** The anime judge writes three hooks per clip (`relatable`, `curious`, `plain`). Spike stores them on the candidate and starts the title card with the first one. A new per-clip `frame` setting (`fit`, `medium`, `close`) crops the sides of the picture before the letterbox scale. The clip page shows the hooks as chips and the frame as a select. Both go through the existing re-render route.

**Tech Stack:** Python 3.14 (`py -3.14`), FastAPI + Jinja2, SQLite, ffmpeg, Pillow, google-genai, pytest.

## Why this exists

The user's channel DragonSoulClips (Team Four Star clips made by Spike) got about 50% "swiped away" on the two Shorts YouTube tested. The hooks read like topic labels ("Mr. Popo's pecking order..."), and the footage fills only 32% of the frame. A comparable channel (@Hakaizo) uses a relatable caption on top and a picture that looks about 4:3 (read from one low-resolution frame, so approximate).

## Decisions (agreed with the user on 2026-11-16)

| Decision | Value |
|---|---|
| Hook voices | `relatable` ("When the bouncer asks you to leave for the third time:"), `curious` (a question), `plain` (one line saying what happens). The judge writes all three for every clip. |
| Default hook | The first voice that is filled in, in the order above. So `relatable`. |
| Other | The Hook title box on the clip page takes any text. A chip click only fills the box. |
| Frame sizes | `fit` (today, picture is 32% of the frame), `medium` (4:3 crop, 42%), `close` (square crop, 56%). |
| Default frame | `medium` for anime clips. `fit` everywhere else, so streamer clips do not change. |
| Which voice won | Read later by comparing `candidates.hook_text` with `candidates.hook_options`. No new column. |

## Global Constraints

- Run Python as `py -3.14` (the Bash tool's `python` is a 3.10 without the project dependencies).
- A hook is at most 80 characters. The judge must not use slurs or strong profanity in a hook.
- Frame names are exactly `fit`, `medium`, `close`. An unknown name means `fit`.
- Frame ratios are exact integers: `medium` is 4:3, `close` is 1:1. Crop width is made even.
- Do not copy captions from other channels. The prompt examples are written for this project.
- Model text reaches pages and videos only through `clean_llm_text` (control characters removed, length capped). Templates escape HTML.
- Commit rules for this repo: commit on `main`, as the user, no `Co-Authored-By` or other Claude trailers. Stage only the files named in each task. The working tree also holds unrelated changes (`src/labels.py`, `src/web/routes/settings.py`, `src/web/templates/pages/settings.html`, `tests/test_labels.py`, `docs/superpowers/specs/2026-11-10-share-standard-design.md`, `LEARNINGS.md`). Never stage them except where a task says so.
- Another session has been editing `src/pipeline/stage9c_render.py` and `src/web/routes/clips.py` (English captions). Every edit below names a text anchor, not a line number. Read the file around the anchor before you edit.

## File Structure

| File | Change |
|---|---|
| `src/models.py` | New `AnimeHooks`; `AnimeCandidate.hooks`. |
| `src/pipeline/anime_moments.py` | New `pick_hooks`; new prompt text; the record carries `hook_options`; `ANIME_RENDER_DEFAULTS` gets `frame`. |
| `src/db.py` | Two migrations; `insert_candidate` stores `hook_options`; `create_or_update_clip` takes `frame`. |
| `src/pipeline/stage9c_render.py` | New `FRAME_RATIOS`, `frame_crop`, `footage_height`; `frame` flows through the filter graph and the title card. |
| `src/web/routes/clips.py` | `frame` form field, validation and pass-through. |
| `src/web/routes/review.py` | Clip page gets `hook_options`. |
| `src/web/templates/pages/clip_detail.html` | Hook chips and the Frame select. |
| `tests/test_anime_hooks.py` | New. Judge hooks. |
| `tests/test_hook_frame_storage.py` | New. Database. |
| `tests/test_frame_size.py` | New. Crop math and ffmpeg. |
| `tests/test_rerender_settings.py` | Two tests added. |
| `LEARNINGS.md` | New entry (project rule: every session). |

---

### Task 0: Commit the title fix that is already in the working tree

Earlier in this session the judge prompt was changed so a line with no speaker no longer says `SPEAKER:` and names follow the transcript. That change is uncommitted in `src/pipeline/anime_moments.py` and Task 1 edits the same file.

**Files:**
- Modify (already edited): `src/pipeline/anime_moments.py`

- [ ] **Step 1: Check the diff holds only the title fix**

Run: `git diff -- src/pipeline/anime_moments.py`
Expected: a `build_prompt` change (no `SPEAKER` placeholder, new title rule) and a new assertion block in the `__main__` self-check. Nothing else.

- [ ] **Step 2: Run the module self-check**

Run: `py -3.14 -m src.pipeline.anime_moments`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/anime_moments.py
git commit -m "Stop the anime judge copying a SPEAKER placeholder into titles, and spell names the way fans do"
```

---

### Task 1: The judge writes three hooks

**Files:**
- Modify: `src/models.py` (class `AnimeCandidate`)
- Modify: `src/pipeline/anime_moments.py` (`ANIME_GUIDE`, `build_prompt`, the candidate record, new `pick_hooks`)
- Create: `tests/test_anime_hooks.py`

**Interfaces:**
- Produces: `AnimeHooks` (fields `relatable`, `curious`, `plain`, all `str`); `AnimeCandidate.hooks: AnimeHooks`; `pick_hooks(c: AnimeCandidate) -> Tuple[str, Dict[str, str]]` returns `(default_hook, {voice: text})`; the candidate record gets `hook_options: Dict[str, str]` (stored by Task 2).

- [ ] **Step 1: Write the failing test**

Create `tests/test_anime_hooks.py`:

```python
"""The anime judge writes three hook captions per clip; the title card starts with the first one that is filled in."""

from src.models import AnimeCandidate
from src.pipeline.anime_moments import build_prompt, pick_hooks


def _cand(**kw):
    base = {"punchline_line_idx": 1, "archetype": "comedy_beat",
            "scores": {"self_contained": 8, "payoff": 8, "setup_present": 8, "delivery": 8, "quotability": 8}}
    return AnimeCandidate.model_validate({**base, **kw})


def test_the_relatable_hook_is_the_default_and_the_others_are_kept():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "When the dirt wins:", "curious": "Why is Krillin below the dirt?",
                                         "plain": "Krillin ranks below dirt"}))
    assert hook == "When the dirt wins:"
    assert list(opts) == ["relatable", "curious", "plain"]


def test_a_blank_voice_is_dropped_and_the_next_one_is_the_default():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "  ", "curious": "Why?", "plain": "He loses"}))
    assert hook == "Why?" and list(opts) == ["curious", "plain"]


def test_hooks_are_one_line_and_at_most_80_characters():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "When\nthe\x00dirt wins:", "plain": "x" * 200}))
    assert hook == "When the dirt wins:" and len(opts["plain"]) == 80


def test_an_older_single_hook_still_works_and_null_hooks_do_not_drop_the_clip():
    assert pick_hooks(_cand(hook_text="Old hook")) == ("Old hook", {})
    assert pick_hooks(_cand(hooks=None, hook_text="Old hook")) == ("Old hook", {})


def test_the_prompt_asks_for_the_three_voices():
    p = build_prompt([{"start": 1.0, "end": 3.0, "text": "Hello.", "speaker": None}], {},
                     {"title": "Dragon Ball Z", "characters": []}, {})
    assert "hooks (an object with relatable, curious and plain)" in p
    for voice in ("- relatable:", "- curious:", "- plain:"):
        assert voice in p
    assert "hook_text" not in p
```

- [ ] **Step 2: Run it and see it fail**

Run: `py -3.14 -m pytest tests/test_anime_hooks.py -v`
Expected: collection error `ImportError: cannot import name 'pick_hooks'`.

- [ ] **Step 3: Add the model**

In `src/models.py`, insert this class directly above `class AnimeCandidate(BaseModel):`:

```python
class AnimeHooks(BaseModel):
    """The three hook captions for one clip, one per voice. The title card starts with the first one that is filled in."""
    relatable: str = Field(default="", description='The clip as an everyday situation, ending in a colon: "When your boss says quick question:"')
    curious: str = Field(default="", description="A question a stranger wants answered")
    plain: str = Field(default="", description="One line saying what happens")

    @field_validator("relatable", "curious", "plain", mode="before")
    @classmethod
    def _text(cls, v):
        return "" if v is None else str(v)
```

In the same file, inside `AnimeCandidate`, replace this line:

```python
    hook_text: str = Field(default="", description="3 to 8 word question or observation for a stranger, not a quote")
```

with:

```python
    hooks: AnimeHooks = Field(default_factory=AnimeHooks, description="Three hook captions, under 80 characters each")
    hook_text: str = Field(default="", description="Older single hook; the judge now fills hooks")

    @field_validator("hooks", mode="before")
    @classmethod
    def _hooks(cls, v):
        return v if isinstance(v, dict) else {}
```

- [ ] **Step 4: Add `pick_hooks`**

In `src/pipeline/anime_moments.py`, insert directly after the `clean_llm_text` function:

```python
HOOK_VOICES = ("relatable", "curious", "plain")  # the first one that is filled in starts on the title card
HOOK_MAX = 80  # the Hook title box on the clip page allows 80


def pick_hooks(c: AnimeCandidate) -> Tuple[str, Dict[str, str]]:
    """(the hook the title card starts with, {voice: text} for each voice the judge filled in).
    An older single hook_text is the fallback when no voice is filled in."""
    opts: Dict[str, str] = {}
    for voice in HOOK_VOICES:
        text = clean_llm_text(getattr(c.hooks, voice), HOOK_MAX)
        if text:
            opts[voice] = text
    return next(iter(opts.values()), clean_llm_text(c.hook_text, HOOK_MAX)), opts
```

- [ ] **Step 5: Change the prompt**

In `src/pipeline/anime_moments.py`, inside `ANIME_GUIDE`, replace these two lines:

```
For each clip, write hook_text: a 3 to 8 word question or observation for a stranger (example: "Why do anime attacks take forever?").
It is not a quote from the clip. It is shown on the title card above the video.
```

with:

```
For each clip, write hooks: three captions for the title card above the video, one per voice, each under 80 characters.
A hook is not a quote from the clip. Never use slurs or strong profanity.
- relatable: the clip as an everyday situation, ending in a colon (example: "When the bouncer asks you to leave for the third time:")
- curious: a question a stranger wants answered (example: "Why do anime attacks take forever?")
- plain: one line saying what happens (example: "Krillin learns he ranks below dirt")
```

In `build_prompt`, replace `hook_line_idx (line number or null), hook_text, title, hashtags,` with `hook_line_idx (line number or null), hooks (an object with relatable, curious and plain), title, hashtags,`.

In the same prompt, replace `In title and hook_text, spell each name` with `In title and hooks, spell each name`.

- [ ] **Step 6: Put the hooks in the candidate record**

In `src/pipeline/anime_moments.py`, in `run_stage7_anime`, find:

```python
        rec: Dict[str, Any] = {
            "origin": "anime_judge", "humor_type": c.archetype, "reason": clean_llm_text(c.why, 400), "why_funny": clean_llm_text(c.why, 400),
            "title": clean_llm_text(c.title or c.hook_text, 120), "hook_text": clean_llm_text(c.hook_text, 80),
```

and replace it with:

```python
        hook, hooks = pick_hooks(c)
        rec: Dict[str, Any] = {
            "origin": "anime_judge", "humor_type": c.archetype, "reason": clean_llm_text(c.why, 400), "why_funny": clean_llm_text(c.why, 400),
            "title": clean_llm_text(c.title or hook, 120), "hook_text": hook, "hook_options": hooks,
```

- [ ] **Step 7: Run the tests and the self-check**

Run: `py -3.14 -m pytest tests/test_anime_hooks.py -v`
Expected: 5 passed.

Run: `py -3.14 -m src.pipeline.anime_moments`
Expected: prints `ok`.

- [ ] **Step 8: Commit**

```bash
git add src/models.py src/pipeline/anime_moments.py tests/test_anime_hooks.py
git commit -m "Have the anime judge write three hooks per clip: relatable, a question, and plain"
```

---

### Task 2: Store hook options and the frame size

**Files:**
- Modify: `src/db.py` (migrations, `insert_candidate`, `create_or_update_clip`)
- Create: `tests/test_hook_frame_storage.py`

**Interfaces:**
- Consumes: the record key `hook_options` (a dict) from Task 1.
- Produces: column `candidates.hook_options` (JSON text, NULL when none); column `clips.frame` (text, default `'fit'`); `create_or_update_clip(..., frame: Optional[str] = None)` where `None` keeps the stored value and a new row gets `'fit'`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hook_frame_storage.py`:

```python
"""Hook options live on the candidate. The frame size lives on the clip."""

import json
import uuid

import pytest

from src.db import create_or_update_clip, get_candidate, get_clip, get_connection, insert_candidate, register_video


@pytest.fixture()
def video():
    vid = register_video("url", f"https://www.youtube.com/watch?v=hookframe&{uuid.uuid4().hex}", title="Hook and frame")
    yield vid
    with get_connection() as conn:  # keep the shared test DB's review queue clean for other tests
        conn.execute("DELETE FROM clips WHERE candidate_id IN (SELECT id FROM candidates WHERE video_id = ?)", (vid,))
        conn.execute("DELETE FROM candidates WHERE video_id = ?", (vid,))


def _cand(vid, **extra):
    return insert_candidate(vid, dict(origin="anime_judge", punchline="p", hook_text="h", post_caption="c", mood="laugh",
                                      humor_type="comedy_beat", status="selected", start_s=1.0, end_s=9.0,
                                      llm_score=80, final_score=80, title="t", **extra))


def test_a_candidate_keeps_its_hook_options(video):
    opts = {"relatable": "When the dirt wins:", "plain": "Krillin ranks below dirt"}
    assert json.loads(get_candidate(_cand(video, hook_options=opts))["hook_options"]) == opts
    assert get_candidate(_cand(video))["hook_options"] is None


def test_a_clip_starts_on_fit_and_none_keeps_the_stored_frame(video):
    cand = _cand(video)
    clip = create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox")
    assert get_clip(clip)["frame"] == "fit"
    create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox", frame="medium")
    assert get_clip(clip)["frame"] == "medium"
    create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox")
    assert get_clip(clip)["frame"] == "medium"
```

- [ ] **Step 2: Run it and see it fail**

Run: `py -3.14 -m pytest tests/test_hook_frame_storage.py -v`
Expected: FAIL. The first test fails with `IndexError: No item with that key` (no `hook_options` column). The second fails with `TypeError: create_or_update_clip() got an unexpected keyword argument 'frame'`.

- [ ] **Step 3: Add the two migrations**

In `src/db.py`, in the `migration_statements` list, add these two lines directly after the `caption_language` line (the one that ends with `# spoken or english, see src/caption_translate.py`):

```python
            "ALTER TABLE candidates ADD COLUMN hook_options TEXT",  # JSON {voice: text}: the judge's three hooks, see pick_hooks in src/pipeline/anime_moments.py
            "ALTER TABLE clips ADD COLUMN frame TEXT DEFAULT 'fit'",  # fit, medium (4:3 crop) or close (square crop), see frame_crop in stage9c_render.py
```

- [ ] **Step 4: Store the hook options**

In `insert_candidate`, in the column list change `concept_spec, judge_model` to `concept_spec, judge_model, hook_options`.

In the `VALUES (...)` list of the same statement, add one more `?` at the end. The list had 30 and must have 31.

In the parameter tuple, add this line directly after `cand.get("judge_model"),`:

```python
                json.dumps(cand["hook_options"]) if cand.get("hook_options") else None,
```

- [ ] **Step 5: Store the frame**

In `create_or_update_clip`, add a parameter after `caption_language: Optional[str] = None,`:

```python
    frame: Optional[str] = None,
```

In its `UPDATE clips SET ...` statement, change `caption_language = COALESCE(?, caption_language)` to `caption_language = COALESCE(?, caption_language), frame = COALESCE(?, frame)`, and in the parameter tuple change `sfx, caption_language, clip_id` to `sfx, caption_language, frame, clip_id`.

In its `INSERT INTO clips (...)` statement, change `sfx, caption_language\n                ) VALUES (` so the column list ends `sfx, caption_language, frame`, and add one more `?` to the end of the `VALUES (...)` list. In the parameter tuple, change `sfx, caption_language or "spoken"` to `sfx, caption_language or "spoken", frame or "fit"`.

- [ ] **Step 6: Run the tests**

Run: `py -3.14 -m pytest tests/test_hook_frame_storage.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/db.py tests/test_hook_frame_storage.py
git commit -m "Store the judge's hook options on the candidate and a frame size on the clip"
```

---

### Task 3: Frame size in the render

**Files:**
- Modify: `src/pipeline/stage9c_render.py`
- Modify: `src/pipeline/anime_moments.py` (`ANIME_RENDER_DEFAULTS`)
- Create: `tests/test_frame_size.py`

**Interfaces:**
- Consumes: `clips.frame` and `create_or_update_clip(frame=...)` from Task 2.
- Produces: `FRAME_RATIOS: Dict[str, Optional[Tuple[int, int]]]`; `frame_crop(frame: str, src_w: int, src_h: int) -> Optional[Tuple[int, int]]` (crop width, crop height, or `None`); `footage_height(frame: str, src_w: int, src_h: int) -> int`; a `frame: str = "fit"` argument on `_layout_filters`, `build_vertical_filtergraph` and `render_single_vertical_clip`; the setting key `frame` read by `run_stage9c_render`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_frame_size.py`:

```python
"""Frame size crops the sides of the picture before it is scaled into the 1080x1920 letterbox."""

import subprocess

import pytest
from PIL import Image

from src.pipeline.anime_moments import ANIME_RENDER_DEFAULTS
from src.pipeline.stage9c_render import _layout_filters, build_vertical_filtergraph, footage_height, frame_crop


def test_frame_crop_keeps_the_middle_at_the_frame_ratio():
    assert frame_crop("fit", 1920, 1080) is None
    assert frame_crop("medium", 1920, 1080) == (1440, 1080)  # 4:3
    assert frame_crop("close", 1920, 1080) == (1080, 1080)   # square
    assert frame_crop("medium", 1280, 720) == (960, 720)
    assert frame_crop("medium", 1440, 1080) is None          # already 4:3: nothing to crop
    assert frame_crop("medium", 1080, 1920) is None          # a tall source is never cropped
    assert frame_crop("huge", 1920, 1080) is None            # an unknown name means fit


def test_the_title_card_sits_above_the_cropped_picture():
    assert [footage_height(f, 1920, 1080) for f in ("fit", "medium", "close")] == [607, 810, 1080]


def _graph(**kw):
    return build_vertical_filtergraph(sec_start=0.0, keep_intervals=[(0.0, 10.0)], layout="letterbox", src_w=1920,
                                      src_h=1080, effective_dur=10.0, ass_rel="x.ass", **kw)


def test_the_crop_comes_before_the_scale_in_both_letterbox_styles():
    assert "[v_trimmed]crop=1440:1080,scale=1080:1920" in _graph(letterbox_style="title", title_input=1, frame="medium")
    assert "[v_trimmed]crop=1080:1080,split=2[bg_in][fg_in]" in _graph(letterbox_style="blur", frame="close")
    assert "crop=1440" not in _graph(letterbox_style="title", title_input=1)  # fit is the default


@pytest.mark.parametrize("frame,rows", [("fit", 607), ("medium", 810), ("close", 1080)])
def test_ffmpeg_fills_the_expected_height(tmp_path, frame, rows):
    graph = ";".join(["[0:v]null[v]"] + _layout_filters("letterbox", "v", "out", 1920, 1080, None, None, None, "title", "", frame))
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=red:size=1920x1080:rate=5:duration=1", "-filter_complex", graph, "-map", "[out]",
                    "-frames:v", "1", str(png)], check=True)
    img = Image.open(png).convert("RGB")
    assert img.size == (1080, 1920)
    red = sum(1 for y in range(1920) if img.getpixel((540, y))[0] > 200 and img.getpixel((540, y))[1] < 80)  # white bars are not red
    assert abs(red - rows) <= 2


def test_anime_clips_start_on_the_medium_frame():
    assert ANIME_RENDER_DEFAULTS["frame"] == "medium"
```

- [ ] **Step 2: Run it and see it fail**

Run: `py -3.14 -m pytest tests/test_frame_size.py -v`
Expected: collection error `ImportError: cannot import name 'footage_height'`.

- [ ] **Step 3: Add the crop helpers**

In `src/pipeline/stage9c_render.py`, insert directly above `def _layout_filters(`:

```python
FRAME_RATIOS: Dict[str, Optional[Tuple[int, int]]] = {"fit": None, "medium": (4, 3), "close": (1, 1)}  # width:height of the picture kept; fit keeps all


def frame_crop(frame: str, src_w: int, src_h: int) -> Optional[Tuple[int, int]]:
    """(crop_w, crop_h) of the middle of the source for a frame size, or None when nothing is cropped: fit, an unknown name,
    or a source already as narrow as the frame. Integer math, and an even width because libx264 needs one."""
    ratio = FRAME_RATIOS.get(frame)
    if not ratio:
        return None
    num, den = ratio
    if src_w * den <= src_h * num:
        return None
    return src_h * num // den // 2 * 2, src_h


def footage_height(frame: str, src_w: int, src_h: int) -> int:
    """Height in pixels of the letterboxed picture inside the 1080x1920 frame. The title card sits above it."""
    w, h = frame_crop(frame, src_w, src_h) or (src_w, src_h)
    return min(OUTPUT_HEIGHT, int(OUTPUT_WIDTH * h / w))
```

- [ ] **Step 4: Pass `frame` through `_layout_filters`**

In `_layout_filters`, change the end of the signature from:

```python
    zoom_z: str = "",
) -> List[str]:
```

to:

```python
    zoom_z: str = "",
    frame: str = "fit",
) -> List[str]:
```

In the same function, change the recursive call:

```python
        inner = _layout_filters(layout, src, f"{dst}_nz", src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style)
```

to:

```python
        inner = _layout_filters(layout, src, f"{dst}_nz", src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style, "", frame)
```

Then replace the two letterbox branches. Find:

```python
    if layout == "letterbox" and letterbox_style == "title":  # title card is overlaid after the zoom
        return [
            f"[{src}]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
```

and replace it with:

```python
    crop = frame_crop(frame, src_w, src_h)
    cut = f"crop={crop[0]}:{crop[1]}," if crop else ""  # the middle of the picture, before it is scaled to the frame width
    if layout == "letterbox" and letterbox_style == "title":  # title card is overlaid after the zoom
        return [
            f"[{src}]{cut}scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
```

Then find:

```python
    if layout == "letterbox":
        return [
            f"[{src}]split=2[bg_in][fg_in]",
```

and replace it with:

```python
    if layout == "letterbox":
        return [
            f"[{src}]{cut}split=2[bg_in][fg_in]",
```

- [ ] **Step 5: Pass `frame` through the filter graph**

In `build_vertical_filtergraph`, change the end of the signature from:

```python
    sfx_at: Optional[List[Tuple[int, float]]] = None,
) -> str:
```

to:

```python
    sfx_at: Optional[List[Tuple[int, float]]] = None,
    frame: str = "fit",
) -> str:
```

In the same function, change:

```python
    lay_args = (src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style, _zoom_expr(zooms) if zooms else "")
```

to:

```python
    lay_args = (src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style, _zoom_expr(zooms) if zooms else "", frame)
```

- [ ] **Step 6: Pass `frame` through the single-clip render and size the title card from it**

In `render_single_vertical_clip`, change the end of the signature from:

```python
    caption_language: str = "spoken",
) -> bool:
```

to:

```python
    caption_language: str = "spoken",
    frame: str = "fit",
) -> bool:
```

In its docstring, add this line after the `letterbox_style:` paragraph:

```
    frame: "fit", "medium" (4:3 crop) or "close" (square crop): how much of the picture Letterbox shows. The title card sits above it.
```

Replace the title card height line:

```python
        video_h = min(OUTPUT_HEIGHT, int(OUTPUT_WIDTH * src_h / src_w))
```

with:

```python
        video_h = footage_height(frame, src_w, src_h)
```

In the `build_vertical_filtergraph(` call at the end of this function, add `frame=frame,` directly after `letterbox_style=letterbox_style,` (the line that is followed by `title_input=(2 if has_music else 1) if title_png else None,`).

- [ ] **Step 7: Read the setting in the batch render**

In `run_stage9c_render`, directly after:

```python
    letterbox_style = src_settings.get("letterbox_style", "title")
```

add:

```python
    frame = src_settings.get("frame", "fit")
    frame = frame if frame in FRAME_RATIOS else "fit"
```

In the `render_single_vertical_clip(` call in that function, add `frame=frame,` directly after `letterbox_style=letterbox_style,` (the line followed by `title_text=cand.get("hook_text") or cand.get("title") or "",`).

In the `create_or_update_clip(` call in that function, add `frame=frame,` directly after `zooms=json.dumps(cand.get("zooms") or []),`.

- [ ] **Step 8: Make medium the default for anime**

In `src/pipeline/anime_moments.py`, change:

```python
                         "cut_pauses": "off", "music": False}
```

to:

```python
                         "cut_pauses": "off", "music": False, "frame": "medium"}
```

- [ ] **Step 9: Run the new tests and the neighbours**

Run: `py -3.14 -m pytest tests/test_frame_size.py tests/test_letterbox_title.py tests/test_layout_switches.py -v`
Expected: all pass (the ffmpeg test needs `ffmpeg` on PATH, as `tests/test_rerender_settings.py` does).

- [ ] **Step 10: Commit**

```bash
git add src/pipeline/stage9c_render.py src/pipeline/anime_moments.py tests/test_frame_size.py
git commit -m "Add a frame size to Letterbox: fit, a 4:3 crop or a square crop, and start anime clips on the 4:3 crop"
```

---

### Task 4: The clip page, the hook chips and the Frame select

**Files:**
- Modify: `src/web/routes/clips.py`
- Modify: `src/web/routes/review.py`
- Modify: `src/web/templates/pages/clip_detail.html`
- Modify: `tests/test_rerender_settings.py` (add two tests at the end)

**Interfaces:**
- Consumes: `FRAME_RATIOS` and the `frame` argument of `render_single_vertical_clip` (Task 3); `candidates.hook_options` and `create_or_update_clip(frame=...)` (Task 2).
- Produces: form field `frame` on `POST /clips/{id}/rerender`; template variable `hook_options: Dict[str, str]`; chips with attribute `data-hook`; a `<select name="frame">`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_rerender_settings.py` (it already has the `env` fixture and the imports for `json`, `get_clip` and `get_connection`):

```python
def test_frame_is_saved_with_the_re_render_and_a_bad_value_means_fit(env):
    form = {"start_s": "28", "end_s": "35", "layout": "letterbox", "letterbox_style": "title", "caption_style": "bold_pop",
            "hook_text": "When the test passes:", "layout_changes": "[]"}
    assert env["c"].post(f"/clips/{env['clip']}/rerender", data={**form, "frame": "close"}, follow_redirects=False).status_code == 303
    assert get_clip(env["clip"])["frame"] == "close"
    assert '<option value="close" selected>' in env["c"].get(f"/clips/{env['clip']}").text
    env["c"].post(f"/clips/{env['clip']}/rerender", data={**form, "frame": "huge"}, follow_redirects=False)
    assert get_clip(env["clip"])["frame"] == "fit"


def test_clip_page_offers_the_three_hooks_and_still_takes_any_text(env):
    assert "data-hook-chips" not in env["c"].get(f"/clips/{env['clip']}").text  # a clip without options shows none
    opts = {"relatable": "When the dirt wins:", "curious": "Why is Krillin below the dirt?", "plain": "Krillin ranks below dirt"}
    with get_connection() as conn:
        conn.execute("UPDATE candidates SET hook_options = ? WHERE id = ?", (json.dumps(opts), env["cand"]))
    html = env["c"].get(f"/clips/{env['clip']}").text
    assert html.count("data-hook=") == 3 and 'data-hook="When the dirt wins:"' in html
    assert 'name="hook_text"' in html  # Other: the box is still there for any text
```

- [ ] **Step 2: Run them and see them fail**

Run: `py -3.14 -m pytest tests/test_rerender_settings.py -k "frame_is_saved or offers_the_three_hooks" -v`
Expected: both FAIL (`frame` stays `fit`; no `data-hook` chips).

- [ ] **Step 3: Accept and validate `frame` in the routes**

In `src/web/routes/clips.py`, change the import line:

```python
from src.pipeline.stage9c_render import SWITCH_LAYOUTS, render_single_vertical_clip
```

to:

```python
from src.pipeline.stage9c_render import FRAME_RATIOS, SWITCH_LAYOUTS, render_single_vertical_clip
```

In `rerender_clip_action`, add a form field directly after the line `letterbox_style: str = Form("blur"),  # the toggle sends "title" when on`:

```python
    frame: str = Form("fit"),             # fit, medium or close; anything else is fit
```

In the `params = dict(` of that function, change `layout_changes=layout_changes, letterbox_style=letterbox_style,` to:

```python
layout_changes=layout_changes, letterbox_style=letterbox_style, frame=frame if frame in FRAME_RATIOS else "fit",
```

In `ai_edit_clip_action`, in its `params = dict(`, change `letterbox_style=clip.get("letterbox_style") or "blur", zooms=None, cuts=None, sfx=None,` to:

```python
letterbox_style=clip.get("letterbox_style") or "blur", frame=clip.get("frame") or "fit", zooms=None, cuts=None, sfx=None,
```

In `_rerender_job`, in the `render_single_vertical_clip(` call, add `frame=p.get("frame", "fit"),` directly after `letterbox_style=letterbox_style,` (the line followed by `title_text=clean_hook or clip.get("cand_title") or "",`).

In the `create_or_update_clip(` call at the end of `_rerender_job`, add `frame=p.get("frame", "fit"),` directly after `letterbox_style=letterbox_style,` (the line followed by `cuts=json.dumps(cuts),`).

- [ ] **Step 4: Give the page its hook options**

In `src/web/routes/review.py`, in the `context={...}` of `clip_detail`, add this line directly after `"ai_edits": list_clip_ai_edits(clip_id),`:

```python
            "hook_options": json.loads(cand["hook_options"]) if cand and cand["hook_options"] else {},
```

- [ ] **Step 5: Add the hook chips**

In `src/web/templates/pages/clip_detail.html`, find this line in the "Text on the video" section:

```html
            <input type="text" name="hook_text" id="field-hook-text" class="input" value="{{ clip.cand_hook or '' }}" maxlength="80" placeholder="Short funny summary of the clip…">
```

and add this block directly after it:

```html
            {% if hook_options %}
            <div class="chip-row" role="group" aria-label="Hook suggestions" style="margin-top: var(--space-2);" data-hook-chips>
              {% for voice, label in [('relatable', 'Relatable'), ('curious', 'Question'), ('plain', 'Plain')] if hook_options.get(voice) %}
              <button type="button" class="chip{% if hook_options[voice] == clip.cand_hook %} is-on{% endif %}" data-hook="{{ hook_options[voice] }}" aria-pressed="{{ 'true' if hook_options[voice] == clip.cand_hook else 'false' }}" title="{{ hook_options[voice] }}">{{ label }}: {{ hook_options[voice] }}</button>
              {% endfor %}
            </div>
            <p class="field__help">Click one to use it, or type your own above. Re-render to apply.</p>
            <script>
            (() => {
              const input = document.getElementById('field-hook-text');
              const chips = document.querySelectorAll('[data-hook-chips] .chip');
              const sync = () => chips.forEach((c) => { const on = c.dataset.hook === input.value.trim(); c.classList.toggle('is-on', on); c.setAttribute('aria-pressed', String(on)); });
              chips.forEach((c) => c.addEventListener('click', () => { input.value = c.dataset.hook; input.dispatchEvent(new Event('input', { bubbles: true })); }));
              input.addEventListener('input', sync);
            })();
            </script>
            {% endif %}
```

- [ ] **Step 6: Add the Frame select**

In the same template, in the "Framing" section, find:

```html
            <p class="field__help">Auto lets the AI pick the layout and any switches again when you re-render, replacing the switches below.</p>
          </div>
```

and add this block directly after the closing `</div>`:

```html

          <div class="field">
            <label class="field__label" for="field-frame">Frame</label>
            <select name="frame" id="field-frame" class="select">
              {% for value, label in [('fit', 'Fit: the whole picture'), ('medium', 'Medium: 4:3 crop'), ('close', 'Close: square crop')] %}
              <option value="{{ value }}" {% if (clip.frame or 'fit') == value %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
            <p class="field__help">How much of the picture Letterbox shows. Medium and Close crop the sides.</p>
          </div>
```

- [ ] **Step 7: Run the tests**

Run: `py -3.14 -m pytest tests/test_rerender_settings.py tests/test_concept_ui.py -v`
Expected: all pass, including the two new tests.

- [ ] **Step 8: Commit**

```bash
git add src/web/routes/clips.py src/web/routes/review.py src/web/templates/pages/clip_detail.html tests/test_rerender_settings.py
git commit -m "Show the three hooks as chips and a Frame select on the clip page, and apply both on re-render"
```

---

### Task 5: Check it by eye, run everything, write the notes

**Files:**
- Modify: `LEARNINGS.md`

- [ ] **Step 1: Render the three frame sizes and look at them**

Run this from the repo root in PowerShell. It makes a 16:9 test clip, renders it at each frame size with a long relatable hook, and saves a thumbnail for each.

```powershell
$out = Join-Path $env:TEMP "frame_preview"
@'
import subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
from src.pipeline.stage9c_render import render_single_vertical_clip
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
sec = out / "section.mp4"
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=8",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                "-shortest", str(sec)], check=True)
for frame in ("fit", "medium", "close"):
    ok = render_single_vertical_clip(sec_file=sec, out_file=out / f"{frame}.mp4", thumb_file=out / f"{frame}.jpg", clip_start=1.0,
                                     clip_end=6.0, layout="letterbox", letterbox_style="title", zooms=[], section_start_s=0.0,
                                     title_text="When the bouncer asks you to leave for the third time:", frame=frame)
    print(frame, ok)
'@ | py -3.14 - $out
Get-ChildItem $out -Filter *.jpg | Select-Object Name, Length
```

Expected: `fit True`, `medium True`, `close True`, and three `.jpg` files.

Open each `.jpg`. Check three things: the picture grows from fit to medium to close, the title text never touches the picture, and nothing looks stretched. If the title overlaps the picture on `close`, check that Step 6 of Task 3 used `footage_height`.

- [ ] **Step 2: Run the related tests, then the full suite**

Run: `py -3.14 -m pytest tests/test_anime_hooks.py tests/test_hook_frame_storage.py tests/test_frame_size.py tests/test_letterbox_title.py tests/test_layout_switches.py tests/test_rerender_settings.py tests/test_concept_ui.py tests/test_anime_new_form.py tests/test_anime_security.py -q`
Expected: all pass.

Run: `py -3.14 -m pytest -q` (this can take several minutes)
Expected: no new failures. If a test fails, run it on a clean checkout of `HEAD~5` before blaming this work: the suite shares one database and another session is committing too.

Run: `py -3.14 -m src.pipeline.anime_moments`
Expected: prints `ok`.

- [ ] **Step 3: Write the notes**

In `LEARNINGS.md`, add a new entry directly under `# Spike: Learnings`, above the newest entry:

```markdown
## 2026-11-16: Three hooks per anime clip and a frame size

- **Built:** the anime judge writes three hooks per clip (`relatable`,
  `curious`, `plain`). The title card starts with the first one. The clip
  page shows them as chips; the Hook title box still takes any text. A new
  per-clip Frame setting (`fit`, `medium` 4:3, `close` square) crops the
  sides before the letterbox scale. Anime clips start on `medium`; every
  other source stays on `fit`.
- **Why:** on the user's Dragon Ball channel about half of the viewers of
  the two Shorts YouTube tested swiped away, the hooks read like topic
  labels, and the picture filled 32% of the frame.
- **Not built:** hooks for Shorts already posted; hooks on the blurred
  style (it has no title card); the anime judge does not read the Standards
  (gold labels) yet.
- **Read results:** compare `candidates.hook_text` with `hook_options` to see
  which voice a clip used:
  `SELECT id, CASE hook_text WHEN json_extract(hook_options,'$.relatable') THEN 'relatable' WHEN json_extract(hook_options,'$.curious') THEN 'curious' WHEN json_extract(hook_options,'$.plain') THEN 'plain' ELSE 'custom' END AS voice FROM candidates WHERE hook_options IS NOT NULL;`
  After about 10 Shorts, compare "Stayed to watch" in YouTube Studio with
  the old 50% and see which voice did best. 4:3 as the right crop is read
  from one low-resolution frame of another channel; treat it as a guess.
```

- [ ] **Step 4: Commit and push**

`LEARNINGS.md` also holds another session's uncommitted notes (Nov 13 and the title-fix entry from Task 0). Commit the file whole.

```bash
git add LEARNINGS.md
git commit -m "Log the hook options and frame size work"
git push origin main
```

Expected: the push succeeds. If it is rejected because `main` moved, run `git pull --rebase origin main` and push again.

---

## Self-review notes

- **Spec coverage:** three hooks per clip (Task 1), a way to pick one and type another (Task 4 chips plus the existing box), default relatable (Task 1 `pick_hooks`), three frame sizes with `medium` as the anime default (Task 3), changeable per clip (Task 4), title card follows the crop (Task 3 `footage_height`), streamer clips unchanged (`frame` defaults to `fit` in every signature, and `create_or_update_clip` gives new rows `fit`).
- **Not covered on purpose:** blurred style has no hook; old Shorts get no hooks; the judge ignores Standards. Fight and crowd-seed clips (made without judge text) keep one hook and show no chips.
- **Checked before handing over:** every text anchor above appears exactly once in its file. The crop math, the ffmpeg filter chains (title and blur styles), the hooks model and the Jinja chip loop were run in isolation and pass. The task tests themselves have not been run, because the code is not written yet.
- **Known risk:** the 4:3 ratio for `medium` comes from one low-resolution frame of another channel. `FRAME_RATIOS` is the one place to change it.
- **Known gap:** nothing measures whether the hooks work. Use the SQL in Task 5 and YouTube Studio after about 10 Shorts.
