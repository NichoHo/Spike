# Academic work on chat-based and chat+multimodal livestream highlight detection

Verification tags used below:
- **[V]** = verified: I read the relevant passage or table in the paper's full text this session (PDF converted to text).
- **[X]** = extracted from the full-text web page by a fetch/scrape tool's summarizer (not read line by line by me; numbers may carry extraction error).
- **[S]** = search snippet or abstract only.
- **[I]** = my inference.

Research date: 2026-10-01.

## Key papers and datasets (what exists, dates, sizes, labels)

### Takeaway
The core chat-highlight literature is small and mostly esports-centric: Fu et al. 2017 (LoL, EMNLP), Han et al. 2019 (biGRU on chat), Liaw & Dai 2020 (MDM), Song, Park & Cha 2021 (EPJ Data Science, 2M Twitch community clips, the only large study on personality streams), Ringer's TwitchChat dataset 2020 and PhD thesis 2022 (TASTE chat transformer plus A/V fusion), Kuaishou's KuaiHL 2024 (ICME, chat+ASR+frames, labels from viewer retention), and a 2026 GamiFIN LLM study on Twitch clips with chat. Danmaku work (Ping & Chen 2017 and others) supplies the lag-calibration idea.

### Cited Findings
**Fu, Lee, Bansal, Berg 2017, "Video Highlight Prediction Using Audience Chat Reactions" (EMNLP 2017) [V]**
- Dataset: 321 LoL esports videos, 218 NALCS (English) and 103 LMS (Traditional Chinese); splits NALCS 128/40/50, LMS 57/18/28 (train/val/test); each game 30 to 50 min. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf)
- Chat volume: average 7,490 chats per video (SD 4,922); about 21,526 viewers per game, of whom ~2,185 unique users typed in chat (~10%). Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf)
- Labels: community highlight videos (5 to 7 min) from a single YouTube channel, frame-matched back to the broadcast. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf)
- Test F1: chat-only L-Char-LSTM 43.2 (NALCS) / 39.7 (LMS); video-only V-CNN-LSTM 72.2 / 69.2; joint lv-LSTM 74.7 / 70.0. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf)
- Character-level LSTM beat word-level LSTM "by 22.3%"; the authors argue the char model picks up content, not just counts, since LMS has less volume variance yet chat still works. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf)

**Han, Huang, Chen 2019, "A deep learning model for extracting live streaming video highlights using audience messages" (AICCC 2019, ACM) [S via Ringer thesis ref 69]**
- biGRU-DNN over per-second mean-pooled word vectors. Ringer could not obtain code or data from the authors and reimplemented it; the reimplementation scored F1 0.107 on Ringer's test set and "struggled to converge". Source: [Ringer thesis 2022, §5.3](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]

**Liaw & Dai 2020, "Live Stream Highlight Detection Using Chat Messages" (IEEE MDM 2020, pp. 328 to 332, DOI 10.1109/MDM48529.2020.00072) [S]**
- Only bibliographic metadata retrieved; a search snippet says it applies Long-Short Term Attention (LSTA) to esports chat. No numbers obtained. Source: [ResearchGate](https://www.researchgate.net/publication/343522615_Live_Stream_Highlight_Detection_Using_Chat_Messages)

**Drankou & Zykov 2020, "Chat-based approach applied to automatic livestream highlight generation" (Intelligent Decision Technologies, Springer, pp. 437 to 447) [S, citation only]**. Cited in [Song et al. 2021 references](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6)

**Kaytoue et al. 2012, "Watch me playing, I am a professional" (WWW 2012 companion)** is a first characterization study of Twitch, not a highlight detector; Ringer used it to motivate channel selection for TwitchChat. Source: [Ringer thesis ref 92/93](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]

**Song, Park, Cha 2021, "Finding epic moments in live content through deep learning on collective decisions" (EPJ Data Science 10:43, Aug 2021) [X]**
- Data: 213 (male) Twitch streamers, May to June 2019; ~5.6 h average stream; ~19,842 chat utterances per stream; **2 million user-created Twitch clips** as labels. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6)
- Labels from clip views: "Popular" = top 5% (>=34 views), "Ordinary" = bottom 50% (<=2 views); random 30 s stream segments as reference. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6)
- Model MINT (Multimodal detection with INTerpretability) with a learned modality-importance mechanism; released pre-trained Twitch emote embeddings. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6); code repo [dscig/twitch-highlight-detection](https://github.com/dscig/twitch-highlight-detection) [S]

**Ringer, Walker, Nicolaou 2020, "TwitchChat: A Dataset for Exploring Livestream Chat" (AIIDE 2020) [V via thesis]**
- Collected June to October 2019 from the most popular English channel for each of 20 top games; 666 streamers, 1,951 stream documents, >60 million tokens; usernames salted+SHA1 hashed; released raw CSV with metadata. Source: [Ringer thesis §5.2.1](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf); [AAAI OJS](https://ojs.aaai.org/index.php/AIIDE/article/view/7439)
- TwitchChat is a chat corpus without highlight labels; it was used for word-vector and MLM pre-training. Source: [Ringer thesis §5.3.2](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]

**Ringer 2022, PhD thesis "Multi-Modal Livestream Highlight Detection from Audio, Visual, and Language Data" (University of York, Aug 2022) [V]**
- Chat model TASTE (Time-Aware Stacked Transformer Encoder): a per-message transformer (CLS pooling) then a "stack of messages" transformer with sine encoding of each message's timestamp, so rate is modeled implicitly; window = 4 s context + 15 s sample + 4 s context (23 s); up to 320 messages, 64 tokens each; MLM pre-trained on TwitchChat + Fu data + Worlds data. Source: [thesis §5.3.1](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf)
- Training: Fu's 218 NALCS games + 49 Worlds 2020 group-stage games; test: 27 Worlds 2020 knockout games; ~12.5% of content labeled highlight. Source: [thesis §5.3.1.3, §5.3.2](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf)
- Related: "Autohighlight: Highlight detection in League of Legends esports broadcasts via crowd-sourced data" (Machine Learning with Applications, 2022) is the journal form of the thesis's audio-visual Auto-Highlight model. Source: [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2666827022000469) [S; page returned 403]
- Earlier: Ringer & Nicolaou 2018 "Deep unsupervised multi-view detection of video game stream highlights" (FDG 2018), novelty-based, uses game footage plus streamer face and speech. Source: [ACM DL](https://dl.acm.org/doi/10.1145/3235765.3235781) [S]

**Deng et al. 2024, "A Multimodal Transformer for Live Streaming Highlight Prediction" (KuaiHL, ICME 2024, arXiv 2407.12002) [X]**
- KLive dataset: 17,897 Kuaishou live rooms, 19,334 h; 1,436,979 train / 286,510 test 30 s segments; each segment has 3 frames, ASR text and audience comments; labels from viewer behaviour (Long View Through Rate). Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002)
- Adds a Modality Temporal Alignment Module because "comments from the audiences may experience some time lag". Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002)

**Lindroos et al. 2026, "Leveraging Large Language Models for Twitch Video Clip Understanding and Summarization" (GamiFIN '26, March 2026) [X]**
- 56 Twitch clips with chat logs; Gemini 1.5 to 2.5 models; chat fed like a subtitle track with a chain-of-thought prompt. Source: [ACM DL](https://dl.acm.org/doi/10.1145/3789624.3789641)

**Danmaku datasets [S]**
- Ping & Chen 2017 (below): Bilibili corpus of 2,108,746 comments from 6,368 videos for embeddings; 11-video highlight test set. Source: [arXiv 1708.02210](https://arxiv.org/abs/1708.02210) [V]
- VideoIC (ACM MM 2020): 4,951 Bilibili videos, 557 h, ~5 million comments (avg 1,077 per video), built for comment generation. Source: [ACM DL](https://dl.acm.org/doi/10.1145/3394171.3413890)
- DanmakuTPP-Events: Bilibili bullet comments with timestamps and frames, for temporal point-process modeling. Source: [awesomepapers](https://awesomepapers.io/multimodal/datasets/danmakutpp-events)
- Chinese esports danmaku entity-sentiment dataset: 124,574 comments from 2023 LoL pro league/MSI videos. Source: [ScienceDB](https://www.scidb.cn/en/detail?dataSetId=1badf91b7d774ecd88c8811855d2501f)

### Inferences
- [I] Song et al. 2021 is the study closest to Spike's setting (personality streams, community clips as labels, emote semantics). Fu and Ringer are both LoL esports, where visual game events dominate and chat is a crowd "cheering" signal.
- [I] No public, labeled, multimodal dataset of personality-driven Twitch streams with funny-moment labels was found. Spike would have to build its own eval set.

### Gaps
- Liaw & Dai 2020 and Han et al. 2019 results not retrieved (paywalled; only metadata).
- No paper titled "Jiang et al., Detecting highlights from live streaming chat" was found; the user's recalled title may correspond to Liaw & Dai 2020 or Han 2019. Not confirmed.
- "LiveChat" (2023 ACL live-streaming dialogue dataset, from Douyin) was not searched in depth; from memory it is a response-generation corpus with no highlight labels [unverified recall].
- KuaiHL claims a dataset/code release; release status not checked.

## Which chat features matter, and rate-only vs content-aware models

### Takeaway
Content-aware chat models beat message rate, but the margin depends heavily on architecture and domain. On LoL Worlds 2020, a timestamp-aware transformer (TASTE) doubled the F1 of a message-density baseline (0.416 vs 0.190), while poorly designed content models did worse than density. On 2M Twitch clips, a deep model on chat frequency alone nearly matched everything else (AUC ~0.875 vs MINT ~0.89 to 0.90), so rate is a very strong baseline for personality streams.

### Cited Findings
- Ringer Table 5.4 (Worlds 2020 knockout test, F1): Density (message count) 0.190; biGRU-DNN (Han 2019 reimpl.) 0.107; L-Char-LSTM (Fu 2017) 0.300; single-second transformer (content of one second, no rate) 0.182; TASTE Small (2+5+2 s) 0.314; TASTE (4+15+4 s) 0.416. Precision/recall for TASTE 0.463/0.378. Source: [Ringer thesis §5.3.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Density and single-second content models were statistically indistinguishable (Wilcoxon p ~0.9). Ringer explains this by an esports "cheering" effect: a small set of tokens spammed rapidly shows up both as content and as density. Source: [Ringer thesis §5.3.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Collapsing messages into per-second pooled vectors (Han's biGRU) loses information; time-awareness is "one of the benefits of TASTE". Source: [Ringer thesis §5.3.1, §5.3.5](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Chat models show large per-game variance: TASTE per-video F1 min 0.061, max 0.542, median 0.431; density min 0.038, max 0.479; in one game density "performed very well", likely because the game was particularly engaging. Source: [Ringer thesis Table 5.5](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Fu 2017: the char-level model's input concatenates chats with stop characters, so it "could learn to use this #chats information"; char-level beat word-level by 22.3%. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf) [V]
- Song et al. 2021 results (accuracy / AUC): feature-based chat frequency 0.7597 / 0.8020; **deep chat frequency 0.8125 / 0.8748**; feature-based chat content 0.7627 / 0.8054; deep chat content 0.7822 / 0.8350; feature-based video 0.6424 / 0.6960; deep video 0.8140 / 0.8901; **MINT 0.8261 / 0.8979**. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]. Conflict: a second extraction pass reported MINT AUC 0.8911 and an ablated MINT of 0.8173 / 0.8911; treat the third decimal as uncertain.
- Song et al. engagement features: utterance frequency, average utterance length, emote frequency, emotes per utterance, subscriber participation ratio, utterances per user, semantic incoherence (Shannon entropy), VADER sentiment. Chat frequency and unique participants were normalized by channel follower count "to prevent the model from learning channel popularity". Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- Song et al. correlations with clip popularity (Spearman): utterance frequency rho 0.2394, emote frequency 0.2101, sentiment strength 0.2537; average utterance length negatively correlated (shorter messages in popular moments). Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- KuaiHL ablation on KLive (Kendall tau-like ranking metric): full 0.5961; without visual 0.5489 (-4.72%); without text (ASR + comments) 0.5760 (-2.01%); previous SOTA AntPivot 0.5818. On PHD dataset mAP 21.89% vs PR-Net 18.66%. Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002) [X]
- Emote semantics resources: Kobs et al. 2020 "Emote-Controlled" (ACM TSC) built emote-based lexicon and weakly supervised sentiment for Twitch; their labeled set is 1,880 messages (40.6/38.0/21.4% pos/neutral/neg). Source: [ResearchGate](https://www.researchgate.net/publication/341125624_Emote-Controlled_Obtaining_Implicit_Viewer_Feedback_Through_Emote-Based_Sentiment_Analysis_on_Comments_of_Popular_Twitch.tv_Channels) [S]; Dolin et al. 2021 "FeelsGoodMan: Inferring Semantics of Twitch Neologisms". Source: [arXiv 2108.08411](https://arxiv.org/pdf/2108.08411) [S]

### Inferences
- [I] For Spike, `chat_rate` alone is a strong baseline on personality streams (Song: AUC 0.875 from frequency alone). Content adds a few AUC points, not a step change. The bigger lever is timing (see lag section) and windowing, not a heavier model.
- [I] Spike's `chat_hype` (emote share) roughly matches Song's "emote frequency" and "emotes per utterance" features, which were positively correlated with popularity. Short average message length is a cheap extra feature Spike does not have.
- [I] Normalizing per channel (Song) matches Spike's per-VOD z-scoring.

### Gaps
- No ablation found that isolates unique-user count versus raw message count.
- No paper compared a modern LLM reading raw chat against rate baselines on a labeled highlight set (the GamiFIN 2026 paper evaluated summaries, not detection).

## Chat combined with audio and video

### Takeaway
Fusion consistently helps, and how much depends on domain. In LoL esports with video, chat added only +0.8 to +2.5 F1 (Fu). In Ringer's thesis the chat transformer (F1 0.534 after offset/smoothing) beat both audio (0.432) and visual (0.506) models alone, and audio+visual+chat reached 0.642. In Song's personality-stream data, video-only and chat-frequency-only were nearly equal, and fusion added ~1 AUC point.

### Cited Findings
- Fu 2017: lv-LSTM chat+video F1 74.7 vs video 72.2 (NALCS, +2.5) and 70.0 vs 69.2 (LMS, +0.8). Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf) [V]
- Ringer Table 6.1 (Worlds 2020 knockout, late "model fusion"), F1: Audio 0.432; Visual 0.506; Auto-Highlight A+V 0.540; TASTE (chat) 0.534; Visual+Text 0.624; Audio+Text 0.593; **Audio+Visual+Text 0.642** (precision 0.713, recall 0.584). Source: [Ringer thesis §6.2.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Per-video robustness: A+V+T per-game F1 min 0.410, max 0.779; TASTE alone min 0.074, max 0.719. Multimodal models "reduce prediction noise". Source: [Ringer thesis Table 6.2](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- The weakest output correlation was between audio and chat models; Ringer suggests their noisy false positives are uncorrelated, which is why fusion works. Source: [Ringer thesis §6.2.5](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Chat supplies context video lacks: the audience "is less likely to react strongly to a replay than to a live game event, even if visually, these segments are identical"; fusion suppressed a visually highlight-like replay at ~3100 s. Source: [Ringer thesis §6.2.5](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Ringer: TASTE alone performed "similar" to the audio-visual Auto-Highlight model, "an exciting result" since it only sees "time-delayed audience reactions". Source: [Ringer thesis §5.3.5](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Song 2021: deep video-only AUC 0.8901 vs deep chat-frequency 0.8748 vs MINT ~0.898. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- KuaiHL: removing visual hurt more (-4.72%) than removing text/comments (-2.01%). Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002) [X]
- GamiFIN 2026: using chat as the sole LLM input "resulted in a significant drop in performance across all models"; older Gemini models leaned on chat, Gemini 2.5 understood clips from audio-visual input alone; best average score 4.80 (gemini-2.5-pro-exp). Source: [ACM DL](https://dl.acm.org/doi/10.1145/3789624.3789641) [X]

### Inferences
- [I] Simple late fusion (averaging per-modality scores, which Spike already does) captured most of Ringer's gain; a learned fusion is not required to get the benefit.
- [I] Because audio and chat errors are weakly correlated, Spike's fusion of chat signals with YAMNet laughter/loudness is well supported; requiring agreement between two families should cut false positives.

### Gaps
- No chat+audio study exists on personality-driven (non-esports) Twitch streams with labeled funny moments.

## Chat delay and lag compensation

### Takeaway
Chat lags the event. The best measured fixed correction is to shift chat-based predictions about 15 to 17 s earlier (Ringer, LoL Worlds). Fu found a forward-looking 7 s chat window best. Danmaku work handles lag by snapping each comment back to the first comment of its topical "lexical chain". No paper reports a full distribution of per-event lag in seconds.

### Cited Findings
- Ringer swept prediction offsets from -30 s to +30 s: negative offsets help a lot, **best -15 s gives F1 0.529 vs 0.416 unshifted** (+27%); positive offsets hurt, "chat messages rarely indicate that an exciting moment is about to happen". Source: [Ringer thesis §5.3.4.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Best combined setting: offset -17 s plus minimum-segment-length 23 s, F1 0.539; offset -15 s plus Gaussian smoothing kernel 22, F1 0.534. Smoothing without offset: best kernel 77, F1 0.432. Ringer notes lag is unidirectional, so a symmetric smoothing kernel is a poor fit. Source: [Ringer thesis Table 5.11, §5.3.4.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Fu 2017: for each frame, the model uses chats from "the next Wt seconds". Window sweep 5 to 9 s gave 32.1, 29.6, 41.5, 28.2, 34.4% (best 7 s). The non-monotonic curve suggests noise. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf) [V]
- Ping & Chen 2017 (danmaku): build word-embedding "lexical chains" per concept (chain cut after 11 s of silence), then reset each comment's timestamp to the first comment in its highest-scoring chain, on the observation that "the first comment about one shot usually occurs within the shot". Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V]
- KuaiHL notes audience comment lag and ASR/visual misalignment (e.g., singing) and learns alignment rather than fixing an offset. Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002) [X]
- Broadcast latency alone (before typing) is commonly 2 to 5 s (ultra-low), 5 to 15 s (low latency), and 15 to 30+ s (normal) per streamer guides. Source: [Hollyland](https://www.hollyland.com/blog/tips/turn-on-low-latency-mode-on-twitch); [Streamlabs](https://streamlabs.com/content-hub/post/how-to-reduce-stream-delay) [S, non-academic]

### Inferences
- [I] Ringer's -15 s figure bundles broadcast latency, reaction time, typing time, and the 2020 esports broadcast setup, so it is an upper-range starting value. For personality streams on low-latency mode, Spike should sweep the offset per channel (e.g., -3 to -20 s) against community clips instead of hard-coding one.
- [I] Lag is one-sided, so Spike should shift chat series backward (or use a causal, left-anchored window) rather than only smoothing symmetrically.
- [I] Twitch community clip start times come from viewers pressing "Clip" while watching, so they also lag the event; clip-heat needs a similar backward shift.

### Gaps
- No academic per-event lag distribution (mean, spread) for Twitch chat was found.
- Danmaku lag differs in kind: VOD danmaku is anchored to playback time, so it lacks broadcast latency.

## Danmaku (time-sync comment) highlight and humor results

### Takeaway
Danmaku research shows that emotion concentration and lag calibration each beat raw comment spikes. Laughter tokens ("233", "lol", "funny") are an explicit "happy" emotion signal that marks a single-emotion-concentrated highlight. Results are on small test sets (11 videos).

### Cited Findings
- Ping & Chen 2017 (EMNLP Workshop on New Frontiers in Summarization): unsupervised framework of lag calibration plus emotion and concept concentration; test set 11 Bilibili videos (1,333 min, 75,653 comments); ground truth = shots in at least 2 of 3 to 4 user-uploaded "mixed-clip" highlight compilations; avg 24.3 highlight shots per video, mean 27.79 s. Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V]
- Table 4 F1 values reported in order: 0.1567, 0.1797, 0.2321, 0.2500, 0.2829, 0.3066, for methods listed as random, uniform, comment-spike selection, spike+emotion+topic, spike+lag-calibration, full model. Lag calibration alone "improves the performance of Spike-selection considerably"; the full model is best. Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V for numbers; column-to-method mapping is my reading of a garbled table, so treat as [I]]
- Spike-selection fails because "comments at the beginning and end of a video are usually high-volume greetings and goodbyes"; spike selection also clusters on consecutive shots. Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V]
- Emotion lexicon from 5 Ekman categories (happy, anger, sad, fear, surprise), seeded manually and expanded by embedding neighbors; slang like "23333" = "ha ha ha" and "6666" = "really awesome"; "this plot is so funny/hilarious/lmao/lol/2333" is given as a single-emotion highlight. Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V]
- Earlier danmaku highlight work: Xian et al. 2015 (emotion-distribution similarity) and Lv et al. 2016 (topic concentration of comment semantic vectors plus a tag classifier). Cited in [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V, citations only]
- Seeing humorous comments is a main reason viewers watch danmaku video. Source: [Springer, "Understanding Gratifications of Watching Danmaku Videos"](https://link.springer.com/chapter/10.1007/978-3-319-20907-4_14) [S]

### Inferences
- [I] The "greetings and goodbyes" failure maps directly to Twitch stream start/end chat floods and raid/sub-train spam. Spike should down-weight the first and last minutes and alert-driven spikes.
- [I] Emotion concentration (one emotion dominating a window) is a cheap content feature Spike can approximate with emote-category share (laugh emotes vs hype emotes).

### Gaps
- No danmaku paper found that classifies highlight type (funny vs exciting) with reported accuracy.
- Recent (2023 to 2026) danmaku highlight papers with numbers were not found in the searches run.

## Does chat distinguish funny from exciting? Highlight type classification

### Takeaway
Only one study speaks to it directly: Song et al. 2021 clustered Twitch emote embeddings into funny, exciting, surprising, nervous, sad, and general. **Funny emotes become more common as clip popularity rises, while exciting emotes become less common**, and human experts picked funny moments more than the model did. No paper reports an accuracy for classifying highlight type from chat.

### Cited Findings
- Emote embeddings (word2vec) clustered into "funny", "surprising", "nervous", "sad", "general", "exciting". Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- Over view-count groups: proportion of clips with funny emotes rises with popularity; exciting, nervous, and sad fall; surprising stays flat. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- Epic moments found span "victory, funny, awkward, embarrassing" contexts; user study examples included failing gameplay, funny moments, surprising turnarounds, and non-game moments such as freestyle rapping. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- User study: expert picks preferred on average (61%); machine picks won 23 of 60 pairs; **expert-selected clips contained funny emotes 73% of the time vs 53% for machine-selected**; machine picks better captured surprising emotes. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- Ringer's esports chat shows a "cheering effect", a few tokens spammed fast, which makes rate and content collapse into one signal for hype. Source: [Ringer thesis §5.3.4](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Ringer, Walker, Nicolaou 2019 (IEEE CoG) jointly recognized streamer emotion and game context on 7,200 annotated LoL stream clips (valence/arousal), proposed as highlight cues. Source: [ResearchGate](https://www.researchgate.net/publication/336101827_Multimodal_Joint_Emotion_and_Game_Context_Recognition_in_League_of_Legends_Livestreams) [S]
- GamiFIN 2026: chat reactions supplied "sentiment, and humor" context to LLM clip summaries. Source: [ACM DL](https://dl.acm.org/doi/10.1145/3789624.3789641) [X]
- Laugh emotes (LUL, OMEGALUL, LULW) signal laughter, often mocking (e.g., embarrassing death); PogChamp signals excitement/shock. Source: [Kotaku](https://kotaku.com/everything-you-always-wanted-to-know-about-the-omegalul-1839784840); [Wikipedia PogChamp](https://en.wikipedia.org/wiki/PogChamp) [S, non-academic]

### Inferences
- [I] Splitting Spike's single `chat_hype` into `chat_laugh` (LUL/OMEGALUL/KEKW/LULW/"lmao"/"LOL") and `chat_hype` (Pog/PogChamp/"LETS GO") is directly supported by Song's emote clusters, and the popularity trend favors the laugh channel for clip value.
- [I] Song's model undershot experts on funny moments (53% vs 73%), which suggests rate-heavy models drift toward surprising/hype moments. A laugh-specific chat channel plus YAMNet laughter targets that gap.
- [I] An emote-to-category map must be maintained per channel (subscriber and 7TV/BTTV/FFZ emotes vary); an embedding approach like Song's, or an LLM labeling the top emotes once per channel, would scale.

### Gaps
- No precision/recall for a funny-vs-hype classifier from chat exists in the literature found.
- Song's correlations by emote category were reported as trends; exact proportions were not extracted.

## Labels: community clips, editor highlights, YouTube uploads, viewer behavior

### Takeaway
Three label families appear. Editor-made highlight videos frame-matched to broadcasts (Fu, Ringer, Ping) capture editorial taste, including low-reaction context shots chat cannot see. Community clip view counts (Song) capture audience taste at scale but are heavily skewed (power law) and confounded by channel size. Platform retention signals (KuaiHL's LVTR) are the industrial option. None of the papers validated community clips against human judgment directly, though Song's user study found model picks from clip-trained models comparable to experts.

### Cited Findings
- Fu: community highlight videos from one YouTube channel, frame-matched. Source: [ACL D17-1102](https://aclanthology.org/D17-1102.pdf) [V]
- Ringer: training is positive-unlabelled (257 broadcasts, 676 unrelated highlight videos; 193 h and 178 h). Test labels frame-matched from the two largest highlight channels (275k and 356k subscribers), 20 games, 18 h 6 min, 0.32 s fidelity; frame matching "took several days". Source: [Ringer thesis §4.2.2](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Ringer error analysis: editors include context (champion select, a cautious fight with one death) that drew little chat reaction, so chat models miss it; conversely chat flagged an exciting post-game stats screen editors omitted. "Such moments are impossible to detect from chat data alone if they do not evoke an audience reaction". Source: [Ringer thesis §5.3.5.1](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]
- Ping & Chen: ground truth = shots in at least 2 of 3 to 4 user-made Bilibili compilations (sorted by plays, under 10 min). Source: [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210) [V]
- Song: clip view counts follow a power law, "only a few clips become popular"; popular = top 5% (>=34 views); chat features normalized by followers to avoid learning channel popularity; female streamers excluded over concern about biased audience reactions. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- Song: clip creation times are spread roughly uniformly over the stream ("approximates a linear function across video stages"), so position in stream says little about epic moments. Source: [EPJ Data Science](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-021-00295-6) [X]
- KuaiHL: Long View Through Rate as weak supervision, with a border-aware pairwise loss. Source: [arXiv 2407.12002](https://arxiv.org/html/2407.12002) [X]
- Highlight share: ~12.5% of LoL broadcast labeled highlight in Ringer's training data. Source: [Ringer thesis §5.3.1.3](https://etheses.whiterose.ac.uk/32406/1/PhD_Thesis__Revised_.pdf) [V]

### Inferences
- [I] For Spike's eval, community clip timestamps (with view counts as relevance grades, normalized per channel) are the best free label and match the only personality-stream study. Treat clip count/views as graded, noisy positives, not as a complete set: many good moments get no clip, and viewer clips lag the event.
- [I] Editor highlights reward context and narrative; clip views reward reaction. Spike's goal (shareable funny clips) aligns more with clip-based labels.

### Gaps
- No study measured agreement between community clips and human-rated funniness, or between clip views and editor selection.
- Twitch clip API exposes `vod_offset` and view counts; the accuracy of `vod_offset` relative to the event was not studied academically.
