# Crowd and external audience-reaction signals for anime clip detection

Scope: timestamped or episode-level audience signals that can stand in for Twitch chat when ranking clippable moments in anime episodes. Constraints: one small PC, $0 budget, official/public APIs or permitted data only, no browser automation, no anti-bot bypass. Research date: 2026-10-27. Labels: "Verified" means a source was fetched or a live call made this session. "Recalled" means training knowledge not checked this session.

## Time-synced comments: Bilibili danmaku and Niconico comments (access, coverage, density, research)

### Takeaway
Danmaku (time-synced overlay comments) is the closest analogue to Twitch chat: each comment carries a playback offset, and academic work since 2017 treats comment volume plus emotion as a highlight signal. Access is only through undocumented, reverse-engineered endpoints (Bilibili `seg.so` protobuf, Niconico `nvComment`), so it carries terms-of-service risk and breakage risk. Coverage is strong for Chinese and Japanese releases and weak for Western-only content such as TeamFourStar abridged shows.

### Cited Findings
- Bilibili danmaku is served from `https://api.bilibili.com/x/v2/dm/web/seg.so` with `oid`, `pid`, `type`, and `segment_index` parameters, and is decoded with a `dm.proto` file from the community repo SocialSisterYi/bilibili-API-collect. — [aardio protobuf example](https://www.aardio.com/zh-cn/doc/example/Network/protobuf/QuickStart.html.md)
- The response is raw protobuf binary, not JSON, and it is fetched in segments of about 6 minutes. One scraper stops when a segment comes back empty. — [Apify Bilibili danmaku extractor description](https://apify.com/xtracto/bilibili-danmaku.md) (third-party, secondary)
- WBI request signing (`w_rid`, `wts`) is required by many Bilibili endpoints. One guide says it applies only to `space/wbi/*` endpoints. Whether `seg.so` needs it was NOT verified. — [bilibili-cli docs](https://pkg.go.dev/github.com/tamnd/bilibili-cli@v0.2.0); [bilibili-source skill](https://tessl.io/registry/skills/github/daymade/claude-code-skills/bilibili-source)
- Open-source tools: `tamnd/bilibili-cli` (Go, Apache-2.0) has a `danmaku` command and a `pkg/dmproto` decoder that needs no protoc. Its authors say to use it "within bilibili's terms of service". `HFrost0/danmakuC` converts Bilibili protobuf danmaku to ASS subtitles. `bgetlib` (PyPI) has a danmaku fetch function. — [bilibili-cli](https://pkg.go.dev/github.com/tamnd/bilibili-cli@v0.2.0); [danmakuC](https://github.com/HFrost0/danmakuC); [bgetlib](https://pypi.org/project/bgetlib/1.0.0)
- Caution: a gitea project "bilibili_video_down" links downloads to an unrelated domain. Do not install it. — [search result review](https://gitea.com/yqqwe/bilibili_video_down)
- Niconico: yt-dlp's Niconico extractor was reworked to read the `nvComment` block from the watch page (server, params, threadKey) and POST to the comment endpoint, with a fallback to the legacy thread-based download. yt-dlp source is the best current reference for this flow. — [yt-dlp mirror commit "Download comments from the new endpoint"](https://gitea.smoothnet.org/nhyatt/yt-dlp/commit/52ecc33e221f7de7eb6fed6c22489f0c5fdd2c6d)
- Niconico comment objects carry `vpos` (playback position). Legacy write-ups describe vpos in hundredths of a second (the search summary said "tenths of a millisecond", which is likely a garble). A paid hosted API (Anysite) returns `vpos_ms`. — [dennogumi write-up](https://git.dennogumi.org/websites/dennogumi/src/branch/master/content/post/2019-01-03-hack-of-the-day-extracting-comments-from-nicovideo.markdown); [Anysite Niconico comments](https://docs.anysite.io/api-reference/niconico/niconicovideoscomments.md)
- `py-niconico-comment` (Python) has `get_comments(watch_url)` with optional login. It predates nvComment, so it is likely stale. — [py-niconico-comment docs](https://py-niconico-comment.readthedocs.io/en/latest/api/py_niconico_comment.html)

Academic work (time-sync comment, or "TSC", highlight detection):
- Ping and Chen (2017), "Video Highlights Detection and Summarization with Lag-Calibration based on Concept-Emotion Mapping of Crowd-sourced Time-Sync Comments", ACL Workshop on New Frontiers in Summarization (W17-4501, arXiv 1708.02210). It names three problems: comments lag behind the shot they describe, comments are sparse and noisy, and highlight judgment is subjective. Method: lag calibration with concept-mapped lexical chains; each shot scored by comment intensity plus emotion and concept concentration; extended SumBasic for summaries. Reports beating benchmarks on large real-world datasets. — [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210); [ACL Anthology W17-4501](https://aclanthology.org/W17-4501/)
- Ping and Chen dataset: about 2.1M Bilibili comments from about 6,368 long videos for embeddings, plus an emotion lexicon, raw comments for 11 videos, and highlight gold standards. Code: [ChanningPing/VideoHighlightDetection](https://github.com/ChanningPing/VideoHighlightDetection). — [arXiv 1708.02210](https://arxiv.org/pdf/1708.02210)
- Li, Li, Ma, Zhao, Zhang, Yu (2023), "Sentiment Analysis on Online Videos by Time-Sync Comments", Entropy 25(7):1016. A TSC sentiment model plus a shot-level sentiment-intensity calculation. Reports +12.8% F1 and +8.0% overlap over the best prior method for highlight extraction. — [Crossref 10.3390/e25071016](https://api.crossref.org/works/10.3390/E25071016); [PMC10378155](https://pmc.ncbi.nlm.nih.gov/articles/PMC10378155) (full text blocked by a browser check, so dataset sizes were not read)
- TSCSet (IUI 2018) is a crowdsourced time-sync comment dataset. — [search result reference list](https://pmc.ncbi.nlm.nih.gov/articles/PMC10378155) (citation only, not read)

### Inferences
- The Spike chat pipeline (comment rate over a window, then a peak boost) maps almost directly onto danmaku. Danmaku needs a lag correction: shift peaks earlier by a few seconds, because comments trail the moment. Ping and Chen confirm the lag exists. The size of the shift is not sourced here, so tune it on labeled episodes.
- Danmaku has one property Twitch chat lacks: it piles up from many separate viewings, so a peak shows the moment viewers react to on rewatch. That is likely closer to "clippable" than live chat, which also reacts to streamer banter. (Inference.)
- Coverage: Bilibili licenses many simulcast anime for mainland China and some regions. Niconico has official anime channels. Both have dense danmaku on popular shows. (Recalled, not verified this session.) Neither is likely to host TeamFourStar content officially.
- ToS risk: both endpoints are undocumented and reverse-engineered. Unauthenticated GETs to `seg.so` at low rates are not anti-bot bypass. WBI signing, if required, is arguably bypassing a request-integrity check, so it is a gray zone. Niconico comment fetches need watch-page data and sometimes a login. Rate: HIGH ToS risk for any redistribution, MEDIUM for personal, local, low-rate use.

### Gaps
- Bilibili and Niconico ToS text on automated access was not fetched. Read both before shipping.
- Exact `seg.so` WBI and login requirements in 2026, and the login-only historical-danmaku endpoint, were not confirmed (the bilibili-API-collect doc URL returned 404).
- No quantitative "comment density at highlight versus baseline" statistic was found. The density pattern is stated qualitatively in the papers.
- No 2024 to 2026 survey of TSC highlight detection was found. Recent multimodal work (for example LLM plus danmaku) may exist but did not surface.

## YouTube: timestamped comments, "Most replayed" heatmap, chapters

### Takeaway
The official YouTube Data API v3 exposes comments (1 quota unit per `commentThreads.list` page) and video stats, but not the "Most replayed" heatmap. The heatmap exists only in watch-page player data. yt-dlp extracts it as a `heatmap` field of about 100 normalized buckets, and this is the strongest free per-second audience-attention signal for YouTube uploads. Fetching it means non-API page access, which YouTube's Terms of Service prohibit for automated means, so it is a ToS risk even without browser automation.

### Cited Findings
- Data API quota: default 10,000 units per day per project, reset at midnight Pacific. `search.list` costs 100 units. `commentThreads.list` costs 1 unit. Insert and update cost 50. An older page version described a separate cap of 100 `search.list` calls per day. Check the project Quotas page. — [YouTube quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- yt-dlp commit "Extract `heatmap` data (#7100)", closing issue #3888, added a YouTube `heatmap` info field: a list of `{start_time, end_time, value}` with value normalized 0 to 1. It is parsed from the player overlay `heatMarkers`. The test expects `'heatmap': 'count:100'`. — [yt-dlp mirror commit 5caf30d](https://bytes.keithhacks.cyou/etc/yt-dlp/commit/5caf30dbc34f10b0be60676fece635b5c59f0d72)
- The current yt-dlp README did not mention "heatmap" in the parts read, so the field exists in code but is not documented in the README field list. — [yt-dlp README](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md)
- No official API endpoint for the heatmap was found. Other tools read the SVG seek-bar path (`svg.ytp-heat-map-svg`, 1000x100 Bezier path) or use Puppeteer. Both are page-scraping, and the Puppeteer one is excluded by Spike's no-browser-automation rule. — [WillianAgostini/youtube-heatmap](https://github.com/WillianAgostini/youtube-heatmap); [yt_most_replayed (npm)](https://npmjs.com/package/yt_most_replayed)
- The heatmap is often absent on new or low-traffic videos and some Shorts. One tool requires more than 50,000 views (that tool's own rule). Datacenter IPs are often blocked, but a home PC is not a datacenter IP. — [claude-code-youtube-mcp get_most_replayed](https://glama.ai/mcp/servers/wynandw87/claude-code-youtube-mcp/tools/get_most_replayed); [glama MCP listing](https://glama.ai/mcp/servers/n2xpftfzce)
- YouTube Terms (Permissions and Restrictions) prohibit accessing the Service by automated means such as robots, botnets, or scrapers, except public search engines following robots.txt or with prior written permission. They also prohibit downloading content unless the Service allows it or YouTube and the rights holder give written permission. — [YouTube Terms of Service](https://www.youtube.com/static?template=terms) (fetched in the Indonesian locale)
- yt-dlp comment options: `comment_sort` (`top` or `new`, default `new`) and `max_comments` (limits per depth). — [yt-dlp README](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md)

### Inferences
- Timestamped comments: fetch `commentThreads.list` (1 unit per page of up to 100) on an official upload. Regex-extract `m:ss` and `h:mm:ss` mentions and build a histogram. This is ToS-clean through the official API. 10,000 units covers about 10,000 comment pages per day, which is plenty. Comment timestamps are sparse but precise to the second, and on anime uploads they often quote the line ("3:12 the face"). (Inference; the API itself is verified.)
- The heatmap gives about 100 buckets per video, so resolution is duration/100. A 24-minute episode gives about 14 s buckets, good for locating a peak window. A 32 s Short gives about 0.3 s buckets, but Shorts often have no heatmap. Use it to find the window, then refine the cut point with local audio and visual features.
- For the reference target (the TFS "A Win is a Win" Short), the useful YouTube signal is the long-form source: the full abridged episode on the TeamFourStar channel. Its heatmap and timestamped comments would likely point to the scene the Short was cut from. (Inference, not tested.)
- Chapters come from `videos.list` snippet.description (1 unit) by parsing `0:00 Title` lines. yt-dlp also exposes `chapters`. Chapters mark structure (OP, segments), not peaks, so they are a weak signal. (The API cost is verified; the chapter-parsing approach is recalled.)
- Official anime channels (Muse Asia, Ani-One) upload full episodes in some regions, and they get large comment volumes. (Recalled; regional availability not verified.)

### Gaps
- No primary source confirms whether YouTube's Developer Policies explicitly ban reading `heatMarkers` from player responses. The general ToS clause applies.
- The current state of the yt-dlp `heatmap` field in 2026 (still populated, or broken by YouTube player changes) was not tested.
- Muse Asia and Ani-One comment-timestamp density was not measured.

## Reddit r/anime, MyAnimeList, AniList, Jikan: can they point to scenes?

### Takeaway
These are episode-level signals, not timestamp signals. They can rank which episode is hot and supply quoted lines or scene descriptions that can be matched to a local transcript, but they rarely give timestamps. The Reddit API now needs manual approval for new OAuth tokens (since November 2025), and its free tier is non-commercial, so Reddit is the hardest to use. AniList and Jikan are free and easy, but they carry scores and episode lists, not scenes.

### Cited Findings
- Reddit free tier: 100 queries per minute per OAuth client ID and 10 per minute without OAuth, in force since July 1, 2023. — [Reddit 2023 announcement via r/redditdev mirror](https://reddit.rtrace.io/r/redditdev/comments/13wsiks/api_update_enterprise_level_tier_for_large_scale/jmnmq38); [Socialcrawl 2026 guide](https://www.socialcrawl.dev/blog/reddit-api-key-limits-alternatives-2026)
- Nov 11, 2025 "Responsible Builder Policy": Reddit closed self-service Data API access. New OAuth tokens need approval, developers are pointed to Devvit plus a request form, and researchers file a ticket (some go to r/reddit4researchers). Existing access is kept. — [r/redditdev announcement (mirror)](https://r.datuan.dev/r/redditdev/comments/1oug31u/introducing_the_responsible_builder_policy_new/noh6fun)
- Free tier is non-commercial. Commercial pricing of $0.24 per 1,000 calls is reported only by vendors with a commercial interest. It is unverified. — [citybiz 2026](https://www.citybiz.co/article/868288/reddit-api-pricing-in-2026-what-youll-actually-pay-at-every-tier/); [xpoz](https://www.xpoz.ai/blog/guides/reddit-api-pricing-tiers-and-alternatives/)
- New OAuth approval reportedly takes 2 to 4 weeks. — [Socialcrawl 2026 guide](https://www.socialcrawl.dev/blog/reddit-api-key-limits-alternatives-2026) (vendor claim, unverified)
- AniList GraphQL: standard limit 90 requests per minute. The docs say the API is "degraded" and limited to 30 per minute. Exceeding the limit gives a 1-minute timeout. `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers are returned. — [AniList rate limiting docs](https://docs.anilist.co/guide/rate-limiting)
- Jikan (unofficial MAL REST API): 3 requests per second and 60 per minute per secondary docs. — [animedex docs](https://animedex.readthedocs.io/en/latest/tutorials/raw_passthrough.html); [AniDojo](https://mintlify.com/antoniamugisa/anidojo/setup/api-integration) (secondary)

### Inferences
- r/anime episode discussion threads (posted by a bot for each airing episode, recalled) have top comments that quote lines or describe the scene ("when X said Y"). Fuzzy-match the quoted text against the local Whisper transcript to get a timestamp. Precision is about one subtitle line. Fit for Spike: personal, local, low-rate use is probably fine under an existing approved token. Getting a new token is now gated.
- MAL and Jikan have per-episode discussion forum topics and episode scores. AniList has `averageScore` and popularity, but no per-scene data. Use them to pick which episodes to process first, not where to cut.
- Jikan scrapes MAL itself. Using Jikan follows Jikan's terms, but it sits one step removed from MAL's own API (MAL has an official v2 API needing a client ID; recalled).

### Gaps
- Reddit Data API Terms text and Responsible Builder Policy criteria were not read from reddit.com directly.
- MAL official API terms and Jikan's own rate-limit page were not fetched.
- No source measured how often r/anime top comments quote exact lines.

## Existing viral clips as a prior (YouTube Shorts, TikTok)

### Takeaway
Through the YouTube Data API, a search for a show title plus "clip" and filtering by views gives a list of moments that already went viral. The cost is 100 units per search, so about 100 searches per day on the free quota. Each clip's position in the source episode must then be found by audio alignment (next sections). TikTok has no free public API for this. Its Research API is gated to academics.

### Cited Findings
- `search.list` costs 100 units and `videos.list` (view counts, duration) costs 1 unit, out of a 10,000-unit default daily quota. — [YouTube quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)

### Inferences
- Workflow: `search.list?q="<show> episode N"&type=video&videoDuration=short` gives candidate clip IDs. `videos.list?part=statistics,contentDetails` gives views and duration. A view-weighted set of known-popular moments results. Locating each moment in the local episode needs the clip's audio, and downloading it is a ToS problem. ToS-safe alternatives: (a) match the clip's title and description text ("A Win is a Win") against the transcript; (b) use the clip's own captions via the API. The `captions.download` call needs owner authorization (recalled), so in practice only titles and descriptions are usable without downloading.
- For the reference Short ("A Win is a Win", 4.6M views), the title is itself the quoted line. Matching titles of top Shorts to transcript lines is a cheap, legal prior that would have found that moment. (Inference.)
- Per Spike's rules, TikTok is out: no free API, and scraping is prohibited. (The Research API eligibility is recalled, not verified this session.)

### Gaps
- No source on TikTok Research API terms in 2026 was fetched.
- No measurement of how often viral-clip titles quote a transcript line.

## AniSkip and anime-skip community timestamp databases (OP, ED, recap)

### Takeaway
AniSkip has a free, keyless REST API keyed by MyAnimeList ID and episode number. It returns OP, ED, mixed-OP/ED, and recap intervals in seconds, plus the episode length the times were measured on. It is a negative signal (exclude these spans from clip candidates) and an alignment anchor. It was verified with a live call.

### Cited Findings
- Live call `GET https://api.aniskip.com/v2/skip-times/1/1?types=op&types=ed&types=recap&episodeLength=0` (MAL 1 = Cowboy Bebop, ep 1) returned `found: true`, OP 57.397 to 145.737 s (episodeLength 1491.506), and ED 1357.923 to 1480 s (episodeLength 1480.155), each with a `skipId` UUID. — [AniSkip API live response](https://api.aniskip.com/v2/skip-times/1/1?types=op&types=ed&types=recap&episodeLength=0) (Verified)
- Skip types: `op`, `ed`, `mixed-op`, `mixed-ed`, `recap`. Times are in seconds with up to 3 decimals. Returns 404 when nothing is found. POST `/skip-times/{malId}/{episodeNumber}` submits, and `/skip-times/vote/{skipId}` votes. — [AniSkip Greasy Fork wrapper](https://greasyfork.org/en/scripts/457460-aniskip/code)
- Anime Skip (anime-skip.com) is a separate project, a GPL-3.0 browser extension for community timestamps, last listed update 2022-10-08. Its API details were not found. — [GNU Gnuzilla listing](https://gnuzilla.gnu.org/extension.php?id=2655498)

### Inferences
- The two `episodeLength` values differ by about 11 s for the same episode, so submissions come from different cuts. Pass the local file duration as `episodeLength` and prefer results whose length is close. Otherwise shift by the OP start difference.
- AniSkip coverage depends on popularity (crowd-submitted). It is weak or empty for abridged parodies such as DBZ Abridged, which have no MAL ID. (Inference.)

### Gaps
- AniSkip terms of use and rate limits were not found. Cache results and keep requests low.
- How the API uses `episodeLength` to filter results was not verified.

## Aligning external timestamps to a local episode file

### Takeaway
External timestamps come from a different cut (simulcast versus Blu-ray, with or without sponsor cards, recap, or preview), so a constant offset is not always enough. Use anchors first (AniSkip OP start, transcript text match), then audio cross-correlation (BBC audio-offset-finder, audalign) when audio of both versions is lawfully available. Piecewise offsets per scene handle cuts that differ in the middle.

### Cited Findings
- BBC `audio-offset-finder` finds where one audio file sits inside another, using cross-correlation of standardized MFCCs (sound-feature vectors). It is robust to encoding noise and typically accurate to about 0.01 s. — [audio-offset-finder (PyPI)](https://pypi.org/project/audio-offset-finder); [ecosyste.ms entry](https://awesome.ecosyste.ms/projects/github.com%2Fbbc%2Faudio-offset-finder)
- `audalign` aligns recordings mainly by fingerprinting, falling back to correlation, spectrogram correlation, and visual alignment. It also has a `fine_align` refinement step. — [audalign (PyPI)](https://pypi.org/project/audalign)
- CoEDL `av_align.py` does not handle time stretch, so a stretched file (for example 25 versus 23.976 fps PAL speed-up) gets only an average offset. — [CoEDL tutorial](https://coedl-knowledgebase.readthedocs.io/en/latest/posts/20170509_av_align-intro-tutorial/index.html)
- A community tool, "delay-check", reports delay, correlation score, confidence, and drift for MKV, MP4, and MKA. — [VideoHelp forum](https://forum.videohelp.com/showthread.php?p=2799464)

### Inferences
- For danmaku and YouTube heatmaps, the reference timeline is the platform's own stream, which cannot be downloaded legally. Without its audio, align by structure instead: OP start (AniSkip or a local OP detector) gives the offset. Transcript match of quoted lines (Reddit or YouTube comments) checks it. Scene-cut fingerprints are an option if the platform's runtime is known.
- Check drift: compare local duration with `episodeLength`, the YouTube `contentDetails.duration`, or Bilibili video duration. A ratio near 25/23.976 (about 4.3%) means PAL speed-up, so scale instead of shifting.
- An external peak should be treated as a window of about plus or minus 10 to 15 s, then refined with Spike's local signals (audio loudness, laughter, scene cuts). This mirrors how Spike already uses the video verdict as a peak boost. (Inference.)

### Gaps
- No source tested these tools on anime simulcast versus Blu-ray cuts.
- No permitted source of platform-side audio for cross-correlation was identified. This is why the structural anchors above are needed.
