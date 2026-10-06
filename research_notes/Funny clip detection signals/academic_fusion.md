# Academic basis for highlight/humor detection, signal fusion, ranking, and evaluation (for Spike)

Research date: 2026-10-01. "Verified" = numbers read from the paper/page this session (via abstract page, ar5iv HTML, PDF parse, or docs). "Search-snippet" = seen only in a search result summary, not opened. "Inference" = my reasoning, not in a source.

## Q1. Highlight detection research: datasets, methods, and which modalities matter

### Takeaway
Across benchmarks, visual and transcript content carry most of the signal; audio helps but is weaker alone, and audience chat alone is a weak predictor in the one esports study that ablated it (chat-only F1 43 vs video-only 72). For YouTube with no chat, the strongest 2024-2026 results come from (a) "Most Replayed" style crowd signals as weak labels and (b) training-free LLM pipelines that score transcript+caption segments built from merged shots.

### Cited Findings
**Livestream / chat-based**
- Fu, Lee, Bansal, Berg, "Video Highlight Prediction Using Audience Chat Reactions", EMNLP 2017. Dataset: 321 League of Legends championship videos (218 NALCS English, 103 LMS Traditional Chinese), each 30-50 min, labels from community-generated highlight videos. (Verified, PDF) — [ACL Anthology PDF](https://aclanthology.org/D17-1102.pdf)
- Fu et al. F-scores: chat-only L-Char-LSTM 43.2 (NALCS) / 39.7 (LMS); video-only V-CNN-LSTM 72.2 / 69.2; chat+video lv-LSTM 74.7 / 70.0. Chat adds only +2.5 / +0.8 F over video. (Verified, PDF) — [ACL Anthology PDF](https://aclanthology.org/D17-1102.pdf)
- Lindroos et al., "Leveraging Large Language Models for Twitch Video Clip Understanding and Summarization", GamiFIN '26 (March 2026): Gemini MLLMs with a chain-of-thought prompt correlate audio-visual moments with chat reactions; evaluated by humans on only 56 clips; Gemini 2.5 judged much better than earlier Gemini. This is summarization of existing clips, not detection. (Search-snippet) — [ACM DL](https://dl.acm.org/doi/10.1145/3789624.3789641)
- I found no 2023-2026 peer-reviewed paper that releases a large Twitch chat-labeled highlight benchmark with modality ablations; a targeted search returned mostly toxicity/user-embedding Twitch papers. (Verified negative result of search) — [search results incl. arXiv 2411.10934](https://arxiv.org/abs/2411.10934)

**Query-based highlight detection (QVHighlights / Moment-DETR / UMT)**
- QVHighlights (Lei et al., NeurIPS 2021): 10,310 queries, 18,367 moments, 10,148 YouTube videos (vlogs, news). Saliency labeled on a 5-point Likert scale by 3 annotators per clip, averaged. Metrics: mAP and HIT@1 (top-scored clip is rated "Very Good"). (Verified, ar5iv) — [arXiv 2107.09609](https://ar5iv.labs.arxiv.org/html/2107.09609)
- Moment-DETR highlight mAP 35.69 without pretraining, 37.43 with weakly supervised pretraining on ASR captions (noisy subtitles as free labels helped). (Verified, ar5iv) — [arXiv 2107.09609](https://ar5iv.labs.arxiv.org/html/2107.09609)
- UMT (Liu et al., CVPR 2022), Table 7 modality ablation: YouTube Highlights mAP visual 73.48 / audio 65.61 / both 74.93; TVSum top-5 mAP 81.89 / 76.51 / 83.14; QVHighlights mAP 37.79 / 13.73 / 38.59 and HIT@1 38.97 / 23.91 / 39.85. Audio alone is clearly weaker; audio adds about +1 to +1.5 points on top of visual. (Verified, ar5iv) — [arXiv 2203.12745](https://ar5iv.labs.arxiv.org/html/2203.12745)

**Crowd-replay weak labels (closest analogue to "community clip heat")**
- Mr. HiSum (Sul, Han, Lee; NeurIPS 2023 Datasets & Benchmarks): 31,892 videos from YouTube-8M with frame-importance labels taken from YouTube "Most Replayed" statistics, aggregated over 50,000+ users per video, normalized to 0-1. Baselines: PGL-SUM, VASNet, SL-module. (Verified, GitHub + NeurIPS page) — [GitHub](https://github.com/MRHiSum/MR.HiSum); [NeurIPS poster](https://neurips.cc/virtual/2023/poster/73441)

**Recent (2025-2026)**
- AHA (NeurIPS 2025, arXiv Sept 2025): online/streaming highlight detection with a VLM plus lightweight heads, no look-ahead; reports +5.9% mAP on TVSum and +8.3% mAP on Mr. HiSum over prior SOTA. (Verified, abstract) — [arXiv 2509.16421](https://arxiv.org/abs/2509.16421)
- SVHighlights (arXiv June 2026): 320 sports videos, avg 120 min, 640 h total; labels from automatically aligning official highlight reels to full broadcasts (only 3.7% of frames needed manual correction). Their training-free TF-SELECTOR merges shots into context-aware segments using transcript cues, then has an LLM score each segment. Ablation: adding transcripts to visual captions gave +6.25 HIT@1; audio volume alone added little beyond captions; all three (captions + transcript + volume) best. Models trained on short videos generalize poorly to hour-long videos. (Verified, arXiv HTML) — [arXiv 2606.06926](https://arxiv.org/html/2606.06926v2)
- Training-free VLM highlight detection on QVHighlights is now competitive: REZE (InternVL3-8B) reported 44.18 mAP / 73.41 HIT@1; HL-CLIP 42.40 mAP / 72.42 HIT@1. (Search-snippet only, not opened) — [REZE arXiv 2608.04480](https://arxiv.org/pdf/2608.04480); [HL-CLIP CVPRW 2024](https://openaccess.thecvf.com/content/CVPR2024W/ELVM/papers/Han_Unleash_the_Potential_of_CLIP_for_Video_Highlight_Detection_CVPRW_2024_paper.pdf)
- LLMVS, "Video Summarization with Large Language Models" (CVPR 2025) uses LLM scoring of captioned frames for summarization. (Search-snippet; details not verified) — [GitHub](https://github.com/mlee47/LLMVS)

### Inferences
- For Spike's no-chat YouTube path, the evidence favors: transcript content (LLM) as the primary signal, loudness/LUFS as a minor additive signal, and a crowd-replay signal (Most Replayed) when available. This matches Spike's current 0.7 LLM / 0.3 signal split in direction.
- The Fu et al. chat result is from esports with chat-only char-LSTM models (2017). Modern emote-aware chat rate may do better, and for "funny" (not "important play") moments chat may matter more. Treat "chat is weak" as plausible but not proven for comedy streams.
- SVHighlights' "segment first, then LLM-score segments" approach is close to Spike's candidate-window design and validates it for long videos.

### Gaps
- Mr. HiSum's exact view threshold, metric definitions (F1, mAP at rho), and any human-vs-Most-Replayed agreement study: PDF could not be parsed this session.
- No verified modality ablation for comedic livestreams with chat (2023-2026).
- LoL-specific follow-ups after Fu 2017 were not retrieved.

## Q2. Humor research: datasets, laughter-as-label, LLM humor ability, and ablations

### Takeaway
Text dominates humor detection; audio and video add small gains (about +1.6 accuracy points on UR-FUNNY). Laughter (laugh tracks, live audiences) is the standard free weak label, and it scales. LLMs still correlate only weakly with humans on "how funny" judgments (Spearman about 0.17-0.27 in a 2025 study), but do better at pairwise/relative judgments.

### Cited Findings
- UR-FUNNY (Hasan et al., EMNLP 2019, TED talks): 16,514 instances (8,257 humorous punchlines, labeled by audience laughter markup, + 8,257 negatives). Accuracy: T 62.85, A+V 53.3, T+A 63.28, T+V 63.22, T+A+V 64.47; human 82.5%. (Verified, arXiv HTML) — [arXiv 1904.06618](https://arxiv.org/html/1904.06618v1)
- MUStARD (Castro et al., ACL 2019, sarcasm in sitcoms): 690 videos. F1 speaker-dependent: T 64.6, A 64.6, V 67.4, T+V 71.6, T+A+V 71.5. Speaker-independent: T 59.8, A 62.7, V 53.6, T+A 63.1, T+A+V 62.8. Visual gains in the dependent setting partly reflected character bias, not general cues. (Verified, ar5iv) — [arXiv 1906.01815](https://ar5iv.labs.arxiv.org/html/1906.01815)
- MHD (Patro et al., WACV 2021): The Big Bang Theory dialogues labeled humorous/not by the canned laugh track; text-only LSTM/BERT did worse than text+video or video-only models. (Verified, search summary of paper) — [WACV 2021 PDF](https://openaccess.thecvf.com/content/WACV2021/papers/Patro_Multimodal_Humor_Dataset_Predicting_Laughter_Tracks_for_Sitcoms_WACV_2021_paper.pdf)
- FunnyNet (ACCV 2022) defines a "funny moment" as an n-second clip followed by laughter, using sitcom laughter as the label. (Search-snippet; paper PDF returned 403) — [ACCV 2022](https://openaccess.thecvf.com/content/ACCV2022/papers/Liu_FunnyNet_Audiovisual_Learning_of_Funny_Moments_in_Videos_ACCV_2022_paper.pdf)
- FunnyNet-W (arXiv Jan 2024): visual + audio + Whisper-style text through an LLM, cross/self-attention; unsupervised labeling that "spots and labels funny audio moments"; evaluated on TBBT, MHD, MUStARD, Friends, UR-Funny; claims SOTA on all. (Verified, abstract; ablation numbers not retrieved) — [arXiv 2401.04210](https://arxiv.org/abs/2401.04210)
- Robust laughter detector (Gillick et al., Interspeech 2021) with public code/models; trained across weakly labeled (AudioSet 10-s windows) and strongly labeled (Switchboard) data. (Search-snippet) — [Paper PDF](https://people.ischool.berkeley.edu/~kimiko/papers/Gillick.2021.Interspeech.pdf); [code](https://github.com/jrgillick/laughter-detection)
- StandUp4AI (arXiv May 2025): 3,617 stand-up videos, 334.2 h, 7 languages, 128,194 laughter instances. Labels from automatic laughter detection (Omine et al. 2024 detector) plus an ASR-mismatch trick (Whisper vs WhisperX timestamp gaps + random forest) that raised laughter-detection F1 0.51 to 0.58. Humor framed as word-level tagging ("laughter right after this word"); text models reach about F1 0.42. (Verified, arXiv HTML) — [arXiv 2505.18903](https://arxiv.org/html/2505.18903)
- SMILE (Hyun et al., NAACL Findings 2024; arXiv Dec 2023): "video laugh reasoning", explaining why an audience laughs; fine-tunes GPT-3 and LLaMA on textual descriptions of video. (Search-snippet) — [ACL Anthology](https://aclanthology.org/2024.findings-naacl.73.pdf). A follow-up SMILE-Next (arXiv 2026) exists (not opened) — [arXiv 2605.28084](https://arxiv.org/html/2605.28084)
- ExFunTube (Ko et al., EMNLP 2023): 10,136 funny YouTube shorts (from r/youtubehaiku) with funny-moment timestamps and explanations; converts video to text via zero-shot models and prompts an LLM. (Search-snippet) — [ACL Anthology](https://aclanthology.org/2023.emnlp-main.176/)
- New Yorker caption contest (Hessel et al., ACL 2023): matching, best model 62% vs human 94%; quality ranking, GPT-4 5-shot 68.2% vs human estimate 64.6%; human explanations preferred over GPT-4's in 67.7% of head-to-heads. (Verified, ar5iv) — [arXiv 2209.06293](https://ar5iv.labs.arxiv.org/html/2209.06293)
- Oogiri humor study (arXiv Nov 2025, AAAI): Spearman between LLM and human "overall funniness" ratings is low: Claude Sonnet 4 0.266, GPT-4.1 0.224, Gemini 2.5 Pro 0.169. Accuracy at ordering High/Mid/Low tiers: 50.9-54.1%. Humans weight empathy; LLMs weight novelty. (Search-snippet of paper) — [arXiv 2511.09133](https://arxiv.org/html/2511.09133v1)
- HumorRank (arXiv April 2026): ranks humor via pairwise LLM judgments aggregated with Bradley-Terry MLE and adaptive Swiss pairing; 25,200 judgments; Kendall tau 0.889 between two LLM judges; but the human validation (60 pairs) had low inter-human agreement (Krippendorff alpha about 0.43). (Verified, third-party review page) — [Pith summary](https://pith.science/paper/2604.19786)
- "Cards Against LLMs: Benchmarking Humor Alignment" (arXiv April 2026) exists (not opened). — [arXiv 2604.08757](https://arxiv.org/pdf/2604.08757)

### Inferences
- For Spike: a laughter detector (streamer laugh, co-host/audience laugh) is a cheap, research-backed per-second signal and also a free weak label for tuning weights. StandUp4AI's Whisper/WhisperX mismatch trick is relevant because Spike already transcribes.
- LLM absolute funniness scores are noisy (rho about 0.2 vs humans); human-human agreement on humor is itself low (alpha about 0.43). So the ceiling for any score is limited, and pairwise comparisons are a better use of the LLM.
- Audio/visual adding only 1-2 points over text in UR-FUNNY suggests a transcript-first LLM is a reasonable core, but laughter (an outcome signal, not a content feature) is different from the generic acoustic features those ablations used.

### Gaps
- FunnyNet / FunnyNet-W modality ablation numbers not retrieved (403 / abstract only).
- No source found measuring LLM humor scoring on streamer/gaming transcripts specifically.

## Q3. Fusion and ranking: weights, learning-to-rank, weak labels, peak picking, LLM score calibration

### Takeaway
Replace hand weights with a model fit on weak labels once roughly a few hundred labeled windows exist: logistic regression first, LightGBM LambdaRank grouped by VOD second. Treat LLM absolute scores as noisy and biased: use probability-weighted scores or pairwise comparisons with order swapping, and aggregate pairwise wins with Bradley-Terry.

### Cited Findings
- Learned fusion beats single modalities in every ablation above, but gains from adding a weaker modality are small (UMT +1-1.5 mAP from audio; Fu +0.8-2.5 F from chat). (Verified) — [UMT](https://ar5iv.labs.arxiv.org/html/2203.12745); [Fu 2017](https://aclanthology.org/D17-1102.pdf)
- Weak labels work at scale: Mr. HiSum uses Most Replayed as labels; Moment-DETR gains from ASR-caption pretraining; SVHighlights aligns official highlight reels; MHD/UR-FUNNY/StandUp4AI use laughter. (Verified, see Q1/Q2) — [Mr. HiSum](https://github.com/MRHiSum/MR.HiSum); [QVHighlights](https://ar5iv.labs.arxiv.org/html/2107.09609); [SVHighlights](https://arxiv.org/html/2606.06926v2); [StandUp4AI](https://arxiv.org/html/2505.18903)
- LightGBM `lambdarank` objective; `rank_xendcg` "is faster than and achieves the similar performance as lambdarank". Labels must be integers, higher = more relevant (e.g. 0 bad ... 3 perfect); default `label_gain` 0,1,3,7,15,... Data must be ordered by query, with group sizes passed via `group`. `lambdarank_truncation_level` focuses training on the top results (tied to NDCG@k). Metrics `ndcg` and `map` with `eval_at` (default 1,2,3,4,5). (Verified, docs) — [LightGBM Parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
- Pairwise Ranking Prompting (Qin et al., 2023): pointwise LLM ranking needs calibrated scores that LLMs lack; listwise output often fails to parse. PRP asks "which of two is better", queries both orders to cancel position bias. Variants: all-pairs O(N^2) win counting, sorting O(N log N), sliding-window O(N) per pass for top-K. A 20B FLAN-UL2 with PRP beat pointwise methods by over 10% on average on BEIR. (Verified, ar5iv) — [arXiv 2306.17563](https://ar5iv.labs.arxiv.org/html/2306.17563)
- Position bias (Zheng et al., MT-Bench, NeurIPS 2023): order-swap consistency GPT-4 65.0%, GPT-3.5 46.2%, Claude-v1 23.8%; most judges favor the first position. Verbosity-attack failure: GPT-4 8.7%, Claude-v1/GPT-3.5 91.3%. Self-preference up to +25% win rate. GPT-4 vs expert agreement 85% vs human-human 81%. (Verified, ar5iv) — [arXiv 2306.05685](https://ar5iv.labs.arxiv.org/html/2306.05685)
- Wang et al. 2023 "LLMs are not Fair Evaluators": swapping order let Vicuna-13B "beat" ChatGPT on 66 of 80 queries. Fixes: explain-then-score with k=3 samples (MEC), score both orders and average (BPC); MEC+BPC raised ChatGPT accuracy 44.4% to 58.7%; sending the 20% most uncertain cases to a human reached 71.3% vs human 71.7%. (Verified, ar5iv) — [arXiv 2305.17926](https://ar5iv.labs.arxiv.org/html/2305.17926)
- G-Eval (Liu et al., 2023): compute score = sum p(s_i) * s_i over score tokens instead of taking the sampled integer, because one score (e.g. "3") dominates and integers cause ties. (Verified mechanism, ar5iv.) The Spearman ablation as returned by my fetch tool showed the no-probability variant slightly higher on SummEval (avg 0.514 vs 0.502), which contradicts the paper's framing; treat the size of the gain as unverified. — [arXiv 2303.16634](https://ar5iv.labs.arxiv.org/html/2303.16634)
- Rubric position bias: LLM judges prefer score options at certain positions in the rubric list; permuting rubric order attenuates it (arXiv Feb 2026). (Search-snippet) — [arXiv 2602.02219](https://arxiv.org/html/2602.02219v2)
- Survey consensus: pairwise judging is more position-consistent and closer to humans than absolute scoring or batch ranking. (Search-snippet of survey) — [A Survey on LLM-as-a-Judge](https://arxiv.org/html/2411.15594v1)
- HumorRank shows Bradley-Terry over pairwise humor judgments gives stable rankings across judges (tau 0.889). (Verified, review page) — [Pith](https://pith.science/paper/2604.19786)

### Inferences
- Practical upgrade path for Spike, lowest effort first:
  1. Keep per-VOD z-scores. Log every candidate window's features (each signal's max/mean in window, LLM score) plus its outcome label.
  2. Fit `sklearn.linear_model.LogisticRegression` on (features -> was-it-good). Coefficients replace hand weights and stay interpretable. Needs maybe 200-500 labeled windows (my estimate, not sourced).
  3. Once there are many VODs, switch to LightGBM `rank_xendcg`/`lambdarank` with `group` = VOD, integer labels (0 = not posted, 1 = posted, 2 = posted and performed well), eval `ndcg@5`.
- Weak labels available to Spike: community clips (Twitch), Most Replayed (YouTube), laughter detector hits, own posted-clip views/retention. Normalize posted-clip performance per channel and per upload time before using as a label (inference: views depend on channel size and posting time).
- LLM scoring fixes: (a) ask for reasoning then score, average 2-3 samples; (b) use logprob-weighted score if the local model exposes logprobs (llama.cpp/Ollama do expose them, recalled, not verified this session); (c) for the final top ~10, run pairwise "which is funnier" with both orders and Bradley-Terry or win counts. With N=10, all-pairs = 45 pairs x 2 orders = 90 calls; sliding/sort variants cut that.
- Rank-normalize or z-score LLM scores per VOD before blending with signal z-scores, so 0.7/0.3 mixes comparable scales (inference; a raw 1-10 LLM score and a z-score are not on the same scale).
- Peak picking/NMS: standard practice is local maxima with a minimum distance and prominence (e.g. `scipy.signal.find_peaks(distance=, prominence=)`), then temporal NMS over candidate windows by IoU. Not verified from a source this session; recalled.

### Gaps
- No paper found that compares hand-set late-fusion weights vs learned weights on clip-performance labels specifically.
- Exact data size needed for stable logistic regression / LambdaRank on this task: unsourced.

## Q4. Evaluation: small labeled set, metrics, offline loop

### Takeaway
Use the benchmark metrics directly: HIT@1 (is the top pick good), precision@k / mAP over ranked windows, and NDCG@k for graded labels. Evaluate per VOD and average, with a fixed held-out VOD set.

### Cited Findings
- QVHighlights defines HIT@1 as whether the top-scored clip is rated "Very Good", and mAP over saliency; labels are 5-point Likert from 3 annotators, averaged. (Verified) — [arXiv 2107.09609](https://ar5iv.labs.arxiv.org/html/2107.09609)
- TVSum is reported with top-5 mAP; YouTube Highlights with mAP. (Verified, UMT Table 7) — [arXiv 2203.12745](https://ar5iv.labs.arxiv.org/html/2203.12745)
- LightGBM supports `ndcg` and `map` with `eval_at` positions directly. (Verified) — [LightGBM docs](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
- Humor labels are inherently noisy: inter-human Krippendorff alpha about 0.43 in HumorRank's validation; UR-FUNNY human accuracy only 82.5%. (Verified) — [Pith](https://pith.science/paper/2604.19786); [UR-FUNNY](https://arxiv.org/html/1904.06618v1)
- Uncertainty-routed human review: labeling only the 20% most uncertain items closed most of the gap to human accuracy in Wang et al. (Verified) — [arXiv 2305.17926](https://ar5iv.labs.arxiv.org/html/2305.17926)

### Inferences
- Solo-dev loop: pick 15-30 VODs (mix Twitch + YouTube). For each, label all candidate windows the pipeline proposes, plus any community clips / Most Replayed peaks it missed (for recall). Use a 0-3 scale, like QVHighlights' Likert. Re-label a 10% sample a week later to measure own consistency.
- Freeze 5-10 VODs as test set; never tune on them. Report HIT@1, precision@5, NDCG@5, and recall of known community clips per VOD.
- Run the eval as a script on every weight/prompt change; log results to a CSV keyed by commit. Spend labeling effort on items where the LLM and signal scores disagree (uncertainty sampling, per the Wang result).
- Label noise ceiling means small metric differences (a point or two) on 15 VODs are likely noise; use per-VOD paired comparisons.

### Gaps
- No source found giving a recommended minimum eval-set size for highlight ranking.

## Q5. Boundary detection: natural clip start/end

### Takeaway
Research supports building candidates from semantically merged segments (shots joined by transcript cues), and placing the label point at the laugh/reaction with context before it. Word-level timing from ASR is the practical boundary unit.

### Cited Findings
- SVHighlights' TF-SELECTOR detects shot boundaries, then merges adjacent shots sharing transcript content into context-aware segments before scoring; this beat clip-level scoring on long videos. (Verified) — [arXiv 2606.06926](https://arxiv.org/html/2606.06926v2)
- FunnyNet labels the n seconds *before* laughter as the funny moment (setup precedes reaction). (Search-snippet) — [ACCV 2022](https://openaccess.thecvf.com/content/ACCV2022/papers/Liu_FunnyNet_Audiovisual_Learning_of_Funny_Moments_in_Videos_ACCV_2022_paper.pdf)
- UR-FUNNY pairs each punchline with its preceding context sentences; StandUp4AI labels the word right before laughter. (Verified) — [UR-FUNNY](https://arxiv.org/html/1904.06618v1); [StandUp4AI](https://arxiv.org/html/2505.18903)
- Moment-DETR / UMT predict moment spans (start, end) directly; UMT treats moment retrieval as keypoint detection. (Verified, abstracts) — [QVHighlights](https://ar5iv.labs.arxiv.org/html/2107.09609); [UMT](https://arxiv.org/abs/2203.12745)

### Inferences
- For Spike: anchor on the peak (laugh/chat spike), then search backward for a sentence start from ASR word timestamps (setup) and forward to the end of the reaction/laugh plus the next sentence end. Snap both edges to silence gaps. Optionally ask the LLM to choose start/end sentence indices from the transcript window.
- Reaction signals (chat, laughter) lag content by a few seconds, so the window should extend before the signal peak more than after it (inference consistent with FunnyNet's "before laughter" labeling; chat delay size not sourced here).

### Gaps
- No verified paper on punchline/setup boundary segmentation for streams; no measured chat reaction delay found this session.
