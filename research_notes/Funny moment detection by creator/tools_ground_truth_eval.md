# Commercial AI clipping tools, ground truth, and evaluation design

Scope note: this file adds to `reports/Funny clip detection signals.md` (which already covers laughter detection, LLM humor-judge weakness, YouTube heatmap basics via Mr. HiSum and CHI 2025, cliptron Recall@10, pairwise re-ranking, Eklipse/StreamLadder/OpusClip in brief). Research date: 2026-10-21. Most sources are vendor blogs or SEO review pages; primary docs are marked as such. Reddit could not be fetched directly (blocked for both fetch tools), so Reddit evidence is limited to search snippets and quotes relayed by other sites.

## 1. What signals each commercial tool claims, per-genre adaptation, published accuracy

### Takeaway
Every tool either keys off speech (transcript-first: OpusClip, Vizard, Klap, Munch, Submagic, Descript, Gling) or off game events (Eklipse, Medal, Sizzle, formerly Powder). None publishes an independently validated accuracy number. The only per-genre adaptation found is Eklipse's 5-way game-genre router and OpusClip's optional "genre" selector, and neither targets humor.

### Cited Findings
- **OpusClip (virality score):** Help docs say the score runs 0 to 99 and reflects four factors, Hook, Flow, Value, Trend; for ClipAnything it also scores relevance to the user's prompt. No training method is described in the help docs. — [OpusClip help: virality score](https://help.opus.pro/docs/article/virality-score) (via search summary)
- **OpusClip API blog (May 13, 2026, vendor claim):** lists transcript signals (hook strength, narrative arc, information density, emotional valence, quotability), audio (pace shifts, pitch range, background reactions, pause patterns), visual (gesture intensity, facial expression, cut dynamics for edited sources). Trained on "hundreds of thousands of (clip, performance) pairs" in one place and "millions of data points" in another (self-contradictory). Calibrated to predict above-median performance on TikTok, Reels, Shorts. Claims a 70+ score predicts above-median performance "~75% of the time on talking-head content", with no method or sample size. Trained most heavily on podcast, talking-head, webinar; advises lowering the threshold 10 to 15 points for non-talking-head content. Claims per-account learning from approved/rejected clips. Admits a 60 clip can beat an 85 clip, and that models drift (revisit thresholds every 60 to 90 days). — [OpusClip blog](https://www.opus.pro/blog/viral-moment-detection-api)
- **OpusClip ClipAnything:** marketed as "multi-modal AI" with prompts; demo source types Vlog, Sports, TV Show, Documentary. — [OpusClip ClipAnything](https://www.opus.pro/clipanything). Workflow has an optional "Select your video genre" step; the help page does not list genres or say what genre changes. — [OpusClip help: how to use ClipAnything](https://help.opus.pro/docs/article/how-to-use-clipanything)
- **Vizard Model v2 (July 2026, vendor claim):** targets "incomplete clips" (starts mid-sentence, punchline without setup). Narrows each hour to about 13 high-confidence clips with surrounding context. Gives a multi-part viral score breakdown (hook, takeaway, story flow). Optimized for podcasts, interviews, webinars, educational content. No accuracy numbers. — [Vizard blog](https://vizard.ai/blog/meet-vizard-model-v2-full-context-clips-that-the-algorithm-actually-rewards)
- **Klap:** Klap's own blog says it analyzes transcripts to detect distinct topics and hooks and attaches a virality score. A review says it works well on interviews/educational content with clear topic shifts and struggles with abstract or heavily visual content; claims it learns from user selections gradually. Language count 50+ to 52 (sources disagree; likely captions). — [Klap blog](https://klap.app/blog/ai-clip-maker); [Unite.ai review](https://www.unite.ai/klap-ai-review/)
- **Eklipse new engine (applies to VODs from June 1, 2026, vendor claim):** scores game-state events (kill feed, objectives, eliminations, round transitions), audio separation (voice, in-game audio), action density, sequence continuation; "scene-aware" frame/UI reading sets boundaries. A genre router picks one of 5 configs (FPS, battle royale, MOBA, tactical shooter, strategy/non-action) from game metadata, per VOD. Unsupported games fall back to generic action detection with lower quality. Admitted failure modes: niche titles, narrative content with no anchor events, non-English voice misclassified, heavy background music. No accuracy figures; humor not addressed. — [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html)
- **Eklipse (marketing):** claims training on "1,000+ titles", in-game cues (kill feed, score spikes, objectives) and audio cues (caster reactions, crowd hype). — [Eklipse help](https://eklipse.gg/help/how-can-i-automatically-clip-the-most-exciting-highlights-from-fast-paced-esports-matches/)
- **Medal:** auto-clipping fires on game events. Roblox experiences and FiveM servers define their own events via a Medal module; any PC game developer can claim the game in the developer portal and send a web request to the local Medal app when an event fires. This is developer-defined telemetry, not learned detection. — [Medal auto clipping](https://medal.tv/auto-clipping)
- **Sizzle:** described as connecting to Twitch/YouTube and clipping on in-game events, filterable by type (headshots, wins). — [Eklipse blog review of tools (competitor source)](https://blog.eklipse.gg/tools/best-free-ai-highlight-tools-twitch.html)
- **Powder:** earlier described as audio + visual cue detection; one blog reports it is shutting down (unconfirmed by an official source). — [Eklipse blog (competitor)](https://blog.eklipse.gg/tools/top-alternatives-powder-gg-tsai.html)
- **StreamLadder:** described as primarily a converter: you give it an existing Twitch clip and it reformats to vertical; it does not itself find highlights (contrasts with the earlier report citing its chat-spike blog). — [Eklipse blog (competitor)](https://blog.eklipse.gg/tools/the-7-best-ai-tools-for-game-highlights-in-2023-tsai.html)
- **Spikes Studio:** reviewers describe transcript-led long-to-short clipping with Twitch integration and multi-language support, with "occasional inaccuracies in AI clipping". — [sendshort review](https://sendshort.ai/guides/spikes-review/); [nemovideo review](https://www.nemovideo.com/blog/ai-video-workflows/spikes-studio-review-short-form-clips)
- **Gling:** transcribes and flags silences, filler words, and bad takes for removal in a text editor; it is a rough-cut tool for YouTubers, not a highlight finder. Directory sources only. — [FutureTools](https://www.futuretools.io/tools/gling)
- **Descript:** shipped "Remove retakes" after user requests for Gling-style bad-take removal. — [Descript feedback board](https://feedback.descript.com/features/p/automatically-edit-out-bad-takes)
- **Submagic:** described by a third-party ranking as caption-styling first, with hook detection "good, not great"; clippers often find moments in OpusClip then caption in Submagic. — [FORKOFF](https://forkoff.xyz/blog/clipping/best-ai-video-editor-2026)
- **Reap benchmark (vendor report, 2026):** all major clippers (OpusClip, Vizard, Submagic, Klap, Veed, Munch, CapCut) treat a clip as one contiguous slice; processing times observed ranged ~7 to 25 min for a 90-min podcast. A vendor-run comparison, not an accuracy benchmark. — [Reap report](https://reap.video/reports/state-of-top-ai-video-clipping-tools-2026)
- **Academic Twitch clip work:** Lindroos et al. (GamiFIN 2026, ACM) use Gemini to summarize/understand 56 Twitch clips (audio-visual moments plus chat reactions); human-rated summaries; Gemini 2.5 best. This is clip understanding, not detection, and has no accuracy against ground-truth highlights. — [JYX record](https://jyx.jyu.fi/handle/123456789/109439); [ACM DOI](https://dl.acm.org/doi/10.1145/3789624.3789641)

### Inferences
- Two families exist: speech/transcript tools tuned on podcast/talking-head performance data, and game-event tools tuned on kills/wins. Funny moments in streams (reaction, banter, visual gags) fall in the gap between them. No tool targets humor explicitly.
- "Per-genre" adaptation in industry is a routing step over genre configs (Eklipse) or an optional user hint (OpusClip). Neither is per-creator. OpusClip's per-account approve/reject learning and Klap's "learns from your selections" are the only per-creator adaptation claimed, both unverified.
- OpusClip's "above-median performance" target is the closest thing to a published evaluation definition in industry: a binary label from real platform outcomes, scored as hit rate per score bucket.

### Gaps
- No published accuracy numbers from Choppity, Munch, Submagic, Sizzle, Spikes Studio; searches returned nothing primary for Choppity and Sizzle internals.
- OpusClip's list of ClipAnything genres and their effect is not documented publicly.
- No engineering talks or blogs found from any of these companies describing offline eval sets or human-label agreement.

## 2. Failure modes from user reviews

### Takeaway
The most-cited complaint is boundary and context failure (punchline without setup, or setup without punchline, mid-word cuts), followed by low yield (30 clips generated, about 2 used) and a virality score that does not predict views. Gaming, vlog, and music content get arbitrary picks because transcript-first models have no speech to anchor on. Non-English complaints were mostly not found in reviews; Eklipse admits it.

### Cited Findings
- r/podcasting user (quoted by eesel and in search snippet): it "always cuts out the funny or important parts"; score descriptions say a clip "lacks..." — [Reddit r/podcasting thread](https://www.reddit.com/r/podcasting/comments/14zzbpk/how_do_yall_feel_about_opus_clips/) (snippet only); [eesel.ai roundup, edited Sep 27, 2026](https://www.eesel.ai/blog/opusclip-reviews)
- eesel's roundup names missing punchline/context as the most-cited issue, and cites sendshort saying the AI misses nuance, comedic timing, sarcasm; cites submagic for creators finding low-score clips outperform high-score ones. No counts. — [eesel.ai](https://www.eesel.ai/blog/opusclip-reviews)
- Low yield: "I pay $58/month for Opus Clip, get 30 clips, and post only 2" — [Reddit r/podcasting](https://www.reddit.com/r/podcasting/comments/1ud8hlw/anyone_else_spending_more_time_reviewing_ai_clips/) (title/snippet). r/opusclip post: "Tired of getting 30 clips from Opus Clip and only using 2", with comment calling clips "a sloppy mess with choppy mid-word jump cuts and pointless hooks" — [Reddit r/opusclip](https://www.reddit.com/r/opusclip/comments/1uavudm/tired_of_getting_30_clips_from_opus_clip_and_only/) (snippet)
- Transcript-only depth: "the clips it finds are pretty surface level because it's working off the transcript. It doesn't actually watch..." — [Reddit r/editing](https://www.reddit.com/r/editing/comments/1s2b7i7/what_do_you_guys_actually_think_about_tools_like/) (snippet)
- Content-type failure: review says skip OpusClip if footage is "b-roll heavy, gaming, vlog, or music content with little continuous speech" because "clip selection turns arbitrary" — [Techpresso review 2026](https://academy.techpresso.co/reviews/is-opus-clip-worth-it)
- Gaming: a fan blog (Sep 2025) says OpusClip is not great at gaming clips but decent at finding them "depending on the game"; also reports "project failed" errors costing a credit on rerun. — [PolyInnovator](https://www.polyinnovator.space/opusclip-is-not-great-at-gaming-clips-here-is-why-i-use-it-anyways/)
- Virality score validity: one reviewer (May 2026, updated Oct 2026) tested one 15-minute talk (21 clips, scores 98 to 80s), tracked no views, calls predictive validity unproven, and twice found an 80s clip fit better than a 90s clip. — [marcandrews.com](https://marcandrews.com/?p=6263). Another reviewer is reported (in a search summary) to have tracked 50 clips over 3 months with >75 scores averaging ~2.3x the views of <50 scores; I could not open that source to verify. — [search result citing marcandrews / other review](https://marcandrews.com/opus-clip-review-2026-ai-video-shorts-tool-tested/)
- Vizard's own v2 launch frames the industry-wide failure as "starts mid-sentence, punchline lands but the setup is missing". — [Vizard blog](https://vizard.ai/blog/meet-vizard-model-v2-full-context-clips-that-the-algorithm-actually-rewards)
- Eklipse admits non-English voice misclassification and background-music interference. — [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html)
- Captions degrade with heavy accents, jargon, fast speech (Spikes Studio, directory source). — [devtoollab](https://devtoollab.com/ai-tools/spikes-studio)

### Inferences
- Ranked by how often they appear across sources: (1) boundary/context cuts, (2) low usable yield, (3) non-predictive virality score, (4) bad on gaming/visual/low-speech content, (5) non-English. This ranking is qualitative; no source counts complaints.
- "Missed visual gags" shows up only indirectly (transcript-only, "doesn't actually watch").
- Low yield (about 2 of 30 used) suggests a useful product metric: accept rate per generated clip, which a review screen can log directly.

### Gaps
- No quantitative complaint tallies from Trustpilot/G2 were retrieved (pages not fetched in budget).
- Direct Reddit thread bodies could not be read; only titles/snippets.

## 3. Ground-truth sources: strengths, biases, coverage

### Takeaway
Twitch community clips are the best free stream ground truth (exact VOD offset, view count, duration) but are biased toward live-audience-size moments and end-of-moment capture. The YouTube Most Replayed heatmap is coarse (100 bins) with a strong start-of-video bias that must be corrected. Fan-clip-channel uploads and r/LivestreamFail need manual or fingerprint matching back to VODs and are heavily popularity-biased.

### Cited Findings
- **Twitch Get Clips (primary docs):** returns `vod_offset` (zero-based seconds from VOD start to clip start; null if no VOD, and null for an indeterminate delay, "typically minutes", after creation), `view_count`, `duration`, `created_at`, `creator_id`, `game_id`, `language`, `is_featured`. Query by broadcaster or game. — [Twitch API reference](https://dev.twitch.tv/docs/api/reference); [Twitch clips guide](https://dev.twitch.tv/docs/api/clips/)
- **Create Clip From VOD (primary docs):** `vod_offset` there marks where the clip ends; clip spans `vod_offset - duration` to `vod_offset`. — [Twitch API reference](https://dev.twitch.tv/docs/api/reference)
- **Clip capture window:** vendor source says a live clip grabs roughly 85 s before the click and about 5 s after, so clippers click after the payoff. — [Frostytools](https://frostytools.com/blog/how-to-turn-twitch-vods-into-clips-without-editing/) (vendor, unverified)
- **Twitch clip selection bias:** "viewers clip what they're watching, not your best moments overall", so low-viewer periods are under-clipped. — [Eklipse blog](https://blog.eklipse.gg/beginner-guide-2/how-to-get-more-clips-on-twitch.html) (vendor)
- **Stream markers:** `/marker` in chat drops a VOD timestamp with up to 140 chars of description; editors and mods can be allowed to place them. A creator-side label source. — [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-livestream-editors-edit-so-fast.html)
- **YouTube Most Replayed as labels (Rhapsody, 2025):** 13,364 English podcast episodes, 90 channels, avg ~27 min. Labels: up to K=20 of 100 bins with score above 0.5. Start bias: before correction 75% of episodes had a highlight in bin 1 (mean first-bin score 0.711 vs 0.054 to 0.208 elsewhere); they replace bin 1 with bin 2. Only videos with enough views have graphs; K and threshold were picked by manual inspection; labels called subjective. — [Rhapsody, arXiv 2505.19429](https://arxiv.org/html/2505.19429)
- **Rhapsody results (test, 2,467 episodes):** hit rate / F1 / AP: random 0.220 / 0.039 / 0.021; GPT-4o text 0.265 / 0.057 / 0.032; Gemini text 0.327 / 0.065 / 0.037; Gemini text+audio 0.293 / 0.063 / 0.040; fine-tuned Llama text+HuBERT 0.490 / 0.197 / 0.153. Zero-shot LLMs barely beat random against crowd replay labels; fine-tuning on the labels helps a lot. — [arXiv 2505.19429](https://arxiv.org/html/2505.19429)
- **OpusClip's industry ground truth** is real platform performance (above-median views on Shorts/Reels/TikTok), not human highlight labels. — [OpusClip blog](https://www.opus.pro/blog/viral-moment-detection-api)

### Inferences
- **Twitch clips:** strengths are exact offsets, a natural popularity weight, and coverage of streams with chat. Biases: (a) live-audience bias (more viewers, more clips), (b) the clip start is usually set well before the peak because of the backward capture window, so the peak sits near the clip end; matching should use the clip's last third or end, not its start; (c) duplicates (many viewers clip the same moment) are a useful agreement signal; (d) `view_count` is shaped by sharing and by Twitch's own featuring, so treat it as a graded relevance label after per-VOD normalization. Early-stream bias was asked about but no source measured it for Twitch clips.
- **Heatmap:** 100 bins means about 108 s per bin on a 3 h VOD (prior report), too coarse for boundary eval; use it for hit-rate style "did we land in a hot bin" checks only, with the first bin dropped or replaced as Rhapsody did.
- **Fan clip channels / r/LivestreamFail:** high-precision, low-recall labels for the very top moments of popular creators; need audio fingerprinting or transcript alignment to map back to VOD time (inference; no source found describing this pipeline). Strong popularity and drama bias (LSF selects for news/drama, not just humor).
- **Coverage across creator categories:** Twitch clips cover gaming and Just Chatting streams; heatmap covers uploaded YouTube videos with enough views; neither covers small creators well. The review screen's accept/reject log is the only label source that covers every creator Spike processes.

### Gaps
- No source quantified Twitch clip bias (early-stream, viewer-count elasticity) or measured how often a clip's `vod_offset` window contains the actual peak.
- Twitch Get Clips pagination ceiling and default sort were not verified in this session (recalled: results sorted by views, capped pages; check docs).
- No source found on matching fan-channel uploads to VOD timestamps at scale.
- Default/min/max Twitch clip duration not verified this session.

## 4. Evaluation design

### Takeaway
Use retrieval metrics against several weak label sources at once (Twitch clips, heatmap bins, review accepts), report them per creator category, and add pairwise human preference for the top picks. Industry evaluates with real outcomes (above-median views); academia with hit rate, P/R/F1, AP on segment labels. Exact-segment matching is the norm in Rhapsody; for streams a time tolerance is needed.

### Cited Findings
- Rhapsody treats highlight prediction as retrieval over 100 segments and reports hit rate, precision, recall, F1, AP, matching exact segment indices (no tolerance described). — [arXiv 2505.19429](https://arxiv.org/html/2505.19429)
- OpusClip's stated target: P(above-median platform performance | score bucket), with a claimed 75% hit rate at 70+ for talking-head content; also suggests per-content-type thresholds and per-account calibration from approvals. — [OpusClip blog](https://www.opus.pro/blog/viral-moment-detection-api)
- A proper score-validity test needs publishing across an audience and tracking over weeks; a single afternoon test proves nothing. — [marcandrews.com](https://marcandrews.com/?p=6263)
- Prior report already covers HIT@1, P@k, NDCG@k, cliptron Recall@10 on community clips, pairwise prompting, and inter-rater alpha about 0.43 for humor. — [Funny clip detection signals.md (local)](C:/Users/Nicholas Ho/Documents/Programming/Project/Spike/reports/Funny clip detection signals.md)

### Inferences
- **Matching rule (proposal):** a pick matches a Twitch clip if the pick window overlaps the clip's final ~15 s, or if temporal IoU >= 0.3 (inference, chosen because the capture window puts the payoff near the clip end). Report results at 2 tolerances (strict and loose) so tolerance choice is visible.
- **Metrics per VOD:** HIT@1, Recall@K (K = number of clips Spike outputs), Precision@K against the union of label sources, NDCG@K with grade = per-VOD percentile of clip view_count. Macro-average by creator category (gaming FPS, gaming other, Just Chatting/IRL, podcast/talk, vlog) so one big category does not dominate.
- **Across creator types:** normalize labels per VOD (percentiles, not raw views), and compare against a per-category baseline (random and chat-rate/loudness). Report lift over baseline rather than raw scores, because label density differs by category (Rhapsody random hit rate is 0.22 at about 5 labels per 100 bins).
- **Human pairwise eval:** for each VOD, show raters Spike's top pick vs a baseline's top pick (blind, both orders), and compute win rate; this sidesteps low absolute-rating agreement.
- **Online eval:** for published clips, the OpusClip-style metric works: share of clips beating the channel's median views within N days, and average percent viewed. Per-channel normalization is needed because views vary by audience size.
- **Product metric:** accept rate on the review screen (reviews show about 2 of 30 for OpusClip) is cheap and covers every creator.

### Gaps
- No public offline eval protocol from any commercial clipper was found.
- No published A/B tests comparing clip selection methods by retention.

## 5. How fan clippers choose clips, and what length/retention data says

### Takeaway
Clipper practice favors self-contained moments that include the setup and are marked at or after the payoff. Length data is vendor-sourced and conflicting: some favor 30 to 60 s, others 11 to 30 s; none is a controlled study.

### Cited Findings
- Clips must stand alone; a failure pattern is starting at the exciting part and skipping the setup; start before the decision, mistake, or pressure point. — [nemovideo workflow guide](https://www.nemovideo.com/blog/ai-video-workflows/twitch-clip-maker-stream-highlights) (vendor)
- Selection is the stage that scales with stream length; editors flag after the payoff lands. — [Frostytools](https://frostytools.com/blog/how-to-turn-twitch-vods-into-clips-without-editing/) (vendor)
- Length claims: Inflow Network study of 5,400 Shorts reportedly found 50 to 60 s videos got ~22x the views of sub-10 s; Vidooly (2M+ Shorts) reportedly found 40 to 60 s highest average views; quso recommends 11 to 30 s, saying retention erodes past 30 s; Social Insider reportedly found <90 s videos average 50% retention vs ~35% for longer. Bytecap notes its length distribution (from OpusClip's April 2026 report) shows what users made, not a randomized comparison. YouTube publishes no universal retention threshold. — [Bytecap](https://www.bytecap.io/research/youtube-shorts-retention-benchmarks); [quso](https://quso.ai/research/youtube-shorts-length); [OpusClip blog](https://opus.pro/blog/ideal-youtube-shorts-length-format-retention); [Shortimize](https://www.shortimize.com/blog/youtube-shorts-retention-rate)
- Vizard v2 deliberately outputs fewer, longer, context-complete clips (about 13 per hour). — [Vizard blog](https://vizard.ai/blog/meet-vizard-model-v2-full-context-clips-that-the-algorithm-actually-rewards)

### Inferences
- The length studies are observational and confounded (creators who make 50 to 60 s Shorts differ from those who make 10 s ones). For Spike, length should be decided by the moment's setup-to-payoff span, then checked against the channel's own retention once clips are posted.
- The industry trend in 2026 (Vizard v2) is fewer, context-complete clips over high-volume detection, which matches the main user complaint.

### Gaps
- No interviews with large clip channels (or LivestreamFail moderators) on selection criteria were found.
- No platform-published or peer-reviewed retention-by-length data for comedy/stream clips specifically.
