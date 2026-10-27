# Audio and Visual Signals for Detecting Clippable Moments in Anime (no chat)

Scope note: research run of 15 tool calls (Oct 2026). "Verified" means read in a source this session. "Inferred" means my reasoning or recalled knowledge, not confirmed by a source here. CPU cost figures are inferred estimates unless a source is cited; no source measured per-episode cost.

## 1. Finding and dropping non-clippable segments (OP/ED, recaps, previews, eyecatches, sponsor cards)

### Takeaway
Use a layered chain, cheapest first: (1) AniSkip API lookup by MAL ID + episode, (2) embedded chapters (many anime releases name chapters "Opening"/"Ending"/"Preview"), (3) Chromaprint fingerprint matching across 2+ episodes of the same season, (4) ffmpeg blackdetect/silencedetect near the end for credits, (5) subtitle regex for recap/preview cards. This is exactly the chain the mature Jellyfin intro-skipper plugin runs (chapters, then Chromaprint, then subtitle/black-frame fallbacks), and it has an anime-specific "preview derived from credits end" rule.

### Cited Findings
- AniSkip public API: `GET https://api.aniskip.com/v2/skip-times/{animeId}/{episodeNumber}` (v1 also exists), plus `relation-rules/{animeId}` for mapping episode numbering across related entries. API version 2.0.576. [AniSkip API docs](https://api.aniskip.com/api-docs)
- AniSkip is keyed by MyAnimeList ID (AllAnime IDs can be resolved to MAL IDs). Example output for Solo Leveling ep 3: OP 130.531 to 220.531 s, ED 1326.58 to 1416.58 s (both 90 s long). Coverage is crowd-sourced; missing episodes must be submitted via their Discord. [synacktraa/ani-skip README](https://github.com/synacktraa/ani-skip)
- Plex's own intro/credits detection (as summarized by a 2026 project issue citing the intro-skipper wiki and Plex blog) uses three signals: Chromaprint audio fingerprints compared across episodes of a season (primary, for intros), ffmpeg `blackdetect` (credits start), and ffmpeg `silencedetect` (silence before credits). [media_preview_generator issue #157](https://github.com/stevezau/media_preview_generator/issues/157)
- Search windows used there: intros 15 s to 2 min long, inside the first 25% of the episode or first 10 min (whichever smaller); credits 15 s to 5 min long, typically in the last 25%. [media_preview_generator issue #157](https://github.com/stevezau/media_preview_generator/issues/157)
- Implementation pattern: two-pass Chromaprint (pass 1 fingerprint each episode in parallel with `fpcalc` from libchromaprint-tools, pass 2 compare fingerprints within each season). A user reported the detection is "very CPU intensive". [media_preview_generator issue #157](https://github.com/stevezau/media_preview_generator/issues/157)
- intro-skipper (Jellyfin) chain for Introduction and Recap: chapter analyzer first, then Chromaprint, first-wins. Chromaprint compares two episodes along one alignment and keeps the longest shared run; a run continues across gaps up to `MaximumTimeSkip`, and two neighbouring runs of at least 8 s each are joined across a longer gap if the gap is at most half the shorter run. This was added specifically because "a gag that changes every episode inside a fixed title sequence" split matches. [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- intro-skipper recap rule: a recap is built around a "sting" (earliest audio two episodes share in the recap window) and ends at the first black run of at least 2 s after the sting. [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- intro-skipper has an anime-specific option `AnimePreviewFromCreditsEnd`: the next-episode preview is derived as the span from the credits end to the episode end. [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- intro-skipper subtitle detection: regex over text subtitle cues (.srt, .ass, .ssa, .vtt, etc.), markup stripped. Recap: first matching cue in the recap window. Preview: matching cues in the last `MaximumPreviewDuration` seconds, preview runs from cue to episode end. Default recap pattern covers English, Japanese, Chinese, Korean and several European languages. Title cards are often subtitled only in translation tracks, so all subtitle languages are read by default. [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- intro-skipper's recap chapter regex was tightened in Oct 2026: on 197 English chapter titles, wrong matches dropped from 99 to 3 (titles like "The Last Supper" or "Earlier That Day" were previously misread as recaps). Lesson: anchor recap patterns to the start of the title. [intro-skipper repo commit log](https://github.com/intro-skipper/intro-skipper)
- intro-skipper's default black-frame threshold is 28 (server default per a commit note). [intro-skipper repo commit log](https://github.com/intro-skipper/intro-skipper)
- Chromaprint is "designed to identify near-identical audio"; Python bindings exist (pyacoustid). [acoustid/chromaprint](https://github.com/acoustid/chromaprint), [beetbox/pyacoustid](https://github.com/beetbox/pyacoustid)

### Inferences
- For Spike: AniSkip first (one HTTP call, zero compute), but it needs a MAL ID, so the UI needs a title/MAL lookup or the user's filename parsing. Fall back to Chromaprint only when the user loads 2+ episodes of the same season; a single episode cannot be fingerprint-matched.
- A dub (e.g., TeamFourStar abridged) often keeps a parody OP or none at all, so AniSkip (which indexes official releases) may give wrong times for parody dubs. Treat AniSkip as advisory and check that the window has music-dominant audio (see section 2) before cutting it.
- Eyecatches (2 to 5 s still card at the act break, usually near mid-episode) and sponsor cards ("This program is brought to you by...") are not covered by any source found. Heuristic (inferred): a near-static frame (very low frame difference) of 2 to 8 s, often with a short jingle, around 40 to 60% of runtime, bracketed by cuts; and recurring across episodes so Chromaprint or perceptual hash (PySceneDetect HashDetector style) matching would catch it.
- In fansub ASS files the OP/ED song lyrics usually sit in dedicated styles (names like "OP", "ED", "Romaji", "Kara") with `\k` karaoke tags. This is recalled, not verified this session, but if true it gives near-free OP/ED bounds from the subtitle file alone.
- CPU cost (inferred): `fpcalc` on a 24 min episode is seconds of CPU; blackdetect needs a full video decode (decode at low res with `-vf scale=160:-1` to make it a fraction of realtime); silencedetect is audio-only and very fast.

### Gaps
- No measured CPU times for fpcalc, blackdetect, or silencedetect on a 24 min episode.
- No source on AniSkip coverage percentage, or on whether it covers recap/preview types (v2 response schema names not fetched; recalled types are op, ed, mixed-op, mixed-ed, recap, but unverified).
- No source on eyecatch or sponsor-card detection.

## 2. Audio cues: music vs speech vs silence, BGM swells, insert songs, SFX bursts, shouting, laughter, comedic timing, loudness

### Takeaway
A general audio tagger (YAMNet or PANNs, AudioSet 521/527 classes) gives per-0.48 s probabilities for Speech, Music, Shout, Yell, Screaming, Laughter, Explosion, etc., on CPU. That one pass covers most audio cues. Loudness alone correlates with highlights but overlaps heavily between highlight and non-highlight clips, so use it as one feature, not a gate.

### Cited Findings
- YAMNet predicts 521 AudioSet classes, built on MobileNet v1. Input is 16 kHz mono; it frames audio into 0.96 s windows with 0.48 s hop and returns scores (N x 521), 1024-d embeddings, and a 64-band log-mel spectrogram. [Kaggle YAMNet model card](https://www.kaggle.com/models/google/yamnet), [TensorFlow YAMNet tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio), [YAMNet README](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md)
- YAMNet's class list includes the human-voice classes relevant here: Speech, Conversation, Narration, Shout, Bellow, Whoop, Yell, Children shouting, Screaming, Whispering, Laughter, Giggle, Snicker, Belly laugh, Chuckle/chortle, Crying/sobbing. [TensorFlow YAMNet tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio)
- Dedicated laughter detector (jrgillick/laughter-detection, Interspeech 2021, PyTorch, MIT license): CLI `segment_laughter.py --threshold=0.5 --min_length=0.2` (defaults: probability 0.5, minimum laugh 0.2 s). Trained on Switchboard, evaluated on AudioSet. Lower threshold gives more recall and more false positives. [jrgillick/laughter-detection](https://github.com/jrgillick/laughter-detection)
- Sports highlight study (2026): highlight clips had higher RMS loudness (mean -26.9 dB vs -28.4 dB), higher peak loudness (-9.0 vs -10.1 dB), about +0.76 dB low-mid and +2.05 dB high-mid band energy. Distributions overlap heavily, "loudness alone is insufficient". Vocal audio was more informative than background sounds, the combination was best. An audio-only GRU beat several published audio-visual models (41.79 mAP), and simple audio+visual fusion was best overall (46.92 mAP). [Audio for Sports Highlight Detection, arXiv 2609.17923](https://arxiv.org/html/2609.17923)
- Audiovisual highlight detection (Amazon, 2021): visual features carry most information for summarization; adding audiovisual affect features and MFCCs improves over visual-only. [arXiv 2102.05811](https://arxiv.org/abs/2102.05811)
- Unsupervised highlight detection can be learned from audio recurrence: audio pseudo-highlights alone trained a model that beat visual-only pseudo-highlights on all three datasets tested. [arXiv 2407.13933](https://arxiv.org/html/2407.13933v2)
- Plex/intro-skipper use ffmpeg `silencedetect` to locate silence that precedes credits. [media_preview_generator issue #157](https://github.com/stevezau/media_preview_generator/issues/157)

### Inferences
- Laughter in anime is mostly diegetic (characters laughing), not a laugh track, so it is weaker evidence than in sitcoms. For an abridged parody dub like the TeamFourStar reference, the comedy lives in dialogue and timing, so laughter is a minor signal.
- Comedic timing detector (inferred, no source): a punchline pattern is speech, then a short gap (0.3 to 1.5 s of low speech probability or silence), then either a single short line, a shout, an SFX sting, or a music stinger. Compute from YAMNet Speech probability plus subtitle cue gaps. Treat it as a candidate end point, not a score.
- Music-to-speech ratio per window: OP/ED and insert-song montages are music-dominant with little speech; a dialogue clip like the reference is speech-dominant with low music. Use YAMNet Music vs Speech probabilities to (a) confirm OP/ED windows and (b) separate "hype/insert song" candidates from "dialogue/comedy" candidates, which need different clip lengths.
- BGM swell: rising short-term loudness (ffmpeg `ebur128` momentary/short-term LUFS) while Music probability stays high and Speech drops. "Sudden silence before a reveal": short-term LUFS drop of 15+ dB for 0.5 to 2 s inside a scene. Both thresholds are my guesses to tune on labeled episodes.
- Shout/Scream/Yell sums are a natural "intensity" feature for shounen fights and comedic overreactions alike (dubs shout a lot in comedy).
- CPU cost (inferred): 24 min = 1440 s gives about 3000 YAMNet frames; MobileNet v1 on 16 kHz audio typically runs many times faster than realtime on one CPU core, so expect well under a minute per episode. PANNs CNN14 is heavier (likely a few minutes on CPU); BEATs heavier still. Not measured.

### Gaps
- No source measured YAMNet, PANNs, or BEATs CPU speed per hour of audio.
- No anime-specific study linking any audio class to viewer engagement.
- No published comedic-timing (pause then punchline) detector found.

## 3. Visual cues: cut rate, motion/sakuga, impact frames, flashes, faces, chibi shifts, on-screen text

### Takeaway
PySceneDetect gives shot boundaries and per-frame content scores (HSV delta, edge delta) that double as a cheap motion/flash signal. Shot length (cut rate) and frame-difference energy are the practical CPU visual features. I found no source on sakuga, impact-frame, or chibi detection; those remain inferred heuristics.

### Cited Findings
- PySceneDetect 0.7.1 detectors and defaults: ContentDetector `threshold=27.0, min_scene_len=15` frames (weighted HSV deltas, edges weight 0 by default); AdaptiveDetector `adaptive_threshold=3.0, window_width=2, min_content_val=15.0` (rolling average, "can help mitigate false detections in situations such as fast camera motions"); HistogramDetector `threshold=0.05, bins=256` (Y channel); HashDetector `threshold=0.395, size=16, lowpass=2` (perceptual hash); ThresholdDetector `threshold=12` (fade to/from black, so it detects fades and black cards). [PySceneDetect detectors docs](https://www.scenedetect.com/docs/latest/api/detectors.html)
- ContentDetector writes per-frame metrics `content_val, delta_hue, delta_sat, delta_lum, delta_edges` to a stats file via StatsManager, so the same pass yields a continuous motion/flash curve, not just cuts. [PySceneDetect detectors docs](https://www.scenedetect.com/docs/latest/api/detectors.html)
- intro-skipper's credits analyzer uses keyframes, black-frame runs, frame differences via ffmpeg `signalstats`, and a "lettering gate" (text-on-screen check) to find credit rolls. [intro-skipper repo commit log](https://github.com/intro-skipper/intro-skipper)
- Visual features carried most of the information in a general audiovisual highlight model, with audio adding gains. [arXiv 2102.05811](https://arxiv.org/abs/2102.05811)

### Inferences
- Anime-specific caveat: anime is drawn "on twos/threes" (8 to 12 drawings per second) with many held frames, pans over still backgrounds, and limited animation in dialogue. Raw frame difference is spiky and low in dialogue, high in fights and camera pans. Use AdaptiveDetector (rolling ratio) for cuts, and smooth `content_val` over 1 to 2 s for motion energy.
- Sakuga/fight proxy: sustained high `delta_edges` + high `content_val` over several seconds with short shots (median shot under ~1.5 s). Optical flow (OpenCV Farneback at 320 px width, 6 to 8 fps sampling) is a better motion measure, but costs much more CPU than frame differencing; use it only on top candidate windows.
- Impact frames / flashes: single-frame or few-frame spikes in `delta_lum` (white flash, inverted/monochrome impact frame) where saturation collapses. Detect as `delta_lum` z-score above ~4 lasting under 3 frames. Photosensitivity-safe edits may have dimmed these in streaming releases.
- Chibi/comedy art-style shifts: no CPU-cheap detector known. A CLIP zero-shot prompt ("chibi super-deformed anime character", "comedic reaction face") on 1 fps sampled frames is plausible with a GPU, and slow-but-feasible on CPU for candidate windows only.
- Face close-ups: generic face detectors are trained on real faces and are unreliable on anime; anime-specific face detectors exist (e.g., lbpcascade_animeface, recalled not verified). Close-up detection could use the largest detected face box area / frame area.
- For the reference clip (dialogue comedy), visual signals are weak: the useful visual input is shot boundaries for clean start/end cuts, not motion.
- CPU cost (inferred): PySceneDetect at full 1080p decode is the bottleneck; downscaling (its `downscale` option or pre-scaled ffmpeg pipe) typically makes a 24 min episode run in a few minutes on a modern CPU.

### Gaps
- No source found for sakuga detection, impact-frame detection, chibi detection, or anime face detection accuracy.
- No measured PySceneDetect runtime for 24 min anime.

## 4. Dialogue cues from subtitles (ASS/SRT) or ASR, and choosing self-contained clip bounds

### Takeaway
Subtitle files give exact cue timing for free, so line density, exchange structure (turn-taking), exclamations, and gaps can be computed without Whisper. Self-contained clips should start and end on scene cuts (PySceneDetect) aligned to subtitle gaps, which matches what the reference Short does (one complete exchange ending on a punchline). Sources here cover subtitle extraction mechanics, not punchline scoring.

### Cited Findings
- ffmpeg can extract embedded text subtitle streams and sidecars (.srt, .ass, .ssa, .vtt, .sub, .smi, .sami) to WebVTT in one demux run; image subtitles (PGS/VobSub) cannot be decoded to text. Non-UTF-8 sidecars are silently dropped by ffmpeg unless re-encoded first (intro-skipper detects charset with UtfUnknown and writes a UTF-8 copy). [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- A muxer can store a subtitle cue up to about 10 s after its audio/video in Matroska; windowed reads need padding (intro-skipper uses 15 s). [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)
- Plain markup stripping and whitespace collapsing are applied before regex matching so multi-line cues read as one line. [intro-skipper docs/analysis.md](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)

### Inferences
- Exclamation density: count `!`, `?!`, all-caps words, and stutters/interjections per 10 s window. ASS lines also carry `\fs`/`\b1` override tags for emphasized shouts in fansubs (recalled).
- Back-and-forth exchange: ASS `Name`/`Actor` fields (when filled) or alternating short lines give turn counts. A rapid exchange (4+ alternating lines in ~15 to 30 s, each under ~2.5 s) ending in a short line followed by a gap is the shape of the reference clip. Without speaker fields, use pyannote diarization on the Whisper path (GPU helps).
- Signs/typesetting lines in ASS (styles named "Sign", positioned with `\pos`) are not dialogue and must be filtered out before computing density.
- Sub vs dub: for a dub, the English subtitle file (if any) may be "dubtitles" or may not match the dub script. Whisper on the dub audio is the reliable transcript; for a sub (Japanese audio), the subtitle file is the only usable English text.
- Clip boundary rule for self-contained clips: start at the first scene cut at or before the first line of the exchange (or the subtitle gap of 0.8 s+ before it); end 0.5 to 1.5 s after the punchline cue ends, snapped to the next scene cut if within ~1.5 s, so the reaction beat lands. Reject windows whose first line is a reply (starts with "And", "But", "Yeah", "So") or whose start shot is mid-action.
- Feed the windowed subtitle text plus cue timing to the optional LLM judge (Gemini/Claude) to rate "does this stand alone and end on a punchline", reusing Spike's existing transcript-judge stage.

### Gaps
- No source on punchline detection heuristics from subtitles.
- No source on ASS speaker-field fill rates in fansubs or official subs.

## 5. Published heuristics or open-source projects that clip anime automatically

### Takeaway
I found no open-source project dedicated to auto-clipping anime into Shorts. The closest reusable pieces are OP/ED/recap/preview detectors (AniSkip, intro-skipper, Plex-style Chromaprint pipelines) and general long-form-to-Shorts tools that rely on Whisper plus an LLM for highlight choice.

### Cited Findings
- Generic open-source Shorts generators use LLM highlight detection over Whisper transcripts plus auto vertical crop (GitHub topic "shorts-maker"; e.g., AI-Youtube-Shorts-Generator with `--num-clips`, `--aspect-ratio 9:16`, local or API mode). [GitHub topic shorts-maker](https://github.com/topics/shorts-maker), [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
- intro-skipper is actively maintained (1,753 commits, last commit Oct 25, 2026) and ships a labeled-file evaluation tool (`tools/CreditsRunner`) for scoring detector changes against ground truth. [intro-skipper repo](https://github.com/intro-skipper/intro-skipper)
- Searches for anime highlight detection returned only general and sports highlight papers, no anime-specific dataset. [search results incl. arXiv 2501.16100, 2407.13933, 2102.05811](https://arxiv.org/abs/2501.16100)

### Inferences
- Spike's plan for anime would be novel in combining these. A practical scoring recipe (inferred): candidates from (a) subtitle exchange windows, (b) YAMNet intensity peaks (Shout+Scream+Explosion), (c) music-swell peaks with high motion; score each window by z-scored features; veto OP/ED/recap/preview/eyecatch spans; then the optional LLM judge picks and bounds dialogue clips.
- The CreditsRunner pattern (labeled episodes + scripted diff of detector changes) is the same eval shape Spike already uses for Twitch VODs (`scripts/eval_stage7.py`), so a small hand-labeled anime set (e.g., 5 to 10 episodes with known popular Shorts timestamps) is the way to tune thresholds.

### Gaps
- No AMV editor guides or anime-clipping blog posts were found within the call budget.
- No public dataset of anime Shorts with source-episode timestamps; building one from channels like TeamFourStar (Short vs full episode) would be manual.
