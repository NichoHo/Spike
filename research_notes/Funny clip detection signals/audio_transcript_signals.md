# Non-chat audio and transcript/LLM signals for funny/highlight moment detection

Research date: 2026-10-01. Scope: signals usable on YouTube uploads (no chat) on one small CPU-first PC. "Verified" = read on the cited page this session. "Inferred" = my reasoning, not stated by a source. Note: firecrawl hit a rate limit mid-session, so some primary PDFs (Gillick 2021 results table) could not be read; those gaps are listed.

## 1. Laughter detection: models, accuracy, CPU cost, licenses, and whether laughter marks the punchline

### Takeaway
Laughter (audience or laugh track) is the strongest proven automatic label for "funny moment": FunnyNet-W labels the 8 s *before* detected laughter as funny and beats prior SOTA on five datasets. Cheapest practical options: Whisper-AT (AudioSet tags from the Whisper encoder for <1% extra compute, BSD-2) or YAMNet (3.7M weights, Apache-2.0). Dedicated laughter models (jrgillick, MIT; omine LaughterSegmentation, weights research-only) are more precise but cost an extra pass.

### Cited Findings
- **jrgillick/laughter-detection**: Aug 2021 update switched to a newer PyTorch model "more accurate and more robust to background noise"; checkpoints trained on Switchboard; ships AudioSet-based eval annotations; MIT license; params `threshold` (default 0.5) and `min_length` (default 0.2 s). README gives no accuracy or speed numbers. Last commit Aug 2021 (stale, Python 3.6 / PyTorch 1.3 era) ([GitHub](https://github.com/jrgillick/laughter-detection)).
- Gillick et al., "Robust Laughter Detection in Noisy Environments", Interspeech 2021: ResNet over spectrograms trained on Switchboard, evaluated on AudioSet clips (~20% laughter in test set) to measure noisy real-world performance ([PDF](https://people.ischool.berkeley.edu/~kimiko/papers/Gillick.2021.Interspeech.pdf); [Semantic Scholar](https://www.semanticscholar.org/paper/Robust-Laughter-Detection-in-Noisy-Environments-Gillick-Deng/6c5916e8c2b1677b5d979f7e33385a2a48700748)).
- **omine-me/LaughterSegmentation** (Interspeech 2024, "Robust Laughter Segmentation with Automatic Diverse Data Synthesis"): billed as "2024 latest laughter detection & segmentation model"; code MIT but the trained model is "research use only"; tested on RTX 2060 SUPER; 16 kHz input is faster; 66 stars, last update Sep 2024 ([GitHub](https://github.com/omine-me/LaughterSegmentation); [topic page](https://github.com/topics/laugh-detection)).
- **YAMNet**: MobileNet_v1, 521 AudioSet classes, 16 kHz mono, 0.96 s patches, "3.7M weights and performs 69.2M multiplies for each 960ms input frame"; balanced mAP 0.306, d-prime 2.318 on AudioSet eval; requires Keras 2 (incompatible with Keras 3) ([TF models README](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md)). Class map includes Laughter, Baby laughter, Giggle, Snicker, Belly laugh, Chuckle/chortle, Shout, Bellow, Whoop, Yell, Screaming ([TF tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio)). Apache-2.0 and ~15 ms per-frame inference reported by a third-party model card ([STMicroelectronics/yamnet](https://huggingface.co/STMicroelectronics/yamnet/commit/973d2502c4a735796c11de90468922dbbe5b28c2); search summary, not independently verified).
- AudioSet "Laughter" class: label quality 10/10 accurate in Google's sample; 5,696 videos (15.8 h); unbalanced-train quality "may be significantly lower" ([AudioSet](https://research.google.com/audioset/dataset/laughter.html)).
- **PANNs CNN14**: 81M params, 0.431 mAP on AudioSet ([PANNs paper](https://arxiv.org/pdf/1912.10211)). LiteRT port: 390.8 ms median for 10 s of 32 kHz audio on a Raspberry Pi 5 (4 threads, XNNPACK); code Apache-2.0, weights CC-BY-4.0 ([HF model card](https://huggingface.co/litert-community/PANNs-CNN14-AudioSet-LiteRT)). A search summary cited ~68 ms per 1 s audio on an i7-1165G7 ([arXiv 2410.21478](https://arxiv.org/pdf/2410.21478)), not verified on-page.
- **Whisper-AT** (Interspeech 2023): freezes Whisper, trains a small Time-and-Layer-wise Transformer on encoder features; outputs 527 AudioSet labels alongside ASR at "<1% additional computational cost"; AudioSet mAP 41.5, "over 40x faster" than standalone taggers ([arXiv 2307.03183](https://arxiv.org/pdf/2307.03183)). Repo: BSD-2-Clause; tiny through large-v2; `at_time_res` must be a multiple of 0.4 s; output logits shape [ceil(len/res), 527]; no mention of faster-whisper/CTranslate2 support ([GitHub](https://github.com/YuanGongND/whisper-at)).
- Whisper-AT used for laughter detection at 0.8 s stride (high-recall config) in TIC-TALK, a 2026 stand-up corpus of 90 specials, 5,400+ segments ([arXiv 2603.21803](https://arxiv.org/abs/2603.21803)).
- **CLAP zero-shot**: LAION-CLAP ~82-91% top-1 on ESC-50 depending on prompts/checkpoint; transductive refinement adds +4.6 to +9.2 pts ([arXiv 2606.17160](https://arxiv.org/html/2606.17160); search summary). No laughter-specific CLAP numbers found.
- **Laughter as funny-moment label (FunnyNet-W, 2024)**: removes centered voice by subtracting stereo channels, energy peak-picks, then K-means on self-supervised (BEATs) features to separate laughter from music. Clip labeled funny if it *immediately precedes* laughter; uses 8 s clips before laughter onset. Laughter detector on Friends: 78.4% temporal precision, 78.3% temporal recall, 95.2% detection precision at IoU 0.3, 55.1% at IoU 0.7 ([arXiv 2401.04210](https://arxiv.org/html/2401.04210v1)).
- StandUp4AI (May 2025): 330+ h stand-up in 7 languages, audience laughter auto-annotated, and proposes improving automatic laughter detection "based on ASR errors"; frames humor as word-level sequence labeling ([arXiv 2505.18903](https://arxiv.org/abs/2505.18903)).
- Older baseline (2003, flagged old): HMM detection of laughter, applause, cheer as "highlight sound effects" for video summarization ([Tsinghua PDF](https://hcsi.cs.tsinghua.edu.cn/Paper/Paper03/200306.pdf)).
- r/editors users report trying jrgillick for finding laughter in edit footage (anecdotal) ([Reddit](https://www.reddit.com/r/editors/comments/1djnt8h/tool_that_analyzes_for_laughter_visual_and_audio/)).

### Inferences
- Evidence that laughter marks punchlines is from *audience/laugh-track* settings (sitcoms, stand-up, TED). For a solo streamer, their own laugh is a reaction, so the funny trigger is usually 2-8 s *before* laugh onset. Use FunnyNet-W's "window before laughter" pattern, not the laugh itself, as the clip core, and extend the clip end to include the laugh.
- Whisper-AT is the best fit cost-wise, but Spike uses faster-whisper (CTranslate2), and Whisper-AT hooks the openai-whisper PyTorch encoder. Running it means a second encoder pass (roughly the cost of openai-whisper encoding, not "<1%"). A YAMNet pass is likely cheaper on CPU: 69.2M multiply-adds per 0.96 s is about 260 GMAC per hour of audio, which should be on the order of a minute or less of CPU time per hour (inferred, not benchmarked).
- Streamer laughter vs game audio: FunnyNet-W's stereo-subtraction trick only works when voice is center-panned and laughter is not, which is the opposite of a streamer mic (the mic is usually center). For streams, separating the mic from game audio is better done with Demucs vocals (see section 2), or by checking the laughter frames overlap Whisper/VAD speech regions from the same speaker.
- Game audio and videos often contain *canned* laughs (memes, sound alerts). Expect false positives; require laughter to co-occur with a loudness rise in the vocal stem or with transcript cues.

### Gaps
- Could not read the Gillick 2021 results table (PDF rendering failed, firecrawl rate-limited), so no precision/recall/F1 numbers for jrgillick or the omine 2024 model.
- No published CPU real-time factor for jrgillick, omine, BEATs, or CLAP on an hour of audio.
- No study found that measures streamer self-laughter (vs audience laughter) as a highlight predictor.

## 2. Other AudioSet classes and mixed game+voice audio; Demucs cost

### Takeaway
AudioSet taggers (YAMNet, PANNs, Whisper-AT) expose Shout, Yell, Screaming, Whoop, Cheering, Applause, Gasp-type classes for free in the same pass as laughter. On mixed stream audio, isolating the voice with Demucs is feasible but costly on CPU (roughly 0.2x to 1.5x real-time depending on CPU and model), so run it only on candidate windows.

### Cited Findings
- YAMNet class list includes Shout, Bellow, Whoop, Yell, Children shouting, Screaming, Whispering, Laughter variants, Crying/sobbing ([TF tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio)).
- Streaming highlight detection needs both game content and the broadcaster's behavior (PhD thesis, multimodal livestream highlights) ([White Rose thesis](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf)).
- Demucs CPU cost (third-party blogs, lower confidence): htdemucs on CPU roughly 1.5x track duration; htdemucs_ft is about 4x slower than htdemucs; ONNX vocals model at RTF 0.20 on an Apple M4 Pro CPU (3-min song in ~22 s) ([Demucs v4 guide](https://tomodahinata.com/en/blog/demucs-v4-music-source-separation-production-guide); [StemSplit ONNX card](https://huggingface.co/StemSplitio/htdemucs-ft-vocals-onnx); [StemSplit setup](https://stemsplit.io/blog/demucs-local-setup-guide)).

### Inferences
- Hour of audio with htdemucs on a modest desktop CPU: about 20 min (RTF 0.2, fast CPU, ONNX) to 90 min (RTF 1.5, older CPU). Too slow for whole-VOD on a $0 box; use it only on the top-N candidate windows from cheap signals.
- A tagger on the full mix already catches shouting/screaming; Demucs matters mainly when game SFX dominate (horror games, shooters), where "Screaming" may be the game, not the streamer.

### Gaps
- No primary benchmark found for AudioSet tagger precision on game+voice livestream mixes.
- No first-party Demucs CPU benchmarks (repo README not read).

## 3. Prosody, paralinguistics, and speech emotion recognition

### Takeaway
Prosody helps when fused with text (FunnyNet-W audio+text 84.5 F1 vs text-only 77.8 on Friends), but single classic cues like "pause before punchline" are not reliable. Speech emotion models (emotion2vec+) give cheap Happy/Surprised/Angry probabilities that work as excitement features, though no study ties them directly to clip-worthiness.

### Cited Findings
- FunnyNet-W ablation on Friends (F1 / Acc): visual 73.2/64.1, audio 73.7/66.6, text 77.8/68.1, audio+text 84.5/80.3, all three 88.2/85.6. The paper says audio carries "intonation, pitch and pauses" cues ([arXiv 2401.04210](https://arxiv.org/html/2401.04210v1)).
- Pause before punchline is contested: Pickering et al. (2011, old) found no evidence that punch lines are preceded by longer pauses or by speech-rate change in 20 joke performances ([Humor 24-2](https://faculty.tamuc.edu/lpickering/Pdfs/Publish_11.pdf)); another prosodic analysis of a stand-up act reports substantial pauses before punchlines ([ResearchGate](https://www.researchgate.net/publication/374268995_Prosodic_Analysis_of_Humor_in_Stand-up_Comedy)).
- TIC-TALK (Mar 2026): performer kinetic energy negatively predicts audience laughter rate (r = -0.75, N = 24); close-up shot proportion correlates with laughter (r = +0.28) ([arXiv 2603.21803](https://arxiv.org/abs/2603.21803)). This is visual stillness, not audio.
- **emotion2vec+**: 9 classes (angry, disgusted, fearful, happy, neutral, other, sad, surprised, unknown); base ~90M params, large ~300M; 16 kHz; utterance or 50 Hz frame mode; ACL 2024 Findings ([HF emotion2vec_plus_base](https://huggingface.co/emotion2vec/emotion2vec_plus_base); [GitHub](https://github.com/ddlBoJack/emotion2vec)). An ONNX port of the base model exists ([HF](https://huggingface.co/pankotaro/emotion2vec-plus-base-onnx)).
- **HaHaScore cascade** (HF, date unclear): text (768-d) + audio (791-d WavLM + prosody) fusion, predicts humor 0-100; val AUC 0.802; trained on Reddit jokes + 639 stand-up files with pseudo-labels; INT8 ONNX 2.9 MB, ~3.3 ms CPU; MIT ([HF](https://huggingface.co/Hayasuki/hahascore-cascade)). Single-author hobby model; treat claims as unvalidated.

### Inferences
- For streamers, simple deltas (pitch range and energy jump vs the speaker's rolling baseline, speech-rate spike, sudden silence then burst) are cheap via librosa/ffmpeg and likely capture "excitement". Humor specifically needs the text side.
- emotion2vec+ base on CPU over only VAD speech, at utterance level, should be well under real-time (inferred from 90M param size; no measured RTF found).

### Gaps
- No quantitative study found linking emotion-recognition outputs to highlight/funny labels in streams or YouTube.
- No CPU RTF found for emotion2vec+ or SpeechBrain/wav2vec2 emotion models.

## 4. Transcript-based humor detection with LLMs: results, failure modes, prompting

### Takeaway
Text is the single strongest modality for funny-moment detection (FunnyNet-W), and Whisper transcripts are nearly as good as human subtitles (F1 gap under 1 pt). But LLMs extracting punchlines from stand-up transcripts only reach ~43-51% agreement with ground truth, and prompt tricks (personas, humor types) did not help. Use the LLM as one scorer fused with audio laughter, not as the sole judge.

### Cited Findings
- FunnyNet-W: Whisper (WhisperX) transcripts vs ground-truth subtitles nearly identical: TBBT 78.2 vs 78.5 F1; UR-Funny 84.2 vs 84.5 F1. Llama-2 7B text encoder beat BERT (88.2 vs 85.3 F1 on Friends) ([arXiv 2401.04210](https://arxiv.org/html/2401.04210v1)).
- Older multimodal SOTA (2021, flagged old): HKT 77.36% acc on UR-FUNNY punchline detection, 79.41% on MUStARD ([AAAI 2021 PDF](https://hoques.com/Publications/2021/MultimodalHumorAAAI2021_CameraReady.pdf)). For UR-FUNNY the language modality is the strongest single modality; on MUStARD visual and language perform about equally ([WACV 2022](https://openaccess.thecvf.com/content/WACV2022/papers/Pramanick_Multimodal_Learning_Using_Optimal_Transport_for_Sarcasm_and_Humor_Detection_WACV_2022_paper.pdf)).
- "From Punchlines to Predictions" (CMCL 2025): extracting humorous lines from stand-up transcripts; GPT-4o 48.9%, DeepSeek-V3 46%, Claude 3.5 Sonnet 43.4%, Gemma 30-35%, humans 40.7% (fuzzy match). GPT-4o drops to 25.4% under semantic-similarity scoring. Prompt variants, personas, and humor-type specialization gave no gain or reduced performance; plain "extract the key humorous lines and punchlines" was best. Human-LLM agreement 59.9%. Larger models often explained instead of quoting. Authors note transcripts lack delivery, tone, and audience reaction ([arXiv 2504.09049](https://arxiv.org/html/2504.09049)).
- HumorBench (Jul 2025, New Yorker cartoon captions): o3 87.5%, Gemini 2.5 Pro / Claude 3.7 Sonnet / DeepSeek R1 ~80%; on HumorBench-Hard no model exceeds 60% (GPT-4o ~42.7%, Llama 4 Maverick ~36%, Qwen2.5-72B ~26.8%). Failures cluster on implicit conceptual leaps and obscure references; wordplay is easier ([arXiv 2507.21476](https://arxiv.org/html/2507.21476v1)).

### Inferences
- Small local LLMs (7-9B) are the tier HumorBench and the CMCL paper show as weakest (Gemma 30-35%). On a $0 CPU box, the LLM is best used to *rank pre-filtered candidates* from audio signals, not to sweep a whole VOD.
- Prompting patterns supported by evidence: plain extraction prompt over persona prompts; ask for exact quotes (so timestamps can be matched back to word-level Whisper output) since models drift to paraphrase. Pairwise comparison and rubric scoring are reasonable but I found no humor-specific study comparing them (inferred).
- Known blind spots: visual gags, game events, and delivery-driven humor (a flat line made funny by tone). These must come from audio (laughter, energy) or video.
- Include the 30-60 s *before* a candidate in the LLM window, since setup context matters (HumorBench failure analysis + FunnyNet's pre-laughter window).

### Gaps
- No 2025-2026 paper found on LLM humor scoring of livestream or gaming transcripts specifically.
- No public engineering write-ups from commercial clippers (Eklipse, Opus Clip) with measured accuracy; marketing pages only ([Eklipse](https://eklipse.gg/features/ai-highlights/)).

## 5. Whisper non-speech tags and diarization

### Takeaway
Do not rely on Whisper emitting "[laughter]" / "(laughs)": it is sporadic and non-reproducible, and laughter corrupts neighboring word timestamps. Use an audio tagger instead and treat any tag Whisper does emit as a bonus. Diarization (pyannote) is costly on CPU and mainly useful for multi-speaker podcasts.

### Cited Findings
- OpenAI forum (Jan 2026): a user ran Whisper-1 hundreds of times on a 2-min stand-up clip; once it emitted "[applause & cheers]" with word timestamps, then never again on identical calls ([OpenAI community](https://community.openai.com/t/speech-to-text-whisper-1-detection-of-laughter-applause-cheers/1371933)).
- Whisper timestamps are inconsistent around laughter: laughter duration gets merged into the next word (Whisper) or previous word (WhisperX) ([StandUp4AI arXiv 2505.18903](https://arxiv.org/pdf/2505.18903), via search summary).
- Whisper hallucinates on non-speech; a 2025 method cuts non-speech hallucinations by over 80% without hurting ASR ([arXiv 2505.12969](https://arxiv.org/html/2505.12969v1)); community advice is to VAD-gate (e.g. Silero) rather than prompt ([Whisper discussion #1606](https://github.com/openai/whisper/discussions/1606); [Reddit](https://www.reddit.com/r/LocalLLaMA/comments/1rlqfd7/we_collected_135_phrases_whisper_hallucinates/)).
- pyannote CPU cost: on an AWS c5.2xlarge (8 vCPU), a 45-min file took ~14.3 min with speaker-diarization-3.0 but ~36.5 min with 3.1, the embedding step being the bottleneck ([pyannote issue #1626](https://github.com/pyannote/pyannote-audio/issues/1626)).

### Inferences
- A laughter burst often shows as a Whisper word with an abnormally long duration. Long-duration words in faster-whisper output are a free, weak laughter cue (inferred from the timestamp-merging finding; StandUp4AI uses ASR errors to improve laughter detection along similar lines).
- Diarization: per the 3.1 timing, roughly 0.8x real-time on an 8-vCPU box, so ~50 min per hour of audio. Worth it only for podcasts/collabs where crosstalk and fast turn-taking are a signal. Solo streams: skip.

### Gaps
- No measurement found of how often open-source faster-whisper large-v3 emits laughter tags.
- No study on crosstalk/overlap rate as a highlight predictor.

## 6. CPU cost per hour of audio (summary)

### Takeaway
Cheap enough for full-VOD sweeps: YAMNet, PANNs CNN14, Whisper-AT on top of an existing openai-whisper run. Run only on candidates: Demucs, pyannote, emotion2vec large, local LLM scoring.

### Cited Findings
- YAMNet: 69.2M multiplies per 0.96 s frame ([README](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md)).
- PANNs CNN14: 390.8 ms per 10 s on Raspberry Pi 5 (RTF ~0.04) ([HF](https://huggingface.co/litert-community/PANNs-CNN14-AudioSet-LiteRT)).
- Whisper-AT: under 1% extra over Whisper ASR FLOPs ([arXiv 2307.03183](https://arxiv.org/pdf/2307.03183)).
- Demucs htdemucs: RTF ~0.2 (M4 Pro, ONNX) to ~1.5 (generic CPU) (third-party blogs) ([HF](https://huggingface.co/StemSplitio/htdemucs-ft-vocals-onnx); [guide](https://tomodahinata.com/en/blog/demucs-v4-music-source-separation-production-guide)).
- pyannote 3.0: ~0.32x RT, 3.1: ~0.81x RT on 8 vCPU ([issue #1626](https://github.com/pyannote/pyannote-audio/issues/1626)).
- HaHaScore INT8 ONNX: ~3.3 ms per sentence on CPU (author claim) ([HF](https://huggingface.co/Hayasuki/hahascore-cascade)).

### Inferences
- Per hour of audio, approximate CPU time (inferred from the above): YAMNet about 1 min or less; PANNs CNN14 about 2-4 min on a desktop x86 (RPi5 RTF 0.04 = 2.4 min, desktop likely faster); Demucs 12-90 min; pyannote 3.1 about 50 min; jrgillick and emotion2vec+ unknown.
- Suggested cheap cascade: (1) YAMNet or PANNs full-VOD pass for laughter/shout/scream/cheer; (2) combine with existing LUFS and speech-rate peaks; (3) for top-N windows, run the LLM on the transcript including 30-60 s of setup, asking for exact quoted punchline lines; (4) optional Demucs or emotion2vec on those windows only.

### Gaps
- None of the CPU figures were measured on Spike's hardware. A 10-minute benchmark of YAMNet vs CNN14 vs jrgillick on one real VOD would resolve which laughter detector to ship.
