# ML and multimodal-LLM approaches to detecting clippable moments in anime

Research date: 2026-10-27. Tags: **[V]** = verified this session from the cited page; **[R]** = recalled from training data, not re-checked (verify before relying on it). Reference target throughout: TeamFourStar "A Win is a Win | Buu Bits", a 32 s self-contained dialogue joke.

## 1. Academic highlight detection / moment retrieval, and transfer to anime

### Takeaway
The DETR family (Moment-DETR, QD-DETR, CG-DETR, TR-DETR, SG-DETR) is trained on live-action vlogs/news (QVHighlights), TVSum and YouTube-Highlights. None target anime, and none model "funny" or "quotable". The closest useful academic line is humor detection that uses sitcom laugh tracks as free labels (FunnyNet-W) and LLM video-to-text humor prompting (ExFunTube). For Spike, these are design inspiration, not drop-in scorers.

### Cited Findings
- [V] QVHighlights introduced joint moment retrieval plus clip-wise saliency scores; Moment-DETR is its baseline. Highlight detection mAP (>= Very Good) is 35.69 without pretraining and 37.43 with ASR-caption pretraining; HIT@1 is 55.6 / 60.2 ([QVHighlights, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf)).
- [V] These models are query-dependent: they score clips against a natural-language query (the paper contrasts this with query-agnostic highlights) ([QVHighlights](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf)).
- [V] Reported QVHighlights HD numbers (mAP / HIT@1-style columns as tabled by SG-DETR): QD-DETR 57.3 / 32.6 (MR columns), CG-DETR 58.4 / 36.3, TR-DETR 57.6 / 33.5. On YouTube-Highlights average: QD-DETR 74.4, CG-DETR 75.9. TVSum average: QD-DETR 85.0, CG-DETR 86.8, TR-DETR 88.1, SG-DETR 87.1 ([SG-DETR, arXiv 2410.01615](https://arxiv.org/html/2410.01615v2)).
- [V] SG-DETR pretrains on a large synthetic set (InterVid-MR) and reports zero-shot QVHighlights performance; the authors say QVHighlights alone is too small for strong pretraining ([SG-DETR](https://arxiv.org/html/2410.01615v2)).
- [V] QD-DETR ships pretrained checkpoints (video+audio and video-only) built on the Moment-DETR codebase and its pre-extracted features ([QD-DETR GitHub](https://github.com/wjun0830/QD-DETR)).
- [V] Anime datasets found on arXiv are for generation (AnimeShooter, AniSora), character appearance (OregairuChar) and scene text detection, not highlight or humor labels ([search results: AnimeShooter](https://arxiv.org/abs/2506.03126), [OregairuChar](https://arxiv.org/html/2511.05263v1), [anime scene text](https://arxiv.org/abs/2510.07951)).
- [V] Newest highlight benchmark found: SVHighlights (sports), 320 videos averaging 2.0 h, labels built by aligning official highlight reels with full broadcasts ([HF papers](https://huggingface.co/papers/2606.06926)).
- [V] FunnyNet-W predicts funny moments from frames, audio and ASR text with cross/self attention. It gets labels by unsupervised laughter detection on sitcom audio (clusters: laughter, music, voice, empty), then removes the laughter from inputs so the trained model works on videos without a laugh track. SOTA on TBBT, MHD, MUStARD, Friends, UR-Funny. Tested on Modern Family (no canned laughter), 453 hand-annotated punchlines ([FunnyNet-W, arXiv 2401.04210](https://arxiv.org/html/2401.04210v1)).
- [V] Related humor datasets: MHD (laughter-track prediction for sitcoms, WACV 2021), UR-FUNNY (TED talks, 1,866 videos), "The Laughing Machine" (WACV 2021) ([MHD PDF](https://openaccess.thecvf.com/content/WACV2021/papers/Patro_Multimodal_Humor_Dataset_Predicting_Laughter_Tracks_for_Sitcoms_WACV_2021_paper.pdf), [UR-FUNNY](https://roc-hci.com/past-projects/multimodal-humor-understanding/)).
- [V] A Columbia 2019 paper generated unsupervised humor labels from time-aligned user comments, the same signal as Twitch chat ([Multimodal Indicators of Humor in Videos](http://www.cs.columbia.edu/speech/PaperFiles/2019/MMPrag19_camera_ready.pdf)).
- [V] Stand-up comedy context/utterance setup (4 context sentences + target) reaches about 61 to 68 F1-range scores across text/visual/face modalities, showing text-only humor classifiers plateau in the 60s ([LREC 2024](https://aclanthology.org/2024.lrec-main.1037.pdf)).

### Inferences
- Transfer to anime is weak for the DETR models: their features (CLIP/SlowFast) and labels are live action, and "salient" in QVHighlights means "relevant to the query", not "funny". A query like "a character delivers a punchline" is possible but unproven.
- The laugh-track trick does not apply directly: anime has no laugh track. The analog for anime is time-synced comments (Bilibili danmaku, Niconico comments), which is the same idea Spike already uses with Twitch chat. A Bilibili data provider exists for search/comments; whether it returns danmaku with timestamps was not checked.
- Training a FunnyNet-style model is out of scope for a $0 one-PC tool. A zero-shot LLM judge (section 5) is the practical path.

### Gaps
- No anime-specific highlight or humor dataset found. Did not check Niconico/Bilibili danmaku highlight papers in detail (one search returned only consumer pages).
- No published zero-shot result of QD-DETR/CG-DETR on animation.

## 2. Multimodal LLMs on anime video: Gemini, Qwen-VL, local VLMs, and cost

### Takeaway
Gemini is the cheapest high-quality option: at the current default (1 fps, 70 tokens per frame plus 25 audio tokens per second) a 24-min episode is about 137k tokens, which costs about $0.04 on Gemini 3.5 Flash-Lite and about $0.10 on Gemini 3.8 Flash (2026 pricing), and all Flash/Flash-Lite models have a free tier. Use a cheap full-episode pass, then re-score only the candidate windows with `start_offset`/`end_offset` and a higher fps. Qwen3-VL-8B is the local fallback.

### Cited Findings
- [V] Current model lineup in the Gemini docs (2026-10-27): Gemini 4 / "Gemini 4 Argon", Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 3.1 Pro Preview, 3 Flash Preview, 2.5 Pro/Flash/Flash-Lite ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding), [pricing](https://ai.google.dev/gemini-api/docs/pricing)).
- [V] Default video sampling is 1 fps. Custom `fps`, `start_offset` and `end_offset` are set in the `processing` config. Timestamps in prompts use `MM:SS`. Max length is about 3 h at low media resolution, about 1 h at high ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)).
- [V] Media resolution token table (current docs): video frame = 70 tokens at unspecified/low/medium (low and medium are treated identically for video), 280 tokens at high; audio = 25 tokens per second at all settings. Google recommends low/medium for general video and high only for text-heavy frames (OCR) ([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)).
- [V] The video page also says roughly 100 tokens per second at default (low) resolution, and states an older scheme: 66 tokens per frame at low, 258 otherwise ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)). [R] The 258/66 per-frame and 32 audio tokens/s figures are the Gemini 2.5 rates (about 300 tok/s default, about 100 tok/s low).
- [V] Prices per 1M input tokens, standard tier, page dated 2026-10-27 ([pricing](https://ai.google.dev/gemini-api/docs/pricing)):
  - Gemini 3.8 Flash: $0.75 in / $3.75 out through 2026-12-31, rising to $1.50 / $7.50 on 2027-01-01. Batch/Flex half. Free tier: yes.
  - Gemini 3.6 Flash: same as 3.8 Flash. Free tier: yes.
  - Gemini 3.5 Flash-Lite: $0.30 in (text/image/video/audio) / $2.50 out; batch $0.15 / $1.25. Free tier: yes.
  - Gemini 3.1 Flash-Lite: $0.25 video, $0.50 audio / $1.50 out. Free tier: yes.
  - Gemini 3 Flash Preview: $0.50 video, $1.00 audio / $3.00 out. Free tier: yes.
  - Gemini 2.5 Flash: $0.30 video, $1.00 audio / $2.50 out. Gemini 2.5 Flash-Lite: $0.10 video, $0.30 audio / $0.40 out. Free tier: yes.
  - Gemini 3.1 Pro Preview: $2.00 / $12.00, no free tier.
- [V] The rate-limits page no longer lists free-tier RPM/TPM/RPD numbers; it tells users to view their active limits in AI Studio (page dated 2026-10-26) ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)).
- [V] Qwen3-VL ships dense and MoE sizes "from edge to cloud"; the 8B Instruct card claims text-timestamp alignment beyond T-RoPE for timestamp-grounded event localization, second-level indexing on hours-long video, native 256K context (expandable to 1M), and pretraining that can recognize "anime" among other categories. GGUF quantizations are available for llama.cpp / LM Studio ([Qwen3-VL-8B-Instruct card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)). The card's date field showed 2025-05-14, which is likely the Qwen3 paper date, not the VL release.
- [R] Qwen3-VL released around Sept to Oct 2025 in sizes including 2B, 4B, 8B, 30B-A3B (MoE) and 235B-A22B; an 8B model at 4-bit fits in about 6 to 8 GB VRAM, but video input at useful fps is VRAM-heavy. InternVL3/3.5 and Qwen2.5-VL-7B are comparable local options. Not re-checked this session.
- [R] Gemini accepts public YouTube URLs directly as video input, which avoids uploading files. Not re-checked this session.
- [R] Free-tier Gemini traffic may be used by Google to improve products; paid tier is not. Verify on the terms page before sending copyrighted episodes.

### Inferences
Worked cost for one 24-min (1,440 s) episode, prompt overhead and output excluded:

| Setting | Tokens/s | Episode tokens | 3.5 Flash-Lite ($0.30) | 3.8 Flash 2026 ($0.75) | 3.8 Flash 2027 ($1.50) |
|---|---|---|---|---|---|
| 1 fps, default/low (70 + 25 audio) | 95 | ~137k | ~$0.041 | ~$0.10 | ~$0.21 |
| 0.5 fps, default (35 + 25) | 60 | ~86k | ~$0.026 | ~$0.065 | ~$0.13 |
| 1 fps, high (280 + 25) | 305 | ~439k | ~$0.13 | ~$0.33 | ~$0.66 |
| Rescore: 60 s window at 2 fps default (140 + 25) | 165 | ~10k | ~$0.003 | ~$0.007 | ~$0.015 |

- Batch tier halves these. A 12-episode cour at 1 fps on 3.5 Flash-Lite is about $0.50; on free tier it is $0 within whatever daily caps AI Studio shows.
- Suggested two-pass plan: pass 1 = whole episode at 0.5 to 1 fps, low resolution, on Flash-Lite, asking for a JSON list of candidate moments with `MM:SS` start/end and a reason. Pass 2 = each candidate +/- 15 s via `start_offset`/`end_offset` at 2 fps on Flash (or Pro for the top few), asking for exact boundaries and a score. Pass 2 adds well under $0.01 per candidate.
- Audio is about a quarter of tokens at 1 fps and over 40% at 0.5 fps. For a dialogue joke the audio (or subtitles) carries the punchline, so do not strip it to save tokens; instead drop fps.
- Gemini 2.5 Flash-Lite is the cheapest per token but prices audio 3x video; it is still about $0.02 per episode at low resolution [R for the 2.5 token rates].
- Local VLMs: frame-sampled Qwen3-VL-8B (for example 1 frame every 2 s plus subtitle text) is feasible on an 8 to 12 GB GPU for rescoring a handful of candidates, not for full episodes at speed. CPU-only is impractical for video.

### Gaps
- No published benchmark found for MLLM humor or highlight quality on anime specifically; anime understanding claims are vendor marketing.
- Free-tier RPM/RPD numbers are only visible in the user's AI Studio console, not in public docs.
- Did not verify whether Gemini 3.8 Flash bills audio at the same rate as video (the page listed one input price).

## 3. Speech: Japanese ASR on anime, dubs, subtitles, translation

### Takeaway
Prefer existing subtitle files (fansub/official .ass/.srt or embedded tracks) over ASR: they are exact, timed, and already English. When ASR is needed for Japanese, use litagin/anime-whisper (13.0% CER on anime/game speech vs 16.5% for whisper-large-v3) or Qwen3-ASR-1.7B; avoid kotoba-whisper on emotional dialogue. English dubs work with standard faster-whisper large-v3/turbo.

### Cited Findings
- [V] anime-whisper: fine-tuned from kotoba-whisper-v2.0, about 0.8B params, trained on about 5,300 hours / 3.73M files of anime-style voice and script data (Galgame_Speech_ASR_16kHz). Average CER on its game/anime test sets: anime-whisper 13.0, whisper-large-v3 16.5, kotoba-whisper-v2.0 18.8. The author warns that an initial prompt causes hallucination and severe quality loss, so do not set one. Also claims fewer hallucinations, faithful transcription of non-verbal sounds and natural punctuation ([anime-whisper card](https://huggingface.co/litagin/anime-whisper)). License not stated on the scraped page.
- [V] kotoba-whisper on clean benchmarks: v2.0 CER 9.2 (CommonVoice 8), 8.4 (JSUT), 11.6 (ReazonSpeech); v2.1 with punctuator similar ([kotoba-whisper-v1.0 card](https://huggingface.co/kotoba-tech/kotoba-whisper-v1.0), [GitHub](https://github.com/kotoba-tech/kotoba-whisper)).
- [V] A 2026 benchmark (20 clips of about 29 s, including comedy/variety and drama/anime) ranked CER: qwen3-asr-1.7b 0.140, whisper (large-v3 family) 0.184, voxtral-mini 0.212, granite-speech-4.1-2b 0.262, parakeet-tdt-0.6b-v3 0.321 (fastest, RTF 0.003), reazonspeech-nemo-v2 0.329, kotoba-whisper-v2.0 0.495 (worst). It says kotoba-whisper repeats phrases on unclear audio, drops words after fillers, and struggles with emotional, multi-speaker speech ([Neosophie benchmark, published 2026-05-01](https://neosophie.com/en/blog/20260226-japanese-asr-benchmark)). Small sample; treat as directional.
- [V] SenseVoice-Small: 11.96% CER on Japanese vs Whisper-large-v3 10.34%, but much faster ([WhisperNotes](https://whispernotes.app/blog/sensevoice-fastest-cjk-transcription)). Vendor blog.
- [R] faster-whisper (CTranslate2) runs large-v3 / large-v3-turbo in int8 on CPU or about 4 to 6 GB VRAM, with word timestamps; it can load converted fine-tunes such as anime-whisper after `ct2-transformers-converter`. Not re-checked.
- [R] Whisper with `task="translate"` gives direct Japanese-to-English, but quality is below transcribe-then-LLM-translate. For an English audience, translating Japanese ASR text with the Gemini or Claude judge in the same call is cheap and usually better. Not benchmarked here.

### Inferences
- Order of preference for the text track: (1) embedded or sidecar English subs, (2) English dub audio through faster-whisper, (3) Japanese audio through anime-whisper or Qwen3-ASR, then LLM translation.
- Japanese ASR CER of 13 to 18% is fine for finding a candidate, not for burning captions. Captions for a sub clip should come from the subtitle file.
- The reference clip (DBZ Abridged) is English parody audio, so it falls under case (2). Note it is a fan parody, not the anime itself; "abridged" humor is written dialogue, which favors a text judge.
- If Spike skips local ASR entirely and sends audio to Gemini, the 25 audio tokens per second already pay for "listening"; local ASR then only matters for the $0 path.

### Gaps
- No public CER for anime-whisper on full TV episodes with music and SFX (its test sets are game voice lines).
- No quality comparison found of Whisper translate vs LLM translation for anime.

## 4. Embeddings: CLIP/SigLIP for iconic frames and known meme scenes

### Takeaway
SigLIP 2 (or CLIP) frame embeddings are good for near-duplicate matching: comparing an episode's frames against a small reference set of known viral or meme screenshots to boost those timestamps. They are not a humor detector. Cost is near zero on a consumer GPU.

### Cited Findings
- [V] SigLIP 2 produces joint image and text embeddings for cross-modal retrieval and re-identification; variants include SO400M and giant backbones at 224 to 512 px, embedding dims 768 to 1536 ([NVIDIA VSS docs](https://docs.nvidia.com/vss/3.2.0/models/clip-object-embeddings.html)).
- [V] clip-retrieval computes about 1,500 image embeddings per second on an RTX 3080 and indexes them for kNN search ([clip-retrieval](https://github.com/rom1504/clip-retrieval)).
- [V] A practical pattern: blend a text vector with the mean of a few reference-image vectors to represent one entity, then kNN-match photos against that index ([Elastic SigLIP-2 example](https://www.elastic.co/search-labs/blog/multimodal-search-siglip-2-elasticsearch)).
- [V] SigLIP-family models are reported to do better than CLIP on zero-shot retrieval and semantic search ([Vizuara comparison](https://vizuara.substack.com/p/multi-modal-representation-learning)). Secondary source.

### Inferences
- A 24-min episode at 1 fps is 1,440 frames: a few seconds to embed on a GPU, a minute or two on CPU with a base model.
- Use cases ranked by value: (a) meme match against user-supplied reference screenshots (cosine above a tuned threshold boosts that timestamp), (b) shot-boundary and "visual change" signal as a cheap feature, (c) text-to-frame queries like "character shocked face" or "explosion", which are noisy on anime.
- For a dialogue joke like the reference, embeddings add little; the punchline is in the words.
- Perceptual hashing (pHash) may beat CLIP for exact meme-frame matching at lower cost; worth testing before adding a model.

### Gaps
- No benchmark found of CLIP/SigLIP on anime screenshot retrieval or anime-specific CLIP fine-tunes; did not search Danbooru-trained encoders.

## 5. Humor and punchline detection from text

### Takeaway
Zero-shot LLM judges given a structured transcript (and optionally a short visual description) are the practical approach; ExFunTube shows that converting video to rich text before asking an LLM improves humor understanding. Laugh-free content needs the model to find setup/punchline structure itself, which favors windows with complete exchanges.

### Cited Findings
- [V] ExFunTube (EMNLP 2023): 10,136 funny YouTube Shorts, filtered with GPT-3.5 to keep videos where both verbal and visual elements matter, annotated with timestamps and text explanations of funny moments. A zero-shot video-to-text prompting method "significantly improves" LLM humor explanation by automatic, rationale-quality and human evaluation ([arXiv 2310.14159](https://arxiv.org/abs/2310.14159), [GitHub](https://github.com/dayoon-ko/ExFunTube)).
- [V] Earlier humor datasets "mostly focus on verbal cues" and specific domains such as speeches or sitcoms ([ExFunTube abstract](https://arxiv.org/abs/2310.14159)).
- [V] FunnyNet-W found intonation, pitch and pauses in audio are high-level humor cues, and ASR text processed by an LLM adds rich information ([FunnyNet-W](https://arxiv.org/html/2401.04210v1)).
- [V] Context-plus-target framing (4 prior utterances, then the candidate line) is the standard setup in multimodal humor datasets ([LREC 2024](https://aclanthology.org/2024.lrec-main.1037.pdf)).

### Inferences
- Give the judge the dialogue as timed lines with speaker labels, ask it to name the setup line(s) and the punchline line, and score only if both fall inside the proposed clip. This directly enforces self-containment.
- Audio delivery matters (FunnyNet-W), which argues for letting Gemini hear the candidate window in pass 2 rather than reading text only.
- Abridged parodies and gag anime will score well on text; action or visual gags will not, so keep a visual path (Gemini video pass) for those.

### Gaps
- No found study measuring current LLMs (Gemini 3.x, Claude) as humor raters against human funniness ratings; the ExFunTube result is about explanation, on older models.

## 6. Prompting patterns, rubrics and clip boundaries for an anime judge

### Takeaway
Ask for structured JSON with `MM:SS` timestamps, a short reason, setup and punchline lines, and boundary checks; snap model timestamps to subtitle cue edges and shot cuts. Gemini's documented `MM:SS` timestamp support and `start_offset`/`end_offset` clipping make the two-pass coarse-then-precise flow straightforward.

### Cited Findings
- [V] Gemini understands `MM:SS` timestamps in prompts and supports clipping intervals and custom fps per request ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)).
- [V] Qwen3-VL claims timestamp-grounded event localization and second-level indexing, so the same JSON-with-timestamps prompt can run locally ([Qwen3-VL card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)).
- [V] Moment-retrieval work treats a moment as start/end span plus per-clip saliency; that split (span + score) is a good output schema for an LLM judge too ([QVHighlights](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf)).

### Inferences
Suggested rubric (each 0 to 10, plus a veto), adapted to the reference clip:
1. **Self-contained**: a viewer with no context gets it. Veto if it needs prior-episode knowledge.
2. **Payoff**: a clear punchline, reveal, or hype beat inside the window.
3. **Setup present**: the setup lines are inside the clip, not cut off.
4. **Delivery**: voice acting, timing, reaction shot (needs audio/frames).
5. **Quotability / meme potential**: short line people repeat.
6. **Length fit**: 15 to 60 s for Shorts; the reference is 32 s.
7. **Spoiler/sensitivity flag** (separate field, not scored).

Boundary recipe:
- Model returns `start`, `end`, `setup_line_idx`, `punchline_line_idx`.
- Snap `start` back to the start of the subtitle cue containing the setup, minus about 0.5 s; snap `end` to the punchline cue end plus a reaction tail (1 to 3 s), then to the nearest shot cut (PySceneDetect or embedding change) within +/- 1 s.
- Reject if a subtitle cue is cut mid-line at either edge.
- Rescore the snapped window in pass 2 with the clip itself as the only input, asking "would this make sense to someone who never saw the show?" This mirrors Spike's current veto/boost use of the Gemini verdict.

Prompt pattern:
- Give the episode transcript as numbered timed lines `[idx] MM:SS-MM:SS SPEAKER: text` (English), plus optional one-line scene notes from sampled frames.
- Ask for up to N candidates as JSON, ranked, each with the rubric fields and a one-sentence "why it is funny" (explanation-first improves humor judgments per ExFunTube's framing; this is an inference, not a measured result for this rubric).
- Include one or two worked examples (the reference clip's transcript and its scores) as few-shot anchors.

### Gaps
- No source found that measures LLM timestamp accuracy on anime; plan to measure it against hand-labeled clips (Spike already has an eval script pattern for Twitch).
- Speaker labels are not in most subtitle files; diarization was not researched here.
