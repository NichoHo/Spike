# Twitch Platform and Crowd Signals for VOD Highlight Detection (beyond chat rate)

Research date: 2026-10-01. Labels: **[V]** verified from a fetched page this session; **[S]** from search-result snippet only (page not fully read); **[R]** recalled from training data, not verified this session; **[I]** inference.

## Helix Get Clips: fields, filtering, vod_offset accuracy, featured clips, clip bursts

### Takeaway
Get Clips (app access token is enough) returns per clip `created_at`, `view_count`, `duration`, `creator_*`, `video_id`, `vod_offset`, `is_featured`. This gives three separate signals per VOD second: clip count (how many distinct people clipped), clip views, and creation-time bursts. `vod_offset` is the best precision available (whole seconds, start of clip). It is null or empty during the live broadcast and after the VOD is deleted, so fall back to `created_at` minus the stream start.

### Cited Findings
- [V] Query params: `broadcaster_id`, `game_id`, `clip_id`, `after`/`before` cursors, `started_at`/`ended_at` (RFC3339 "reporting window"), `is_featured`, `first` (1-100, default 20). — [Helix reference](https://dev.twitch.tv/docs/api/reference/#get-clips)
- [V] Response: `id, url, embed_url, broadcaster_*, creator_id/login/name, video_id, game_id, language, title, view_count, created_at, thumbnail_url, duration`. — [Helix reference](https://dev.twitch.tv/docs/api/reference/#get-clips)
- [V] `vod_offset` added 2023-07-20: "the number of seconds from the start of the video to the beginning of the clip". `is_featured` added to request and response 2023-09-12. — [Twitch API changelog](https://dev.twitch.tv/docs/change-log/)
- [V] "If you get a clip that was created during the current broadcast, the `video_id` field may contain an empty string and the `vod_offset` field may contain null." — [Clips guide](https://dev.twitch.tv/docs/api/clips/)
- [S] If the video is no longer available, `video_id` is an empty string and `vod_offset` is null. — [Helix reference via search](https://dev.twitch.tv/docs/api/reference)
- [V] Live clip capture window: "about 85 seconds of the stream before the call and about 5 seconds after the call"; clip length is 5 to 60 seconds; `has_delay=true` shifts the capture window right. — [Clips guide](https://dev.twitch.tv/docs/api/clips/)
- [V] Default page is 20 clips; more results come with a `pagination.cursor`. — [Clips guide](https://dev.twitch.tv/docs/api/clips/)
- [S] Old forum reports exist of pagination returning null or ending early on large clip sets. — [Dev forum](https://discuss.dev.twitch.com/t/new-twitch-api-helix-returns-null-on-clip-request-with-pagination/22643)
- [V] New 2025 clip endpoints: "Get Clips Download" (open beta 2025-09-19, GA 2025-10-30) gives clip video file URLs. "Create Clip From VOD" (open beta 2025-12-19). — [Twitch API changelog](https://dev.twitch.tv/docs/change-log/)
- [V] Create Clip From VOD needs a user token with `editor:manage:clips` or `channel:manage:clips`, so only the broadcaster or an editor can call it. Beta users report clips shifting several seconds from the requested `vod_offset`. — [Dev forum announcement](https://discuss.dev.twitch.com/t/introducing-clip-api-improvements-and-clip-from-vod-in-open-beta/64492)
- [S] Developers use undocumented GQL to get offsets when Helix returns null. That route is off-limits for Spike. — [Gist](https://gist.github.com/hexcowboy/802853d960d79958500b1a587f3a7e51)

### Inferences
- [I] Query with `started_at`/`ended_at` set to the VOD's `created_at` and `created_at + duration` (plus a few hours of slack for late clips made while watching the VOD). Then filter `video_id == vod_id`. Clips made later from the VOD still carry the same `video_id`.
- [I] Signal shape per second: `clip_count(t)` (number of distinct `creator_id` values whose `[vod_offset, vod_offset+duration]` covers t) is a cleaner "crowd agreed this mattered" signal than views. Views are dominated by one viral clip and by external sharing (Reddit or Twitter traffic), so they are better read as "this moment travelled". Keep both. The planned `log(1+views)` sum fits views. Add a separate count term so 8 low-view clips at one moment still score.
- [I] Bursts: during a live stream, clips of one moment are created within seconds of each other. Clustering `created_at` within roughly 30 s, or `vod_offset` within roughly 20 s, finds "many people clipped this" events. Live clips start roughly 85 s before the click. The punchline therefore sits near the clip's end, not its start, so weight the last third of each live clip more.
- [I] Precision: `vod_offset` is whole seconds. Clip boundaries are fuzzy by several seconds, since clippers trim by hand. Treat it as roughly ±5 s.
- [I] `is_featured=true` clips are streamer-curated, which is a strong quality label (useful as ground truth for evaluation).
- [I] Clips by the same `creator_id` as the broadcaster or a known bot may be Auto Clips or "Clip That" output (see next section). No field verified marks them.

### Gaps
- Did not verify whether Helix caps total results per query (old forum lore says about 1000 per date window). Workaround: split the date range into smaller windows.
- No documented vod_offset accuracy figure was found. Accuracy for clips made from a VOD, as opposed to live, was not checked.
- Not verified whether Get Clips marks Auto Clips or "Clip That" clips with any distinguishing field.

## Stream markers, exported highlights, Auto Clips / Moments

### Takeaway
Stream markers (`position_seconds`) are the most precise streamer-intent signal. However, Get Stream Markers needs a user token from the broadcaster or an editor, so for third-party channels they are unreachable with an app token [R]. Get Videos `type=highlight` lists streamer-exported highlights, but gives no offsets into the source VOD. Twitch's AI Auto Clips (alpha late 2025 to 2026) produce ordinary clips. No separate "moments" API was found.

### Cited Findings
- [V] Get Stream Markers: params `broadcaster_id` (Helix reference lists this, though the docs use `user_id` [R]), `video_id`, `first` (max 100), `after`. Returns marker `id`, `created_at`, `description`, `position_seconds`. — [Helix reference](https://dev.twitch.tv/docs/api/reference/#get-stream-markers)
- [R] Get Stream Markers requires a user access token with `user:read:broadcast` or `channel:manage:broadcast`, and returns markers only for the token's user or for channels where that user is an editor. Verify on the reference page before relying on it.
- [V] Get Videos: filter `type` = archive/highlight/upload/all, `sort` = time/trending/views. Returns `stream_id`, `created_at`, `published_at`, `duration`, `view_count`, `muted_segments` and more. No source-VOD offset for highlights. — [Helix reference](https://dev.twitch.tv/docs/api/reference/#get-videos)
- [V] Since 2025-04-19 (deadline extended to 2025-05-19), channels may store at most 100 hours of Highlights plus Uploads. Past broadcasts and clips are not affected. — [TechCrunch](https://techcrunch.com/2025/02/20/twitch-caps-streamers-storage-at-100-hours-of-highlights-and-uploads); [Twitch Support on X](https://x.com/TwitchSupport/status/1911837184119668918)
- [V] TwitchCon San Diego (2025-10-17) announced Auto Clips: AI that clips "the best parts of your stream" using broadcast signals "such as positive excitement from the stream or funny banter", plus a "Clip That" voice command. Streamers review the clips after the stream. Twitch says it will "help highlight relevant moments in your VODs". — [Twitch blog](https://blog.twitch.tv/en/2025/10/17/ten-years-of-twitchcon-here-s-what-we-announced-in-san-diego/)
- [S] Auto Clips entered alpha for accepted channels (2026). — [Threads, Zach Bussey](https://www.threads.com/@zachbussey/post/DV41DSEFiCF)
- [S] Third-party blogs say "Clip That" is rolling out to Partners and Affiliates, and that Auto Clips/"Clip That" clips include captions by default. These are secondary sources. — [StreamLadder](https://www.streamladder.com/blog/twitch-clip-that-voice-command)
- [V] The VOD chapters (game changes) are present in the TwitchDownloader JSON `video.chapters` (`startMilliseconds`, `lengthMilliseconds`, `gameDisplayName`). — [TwitchDownloader ChatRoot.cs](https://raw.githubusercontent.com/lay295/TwitchDownloader/master/TwitchDownloaderCore/TwitchObjects/ChatRoot.cs)

### Inferences
- [I] Once published, Auto Clips should show up in Get Clips like any other clip. That would make them a free "Twitch's own AI thinks this is good" signal inside the clip_heat input. They would also bias it, so try to tell them apart (by creator or title pattern) once observed.
- [I] Exported highlights: match a highlight to its source VOD by comparing timestamps or audio fingerprints. That is heavy work. Lazy version: ignore highlights, since clips cover the same need.
- [I] Chapter boundaries (game switches) are segment hints, not highlights. Use them to normalise chat rate per segment.

### Gaps
- No public API for Twitch "VOD moments", Stream Summaries, or Auto Clips candidates was found. Rejected candidates are not exposed anywhere.
- Marker scope requirements were recalled, not verified.

## Events in TwitchDownloaderCLI chat replay JSON; viewer counts for past VODs

### Takeaway
The chat JSON carries `bits_spent` per message, `user_notice_params.msg_id` (subs, resubs, gift subs, highlighted messages), badges, emote fragments, and `content_offset_seconds` (sub-second float [R]). Raids, polls, predictions, hype trains, and plain channel-point redemptions are generally absent from VOD replay [R/I]. Viewer count over time for a past VOD cannot be obtained from any official API.

### Cited Findings
- [V] Comment fields: `_id, created_at, channel_id, content_type, content_id, content_offset_seconds, commenter{display_name,_id,name,bio,created_at,updated_at,logo}, message{body, bits_spent, user_color, fragments[{text, emoticon{emoticon_id}}], user_badges[{_id, version}], user_notice_params{msg_id}, emoticons[{_id,begin,end}]}`. Root also has `video{title, id, created_at, start, end, length, viewCount, game, chapters[]}` and `embeddedData`. — [ChatRoot.cs](https://raw.githubusercontent.com/lay295/TwitchDownloader/master/TwitchDownloaderCore/TwitchObjects/ChatRoot.cs)
- [S] `user_notice_params.msg_id` values seen: `sub, resub, subgift, submysterygift` (plus IRC-style values like `giftpaidupgrade, raid, ritual, bitsbadgetier`). Highlighted channel-point messages carry `"msg-id": "highlighted-message"`. — [TwitchDownloader issue #102](https://github.com/lay295/TwitchDownloader/issues/102); [IRC tags](https://dev.twitch.tv/docs/irc/tags/)
- [V] A 2022 regression made `msg_id` null for every message (v1.50.5). Treat the field as unreliable and fall back to body-text patterns (for example "subscribed at Tier", "is gifting") plus `user_badges`. — [Issue #393](https://github.com/lay295/TwitchDownloader/issues/393)
- [V] CLI options: output `.json/.html/.txt`; `-E/--embed-images`; `--bttv/--ffz/--stv` (default true); `--compression Gzip`; `-b/-e` trim. — [CLI README](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderCLI/README.md)
- [V] IRC added `viewermilestone` and `modiversary` USERNOTICE types (2026-06-18). Live only, so they may not appear in replay. — [Changelog](https://dev.twitch.tv/docs/change-log/)
- [V] Hype train: "Get Hype Train Events" was removed 2026-02-05 and replaced by "Get Hype Train Status" (current state only). EventSub hype train v1 was deprecated 2025-06-13. — [Changelog](https://dev.twitch.tv/docs/change-log/)
- [S] There is no way to get viewer count over time for past streams via the API. You must poll Get Streams live (about once per minute). — [Dev forum](https://discuss.dev.twitch.com/t/analytics-of-single-stream/45335)
- [R] TwitchDownloader fetches VOD comments through Twitch's internal GQL endpoint (gql.twitch.tv with the web client-id), not Helix. Helix has no VOD-chat endpoint. The CLI README does not state this.

### Inferences
- [I] Usable replay signals: `bits_spent` sum per window (money = strong reaction, but streamer-dependent and often TTS-driven, not funny); gift-sub bursts (`submysterygift`), often triggered by hype moments; emote-fragment density by emote id (KEKW, LUL, OMEGALUL, Pog via `fragments[].emoticon` plus 3rd-party names in text); distinct-chatter count per window; and the share of messages from subs or first-time chatters (badges).
- [I] Sub/gift events are partly scheduled noise (sub goals, alerts). Down-weight them unless they cluster with emote spikes.
- [I] Viewer count: the only $0 path is a live recorder that polls Get Streams every 60 s while the channel is live. That is out of scope for a VOD-only tool. `video.viewCount` is a total, not a time series.

### Gaps
- Not verified which msg_id types actually appear in current (2026) VOD replay. Raid, poll, prediction, and hype-train presence is recalled and inferred, not tested. Download one VOD's JSON and `jq '[.comments[].message.user_notice_params.msg_id] | group_by(.) | map({(.[0]//"null"): length})'` to confirm.
- `content_offset_seconds` precision (float vs int) was not verified in a sample file.

## External crowd signals (Reddit LSF, YouTube, X)

### Takeaway
YouTube "Most Replayed" heatmaps on the streamer's own VOD or highlight uploads are the richest external signal. They are likely reachable through yt-dlp's `heatmap` field [R], but need a mapping from YouTube time to Twitch VOD time. Reddit r/LivestreamFail is a decent but sparse signal (only big moments of big streamers), and access now needs Reddit approval. X/Twitter is impractical at $0.

### Cited Findings
- [S] Reddit Data API: free for non-commercial use at 100 queries/min per OAuth client (10-minute average). Since the "Responsible Builder Policy" (updated 2026-06-05 per secondary source), developers must request access and get approval. Commercial use is about $0.24 per 1,000 calls by contract. All of this is from secondary blogs: the primary Reddit help page returned 403. — [SocialCrawl](https://www.socialcrawl.dev/blog/reddit-data-api-2026); [Prowlo](https://prowlo.com/blog/reddit-data-api)
- [V-limited] The yt-dlp README excerpt fetched did not show a `heatmap` field (excerpt was truncated). — [yt-dlp README](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/README.md); [issue #3888](https://github.com/yt-dlp/yt-dlp/issues/3888)
- [R] yt-dlp has exposed `heatmap` (list of `{start_time, end_time, value}`, about 100 buckets) in `--dump-json` for YouTube videos since roughly 2023. Verify with `yt-dlp -j URL | jq .heatmap`. Heatmaps only exist on videos with enough views. The official YouTube Data API does not expose them.
- [S] Community tools already clip YouTube videos from heatmap data. — [youtube-heatmap-clipper](https://github.com/nawirwii/youtube-heatmap-clipper)
- [R] X API free tier is write-only or extremely limited, and the read tiers are paid ($100+/month historically). Not practical at $0.

### Inferences
- [I] Reddit: search `r/LivestreamFail` for `site:clips.twitch.tv` or `twitch.tv/<channel>/clip` links, take the clip slug, then look up its `vod_offset` with Helix Get Clips `id=`. Post `score` and `num_comments` serve as weights. Useful only for large streamers. Make it optional and off by default, given the approval friction.
- [I] YouTube: if the streamer uploads full VODs to YouTube, the heatmap maps nearly 1:1 (plus a constant offset, found by audio cross-correlation). Highlight uploads give little alignment. Fetching the heatmap uses yt-dlp, which is outside YouTube's ToS for downloading but is metadata-only here. Flag it as a grey area.
- [I] Compilation channels re-uploading moments: alignment is costly (audio fingerprinting) for little gain over clips. Skip.

### Gaps
- Reddit's primary policy page was not readable (403). Exact current approval process is unverified.
- The yt-dlp heatmap field was not confirmed from source this session.
- Current X API pricing was not checked.

## Twitch Developer Agreement / ToS relevant points

### Takeaway
Helix use (Get Clips, Videos, Markers) is plainly permitted under the Developer Agreement. Downloading VOD video (yt-dlp) and chat replay (TwitchDownloader via internal GQL [R]) relies on undocumented endpoints. These are widely used and tolerated, but not sanctioned by an official API. For a self-hosted personal tool the risk is low, but it should be stated, not hidden.

### Cited Findings
- [V-failed] The agreement lives at legal.twitch.com/en/legal/developer-agreement/ (redirect from twitch.tv). The page body did not render for fetching, so no clause was verified. — [Developer Agreement](https://legal.twitch.com/en/legal/developer-agreement/)
- [V] Twitch now offers an official clip-file download (Get Clips Download, GA 2025-10-30). This is the sanctioned way to get clip video. — [Changelog](https://dev.twitch.tv/docs/change-log/)

### Inferences / Recalled
- [R] The agreement forbids using undocumented or non-public APIs and scraping, requires respecting rate limits (Helix is roughly 800 points/minute per app token), and restricts storing or redistributing Twitch content beyond what is needed. The Twitch ToS also forbids downloading content except through features Twitch provides. Re-read the live agreement before publishing Spike.
- [I] Safest stance for Spike: Helix for all metadata; Get Clips Download for clip files; yt-dlp/TwitchDownloader only on the user's own or explicitly permitted VODs; no redistribution of chat logs.

### Gaps
- Exact clause text on data retention, caching, and AI/ML use was not verified.

## Twitch VOD retention (2026)

### Takeaway
Past broadcasts: 7 days (regular), 14 days (Affiliate), 60 days (Partner, Turbo, Prime). Clips and past broadcasts are exempt from the 100-hour Highlights/Uploads cap.

### Cited Findings
- [S] "Twitch Partners, Prime and Twitch Turbo users will have past broadcasts saved for 60 days… Twitch Affiliates… 14 days. All other broadcasters… 7 days." — [Twitch Help: On-Demand Content](https://help.twitch.tv/s/article/video-on-demand?language=en_US) (direct fetch failed with a CSS error; text came from the search snippet of that page)
- [V] 100-hour combined cap on Highlights plus Uploads from 2025-04-19 (extended to 2025-05-19). Least-viewed highlights are deleted first. — [TechCrunch](https://techcrunch.com/2025/02/20/twitch-caps-streamers-storage-at-100-hours-of-highlights-and-uploads); [GameRant](https://gamerant.com/twitch-100-hour-storage-limit-highlights-uploads-video-on-demand-change/)

### Inferences
- [I] Spike must process a VOD within 7 days for non-affiliates. Once a VOD is deleted, its clips survive but their `vod_offset` becomes null. Snapshot the clip list (with offsets) when the VOD is first ingested.

### Gaps
- Whether the 2026 help page changed the "Prime" wording was not confirmed.
