# Spike: Blueprint

A self-hosted service that turns long videos and Twitch streams into finished
vertical shorts (YouTube Shorts, TikTok, Instagram Reels). A user picks a
streamer or submits a video. The service finds the entertaining moments, cuts
them, reframes them to 9:16, adds captions, music, and effects, and hands back
finished clips. Posting is optional and uses the official platform APIs.

**Status:** planning. No code written yet.
**Audience:** Nicholas and a small team (known people, no public sign-up).
**Runs on:** one small PC. GPU optional.
**Budget:** $0 by default. Every paid service is optional.
**Security tier:** T2, Internal/Team. See Phase 8.
**Scaling:** not applicable. The user base is small and fixed, and the service
runs on one machine. Re-check if it opens to outside creators (see §12).

---

## Contents

1. The problem and the goal
2. Constraints
3. Architecture
4. Tech stack and cost
5. The pipeline, stage by stage
6. Moment detection (the core)
7. Editing: layout, captions, music, effects
8. Posting
9. Data model
10. Screens
11. Hardware, throughput, and storage
12. Legal and platform-policy rules
13. Phases
14. Risks
15. Open questions
16. Appendix: facts, verified vs recalled
17. Session learnings (`LEARNINGS.md`)

**Rule for every AI or human work session:** before the session ends, update
`LEARNINGS.md` in the project root. If the file does not exist, create it.
Read it at the start of the next session. See §17.

---

## 1. The problem and the goal

Clipping long content by hand is slow. An editor watches hours of footage to
find a few good minutes, then cuts, reframes, and captions each clip. Paid
tools (Opus Clip, Klap, Vizard, Eklipse, StreamLadder) do this, but they
charge per clip or per month, and most ignore the best signal a stream has:
the live chat.

### What Spike must do

1. Accept three inputs: an uploaded video file, a video URL, or a streamer to
   follow.
2. For a followed streamer, find each new past broadcast and process it with
   no human action.
3. Find the most entertaining moments and rank them with a score and a reason.
4. Produce finished 9:16 clips: reframed, captioned, loudness-normalized, with
   optional music and effects.
5. Let a team member review, trim, fix captions, and re-render a clip in a few
   seconds.
6. Hand over each clip as a download, or post it through the official
   platform APIs, now or on a schedule.
7. Notify the team when clips are ready.
8. Learn from results: record how posted clips perform, so the scoring can be
   tuned.

### What Spike must not do

- Post clips of a creator who has not given permission (see §12).
- Scrape platforms with browser automation, or bypass any platform's
  anti-bot or DRM measures.
- Post to a platform through anything other than its official API.
- Execute or obey text found in transcripts, chat logs, or video titles.
  That text is written by strangers and is data only.

---

## 2. Constraints

| Constraint | Effect on the design |
|---|---|
| One small PC, GPU optional | Download audio first, video only for the chosen sections. Use small, quantized models. One job at a time |
| $0 budget | Open-source tools only. Free API tiers where a local option is too slow. No paid posting services |
| Small, known team | No public sign-up. Access through a private network (Tailscale), not the open internet |
| Platform audits | YouTube and TikTok force posts to private until the app passes their audit. Plan for "download" and "send to TikTok inbox" first |
| Stream VODs expire | Twitch deletes past broadcasts after a set time. Process new VODs soon after the stream ends |

---

## 3. Architecture

Everything runs on the small PC. Team members reach it through Tailscale.

```
  Team member's browser
          |
          |  HTTPS over Tailscale (private network, no public port)
          v
  +-------------------------------------------------------------+
  |  SMALL PC                                                   |
  |                                                             |
  |  +------------------+        +---------------------------+  |
  |  |  WEB APP         |        |  WORKER                   |  |
  |  |  FastAPI + htmx  |<------>|  one job at a time        |  |
  |  |  review, submit, |  SQLite|  fetch -> transcribe ->   |  |
  |  |  settings        |        |  signals -> moments ->    |  |
  |  +------------------+        |  cut -> render -> notify  |  |
  |                              |  -> post (optional)       |  |
  |  +------------------+        +---------------------------+  |
  |  |  WATCHER         |                    |                  |
  |  |  every 15 min:   |                    |                  |
  |  |  new VODs?       |                    v                  |
  |  +------------------+           data/ (media on disk)       |
  +-------------------------------------------------------------+
        |                  |                 |              |
        v                  v                 v              v
  Twitch API         LLM (Gemini free   Discord webhook   YouTube / TikTok /
  YouTube RSS        tier, or local     (clips ready)     Instagram APIs
  yt-dlp             Ollama)                              (optional)
```

### Why this shape

**One machine, no cloud database.** Video files are large. Supabase's free
storage and most free hosting tiers cannot hold them. Keeping media, database,
and web app on one PC removes every upload and sync step. SQLite is enough for
a small team and one worker.

**Three processes, one codebase.** The web app, the worker, and the watcher
are separate processes so a long render never blocks the web page. They share
one Python package and one SQLite file. No Redis, no Celery. The `videos`
table is the job queue.

**Tailscale, not a public URL.** The web app never listens on the public
internet. Only devices on the team's tailnet can reach it. This removes most
of the attack surface a T2 app must otherwise defend, and Tailscale supplies
the login (see §4, "Auth").

**Audio first.** A 3-hour 1080p60 VOD at 6 Mbps is about 8 GB
(6 Mbps x 10,800 s / 8). Its audio-only stream is about 200 MB. Spike analyzes
the audio, picks the moments, and then downloads video only for those
sections. This is the single biggest saving on a small PC.

**One LLM client, swappable backend.** Gemini, Ollama, and Anthropic all offer
an OpenAI-compatible chat endpoint. Spike calls one endpoint with `httpx` and
reads the base URL, key, and model name from settings. Changing provider is a
settings change, not a code change.

### Known single point of failure

The PC. If it is off, asleep, or out of disk, nothing runs. The watcher
catches up on missed VODs when the PC comes back, as long as Twitch has not
deleted them yet. Phase 7 adds a "no heartbeat" alert.

---

## 4. Tech stack and cost

Licenses and prices below are from memory unless §16 marks them verified.
Phase 0 confirms each one before it is installed.

| Layer | Choice | Cost | Why |
|---|---|---|---|
| Language | Python 3.12 | Free | Every video and ML library needed is Python-first |
| Web app | FastAPI + Jinja2 templates + htmx | Free | Server-rendered pages. No Node build step, no separate frontend project |
| Database | SQLite (WAL mode) | Free | One file, one machine, small team |
| Job queue | The `videos` table in SQLite | Free | One worker. A second queue system adds nothing |
| Download | yt-dlp | Free | Handles Twitch VODs, YouTube, and many other sites. Supports audio-only formats and section downloads |
| Twitch data | Twitch Helix API (app access token) | Free | New VODs per streamer, community clips with view counts |
| Twitch chat replay | TwitchDownloaderCLI (`chatdownload`) | Free | No official API exists for VOD chat. This uses Twitch's internal API and can break (see §14) |
| YouTube data | Channel RSS feed + yt-dlp | Free | New uploads per channel with no API key |
| Transcription | faster-whisper, int8, word timestamps, VAD filter | Free | Runs on CPU. Word timestamps drive both cutting and captions |
| Audio features | ffmpeg `ebur128`/`astats` + numpy | Free | Loudness per second |
| Audio events | YAMNet (Apache-2.0), TFLite build (recalled, verify); PANNs CNN14 as fallback | Free | Laughter and shout tags per second on CPU. Phase 0 picks one by benchmark |
| Peak picking | `scipy.signal.find_peaks` | Free | Height, distance, and prominence in one call |
| YouTube crowd data | yt-dlp `heatmap` field + YouTube Data API `commentThreads.list` (API key) | Free | "Most replayed" and timestamped comments stand in for chat on YouTube |
| Scene cuts | PySceneDetect (on downloaded sections only) | Free | Keeps clip edges off mid-shot cuts |
| LLM | Gemini API free tier (default), Ollama local (fallback) | Free | Gemini handles long transcripts fast, and can judge YouTube windows with audio and video (§6.3). Ollama keeps everything local but is slow on CPU and a weak humor judge |
| Face tracking | MediaPipe face detection | Free | Fast on CPU. Avoid Ultralytics YOLO: recalled as AGPL-3.0 |
| Render | ffmpeg (libx264, or Intel QSV / NVENC if present) | Free | One ffmpeg command per clip |
| Captions | ASS subtitle files, burned in by ffmpeg (libass) | Free | Word-by-word highlight styles without a browser renderer |
| Music | Local folder of licensed tracks | Free | YouTube Audio Library, Pixabay Music. See §12 |
| Notifications | Discord webhook | Free | One HTTP POST. The team already reads Discord, or use Telegram |
| Private access and auth | Tailscale (`tailscale serve`) | Free plan | Private HTTPS, SSO login with 2FA, identity headers per request |
| Posting | YouTube Data API, TikTok Content Posting API, Instagram Graph API | Free | Official APIs only. Audits apply (§8) |

### Auth

`tailscale serve` puts the app behind HTTPS on the tailnet and, per request,
adds headers that name the Tailscale user (recalled: `Tailscale-User-Login`,
verify in Phase 0). Spike trusts those headers **only** on requests that come
from the local `tailscale serve` proxy. The app binds to `127.0.0.1`, so no
other client can reach it to forge the header. The login address must also be
in the `users` table, so a person on the tailnet who is not a team member
still gets a 403.

Fallback if the header approach fails verification: email + password, hashed
with argon2, accounts created by an admin CLI command. No self sign-up.

### Upgrade paths (not built now)

- **Faster transcription:** Groq's hosted Whisper free tier (recalled), or any
  NVIDIA GPU with faster-whisper on CUDA.
- **Better scoring:** point the LLM settings at Claude (Anthropic's
  OpenAI-compatible endpoint). Paid. Claude Haiku 4.5 is the low-cost option.
- **Fancy animated captions:** Remotion. Check its license terms first
  (recalled: free for individuals and small companies).

---

## 5. The pipeline, stage by stage

Each video moves through fixed stages. Each stage writes its output to
`data/videos/<id>/`. If the worker crashes, it restarts the video at the first
stage whose output file is missing. No stage runs twice.

| # | Stage | Input | Output file | Notes |
|---|---|---|---|---|
| 1 | `fetch_meta` | URL, upload, or VOD id | `meta.json` | Title, duration, channel, and yt-dlp's `heatmap` when present. Reject over the max duration (default 12 h) |
| 2 | `fetch_audio` | URL | `audio.m4a` | yt-dlp audio-only format. For uploads, ffmpeg extracts audio |
| 3 | `fetch_chat` | Twitch VOD id | `chat.json` | Twitch only. Skipped for other sources |
| 4 | `fetch_crowd` | Twitch VOD id or YouTube id | `clips.json` or `comments.json` | Twitch: Helix Get Clips for the broadcaster in the VOD's time range, saved at once with `vod_offset`, `creator_id`, `view_count`, and `is_featured` (`vod_offset` turns null after the VOD is deleted). Also fetches the channel's BTTV/FFZ/7TV emote names. YouTube: `commentThreads.list`, top 10 pages (1 quota unit each). Skipped for uploads |
| 5 | `transcribe` | `audio.m4a` | `transcript.json` | Word-level. Language auto-detected, or fixed per source |
| 6 | `signals` | audio, chat, clips, comments, heatmap | `signals.npz` | Per-second series (§6.1), including one YAMNet pass over the audio |
| 7 | `moments` | signals, transcript | rows in `candidates` | Peaks and transcript proposals, LLM judge, optional Gemini judge, pairwise re-rank (§6.2 to §6.4) |
| 8 | `fetch_sections` | chosen candidates | `sections/<cand>.mp4` | yt-dlp `--download-sections` with 5 s padding each side. Uploads skip this |
| 9 | `render` | sections, transcript | `clips/<clip>.mp4`, thumbnail | Layout, captions, music, effects, loudness (§7) |
| 10 | `notify` | clips | Discord message | Count, top score, link to the review page |
| 11 | `post` | approved clips | rows in `posts` | Only if the source's posting rule allows it (§8) |

### Job states

`queued -> running(stage) -> ready -> done` or `failed(stage, error)`.

- `ready` means clips are rendered and waiting for review.
- `done` means every clip is approved, rejected, or posted.
- A failed stage retries twice with backoff (30 s, 5 min), then stays
  `failed` with the error shown in the Jobs screen and a Retry button.
- One network failure (a chat download, a community-clips call) never fails
  the whole job. The stage records the gap, and moment detection runs on the
  signals it has.

### Worker loop

```
loop:
  claim = UPDATE videos SET status='running', claimed_at=now
          WHERE id = (SELECT id FROM videos WHERE status='queued'
                      ORDER BY priority DESC, created_at LIMIT 1)
          RETURNING id
  if none: sleep 10 s, continue
  run stages in order, skipping any with existing output
```

One worker, one job at a time. Mark this in code with a `ponytail:` comment:
a second worker needs a row-level claim check and more RAM than a small PC
has.

### Watcher

Every 15 minutes, for each source with `auto_process = true`:

- **Twitch:** Helix Get Videos (`type=archive`) for the broadcaster. Any VOD
  not already in `videos` and not still live gets queued.
- **YouTube:** fetch the channel's RSS feed. New video ids get queued.

The unique index on `videos(origin, external_id)` stops duplicates, even if
two watcher runs overlap.

---

## 6. Moment detection (the core)

This is the part that decides whether Spike is worth using. Everything else is
plumbing that open-source tools already solve.

**Research basis:** `reports/Funny clip detection signals.md` and
`reports/Twitch chat highlight detection.md` (2026-10-01). Four findings
shape this section:

- **Laughter means "funny". Loudness only means "loud".** Humor datasets use
  laughter as their label. The funny part is the setup in the seconds
  *before* the laugh.
- **The transcript holds most of the humor, but LLMs judge it poorly on
  their own.** LLM funniness ratings correlate with human ratings at about
  0.2. So signals propose candidates, and the LLM judges short windows. The
  LLM never hunts across hours alone.
- **On YouTube, viewers already marked the moments.** The "Most replayed"
  heatmap marks replays. Timestamped comments ("2:34 lmao") mark jokes.
- **A chat spike means "something happened", not "something was funny".**
  The spike says *when* the crowd reacted. The emote family says *how*:
  laugh emotes mark the funny ones. Chat also arrives 10 to 20 s late.

Two paths, one pipeline:

- **Streams (Twitch VODs):** chat, community clips, and audio events find
  candidate peaks. The LLM judges and trims them.
- **Uploads and URLs with no chat:** audio events (laughter, shouting),
  loudness, and YouTube crowd signals find candidate peaks. The LLM also
  reads the transcript in chunks and proposes moments. Both sets become
  candidates. Public YouTube URLs also get an optional audio-visual judge
  (§6.3).

### 6.1 Signals (per second of the VOD)

**Clean chat first.** Raids, sub trains, bots, and greetings make spikes that
are not reactions to content. Before any chat signal is computed:

- Drop messages from the bot list in `settings` (Nightbot, StreamElements,
  Moobot, Fossabot, and per-source bots).
- Drop messages that start with `!`, and messages with a non-null
  `user_notice_params.msg_id`. Also drop sub and gift-sub text patterns,
  because a known bug left `msg_id` null in some replays.
- Count each user once per 1 s bin.
- Raids: a burst of chatters never seen before in this VOD. Zero all chat
  signals for 60 s after one. Mark this rule with a `ponytail:` comment: it is
  a heuristic, tuned in Phase 3.
- Halve chat signals in the first and last 5 minutes ("hi" and "bye" floods).
- Polls: windows where most messages are a digit, "yes", or "no" are zeroed.

| Signal | Source | How it is computed |
|---|---|---|
| `chat_users` | cleaned chat | Unique chatters per second, smoothed over 5 s, z-scored on `log1p` against a rolling 10-minute median (it follows viewer growth). Zero in any window with fewer than 3 unique chatters, so a tiny chat cannot fake an eruption |
| `chat_laugh` | cleaned chat | Share of unique chatters posting a laugh token, smoothed over 5 s, shrunk toward the VOD mean when few people chat (add-k). Laugh tokens: `LUL`, `LULW`, `KEKW`, `KEKL`, `OMEGALUL`, `ICANT`, `pepeLaugh`, `lol`, `lmao`, `xd`, `💀`, `😂`, and other languages (`jaja`, `kkkk`, `rsrs`, `555`, `ㅋㅋㅋ`, `www`, `wkwk`) |
| `chat_hype` | cleaned chat | Same as `chat_laugh`, for hype only: `Pog`, `PogChamp`, `POGGERS`, `W`, `EZ`, `Clap`, `NO WAY` |
| `chat_agree` | cleaned chat | Share of messages equal to the most common message in the window (emote walls, `?????` floods), smoothed over 5 s |
| `clip_heat` | community clips | For each second, the sum over *distinct clip creators* covering it of `1 + log(1 + views)`. Many people clipping one moment means the crowd agreed. Views only mean the clip travelled |
| `laugh` | audio | Per-second max YAMNet probability over the laughter classes (Laughter, Giggle, Snicker, Belly laugh, Chuckle). Counts only when the run lasts 0.5 s or more and transcript words fall within 3 s of it. The gate drops canned meme laughs played over silence |
| `shout` | audio | Same as `laugh`, for Shout, Yell, Screaming, and Whoop |
| `audio_loud` | audio | Short-term loudness (LUFS) per second from ffmpeg `ebur128`. Fires on explosions and music as readily as on jokes, so it is a minor signal |
| `speech_rate` | transcript | Words per second, smoothed over 5 s. Fast speech often means excitement |
| `replay_heat` | YouTube heatmap | yt-dlp's `heatmap` field from `meta.json`: 100 equal bins, value 0 to 1, held flat across each bin. Zero for the first 60 s, because the heatmap always peaks at the start. Absent on Twitch and on low-view videos |
| `comment_heat` | YouTube comments | Timestamps parsed from top-level comments. Weight 2 when the comment matches the laugh list (`lol`, `lmao`, `dead`, `💀`, `😂`, and per-source terms), else 1. Smoothed over 5 s |

Mark the `laugh` gate in code with a `ponytail:` comment: it is a heuristic,
tuned in Phase 0 against a real VOD.

Token lists live per source (`sources.chat_tokens`), grouped into `laugh`,
`hype`, `confusion` (`?`, `WutFace`, `monkaS`), and `sad` (`Sadge`, `F`,
`o7`). Third-party emotes are loaded per channel from the BTTV, FFZ, and 7TV
public APIs: they are 44 of the top 100 emotes on Twitch. Emote names appear
in plain message text, so name matching is enough. "Clip it" messages are
logged as a feature only.

**Normalize per VOD.** Convert each series to a robust z-score:
`(x - median) / (1.4826 * MAD)`. One streamer's chat runs at 2 messages per
second, another's at 200. The z-score makes both comparable.

**Shift chat back in time.** Chat reacts after the event. Stream delay adds
more. Measured lags are 15 s and 20 to 27 s in esports studies. Estimate the
lag per VOD: cross-correlate `chat_laugh` with the audio `laugh` series over
shifts of 0 to 30 s. Use the best shift when its peak is clear. Otherwise use
the source's last estimate, otherwise the default `chat_offset_s` (12 s).
Store the result on `videos.chat_offset_s` and shift every chat signal by it.
Do not shift `clip_heat` (clips carry their own offset) or comment timestamps
(viewers type the time of the punchline).

**Fuse.** Two weight sets, picked by whether the VOD has chat:

```
with chat:    hype(t) = 0.20 * chat_users + 0.20 * chat_laugh + 0.20 * clip_heat
                      + 0.15 * laugh + 0.05 * chat_hype + 0.05 * chat_agree
                      + 0.05 * audio_loud + 0.05 * shout + 0.05 * speech_rate

without chat: hype(t) = 0.30 * laugh + 0.25 * replay_heat + 0.15 * comment_heat
                      + 0.15 * audio_loud + 0.10 * shout + 0.05 * speech_rate
```

Weights live in `settings`. Missing signals get weight 0 and the rest are
rescaled to sum to 1. Small chats cannot spike meaningfully: when a VOD's
median is under 0.5 cleaned messages per second, halve all chat weights
before the rescale. These starting weights are still guesses. §6.5 replaces
them with fitted ones.

### 6.2 Candidate peaks

1. Smooth `hype(t)` over 10 s.
2. Find peaks with `scipy.signal.find_peaks`: `height` = `peak_threshold`
   (default z = 2.0), `distance` = 60 s, `prominence` = 1.0. Prominence stops
   a flat plateau from producing several peaks.
3. Take the top `3 x target_clip_count`.
4. For each peak at time `p`, the context window is `[p - 60, p + 30]`. The
   default clip window is `[p - 25, p + 10]`. When `laugh` is the largest
   term in `hype(p)`, the clip window is `[p - 30, p + 8]`, because the setup
   comes before the laugh.
5. Tag each candidate. `chat_mood` is the dominant token family at the peak
   (`laugh`, `hype`, `confusion`, `sad`, or null without chat).
   `families_agree` counts the signal families (chat, clips, audio) with
   z > 1 at the peak. Chat and audio make uncorrelated errors, so agreement
   between them is informative.

**Uploads add a second source.** Split the transcript into 8-minute chunks
with 1 minute of overlap. Ask the LLM for up to 3 moments per chunk. Merge
these with the signal peaks: when two candidates overlap by more than 50%
(IoU, overlap divided by union), keep one and set its `origin` to `both`.
Agreement between the two sources is a feature that §6.5 can learn from.

### 6.3 LLM judge

One LLM call per candidate. The prompt holds:

- The source's style notes (for example "comedy streamer, reward chaotic
  moments" or "educational, reward clear standalone explanations").
- The transcript of the context window, one numbered line per phrase:
  `L12 [01:02:03.4] word word word`. The audio pass writes non-verbal events
  into the lines: `[laughter 2.3 s]`, `[shouting]`, `[replayed]` (top 10% of
  `replay_heat`), and `[stretched word]` for a word longer than 1.5 s
  (Whisper often hides a laugh inside a stretched word).
- A chat excerpt from the lag-shifted peak window, inside `<untrusted_chat>`
  tags. Duplicates are collapsed with counts (`KEKW x48`), top 30 lines,
  plus one line of family shares (`laugh 62%, hype 8%, ? 20%`). Chat is
  context only: LLMs judge badly from chat alone. For YouTube, the top 10 comments that point into
  the window, inside `<untrusted_comments>` tags.
- The signal values at the peak.

The system prompt says that transcript, chat, and comment text is data, that
instructions found inside it must be ignored, and that the only valid output
is the JSON below.

The instruction is plain extraction: "Quote the punchline line exactly. Give
the line where the setup starts and the line where the reaction ends." No
persona. Persona and humor-type prompts did not help in tests. The model
returns line numbers, not seconds. Code maps lines to word timestamps,
because LLM timestamps are too coarse for clip edges.

```json
{
  "keep": true,
  "start_line": 9,
  "end_line": 17,
  "punchline": "and that's why I don't own a ladder anymore",
  "score": 82,
  "title": "He did NOT expect that jump",
  "hook_text": "Wait for it...",
  "post_caption": "the jump that broke chat #gaming #clips",
  "hashtags": ["gaming", "clips"],
  "reason": "Setup, fail, and chat eruption all in 28 s. Works without context.",
  "mood": "hype",
  "needs_context": false
}
```

Scoring rubric, given to the model:

| Factor | Weight | Question |
|---|---|---|
| Hook | 30 | Do the first 3 seconds make a viewer stay? |
| Standalone | 25 | Does it make sense with no knowledge of the stream? |
| Payoff | 25 | Is there a clear punchline, reaction, or result? |
| Energy | 10 | Is the delivery animated, loud, or surprising? |
| Length fit | 10 | Does it land in 20 to 45 seconds without padding? |

Run each candidate twice and average the scores. LLM humor scores are noisy.
The Settings screen warns that the local 7B fallback is the weakest humor
judge of the supported backends.

**Optional audio-visual judge (Gemini).** The text judge cannot see visual
gags or hear delivery. For public YouTube URLs (default on), send the top
`2 x target_clip_count` windows to Gemini as the YouTube URL plus
`start_offset` and `end_offset`, at 1 fps and low resolution. Gemini hears the
audio and sees the frames. It returns `av_score` (0 to 100) and
`visual_only` (true when the joke is not in the transcript). When present,
`llm_score` becomes the mean of the text score and `av_score`. Its timestamps
are never used for clip edges. Cost: about $0.03 per 3-hour VOD on Gemini 2.5
Flash-Lite, inside the free tier (8 hours of YouTube video per day). Off for
Twitch and private uploads until the §6.5 eval shows it adds picks.

### 6.4 Validation, snapping, and selection

The LLM's output is untrusted. Before use:

1. Parse it against a Pydantic model. Reject on any error. Retry once, then
   drop the candidate.
2. Map `start_line` and `end_line` to word timestamps. Reject if either line
   is outside the context window. Reject if duration is outside
   `[min_len, max_len]` (default 12 s to 60 s).
3. Snap `start` back to the nearest word that follows a pause of 0.4 s or
   more. Snap `end`: if a `laugh` run overlaps the end, end at the laugh's
   end plus 0.6 s, because Whisper word times inside laughter are
   unreliable. Otherwise, end at the end of the current word plus 0.6 s.
   Never end before the `punchline` line ends.
4. If a scene cut falls within 1 s of either edge, move the edge to the cut.
   (Runs after `fetch_sections`, on the downloaded section.)
5. Put both scores on one scale. Convert `llm_score` and the peak's `hype`
   to percentiles within this VOD (0 to 100). Then
   `final_score = w_llm * llm_pct + (1 - w_llm) * signal_pct`. `w_llm`
   defaults to 0.7 for VODs without chat and 0.5 for VODs with chat. The
   0.5 is a starting guess: the only public comparison (cliptron) had 13
   moments and a chat baseline tuned on its own answers, and untuned chat
   rate scored Recall@10 0.295. The §6.5 eval decides. Both live in
   `settings`.
6. Drop candidates with `keep = false` or a raw `llm_score` under
   `min_llm_score` (default 50). Percentiles only rank inside one VOD, so
   this floor stops a dull VOD from producing clips.
7. Remove overlaps: when two candidates overlap by more than 30%, keep the
   higher score.
8. **Pairwise re-rank.** Take the top 6 by `final_score`. For each pair, ask
   the LLM "Which clip would more viewers find funny or entertaining?" in
   both orders (15 pairs x 2 = 30 short calls). A pair counts as a win only
   when both orders agree. Otherwise it is a tie. Order by wins, then by
   `final_score`. Order bias in LLM judges is large, so both orders are
   required.
9. Keep the top `target_clip_count` (default: 2 per VOD hour, max 10).

### 6.5 Learning and evaluation

The review screen produces labels for free. Every approve and reject is a
labeled window.

- **Log features.** For every candidate, kept or dropped, store each
  signal's max and mean inside the clip window, its `origin`, and its raw
  and percentile scores in `candidates.features`.
- **Labels, weakest to strongest:** overlap with community clips or the top
  heatmap bins; review approve or reject (with `reject_reason`); posted;
  `post_stats` views, normalized per channel.
- **Test set.** Phase 0 labels 3 videos. Grow it to 10 VODs, each moment
  graded 0 to 3, and freeze it. `spike eval` re-runs detection on the frozen
  set and reports HIT@1 (is the top pick good), P@5, NDCG@5, and recall of
  community clips. Run it on every prompt, weight, or model change. A 1 to 2
  point difference on 10 VODs is noise.
- **Re-fit weights.** After a few hundred labeled windows (an estimate, not a
  sourced number), fit logistic regression on the logged features. Its
  coefficients become the new weights. Only with many VODs, move to LightGBM
  `rank_xendcg` grouped by VOD.
- **Label where it matters.** Spend review effort on candidates where the
  LLM percentile and the signal percentile disagree most.
- **Twitch labels from community clips.** Merge clips into moments when they
  are within 30 s of each other (without merging, recall inflates about 2x).
  Count clips with 5 or more views. A streamer-featured clip (`is_featured`)
  is a stronger grade. Report Recall@10 against an untuned `chat_users`-only
  arm: that is the floor Spike must beat.
- **Transcript proposals on streams.** About 10% of human-clipped moments sit
  below median chat rate, out of chat's reach. Run the transcript-chunk
  proposals (§6.2) on streams as an eval arm. Turn it on only if it raises
  recall.
- **Check the lag.** Log `chat_offset_s` per VOD and compare it with
  community clip ends.

### 6.6 Not used, and why

- **Whisper's own `[laughter]` tags:** sporadic and not reproducible.
- **Demucs voice separation and pyannote diarization:** close to real time
  on CPU. Too slow for a whole VOD.
- **Face expressions, CLIP "funny" prompts, scene-cut density, game
  kill-feed reading:** they find action or edits, not jokes. Scene cuts are
  still used for edge snapping (§6.4 step 4).
- **Local video LLMs (Qwen3-VL) on CPU:** too slow, with coarse timestamps.
- **Learned chat models (transformers over chat text):** need labels, and
  chat content added only a few AUC points over plain rate in the largest
  study.
- **Kleinberg burst detection:** assumes Poisson arrivals, which chat breaks.
  No shown gain over z-scores.
- **Stream markers:** need the broadcaster's token (recalled).
- **Viewer-count history:** no API for past VODs.
- **Reddit r/LivestreamFail and X:** API approval or cost, and only big
  moments of big streamers.
- **YouTube heatmap for Twitch streamers:** only when the streamer re-uploads
  the full VOD. Then treat it as a YouTube source.
- **Revisit:** facecam smile scores from MediaPipe (already installed for
  face tracking), only if the eval shows Spike misses silent reactions.

---

## 7. Editing: layout, captions, music, effects

Output: 1080x1920, H.264 High, AAC 160 kbps, 30 fps (60 fps if the source is
60 and the source setting asks for it), loudness normalized to -14 LUFS.

### 7.1 Layouts

| Layout | When | How |
|---|---|---|
| `face_track` | Talking head, podcast, IRL | MediaPipe face detection at 4 fps. Crop center follows the largest face, smoothed with an exponential moving average so the frame does not jitter. Hold position when no face is found |
| `split` | Gaming with a facecam | Facecam box on top (1080x640), gameplay crop below (1080x1280). The facecam box is set once per source by drawing it on a frame in the Sources screen |
| `center` | No face, no facecam | Center crop |
| `letterbox` | Wide content where cropping loses too much | Full frame scaled to width, blurred and zoomed copy fills the background |

The default comes from the source setting. The reviewer can switch layout per
clip and re-render. Auto-detecting the facecam position is out of scope: a
one-time box per streamer is faster to build and never wrong.

### 7.2 Captions

- Built from faster-whisper word timestamps. No second transcription.
- 1 to 3 words per line, one line on screen, placed in the lower third
  (above the gameplay HUD for `split`, set per source).
- Style presets in ASS format: `bold_pop` (white, black outline, current word
  in the accent color and scaled up), `clean` (white, soft shadow),
  `karaoke` (words fill in as spoken).
- Reviewer can edit the caption text in the review screen. The edit changes
  words, never timings. A full re-transcribe is a separate button.
- Optional profanity mask per source (`f***`).
- Escape `{`, `}`, and `\` in every word before it goes into the ASS file.
  These are ASS control characters. A transcript is untrusted input.

### 7.3 Music

- `music/` folder with one subfolder per mood: `hype`, `funny`, `chill`,
  `dramatic`, `wholesome`. Each track has a sidecar `.json` with its license
  source and URL.
- The LLM's `mood` picks the folder. A random track from it plays.
- Music sits at -22 dB under speech. ffmpeg `sidechaincompress` ducks it
  further while someone speaks.
- Off by default for gaming sources, where game audio is the point. On/off
  per source and per clip.

### 7.4 Effects (kept small on purpose)

| Effect | Rule |
|---|---|
| Hook title | `hook_text` shown for the first 2.5 s, top of frame |
| Punch-in zoom | 1.0x to 1.15x over 0.3 s at the peak second, back out over 1 s. Once per clip |
| Loudness | `loudnorm` two-pass to -14 LUFS, true peak -1.5 dB |
| Silence trim | Cut internal pauses longer than 1.2 s (optional, per source) |

Skipped: sound effects, emoji overlays, B-roll, progress bars. Add one when
the team asks for it and Phase 7's numbers say captions and hooks are not
enough.

### 7.5 Render command shape

One ffmpeg call per clip. The Python code builds the argument list and passes
it to `subprocess.run([...])` with **no shell**. Titles, captions, and file
names never become part of a shell string. The filter graph:
trim -> layout crop/scale -> zoom -> ASS captions -> hook text overlay, and
for audio: trim -> music mix with sidechain duck -> loudnorm.

---

## 8. Posting

Posting is optional. The default for every source is "review first, then
download or post by hand." Auto-posting is a per-source rule the admin turns
on.

### 8.1 Platform facts (checked 2026-09-29, see §16)

| Platform | Cost | Limit | Gate |
|---|---|---|---|
| YouTube Shorts | Free | 100 uploads/day per Google Cloud project | Uploads from an unverified project are forced **private** until the app passes Google's compliance audit |
| TikTok | Free | Unaudited: max 5 posting users per 24 h | Direct Post needs TikTok's audit for anything but private (`SELF_ONLY`). **Upload to inbox** mode needs no audit: the clip lands in the creator's TikTok inbox, and they tap Post in the app |
| Instagram Reels | Free | 100 API posts per account per 24 h | Needs a Business or Creator account. Meta app review needed for accounts outside the app's own team (recalled). The API fetches the video from a public URL, or uses resumable upload (recalled, verify) |

### 8.2 Rollout order

1. **Download + copy caption.** Works on day one for every platform.
2. **TikTok, upload-to-inbox.** Free, no audit, and a human still taps Post,
   which also keeps TikTok's audit and spam rules easy.
3. **YouTube.** Build it, post privately, then apply for the audit. Once it
   passes, posts can be public and scheduled.
4. **Instagram.** Last. It needs a Business/Creator account and likely a
   public video URL, which conflicts with "no public port." Options: a
   short-lived Cloudflare Tunnel URL for one file, or the resumable upload
   flow if Phase 6 confirms it.

### 8.3 Auto-post rule (per source)

Auto-post only fires when **all** of these hold:

- The source's `permission` is `own`, `written`, or `program` (§12).
- A platform account is connected and its token is valid.
- The clip's `final_score` is at or above the rule's threshold (default 80),
  and its raw `llm_score` is at or above 70. `final_score` is a per-VOD
  percentile, so on its own it would pass the top clip of a dull VOD.
- The account's daily cap is not reached (default 3 per day, well under every
  platform limit, to avoid spam flags).
- The clip is not flagged `needs_context`.

Anything that fails a check waits in the review queue instead.

### 8.4 Scheduling

Posts get a `scheduled_for` time. The worker checks every minute for due
posts. Default slots per account: 12:00 and 19:00 local time. The reviewer can
pick "now" or any slot.

---

## 9. Data model

SQLite, WAL mode, foreign keys on. Times in UTC ISO-8601. Media lives on disk
under `data/`. The database holds paths, not blobs.

### `users`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| login | text unique | Tailscale login (email) |
| name | text | |
| role | text | `admin` or `member`. CHECK constraint |
| active | integer | 0 blocks every request immediately |
| created_at | text | |

Admins connect platform accounts, edit settings, manage users, and delete
media. Members submit jobs, review, edit, render, download, and post to
accounts that are already connected.

### `sources`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| kind | text | `twitch` or `youtube` |
| external_id | text | Broadcaster id or channel id. Unique with `kind` |
| display_name | text | |
| permission | text | `own`, `written`, `program`, `none` |
| permission_note | text | Where the permission is recorded (link, date, who) |
| auto_process | integer | Watcher queues new VODs |
| style_notes | text | Goes into the LLM prompt |
| language | text | Null = auto-detect |
| layout | text | Default layout |
| facecam_box | text (json) | `{x, y, w, h}` as fractions of the frame |
| caption_style | text | Preset name |
| caption_y | real | Vertical position, fraction of frame |
| music | integer | On/off default |
| chat_offset_s | real | Last per-VOD lag estimate. Default 12 (§6.1) |
| chat_tokens | text (json) | Per-channel token lists: `{laugh, hype, confusion, sad, bots}`, merged with BTTV/FFZ/7TV emote names |
| auto_post | text (json) | `{account_ids, min_score, per_day}` or null |
| created_by | integer fk users | |

### `videos` (also the job queue)
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| source_id | integer fk | Null for one-off uploads and URLs |
| origin | text | `upload`, `url`, `twitch_vod`, `youtube` |
| external_id | text | Unique with `origin` |
| url | text | |
| title | text | Untrusted. Escaped on render |
| duration_s | real | |
| chat_offset_s | real | Lag used for this VOD's chat signals (§6.1). Null without chat |
| status | text | `queued`, `running`, `ready`, `done`, `failed` |
| stage | text | Current or failed stage |
| error | text | Last error, shown in Jobs |
| attempts | integer | |
| priority | integer | Manual submissions beat watcher jobs |
| submitted_by | integer fk users | Null for watcher jobs |
| created_at, claimed_at, finished_at | text | |

### `candidates`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| video_id | integer fk | ON DELETE CASCADE |
| peak_t | real | |
| start_s, end_s | real | After snapping |
| origin | text | `signal`, `llm_chunk`, or `both` (§6.2) |
| chat_mood | text | `laugh`, `hype`, `confusion`, `sad`, or null (§6.2). Shown in review |
| signal_score, llm_score, final_score | integer | 0 to 100. `llm_score` is raw, the other two are per-VOD percentiles (§6.4) |
| av_score | integer | Gemini audio-visual score, or null |
| punchline | text | Untrusted LLM output. Escaped |
| features | text (json) | Per-signal max and mean in the clip window. Training data for §6.5 |
| title, hook_text, post_caption | text | Untrusted LLM output. Escaped |
| hashtags | text (json) | |
| reason | text | Shown in review |
| mood | text | |
| needs_context | integer | |
| status | text | `proposed`, `selected`, `dropped` |

### `clips`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| candidate_id | integer fk | |
| version | integer | Each re-render is a new version. Old files are deleted |
| layout, caption_style | text | |
| trim_start_s, trim_end_s | real | Reviewer adjustments |
| caption_overrides | text (json) | Word index -> new text |
| music_track | text | Path, or null |
| file_path, thumb_path | text | |
| status | text | `rendering`, `ready`, `approved`, `rejected`, `posted` |
| reviewed_by | integer fk users | |
| reviewed_at | text | |
| reject_reason | text | Feeds Phase 7 tuning |

### `accounts`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| platform | text | `youtube`, `tiktok`, `instagram` |
| display_name | text | |
| access_token_enc, refresh_token_enc | blob | Encrypted with Fernet. Key in `.env` only |
| expires_at | text | |
| connected_by | integer fk users | |

### `posts`
| Column | Type | Notes |
|---|---|---|
| id | integer pk | |
| clip_id, account_id | integer fk | Unique pair. No double posts |
| status | text | `scheduled`, `uploading`, `posted`, `sent_to_inbox`, `failed` |
| scheduled_for | text | |
| platform_post_id, url | text | |
| error | text | |
| posted_by | integer fk users | Null if auto-posted |

### `post_stats`
| Column | Type | Notes |
|---|---|---|
| post_id | integer fk | |
| measured_at | text | Pulled at 24 h and 7 d |
| views, likes, comments, shares | integer | |

### `settings`
Key/value. Holds LLM base URL and model name (not the key), both signal
weight sets, `w_llm` for each path, thresholds, clip length range, target
counts, retention days, default slots.

### `events`
`id, ts, video_id, level, message`. The Jobs screen reads it. Pruned after 30
days. Never holds tokens or keys.

### Files on disk

```
data/
  spike.db
  backups/spike-YYYY-MM-DD.db
  videos/<id>/meta.json, audio.m4a, chat.json, clips.json, comments.json,
             transcript.json, signals.npz, sections/, clips/
  uploads/<uuid>.<ext>
music/<mood>/<track>.mp3 + .json
```

---

## 10. Screens

The UI is for short sessions: open, review five clips, leave. Dense,
keyboard-first, dark by default (video looks better on dark), light theme
available.

### 10.1 Review (home)

- Grid of `ready` clips, newest job first, highest score first inside a job.
- Each card: autoplaying muted 9:16 preview on hover/focus, score, title,
  reason, source, duration.
- Open a clip: large player, full reason and signal breakdown, and controls:
  - Trim start/end (plus/minus 0.5 s buttons and number fields).
  - Layout switch, caption style switch, music on/off.
  - Caption text editor (word list, text only).
  - Re-render (goes to the front of the queue, about a minute).
  - Approve, Reject (with a reason), Download, Copy caption, Post / Schedule.
- Keys: `j`/`k` next/previous, `space` play/pause, `a` approve, `r` reject,
  `d` download, `[`/`]` nudge start, `{`/`}` nudge end, `e` edit captions.

### 10.2 New

Three tabs: upload a file (drag and drop, size limit shown), paste a URL
(allowed hosts listed), or pick a followed streamer and a specific VOD.
Optional per-job overrides: clip count, length range, layout.

### 10.3 Sources

List of followed streamers and channels with permission status, auto-process
toggle, last VOD processed, and clip count. Source edit page: all `sources`
fields, a frame grab to draw the facecam box on, and a caption position
preview.

### 10.4 Jobs

Every video with status, current stage, elapsed time per stage, error, and
Retry / Cancel. A disk-usage bar at the top.

### 10.5 Posts

Scheduled and past posts per account, with status, link, and stats once
Phase 7 exists.

### 10.6 Settings (admin)

Users, platform accounts (connect/disconnect via OAuth), LLM provider,
scoring weights and thresholds, retention, notification webhook.

### Design system

**`DESIGN.md` is the source of truth** for tokens, components, page
recipes, and copy rules. Summary:

- Plain CSS with tokens on `:root`. No CSS framework, no build step.
- Neutral greys, a neutral high-contrast primary button, one blue accent
  for links, focus, and progress. Status colors only on badges and alerts.
- Geist and Geist Mono, self-hosted. Tabular numbers for scores and times.
- One page, one job, at most one primary button.
- Every screen has loading, empty, error, and stale states.
- Visible focus ring on every interactive element. Every icon button has a
  text label or `aria-label`.
- Before building: run the `design-taste-frontend` skill. Before calling the
  UI done: `impeccable`, then the Web Interface Guidelines check.

---

## 11. Hardware, throughput, and storage

### Minimum PC

| Part | Minimum | Better |
|---|---|---|
| CPU | 6 cores, 2019 or newer | 8+ cores |
| RAM | 16 GB | 32 GB (needed for local LLM fallback) |
| Disk | 500 GB SSD | 1 TB SSD |
| GPU | None | Intel iGPU with Quick Sync (fast encode) or any NVIDIA card (fast transcribe and encode) |
| Network | 50 Mbps down | 100+ Mbps |

Power settings: never sleep while the worker has a job. Wake timers on if the
watcher must run overnight (same lesson as Proposal Desk).

### Throughput estimate for one 3-hour VOD, CPU only (AMD Ryzen 7 5800H)

Measured in Phase 0 on real 31.8-min audio sample.

| Stage | Estimate / Measured | Basis |
|---|---|---|
| Audio download | 2 to 5 min | About 200 MB |
| Chat download | 2 to 5 min | Measured ~1.5 min for 30m chat via TwitchDownloaderCLI |
| Transcription (faster-whisper `small`, int8, VAD) | **~58 min (measured)** | Phase 0 benchmark on AMD Ryzen 7 5800H: RTF 0.325 (3.1x real-time). `base` is ~18 min (RTF 0.099) |
| Signals | 1 to 2 min | numpy over ~10,800 samples |
| Audio events (YAMNet) | **~1 min (measured)** | Phase 0 benchmark on AMD Ryzen 7 5800H: RTF 0.005 (0.3 CPU-min/hr) |
| Comments and heatmap | under 1 min | 10 API calls plus data already in `meta.json` |
| LLM, Gemini | 4 to 8 min | About 60 judge calls (2 samples each) plus 30 short pairwise calls, network-bound |
| Gemini audio-visual judge | 1 to 3 min | YouTube only, about 12 short windows, network-bound |
| LLM, local 7B on CPU | 30 to 60 min | Slow token rate on CPU |
| Section downloads | 5 to 10 min | 6 sections x ~50 MB |
| Render | 6 to 15 min | 6 clips x 1 to 2 min each with libx264 `veryfast` via native ffmpeg `sendcmd` |
| **Total** | **about 1.2 to 1.8 h** | With Gemini + faster-whisper `small` |

Rough capacity: 8 to 15 hours of VOD per day. Enough for a few streamers.
If the queue backs up, the fixes in order: smaller Whisper model (`base`),
Quick Sync or NVENC encoding, Groq Whisper, then a GPU.

### Storage and retention

| Item | Kept for | Default |
|---|---|---|
| Audio, chat, transcript, signals | Until job is `done` + N days | 7 days |
| Section video | Until job is `done` + N days | 3 days |
| Uploaded source files | Until job is `done` + N days | 3 days |
| Rendered clips | N days after posted or rejected | 30 days |
| Database and backups | Always, 14 daily backups | |

A nightly cleanup job deletes expired files. The watcher pauses and alerts if
free disk falls under 50 GB.

---

## 12. Legal and platform-policy rules

These rules protect the team's accounts. Treat them as requirements.

1. **Permission per source.** Every source records a permission level:
   - `own`: the team's own channel.
   - `written`: the creator agreed in writing (link or screenshot noted).
   - `program`: the creator runs a public clipping program that allows it
     (link noted).
   - `none`: processing for private review only. Spike **blocks posting**
     from these clips in code, not just in the UI.
2. **Music must be licensed for the target platform.** Store the license
   source for every track. No commercial songs.
3. **Reused content.** YouTube's monetization policy and TikTok's originality
   rules can limit reach or earnings for clips of other people's content
   (recalled, verify before relying on monetization). Captions, hooks, and
   edits help, but permission is the real protection.
4. **Downloading.** Download only what the team has permission to use. Check
   Twitch's and YouTube's terms on downloading during Phase 0 and record the
   result in §16. The "Most replayed" heatmap comes from yt-dlp's read of
   YouTube's player data, the same unofficial mechanism as downloads, so it
   is optional and can break without notice. Comments come only through the
   official YouTube Data API.
5. **Posting volume.** Default 3 auto-posts per account per day. Bursts of
   near-identical posts look like spam to every platform.
6. **No browser automation, no unofficial posting APIs, no second accounts to
   dodge limits.**

---

## 13. Phases

Each phase ends with a "done when" check that can be observed, not just a
list of built things.

### Phase 0: Spike and verification (1 to 2 days)

- Record the real PC specs. Run faster-whisper `base`, `small`, and `medium`
  (int8) on a 30-minute sample. Record real-time factors. Pick the model.
- Run OpenShorts (MIT) locally on the same sample as a quality baseline.
  Read its reframe and caption code. Decide what to reuse, with its license
  notice kept.
- Verify every "recalled" item in §16 that later phases depend on. Update
  §16 with the results.
- Create a Twitch app (client credentials) and a Gemini API key. No billing
  account attached to the Gemini project, so it cannot charge.
- Create a YouTube Data API key (no billing). Confirm the yt-dlp `heatmap`
  field is present on the YouTube test video.
- Confirm Gemini accepts a YouTube URL with `start_offset`/`end_offset` on
  the free tier.
- Pick 3 test videos: one Twitch VOD with an active chat, one podcast, one
  gameplay video without chat. Team members each mark the 5 moments they
  would clip and grade each 1 to 3. This is the ground-truth set for Phases
  1 and 3, and the start of the §6.5 test set.
- Benchmark YAMNet (TFLite) and PANNs CNN14 on one real VOD: CPU time per
  audio hour, and how many team-marked moments have a `laugh` hit within
  30 s. This checks the one unproven link in §6: whether a streamer's own
  laughter marks good clips (the studies used audience laughter). Tune the
  `laugh` gate here. Pick the faster model unless the other finds clearly
  more marked moments.

- Download one real VOD's chat replay and check what it holds: the
  `msg_id` values present, whether raid and sub lines appear, the precision
  of `content_offset_seconds`, and whether 7TV emote names resolve. Sources
  disagree on what replays keep, and the §6.1 chat cleaning depends on it.

**Done when:** the benchmark table is filled with real numbers, §16 is
updated, the ground-truth set exists, one laughter model is chosen, and the
chat replay contents are recorded in §16.

### Phase 1: Core pipeline as a CLI

- `spike run <file-or-url>`: stages 1, 2, 4 (YouTube comments), 5, 6 (no-chat
  signals: `laugh`, `shout`, `audio_loud`, `speech_rate`, `replay_heat`,
  `comment_heat`), 7 (signal peaks plus transcript chunks), 8, and a plain
  16:9 cut.
- Pydantic validation of LLM output, line-to-timestamp mapping, snapping,
  percentile blend, pairwise re-rank, selection.
- `spike eval`: runs detection on the ground-truth set and prints HIT@1,
  P@5, and NDCG@5 (§6.5).
- Stage checkpoints and resume.
- One small self-check script: runs the selection logic on a fixed fake
  transcript and asserts the output windows.

**Done when:** on the 3 test videos, at least 3 of Spike's top 5 match a
moment a team member marked, and a killed run resumes without redoing
finished stages.

### Phase 2: Vertical edit

- Layouts `face_track`, `split`, `center`, `letterbox`.
- ASS captions with the three presets, word-by-word timing.
- Hook text, punch-in zoom, loudness normalization.
- Thumbnail frame.

**Done when:** the team rates 4 of 5 rendered clips "postable as is" on
framing and captions (content quality is Phase 1's job), and captions stay
within 100 ms of speech on a spot check.

### Phase 3: Streams

- Twitch Helix: VOD list, community clips with offsets.
- Chat replay download. Audio-first fetch and section downloads.
- Chat cleaning, all chat signals, fusion, peak picking (§6.1, §6.2).
- Per-VOD lag estimate. Check it on the test VOD against community clip
  ends. Tune the raid rule there too.
- Community-clip labels and the untuned `chat_users` baseline arm in
  `spike eval` (§6.5).
- The watcher for Twitch and YouTube sources.

**Done when:** on the test VOD, at least 4 of Spike's top 5 match a
team-marked moment (better than Phase 1, because chat helps), Spike beats the
untuned `chat_users` baseline on community-clip Recall@10, and a new VOD
from a followed streamer is processed with no human action.

### Phase 4: Web app

- FastAPI app, worker, and watcher as three processes. Start on boot
  (Windows Task Scheduler or NSSM service).
- Tailscale Serve, header auth, `users` table, admin/member roles.
- Screens: Review, New, Sources, Jobs, Settings (without platform accounts).
- Re-render with trims, layout, caption, and music changes.
- Discord notification when a job reaches `ready`.
- Upload handling: size cap, ffprobe type check, stored outside any served
  folder.

**Done when:** a second team member, from their own device, submits a URL,
gets the Discord ping, trims and re-renders a clip, and downloads it. A device
that is not on the tailnet cannot load any page.

### Phase 5: Music and effects polish

- Music library with mood folders and license sidecars. Ducking.
- Silence trim option.
- Per-source defaults for everything in §7.

**Done when:** music never masks speech on a spot check of 10 clips, and
every track in `music/` has a license sidecar (a startup check enforces it).

### Phase 6: Posting

- Accounts screen with OAuth for each platform. Tokens encrypted at rest.
- TikTok upload-to-inbox first. Then YouTube upload (private until audit),
  then apply for the YouTube audit. Instagram last, after the upload method
  is verified.
- Posts screen, scheduling, per-source auto-post rules with every check in
  §8.3, and the `permission = none` block enforced in the posting function
  itself.

**Done when:** one approved clip reaches a team TikTok inbox and one uploads
to YouTube (private), from the UI, and a test proves a `permission = none`
clip cannot post through any path.

### Phase 7: Reliability and feedback

- Retry with backoff on every network stage (already sketched in §5, made
  complete here).
- Heartbeat: the worker writes a timestamp every minute. If it goes stale for
  30 minutes, a small separate scheduled task sends a Discord alert.
- Disk-space guard and nightly cleanup.
- Nightly SQLite backup (`.backup` command), 14 kept.
- Pull post stats at 24 h and 7 d. A Stats view shows views by score band and
  by signal mix.
- Grow the ground-truth set to 10 graded VODs and freeze it (§6.5).
- Once a few hundred reviewed candidates exist, fit logistic regression on
  `candidates.features` against review and post labels. Adopt the new
  weights, `w_llm`, and `min_llm_score` only if `spike eval` improves.
  Record the change and the data behind it.
- Decide from `spike eval` whether the Gemini audio-visual judge turns on
  for Twitch VODs.

**Done when:** unplugging the network mid-job ends in a clean retry, a
stopped worker produces an alert within 35 minutes, and the Stats view shows
real numbers.

### Phase 8: Security and hardening (T2, Internal/Team)

Tier T2: a small known team, reachable only through a private network, holding
OAuth tokens that can post to real accounts. The tokens are the most valuable
thing in the system.

**Scaling:** not needed. Fixed small team, one machine. Re-check if outside
creators get access, which would also move security to T3.

**Secrets and keys**
- [ ] Twitch secret, Gemini key, YouTube Data API key, OAuth client secrets, Discord webhook, and
      the Fernet key live only in `.env` on the PC. `.env` and `data/` are in
      `.gitignore` before the first commit.
- [ ] Any secret that was ever committed is rotated, not just deleted.
- [ ] Rotate keys on a schedule and when a team member leaves.

**Data access**
- [ ] SQLite is a local file. It is never shared over the network.
- [ ] Platform OAuth tokens encrypted at rest (Fernet). The key never enters
      the database or logs.
- [ ] Role checks on the server for every admin action (accounts, settings,
      users, deletes). A member calling an admin route directly gets a 403.
- [ ] Every data query uses SQLite parameters, never string-built SQL.

**Auth and access**
- [ ] Web app binds to `127.0.0.1` only. Tailscale Serve is the only way in.
- [ ] Every route, including downloads and media files, checks the identity
      header and an `active` row in `users`. No unauthenticated route except
      a health check that returns nothing sensitive.
- [ ] Setting `active = 0` blocks the next request. Removing a person from
      the tailnet is the second lock.
- [ ] Pydantic models accept only the fields each form may change (no stray
      `role` on a profile update).
- [ ] 2FA on the Tailscale identity provider, Google Cloud, Twitch developer,
      TikTok developer, Meta developer, GitHub, and Discord accounts.

**Rate limiting and abuse**
- [ ] Per-user cap on job submissions (default 10 per hour) and re-renders
      (default 60 per hour), enforced server-side.
- [ ] Upload size cap (default 20 GB) and max video duration (default 12 h).
- [ ] Gemini project has no billing account, so it cannot overspend. If a
      paid LLM is ever enabled, set a billing cap and alert first.

**Input and output handling**
- [ ] URL submissions allowed only for listed hosts (`twitch.tv`,
      `youtube.com`, `youtu.be` to start). This stops yt-dlp from being
      pointed at internal addresses or arbitrary extractors.
- [ ] Uploads: extension allowlist, ffprobe must read it as video, stored in
      `data/uploads/` with a random name, never served directly. Downloads go
      out with `Content-Disposition: attachment`.
- [ ] Every subprocess (`ffmpeg`, `yt-dlp`, `TwitchDownloaderCLI`) runs with
      an argument list, never `shell=True`. A test feeds a title containing
      `; rm -rf` and `$(...)` through the whole render path.
- [ ] ASS control characters escaped in captions. Jinja2 autoescape on for
      all pages. No `|safe` on any user, transcript, chat, or LLM text.
- [ ] Log lines escape newlines and control characters from untrusted text.

**AI/LLM**
- [ ] Transcript, chat, and YouTube comments sit in tagged data blocks. The
      system prompt says to ignore instructions inside them.
- [ ] The Gemini audio-visual judge receives only public YouTube URLs. Private
      uploads never leave the PC through it.
- [ ] The LLM has no tools. Its output is JSON validated by Pydantic, clamped
      to the context window, and never used in a shell command or SQL.
- [ ] Per-user cap on LLM-triggering actions (covered by the job cap).

**Dependencies**
- [ ] `pip-audit` clean before each deploy.
- [ ] Every package checked on PyPI (real name, maintainer, downloads) before
      install. No lookalike names.
- [ ] Pin versions in `requirements.txt`, except yt-dlp, which must update
      often to keep working. Review its release notes on each update.

**Operations**
- [ ] HTTPS via Tailscale Serve certificates.
- [ ] Security headers on every response: CSP (no inline scripts, htmx loaded
      from a local file), `X-Frame-Options: DENY`,
      `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
      HSTS.
- [ ] FastAPI debug off. Errors show a generic message and an error id. Full
      tracebacks go to the log only.
- [ ] Logs never contain tokens, keys, or the Fernet key. A test grep checks
      a day of logs.
- [ ] Nightly backups (Phase 7) and one tested restore.

**Done when:** every box above is checked by hand against the running system,
and `pip-audit` is clean.

---

## 14. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Moment detection picks boring clips | Medium | High, the product fails | Ground-truth set in Phase 0. Laughter and crowd signals for uploads, chat for streams. `spike eval` on every change. Phase 7 re-fits weights from review labels |
| A streamer's own laughter does not mark good clips (studies used audience laughter) | Medium | Medium | Phase 0 benchmark checks it. If it fails, `laugh` weight drops and its share moves to the other signals |
| yt-dlp stops exposing the heatmap | Medium | Low | Optional signal. Its weight rescales to the others |
| Raids, sub trains, and bot spam outrank real moments | High without filtering | Medium | Chat cleaning in §6.1. Unique chatters instead of message counts |
| Chat lag is wrong for a channel, so clips start too late | Medium | Medium | Per-VOD lag estimate against audio laughter, logged and checked against clip ends |
| Twitch changes the internal chat API | Medium | Medium | Chat is one signal of several. Detection still runs without it. Pin a known-good TwitchDownloaderCLI and watch its releases |
| yt-dlp breaks on a site change | High, happens often | Medium | Update yt-dlp weekly. Failed fetch shows a clear error and Retry |
| Small PC falls behind | Medium | Medium | Audio-first design. Smaller model, hardware encode, Groq Whisper, then a GPU |
| Copyright strike on a team account | Low with §12 rules | High | Permission field enforced in code. Licensed music only |
| YouTube or TikTok audit refused | Medium | Low | Download and TikTok inbox work without any audit |
| Gemini free tier changes or ends | Medium | Low | Settings switch to Ollama or a paid model. No code change |
| Gemini free tier uses submitted data for training (recalled) | Unknown | Low for public streams | Verify in Phase 0. Use Ollama for private uploads if true |
| PC off or asleep | Medium | Low | Watcher catches up. Heartbeat alert in Phase 7 |
| Disk fills | Medium | Medium | Retention, nightly cleanup, 50 GB guard |

---

## 15. Open questions

1. What are the small PC's real specs (CPU, RAM, disk, GPU)? This sets the
   Whisper model and the capacity estimate.
2. Which streamers and channels first, and what permission does the team have
   for each?
3. Which platform matters most? This decides the Phase 6 order.
4. Which languages? Whisper handles many, but caption styling and the LLM
   prompt may need per-language tuning.
5. How many people on the team, and who is admin?
6. Should Spike also clip live, during the stream (not just after)? Not in
   this plan. It needs a live HLS reader and live chat, and a small PC may not
   keep up.

---

## 16. Appendix: facts, verified vs recalled

### Verified 2026-09-29 (web search of official docs or the repo)

- **YouTube:** `videos.insert` uses the "Video Uploads" quota bucket, 100
  uploads per day per project. Uploads from unverified API projects created
  after 28 July 2020 are restricted to private until audit. (Google
  developer docs, plus a third-party summary.)
- **TikTok:** unaudited clients can only post with `SELF_ONLY` (private)
  visibility, and at most 5 users can post in a 24 hour window. Upload to
  inbox mode needs no audit. (TikTok developer docs, plus a third-party
  summary for the inbox detail.)
- **Instagram:** 100 API-published posts per account in a moving 24 hour
  window. (Meta developer docs.)
- **OpenShorts:** MIT license (except its `cloud/` folder). Python/FastAPI
  backend, React frontend, faster-whisper, MediaPipe, YOLOv8, yt-dlp,
  ffmpeg. Its clip generator works with Gemini or a local LLM via
  `LLM_BASE_URL`. Posting goes through Upload-Post, a paid third party. No
  Twitch or chat input. (GitHub repo.)

### Verified 2026-10-01 (moment detection research)

Sources are in `reports/Funny clip detection signals.md`.

- **yt-dlp `heatmap`:** a list of `start_time`, `end_time`, and `value`
  (0 to 1), 100 bins per video. Not in YouTube's official API. (yt-dlp
  source.)
- **YouTube Data API:** `commentThreads.list` costs 1 quota unit per call and
  returns up to 100 threads. (Google developer docs.)
- **Gemini video:** accepts public YouTube URLs, processes the audio track,
  samples 1 fps by default (custom `fps` allowed), supports
  `start_offset`/`end_offset`. Free tier allows 8 hours of YouTube video per
  day. 2.5 Flash-Lite costs $0.10 per 1M video tokens. (Google AI docs and
  pricing page, last updated 2026-10-01.)
- **YAMNet:** 521 AudioSet classes including Laughter, Giggle, Snicker, Belly
  laugh, Chuckle, Shout, Yell, Screaming, Whoop. Apache-2.0. (TensorFlow
  models README.)
- **LightGBM:** `lambdarank` and `rank_xendcg` objectives take integer
  labels grouped per query. (LightGBM docs.)

- **Twitch Get Clips:** returns `video_id`, `vod_offset` (whole seconds,
  added 2023-07-20), `view_count`, `duration`, `created_at`, `creator_id`,
  and `is_featured`. Filters by `started_at`/`ended_at`, up to 100 per page.
  `vod_offset` is null while live. (Twitch Helix reference.) Null after VOD
  deletion is from a search snippet only.
- **TwitchDownloader chat JSON:** each comment has `content_offset_seconds`,
  `message.bits_spent`, `user_notice_params.msg_id`, `user_badges`, and emote
  fragments. (TwitchDownloader source, `ChatRoot.cs`.) Whether real replays
  fill these is checked in Phase 0.
- **Chat lag:** best shift was -15 s on LoL Worlds 2020 (Ringer thesis, York
  2022). LIGHTOR learned 20 to 27 s (ICDE 2020). Both are esports.

Sources for the Twitch items are in `reports/Twitch chat highlight
detection.md`.

### Verified 2026-10-01 (Phase 0 Benchmarks and Research)

- **Tailscale Serve identity headers:** confirmed `Tailscale-User-Login` (also
  `Tailscale-User-Name`, `Tailscale-User-Profile-Pic`). Tailscale strips incoming
  headers to prevent spoofing; injects only for tailnet traffic. Free Personal plan
  covers up to 6 users (unlimited devices). (tailscale.com)
- **faster-whisper CPU speed:** official README benchmark on modern desktop CPU
  (i7-12700K) achieves RTF ≈ 0.13 (~7.6x real-time) for `small` INT8 on CPU. (faster-whisper README)
- **yt-dlp Twitch VODs:** `-x --audio-format m4a` downloads audio-only;
  `--download-sections "*START-END"` supported on HLS streams via ffmpeg. (yt-dlp docs & testing)
- **Twitch VOD retention:** Partners/Turbo/Prime: 60 days; Affiliates: 14 days;
  Regular users: 7 days. Highlights do not expire (100h max). (help.twitch.tv)
- **Twitch & YouTube ToS on downloading:** Both technically prohibit third-party
  downloading of others' content without permission. YouTube ToS is explicit (Premium
  offline only). Downloading own content via official dashboard is permitted. (twitch.tv / youtube.com ToS)
- **TwitchDownloaderCLI:** MIT license. Command:
  `TwitchDownloaderCLI chatdownload -u <VOD_ID> -o <out.json>`. Real replay inspection
  confirmed `content_offset_seconds` is whole integers, `msg_id` is null/absent,
  raid/sub notices appear as body text, and 7TV emote tokens appear in plain text body.
  (Phase 0 test on VOD 2887910568)
- **7TV public API:** `GET https://api.7tv.app/v3/users/twitch/{user_id}` returns
  active emote set; no authentication required for read operations. (api.7tv.app)
- **YouTube Data API quota:** 10,000 units/day default per Google Cloud project
  (shared across all keys). (Google developer docs)
- **Gemini OpenAI-compatible endpoint:** `https://generativelanguage.googleapis.com/v1beta/openai/`.
  Free tier uses submitted data for model training by default; paid tier does not.
  YouTube URLs with `start_offset`/`end_offset` supported via `google-genai` SDK
  `VideoMetadata`. (ai.google.dev)
- **Anthropic OpenAI-compatible endpoint:** `https://api.anthropic.com/v1/` — official
  OpenAI SDK compatibility layer provided by Anthropic. (docs.anthropic.com)
- **Instagram Reels resumable upload:** Supported via Graph API without public URL:
  POST `upload_type=resumable` to `/media`, upload bytes to `rupload.facebook.com/ig-api-upload/<ID>`,
  then publish. (Meta developer docs)
- **Licenses:** faster-whisper (MIT), MediaPipe (Apache 2.0), PySceneDetect (BSD 3-Clause),
  htmx (0BSD). Ultralytics is AGPL-3.0 (strong copyleft, avoid). Remotion is source-available /
  custom license (free only for <=3 employees; paid commercial license required for >=4 employees).
- **YouTube & TikTok reuse policies:** Both penalize unoriginal/reused clips lacking
  meaningful transformation/human commentary (YouTube "inauthentic content" policy;
  TikTok FYF suppression & Creator Rewards disqualification).
- **YAMNet TFLite on Windows:** `tflite-runtime` does not ship Windows wheels for
  Python 3.14. Running `yamnet.tflite` via `tf.lite.Interpreter` (from `tensorflow` 2.22rc0)
  works cleanly: measured 9.7s inference for 31.8 min of audio (RTF 0.005, 0.3 CPU-min
  per audio hour). PANNs CNN14 ruled out (~20x heavier, no PyPI package). (Phase 0 benchmark)

### Recalled, verify before relying on it

- Helix Get Stream Markers needs the broadcaster's or an editor's token.

---

## 17. Session learnings (`LEARNINGS.md`)

`LEARNINGS.md` carries context from one session to the next. This blueprint
records the plan. `LEARNINGS.md` records what each session found out.

### When to update it

1. At the start of a session, read `LEARNINGS.md` if it exists.
2. At the end of a session, add one entry to `LEARNINGS.md`.
3. If the file does not exist, create it with the heading `# Spike: Learnings`,
   then add the entry.

Do this even when the session only answered questions and changed no code.

### Entry format

Add the newest entry at the top, below the heading.

```
## YYYY-MM-DD: <short topic>

- **Done:** what changed (files, decisions).
- **Learned:** facts found, with "verified" or "recalled" and the source.
- **Decided:** choices made and the reason for each.
- **Open:** questions or next steps for the next session.
```

### Rules

- Keep each entry short. Use 3 to 10 bullets.
- Write facts, not a story of the session.
- If a learning changes the plan, also update the matching section of this
  blueprint. Do not let the two files disagree.
- If an old entry is now wrong, mark it `(superseded YYYY-MM-DD)`. Do not
  delete it.
- Never put secrets, keys, tokens, or passwords in the file.
