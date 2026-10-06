# Visual Signals and Multimodal Video LLMs for Funny/Highlight Moment Detection

Research date: 2026-10-01. "Verified" = read on an official/primary page this session. "Inferred" = my calculation or reasoning from cited numbers. Anything recalled from training data and not re-checked is marked "(recalled, unverified)".

## 1. Facial expression / reaction detection on facecams

### Takeaway
Cheap, CPU-friendly face tools exist (MediaPipe blendshapes, HSEmotion), and a smile/jaw-open spike on a facecam is a plausible "reaction" proposal signal. But in-the-wild FER accuracy is only ~60-65% on AffectNet, streamer facecams are small and badly lit, and no source found measures facecam signals alone as a highlight predictor. Treat it as one weak feature, not a detector.

### Cited Findings
- MediaPipe Face Landmarker outputs 52 ARKit-style blendshape scores (jaw open, eye blink, smile, etc.) from the face mesh, usable for expression detection. `mouthSmileLeft/Right` and `jawOpen` are among them. [Google MediaPipe Face Landmarker guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker); [Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)
- Face Landmarker reportedly runs 30+ fps CPU-only on modern hardware; one Android write-up reports ~8-12 ms with GPU delegate on Snapdragon 7-series. These are third-party claims, not official benchmarks. [pub.dev mediapipe_face_mesh](https://pub.dev/packages/mediapipe_face_mesh); [MVP Factory blog](https://mvpfactory.io/blog/wiring-android-s-camerax-to-a-quantized-face-mesh-model-for-real-time-ar-makeup)
- HSEmotion (now EmotiEffLib): EfficientNet/MobileNet FER models predicting basic emotions plus valence-arousal. Inference on a Snapdragon 888 phone CPU: 16±5 ms (mobilenet_7) to 59±26 ms depending on model. [HSEmotion paper](https://www.researchgate.net/publication/364625072_HSEmotion_High-speed_emotion_recognition_library); [GitHub EmotiEffLib](https://github.com/HSE-asavchenko/face-emotion-recognition)
- HSEmotion AffectNet accuracy: mobilenet_7 64.71% (7 classes); enet_b0_8_best_afew 60.95% (8 classes) / 64.63% (7 classes). enet_b2_8 was SOTA for 8-class AffectNet at publication. [HSEmotion paper](https://www.researchgate.net/publication/364625072_HSEmotion_High-speed_emotion_recognition_library)
- Live-streaming FER is harder than lab settings because of varied backgrounds and lighting. [PMC9399731, YOLOv5 FER in live streaming](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9399731/)
- Roohi et al. built the first automatic game-stream emotion annotation system combining facial-expression networks, transcript sentiment, voice emotion and low-level features, aiming to replicate human annotation of emotional moments. [Roohi et al., CHI PLAY 2019](https://dl.acm.org/doi/pdf/10.1145/3311350.3347197)
- Ringer & Nicolaou propose unsupervised multi-view highlight detection on game streams. It jointly uses game footage and the streamer's social signals (facial expressions and speech). The abstract does not give a facecam-only vs game-only ablation. [arXiv 1807.09715](https://arxiv.org/abs/1807.09715)
- A 2026 benchmark (TRINITY) defines "emotion-driven highlights" as segments with observable facial expressions and reactions, and applies FER models for 7 basic emotion labels. [TRINITY, arXiv 2608.29577](https://arxiv.org/pdf/2608.29577)

### Inferences
- At 2-4 fps sampling, MediaPipe + a smile/jawOpen rolling z-score costs well under real time on a small CPU. A 3-hour VOD at 2 fps is ~21,600 frames. At ~20-30 ms per frame that is roughly 7-11 minutes CPU (inferred from the per-frame figures above, not benchmarked).
- Laughter is better captured by audio (laughter detector) than by face. Face is useful for silent reactions (shocked face, face in hands). Blendshapes (continuous jawOpen + smile) are likely more robust than 7-class FER labels for "laughing", since FER often confuses laughing with surprise or fear (inferred).
- A facecam must first be located: crop detection (largest stable face box over time) is needed because the face may be ~10% of a 1080p frame. Low resolution hurts all FER models (inferred).
- py-feat and DeepFace were not checked this session. DeepFace wraps several FER backends; py-feat gives Action Units (AU12 lip corner puller = smile, AU25/26 = mouth open) (recalled, unverified).

### Gaps
- No source found giving precision/recall of facecam smile/laugh spikes as a highlight predictor on real Twitch/YouTube VODs.
- No official MediaPipe CPU latency table for desktop x86 with blendshapes enabled.
- py-feat and DeepFace speed and accuracy not verified.

## 2. Scene change, motion energy, and on-screen game events

### Takeaway
Scene detection (PySceneDetect) finds cuts, not highlights. It is useful for snapping clip boundaries and, on edited YouTube uploads, for spotting editor-made emphasis (fast-cut bursts). Motion energy and game-event detection (kill feed, victory/death screens via OCR or templates) are game-specific signals with no general humor value.

### Cited Findings
- PySceneDetect AdaptiveDetector compares adjacent-frame content like ContentDetector, but uses a rolling-average threshold to reduce false cuts from fast camera motion. It is two-pass. [PySceneDetect detectors docs 0.7.1](https://www.scenedetect.com/docs/latest/api/detectors.html); [CLI docs](https://www.scenedetect.com/docs/latest/cli.html)
- PySceneDetect speed: downscaling by integer factor `-d N`; each increment speeds processing by ~4x; default factor is picked from resolution. [PySceneDetect CLI](https://www.scenedetect.com/cli/)
- CLIP-style frame scoring and frame-only methods fail where frames look alike and only audio disambiguates. This is the common case for a talking-head or static-gameplay stream. [Zero-shot video highlight detection, arXiv 2609.14790](https://arxiv.org/pdf/2609.14790); [SVHighlights](https://arxiv.org/html/2606.06926)

### Inferences
- Livestream VODs have almost no cuts (one continuous capture), so scene-cut density is near-useless there except for scene switches in OBS (e.g. "BRB" or "Just chatting" scenes), which mark segment boundaries, not highlights.
- On edited YouTube uploads, editors already cut out dead air. Zoom-ins, sudden cuts, and replay segments are editor emphasis markers. Cut density spikes may weakly correlate with jokes there (inferred, no source).
- Motion energy (frame difference at 2 fps on a downscaled frame) is near free on CPU. It fires on gameplay action (fights, explosions), not on verbal comedy. Useful as a "chaos" feature for gaming content only.
- Game-event detection by OCR/template (kill feed text, "VICTORY", "YOU DIED") is high precision per game but needs per-game templates. It predicts "action highlights", which overlaps poorly with "funny". Worth it only if Spike targets a few specific games.

### Gaps
- No study found that measures scene-cut or motion features as highlight predictors for comedy specifically.
- No benchmark of game-event OCR for highlight extraction found this session.

## 3. Multimodal video LLMs: Gemini, GPT, Claude, local Qwen/InternVL/LLaVA

### Takeaway
Gemini is the only major API that ingests video natively with audio and accepts public YouTube URLs directly, at ~100-300 tokens per second of video. An hour of video costs roughly $0.06 (2.5 Flash-Lite, low res) to $1.50+ (3.1 Pro). Claude has no native video input (frames only). Local Qwen3-VL-8B can generate textual timestamps and runs via llama.cpp GGUF, but its grounding is coarse (Charades-STA R@0.3 ~69%).

### Cited Findings: Gemini (verified 2026-10-01 on official docs)
- YouTube URL input: free tier limited to 8 hours of YouTube video per day; paid tier no length limit; only public videos (not private or unlisted). Gemini 2.5+ accepts up to 10 videos per request. [Gemini video understanding docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Static mode (default): frames sampled at 1 FPS; custom `fps` configurable. Audio processed at 1 Kbps single channel; timestamps added every second. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Tokens: 66 tokens/frame (low `media_resolution`) or 258 tokens/frame (standard); audio 32 tokens/second. The docs summarize this as ~100 tokens/s (default) or ~300 tokens/s (high res). [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding). Note: the 100 vs 300 per-second labels and 66 vs 258 per-frame figures came from a page summary; the arithmetic (66+32≈100, 258+32≈290) is consistent.
- Length: up to ~3 hours in a 1M context at low resolution, ~1 hour at high/default. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Clipping: `start_offset` / `end_offset` (seconds) in video metadata lets you send only a window of a file or URL. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Timestamps referenced in prompts/outputs use MM:SS format. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- File API: 20 GB (paid) / 2 GB (free) per file; inline data < 100 MB. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Known limitation stated by Google: fast action sequences may lose detail due to 1 FPS sampling. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- New "agentic mode" on newer models: the model navigates the video, loading transcript, frames, and/or audio on demand. It uses up to 88% fewer tokens on long content but may increase time-to-first-token on clips under 5 minutes. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding). Which models support it was not confirmed (the AI Studio guide page did not render).
- Gemini 2.5 Pro "rivals specialized fine-tuned models" on QVHighlights moment retrieval. Low-res mode lets 2.5 Pro process ~6 h of video in 2M context with VideoMME 84.7% vs 85.2% at default res. No exact QVHighlights number given. [Google Developers Blog, Gemini 2.5 video](https://developers.googleblog.com/en/gemini-2-5-video-understanding/)
- Google says Gemini 2.5 identifies moments "using audio-visual cues", e.g. 16 segments in a 10-min keynote. [Google Developers Blog](https://developers.googleblog.com/en/gemini-2-5-video-understanding/)

### Cited Findings: Gemini pricing (official page, "last updated October 1, 2026")
Per 1M input tokens, paid tier. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

| Model | Free tier | Text/image/video in | Audio in | Output | Notes |
|---|---|---|---|---|---|
| Gemini 3.8 Flash | Yes | $0.75 (to 2026-12-31), $1.50 from 2027-01-01 | not separately listed | $3.75, then $7.50 | price doubles in 2027 |
| Gemini 3.5 Flash | Yes | $1.50 | not listed | $9.00 | |
| Gemini 3.5 Flash-Lite | Yes | $0.30 | not listed | $2.50 | |
| Gemini 3.1 Flash-Lite | Yes | $0.25 | $0.50 | $1.50 | |
| Gemini 3.1 Pro Preview | No | $2.00 (≤200k), $4.00 (>200k) | not listed | $12 / $18 | |
| Gemini 2.5 Flash | Yes | $0.30 | $1.00 | $2.50 | |
| Gemini 2.5 Flash-Lite | Yes | $0.10 | $0.30 | $0.40 | cheapest |
| Gemini 2.5 Pro | Yes | $1.25 (≤200k), $2.50 (>200k) | not listed | $10 / $15 | |

- Batch API gives a 50% discount; context caching is paid-tier only. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

### Cited Findings: other APIs and local models
- Claude: no native video ingestion as of Sept 2026. The standard workaround is ffmpeg frames + Whisper transcript passed as images + text. Claude processes only the first frame of an animated GIF. [vomo.ai](https://vomo.ai/guide/can-claude-analyze-video); [claudecamp.ai](https://claudecamp.ai/blog/claude-code-video-processing); [claude-video GitHub](https://github.com/bradautomates/claude-video). These are third-party sources; the official Anthropic docs were not checked.
- Qwen-VL series takes video and emits textual timestamps. Qwen3-VL uses text-timestamp alignment plus spatio-temporal grounding data and RL post-training on grounding. Qwen3-VL-8B scores Charades-STA R@0.3 = 69.3. One paper reports 36.76 mIoU for direct timestamp generation (dataset attribution in the search snippet was garbled, treat as approximate). [REZE, arXiv 2608.04480](https://arxiv.org/html/2608.04480v1); [Qwen2.5-VL tech report](https://arxiv.org/pdf/2502.13923)
- Qwen3-VL GGUFs supported by llama.cpp since 2025-10-30. Official GGUF has LLM in FP16/Q8_0/Q4_K_M and mmproj vision encoder in FP16/Q8_0. A generic 8B Q4_K_M needs ~6-7 GB VRAM. [Qwen/Qwen3-VL-8B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF); [Unsloth guide](https://docs.unsloth.ai/models/qwen3-vl-how-to-run-and-fine-tune); [localllm.in](https://localllm.in/blog/ollama-vram-requirements-for-local-llms)
- Training-free trick: ask a VLM yes/no per segment ("is X happening?") and use the probability curve for grounding, instead of asking it to emit timestamps. [Your VLM Already Knows When, arXiv 2608.08315](https://arxiv.org/pdf/2608.08315)
- LLM-based zero-shot highlight detection is limited by strict input-frame budgets, which cause information loss on long videos. [arXiv 2609.14790](https://arxiv.org/pdf/2609.14790)
- Existing "viral clip" workflows already use gemini-2.5-flash to find funny moments, reactions, and unexpected events in YouTube videos and cut them with FFmpeg. [n8n workflow 11584](https://n8n.io/workflows/11584-extract-viral-worthy-clips-from-youtube-videos-with-gemini-ai-and-ffmpeg-editing/); [gemini-video-scrubber demo](https://github.com/trippedout/gemini-video-scrubber)

### Inferences (cost math, per hour of video, input tokens only)
Using 66 tok/frame (low) or 258 tok/frame (standard) at 1 fps, plus 32 tok/s audio:
- Gemini 2.5 Flash-Lite: low ≈ 237.6k video tok × $0.10 + 115.2k audio tok × $0.30 ≈ **$0.06/h**; standard ≈ **$0.13/h**.
- Gemini 3.1 Flash-Lite: low ≈ **$0.12/h**; standard ≈ **$0.29/h**.
- Gemini 2.5 Flash: low ≈ **$0.19/h**; standard ≈ **$0.39/h**.
- Gemini 3.8 Flash (assuming one price for all media): low ≈ 360k × $0.75 ≈ **$0.27/h**; standard ≈ **$0.81/h** (doubles in 2027).
- Gemini 3.1 Pro: a full hour exceeds 200k tokens, so the $4/M tier applies: low ≈ **$1.44/h**; standard ≈ **$4.30/h**.
- Output (a JSON list of ~20 moments, ~2k tokens) adds well under $0.05 on any model. Batch halves all of this.
- Free tier: 8 h/day of YouTube URLs covers a hobby workload for $0, but free-tier RPM/TPD limits were not verified, and free-tier data may be used by Google to improve products (recalled, unverified).
- Local Qwen3-VL-8B at Q4 fits a 8 GB GPU for short windows. On CPU only, video understanding is likely minutes per short clip (inferred, no benchmark found). Realistic local use: score 30-60 s candidate windows, not whole VODs.

### Known failure modes
- 1 fps sampling misses fast visual gags (Google's own caveat). [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Frame-only pipelines (GPT via frames, Claude via frames, CLIP) miss audio-only jokes unless a transcript is added. [arXiv 2609.14790](https://arxiv.org/pdf/2609.14790)
- Video LLM timestamps are coarse: Charades-STA R@0.3 of ~69% for Qwen3-VL-8B means roughly 3 in 10 predictions do not even overlap 30% with the true moment. Gemini timestamp drift and hallucinated timestamps on hour-long inputs are widely reported anecdotally but I found no measured rate (gap).

### Gaps
- OpenAI GPT-5 video input: not verified. Recalled: OpenAI APIs take images (frames), not video files, and have no native audio-with-video path in the chat API (recalled, unverified; check platform.openai.com docs).
- Gemini free-tier rate limits (RPM, tokens/day) per model not fetched.
- Whether "agentic mode" is enabled for 3.x Flash models and how it is billed.
- Exact QVHighlights mAP/R1 numbers for Gemini, GPT, Qwen3-VL. InternVL, VideoLLaMA 3, LLaVA-Video grounding numbers not checked.
- No measured hallucination rate for "find the funniest moments" style prompts.

## 4. Does Gemini process the audio track? Free tier limits

### Takeaway
Yes. Verified: in static mode Gemini extracts audio at 1 Kbps mono with per-second timestamps alongside 1 fps frames, and Google advertises audio-visual moment finding. Free tier allows 8 h/day of YouTube URL input, public videos only, and 2 GB per uploaded file.

### Cited Findings
- "Audio is processed at 1Kbps (single channel). Timestamps are added every second." Billed at 32 tokens/s. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Gemini 2.5 identifies moments "using audio-visual cues". [Google Developers Blog](https://developers.googleblog.com/en/gemini-2-5-video-understanding/)
- Free tier: 8 h YouTube/day; public videos only; File API 2 GB free vs 20 GB paid. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Free tier exists for 3.8 Flash, 3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Flash, 2.5 Flash-Lite, 2.5 Pro; not for 3.1 Pro Preview. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

### Inferences
- 1 Kbps mono audio is enough for speech and laughter, but music/SFX fidelity is poor. Gemini catches verbal jokes better than frame-only APIs, but it is not a substitute for a dedicated laughter detector on precise timing (inferred).
- Twitch VODs are not YouTube URLs. They need download and File API upload (2 GB free cap means a long 1080p VOD must be downscaled or split, or only candidate windows uploaded).

### Gaps
- Per-model free-tier RPM/TPM/RPD numbers.
- Whether the YouTube-URL path honors `start_offset`/`end_offset` for windows (docs list clipping generally; not confirmed for URL input specifically).

## 5. Zero-shot CLIP / SigLIP frame scoring

### Takeaway
Useful as a cheap visual tag ("person laughing", "explosion", "death screen") on top of other signals, and research shows CLIP-based highlight detection works on datasets like TVSum. It is weak for humor, which is mostly verbal and temporal, and it lacks temporal context.

### Cited Findings
- CLIP can be adapted for highlight detection (CVPR 2024 workshop: "Unleash the Potential of CLIP for Video Highlight Detection"). [Han et al., CVPRW 2024](https://openaccess.thecvf.com/content/CVPR2024W/ELVM/papers/Han_Unleash_the_Potential_of_CLIP_for_Video_Highlight_Detection_CVPRW_2024_paper.pdf)
- Zero-shot framework (2026): LLM writes likely-highlight descriptions from metadata, diffusion makes synthetic prototype images, CLIP matches frames. Clip-level scoring lacks the wider context to judge if a moment is a highlight in a long video. CLIP is limited on actions needing strong temporal correlation. Frame-only methods fail when frames look alike and only audio disambiguates. [arXiv 2609.14790](https://arxiv.org/pdf/2609.14790)
- Zero-shot moment retrieval with off-the-shelf models is feasible. [arXiv 2211.02178](https://arxiv.org/pdf/2211.02178)

### Inferences
- SigLIP/CLIP ViT-B at 1 fps over a 3 h VOD is ~10.8k images. CPU throughput is likely tens of images per second for ViT-B/32 (recalled, unverified), so minutes on CPU. Affordable.
- Best use: (a) facecam crop vs "a person laughing hard" prompt as a second opinion on blendshapes; (b) game screen vs per-game event prompts ("victory screen", "game over screen"). Do not prompt for abstract "funny" or "chaotic"; image-text models lack a notion of humor (inferred).

### Gaps
- No direct evaluation of CLIP/SigLIP prompts for humor or streamer reactions found.

## 6. Practical recipe: cheap proposals, then a video LLM on short windows

### Takeaway
Run free local signals (chat, audio laughter/loudness, transcript, plus face blendshapes and motion) to propose ~20-40 candidate windows of 30-90 s, then send only those windows to Gemini (via `start_offset`/`end_offset` or local ffmpeg cuts) for a judge-and-trim step. This costs cents per VOD and fits the free tier. For YouTube uploads without chat, a single full-video Gemini Flash-Lite pass at low resolution (~$0.06-0.12/h, or free) is itself a viable proposal stage.

### Cited Findings
- Clipping offsets and custom fps are supported, so windows can be sent at higher fps (e.g. 2-5 fps) to fix the 1 fps blind spot for fast gags. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- Batch API gives 50% off for non-urgent jobs. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Agentic mode up to 88% fewer tokens on long content, if available on the chosen model. [Gemini video docs](https://ai.google.dev/gemini-api/docs/video-understanding)

### Inferences (cost estimates)
- 30 windows × 60 s = 30 min of video. At 2 fps standard res: 30 × 60 × (2 × 258 + 32) ≈ 986k tokens. On 2.5 Flash-Lite ≈ $0.10 video + $0.03 audio ≈ **$0.13 per VOD**; on 3.1 Flash-Lite ≈ **$0.27**; on 3.8 Flash ≈ **$0.74** (inferred).
- At 1 fps low res the same 30 windows cost ≈ $0.03 (2.5 Flash-Lite). Effectively free.
- Full-VOD Gemini pass alternatives: 3 h VOD at low res on 2.5 Flash-Lite ≈ $0.18; on 3.1 Pro ≈ $4.30. The windowed approach is 1-2 orders of magnitude cheaper on premium models and gives the LLM a focused judging task instead of open-ended "find the funniest" over 3 hours, which is where timestamp drift is worst (inferred).
- Ask the LLM for relative timestamps inside each short window and a 1-10 funniness score with a reason. Map back to absolute time in code. This avoids long-context timestamp errors (inferred).
- Local $0 option: Qwen3-VL-8B Q4 on a ≥8 GB GPU judging 30 s windows (frames + transcript). Feasible but slow and weaker than Gemini; CPU-only is probably impractical for more than a handful of windows (inferred, no benchmark).
- Visual signals worth adding to Spike's cheap pass, ranked by expected value: (1) facecam jawOpen+smile blendshape spikes, (2) motion-energy spikes for gaming, (3) per-game event templates/OCR, (4) CLIP tags. Scene cuts mainly for boundary snapping on edited uploads.

### Gaps
- No public evaluation comparing "full-video Gemini" vs "proposal + Gemini judge" for humor recall.
- Real end-to-end latency of Gemini on 60 s windows not measured (recalled: typically seconds to tens of seconds per request, unverified).
