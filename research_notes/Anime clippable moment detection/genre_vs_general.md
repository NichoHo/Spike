# Anime clippable-moment detection: one general scorer vs genre/category-specific scoring

Scope: should Spike score anime moments with one general model, or weight signals by the show's genre? Which clip archetypes exist, what detects them, and how to get genre metadata. Research date: 2026-10-27. "Verified" = read in a source this session. "Inferred" = my reasoning from cited data.

## Q1. In highlight-detection research, do domain/genre-specific models beat general ones?

### Takeaway
Yes, when each model is trained on labelled data for that category: models trained on one category transfer poorly to another. But the research trend is toward one shared model that is conditioned on category, query, or user, and those conditioned models close most of the gap. For Spike (no per-genre training data), this argues for one scorer with genre as a conditioning input (weights/prompt), not separate per-genre models.

### Cited Findings
- Verified: highlight detectors "are typically domain-specific", tailored to a category such as skiing (Xiong et al., CVPR 2019). [Less Is More, CVPR 2019](https://openaccess.thecvf.com/content_CVPR_2019/papers/Xiong_Less_Is_More_Learning_Highlight_Detection_From_Video_Duration_CVPR_2019_paper.pdf)
- Verified: Sun, Farhadi, Seitz ranked "domain-specific highlights" by learning from online edited videos per domain; latent ranking beat latent classification by about 7% mAP on average across domains. [Ranking Domain-Specific Highlights (Semantic Scholar)](https://www.semanticscholar.org/paper/Ranking-Domain-Specific-Highlights-by-Analyzing-Sun-Farhadi/5c7adde982efb24c3786fa2d1f65f40a64e2afbf); [PDF](https://scispace.com/pdf/ranking-domain-specific-highlights-by-analyzing-edited-tebdxpvu1b.pdf)
- Verified (numbers): Cross-category transfer hurts. In ICCV 2021 "Cross-category Video Highlight Detection via Set-based Learning", a model trained on surfing and tested on dog scored 0.485 mAP vs 0.708 for a model trained on dog (target-oracle). Their domain-adapted model (DL-VHD) recovered most of it (0.649). On parkour: source-only 0.547, DL-VHD 0.748, oracle 0.772. On ActivityNet, source sport to target household: 0.707 source-only, 0.793 DL-VHD, 0.787 oracle. The paper says highlights of one category "may be nuisance" for another. [arXiv 2108.11770](https://arxiv.org/html/2108.11770v1)
- Verified: AAAI 2023 "Cross-Category Highlight Detection via Feature Decomposition and Modality Alignment" (Zhang) argues one model "can be employed to detect highlights for all video classes instead of training one expert model for each category", while conceding it "does not gain the best performance in some specific categories". Reported averages: YouTube Highlights 0.749 mAP, TVSum top-5 mAP 0.815 (visual+audio), with audio adding about 1 point over visual only. [AAAI 2023 PDF](https://ojs.aaai.org/index.php/AAAI/article/view/25462/25234)
- Verified: TVSum results are reported per category (10 categories such as vehicle tire, parade, dog show, beekeeping); per-category scores in the AAAI paper ranged from 0.730 (FM) to 0.911 (BT), so difficulty differs a lot by category even for one model. [AAAI 2023 PDF](https://ojs.aaai.org/index.php/AAAI/article/view/25462/25234)
- Verified: QVHighlights (NeurIPS 2021) reframes highlight detection as query-dependent: one model, with the "what counts as a highlight" supplied as a natural-language query. Pretraining on in-domain data (5.4K QVHighlights videos) beat pretraining on 10K out-of-domain HowTo100M videos for highlight mAP (37.70 vs 35.97), so domain match still matters at pretraining time. [QVHighlights paper](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf)
- Verified: PHD-GIFs (ACM MM 2018): conditioning a shared model on a user's history "substantially improves" accuracy over generic highlight detection, even with one user-specific example, and it "outperforms the baseline of training one model per user". [arXiv 1804.06604](https://arxiv.org/html/1804.06604v2)

### Inferences
- Pattern across the literature: (a) a single unconditioned general model is worst, (b) separate per-category models need per-category labels, (c) a shared model plus a conditioning signal (category, query, user history) matches or beats per-category models without needing separate training sets. PHD-GIFs is the cleanest evidence for (c) beating (b).
- Spike's LLM judge is already a query-conditioned scorer. The equivalent of the research's "conditioning" is putting the genre prior and archetype definitions into the judge prompt and the signal weights, not building separate pipelines.
- None of these benchmarks contain anime. Transfer of the numbers to anime is inferred, not verified.

### Gaps
- Found no paper evaluating highlight detection on anime specifically, or on scripted TV comedy vs action. No anime highlight benchmark found.
- Did not check 2025-2026 video-LLM highlight papers in detail (one search returned only QVHighlights-era work).

## Q2. What anime clip content performs on Shorts/TikTok, per genre, and how does abridged/dub comedy differ?

### Takeaway
Hard per-genre view statistics do not exist publicly. Channel data pulled this session shows that dialogue-driven comedy clips (abridged dub) massively outperform official licensor clips, and that even official clips of action and drama shows are titled and framed as comedy, reaction, or relationship beats. The clip's archetype (a self-contained punchline) predicts performance better than the show's genre tag.

### Cited Findings
- Verified (channel data, 48 most recent Shorts, observed 2026-10-27): TeamFourStar (4.47M subscribers) Shorts are abridged parody dialogue beats. Yu Yu Hakusho Abridged Shorts ranged 66K to 1M views, most 110K to 310K. Sailor Moon Abridged Shorts ranged 347K to 1.1M. Their non-anime Bob Ross parody Shorts got 25K to 51K. Titles are punchline or meme phrases ("Skill Issue", "Because We're Blondes!", "My JAGAN Eye"), not scene descriptions. Source: YouTube channel Shorts listing via Firecrawl `youtube-com/videos/channel_shorts` for [@TeamFourStar](https://www.youtube.com/user/TeamFourStar)
- Verified (same method): Crunchyroll's 48 most recent Shorts got 5.4K to 35K views each. Shows include action/dark fantasy (Daemons of the Shadow Realm, BLACK TORCH, Re:ZERO S4), romance/shoujo (The Ogre's Bride, Please Excuse My Younger Brothers), villainess isekai, and comedy isekai. Titles of action-show clips still frame a comedy or reaction beat: "Did He Just Slice His Own Neck?", "Getting Roasted by Your Own Daemon Sidekick", "Asuma Has The FAKEST Smile", "Subaru Needed That SLAP". Romance clips frame a relationship beat: "Is Gen Getting Jealous?", "She May Be More In Love Than She Realizes". Top performers in that sample were ecchi/comedy beats from The Exiled Heavy Knight (29K to 35K). Source: [@crunchyroll Shorts](https://www.youtube.com/@crunchyroll/shorts) via the same Firecrawl capability.
- Verified: Muse Asia (9.01M subscribers) returned no Shorts tab in the listing (tab absent or not exposed). Source: same Firecrawl capability, channel @MuseAsia.
- Verified: Crunchyroll's TikTok posts "bite-sized clips of popular anime scenes, cosplay showcases, and fan challenges". [New Day Studio](https://www.newdaystudio.co/blog/tiktok-brands-that-went-viral)
- Verified (creator guidance, not anime-specific): hook should land in the first 1 to 3 seconds; TikTok 1 to 2 s, Shorts 2 to 3 s; on-screen text before speech helps muted viewing; Shorts should make a promise the 30 to 60 s runtime can fulfil. Cites a WARC finding that people decide within 1.7 s. [Captions.ai](https://captions.ai/blog/video-hooks-how-to-write-a-scroll-stopping-opening)
- Verified (opinion): r/anime users criticize chopped-up clip compilations but accept clips that showcase the main point, such as a character's best fight moments. [Reddit r/anime](https://www.reddit.com/r/anime/comments/12r5ryo/does_anyone_actually_enjoy_those_choppedup_clips/)
- Not verified this session: the reference Short "A Win is a Win | Buu Bits" (4.6M views, 32 s). It was not in the 48 most recent TFS Shorts. Its stats come from the caller's brief.

### Inferences
- The TFS vs Crunchyroll gap (roughly 10x to 50x per Short) is confounded by audience, brand, and English dialogue, so it is not a clean genre effect. It does show that the winning unit is a short, self-contained spoken exchange with a punchline, which is exactly what a transcript-based judge can find.
- The TFS reference case breaks "genre tag predicts clip type": DBZ is tagged Action/Adventure on AniList/MAL, yet its best clips are comedy dialogue because of the dub. Same for official dubs with joke-heavy localization. So the audio track (dub vs sub, abridged vs canon) must override the show prior.
- Official channels retitle action scenes as reaction/comedy hooks. This suggests that across genres, the "hook" is usually an emotional or comedic reaction, while pure spectacle (sakuga) is the archetype most tied to action genres.
- Subbed clips depend on burned-in or on-screen English text for the hook; dubbed or abridged clips can hook on the first spoken line. Inferred from the hook guidance plus the title patterns, not measured.

### Gaps
- No reliable public analytics break down anime Short views by genre (shonen, romance, slice of life, horror, isekai, sports). Searches returned only how-to videos and AI-automation tutorials.
- Could not sort channels by most-viewed Shorts (the listing is newest first), so all-time top clips per channel were not sampled.
- No data found comparing dub vs sub clip performance directly.
- Typical length per genre: not found. Only the generic 30 to 60 s Shorts guidance.

## Q3. Per-scene archetype detection vs per-show genre tags: is a hybrid better? How to get genre?

### Takeaway
Use a hybrid: the show's tags give a prior over archetypes and signal weights, and per-scene detection decides. Tags are show-level and multi-valued, so they cannot say which scene is a fight and which is a joke. AniList tags carry a 0 to 100 relevance rank, which maps directly onto prior weights.

### Cited Findings
- Verified: AniList `MediaTag` has `name`, `category`, `rank` ("relevance ranking of the tag out of the 100 for this media"), `isGeneralSpoiler`, `isMediaSpoiler`, `isAdult`. [AniList MediaTag reference](https://docs.anilist.co/reference/object/mediatag)
- Verified: AniList media queries filter by `genres`, `tags`, `minimumTagRank`; API is GraphQL at `https://graphql.anilist.co`, no key needed for reads. [AniList Media queries](https://docs.anilist.co/guide/graphql/queries/media); [FreeAPIHub example](https://freeapihub.com/apis/anilist)
- Verified: Jikan (unofficial MAL REST v4) exposes `/anime/{id}/full` and `/genres/anime`; genres can be filtered as "genres", "explicit_genres", "themes", or "demographics". [Jikan docs](https://docs.api.jikan.moe/); [JikanPy docs](https://jikanpy.readthedocs.io/)
- Verified: the research analogue: PHD-GIFs combined a generic model with a per-user signal and beat both generic and per-user-only models. [arXiv 1804.06604](https://arxiv.org/html/1804.06604v2)
- Verified: TFS's abridged series run on action sources (DBZ, Yu Yu Hakusho) but their Shorts are comedy. [TFS wiki](https://teamfourstar.fandom.com/wiki/DragonBall_Z_Abridged); channel data above.

### Inferences
- Recommended structure (inferred design, not from a source):
  1. Show prior: fetch AniList `genres` + `tags{name rank category isMediaSpoiler}` (Jikan genres/themes/demographics as fallback). Convert to a prior over archetypes, weighted by `rank/100`. Example: Action + Shounen boosts fight/sakuga and transformation; Comedy/Parody boosts comedy beat; Romance boosts romance/wholesome; Drama/Tragedy boosts emotional; Mystery/Psychological boosts twist/reveal.
  2. Source override: user flag or detector for "abridged / parody / dub". If set, raise the comedy-beat prior regardless of genre (the TFS case). Detect via channel/file metadata, English audio language, or the AniList `Parody` tag.
  3. Per-scene classification: the LLM judge labels each candidate with one archetype plus a score. The prior adjusts the final score modestly (for example a multiplier in 0.8 to 1.2), so a great joke in an action show still wins.
  4. Spoilers: use `isMediaSpoiler` tags and the twist/reveal archetype to flag, not boost, late-series reveals.
- Archetype to signal map (inferred, standard signal choices):
  - Fight/sakuga: shot-cut rate, optical-flow motion magnitude, audio RMS and music swell, impact SFX, few words.
  - Transformation/power-up: sustained loudness ramp, shouting, glow/brightness change, music leitmotif, scream in transcript.
  - Comedy beat: dense dialogue, setup-punchline in transcript, short pause after punchline, laugh SFX in abridged; LLM is the main detector. Low motion is fine.
  - Iconic line: a quotable sentence (short, named-character, often repeated in fandom); LLM plus dialogue isolation.
  - Emotional/tearjerker: slow pacing, soft music, crying audio, low motion, long shots.
  - Plot twist/reveal: transcript reveal markers, sudden music stop or sting, close-ups. Spoiler risk.
  - Romance/wholesome: two-character dialogue, blush/close-up, soft music, confession words.
  - Cringe/reaction: exaggerated reaction faces, abrupt silence, awkward dialogue; mostly LLM.
- Weighting change per genre should be small for the transcript judge (it already reads content) and larger for the low-level audio-visual signals: motion and loudness are strong for action but mislead in comedy, where the best moments are quiet dialogue. This mirrors the research finding that one category's highlights can be another's "nuisance".

### Gaps
- No study found that compares show-level tags vs scene-level classification for multi-genre anime.
- AniList tag `rank` is community-voted; reliability per show was not measured.
- Did not verify AniList rate limits this session (recalled as about 90 req/min; check the docs before relying on it).

## Q4. How commercial auto-clippers handle genre

### Takeaway
They all moved toward genre conditioning on top of one engine: Opus Clip has a user-selected genre in its curation model, and Eklipse tunes detection per game category. None publish how much weights change.

### Cited Findings
- Verified: OpusClip 3.0 introduced a "Genre-Specific Curation Model": the user specifies the video genre (Q&A, vlog, listicle, webinar, etc.) and the curation "approach" is tailored. [OpusClip blog](https://www.opus.pro/blog/opusclip-clip-different)
- Verified: setup asks for content genre (podcast, vlog, sports, others) before processing. [BIGVU review 2026](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/)
- Verified: OpusClip Virality Score (0 to 99) is based on factors including Value (emotional resonance, connection) and Trend; ClipAnything mode also checks relevance to a user prompt. [OpusClip help](https://help.opus.pro/docs/article/virality-score)
- Verified (independent review): the virality score "ranks clips well and predicts nothing"; testers discard a fifth to two fifths of output; works best on continuous speech, poorly on b-roll, gaming, music. [Techpresso review](https://academy.techpresso.co/reviews/is-opus-clip-worth-it); BIGVU headline also cites a 40% discard rate. [BIGVU](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/)
- Verified: Eklipse combines gameplay events (kills, wins), audio spikes (excitement, laughter), and chat sentiment (emote spikes, message velocity) into a per-moment score, "with highlight detection tuned for each game category"; it supports 3,000+ games. [Eklipse](https://eklipse.gg/); "what counts as a highlight changes with what you play" [Eklipse features](https://eklipse.gg/features/)
- Verified (competitor claim, biased): WayinVideo says Eklipse relies on gameplay events, audio spikes, and scene changes, so "subtle highlights" are missed; WayinVideo claims game-specific AI plus video understanding and keyword search. [WayinVideo](https://wayin.ai/blog/eklipse-alternative/)
- Verified: Vizard's gaming tool claims detection of "high-intensity kills and clutch wins". [Vizard](https://vizard.ai/tools/ai-gaming-clip-maker)
- Klap: no genre documentation found.

### Inferences
- Industry pattern matches the research: one engine, a genre switch that changes curation. Eklipse's per-game tuning is the closest analogue to per-anime-genre weights. Spike's Twitch pipeline already blends transcript and chat signals the same way.
- Loudness/event-driven detection (Eklipse style) misses quiet comedy, which is exactly the TFS archetype. A transcript LLM judge is needed for comedy and iconic lines.

### Gaps
- None of the vendors document their per-genre weights or report accuracy per genre.
- No commercial clipper found that targets anime episodes specifically.

## Bottom-line recommendation for Spike (inferred)
- One scorer, conditioned by genre. Do not build separate per-genre pipelines.
- Score = per-scene archetype score from the LLM judge plus audio-visual signals, multiplied by a modest show prior (from AniList tags with `rank`), with a "dub/abridged/parody" override that boosts comedy.
- Shift weights per genre mainly on low-level signals: motion/loudness high for action and transformation, low for comedy, romance, emotional.
- Clip unit: a self-contained 20 to 60 s beat that opens on its hook within 1 to 3 s (for comedy, start on the setup line, end just after the punchline reaction).
- Validate on a small labelled set across 3 to 4 genres before tuning weights, since no public anime benchmark exists.
