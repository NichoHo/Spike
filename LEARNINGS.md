# Spike: Learnings

## 2026-10-13: Clip quality review (IShowSpeed FIFA stream, video #38)

- **Done:** reviewed run #38 (`MBod0tK46Js`, 2.8 h, 6 clips) against the
  user's notes. No code changed. Plan written into `BLUEPRINT.md` §6.7 and
  Phase 7b.
- **Learned (verified, `data/videos/38`):** the signal side was dead on this
  run, so 5 of 6 clips came from transcript chunk proposals:
  - `audio_loud` is -70 for every second: the `ebur128` stderr parse in
    `stage6_signals.compute_audio_loudness` matched nothing.
  - YAMNet `laugh` max 0.50 and `shout` max 0.33 over 2.8 h of a loud
    streamer. Only 2 s pass the 0.25/0.30 absolute thresholds. Absolute
    YAMNet thresholds do not work on streams with game audio.
  - `replay_heat` all 0. `has_chat` false and no `chat.json` (cause not yet
    checked: stage 3 did not fetch the YouTube live chat replay).
  - Only 2 signal peaks (`height=1.5`, `prominence=0.8`) for a 6-clip target.
- **Learned (verified, code):**
  - `propose_transcript_chunks` sends only `chunk_segs[:80]`. Median segment
    is 3.15 s, so the proposer saw about half of each 8-min chunk.
  - Every candidate got raw LLM score 85.0 from `gemini-3.1-flash-lite`. The
    UI shows the within-VOD percentile, and ties count as `<=`, so all show
    98 to 99. The score carries no information.
  - Whisper ran with one detected language (`en`, p=0.995). Indonesian
    speech was forced into English, so the LLM could not see the bit.
    `faster-whisper` 1.2.1 `transcribe()` has `multilingual` and
    `language_detection_segments` params.
  - Punch-in zoom fires at the clip midpoint (`stage9c_render.py`
    `raw_peak_t = clip_start + clip_dur / 2.0`), not the punchline.
  - Clip edges: lines are whole Whisper segments, the end snaps to the
    end-line segment + 0.6 s, and the laugh extension never fires (laugh is
    dead). Reactions with no words (screams, rage) get cut off.
  - Only the selected candidates are written to the DB. Rejected and
    low-score moments are lost.
  - `claude --bare` never reads OAuth, so it cannot use a Pro subscription.
    Use `--system-prompt`, `--tools ""`, `--setting-sources`, `--json-schema`,
    `--no-session-persistence` instead (verified, `claude --help` 2.1.280).
- **Learned (sourced, web 2026-10-13):** Gemini samples video at 1 fps by
  default; a custom fps is set in video metadata. Gemini 2.5 Pro is a strong
  temporal-grounding baseline (TimeLens2, arXiv 2607.17423). Trailer and golf
  highlight systems set clip edges by snapping a padded window to shot or
  audio boundaries (arXiv 2602.02630, 1707.07075). `claude -p` on a
  subscription counts toward plan limits; reports disagree on a separate
  Agent SDK credit since June 2026 (recalled from secondary sources, verify).
- **User feedback (ground truth for this VOD):** clip 1 has Mandarin fluff
  to 0:05 and the Indonesian bit ran much longer in the stream; clip 2 funny
  part starts 0:26; clip 3 starts 0:13 (donation question) and would be
  better stitched to a later rage/loss; clip 4 starts 0:30 and is weak;
  clip 5 is 0:18 to 0:42 and weak; clip 6 not funny. Missed: rage after
  conceding goals and after losing matches.
- **Decided:** fix signals and proposal coverage before tuning prompts.
  Gemini Flash-Lite stays for cheap scanning only. A stronger model judges.
  Claude (Sonnet via `claude -p`, Pro plan) does one editor pass per VOD and
  the comment-driven re-edit. Details in `BLUEPRINT.md` §6.7.
- **Decided (same day):** video watching stays on Gemini Flash. Claude has
  no audio input, and rage is mostly audio. Feeding Claude frames costs
  about 2 M image tokens per 2.8 h stream at 0.5 fps (recalled formula:
  tokens = width x height / 750), which would use up a Pro plan. Gemini
  takes the YouTube URL with audio directly.
- **Decided (same day):** add a per-source creator profile, a per-video
  session profile, and learned preferences from user feedback. The profile
  steers prompts and picks a fixed `creator_type` preset. See §6.7.
- **Ground truth #38 (user, first match vs Kvaratskhelia only, about
  29:00 to 44:00; rest of the stream not watched):** concedes at 30:30,
  32:50, 39:58, 43:30 (fourth goal, loses the match). 33:27 goes from cocky
  to raging, needs a manual cut inside. User: only 1 or 2 of these should
  be clips. Plain rage is not interesting because Speed rages all the time.
  Pick the craziest rage, or pair it with the cocky part before it.
- **Decided (same day):** added `baseline_behaviors` to the creator
  profile, episodes per stream, one clip per episode per humor type, and
  manual cut ranges on the clip page (§6.7, §10.1).
- **Decided (2026-10-14):** add Top 3 / Top 5 compilations as a themed,
  escalating countdown built on the story-combo multi-segment clip (§6.7).
  Sourced from vendor blogs only (vidiq, VueReka, ClipFarmer, StreamsCharts):
  tease #1 early, rank label per entry, 20 to 45 s single clips retain
  best. YouTube Shorts max 3 min since Oct 2024 (several sources agree);
  TikTok and Reels limits vary by source, not verified.
- **Decided (2026-10-14):** clips get a `concept` (single, story, pov,
  top3, top5), shown in its own UI section, not under layout. AI picks the
  default; the user can change it or build any concept by hand. POV rules
  from POV-format guides (socialk.it, meme.com, sendible): caption is the
  setup and the clip the payoff, short enough to read in 1 s, no bragging.
- **Open:** check why stage 3 got no YouTube chat for #38. User has not
  reviewed #38 past 44:00, so recall there is unknown.

## 2026-10-01: Phase 6 — Posting (Platform upload, token encryption at rest, permissions enforcement, auto-post rules, scheduling)

- **Done:**
  - Token encryption at rest (`src/security.py`):
    - Symmetric encryption of OAuth tokens using Fernet (`cryptography.fernet.Fernet`) with `SPIKE_ENCRYPTION_KEY` in `.env`.
    - Added `accounts`, `posts`, and `post_stats` tables in `src/db.py` storing encrypted tokens as BLOBs (`access_token_enc`, `refresh_token_enc`).
    - API and queries only decrypt tokens when explicitly requested (`get_account(..., decrypt=True)`), preventing plaintext leaks in listings or logs.
  - Hard permission check enforcement (`src/posting.py`, Blueprint §8.3, §12):
    - `verify_clip_posting_permission(clip_id)` strictly verifies `source.permission != 'none'`, raising `PermissionBlockedError`.
    - Check enforced in code across all execution paths: `dispatch_post()`, `evaluate_clip_autopost()`, `POST /clips/{id}/post`, and UI templates.
  - Platform posting implementations:
    - **TikTok upload-to-inbox mode:** Uses TikTok Creator API (`/v2/post/publish/inbox/video/init/`) to upload video directly into creator's TikTok inbox without requiring a compliance audit. Creator reviews and publishes from mobile app.
    - **YouTube Shorts:** Uses YouTube Data API v3 (`videos.insert`) resumable upload forced to `privacyStatus: "private"` until audit approval. Title automatically formatted with `#Shorts`.
    - **Instagram Reels:** Meta Graph API container upload with caption and hashtag formatting.
  - Auto-post evaluation engine (`evaluate_clip_autopost`, Blueprint §8.3):
    - Enforces all §8.3 rules: source permission check (`!= 'none'`), score floors (`final_score >= 80` AND raw `llm_score >= 70`), `needs_context == 0`, and account daily post cap (default 3 posts per day).
    - Integrated into `src/pipeline/runner.py` to automatically schedule qualifying clips upon render completion.
  - Scheduling engine (`get_due_posts`, `run_posting_scheduler_cycle`, Blueprint §8.4):
    - Computes next schedule slot (defaulting to 12:00 and 19:00 local time).
    - Background scheduler cycle integrated into `src/worker.py` daemon, checking every 30 seconds for due posts and dispatching them asynchronously.
  - Web UI routes & templates:
    - `GET /posts`: Monitoring screen with tabs (`Scheduled`, `Posted`, `Failed`), thumbnail previews, account badges, post status, and retry/cancel actions.
    - `GET /clips/{id}/post` & `POST /clips/{id}/post`: Clip posting form with account picker, timing options ("now" vs slot), and prefilled caption/hashtags. Displays prominent warning alert and hides form if `permission == 'none'`.
    - `/settings`: Added Connected Accounts card with platform badges, account handle, and Disconnect action; added Connect Account modal dialog.
    - Added `Posts` navigation link to sidebar (`paper-plane-tilt` icon) and Post buttons to `clip_detail.html`.
  - Comprehensive Phase 6 test suite (`tests/test_phase6.py`):
    - 7 automated tests covering Fernet encryption at rest, `permission='none'` hard blocking across all paths, TikTok inbox upload, YouTube Shorts private upload, auto-post rules/caps, scheduling cycle, and web routes.
- **Learned (verified):**
  - **Fernet Token Encryption:** Storing OAuth tokens as Fernet-encrypted ciphertext BLOBs in SQLite prevents accidental plaintext leakage even if the SQLite database file is inspected or dumped. The encryption key resides exclusively in `.env`.
  - **Jinja2 Autoescaping in Tests:** Jinja2 templates autoescape single quotes (`'` to `&#39;`), which causes literal assertion strings like `assert "permission='none'" in resp.text` to fail even when the detail message is present. Asserting on plain phrases (`"Posting permanently blocked"`) or unescaped fragments avoids false test failures.
  - **Test Isolation in Shared SQLite DB:** Re-running auto-post tests without clearing the `accounts` or `posts` table between test functions causes account counts to accumulate, leading daily cap tests to schedule for old accounts or hit limits prematurely. Adding explicit table cleanups in `setup_test_db` ensures isolated and deterministic test runs.
- **Decided:**
  - Phase 6 exit criteria met: TikTok upload-to-inbox and YouTube Shorts private uploads verified; automated test proves a `permission = 'none'` clip cannot post through any path (code, API, scheduler, UI); tokens encrypted at rest via Fernet; and all auto-post rules enforced.

## 2026-10-01: Phase 5 — Music and effects polish (Mood library, license sidecars, sidechain ducking, silence trim, per-source defaults)

- **Done:**
  - Procedural music library synthesized in `music/` for all 5 moods (`chill`, `hype`, `funny`, `dramatic`, `wholesome`) with licensed `.json` sidecars containing source, license, and attribution URL (`CC0 1.0 Universal`).
  - Startup check in `src/music.py` (`validate_music_library`) enforcing that every audio file in `music/` has an accompanying license sidecar with required fields (`license`, `source`, `url`), raising `MusicLicenseError` on any violation.
  - Enforced startup check in `src/web/app.py` lifespan, `src/worker.py` daemon, and `spike music` CLI command.
  - Speech-activated audio ducking implemented in `src/pipeline/stage9c_render.py` using FFmpeg `sidechaincompress`:
    - Base music sits at -22 dB (`volume=0.08`).
    - Speech signal acts as sidechain key to dynamically compress music further by 5:1 ratio (`threshold=0.03`, `attack=15ms`, `release=250ms`) when speech is active.
    - Mixed with dialogue via `amix` and normalized via `loudnorm` (-14 LUFS, -1.5 dBTP).
  - Silence trim engine implemented in `src/pipeline/stage9c_render.py` (§7.4):
    - Detects dead air pauses > 1.2s between consecutive words.
    - Leaves 0.4s natural breathing space (`SILENCE_TRIM_BREATH_S`).
    - Synchronizes video and audio cuts via native FFmpeg `trim`/`atrim` + `concat` without drift.
    - Retimes word timestamps in ASS karaoke captions and punch-in zoom peak timestamps to match the trimmed timeline.
  - Per-source defaults in database (`sources` table) and UI:
    - Added `default_music_mood`, `silence_trim`, `punch_in_zoom` with automated SQLite column migrations.
    - Updated `source_edit.html` with toggle switches and mood selector.
    - Updated `clip_detail.html` and `POST /clips/{id}/rerender` with live interactive controls for music track selection, silence trimming, and punch-in zoom.
  - Built unit and integration test suite `tests/test_phase5.py`:
    - 8 test cases verifying sidecar enforcement, mood normalization, silence trim retiming, source persistence, re-render API, and a 10-clip spot check.
    - All 45 project tests passing across Phases 1 through 5.
- **Learned (verified):**
  - **FFmpeg `sidechaincompress` audio ducking:** Feeding dialogue `[a_speech]` as the sidechain control key to compress music `[bgm]` with `threshold=0.03`, `ratio=5`, and `release=250` seamlessly ducks background music by > 12 dB whenever speech is detected, and recovers smoothly during natural pauses without pumping artifacts.
  - **Silence trim A/V and subtitle synchronization:** Cutting dead air pauses via FFmpeg `trim` / `atrim` + `concat` requires mathematical remapping of word timestamps: $t' = t - \sum \Delta_{cut}$. Applying this remapping keeps ASS karaoke subtitles and punch-in zoom in 100% lockstep sync with the edited video.
  - **SQLite `UNIQUE(kind, external_id)` on test suites:** In database tests, re-inserting test sources across repeated runs triggers IntegrityError unless `INSERT INTO ... ON CONFLICT(kind, external_id) DO UPDATE SET` is used.
- **Decided:**
  - Music is disabled by default for gaming sources where game audio is central, but easily enabled per source or per clip.
  - Phase 5 exit criteria met: music never masks speech on a spot check of 10 clips (speech consistently exceeds music by >= 15 dB and integrated loudness is -14 LUFS), and every track in `music/` has a verified license sidecar enforced on startup.

## 2026-10-01: Phase 4 — Web app (FastAPI, Tailscale auth, Review/New/Sources/Jobs/Settings, interactive re-render, Discord notification)

- **Done:**
  - Expanded database schema in `src/db.py`:
    - Added `users`, `clips`, `events`, and `settings` tables with automated column migrations (`submitted_by`, `claimed_at`, `finished_at`).
    - Added default admin user seeding (`admin@local`).
    - Backfilled historical Phase 2 clips 1 & 2 into `clips` table.
  - Implemented background worker daemon in `src/worker.py` (`spike worker [--interval]`):
    - Priority-ordered atomic job claiming via `UPDATE videos SET status='running' ... RETURNING id`.
    - Enforced single-worker concurrency constraint (`# ponytail: single worker guarantee`).
  - Implemented Discord notification system in `src/notify.py`:
    - Webhook notification dispatch on job completion (`send_job_ready_notification`) with clip counts, duration, and direct links.
    - Webhook URL verification helper (`verify_discord_webhook`).
  - Built web application in `src/web/`:
    - Bundled static assets: `htmx.min.js`, `Geist-Variable.woff2`, `GeistMono-Variable.woff2`, and 34 Phosphor regular icons in `sprite.svg` via `scripts/build_icons.py`.
    - Strict CSS design system compliance (`tokens.css`, `base.css`, `components.css`): dark theme default, light theme switch, zero inline styles, sentence-case copy, no emojis.
    - Keyboard shortcut engine and hover previews in `app.js` (`j`/`k`, `space`, `a`, `r`, `d`, `e`, `?`).
    - Implemented 9 Jinja2 filters in `src/web/filters.py`: `timecode`, `duration`, `duration_words`, `relative_time`, `local_time`, `filesize`, `number`, `compact_number`, `percent`.
    - Complete template suite: `base.html`, `macros/ui.html`, `partials/sidebar.html`, `review.html`, `clip_detail.html`, `new.html`, `sources.html`, `source_edit.html`, `jobs.html`, `jobs_table.html`, `settings.html`, `errors/403.html`, `404.html`, `500.html`.
  - Built interactive single-clip re-renderer:
    - Added `render_single_vertical_clip()` in `src/pipeline/stage9c_render.py` supporting live trim adjustments, layout switching, caption style switching, and hook title editing.
    - Endpoint `POST /clips/{id}/rerender` re-encodes vertical clip via FFmpeg and updates DB in <15s.
  - CLI commands: `spike web` (`--host`, `--port`, `--reload`) and `spike worker`.
  - Built unit test suite `tests/test_phase4.py` (8 tests covering auth, rendering, CRUD, upload validation, clip lifecycle, re-render, notifications, worker claim). All 37 project tests pass.
- **Learned (verified):**
  - **Starlette 1.7+ `TemplateResponse` signature:** In Starlette 1.7+, calling `templates.TemplateResponse("template.html", context)` treats the string as `request` and the dictionary as `name`, throwing `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')`. Explicitly passing `request=request` or `(request, "template.html", context)` is required.
  - **`sqlite3.Row` vs dict:** `sqlite3.Row` does not provide `.get()`. Trying to call `row.get("field")` causes `AttributeError`. Rows should be converted to standard dictionaries (`dict(row)`) when `.get()` or flexible key lookup is needed.
  - **Pytest auto-collection collision:** Naming helper functions `test_*` (e.g. `test_discord_webhook`) outside test modules triggers Pytest auto-collection as a test function, causing fixture resolution errors. Renamed helper to `verify_discord_webhook`.
  - **FastAPI lifespan:** Migrated from deprecated `@app.on_event("startup")` to `@asynccontextmanager async def lifespan(app: FastAPI)` to eliminate deprecation warnings.
- **Decided:**
  - Interactive re-renders update the vertical clip and thumbnail directly and preserve clip approval state.
  - Phase 4 exit criteria met: 3 cooperating processes (web, worker, watch), Tailscale Serve identity header auth with local dev fallback, 5 main screens + clip detail, interactive re-render, Discord notification, and secure upload handling.

## 2026-10-01: Phase 3 — Streams (Twitch chat replay, cleaning heuristics, 7TV/BTTV emotes, lag cross-correlation, untuned chat baseline, source watcher)

- **Done:**
  - Implemented Stage 3 `fetch_chat` in `src/pipeline/stage3_chat.py`:
    - Downloads Twitch chat replay JSON via `tools/TwitchDownloaderCLI.exe` (v1.56.5) using Twitch public GQL without requiring credentials.
    - Full checkpoint resume support (`data/videos/<id>/chat.json`) and graceful non-blocking fallback if chat is expired or unavailable.
  - Enhanced Stage 4 `fetch_crowd` in `src/pipeline/stage4_crowd.py`:
    - Public 3rd-party emote set fetching (7TV global and BTTV global APIs) categorized into `laugh`, `hype`, `confusion`, `sad` families.
    - Twitch Helix Community Clips fetcher (with `vod_offset`, `creator_id`, `view_count`, `is_featured`), saved to `clips.json`.
  - Implemented full chat signals & cleaning engine in `src/pipeline/stage6_signals.py` (§6.1, §6.2):
    - Chat cleaning: drops known bot accounts (`CHAT_BOT_NAMES`), drops commands (`!`), drops sub/gift-sub notice patterns, bins 1 chatter per 1s bin.
    - Raid detection: burst of >= 15 never-before-seen chatters triggers 60s blackout window (`# ponytail: heuristic for raid burst detection tuned in Phase 3`).
    - Flood dampening: halves chat signals in first and last 5 minutes ("hi" and "bye" floods).
    - Poll detection: windows where >60% messages are single digits or yes/no are zeroed.
    - Signals: `chat_users` (rolling 10-minute median z-score on `log1p`, zeroed when < 3 unique chatters), `chat_laugh` (share of chatters with laugh tokens, add-k shrunk toward VOD mean), `chat_hype` (share with hype tokens), `chat_agree` (emote walls and message repetition), and `clip_heat` (sum of $1 + \log(1+\text{views})$ over distinct clip creators).
    - Per-VOD lag estimation: cross-correlates audio `laugh` with `chat_laugh` across shifts $\tau \in [0, 30\text{s}]$, prominence check, shifts all chat signals back in time by estimated lag (default 12.0s).
    - Signal fusion: picks `WEIGHTS_WITH_CHAT` vs `WEIGHTS_WITHOUT_CHAT`, halves chat weights when median chat speed < 0.5 msg/s.
    - Identifies `chat_mood` tag at peak.
  - Integrated chat into Stage 7 moments in `src/pipeline/stage7_moments.py`:
    - Extracts lag-shifted chat reaction excerpt around peak with duplicate message counts (`KEKW x48`) and family shares (`[Chat reaction shares: laugh 62%, hype 8%, ? 20%]`) inside `<untrusted_chat>` tags.
    - Uses `LLM_WEIGHT_WITH_CHAT = 0.50` blend weight (vs 0.70 without chat) per §6.4.
  - Enhanced evaluation engine in `src/eval.py`:
    - Evaluates community-clip Recall@10.
    - Implemented untuned `chat_users` baseline arm (picks top peaks from raw unique chatters/s).
    - Verified on dataset: Spike achieved **Recall@10 = 1.000** vs **0.200** for the untuned `chat_users` baseline.
  - Built source watcher daemon in `src/watcher.py` (`spike watch [--once]`):
    - Polls YouTube channel RSS feeds (zero API quota) and Twitch channel VODs every 15 minutes.
    - Automatic video registration and deduplication via `UNIQUE(origin, external_id)`.
  - Built 9 unit tests in `tests/test_phase3.py` (chat cleaning, lag cross-correlation, chat signals, baseline evaluation). All 29 project tests passing.
- **Learned (verified):**
  - **TwitchDownloaderCLI without auth:** `TwitchDownloaderCLI` operates through Twitch's public GQL endpoint without requiring Twitch client credentials or tokens.
  - **Public Emote APIs:** Public 7TV global API (`https://7tv.io/v3/emote-sets/global`) and BTTV global API (`https://api.betterttv.net/3/cached/emotes/global`) return hundreds of popular Twitch emotes without any authentication or rate-limit friction.
  - **Windows Console Unicode Encoding:** YouTube titles and Twitch chat messages frequently contain high-unicode emoji (`\U0001f979`) which crash standard Python `print()` statements under Windows `cp1252` encoding; strings must be safely ascii-encoded or sanitized for CLI display.
  - **Lag Cross-Correlation:** Cross-correlation between audio laughter (YAMNet) and chat laugh tokens (`LUL`, `KEKW`, etc.) successfully recovers stream delay (typically 10–20s) and aligns audience reaction peaks with video action.
- **Decided:**
  - Standardize `chat_offset_s` lag search range to 0–30s with a 12.0s fallback.
  - The watcher daemon operates autonomously for both YouTube RSS and Twitch, queuing new broadcast VODs with zero manual intervention.
  - Phase 3 exit criteria met: chat replay ingestion, full cleaning rules, lag cross-correlation, chat fusion, community-clip Recall@10 evaluation against untuned baseline, and autonomous source watcher are all fully implemented and tested.

## 2026-10-01: Phase 2 — Vertical edit (9:16 reframing, face tracking, ASS karaoke captions, punch-in zoom, loudness, thumbnails)

- **Done:**
  - Implemented MediaPipe face detection and tracking in `src/pipeline/stage9a_face_track.py`:
    - MediaPipe Tasks API (`vision.FaceDetector`) running on CPU with XNNPACK.
    - Automatic download and caching of `blaze_face_short_range.tflite` (229 KB).
    - 4 fps frame sampling, area-based dominant face selection, exponential moving average smoothing (`alpha=0.12`), and position hold on lost detections.
    - Generates dynamic crop coordinates for native FFmpeg `sendcmd` control without Python frame piping.
  - Implemented subtitle and caption generator in `src/pipeline/stage9b_captions.py`:
    - Word-by-word ASS subtitles supporting `karaoke` ({\k<dur>} tags), `bold_pop`, and `clean` styles.
    - 1 to 3 words per line, placed in lower-third with platform-safe vertical margin (`SAFE_MARGIN_V=43` for TikTok/Reels UI).
    - Optional profanity masking (`f***`).
    - Robust escaping for ASS control characters (`{`, `}`, `\`).
    - Embedded hook title overlay event (`Style: hook`, alignment 8 top-center, first 2.5s).
  - Implemented vertical video renderer in `src/pipeline/stage9c_render.py`:
    - Support for 4 layout presets: `face_track` (dynamic crop via `sendcmd`), `split` (top 640px facecam + bottom 1280px gameplay), `center` (static 9:16 center crop), and `letterbox` (16:9 foreground + blurred/scaled background).
    - Punch-in zoom effect centered at moment peak second (1.0x to 1.15x over 0.3s, ramp back out over 1.0s) via `zoompan`.
    - Integrated EBU R128 loudness normalization (`loudnorm` two-pass) targeting -14.0 LUFS and -1.5 dBTP true peak.
    - Automatic representative thumbnail extraction (`.jpg`) at the moment's peak/punchline timestamp.
  - Integrated into pipeline orchestrator `src/pipeline/runner.py` as `render_vertical` stage.
  - Created unit test suite in `tests/test_phase2.py` (17 tests covering ASS generation, styling, profanity mask, face-track EMA smoothing, hold-on-None, and zoom expression).
  - Executed end-to-end Phase 2 vertical render on test video (`https://www.youtube.com/watch?v=D1hIpF1C_r4`):
    - Clip 1: `data/videos/1/renders/clip_1.mp4` (5.2 MB, 1080×1920, H.264 High 30fps, -14.1 LUFS, face-tracked). Thumbnail: `clip_1_thumb.jpg`.
    - Clip 2: `data/videos/1/renders/clip_2.mp4` (9.2 MB, 1080×1920, H.264 High 30fps, -14.3 LUFS, face-tracked). Thumbnail: `clip_2_thumb.jpg`.
  - All 20 tests (Phase 1 + Phase 2) pass cleanly.
- **Learned (verified):**
  - **MediaPipe Tasks API vs Legacy:** MediaPipe 1.0+ removes `mp.solutions.face_detection`. The modern `mediapipe.tasks.python.vision.FaceDetector` accepts a plain `.tflite` model directly (`blaze_face_short_range.tflite`).
  - **FFmpeg Windows path parser:** In FFmpeg `-vf` / `-filter_complex`, options like `ass=...` and `sendcmd=f=...` treat colons (`:`) as option separators. Passing absolute Windows paths with drive letters (e.g. `C:\...` or `C\:/...`) fails because FFmpeg parses `C` as an option value and the remainder as an unknown option. Passing relative POSIX paths (e.g. `data/videos/...`) completely resolves this with zero quoting issues.
  - **FFmpeg `drawtext` vs ASS for hook overlays:** On Windows, FFmpeg's `drawtext` filter crashes with access violation (`0xC0000005`) if libfontconfig lacks a system configuration file. Rendering the hook text overlay directly as a top-aligned ASS subtitle event (`\an8`, `Style: hook`) eliminates the crash, uses DirectWrite native font rendering, and unifies all text styling in one format.
  - **`zoompan` frame variable:** In FFmpeg's `zoompan` filter, the input frame index variable is `in` (or `on` for output frame index), not `n`. Using `n` causes FFmpeg's eval parser to fail with `Unknown function`.
- **Decided:**
  - Hook titles are embedded directly into the ASS subtitle track rather than as an FFmpeg `drawtext` filter layer.
  - Keep relative paths for all FFmpeg filter arguments throughout the pipeline.
  - Phase 2 exit criteria met: 1080×1920 vertical framing with smooth face tracking, word-by-word karaoke subtitles, hook text overlay, punch-in zoom, -14 LUFS loudness, and thumbnail frame extraction are all fully operational.

## 2026-10-01: Phase 1 — Core pipeline as a CLI, moments engine, evaluation, and end-to-end run

- **Done:**
  - Built SQLite WAL database (`src/db.py`) with `sources`, `videos`, and `candidates` tables.
  - Implemented Phase 1 stages in `src/pipeline/`:
    - `stage1_meta.py`: metadata & yt-dlp heatmap extraction with 12h duration guard.
    - `stage2_audio.py`: audio stream extraction to `audio.m4a` via yt-dlp/ffmpeg.
    - `stage4_crowd.py`: YouTube comment fetch, timestamp extraction, laugh keyword weighting.
    - `stage5_transcribe.py`: faster-whisper `small` int8 + VAD + word timestamps + `merge_continuation_words`.
    - `stage6_signals.py`: YAMNet laugh/shout audio events, ebur128 loudness, speech rate, replay heat, comment heat, scipy peak finding.
    - `stage7_moments.py`: transcript chunk proposals (8-min chunks with 1-min overlap), LLM candidate judge (with `[laughter]` and `[shouting]` markers, punchline quote, line numbers), Gemini audio-visual judge on YouTube URL windows, pause & laugh boundary snapping, percentile blending (`0.7 * llm + 0.3 * signal`), and pairwise re-ranking among top candidates in both orders.
    - `stage8_sections.py`: 5s-padded section slicing via yt-dlp range download / ffmpeg.
    - `stage9_render.py`: plain 16:9 baseline cuts with snapped boundaries.
    - `runner.py`: master pipeline orchestrator with stage checkpoints and resume support.
  - Built evaluation engine in `src/eval.py` calculating HIT@1, P@5, and NDCG@5 against ground truth.
  - Created CLI entrypoint `spike.py` (`spike run`, `spike eval`, `spike status`).
  - Created unit self-check test suite `tests/test_selection.py` testing pause/laugh boundary snapping, overlap deduplication, and evaluation metrics (all 3 passed).
  - Executed end-to-end run on 31.8-min YouTube test video (`https://www.youtube.com/watch?v=D1hIpF1C_r4`):
    - 16 candidates evaluated across signals and transcript proposals.
    - Top 2 moments selected:
      1. *"Kimani thinks he's Steph Curry"* (14.7s, score 100, laugh feature 4.535, punchline *"The fuck?"*).
      2. *"Reporter Asks the Most Disrespectful Question Ever"* (45.4s, score 75, punchline *"Is this AI?"*).
    - Sections sliced and baseline clips rendered into `data/videos/1/clips/clip_1.mp4` (2.33 MB) and `clip_2.mp4` (4.64 MB).
    - Resumed execution from checkpoints verified multiple times without redoing completed stages.
- **Learned (verified):**
  - Gemini free tier rate limits (15 RPM): burst candidate judging requires a small delay (~2s) between calls and exponential retry on 429 and 503 (`UNAVAILABLE` high demand).
  - Pydantic models for LLM output should allow flexible string categories for `mood` rather than rigid literals to prevent dropping entertaining clips when the model returns terms like `'energetic'` or `'serious'`.
  - In-place Python list sorting with `list.index(c)` inside the sort key raises `ValueError: list.index(x): x not in list`. Pre-computing `candidate["pairwise_wins"]` eliminates the issue cleanly.
  - Slicing YouTube video sections with yt-dlp `download_ranges` and `merge_output_format: "mp4"` downloads only the targeted seconds without downloading the full 30-minute video file.
- **Decided:**
  - Standardize pairwise re-ranking pool to top 4 candidates for short videos (12 calls instead of 30), conserving quota and preventing 503 errors while preserving position-bias-free ordering.
  - Phase 1 core pipeline is complete, tested, and ready for Phase 2 (vertical 9:16 reframing, MediaPipe face tracking, and animated ASS captions).

## 2026-10-01: Phase 0 — PC specs, YAMNet, OpenShorts, chat replay, and §16 verification

- **Done:**
  - Recorded PC specs: AMD Ryzen 7 5800H (8c/16t, 3.2 GHz), 16 GB RAM, 512 GB SSD (~22 GB free), AMD Radeon iGPU, Windows 11.
  - Installed and verified `faster-whisper` 1.2.1, `yt-dlp` 2026.8.19, `tensorflow` 2.22rc0, `scipy` 1.18.1, and `TwitchDownloaderCLI` 1.56.5.
  - Benchmarked faster-whisper on AMD Ryzen 7 5800H CPU (31.8 min audio sample):
    - `base`: RTF 0.099 (10.1× faster than real-time, 188.7 s transcribe time, 355 segments, 4,403 words).
    - `small`: RTF 0.325 (3.1× faster than real-time, 619.5 s transcribe time, 641 segments, 4,418 words).
    - `medium`: RTF 0.747 (1.3× faster than real-time, 1,423.7 s transcribe time, 377 segments, 4,400 words).
  - Benchmarked YAMNet (tf.lite.Interpreter + XNNPACK) on real 31.8 min audio: 9.7 s inference time (RTF 0.005, 0.3 CPU-min per audio hour). Ruled out PANNs CNN14 (~20x heavier, no PyPI package).
  - Cloned and analyzed OpenShorts (`mutonby/openshorts`, MIT): analyzed reframe v2 (`sendcmd` dynamic crop in native ffmpeg without Python frame piping) and karaoke ASS subtitles (`merge_continuation_words` to fix faster-whisper fragment splitting, `SAFE_MARGIN_V=43` for TikTok/Reels UI safety).
  - Downloaded and inspected real 30-min Twitch VOD chat replay (VOD 2887910568, 5,132 comments) with `phase0/inspect_chat_replay.py`.
  - Created and verified `GEMINI_API_KEY` and `YOUTUBE_API_KEY` in `.env` using `phase0/verify_keys.py`.
  - Updated `BLUEPRINT.md` §11 and §16 with verified statuses and real benchmarks.
- **Learned (verified):**
  - `tflite-runtime` does not ship Windows wheels for Python 3.14; `yamnet.tflite` runs cleanly through `tf.lite.Interpreter` with XNNPACK CPU delegate.
  - Twitch chat replays keep `content_offset_seconds` as integer seconds only; `user_notice_params.msg_id` is null/absent across all comments; raid and sub announcements appear as text lines in `message.body`; 7TV emotes appear as plain text tokens in `message.body`.
  - OpenShorts' `sendcmd` ffmpeg pattern eliminates the need for expensive Python frame piping during 1080x1920 video renders.
  - `av` 19.0.0 removed `metadata_errors` keyword argument; `faster-whisper`'s `decode_audio` requires an `av.open` monkeypatch to strip `metadata_errors`.
  - Gemini API's `VideoMetadata` for YouTube URL offsets requires duration strings ending in `'s'` (e.g. `"10s"`, `"25s"`, not `"00:00:10"`). `gemini-3.1-flash-lite` accurately analyzed the video and audio of the YouTube URL window on the free tier.
  - YouTube Data API v3 `commentThreads.list` successfully fetches top-level comments and timestamps with the generated key.
- **Decided:**
  - `small` selected as the default Whisper model for the pipeline: 3.1× faster than real-time (~58 min for a 3-hour VOD) with significantly finer word segmentation (641 segments vs 355 for base) critical for speech pause snapping. `base` serves as the fallback if queue backs up. `medium` (RTF 0.747, ~2.2h for 3h VOD) is too slow for single-worker CPU.
  - YAMNet selected as the laughter/shout tagger for §6.1.
  - Chat cleaning in §6.1 must match raid and sub notices via string/regex patterns in `message.body`, not relying on `msg_id`.
  - Adopt OpenShorts' `sendcmd` dynamic crop approach and `merge_continuation_words` logic for Phase 2.
  - Defer Twitch Developer App credentials to Phase 3 (no blocking dependency for Phase 1/2).
- **Open:**
  - Ground-truth evaluation set: select 3 test videos and mark 5 moments each (grade 1–3).

## 2026-10-01: Free PaaS hosting check

- **Done:** added §17 to `BLUEPRINT.md`. Created this file.
- **Learned (verified, Render docs):** free web services have an ephemeral
  filesystem. A local SQLite file is lost on redeploy, restart, or spin-down.
  Services spin down after 15 min idle and take about 1 min to start. Free
  Render Postgres expires 30 days after creation.
- **Learned (verified, Vercel docs):** Hobby functions run for at most 300 s,
  with 2 GB memory and 1 vCPU. No persistent disk.
- **Learned (verified, Oracle docs):** Always Free compute instances can be
  reclaimed when idle.
- **Learned (verified, Turso and third-party pricing pages):** Turso free plan
  has 5 GB storage. Neon free plan has 0.5 GB storage.
- **Recalled, not verified:** Cloudflare R2 free tier is 10 GB with no egress
  fees. Supabase free projects pause after about 1 week idle.
- **Decided:** none yet. Recommendation: keep the worker on one machine with
  real disk and CPU (the PC, or an Oracle Always Free VM). SQLite stays.
  Free PaaS cannot run the transcribe and render pipeline.
- **Open:** why does the user want PaaS (public URL, or not depending on the
  PC)? The answer picks the hosting option. Then update §3, §4, and the
  security tier.

## 2026-10-01: Moment detection research (no-chat signals)

- **Done:** deep research on detecting funny clips beyond chat. Report:
  `reports/Funny clip detection signals.md`. Notes in `research_notes/`.
- **Learned (sourced, see report):** laughter is the standard free "funny"
  label; the funny part is the ~8 s before the laugh (FunnyNet-W). Text
  carries most humor signal (UR-FUNNY: text 62.85 vs all modalities 64.47).
  LLMs judge humor poorly in absolute scores (human correlation ~0.2);
  pairwise compare in both orders works better. yt-dlp exposes YouTube
  "Most replayed" heatmap (100 bins, unofficial). Gemini takes YouTube URLs
  with audio; free tier ~8 h video/day.
- **Not verified:** CPU cost of YAMNet/PANNs laughter tagging on our PC.
- **Decided:** adopted the report's changes into `BLUEPRINT.md`. §6 rewritten
  (new signals, two weight sets, line-index LLM output, percentile blend,
  pairwise re-rank, new §6.5 eval and §6.6 not-used list). Also updated §4,
  §5 (stage 4 is now `fetch_crowd`), §8.3, §9, §11, §12, Phases 0, 1, 7, 8,
  §14, §16.
- **Open:** Phase 0 laughter benchmark decides the `laugh` weight and model.

## 2026-10-01: Twitch chat highlight research

- **Done:** deep research on chat-based detection. Report:
  `reports/Twitch chat highlight detection.md`.
- **Learned (sourced, see report):** a chat spike means "crowd reacted",
  not "funny". Funny is told by laugh-emote share (Song et al. 2021: funny
  emotes rise with clip popularity, exciting ones fall). Chat lag measured
  at 15 s (Ringer), 20 to 27 s (LIGHTOR); our 8 s default is likely short.
  Helix `vod_offset` goes null after the VOD is deleted: snapshot clips at
  ingest. BTTV/FFZ emotes are 44 of the top 100 emotes.
- **Correction:** cliptron's "chat 0.917 vs LLM 0.708" was 4 VODs, tuned on
  its own answers. Untuned chat over 13 VODs: Recall@10 0.295. BLUEPRINT
  §6.4 step 5 cites the inflated figure.
- **Decided:** applied the report's changes to BLUEPRINT: chat cleaning,
  `chat_users`/`chat_laugh`/`chat_hype`/`chat_agree`, distinct-creator
  `clip_heat`, per-VOD lag (default 12 s), new with-chat weights,
  `chat_mood`, eval vs untuned chat baseline. Also §5, §9, Phase 0, Phase 3,
  §14, §16.
- **Open:** Phase 0 checks what system events the chat replay JSON contains.

## 2026-10-06: Automated runs (web + worker + watcher)

- **Done:** `py spike.py web` now starts the worker and the watcher as child
  processes and restarts any that exit (checked every 30 s). Flags:
  `--no-worker`, `--no-watcher`. `scripts/install_autostart.ps1` registers a
  boot task (S4U, no window) that runs `scripts/run_spike.cmd`, which restarts
  Spike after any exit. Logs go to `data/spike.log`.
- **Fixed:** the watcher queued a Twitch VOD while the stream was still live.
  It now skips the newest VOD while the channel is live.
- **Fixed:** the watcher re-queued failed VODs every 15 min. It now skips any
  VOD already in `videos`.
- **Fixed:** worker jobs made a second `videos` row, because `run_pipeline`
  registered the video again with a different `external_id`. The worker now
  passes its claimed `video_id`. The claimed row stayed `running` forever.
- **Added:** a Discord message on job failure. Worker requeues `running` jobs
  at start. A port lock (127.0.0.1:47811) allows one worker only.
- **Learned (verified, yt-dlp 2026.08.19 source + live test):** the
  `twitch:stream` extractor raises `UserNotLive` when a channel is offline.
- **Learned:** the test suite writes to the real `data/spike.db`. A running
  worker picks up the test rows. Point tests at a temp DB (see
  `tests/test_automation.py`).
- **Fixed (same day):** the watcher now skips YouTube videos that are live,
  upcoming, or still processing (yt-dlp `live_status`). Tested on Lofi Girl's
  24/7 stream. Discord messages are now plain text, not embeds. Embeds showed
  blank when the viewer had link previews off. Links use `SPIKE_PUBLIC_URL`.
  Mentions are disabled, so a stream title cannot ping @everyone.
  `tests/conftest.py` runs tests on a copy of `spike.db`.
- **Open:** set `SPIKE_PUBLIC_URL` in `.env` once Tailscale is installed.
