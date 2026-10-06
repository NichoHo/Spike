# How Existing Products and Open-Source Projects Detect Highlight/Funny Moments

Status legend: **[V]** verified this session from primary source (repo code, official docs, API). **[C]** claimed by vendor marketing/help docs, method not independently checked. **[3P]** third-party review/blog claim. **[R]** recalled from training data, not re-checked this session. **[I]** inference.

Research date: 2026-10-01.

## Q1. Commercial products: what signals do they claim, and how good are the picks?

### Takeaway
Every commercial clipper discloses only marketing-level signal lists; none publishes a method paper, eval, or patent found in this pass. Talking-head tools (OpusClip, Klap, Vizard, Munch, Submagic-class) are transcript+LLM first, with OpusClip's ClipAnything adding visual/audio/sentiment. Gaming tools (Medal, Eklipse, StreamLadder, Twitch Auto Clips, ex-Powder) lean on game-event APIs or kill-feed vision, audio shouts/laughs, and chat spikes. The consistent user complaint is that transcript-first tools miss silent visual moments and cut jokes before the punchline.

### Cited Findings
**OpusClip**
- [C] ClipAnything "analyzes each frame through visual, audio, and sentiment cues, identifying objects, scenes, actions, sounds, emotions, texts," then "each scene is then rated based on its virality potential"; users can steer with a text prompt. No scoring method disclosed. — [OpusClip help: ClipAnything](https://help.opus.pro/docs/article/9947095-clip-anything)
- [3P] Virality score is 0 to 99, described as built from hook strength, emotional flow, perceived value, trend alignment; reviewers say it ranks clips within one video but does not predict absolute views ("a 92 won't reliably beat a 78"). — [datastudios.org](https://www.datastudios.org/post/opus-clip-clipanything-video-repurposing-virality-scoring-and-pricing); [ssemble review](https://www.ssemble.com/blog/opus-clip-review-2026)
- [3P] Third-party review says OpusClip's pipeline is GPT-4-powered transcript analysis. Not confirmed by OpusClip itself. — [therundown.ai](https://www.therundown.ai/tools/opus-clip)
- [3P] Reddit-sourced complaints: cuts jokes before the punchline, omits the context sentence, low-score clips sometimes outperform "winners." — [eesel.ai review roundup](https://www.eesel.ai/blog/opusclip-reviews)
- [3P] Gaming test: OpusClip "consistently picked commentary-heavy moments over gameplay moments"; a silent 1v3 clutch was missed. Source is a competitor blog, so biased. — [snowball-for-streamers](https://snowball-for-streamers.com/en/blog/opus-clip-doesnt-work-for-gaming)

**Klap / Vizard**
- [C] Klap (on its own blog) says its AI evaluates "sentence meaning, delivery pace, and topic shifts." — [klap.app blog](https://klap.app/blog/vizard-ai-review)
- [3P] Vizard's hook detection "hit or miss"; picks need trimming; mixed user reviews (some call it "very garbage"). — [ngram.com](https://www.ngram.com/blog/vizard-alternatives-tested); [Capterra Vizard reviews](https://www.capterra.com/p/10009818/Vizard/reviews/)

**Eklipse** (gaming streams)
- [C] Help center lists three signals: visual ("key in-game actions and on-screen events"), audio ("shouts, laughs, and fast commentary"), game data ("kills, wins, and other key stats"); claims 3000+ games; unsupported games fall back to Voice Command manual flagging. No chat signal is listed. — [Eklipse help](https://eklipse.gg/help/how-does-the-ai-actually-detect-a-highlight-in-my-stream/)
- [C] New "Gameplay Intelligence" engine (from 2026-06-01) adds game-state events (kill feed, objectives), audio source separation (voice vs in-game), on-screen "action density," and continuity (streak/comeback). Eklipse admits the old engine was "trigger event (kill feed or audio spike) + fixed 15 to 30 s window," which "falls apart" outside clean kill-feed games. — [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html)

**StreamLadder (ClipGPT)**
- [C] Signals: chat activity spikes, voice excitement/emotion, in-game events (multi-kills, boss fights), specific emote reactions. — [StreamLadder blog](https://www.streamladder.com/blog/twitch-auto-clips-your-guide-to-automatically-capturing-stream-highlights)

**Medal**
- [C] Auto clipping fires when "the game reports a kill, ace, goal, or win," i.e. game-integration events, not vision; built on the game's replay system; Streamer Mode in some games can block detection. Supported list includes Rocket League, LoL, GTA V, Dota 2, Roblox, PUBG, CS2, Fortnite, Valorant, and others. — [Medal auto-clipping](https://medal.tv/auto-clipping); [Medal support](https://support.medal.tv/support/solutions/articles/48001167701-what-is-automatic-event-detection-auto-clipping-)

**Powder.gg**
- [3P] Shut down early 2026 after seven years (financial). Its "Universal Game Support" mode listened to audio "for shouts and volume spikes as a rough stand-in for a kill feed." Source is a competitor (GameClipper Advanced), which itself reads kill feeds with OCR locally. — [gameclipperadvanced.com](https://gameclipperadvanced.com/blog/powder-gg-alternatives/)

**Twitch native**
- [V] "Featured Clips" are hand-picked by streamer/editors/mods; discovery favors recent, engaging featured clips. No automatic picking. — [Twitch help](https://help.twitch.tv/s/article/featured-clips?language=en_US)
- [3P] Twitch announced "Auto Clips" at TwitchCon Rotterdam (2026-05-30): uses chat activity, voice tone, on-screen events; voice trigger "Twitch Clip That"; alpha, English only. Not confirmed against a Twitch primary source in this pass. — [streamer.guide](https://streamer.guide/blog/twitchcon-rotterdam-2026-new-features-1440p-clips-guilds); [streamchatai.com](https://streamchatai.com/blog/twitchs-new-ai-stream-summaries-and-auto-clips-what-they-actually-mean-for-your-channel)

### Inferences
- [I] The industry converges on the same cheap signal stack Spike can run locally: transcript + LLM ranking, audio loudness/laughter/shout, chat rate (when present), and game events. "Visual" claims by vendors are vague; for gaming, the concrete version is kill-feed OCR or game APIs.
- [I] "Virality score" is a within-video ranking from an LLM rubric, not a validated predictor. Spike can copy the rubric pattern (score + hook + reason) at zero cost, as open-source repos do.
- [I] For funny moments specifically, the main failure mode reported (cut before punchline, missing setup) is a boundary problem, not a detection problem. Boundary handling deserves as much effort as scoring.

### Gaps
- No engineering blogs, patents, or interviews disclosing actual models/weights found for OpusClip, Klap, Vizard, Munch, Quso/vidyo.ai, Submagic, Descript. Patent search (Google Patents) not done in this pass.
- Munch, Quso/vidyo.ai, Submagic, Descript not individually checked; assume transcript+LLM class [I].
- No vendor publishes precision/recall. Only quality evidence is reviews, many written by competitors.

## Q2. YouTube "Most replayed" heatmap and timestamped comments as signals

### Takeaway
The heatmap is readable with yt-dlp today (field `heatmap`, 100 normalized segments, no API key), it is the only no-chat crowd signal that works on any popular YouTube video, and one CHI 2025 paper found highlights built from it were rated comparable to human-made ones. It is absent on low-view videos and comes from an unofficial internal player response, so it can break and sits outside the official API. Timestamped comments via YouTube Data API are a legitimate complement at 1 quota unit per 100 comments.

### Cited Findings
- [V] yt-dlp info dict documents `heatmap`: "A list of dictionaries" with `start_time`, `end_time` (seconds) and `value` ("normalized value ... float between 0 and 1"). — [yt-dlp common.py](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/extractor/common.py)
- [V] yt-dlp's YouTube extractor tests expect `'heatmap': 'count:100'`, i.e. 100 equal segments per video regardless of length (a 3 h VOD gives ~108 s bins). — [yt-dlp youtube/_video.py](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/extractor/youtube/_video.py)
- [V] Feature was requested in yt-dlp issue #3888 (2022-05-27). — [GitHub issue](https://github.com/yt-dlp/yt-dlp/issues/3888)
- [3P] Heatmap is not in the official public API, is not available for every video, appears only after enough viewing activity. — [search summary of Apify actor page](https://apify.com/karamelo/youtube-most-replayed-scraper-heatmap-extractor)
- [V, abstract only] CHI 2025 paper "Generating Highlight Videos of a User-Specified Length using Most Replayed Data": user studies found auto highlights "indistinguishable from those created by humans in viewing experience." Full text blocked (403). — [ACM DL](https://dl.acm.org/doi/10.1145/3706598.3713880)
- [3P, abstract] "Can we predict the Most Replayed data...?" built YTMR500 (500 videos); predicting it is hard for human annotators, their model beat humans. — [arXiv 2309.06102](https://arxiv.org/pdf/2309.06102)
- [V] arXiv 2607.01400 (48 videos, 11 categories incl. comedy/gaming/reaction): predicted-fMRI signals do not predict replay heatmaps (partial r = +0.058, p = 0.23), "not above simple loudness/motion baselines"; results required position control, implying a strong position effect (e.g. start-of-video). Authors built their own heatmap acquisition "robust to YouTube's SABR streaming." — [arXiv 2607.01400](https://arxiv.org/abs/2607.01400)
- [V] YouTube Data API `commentThreads.list`: 1 quota unit per call, up to 100 threads per page, `order=time|relevance`. — [YouTube Data API docs](https://developers.google.com/youtube/v3/docs/commentThreads/list)
- [R] Default Data API quota is 10,000 units/day per project; public comments readable with an API key (no OAuth). So ~1M comments/day nominal. Verify on the quota docs page.
- [R] YouTube ToS forbids accessing the service by automated means except via public search engines or with permission; yt-dlp use is a ToS grey zone, not illegal per se in most places. Not legal advice; verify current ToS text.

### Inferences
- [I] Heatmap is a replay/seek signal, not a "funny" signal. Peaks also mark skipped-to content (sponsor end, music drop, the answer to a question). Use it as a prior to boost transcript/audio candidates, not as a sole detector.
- [I] 100-bin resolution is fine for 10 to 30 min videos (6 to 18 s bins) but too coarse for multi-hour VODs; pair with audio/transcript to localize within a bin.
- [I] Timestamped comments ("2:34 lmao") parsed with a regex like `\b(\d{1,2}:)?\d{1,2}:\d{2}\b` plus a laugh/emote lexicon give a per-moment "funny" label that the heatmap lacks. Best on popular videos; cost is trivial within quota.
- [I] Both signals only exist for already-published, already-watched videos, so they help clipping other creators' or own back-catalog videos, not fresh uploads.

### Gaps
- No published comparison of heatmap peaks vs human-chosen funny moments specifically.
- Exact behavior of heatmap availability thresholds is undisclosed by YouTube.
- Did not read the CHI 2025 full text for effect sizes.

## Q3. Open-source projects: method, stars, license, activity

### Takeaway
Nearly all popular open-source "OpusClip alternatives" are Whisper transcript + LLM prompt ("find viral moments, return timestamps + score + reason"), increasingly with a local Ollama option. ClipsAI is the exception (TextTiling topic segmentation, no "funny" detection) and is stale. Small repos explore heatmap, chat velocity, and YOLO/voice triggers; one (cliptron) actually measured against human Twitch clips and found a tuned chat-rate baseline beat an LLM agent.

### Cited Findings
Stars/license/last push pulled from GitHub API on 2026-10-01 [V].

| Repo | Stars | License | Last push | Detection method |
|---|---|---|---|---|
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | 5,857 | MIT | 2026-09-30 | [V README] Gemini 3.1 Flash-Lite over transcript + scene boundaries picks 3 to 15 moments; `LLM_BASE_URL` swaps in Ollama/LM Studio/vLLM; faster-whisper; MediaPipe+YOLOv8 reframing |
| [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) (redirect from SamurAIGPT) | 5,191 | MIT | 2026-09-29 | [V README] Whisper/faster-whisper + OpenAI/Gemini ranking on rubric: hooks, emotional peaks, opinion bombs, revelations, conflict, quotable lines, story peaks; outputs score + hook + reason; dedupes overlaps |
| [modelscope/FunClip](https://github.com/modelscope/FunClip) (Alibaba) | 6,359 | MIT | 2026-09-16 | [3P/README summary] FunASR Paraformer ASR + CAM++ speaker ID; v2 "LLM clipping" sends SRT + prompts to Qwen/GPT, parses timestamps. Chinese-first. — [repo](https://github.com/modelscope/FunClip) |
| [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | 544 | MIT | 2024-01-17 (stale) | [3P docs] TextTiling with BERT embeddings on Whisper transcript, finds topic shifts, not highlights. — [ClipsAI docs](https://www.clipsai.com/references/clip) |
| [Shaarav4795/ClippedAI](https://github.com/Shaarav4795/ClippedAI) | 213 | none asserted | 2026-09-04 | [V README] clipsai segments + heuristic "engagement score" (engagement-word ratio 30% weight, etc.); Groq LLM for titles only |
| [fralapo/clippyme](https://github.com/fralapo/clippyme) | 50 | MIT | 2026-09-30 | [V README] transcript + Gemini choose/rank moments; PySceneDetect; fallback splits without Gemini |
| [VadlapatiKarthik/autoclipper](https://github.com/VadlapatiKarthik/autoclipper) | 36 | not stated | n/a | [3P README] YouTube heatmap ("audience retention"), Twitch/Kick chat spikes, timestamped comments |
| [nawirwii/youtube-heatmap-clipper](https://github.com/nawirwii/youtube-heatmap-clipper) (fork of 0xACAB666/yt-heatmap-clipper) | 1 | MIT | 2026-09-28 | [V README] clips YouTube Most Replayed peaks; optional faster-whisper subs, local LLM |
| [windycityassassin/reactorlab](https://github.com/windycityassassin/reactorlab) | n/a | n/a | n/a | [3P] live Twitch: score = α·audio_z + β·chat_z, audio RMS dBFS and chat velocity each z-scored vs own rolling baseline |
| [infectedresearch/cliptron](https://github.com/infectedresearch/cliptron) | 0 | not stated | n/a | [V README] chat (Twitch GQL VOD replay) + Whisper transcript; evaluated against human Helix clips as ground truth |
| [bendawg2010/Auto-clipper](https://github.com/bendawg2010/Auto-clipper) | n/a | n/a | n/a | [3P] YOLO object detection, pixel analysis, voice trigger "clip it"; local |
| [lxgicstudios/lxgic-clipper](https://github.com/lxgicstudios/lxgic-clipper) | n/a | n/a | n/a | [3P] claims audio spikes, chat velocity, game-state changes, visual motion |

- [V] cliptron eval: clips clustered into moments with 30 s gaps, clips with at least 5 views. On 4 VODs / 13 moments: LLM agent Recall@10 = 0.708 vs tuned baseline 0.917; median boundary error 28.6 s vs 30.8 s; agent costs $0.10 and 15.6 s per VOD vs ~$0 and <1 s. On 13 VODs / 67 moments, tuned chat-rate baseline Recall@10 = 0.360, 6.0x over random. "Human moments cluster at chat peaks (55% in top 10%)." Tiny sample, 0 stars, treat as indicative. — [cliptron](https://github.com/infectedresearch/cliptron)

### Inferences
- [I] Open source offers no novel "funny" detector. The real options are: LLM-on-transcript (handles verbal humor, misses visual/silent humor), audio z-score (laughter/shouts), chat/heatmap/comment crowd signals. Spike's differentiation would be fusing these, plus a laughter classifier, which none of the top repos do.
- [I] cliptron hints that where crowd signals exist, a tuned crowd baseline beats an LLM at recall; the LLM's value is in topical or requested moments and in titles/boundaries.
- [I] Local-LLM support (openshorts, heatmap-clipper) shows the $0 path is viable: Ollama for ranking, faster-whisper for ASR.

### Gaps
- Stars/licenses for reactorlab, Auto-clipper, lxgic-clipper not fetched.
- None of the big repos (openshorts, AI-Youtube-Shorts-Generator, FunClip) publish any evaluation of pick quality.
- Did not search Hugging Face / papers-with-code highlight-detection models (e.g. moment-retrieval models); out of scope for products, may be covered by another researcher.

## Q4. Game-specific detectors (kill feed OCR/templates, Medal/Powder approach)

### Takeaway
Two families: official game-event integrations (Medal, Eklipse "game data," likely Overwolf-style APIs) and screen reading of the kill feed (GameClipper Advanced OCR, Eklipse's vision layer). Audio-spike fallback (Powder Universal mode, Eklipse old engine) is the generic option and is described by vendors themselves as rough.

### Cited Findings
- [C] Medal: game reports kill/ace/goal/win, clip saved around it; Streamer Mode can block it. — [Medal](https://medal.tv/auto-clipping)
- [3P] GameClipper Advanced reads on-screen kill feeds via OCR, offline, $19 one-time. — [gameclipperadvanced.com](https://gameclipperadvanced.com/blog/powder-gg-alternatives/)
- [C] Eklipse game-state events from kill feed entries, objective captures, eliminations. — [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html)
- [3P] Powder Universal mode used audio shouts/volume spikes as kill-feed stand-in. — [gameclipperadvanced.com](https://gameclipperadvanced.com/blog/powder-gg-alternatives/)
- [3P] Medal user feedback requests customizable pre/post-event clip timing, implying fixed windows today. — [Medal feedback #4472](https://feedback.medal.tv/4472)

### Inferences
- [I] Game-event APIs need the game running locally during recording; for a VOD/YouTube clipper like Spike, only kill-feed OCR/template matching on the video frames is applicable, and it is per-game work with UI/resolution brittleness.
- [I] Kills are "hype," not "funny." For a funny-moment clipper, game events are a secondary signal at best.

### Gaps
- Medal's exact integration mechanism (Overwolf GEP, Riot local API, log parsing) not confirmed this pass [R: likely mixed].
- No public accuracy numbers for any kill-feed OCR detector found.
