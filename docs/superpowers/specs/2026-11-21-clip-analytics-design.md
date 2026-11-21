# Clip analytics: stats per Short, AI insights, and tuning from results

## Goal

1. See how each posted Short did, linked to the clip that made it.
2. Get a weekly explanation of why the best and worst Shorts did what they did.
3. Let the results move the judge in small steps that the user approves.

## What the code and data show

- `posts` stores `platform_post_id`. `post_stats` exists, but no code writes it (grep finds only the `CREATE` in `db.py`). BLUEPRINT Phase 7 plans "pull post stats at 24 h and 7 d". It was not built.
- On this machine, `data/spike.db` has 0 accounts, 0 posts, 0 `post_stats` rows and 0 anime candidates (checked 2026-11-21). The 29 DragonSoulClips Shorts are not linked to any clip.
- A candidate stores `features`, the scores, `hook_text` and `hook_options`. A clip stores layout, caption style and frame size. `restart_job` deletes candidates (clips cascade), and cleanup deletes section files after 7 days. So a posted Short must keep its own copy of these facts, as a label does.
- The YouTube sign-in asks for `youtube.upload` and `youtube.readonly`. The Analytics API needs `yt-analytics.readonly` as well, and `reports.query` also needs `youtube.readonly` (verified, reports.query reference, 2026-11-21).
- `labels.analyze_gold` already has Gemini watch a Short at low resolution. Gemini uses about 100 tokens per second of video at low resolution (verified, Gemini video docs, 2026-11-21).
- `src/outreach/youtube.py` already lists a channel's uploads (`playlistItems`) and reads `statistics` in batches of 50 (`videos.list`), with quota counting.
- `run_claude` (`claude -p` on the Pro plan) is the Claude path. The editor and the creator profile use it.

## Design

The work has five steps. Each step ships on its own. Step 1 alone answers "what gets views".

### Step 1: YouTube stats and the Analytics tab

**Tables**

`published`: one row per Short on a connected channel.

| Column | Meaning |
|---|---|
| `account_id` | FK `accounts`, cascade |
| `platform` | `youtube` (Instagram and TikTok later) |
| `platform_video_id` | Unique per platform |
| `url`, `title`, `published_at`, `duration_s` | From the platform |
| `post_id` | FK `posts`, set null. Set when Spike posted the Short |
| `candidate_id` | No FK. The candidate it came from. Null when unlinked |
| `facts` | JSON copy, made when the row is linked: title, hook text, hook voice, hook options, layout, frame, caption style, music, scores, judge reason, and `clips.render_facts` (Step 2) |
| `watch_notes` | JSON from Step 2 |
| `retention` | JSON: the 100 `audienceWatchRatio` points |
| `link_state` | `auto`, `confirmed` or `none` |

`published_stats`: one row per Short per day. Columns: `published_id`, `day`, `views`, `engaged_views`, `likes`, `comments`, `shares`, `subs_gained`, `avg_view_pct`, `avg_view_s`. Unique on (`published_id`, `day`).

`post_stats` is dropped. No code writes it, so it is empty on every machine.

**Linking**

- When Spike uploads a Short, it creates the `published` row with `post_id` and the facts. `link_state` is `auto`.
- Once a day, Spike lists the channel's uploads with the existing outreach helpers (about 2 quota units per 50 Shorts). Each new video of 180 s or less becomes a row.
- A new row links by itself when its title matches exactly one candidate made before the Short was published. The match ignores case and spacing and needs a `difflib` ratio of 0.9 or more.
- Other rows show as Unlinked, with a picker that lists clips by title, newest first. A pick sets `link_state` to `confirmed`.
- Unlinked Shorts (for example the 29 old ones) still count for the channel median, get watch notes, and go to the insights with less detail.

**Pulling**

- Once a day, in the worker loop next to `sweep_old_sections`. It covers Shorts under 35 days old, and every Short on the first import.
- One `reports.query` call: `ids=channel==MINE`, `dimensions=day,video`, `filters=video==id1,id2,...`. Metrics: `views,engagedViews,likes,comments,shares,subscribersGained,averageViewPercentage,averageViewDuration`. The date range runs from the oldest publish date to today.
- Limits (verified): up to 500 video ids per call, and video ids times days must stay at 50,000 or less.
- `dimensions=day,video` with a multi-video filter is allowed by the reference, but check it at build time. The fallback is one call per Short.
- Analytics data arrives late (recalled: about 2 days; check at build time). Each day row is upserted, so late numbers fill in.
- Retention needs one call per Short (single-video only, verified). Spike makes it at age 7 days and at age 28 days.

**Numbers (computed in code, never by a model)**

- `views_7d` = the sum of views on days 0 to 6 after publishing. The same for 1 day and 28 days. All comparisons use the same age.
- `stayed` = `engaged_views` ÷ `views` over the same days. This is the closest API number to Studio's "Stayed to watch". It is not known to be the same metric.
- `multiple` = `views_7d` ÷ the median `views_7d` of the channel's other Shorts published in the 90 days before. It is blank when fewer than 5 such Shorts exist. Above 3x is a hit, under 1.5x is a normal day (a rule of thumb from instagram-agent-skill, not measured).
- Shares per 1,000 views, and subscribers per 1,000 views.
- `diagnosis`: low `stayed` means an opening problem. Good `stayed` with a low `multiple` means YouTube did not push it, or the topic is weak. Views with no subscribers means a channel page problem.
- `drop` = the largest fall between two neighboring retention points in the first 90% of the Short. It is shown as seconds and as the transcript line at that time (from `facts`). Until Step 2 ships, and for unlinked Shorts, it shows the seconds only. Replays can push Shorts curves above 1.0 (recalled), so drops are measured as falls, not as levels.

**The tab**

- `/analytics`, a new nav item.
- One table, one row per Short: thumbnail, title, publish date, age, hook voice, frame, `views_7d`, `multiple`, `stayed`, average % watched, `drop` (time and line), link state. Every column sorts.
- A group view: by hook voice, frame, layout, score band or opening check. Each group shows the median `stayed`, the median `multiple` and `n`.
- No charts in this design.

**Sign-in**

- Add `yt-analytics.readonly` to the YouTube scope in `PLATFORMS`. A connected YouTube account must sign in again.
- The Google Cloud project must have the YouTube Analytics API turned on. This is a manual step for the user.
- A 403 from the Analytics call marks the account "Reconnect for analytics". An OAuth app left in Testing gets refresh tokens that expire after 7 days (LEARNINGS, 2026-10-14). A failed refresh shows on the tab as "Reconnect YouTube".

### Step 2: Opening checks and watch notes

**Opening checks (from `beats.py` in instagram-agent-skill; no model)**

- Computed at render time in `stage9c_render`, from the output of `retime_words_for_cuts` (words in output time). Stored in a new column `clips.render_facts`, and copied into `published.facts` when a row links.
- Fields:
  - `first_word_s`: the seconds before the first spoken word.
  - `words_first_3s`: the words spoken in the first 3 s.
  - `longest_quiet_s`: the longest gap between two words.
  - `loops`: true when the last line shares a word of 4 or more letters with the first line (stop words excluded).
  - `hook_card`: true when the clip has hook text.
  - `lines`: each caption line with its output start time. The `drop` lookup uses it.
- The clip page shows the checks on one line. The Analytics groups use them.
- No check changes a render yet. The data decides first. Comedy needs its setup, so the "open on the payoff" rule is not adopted.

**Watch notes (Gemini, `DEFAULT_GEMINI_MODEL`, low resolution)**

- Once per Short, stored in `published.watch_notes`, never redone.
- Input: the public YouTube URL. `config.py` says the default model accepts YouTube URLs. Check at build time that the URL works with low resolution. The fallback is the clip file when the row is linked.
- Output JSON:
  - `opening`: what is seen and heard in the first 3 s.
  - `hook_card`: the text on screen, and whether it is readable.
  - `subject`: one sentence.
  - `pacing`: cuts and dead air.
  - `style`: layout, captions and crop.
  - `ending`: whether it loops.
- Cost: about 3,000 tokens for a 30 s Short. At most 10 watches a day, counted by `gemini_budget`.

### Step 3: Weekly insights (Claude Sonnet)

- In the worker when the newest report is 7 or more days old, and from a Run now button that works once a day at most. The call is `run_claude(model="sonnet", label="analytics insights")`.
- Input, built in code:
  - The top 5 and the bottom 5 Shorts that are at least 7 days old, by `stayed`, with ties broken by `multiple`.
  - For each one: the facts summary, the opening checks, the watch notes, the numbers, and the drop with its line.
  - The group table with `n`.
- Size: about 10,000 tokens in and 1,500 out, plus about 4,000 tokens of `claude -p` overhead (measured, `claude_cli.py`).
- Prompt rules:
  - Every finding cites `published` ids and `n`.
  - A finding is `solid` only with 10 or more Shorts on each side.
  - Day and time are checked last.
  - With fewer than 5 Shorts, the answer is "not enough data".
- Output schema: `findings` [{`claim`, `ids`, `n`, `confidence`: `solid` or `worth_testing`}], `drops` [{`id`, `at_s`, `line`, `likely_cause`}], `next_test` {`change`, `keep_same`, `shorts_needed`}.
- Stored in a new table `insights` (`created_at`, `json`, `tokens_in`, `tokens_out`). The tab shows the newest report and lists the older ones.
- When Claude is paused or fails, the tab shows the error. There is no Gemini fallback, because a weekly report can wait.
- Why Sonnet: Haiku claims more than 29 Shorts support. Opus uses more of the Pro plan, and the input is small. The limit here is data, not reasoning.

### Step 4: Suggested standards (own winners and comparable channels)

From `ig-viral` in instagram-agent-skill: rank by the multiple over each channel's own median, not by views.

- The Standards card on Settings gets "Learn from a channel". The user pastes a YouTube channel link, for example `@Hakaizo`. Spike stores it in the setting `standard_channels`.
- Once a month per channel, and when a channel is added, Spike lists its last 200 uploads with the outreach helpers: 4 `playlistItems` calls and 4 `videos.list` calls, about 8 of 10,000 units.
- Shorts are 180 s or less. Shorts younger than 14 days are left out, because their views are still growing. `multiple` = views ÷ the median views of the rest.
- Suggestions:
  - Up to 10 Shorts with `multiple` 3 or more that are not already standards.
  - Own Shorts with `multiple` 2 or more and `stayed` above the channel median, once 10 own Shorts are at least 7 days old.
- The card lists the suggestions with Add and Dismiss. Add runs the existing gold intake (`analyze_gold`) and stores the multiple in a new column `labels.multiple`. `examples_block` then says "Nx its channel's median".
- Public data has views only. These Shorts teach what YouTube pushes. Spike's own stats teach what keeps viewers watching.

### Step 5: The default hook voice

- `pick_hooks` starts the title card on the first filled voice in `HOOK_VOICES` (relatable today).
- When each voice has 10 or more linked Shorts that are at least 7 days old, and one voice has the highest median `stayed`, the tab offers "Make <voice> the default".
- On approval, the setting `hook_voice_order` puts that voice first.
- When `candidate_id % 5 == 0`, the clip starts on the next filled voice in the order instead, so the other voices keep getting tested.
- Each change is logged as an event and in LEARNINGS.md, with the numbers behind it.

### Instagram and TikTok (only when an account is connected)

- **Instagram:** the same `published` row. Spike pulls lifetime insights once a day while the Reel is under 35 days old: `views`, `reach`, `ig_reels_avg_watch_time`, `reels_skip_rate`, `shares`, `saved`. Scope: `instagram_business_manage_insights`. `stayed` = 1 minus the skip rate. Meta says data can lag up to 48 hours (verified, media insights reference).
- **TikTok:** counts only, through the `video.list` scope (recalled: needs app review). No retention data. Spike posts to the TikTok inbox, so linking matches by post time and caption.

## Not in this design

- Charts.
- Refitting the score weights. That stays in Phase 7 and needs a few hundred Shorts and `spike eval`.
- Prompt changes written by a model.
- Automated comments, replies or DMs.
- The instagram-agent-skill hook scorer and formula list. The author measured AUC 0.56 for picking winners, and the formulas are written for people who talk to the camera.

## Security (T2, Internal/Team, as BLUEPRINT Phase 8)

- The new scopes are read-only. Tokens stay encrypted in `accounts`, as today.
- The Analytics tab needs a login. Learn from a channel, Run now and Make default are admin-only.
- Channel links are accepted only from `youtube.com` and `youtu.be`, and the handle must match `@[A-Za-z0-9._-]{3,30}`. A link never reaches a shell.
- Titles, transcripts and watch notes are untrusted. In a prompt they go inside `<untrusted_data>` tags with a "raw DATA" note. Model output is escaped by the templates and never goes into SQL or a shell.
- Caps: 1 weekly Claude run plus 1 manual run a day, and 10 Gemini watches a day.
- Tokens and keys never go into events or logs.
- Scaling: none. Spike is an internal tool for a small, fixed team.

## Testing and acceptance

One `tests/test_analytics.py`, with the platform calls faked:

1. Linking: a Spike upload creates a linked row. An exact title links automatically. Two matching candidates leave the row unlinked. A pick in the picker sets `confirmed`.
2. Stats: a faked `reports.query` response becomes day rows. A second run does not duplicate them.
3. Numbers: `views_7d` sums days 0 to 6. `multiple` is blank with fewer than 5 other Shorts. `drop` finds the right line.
4. Opening checks on a fixed word list: `first_word_s`, `longest_quiet_s` and `loops`.
5. Insights: the prompt contains the untrusted tags and the ids. The output is checked against the schema. The caps hold.
6. Suggestions: Shorts under 14 days old are left out, 3x or more is suggested, and existing standards are skipped.
7. Hook voice: `hook_voice_order` changes `pick_hooks`, and every fifth candidate starts on another voice.
8. Live: connect the channel, import, and compare 3 Shorts with YouTube Studio.
9. The full suite has the same failures as `main` before the change.

## Open questions

- How do Shorts reach YouTube today, by hand or through Spike? The design handles both. By hand means more Unlinked rows to confirm.
- Which machine holds the clips behind the 29 old Shorts? If one does, its database can link them.
