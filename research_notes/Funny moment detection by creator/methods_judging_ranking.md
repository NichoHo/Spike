# Methods for funny / highlight moment detection: candidates, judging, ranking, per-creator adaptation

Scope note: the earlier reports (`reports/Funny clip detection signals.md`, `reports/Twitch chat highlight detection.md`) already cover the UR-FUNNY ablation (text 62.85%, all three 64.47%), FunnyNet-W (audio+text 84.5 F1 vs text 77.8), StandUp4AI, YAMNet/PANNs, LLM punchline extraction (GPT-4o 48.9%, Claude 3.5 Sonnet 43.4%), Spearman ~0.17 to 0.27 for absolute LLM funniness ratings, HumorBench, cliptron (LLM Recall@10 0.708 vs chat baseline 0.917), Pairwise Ranking Prompting, MT-Bench position bias (65% consistency), Wang et al. order-swap + 3 samples (44.4% to 58.7%), Gemini video docs and pricing, Mr. HiSum / Most Replayed, the CHI 2025 heatmap study, SVHighlights, and Pickering 2011 on pauses. These notes add what those reports do not cover. Dates are arXiv or venue dates. Tool budget limited this pass to about 18 calls, so several items are marked as gaps.

## Multimodal humor and sarcasm detection: which modality carries the signal

### Takeaway
For humor, text dominates (see earlier report). For sarcasm, which depends on tone, audio carries the most signal and beats text by about 9 F1 points when an audio LLM is used. Speaker-dependent training helps only marginally on MUStARD-style data.

### Cited Findings
- Original MUStARD (ACL 2019): TV-show utterances with text, audio and video; multimodal input reduced relative error of sarcasm detection by up to 12.9% in F-score compared with single modalities ([Castro et al., arXiv 1906.01815](https://arxiv.org/pdf/1906.01815)).
- 2025 evaluation of multimodal LLMs on MUStARD++: Qwen-Audio (audio only) reached 75.1% F1, text-only 66.4%, text+audio 76.8%, text+video 71.7%, audio+video best at 77.9%. Visual-only models were weakest ([arXiv 2509.15476](https://arxiv.org/pdf/2509.15476)). Numbers come from search-result summaries of the paper, not a full read; protocols differ between papers, so cross-paper comparisons are loose.
- MUStARD++ corpus paper: speaker-dependent results were "marginally better in all modality combinations"; their model scored 72.0 F1 speaker-independent vs 74.2 speaker-dependent on original MUStARD, and 70.2 vs 70.3 on MUStARD++ ([arXiv 2206.02119](https://arxiv.org/pdf/2206.02119)).
- ProSarc (2026) ablation on MUStARD++: full model 70.79% F1; removing the prosodic incongruity analyzer dropped it to 67.69%, the largest single drop ([arXiv 2606.06168](https://arxiv.org/pdf/2606.06168)).
- A 2026 EACL SRW paper (leave-one-speaker-out on MUStARD++) found sarcasm with overt prosodic and visual cues much easier to detect than monotone, context-dependent sarcasm ([ACL Anthology 2026.eacl-srw.36](https://preview.aclanthology.org/ingest-eacl/2026.eacl-srw.36.pdf)).
- AMuSeD reports 81.0% F1 with text+audio plus augmentation, above prior trimodal MUStARD results ([arXiv 2412.10103](https://arxiv.org/html/2412.10103v1)).

### Inferences
- Modality value depends on humor type: wordplay and stories live in the transcript; sarcasm, deadpan and "the way they said it" live in audio. Gemini, which ingests audio with video, is the natural judge for delivery-driven moments; a text-only Claude judge will miss them.
- Video adds the least in both humor and sarcasm ablations, so frame sampling rate is not where to spend budget. Audio and transcript are.
- Speaker-dependent gains are small in the academic data (0 to 2 F1), which tempers expectations for heavy per-creator model training. Per-creator calibration (normalization, exemplars) is cheaper and probably captures most of it (inference, untested).

### Gaps
- I did not re-verify MHD (Big Bang Theory laugh-track) ablation numbers in this pass; see the earlier report for its role as a laugh-track dataset.
- No study found that measures a streamer's own laughter (rather than audience or laugh track) as a label.

## MLLM highlight detection and moment localization in long video

### Takeaway
Video LLMs localize well inside short windows but collapse on hour-long video because they pick the wrong region ("search failure"). A retrieve-then-ground pipeline (cheap retrieval proposes a few short windows, the MLLM grounds within them) beat a monolithic Video-LLM by 6.7x on hour-scale grounding. For humor specifically, older video LLMs could not localize funny moments at all.

### Cited Findings
- ExtremeWhenBench (NAVER, June 2026): 2,273 queries over 194 videos, mean 75.7 min, max 9 h. On Charades-STA (30 s clips) vs this benchmark, mIoU dropped: Qwen3.5-9B 0.579 to 0.110 (best N), Gemini-2.5-flash (1k frames) 0.308 to 0.053, Gemini-3.5-flash (auto-fps) 0.466 to 0.115, GPT-5.4 (64 frames) 0.299 to 0.013. A plain CLIP ViT-L/14 frame-retrieval baseline at 1 fps scored 0.269, beating every Video-LLM under their compute budget ([arXiv 2606.12300](https://arxiv.org/pdf/2606.12300)).
- Same paper: 85% of failures (IoU < 0.05, 100 sampled cases) were search failures (prediction more than 5 min from ground truth), 11% localization failures. When cropped to a 30 s window around the target, Qwen (0.572) and Gemini-3.5-flash (0.578) matched their short-video ceiling, so localization is intact once in the right region. Qwen dropped below CLIP at about a 20 min window; Gemini-3.5-flash stayed above CLIP until full-video length ([arXiv 2606.12300](https://arxiv.org/pdf/2606.12300)).
- Retrieve-then-ground hybrid (CLIP top-3 windows, +/-1 min each, NMS 60 s, then Video-LLM): mIoU 0.354 using 6 min of context vs 0.053 for the monolithic Video-LLM on the full 76 min (6.7x) and 0.269 for retrieval alone (1.32x). Performance peaked at K=3 windows and degraded at K=10, where the model again had to search about 20 min ([arXiv 2606.12300](https://arxiv.org/pdf/2606.12300)).
- Frame scaling alone does not fix it: Qwen3.5-9B mIoU on the hour-scale benchmark rose from 0.022 at 128 frames to 0.110 at 2,048 frames and still trailed CLIP retrieval ([arXiv 2606.12300](https://arxiv.org/pdf/2606.12300)).
- TimeChat (CVPR 2024): zero-shot gains over prior video LLMs of +27.5 R@1 (IoU=0.5) on Charades-STA and +5.8 HIT@1 on QVHighlights ([arXiv 2312.02051](https://arxiv.org/abs/2312.02051)). A 2025 survey lists TimeChat zero-shot QVHighlights at 14.5 mAP / 23.9 HIT@1 (search-summary of the survey table; [arXiv 2508.10922](https://arxiv.org/pdf/2508.10922)).
- The same survey's fine-tuned QVHighlights highlight-detection table (read directly from the PDF): VideoChat-TPO 38.8 mAP / 66.2 HIT@1, VideoExpert 36.1 / 61.0, TRACE 31.8 / 51.5, VideoChat-T 27.0 / 55.3, TemporalVLM 25.1 / 43.0, VTG-LLM 24.1 / 41.3, MLLM-TA 23.9 / 40.1, TimeChat 21.7 / 37.9 ([arXiv 2508.10922](https://arxiv.org/pdf/2508.10922)). Survey also notes direct fine-tuning of MLLMs for highlight detection "remains unreported" and HD needs specialized adaptations.
- TimeLens2 (July 2026) reports Gemini 2.5 Pro at 75.9 R1@0.5 on QVHighlights moment retrieval (short videos) and 20.5 R1@0.5 on VUE-TR; TimeLens2-8B trails it by 0.2 points on QVHighlights ([arXiv 2607.17423](https://arxiv.org/pdf/2607.17423), via search summary).
- LongEgoRefer (2026): Gemini 2.5 Pro reached 49.93 tIoU@0.3 and 19.35 tIoU@0.5 on long egocentric temporal grounding ([arXiv 2607.02096](https://arxiv.org/pdf/2607.02096), via search summary).
- TimeScope (July 2025): Gemini 2.5 Pro kept near 100% accuracy on long-video QA until about 20 min, then fell to about 65% by 8 h; it was the only model reported to hold up past an hour ([Simon Willison, 2025-07-23](https://simonwillison.net/2025/Jul/23/timescope/)). This is QA, not grounding.
- FunQA (ECCV 2024): 4.3K counter-intuitive clips (HumorQA, CreativeQA, MagicQA), 312K QA pairs, 24 h. For the timestamp localization task the authors state "There is no model that has the ability to answer the Timestamp Localization Task"; models asked for a time span described the video instead ([arXiv 2306.14899v2](https://arxiv.org/html/2306.14899v2)). These were 2023-era open video LLMs, not Gemini.

### Inferences
- Candidate generation should not be "ask Gemini for the funniest moments of this 3-hour VOD". Use cheap signals (laughter, chat, replay heat, transcript-LLM proposals) to pick a handful of windows, then ask the MLLM to judge and ground inside each window of a few minutes. The K=3 peak and K=10 degradation suggest a few short windows per call rather than many in one call.
- Gemini is the strongest long-context model in every benchmark found, so a whole-VOD Gemini pass is a reasonable extra candidate source (recall), but its timestamps should be treated as coarse (minutes), and refined by a second short-window call or by transcript/laugh alignment.
- Funny-moment localization has no direct MLLM benchmark with modern models; the closest evidence (FunQA) is negative for old models. Spike's own eval set is the only way to measure this.

### Gaps
- No benchmark found that measures Gemini 2.5/3.x on localizing humorous moments in hour-long video. FunQA H1 has not been re-run with frontier models in sources found.
- VTimeLLM and UniVTG absolute QVHighlights numbers could not be cleanly extracted (survey table columns garbled in search results).
- TimeLens2 and LongEgoRefer numbers come from search summaries, not a full read.

## LLM-as-judge for humor: reliability, bias, pairwise vs absolute, ranking

### Takeaway
LLMs separate clearly funny from clearly unfunny captions about as well as crowd workers (65 to 77%), but fall to near chance on close calls, and group/listwise comparisons beat pairwise for models. Persona prompts barely help; fine-tuning (or anchoring) on the target audience's own preferences is the one intervention with a large, measured gain (67% to 82.4%).

### Cited Findings
- "Do Androids Laugh at Electric Sheep?" (ACL 2023): New Yorker caption tasks (matching, quality ranking, explanation). Best multimodal models were 30 accuracy points behind humans on matching; humans preferred human explanations over few-shot GPT-4 explanations in more than 2/3 of head-to-heads ([Hessel et al., arXiv 2209.06293](https://arxiv.org/abs/2209.06293)).
- "Humor in AI" (NeurIPS 2024 D&B): 250M+ votes on about 2.2M captions. Distinguishing top-10 captions from captions ranked 1000-1009: GPT-4-Turbo pairwise 66.5% (text descriptions), GPT-4o 65%, GPT-4o-vision with the image 60.5%, crowd workers 60.8 to 61.7%. In group (listwise) comparison GPT-4-Turbo reached 77.5% vs crowd 59.2%; a former New Yorker cartoon editor reached 94.3% ([arXiv 2406.10522](https://arxiv.org/html/2406.10522v2)).
- Same paper: group comparisons were more accurate for LLMs but harder for crowd workers; adding the image lowered GPT-4-Turbo's accuracy (60.5% with image vs 67% text-only); GPT-4 models showed "a strong bias" toward one answer position, corrected by recalibrating the threshold on a validation set (size of bias not reported) ([arXiv 2406.10522](https://arxiv.org/html/2406.10522v2)).
- "Bridging the Creativity Understanding Gap" (Feb 2025): GPT-4o prompting about 67% on 10-vs-1000 caption ranking (73% with improved visual annotation, 5-shot); persona prompting gained about 3 points at best; o1-preview explanations 76%; fine-tuning GPT-4o on crowd preferences gave 79.4% without and 82.4% with explanations. On the harder 30-vs-300 split the best model reached 63.2% (prompting 53.9%). Five human experts averaged 78% (10-vs-1000) and 61.6% (30-vs-300); best single expert 85.3%; expert agreement Fleiss kappa 0.36 and 0.23 ([arXiv 2502.20356](https://arxiv.org/html/2502.20356)). Note: the paper's "matches/outperforms experts" claim holds against the expert average, not the best expert.
- Same paper: persona prompting failed to capture the contest crowd's preferences while fine-tuning on their rankings did; authors argue LLMs struggle with subgroup preferences without data ([arXiv 2502.20356](https://arxiv.org/html/2502.20356)).
- HumorRank (2026) argues 1-10 scalar scores fail to capture funniness and uses pairwise "duels" aggregated into a global ranking ([search summary via alphaxiv 2604.19786](https://www.alphaxiv.org/overview/2604.19786)). Cards Against LLMs (2026) frames humor alignment as picking the funniest of several options ([arXiv 2604.08757](https://arxiv.org/pdf/2604.08757)). Neither was read in full.
- Score compression / calibration drift in pointwise judging is widely reported by practitioners (scores cluster near the high end; anchors drift across samples and model versions) but I found no peer-reviewed study quantifying it for humor ([GoDaddy engineering](https://www.godaddy.com/resources/news/calibrating-scores-of-llm-as-a-judge); [barkingiguana rubric post](https://barkingiguana.com/writing/llm-as-a-judge-designing-a-rubric-you-can-trust/)). A 2026 preprint reports that post-hoc affine rescaling of judge scores never matched a judge given human-rated demonstrations in the prompt, and hurt below about 40 to 80 anchors ([arXiv 2606.03043](https://arxiv.org/pdf/2606.03043), via search summary, preliminary).

### Inferences
- For ranking a small candidate set, use listwise (show 4 to 8 candidates, ask for an order or best pick) or pairwise with both orders, not absolute 0-100 scores. Use the absolute score only as a coarse filter, normalized per VOD.
- Close calls are near chance for both models and experts (30-vs-300: 54 to 63%), so heavy tournament machinery on near-tied candidates buys little; spend calls on separating the top tier from the rest.
- Giving the judge text descriptions sometimes beat giving it pixels (caption contest). For Spike, a transcript with inline non-verbal markers may judge as well as raw frames for many moments; Gemini AV judging should be validated against text-only on Spike's own data rather than assumed better.
- The strongest lever is target-audience data: fine-tuning or in-prompt demonstrations of what this creator's audience liked. Personas ("you are a Twitch viewer") are not worth tuning.

### Gaps
- No humor-specific study measured self-consistency (multiple samples averaged) or Elo/Bradley-Terry vs listwise directly. The earlier report's Bradley-Terry evidence remains the best available.
- No study on Claude or Gemini position bias size in humor pairwise tasks.

## Personalization: surprise relative to a creator's baseline

### Takeaway
User-history-conditioned highlight detection is an established line (ECCV 2020, ECCV 2022) and helps, but the clearest measured humor-specific evidence is the caption-contest result: matching a specific audience's taste required its preference data, and personas did not substitute.

### Cited Findings
- Rochan et al. (ECCV 2020) "Adaptive Video Highlight Detection by Learning from User History": conditions a temporal-conv highlight detector on the user's previously created highlights via a temporal-adaptive instance normalization layer whose parameters come from a history encoder; evaluated with per-video mAP on a large-scale user-GIF dataset; reports more accurate, user-specific predictions ([arXiv 2007.09598](https://arxiv.org/abs/2007.09598)). Absolute mAP gain not verified this pass; a secondary summary cites +0.8 mAP (5.2% relative), unconfirmed ([search result](https://astro.paperswithcode.com/paper/adaptive-video-highlight-detection-by)).
- PAC-Net (ECCV 2022) generates a user-adaptive highlight classifier from preference-related user history ([ECVA](https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/1853_ECCV_2022_paper.php)). PHD-GIFs (2018) is the precursor dataset/approach ([paperswithcode 1804.06604](https://paperswithcode.co/paper/1804.06604)).
- Speaker-dependent vs independent sarcasm training differs by 0.1 to 2.2 F1 ([arXiv 2206.02119](https://arxiv.org/pdf/2206.02119)).
- Fine-tuning on a target crowd's preferences: 67% to 82.4%; persona prompting about +3 points ([arXiv 2502.20356](https://arxiv.org/html/2502.20356)).
- Demonstration-anchored judges beat post-hoc rescaling ([arXiv 2606.03043](https://arxiv.org/pdf/2606.03043), preliminary).

### Inferences
- Cheapest effective adaptation, in order: (1) per-creator normalization of every signal (z-score or percentile against that channel's own history, so a loud streamer's laughter is not always "high"); (2) few-shot exemplars in the judge prompt: 3 to 5 of the creator's past top clips (transcript excerpt plus why it hit) and 1 to 2 rejected ones; (3) a small learned per-creator re-ranker once approve/reject labels exist.
- "Surprise relative to baseline" maps naturally to per-channel anomaly scoring on signals (z vs the channel's rolling distribution) rather than per-VOD only; this is an inference, no source tests it for humor.

### Gaps
- No study found that tests few-shot exemplars of a creator's past viral clips in an LLM highlight-judging prompt.
- No humor-specific per-creator anomaly-detection evidence.

## Learning from engagement data and user feedback

### Takeaway
Most Replayed heatmaps and community clips are validated weak labels (earlier reports). This pass found no new primary evidence on bandits or reward models for clip selection; the caption-contest fine-tuning result is the best evidence that preference data beats prompting.

### Cited Findings
- Mr. HiSum (31,892 videos, Most Replayed labels) and the CHI 2025 heatmap study are covered in the earlier report ([Mr. HiSum GitHub](https://github.com/MRHiSum/MR.HiSum); [ACM DL](https://dl.acm.org/doi/10.1145/3706598.3713880)).
- Crowd-preference fine-tuning raised humor ranking accuracy by about 15 points over prompting ([arXiv 2502.20356](https://arxiv.org/html/2502.20356)).
- 250M crowd votes produce stable rankings that separate top from mid-ranked captions, while individual expert agreement is only kappa 0.23 to 0.36 ([arXiv 2406.10522](https://arxiv.org/html/2406.10522v2); [arXiv 2502.20356](https://arxiv.org/html/2502.20356)).

### Inferences
- Single approve/reject clicks are noisy (individual raters disagree a lot), so aggregate them per creator before updating prompts or weights, and prefer pairwise feedback ("A or B?") which matches the stronger judging format.
- A practical loop: store approved/rejected clips as exemplars (rotating into the prompt), and once a few hundred labels exist, fit the ranker described in the earlier report. A bandit is not justified until there is enough traffic to explore.

### Gaps
- No primary sources found on contextual bandits or reward models for highlight/clip selection, or on clipping startups' eval write-ups with numbers.

## Clip boundaries and comedic timing

### Takeaway
New 2026 evidence says timing matters more than content for how a joke lands: pauses lengthen before high-surprise punchlines, and stillness correlates with laughter. Trimming "dead air" before a punchline is likely to remove part of the joke.

### Cited Findings
- CogSci 2026 "Timing is Everything" (828 professional Chinese stand-up performances): temporal features "substantially outweigh" semantic incongruity in predicting audience appreciation; peak (not average) semantic violation matters; pauses systematically lengthen before high-surprise punchlines; this coupling separated successful from unsuccessful performances. No effect sizes on the page ([project page](https://yzhu.io/publication/humor2026cogsci/)).
- TIC-TALK (March 2026) multimodal stand-up timing database: low movement correlated with audience laughter at r = -0.75, consistent with stillness before punchlines; correlational ([arXiv 2603.21803](https://arxiv.org/pdf/2603.21803), via search summary).
- Earlier report: Pickering 2011 found the pause-before-punchline cue contested in conversational joke-telling; this new work is for performed stand-up and supports it there. Popular claims of an optimal 500 to 800 ms pause are unsourced.
- ExtremeWhenBench: once the model is in the right region, boundary placement has "reasonable fidelity" ([arXiv 2606.12300](https://arxiv.org/pdf/2606.12300)).

### Inferences
- Silence-removal / jump-cut passes should protect the 0.3 to 2 s gap immediately before the punchline line and the laugh after it; only trim silence earlier in the setup. Boundary start should be on the setup sentence, end after the reaction (laugh offset plus a short tail), as the earlier report recommends.
- Streams are not stand-up; pause effects in casual talk are weaker (Pickering), so treat this as "do not destroy" rather than "use pause as a detector".

### Gaps
- No study found that measured audience response to the same clip with and without pre-punchline pauses removed.
- Exact pause durations and effect sizes from the CogSci 2026 paper not retrieved.
