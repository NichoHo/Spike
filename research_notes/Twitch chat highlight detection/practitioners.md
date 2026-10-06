# Practitioner Twitch chat highlight detection (open source, products, clippers), as of 2026-10

Legend: **[V]** verified by reading code/docs this session. **[C]** claimed by the source, not checked. **[I]** my inference.

## Q1. Open-source projects: exact algorithms, parameters, evaluations

### Takeaway
Nearly every open-source tool does the same thing: count messages (sometimes keyword/emote matches) in fixed bins of 2 to 20 s, rank or threshold, then suppress neighbours (non-maximum suppression, NMS) 30 to 150 s apart. None of them learns a lag offset. cliptron is the only one with a real evaluation, and its headline chat-rate number (Recall@10 0.917) is oracle-tuned per VOD on 13 moments from one channel. Treat it as an upper bound, not a deployable figure.

### Cited Findings

**cliptron (infectedresearch/cliptron)**: 0 stars, no license file, last push 2026-09-25, Python. [V] — [repo](https://github.com/infectedresearch/cliptron)
- Ground truth = human Twitch clips from Helix `Get Clips` (`vod_offset`). Chat comes from GQL VOD replay (`contentOffsetSeconds`). Speech comes from Whisper over HLS. [V] — [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md)
- Baseline `chat_rate` [V] — [baselines.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/evals/baselines.py):
  - 5 s histogram bins of raw message count. No emote weighting, no unique-user count, no spam filter.
  - Trailing rolling sum over `window_s`, default 60 s.
  - Greedy pick of the highest bins, rejecting any within `sep_s` (default 90 s) of a chosen bin. This is NMS.
  - The output span is `[bin_start, bin_start + 60 s]`. No lag correction. The docstring says this is deliberate: "chat peaks land 35-44 s AFTER the true clip start (viewer reaction lag). We deliberately do not correct for it here."
- `chat_rate_tuned` sweeps `WINDOWS = (30, 60, 120, 240)` × `SEPARATIONS = (45, 90, 150)` and keeps the best config for each VOD, scored on that same VOD's answer key. The docstring says: "Tuned on the same data it is scored on, which favours the baseline. That is intentional." [V] — [baselines.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/evals/baselines.py)
- Per-VOD winning configs: 9 of 13 VODs picked window 30 s. 8 of 13 picked sep 45 s, the smallest values in the grid. Outliers were 60/45, 120/90, 120/150, and 240/150. [V] — [results/20260924T210018Z_primary.json](https://github.com/infectedresearch/cliptron/blob/HEAD/results/20260924T210018Z_primary.json)
- Dataset: all 13 VODs are from one channel, **theprimeagen**. Each VOD has 1,352 to 6,417 chat messages and 2 to 11 moments, 67 moments in total. [V] — same results file
- Metrics [V] — [metrics.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/evals/metrics.py):
  - Human clips are merged into "moments" with a 30 s gap, because "42 clips → 19 moments (~2x recall inflation if skipped)."
  - A hit means the prediction midpoint falls inside the moment ±15 s, or the spans overlap at all with 15 s tolerance. The overlap rule is lenient when predictions are 60 s long.
  - Ground truth only counts clips with ≥5 views.
- 13-VOD results [V] — [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md):

  | Arm | Recall@10 |
  |---|---|
  | random | 0.060 |
  | uniform | 0.074 |
  | untuned chat-rate | 0.295 |
  | tuned chat-rate | 0.360 ± 0.058 |

  Median boundary error is about 31 s for all chat arms.
- The often-quoted "0.917 vs 0.708 agent" comparison covers only the 4 transcribed VODs, 13 moments. The README itself calls this "n=13" and "The gap is 2.7 moments." On the same 4 VODs, the agent wins R@5 (0.542 vs 0.500) and median boundary error (28.6 vs 30.8 s). [V] — [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md)
- Where human moments sit in the chat-rate distribution [V] — [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md):
  - Median moment is at the 0.916 chat-rate percentile of its VOD.
  - 55% of moments are in the top 10%, and 78% are in the top 25%.
  - 10.4% are below the median. The README says no chat detector reaches these.
- The diagnostic uses `BIN, WIN, LAG = 5.0, 60.0, 45.0`. It looks at chat from the moment start up to moment end + 45 s. [V] — [diagnose.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/evals/diagnose.py)
- Hybrid agent [V] — [agent.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/agent.py):
  - Candidates are chat peaks over 240 s buckets, plus regions the LLM picks.
  - Final rank = LLM score + `CLIPPER_PRIOR_WEIGHT` (default 1.1) × chat-rank prior scaled to 0–10.
  - If the model returns too few clips, the list is topped up with chat peaks.
  - The prompt says: "Chat reacts 35-45s AFTER the thing that caused it, so the cause is usually at the START of a high-chat bucket or in the bucket just before."
- Author's lessons from the journal [V] — [journal.md](https://github.com/infectedresearch/cliptron/blob/HEAD/journal.md):
  - "Raids and emote spam outrank real clips"
  - "boundaries are linguistic"
  - "chat finds candidates, model does boundaries and tie breaks"
  - On the first VOD, untuned chat-rate R@10 was 0.214 (3.65× random).
- Future work listed in the README: "Model the chat lag instead of prompting it... Learn the offset per channel", and "Train the ranker". [V] — [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md)

**joaohenggeler/twitch-chat-highlights**: 10 stars, MIT, Python, active 2026-02. Uses keyword/emote category counting. [V] — [repo](https://github.com/joaohenggeler/twitch-chat-highlights)
- Config defaults [V] — [config.json.template](https://github.com/joaohenggeler/twitch-chat-highlights/blob/HEAD/Source/config.json.template):
  - `bucket_length: 20` s.
  - `message_threshold: 15`, the minimum category matches in a bucket.
  - `top_bucket_distance_threshold: 3` buckets (about 60 s NMS).
  - `top_url_delay: 15`. The parameter name suggests the VOD link is set 15 s before the bucket. I did not trace its use in code.
- Emote and word categories (the README example is "top 10 funniest moments by counting the occurrence of the LUL emote in a 20-second window") [V] — same config file:

  | Category | Words and patterns | Top N |
  |---|---|---|
  | Funny | `LUL, LULW, OMEGALUL, KEKW, regex:LMF?AO+, regex:LO+L` | 10 |
  | Pog | `POG, POGGERS, PogChamp` | 1 |
  | Scary | `monkaS, monkaW` | 1 |
  | Sad | `PepeHands, FeelsBadMan, Sadge, BibleThump, :(` | 1 |
  | Weird | `WutFace, DansGame, WeirdChamp, yikes, regex:WTF+, regex:bruh+, regex:\?+` | 1 |
  | Surprise | `D:` | 1 |
  | Jam | `ratJAM, SourPls` | 1 |
  | Good Bit / Bad Bit | `+2` / `-2` | not ranked |

- "+2 vs -2" comparisons produce "Best", "Worst", and "Controversial Bit" lists. Controversy is measured as `(p+n)/(|p-n|+1)` (Northernlion community convention). Tokens are lowercased and split on whitespace, then matched per word. [V] — [highlight.py](https://github.com/joaohenggeler/twitch-chat-highlights/blob/HEAD/Source/highlight.py)

**windycityassassin/reactorlab** (`clipping/`): 0 stars, pushed 2026-09. Live and offline, fuses chat and audio. [V] — [README](https://github.com/windycityassassin/reactorlab)
- Bins are 2 s. Audio is RMS dBFS over 1 s windows, and chat is messages per bin. Each signal is z-scored against the mean and std of the scored window. `score = 0.6·audio_z + 0.4·chat_z`. [V] — [score.py](https://github.com/windycityassassin/reactorlab/blob/HEAD/clipping/src/clipping/score.py)
- Threshold `min_score 1.2`, lowered to 0.5 for TTS podcasts because "two-voice TTS is loudness-flat". [V] — [score.py](https://github.com/windycityassassin/reactorlab/blob/HEAD/clipping/src/clipping/score.py), [README](https://github.com/windycityassassin/reactorlab)
- NMS `min_gap 30 s`. Clip window is **pre 8 s / post 20 s** around the peak. Live mode skips the last 15 s (`detect-lag`). [V] — [cli.py](https://github.com/windycityassassin/reactorlab/blob/HEAD/clipping/src/clipping/cli.py)
- I found no chat-to-video lag shift in score.py or chat.py (grep for lag/shift/offset). Chat is read from anonymous IRC. "No model anywhere in the loop." [V] — [score.py](https://github.com/windycityassassin/reactorlab/blob/HEAD/clipping/src/clipping/score.py), [README](https://github.com/windycityassassin/reactorlab)

**sqrtminustwo/twitch_auto_clipper**: MIT, on PyPI, live. Measures message *agreement*, not volume. [V] — [repo](https://github.com/sqrtminustwo/twitch_auto_clipper)
- Defaults: `counter_interval_seconds=20` (counters reset each interval), `clipable_message_ratio=0.5`, `clipable_wait=10` s before calling Create Clip, `common_value=1`, `emote_value=2` for 7TV emotes, plus `excluded_words`. [V] — [TwitchAutoClipper.py](https://github.com/sqrtminustwo/twitch_auto_clipper/blob/HEAD/twitch_auto_clipper/TwitchAutoClipper.py)
- The trigger fires when the weighted count of the single most frequent message ÷ total messages in the interval ≥ 0.5. Because emotes count double, the ratio can exceed 1. [V] — [README](https://github.com/sqrtminustwo/twitch_auto_clipper)

**Vladshmalii/twitch-auto-clip-bot**: MIT. Combines chat velocity, audio RMS and onsets, YOLO video, and keywords. [V] — [repo](https://github.com/Vladshmalii/twitch-auto-clip-bot)
- Each signal is capped at 1 and the capped signals are weighted-summed: `chat_score=min(velocity/100,1)`, `audio_rms*10`, `onsets/10`, `keywords/5`. Clips when `final>0.7`. `CHAT_VELOCITY_THRESHOLD=50` messages per 10 s. [V] — [signal_aggregator.py](https://github.com/Vladshmalii/twitch-auto-clip-bot/blob/HEAD/app/services/signal_aggregator.py), [README](https://github.com/Vladshmalii/twitch-auto-clip-bot)
- The README claims "F1 ~0.95" with no dataset or evaluation code. Treat as unsupported. [C] — [README](https://github.com/Vladshmalii/twitch-auto-clip-bot)

**marianonj/TwitchAutoClipper**: 2 stars. Uses chat frequency, message content, and audio. [V] — [repo](https://github.com/marianonj/TwitchAutoClipper)
- `set_clip_timings` is marked "WIP". It drops bins below the 25th percentile of frequency and ranks the rest by per-category text-match counts. `return_timestamps` expands each chosen bin by ±1 bin and merges adjacent ones. [V] — [main.py](https://github.com/marianonj/TwitchAutoClipper/blob/HEAD/main.py)

**Other small repos**:
- Fullonibus/twitch-highlight-detector (Java, 2026-06): plan-only README. Planned sliding windows of 10 s and 30 s, a threshold spike, "emote density", and a Twitch/7TV/FFZ emote dictionary. [V] — [repo](https://github.com/Fullonibus/twitch-highlight-detector)
- nirvagold/stream-clipper (Tauri/Rust, MIT, 3 stars): audio RMS above baseline plus WebRTC VAD. Chat spikes from TwitchDownloader JSON are a paid "Pro" feature, with "Audio + Chat overlap = higher score" and user-set weights. [V] — [repo](https://github.com/nirvagold/stream-clipper)
- igaskin/twitch_auto_clip: Grafana emote-rate monitor only. [V] — [repo](https://github.com/igaskin/twitch_auto_clip)
- LasTechLabs/Twitch-VOD-Chat-Analyzer (2020): plots chat-activity histograms with a keyword filter and an adjustable window. [V] — [repo](https://github.com/LasTechLabs/Twitch-VOD-Chat-Analyzer)
- pelledrijver/twitch-highlights (42 stars): compiles existing Twitch clips ranked by popularity. It does no detection. [V] — [repo](https://github.com/pelledrijver/twitch-highlights)

### Inferences
- [I] Typical knobs across the code read here:

  | Knob | Range seen |
  |---|---|
  | Bin | 2–20 s |
  | Rolling window | 20–60 s |
  | NMS gap | 30–90 s |
  | Clip | about 28–60 s |

  Spike's z-score + `find_peaks` design already matches the most sophisticated open-source fusion (reactorlab's z-scored chat + audio). Spike goes further with emote share and laughter.
- [I] cliptron's best settings concentrating at the smallest window (30 s) and separation (45 s) means its grid was too coarse at the low end. Shorter windows (10–20 s) were never tested, so the true optimum may be lower.
- [I] cliptron's "35–44 s lag" is measured from the **start of a human clip** to the chat peak. It is not event-to-reaction time. Per Twitch's Create Clip docs (Q5), a default clip covers about 25 s before the click to about 5 s after. So that figure includes about 25–30 s of clip pre-roll, and the real event-to-chat-peak lag is roughly 10–19 s. That fits cliphunter's "10–20 seconds" (Q4) and suggests Spike's 8 s shift may be slightly short. This needs measuring on Spike's own data.
- [I] sqrtminustwo's "single-message agreement ratio" is a cheap feature Spike lacks. It catches "?" floods and copypasta waves even when total rate barely rises, which matters in small chats.

### Gaps
- GitHub search found no repos under the names "TwitchChatAnalyzer", "highlight-finder", "LiveStreamHighlights", or a Twitch "reactorlab" beyond windycityassassin's. Older well-known repos may exist under names my queries did not hit.
- yakiya51/TwitchHighlightDetector and mhuber161/twitch-chat-highlights have no README and I did not read their code.
- No open-source project other than cliptron publishes an evaluation.

## Q2. Commercial products: what they disclose about chat use

### Takeaway
Vendors disclose signal *types* but no parameters. Twitch Auto Clips names "excitement" and "funny banter". ClipGPT shows "High chat excitement" labels. Eklipse and Streamlabs are primarily game-event and audio detectors.

### Cited Findings
- **Twitch Auto Clips** was announced at TwitchCon 2025 (Oct 17). It creates clips "based on the best parts of your stream using AI", from signals such as "positive excitement from the stream or funny banter". Alpha testing started the following month, behind a waitlist. Auto Clips get captions automatically and can be turned off. Twitch planned splicing "to eliminate dead space or combine great moments". [V] — [Twitch blog](https://blog.twitch.tv/en/2025/10/17/ten-years-of-twitchcon-here-s-what-we-announced-in-san-diego/)
- **"Twitch, Clip That"** is a voice command that clips live. Captions are on by default for Clip That and Auto Clips, and the toggle is in Creator Dashboard > Settings > Stream > Clip Settings. [C, from search snippets of Twitch help] — [Clips Settings](https://help.twitch.tv/s/article/clips-settings?language=en_US), [How to use clips](https://help.twitch.tv/s/article/how-to-use-clips?language=en_US&language=fi%3D)
- Third-party descriptions say Twitch Auto Clips keys off "chat velocity, emote usage, and subscriber activity spikes". This is not confirmed by Twitch. [C] — [StreamChat AI blog](https://streamchatai.com/blog/twitchs-new-ai-stream-summaries-and-auto-clips-what-they-actually-mean-for-your-channel); [Eklipse blog](https://blog.eklipse.gg/beginner-guide-2/how-to-get-more-clips-on-twitch.html)
- **StreamLadder ClipGPT**:
  - Analyzes the whole VOD for "engaging chat interactions, intense highlights, or chaotic reactions".
  - Gives a 0–100 virality score per moment.
  - Claims "11 million clips made by 1 million streamers".
  - Signal breakdown is not disclosed. [V] — [ClipGPT page](https://www.streamladder.com/clipgpt)
  - Search snippets mention UI labels "High chat excitement" and "Emotional spike detected", and "chat velocity spikes" for Just Chatting. [C] — [StreamLadder](https://www.streamladder.com/clipgpt/ai-clipping)
- **Eklipse**:
  - Help docs describe object detection and OCR for "kills, boss fights", plus a "Clip it!" voice command. Chat use is not documented. [V] — [Eklipse help](https://eklipse.gg/help/how-does-eklipse-work/)
  - Marketing says it scores "laughter, shouting, and sudden volume changes" alongside gameplay, and that a newer engine handles Just Chatting reactions. [C] — [Eklipse vs StreamLadder](https://eklipse.gg/compare/eklipse-vs-streamladder/)
- **Streamlabs AI Game Highlighter** detects game events ("eliminations, knockdowns, shield drops, gunshots"), "emotional cues", and mic activity. A search snippet says the Highlighter became "GHUB Replay". [C] — [Streamlabs](https://streamlabs.com/content-hub/post/streamlabs-ai-game-highlighter)
- **Sizzle** is described (by a competitor) as clipping on in-game events. [C] — [Eklipse: Sizzle alternatives](https://eklipse.gg/compare/sizzle-alternatives/)
- **KoalaVOD** is described as analyzing "VOD chat activity to automatically detect hype moments". [C] — [AlternativeTo](https://alternativeto.net/software/koalavod)
- **ClipMe** (vendor blog) says a "roughly 10-hour stream produced about 50 ranked clips in around 5 minutes". [C] — [ClipMe](https://clipme.com/blog/chat-velocity-viral-moments)

### Inferences
- [I] No vendor publishes accuracy against human clips. cliptron's eval method (Helix clips as labels) is the only public benchmark design found.
- [I] Game-event vendors (Eklipse, Sizzle, Streamlabs) are a different branch from chat-first tools. For funny Just Chatting content, the chat-plus-audio products (ClipGPT, ClipMe, KoalaVOD) are the closer analogues to Spike.

### Gaps
- I did not verify Athenascope's status (likely defunct) or Medal's and Clipbot's detection signals.
- I did not check Nightbot, Fossabot, or Firebot `!clip` docs. [I] These presumably call Helix Create Clip, so they inherit its window (Q5).
- Twitch has not published the exact Auto Clips signals or its general-availability (GA) status as of 2026-10. No primary source was found beyond the 2025 announcement.

## Q3. How human clippers find moments, and funny vs hype

### Takeaway
Practitioner guides boil down to: scrub the timeline for chat spikes, then label the spike by emote family. Laugh walls (KEKW/LUL/OMEGALUL/ICANT/LOL) mean funny. Pog walls and caps "HOW" mean hype. I found no primary Reddit or clipping-agency workflow source.

### Cited Findings
- A "LUL spike" is a "wall of LUL, LULW, KEKW, OMEGALUL, ICANT, and 'LOL'" and signals "a fail, a roast, or a clean joke". A "POG spike" is POG/POGGERS/PogU, "INSANE", "NO WAY", and caps "HOW". [C, vendor blog] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
- Hype is scored 0–100 from laugh/hype emote ratio, meme-phrase count, caps-lock ratio, and message-length distribution. "Hype 80+ is almost always clipworthy" and "30 is usually noise". [C] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
- When scanning a VOD, look for "chat spikes, category changes, raids, long fights, boss attempts, overtime rounds, and sudden camera reactions". Use AI to make a shortlist, then review each candidate like an editor. [C] — [Fragcut](https://fragcut.io/blog/how-to-turn-twitch-vods-into-clips)
- One editor workflow: the editor presses a button live when something funny happens, then later finds the marker in the VOD, rewinds a few seconds, and clips. [C] — [AlternativeTo listing summary via search](https://alternativeto.net/software/koalavod)
- Community emote taxonomies already used as code (joaohenggeler): Funny vs Pog vs Scary vs Sad vs Weird ("?"-floods, WTF, bruh) vs Surprise (D:). [V] — [config.json.template](https://github.com/joaohenggeler/twitch-chat-highlights/blob/HEAD/Source/config.json.template)

### Inferences
- [I] Funny differs from hype mainly in emote family: laugh tokens vs Pog/caps tokens. Spike's `chat_hype` (emote share) should be split into a laugh-share channel and a hype-share channel. A "?"-flood or "Weird" channel catches the cringe/awkward-funny class.

### Gaps
- No Reddit (r/LivestreamFail) threads or clipping-agency SOPs were retrieved. Searches returned only vendor SEO content. A Reddit-specific fetch would close this.

## Q4. Spam, raid, and bot filtering; chat size; languages; emote-only; lag values

### Takeaway
Everyone names raids, sub trains, and bot spam as the main false positives, but no public code I read filters them. cliptron's author says "Raids and emote spam outrank real clips". Published lag values range from "≥10 s" to "10–20 s". For human clip starts the range is 35–45 s.

### Cited Findings
- False-positive sources: sub-train identical messages, raid messages, "lag complaints", and spam bots. None are quantified. [C] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
- Suppress "raids, sub trains, streamer-prompted chat moments". [C] — [ClipMe](https://clipme.com/blog/chat-velocity-viral-moments)
- "Raids and emote spam outrank real clips". [V] — [cliptron journal](https://github.com/infectedresearch/cliptron/blob/HEAD/journal.md)
- Recipe: buckets of "5–10 seconds", a "rolling baseline: median or exponentially weighted average over the last several minutes", and a score as a "multiple of baseline (or a z-score)". [C] — [ClipMe](https://clipme.com/blog/chat-velocity-viral-moments)
- Rolling average over "the last 30-60 seconds" with a "3× is a common threshold" spike rule. [C] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
- Small chats: "A stream with 0.5 messages/sec baseline can't spike meaningfully". [C] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
- Lag values found:
  - ClipMe: "A spike at 1:42:10 usually means the moment started at 1:42:00 or earlier", so at least 10 s. [C] — [ClipMe](https://clipme.com/blog/chat-velocity-viral-moments)
  - cliphunter: "10-20 seconds". [C] — [cliphunter.gg](https://cliphunter.gg/blog/twitch-chat-spike-detection)
  - cliptron: 35–45 s, measured against human clip start. [V] — [agent.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/agent.py)
- Stream latency rule of thumb "used to be 11 seconds", and low-latency mode is now the default. [C, HN comment] — [HN](https://news.ycombinator.com/item?id=44101507)
- Replay sync hazards:
  - Chat rendered for a clip appeared "about 30-40 seconds in front of the clip". No maintainer explanation was given. [V] — [TwitchDownloader #1285](https://github.com/lay295/TwitchDownloader/issues/1285)
  - "VOD chat is out of sync (a minute behind)". [C, title only] — [Twitch dev forum](https://discuss.dev.twitch.com/t/vod-chat-is-out-of-sync-a-minute-behind/24586)
  - Disconnect Protection screens delay chat by the outage length. [C, search snippet] — [TwitchDownloader issue](https://github.com/lay295/TwitchDownloader/issues/1285)
- Emote handling:
  - sqrtminustwo weights 7TV emotes ×2 vs plain messages ×1 and supports `excluded_words`. [V] — [TwitchAutoClipper.py](https://github.com/sqrtminustwo/twitch_auto_clipper/blob/HEAD/twitch_auto_clipper/TwitchAutoClipper.py)
  - Fullonibus plans a Twitch + 7TV + FFZ emote dictionary. [V] — [README](https://github.com/Fullonibus/twitch-highlight-detector)

### Inferences
- [I] Cheap filters worth adding to Spike, since none of the reviewed tools ship them:
  - Drop messages from known bots and from the sub/raid USERNOTICE system events. GQL replay exposes message types.
  - Count unique chatters per bin rather than messages.
  - Cap each user's contribution per bin.
  - Down-weight bins inside 60 s after a raid event.
- [I] Per-VOD z-scoring (Spike) handles different chat sizes better than fixed thresholds (Vladshmalii's 50 msgs/10 s). But below about 0.5 msg/s, chat should get a lower fusion weight than audio and laughter. A Poisson-style significance test would handle this better than a z-score at low counts.
- [I] Lag may differ per channel and over time, because of low-latency mode and sync bugs. Spike could estimate it per VOD by cross-correlating chat rate with audio loudness or laughter onsets, the "learn the offset" step cliptron lists as future work.

### Gaps
- No multilingual handling was found in any tool. Laugh tokens in other languages ("www", "kkkk", "jajaja", "xD", "ㅋㅋㅋ") are not covered by any list I read.
- There is no measured distribution of event-to-chat-peak lag beyond cliptron's clip-start-based number.

## Q5. Clip length and placement relative to the chat peak

### Takeaway
Tools put most of the clip *before* the chat peak. reactorlab uses 8 s before and 20 s after an audio/chat peak. Human Twitch clips (Create Clip default) cover about 25 s before the click to 5 s after. cliptron finds chat peaks about 35–45 s after human clip starts, with 60 s clips.

### Cited Findings
- Twitch Create Clip:
  - "captures up to 90 seconds". For example, a call at 4:00 captures "approximately the 2:35 mark to approximately the 4:05 minute mark".
  - "By default, Twitch publishes up to the last 30 seconds of the 90 seconds window."
  - The `duration` param ranges 5–60 s, default 30.
  - [V] — [Twitch API reference, Create Clip](https://dev.twitch.tv/docs/api/reference/#create-clip)
- Default 30 s on mobile vs a 90 s editor window on desktop, publishable 5–60 s. [C] — [search summary of guides](https://blog.eklipse.gg/streaming-tips/how-to-clip-on-twitch-as-a-viewer.html)
- reactorlab: `--pre 8 --post 15` in the README example, and defaults `pre 8.0` / `post 20.0`. [V] — [cli.py](https://github.com/windycityassassin/reactorlab/blob/HEAD/clipping/src/clipping/cli.py)
- cliptron:
  - Detector spans are 60 s from the bin start, with no back-shift.
  - Agent fallback clips are 35 s (`start_s + 35`).
  - `render_clip` allows 5–180 s.
  - The agent snaps boundaries to Whisper segment edges, giving median boundary error 28.6 s vs 30.8 s for the detector.
  - [V] — [agent.py](https://github.com/infectedresearch/cliptron/blob/HEAD/src/clipper/agent.py), [README](https://github.com/infectedresearch/cliptron/blob/HEAD/README.md)
- sqrtminustwo waits `clipable_wait=10` s after the trigger before calling Create Clip. That shifts the 30 s window to about 15 s before the trigger to 15 s after. [V] — [TwitchAutoClipper.py](https://github.com/sqrtminustwo/twitch_auto_clipper/blob/HEAD/twitch_auto_clipper/TwitchAutoClipper.py)
- cliptron's human clips have a median duration of 60 s on the first VOD. [V] — [journal.md](https://github.com/infectedresearch/cliptron/blob/HEAD/journal.md)

### Inferences
- [I] A defensible default for Spike, taking the chat peak as the reference point:
  - Start 20–30 s before the (unshifted) chat peak, end 5–10 s after.
  - Snap both edges to speech or silence boundaries. Speech snapping was the one placement improvement cliptron measured.
  - This matches the window human clippers produce with the default Twitch clip button.
- [I] Spike's 8 s shift plus an LLM judge choosing boundaries is roughly the cliptron hybrid. The main missing pieces, ranked:
  1. An evaluation using Helix clips as labels (moments merged at 30 s gap, views ≥5, R@10).
  2. Laugh vs hype emote split plus a "?"-flood channel.
  3. Unique-chatter and raid/sub/bot filtering.
  4. Per-VOD lag estimation.

### Gaps
- I found no practitioner source that states clip placement relative to a chat peak in seconds, other than reactorlab's defaults and the Twitch button semantics.
