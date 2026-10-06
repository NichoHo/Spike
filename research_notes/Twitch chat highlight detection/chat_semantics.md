# Twitch chat spike semantics: what spikes mean and how to tell funny from other spikes

Scope note: researched 2026-10-01. "Verified" = read in a fetched source this session. "Inferred" = reasoning from sources or from recall, flagged as such. Direct answer to the user's question: no, a spike is not "funny". Prior work treats a spike as "something happened" (any highlight type), and separate content signals (laughter tokens) are needed to label it funny.

## Q1. Non-highlight causes of chat spikes and how to filter them

### Takeaway
Many spikes are not reactions to on-screen content: sub/gift events, raids, giveaways and !commands, bot output, copypasta, and stream start/end greetings. Twitch VOD chat replay (what TwitchDownloaderCLI fetches) appears to drop most system events, so sub-bomb "system lines" are mostly absent, but the human chat they trigger ("W", "PogU", thank-you spam) is still there and looks like hype. Filter with: bot account list, "!" prefix, duplicate-message collapse, unique-chatter counting, and `user_notice_params.msg_id` when present.

### Cited Findings
- Twitch VOD chat replay includes only ordinary chat messages (id, login, display name, content offset, created time, text fragments and emotes, badges, color). It omits "subs, resubs, gift subs, raids, announcements; channel point redeems (a redeem with a message shows up as a plain message with no reward info; one without a message doesn't appear at all)". Also missing: first-time chatter flags, highlighted messages, power-ups, reply threading; cheers survive only as the cheer text. [vEXOULZ/twitch-archive issue #21](https://github.com/vEXOULZ/twitch-archive/issues/21) (verified; a third-party developer's observation, not official Twitch docs)
- Partial conflict: TwitchDownloader's JSON schema has a `message.user_notice_params.msg_id` field and a `bits_spent` field, so some notice/bits metadata can appear in downloaded comments. [TwitchDownloader ChatRoot.cs](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderCore/TwitchObjects/ChatRoot.cs) (verified). The WPF chat render can draw sub, resub and sub gift messages, which is an option the user can disable. [TwitchDownloader WPF README, via search snippet](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderWPF/README.md) (snippet only). Resolve by checking real downloaded JSON for non-null `user_notice_params.msg_id` values.
- Full schema per comment: `_id, created_at, channel_id, content_type, content_id, content_offset_seconds, commenter{display_name,_id,name,bio,created_at,updated_at,logo}, message{body, bits_spent, fragments[{text, emoticon}], user_badges[{_id, version}], user_color, user_notice_params{msg_id}, emoticons[{_id, begin, end}]}`. [ChatRoot.cs](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderCore/TwitchObjects/ChatRoot.cs) (verified)
- Live IRC USERNOTICE `msg-id` values include sub, resub, subgift, anonsubgift, submysterygift, giftpaidupgrade, rewardgift, anongiftpaidupgrade, raid, unraid, ritual, bitsbadgetier; raid tags include `msg-param-login`, subgift tags include recipient fields. [Twitch IRC docs](https://dev.twitch.tv/docs/chat/irc/) via search summary (search snippet, not fetched in full)
- Copypasta is a wall of text spammed to provoke a reaction, often stacked during hype moments. [Kotaku, How To Read Twitch Chat](https://kotaku.com/how-to-read-twitch-chat-1825835496) (search snippet)
- Nightbot and StreamElements spam filters target caps, links, emotes, symbols, long paragraphs, banned words (i.e. these bots are present in many chats and themselves post moderation/command replies). [StreamHub Nightbot guide](https://streamhub.world/streamer-blog/software/1016-using-nightbot-for-stream-moderation-and-commands-a-comprehensive-guide/) (search snippet)
- joaohenggeler's highlight scripts use a `top_bucket_distance_threshold` to stop near-duplicate highlights clustering, and require explicit category word lists rather than raw rate. [twitch-chat-highlights](https://github.com/joaohenggeler/twitch-chat-highlights) (verified)

### Inferences
- Spike size by cause: I found no source quantifying how large sub bombs, raids, giveaways or hello/bye floods are relative to funny spikes. Recall-based (unverified): raid arrivals and "!enter"/giveaway keyword floods can exceed any content reaction because hundreds of distinct users post the same token; stream-start "hi" floods are front-loaded in the first minutes.
- Practical filters (inferred, cheap): drop messages whose commenter `name` is in a bot list (nightbot, streamelements, moobot, fossabot, streamlabs, wizebot, soundalerts, sery_bot, plus any account that posts > N identical messages); drop bodies starting with "!"; drop messages with non-null `user_notice_params.msg_id`; drop the first and last ~3 to 5 minutes or down-weight "hi/hello/bye/gn" tokens; count unique chatters, not messages, so one spammer cannot make a spike; collapse exact repeats from the same user inside the window.
- Raid detection without system events: a burst of first-ever messages from previously unseen usernames, often all containing the raider's raid message or emote, is a raid signature (inferred).
- A streamer asking chat a question ("type 1 or 2", "is this good?") produces short, uniform answers. These look like emote walls but the dominant tokens are digits, "yes/no", or a single word; a "1/2/yes/no" share feature can separate them (inferred).

### Gaps
- No measurement found of spike magnitude per non-content cause.
- Not verified whether 2026 Twitch GQL replay still returns any sub/raid lines; the two sources above disagree in emphasis.
- No published, maintained bot-account list was found; the list above is from recall.

## Q2. Emote semantics: laughter vs hype vs shock vs sad vs cringe; getting per-channel third-party emotes

### Takeaway
Laughter, hype, fear and sadness emotes are distinct and labelable, but Spike's current hype list mixes them: LUL/KEKW/OMEGALUL/LMAO are laughter, Pog/W are hype, "?????" is confusion/shock. Splitting into a laughter score vs a hype score is the core change. Third-party emotes (BTTV/FFZ/7TV) are a large share of real usage, and TwitchDownloader only embeds them with `--embed-images`; they appear in message text regardless, so a name list from the public APIs is enough to match them.

### Cited Findings
- Emote meanings from a peer-reviewed table: PogChamp = "Amazement, for example, if the streamer shows extraordinary skill in the game"; LUL = "General laughter or amusement"; Kappa = sarcasm/irony. [Kobs et al., Emote-Controlled, ACM TSC 2020](https://dl.acm.org/doi/fullHtml/10.1145/3365523) (search excerpt of the paper; full page returned 403)
- Kobs et al. built an emote sentiment lexicon by surveying active Twitch users on the 100 most used emotes, released as TSV (average score in [-1,1] and positive/neutral/negative distribution), plus 2,000 labeled comments with 3 annotators each. License: non-commercial only. [konstantinkobs/emote-controlled](https://github.com/konstantinkobs/emote-controlled) (verified). Note: it labels polarity (positive/negative), not emotion type, so it does not separate funny from hype.
- Kobs et al. found that removing examples containing "Pog" raised their CNN accuracy to 65.6% (about 2 points), i.e. ambiguous emotes hurt sentiment models. [Emote-Controlled](https://dl.acm.org/doi/fullHtml/10.1145/3365523) (excerpt)
- FeelsGoodMan (Dolin et al., arXiv 2108.08411): 313M messages from 521k streams over one week in April 2021; 8.06M emotes exist, 400k+ observed; emotes are one third of unique tokens; "FFZ and BTTV emotes... represent 44 of the top 100 most used emotes". Unsupervised k-NN over word embeddings assigned sentiment to 22,507 emotes (RMSE 0.275 vs manual labels). Sad cluster example: FeelsBadMan neighbors Sadge, PepeHands, peepoSad. No public dataset or code URL in the paper. [FeelsGoodMan](https://arxiv.org/html/2108.08411v2) (verified). Note: 7TV was not counted separately in that 2021 study.
- MINT ("Finding Epic Moments in Live Content through Learning from Collective Decisions", EPJ Data Science) uses an emote embedding for audience sentiment plus video; 0.8261 accuracy classifying popular clips; a user study found it surfaced diverse moment types: funny, sad, exciting, nervous. [dscig/twitch-highlight-detection](https://github.com/dscig/twitch-highlight-detection) (verified). This directly supports "spike != funny": popular moments span emotion types.
- KEKW = extreme laughter (El Risitas image); OMEGALUL = more extreme than LUL/KEKW, a BTTV/7TV emote not first-party; pepeLaugh = intense laughter. [StreamLadder KEKW](https://www.streamladder.com/emotes/kekw), [StreamLadder OMEGALUL](https://www.streamladder.com/emotes/omegalul), [own3d pepeLaugh](https://www.own3d.tv/en/blog/dictionary/pepelaugh/) (search snippets; popular glossaries, not research)
- monkaS = intense anxiety/stress; Kappa = sarcasm. [psewdg emote dictionary](https://www.psewdg.com/twitch-emote-dictionary/) (search snippet)
- Third-party emote lookup endpoints: BTTV `https://api.betterttv.net/3/cached/users/twitch/{twitch_user_id}` and global `/3/cached/emotes/global`; FFZ `https://api.frankerfacez.com/v1/room/{channel}` and `/v1/set/global`; 7TV needs the user then the emote set ID as a second request. [chuckxD endpoint gist](https://gist.github.com/chuckxD/377211b3dd3e8ca8dc505500938555eb), [all-chat PR #883](https://github.com/caesarakalaeii/all-chat/pull/883) (search snippets). Official 7TV docs live at [7tv.app/api/docs](https://7tv.app/api/docs) (page did not render for the fetcher). From recall, unverified: `https://7tv.io/v3/users/twitch/{twitch_user_id}` returns `emote_set.emotes[].name`, no auth.
- TwitchDownloaderCLI `chatdownload`: `--embed-images` (default false) embeds first-party emotes, badges and cheermotes; `--bttv`, `--ffz`, `--stv` (default true) add third-party emotes but only take effect with `--embed-images`. Embedded third-party entries carry `id, name, url, width, height, isZeroWidth, data` under `embeddedData.thirdParty`. `--compression Gzip` cuts JSON 40 to 90%. [TwitchDownloaderCLI README](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderCLI/README.md), [ChatRoot.cs](https://github.com/lay295/TwitchDownloader/blob/master/TwitchDownloaderCore/TwitchObjects/ChatRoot.cs) (verified). Caveat: these are the channel's emotes at download time, not at stream time.

### Inferences
- Proposed category lists (inferred from the glossaries above plus recall; validate on real VODs):
  - Laughter: LUL, LULW, KEKW, KEKL, OMEGALUL, ICANT, pepeLaugh (often "he doesn't know" anticipation, recall), LMAO, LMFAO, lol, xd/XD, "HAHA+", 💀, 😂, 🤣, Kappa-adjacent irony is NOT laughter.
  - Hype/skill: Pog, PogChamp, POGGERS, PogU, W, EZ, Clap, "GG", "CLIP IT" (also appears for funny).
  - Shock/confusion: "?", "????", monkaS, monkaW, WutFace, D:, "WHAT", "NO WAY".
  - Sad/respect: Sadge, PepeHands, BibleThump, F, o7, RIP.
  - Cringe/awkward: Cringe, Aware, monkaHmm, "uhm", 😬.
  - Fail (often funny): "L", "LMAO", OMEGALUL, ICANT co-occurring with "?" is a classic fail-comedy pattern (inferred).
- "Clip it" and "?????" should move out of the hype bucket into their own features: "clip" is type-agnostic, "?" is confusion.
- Emote names are case-sensitive tokens in chat ("W" vs "w", "LUL" vs "lul"); matching on whitespace-split tokens against the channel's emote name set is enough, no image data needed, so `--embed-images` is optional (inferred; it mainly gives you the name list for free).

### Gaps
- No dataset found that labels emotes by emotion type (laughter vs hype vs fear) rather than polarity. "Unpacking Twitch emote sentiment" and "TwitchEmoteSentiment" named in the brief were not found in searches.
- 7TV API response shape not verified this session.

## Q3. Features beyond rate that separate funny from other spikes

### Takeaway
The best-supported extra features are message length (shorter at highlights) and message similarity (more repetitive at highlights), from LIGHTOR. Funny-specific separation must come from content: laughter token share (multilingual), vs hype, "?", sad and greeting shares. Rate alone does not encode type.

### Cited Findings
- LIGHTOR (ICDE 2020, Dota 2 and LoL, 60 + 173 live videos) uses three chat features: message number, message length, message similarity. "For highlights, viewers tend to send short messages, and messages tend to be more similar to each other." Precision up to 70 to 90%. [LIGHTOR paper](https://www.cs.sfu.ca/~jnwang/papers/lightor.pdf) (verified via extraction)
- Fu et al. 2017 (EMNLP, LoL esports, 218 NALCS + 103 LMS videos, English and Traditional Chinese chat): chat-only character LSTM F1 43.2 (NALCS) / 39.7 (LMS); video-only 72.2 / 69.2; combined 74.7 / 70.0. Chat alone is a weak highlight predictor in esports broadcasts. [Fu et al., Video Highlight Prediction Using Audience Chat Reactions](https://aclanthology.org/D17-1102.pdf) (verified via extraction)
- joaohenggeler's tool defines highlight categories by word/emote lists (e.g. top 10 funniest moments by counting LUL in a 20 s window) and can compare opposing categories (positive vs negative, plus "controversial"). [twitch-chat-highlights](https://github.com/joaohenggeler/twitch-chat-highlights) (verified)
- hougesen/twitch-highlight-finder focuses on emotes to be language-independent. [twitch-highlight-finder](https://github.com/hougesen/twitch-highlight-finder) (search snippet)
- Online laughter by language: Spanish "jaja", Portuguese "kkkk"/"rsrs", Thai "55555", Korean "ㅋㅋㅋ"/"ㅎㅎㅎ", Japanese "www" (more w = funnier), Indonesian "wkwk". [OpenL blog](https://blog.openl.io/how-people-laugh-online/), [Rest of World](https://restofworld.org/2023/how-people-laugh-online/) (search snippets)
- Kobs et al.: positive is the most common sentiment class in their labeled Twitch comments (40.06%). [Emote-Controlled](https://dl.acm.org/doi/fullHtml/10.1145/3365523) (excerpt)

### Inferences
- Feature set for a funny score (inferred, all cheap per 1 s bin):
  1. laugh_share = unique chatters posting a laughter token / unique chatters in window (use chatters, not messages).
  2. hype_share, q_share ("?" only messages), sad_share, greet_share, cmd_share as separate negatives or labels.
  3. unique_chatters_per_s z-score as the "something happened" gate, instead of raw messages/s (resists one-user spam).
  4. median message length drop and top-token concentration (share of messages equal to the most common token) as "emote wall" strength; both are LIGHTOR-backed signs of a highlight, not of funniness.
  5. Onset shape: funny reactions are usually sudden (punchline). Slow builds point to tension or hype trains (inferred, no source found).
- Rule of thumb: spike gate on unique chatters, then label by which share dominates. Funny = laugh_share high and laugh_share > hype_share. Fails: laugh + "?" + "L". Clutch plays: Pog/W/Clap. Scary: monkaS/"?"/WutFace. Sad: o7/F/Sadge.
- Kappa and "LUL" can be sarcastic (laughing at the streamer); still "funny" for clipping purposes (inferred).

### Gaps
- No source measured onset shape (sudden vs slow build) by moment type.
- No source compared unique chatters vs message count head to head.
- No evidence found on sentiment-shift features specific to funny moments.

## Q4. Chat lag between event and reaction

### Takeaway
Measured lag is longer than Spike's 8 s shift. LIGHTOR learned a constant of about 20 to 27 s between highlight start and the chat-volume peak. Lag = stream latency (about 2 to 15 s by latency mode) + human reaction and typing time, and it varies by channel, so it should be estimated per channel or per VOD.

### Cited Findings
- LIGHTOR: delay between highlight and chat-message peak is "around 20s"; handled by subtracting a constant c learned from training data, around 20 s to 27 s, from the peak time to estimate highlight start. [LIGHTOR](https://www.cs.sfu.ca/~jnwang/papers/lightor.pdf) (verified via extraction; Dota 2 / LoL data from around 2018, when latency was higher)
- Twitch latency: normal mode around 10 to 15 s (5 to 25 s range); low latency 4 to 6 s (2 to 5 s good setups); "ultra low" about 1.5 to 3 s. [space-node guide 2026](https://space-node.net/blog/twitch-low-latency-streaming-guide-2026), [StreamScheme stream delay](https://www.streamscheme.com/how-to-set-up-a-twitch-delay/) (search snippets; blog quality)
- Streamers can also add a deliberate broadcast delay (anti-stream-sniping), adding minutes in some setups. [StreamScheme stream delay](https://www.streamscheme.com/how-to-set-up-a-twitch-delay/) (search snippet)
- joaohenggeler uses a configurable `top_url_delay` subtracted from the VOD timestamp. [twitch-chat-highlights](https://github.com/joaohenggeler/twitch-chat-highlights) (verified)

### Inferences
- `content_offset_seconds` is when the server received the message on the VOD timeline. The viewer saw the event at event_time + latency, then reacted. So peak offset ≈ event + latency + reaction (2 to 5 s) + time for the peak to build. An 8 s shift fits low-latency channels; 15 to 25 s fits normal latency or esports broadcasts (inferred).
- Better: estimate lag per VOD by cross-correlating chat laugh_share or unique-chatter rate with the audio loudness/laughter envelope over lags 0 to 30 s, and take the argmax; or use community clips (their VOD offsets) as anchors. Clip windows also absorb error if they start ~25 s before the chat peak (inferred).
- Delay is a distribution, not a constant: use the onset of the rise (first bin above threshold), not the peak, as the anchor, since big peaks keep building for several seconds (inferred).

### Gaps
- No 2024 to 2026 measurement of chat lag per latency mode was found.
- No published cross-correlation lag estimate on Twitch chat vs audio was found in this pass.

## Q5. Normalization across chat sizes and burst detection

### Takeaway
Per-VOD z-scores break on small chats (counts are sparse, Poisson-like, and a few messages produce big z values) and saturate on huge chats. Use unique chatters, a rolling baseline, and a count-aware test (Poisson tail or percentile) with a minimum-count floor. Kleinberg bursts are a principled option but assume Poisson arrivals, which chat violates.

### Cited Findings
- Kleinberg's burst model uses a multistate automaton where a hidden bursty state emits messages at a higher rate; it assumes Poisson arrivals with exponential gaps, an assumption several papers call inappropriate for real message streams. [Zhao et al. arXiv 1411.3808](https://arxiv.org/pdf/1411.3808), [Kleinberg, Bursty and Hierarchical Structure in Streams](https://www.researchgate.net/publication/2842034_Bursty_and_Hierarchical_Structure_in_Streams) (search snippets)
- An R implementation exists (`bursts` package). [CRAN bursts](https://cran.r-project.org/web/packages/bursts/bursts.pdf) (search snippet)
- Social-media bursts split into exogenous (outside event) and endogenous (internal cascade) with baseline fluctuations. [arXiv 1407.6447](https://arxiv.org/pdf/1407.6447) (search snippet; relevant analogy: content reaction = exogenous, copypasta cascade = endogenous)
- LIGHTOR and joaohenggeler both use fixed window counts with thresholds (minimum count per bucket) rather than z-scores. [LIGHTOR](https://www.cs.sfu.ca/~jnwang/papers/lightor.pdf), [twitch-chat-highlights](https://github.com/joaohenggeler/twitch-chat-highlights) (verified)

### Inferences
- Small chats (under ~1 message/s): sum over 10 to 20 s windows, require a minimum number of unique chatters (e.g. 3 to 5), and score with a Poisson upper-tail p-value against a rolling median rate. For share features (laugh_share), shrink toward the VOD mean with a prior (add-k smoothing) so 2 of 2 messages being "LUL" does not score 100%.
- Large chats: use log rate or rank percentiles; z on raw rate is dominated by the few largest events.
- Rolling baseline (e.g. median of the previous 5 to 10 min) handles slow drifts like viewer count rising through a stream, which a single per-VOD mean does not (inferred).

### Gaps
- No source compared z-score vs percentile vs Kleinberg on Twitch chat directly.
