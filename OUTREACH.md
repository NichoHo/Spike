# Spike: Client Outreach Playbook

How to find and approach streamers, podcasters, and creators who could pay
for Spike clips. This is a sales process managed through a custom Outreach dashboard inside Spike.

**Researched:** 2026-10-14. Rates and reply
numbers come from vendor blogs and are not verified.

---

## 1. Rule zero: fix clip quality first

A sample clip is the pitch. A weak sample loses that creator for good.
Run #38 gave 6 clips and the user rated most of them weak (see
`LEARNINGS.md`, 2026-10-13). Finish Phase 7b and the Indonesian transcript
fix before you contact anyone. Test: would you post the clip on your own
account? If not, do not send it.

---

## 2. What you sell

Two models exist. Spike can serve both.

| Model | Who posts | Who pays | Spike permission |
|---|---|---|---|
| A. Pay per view (default) | The team, on team clip accounts | Creator pays per 1,000 views (CPM) | `written` (or `program` on Whop) |
| B. Done-for-you clips | The creator, on their own channels | Creator pays a flat monthly fee | `written` |

### 2.1 Model A terms (pay per view)

| Term | Starting value | Why |
|---|---|---|
| Rate | $1 per 1,000 views (English creators), $0.50 (Indonesian or SEA creators) | Market average is about $1; SEA budgets are smaller (judgment) |
| Minimum per clip | 10,000 views before a clip counts | Filters flops, but most good clips still pay |
| Cap per clip | $100 | One viral clip cannot blow the budget |
| Cap per month | $150 to $500, agreed up front | Creator knows the worst case |
| Free trial | 1 week of clips | Proof before any money |
| Billing | Monthly invoice with analytics screenshots, or the creator funds a Whop campaign | Whop holds the budget and pays on approved views (reported fee about 10%) |

Do not use "pay only when a clip reaches 100,000 views":

1. Most clips from a mid-size creator will not reach 100,000 views on a new
   account. You would do most of the work for free.
2. A clip with 90,000 views gives the creator real reach and earns $0. That
   feels unfair, and it pushes you to chase only viral bets.
3. "Per 1,000 views" is unclear. Is a 1,000,000-view clip paid once or
   ten times? Price per 1,000 views instead.
4. A view threshold is not a guarantee. Do not call it one.

Example (assumed numbers, check against your own data): 30 clips a month,
10 clips pass 10,000 views, those 10 clips get 400,000 views in total. At
$1 per 1,000 views, the creator pays $400 (or the monthly cap). Under the
100,000 rule, maybe 1 clip qualifies and you earn $100.

### 2.2 Model B terms (done-for-you)

About $150 to $400 a month for 20 to 30 finished clips that the creator
posts. This is a judgment call: no public rate card exists for small
creators. Spike makes extra clips almost free, so you can price below human
editors. The creator keeps all platform revenue.

### 2.3 Platform revenue (Model A)

On your own accounts, you keep the platform revenue. Write this into the
agreement. Do not plan your income on it:

| Platform | What it pays clip accounts (third-party estimates, not verified) |
|---|---|
| YouTube Shorts | About $0.02 to $0.08 per 1,000 views for entertainment with a mixed audience. Needs YPP. The reused-content policy can block a channel of other people's clips, even with permission |
| TikTok Creator Rewards | Needs 10,000 followers, 100,000 views in 30 days, videos over 1 minute, and original content. Most short clips do not qualify |
| Instagram Reels | Little or nothing for most accounts (recalled) |

One million views earn about $20 to $80 from YouTube Shorts, against about
$1,000 from the creator at $1 per 1,000 views. The creator's fee is the
business. Platform revenue is a bonus.

Market context (vendor blogs, 2026, not verified): Whop campaigns pay
clippers $0.20 to $6 per 1,000 views, about $1 on average. Large agencies
sell at about $0.50 to $4 per 1,000 views with $5,000+ minimums.

---

## 3. Who to target

### 3.1 Size

Target the middle. Big creators already have editors or managers. Very small
creators cannot pay and have little footage people search for.

| Platform | Target range (starting guess) |
|---|---|
| Twitch or Kick | About 50 to 1,000 average live viewers |
| YouTube live or podcast | About 10,000 to 300,000 subscribers |

These ranges are a judgment call, not a sourced number. Adjust them after the
first 30 contacts.

### 3.2 Signs a creator needs you

Check all of these by hand or automated via API signals on their channels:

1. They stream or record long sessions (2 hours or more), several times a
   week.
2. Their Shorts, TikTok, or Reels are missing, rare, or more than 2 weeks
   old.
3. Fans already clip them (Twitch clips page, fan clip channels). Demand
   exists, but nobody turns it into a steady channel.
4. They run a clipping campaign on Whop or a similar site. They already pay
   for clips. These are the warmest leads.
5. They list a business email.

### 3.3 Personality and format that fit Spike

Spike finds moments from chat, laughter, loudness, and the transcript. Pick
creators where those signals are strong.

Good fit:

- High energy, loud reactions, rage, laughter, constant talking.
- Strong recurring bits, catchphrases, or running jokes.
- Active chat (more signal for Spike).
- Podcasts with 2 or more people on video, with funny or bold opinions.
- Indonesian or mixed-language creators. Most clipping agencies work in
  English only. Spike can transcribe Indonesian after the language fix.

Poor fit:

- Quiet, focused gameplay (speedruns, strategy, chess with little talk).
- Music streams. Copyright claims are likely.
- Gambling streams. They pay well, but the platform and legal risk is high.
- Solo audio podcasts with no video.

---

## 4. How to contact them

### 4.1 Channel order

1. **Business email.** Look in the YouTube channel description or Twitch user bio. Creators list it for offers like this.
2. **X or Instagram DM.** Send one short note that points to the email if provided in bio.
3. **Their Discord.** Join, take part, and be a real member first. Most
   servers ban self-promotion, so never post an ad there.
4. **Manager or agency email.** Use it only for big creators. It is slow.

### 4.2 The first message

Lead with free work, not a pitch.

1. Review and approve the streamer candidate in the Outreach dashboard.
2. Spike automatically processes their latest long stream to generate **1 trial clip**.
3. Check and edit the 1 sample clip by hand inside Spike's editor (`/clips/<id>`).
4. Share it as a private link (Google Drive, see §6.3). Never post their clips
   publicly before they agree in writing.
5. Send a short email via the dashboard (Gmail API):

```text
Subject: A clip from your <day> stream

Hi <name>,

I cut a vertical clip from your stream on <date>: <the moment, e.g. "the donation question at 1:42:10">.

<link>

We're a small team that turns streams into Shorts, TikToks and Reels. We pick the moments, edit and caption them, and post them on our clip accounts with your channel tagged in every post. You pay only for views we bring in: $1 per 1,000 views on clips that pass 10,000 views, with a $300 monthly cap so the bill never surprises you. If a clip flops, you pay nothing for it.

If you like it, we'll clip your next week of streams for free first, so you can judge from real numbers.

Should we start with your next stream?

<your first name>
Nexdev · <link to your clip accounts or a results page>
If you'd rather not hear from me, reply "no" and I won't email again.
```

Rules for the email:

- Sign with a person's name, not only the company.
- Link to proof (your clip accounts or a page of results). A software company website does not show that you can clip.
- Name real moments with timestamps. That proves you watched; "we've been watching your streams" does not.
- Put the price in the first email. A clear number builds trust and saves a round trip.
- Follow up once after 4 days, then once more after 11 days. Stop after that.

### 4.3 From yes to paid

1. Free trial: 1 to 2 weeks of clips.
2. Get written permission. Record the link or screenshot in the source's permission field.
3. Ask for a testimonial and their view numbers.
4. Move to a paid plan. Use their numbers in the next pitches.

### 4.4 Volume

The Outreach dashboard (§6) tracks each lead: name, platform, size, contact channel, date sent, follow-up dates, reply, result. Cold email reply rates average about 1 to 2% (vendor claim). Personalized samples should perform better; measure your rate after 50 contacts.

---

## 6. Outreach dashboard

Exactly 1 trial clip per creator. You manually review and approve every streamer first in bulk before any trial clip is rendered. Then, you review and edit the generated clip and email draft before sending. All review steps support bulk operations. Outreach is managed through a central control dashboard, not spreadsheets.

### 6.1 Where it lives

Decision: an Outreach section inside the Spike web app (`/outreach`), with its own code and its own database.

| Part | Where |
|---|---|
| Code | `src/outreach/` (finder, scoring, email, routes) |
| Data | `data/outreach.db`. Lead data is personal data (UU PDP), so it stays out of `spike.db` |
| Finder | Its own process, like the watcher. Runs on a schedule |
| UI | `/outreach` pages in the same app, same login, same design system (`DESIGN.md`) |

Inside the same app, creating a trial clip is an internal function call, and editing a clip is a direct link to `/clips/<id>`. You edit clips seamlessly in Spike's standard editor UI.

### 6.2 Where the lead data comes from

Leads come only from the official YouTube Data API v3. No creator databases, paid tools, or scrapers.

#### A. YouTube Data API v3 rules and quotas

- **Quota (verified 2026-10-14, Google quota calculator):** `search.list` has its own bucket: 100 calls a day, 1 unit each. All other methods share 10,000 units a day.
  - `channels.list`, `playlistItems.list`, `videos.list`: 1 unit per call (up to 50 items).
- **Ledger:** Outreach counts every call in `outreach.db` (`quota` table, day in Pacific time). It stops at its share: 60 searches (Spike's source lookup uses the rest) and 10,000 minus 1,000 units kept for Spike. A `quotaExceeded` error also stops the run.
- **30-day limit (Developer Policy III.E.4):** The nightly job re-fetches channel data for every lead. Activity numbers are re-fetched only while they drive a decision (`found`, `needs_contact`, `approved`); later they are dropped, and only the clipped stream is re-fetched. Data older than 30 days is purged. Manual contacts and sales history stay.
- **No scraping (III.E.6):** Emails and social links come only from the public channel description (`snippet.description`). The About-page email sits behind a CAPTCHA, so a person adds it in Needs contact.
- **One project:** Outreach uses Spike's `YOUTUBE_API_KEY` and shares its daily quota.

#### B. Twitch Helix finder (accepted risk)

**Decision (user, 2026-10-14):** use Twitch Helix to find leads and accept the terms risk. The Twitch Developer Agreement, Schedule 1, bans using Twitch API data to target users with commercial offers (verified 2026-10-14). See `BLUEPRINT.md` §12 rule 7.

**Main risk:** Twitch revokes the client ID. Twitch cannot see the emails. It can see an app scanning whole categories and looking up users it never processes. No source gives a probability.

**Credentials (user's decision, 2026-10-15):** the finder uses Spike's own `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`. Spike's pipeline uses the same app to find VODs and community clips, so if Twitch revokes it, clip scoring loses chat-side signals too, not only the finder. Fallback if that happens: register a new Twitch app and update `.env`. The finder is off until an admin turns it on in Finder settings.

**How it works (`src/outreach/twitch.py`, endpoints verified against the Helix reference 2026-10-14):**

1. **Sample live channels** at the listed hours (default 07, 09, 11, 20, 22 on this PC, WIB): Indonesian prime time is about 20:00 to 23:00, US evenings about 07:00 to 11:00. For each saved Twitch search (category and/or language), `GET /streams?type=live&first=100` pages through live channels. Results come sorted by viewers, highest first, so paging stops once viewers fall below half the range (at most 30 pages). Channels from half to twice the viewer range are stored as samples: user ID, login, viewers, language, category, title. Samples are deleted after 24 hours.
2. **Find leads** in the nightly run (after YouTube): average each channel's viewers over its distinct sample times in the last 24 hours, and keep averages inside the search's range (default 50 to 1,000). Then `GET /users` (100 logins a call) for the bio, and `GET /videos?type=archive&first=30` (1 call per channel) for stream frequency, length, views per stream, and the newest past broadcast to clip. Same hard filters as YouTube (long streams, a VOD to clip, gambling), the same Gemini fit score, and its own daily cap (default 15).
3. **Contact:** emails come only from the bio. Never Whispers or the chat APIs. Email goes out through Gmail, outside Twitch.
4. **One person, one lead:** a Twitch channel that a YouTube lead links to, or that was added by hand, is dropped. Opt-outs cover every linked identity.
5. **24-hour cache** (Developer Agreement): the nightly run re-fetches every Twitch lead's bio and activity, or purges it when older than a day. The clipped stream's date is copied to `clip_stream_at` (our own record) when the email is drafted, so follow-ups can still name the day.

**Rate:** at most 60 requests a minute through the shared limiter, which also obeys `Ratelimit-Remaining`/`Ratelimit-Reset` (verified header names) and waits out a 429. Twitch does not publish the bucket size on the guide page; the headers report it.

**Measured live (2026-10-15, Spike's Twitch app):**
- At 19:50 WIB, Indonesian Twitch had 59 live streams in every category, the biggest at 22 viewers, and none in Just Chatting. Indonesian streamers are mostly not on Twitch, so Indonesian leads come from YouTube. Use Twitch searches for English (or other) streamers.
- English Just Chatting: 2 pages gave 188 channels in range in 3 s. The finder kept 119 candidates in the 50 to 1,000 range, 77 passed the filters (39 had too few long streams, 3 were gambling), and 5 were added, the daily cap (2 with a bio email). The run took 128 s: one Get Videos call per candidate at 60 a minute.

**Kick:** no finder. Kick leads are added by hand.

#### C. How the finder picks streamers

1. Each saved search calls `search.list` with `type=video`, `videoDuration=long` (over 20 minutes), `order=date`, and `publishedAfter` = the look-back window (14 days). `relevanceLanguage` and `regionCode` come from the search. A search has one of two types:
   - **Live streams** adds `eventType=completed`: finished YouTube live streams.
   - **Re-uploads** leaves `eventType` out, to find Twitch and Kick streamers who upload their streams to YouTube afterwards (`eventType=completed` never matches those). Long uploads count as streams. The channel must link a Twitch or Kick channel in its description; the login or slug is stored on the lead (`twitch`, `kick`). Gemini is told to score fan, clip and compilation channels below 20, because they are not the streamer.
2. New channels (not a lead, not opted out, and not dropped in the last 30 days) get `channels.list` (snippet, statistics, uploads playlist). Channels outside the subscriber range are dropped before any further call.
3. For the rest, one `playlistItems.list` each, then `videos.list` in batches of 50 with `statistics` (no extra cost: `videos.list` is 1 unit whatever the parts). This gives long streams in the window, average length, the last stream, Shorts in the window (3 minutes or less), and the newest long stream to clip.
4. Hard filters: **views per stream** inside the search's range (the median views of streams in the window, leaving out streams under a day old; one viral VOD cannot make a small streamer look big), at least 2 streams of 2 hours or more, no more than 10 Shorts in the window (someone clips them already), a finished stream to clip, and no gambling words.
5. Gemini (Flash-Lite) scores fit 0 to 100 with a one-line reason, 10 channels per call, and detects the spoken language. If the search names a language and the channel speaks another, it is dropped (`relevanceLanguage` is only a hint).
6. The best are stored as `found`, up to the daily lead cap. A channel that is the same streamer as an existing lead (the same Twitch or Kick link, or a hand-added `twitch:`/`kick:` lead) is dropped, so one person never becomes two leads. An opt-out on any linked identity covers all of them.
7. Channels dropped by a filter, the fit score or the language check go into the `seen` table (platform, channel ID, reason, time). The finder skips them for 30 days, so they cost no quota each night. After 30 days the row is deleted and the channel can qualify again. Channels that passed but missed the daily cap, or were not scored, are not recorded, so they get another chance the next night.

**Rate limit:** every finder request goes through one shared limiter (`src/outreach/net.py`): at most 60 requests a minute, evenly spaced, no jitter. It also obeys `Ratelimit-Remaining`/`Ratelimit-Reset` and `Retry-After` headers, and retries 429, 5xx and network errors up to 3 times with backoff. Each retry is charged to the quota ledger, because failed calls cost quota too.

#### Schedule and volume limits

All of these are editable in Finder settings.

| Setting | Default | Why |
|---|---|---|
| When | 03:00 each day, or the first minute after if the PC was off. "Run finder now" runs the finder only | Leads are ready in the morning |
| Searches per run | Up to 20, oldest-run first. A run stops early once it has 4 times the lead cap in new channels | Saves search calls |
| New leads per day | 30 | Prevents a review backlog |
| Search calls per day | 60 of 100 | Spike's source lookup needs the rest |
| Units kept for Spike | 1,000 | Spike's comment fetch and lookups still work |
| Nightly refresh | Every lead with API data | 30-day rule |

### 6.3 The pipeline

```text
FINDER (scheduled)         YOU (bulk review)           SPIKE (worker)            YOU (manual review/edit)    YOU (bulk send)
search & filter via   ->   approve or reject      ->   1 trial clip per     ->   edit clip in Spike     ->   send personalized
YouTube Data API           streamers in dashboard      approved streamer         (/clips/<id>), approve     emails via Gmail API
```

1. **Find & Filter.** The scheduled finder queries the YouTube Data API, filters channels by size (10,000 to 300,000 subscribers by default) and recent long streams, extracts public description emails, and drops duplicates (§6.2 C).
2. **Score.** An LLM rates fit (0 to 100) based on signals in §3.3 (high energy, active chat, podcasts, Indonesian/English).
3. **Streamer Review (You, bulk).** In the `/outreach` dashboard, review discovered streamers first. Approve or reject candidate streamers in bulk using checkboxes.
   - Approved streamers with missing contact details move to `needs_contact` (no trial clip rendered until contact info is added).
   - Approved streamers with contact details move to `clip_queued`.
4. **Trial Clip Generation (Spike).** Outreach connects directly with Spike's pipeline to queue exactly 1 trial clip per approved creator (`permission = none`, `target_clips = 1`, `auto_process = off`, `prospect = true`). Spike renders the latest long VOD at low priority.
5. **Clip & Draft Review (You).** The generated clip appears in Spike's standard Review UI. Click "Edit clip" in the dashboard to open `/clips/<id>` and edit/polish the clip. Approving the clip generates the personalized email draft.
6. **Send Emails (You, bulk).** Review drafted emails on the dashboard and click Send in bulk. Outreach dispatches messages via the Gmail API (staggered every few minutes, max ~20/day).
7. **Follow Up (automatic).** Automated follow-ups trigger after 4 and 11 days if no reply is detected via Gmail API. A "no" or "unsubscribe" reply marks the lead opted out permanently.

**Sharing the clip:** Outreach uploads the approved trial clip to Google Drive with an "anyone with link" view permission and includes the URL in the email draft. Files are deleted after 30 days if no reply is received.

**Processing Capacity:** Rendering 1 clip from a 3-hour stream takes ~1.2 to 1.8 hours on single-PC hardware (due to full-stream transcription). Daily cap: 3 trial clips per day (max first 2 hours of VOD).

### 6.4 Lead statuses

`found` > `approved` (or `needs_contact` until email is set) or `rejected` > `clip_queued` > `clip_ready` > `clip_approved` > `email_ready` > `sent` > `followup_1` > `followup_2` > `replied` > `trial` > `client`. `opted_out` is permanent.

Two side exits were added in the build: `clip_failed` (the Spike job failed, found no moment, or the clip was rejected; approving another moment of the same stream still moves the lead on) and `bounced` (the address does not exist; no follow-ups). `approved` means "waiting for a daily trial-clip slot".

### 6.5 Dashboard Screens

| Screen | What it shows | Bulk actions |
|---|---|---|
| Streamers to review | Avatar, name, platform, subscribers / viewer count, language, last stream date, Shorts frequency (14d), bio contacts, fit score & reason | Bulk Approve (triggers 1 trial clip, or moves no-contact leads to Needs contact), Bulk Reject, Snooze 30 days |
| Needs contact | Approved streamers missing email/socials. Direct link to channel | Save manually entered emails (moves lead to trial clip pipeline) |
| Add lead (button, every tab) | Dialog: channel link (YouTube, Twitch, or Kick), email, stream to clip, name, email language, where found, paid-campaign flag | Adds one lead found outside the finder (Whop, Kick, referrals). Counts as the streamer review: it goes to the trial-clip queue, or to Needs contact without an email |
| Clips in progress | Pipeline status from Spike for the 1 trial clip per streamer | None |
| Ready to email | Embedded clip preview, "Edit clip" link to `/clips/<id>`, editable email draft, recipient | Send selected (bulk), Regenerate drafts |
| Sent | Delivery date, follow-up schedule | Stop follow-ups |
| Replies | Email reply snippet, sentiment tag | Mark trial, Mark client, Opt out |
| Clients | Model A or B settings, monthly cap, start date, link to active Spike source | None |
| Finder settings | Saved search queries, platform filters (Twitch/YouTube), daily limits (new leads, max trial clips), follow-up toggles | None |
| Stats | Email conversion, reply rates, closed client counts per saved search | None |

### 6.6 Data (`data/outreach.db`)

| Table | Main columns |
|---|---|
| `leads` | `id, platform, channel_id, name, url, email, email_source, instagram, x, tiktok, discord, website, language, subscribers_or_viewers, last_stream_at, shorts_14d, whop_flag, fit_score, fit_reason, status, reject_reason, spike_source_id, spike_video_id, spike_clip_id, drive_url, api_fetched_at, created_at` |
| `searches` | `id, platform (youtube/twitch), query, language, region, min_size, max_size, active, last_run_at` |
| `messages` | `id, lead_id, kind (first, followup_1, followup_2), subject, body, gmail_message_id, gmail_thread_id, status, sent_at, reply_at, reply_snippet` |
| `opt_outs` | `email, channel_id, at`. Checked before every email dispatch, never deleted |

`api_fetched_at` tracks 30-day API data expiration for YouTube compliance. Manually entered contact details and sales history are retained permanently.

### 6.7 Secrets and Security (BLUEPRINT Phase 8)

- **Google OAuth client:** `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` live only in `.env`. Sign-in uses the authorization code flow with PKCE and a one-time `state`.
- **Gmail OAuth Token:** Encrypted with Fernet key (`src/security.py`). Scopes: `gmail.send` and `gmail.metadata` (headers only, for reply detection; Google lists it as restricted), plus `openid email` to learn the sender address.
- **Google Drive Token:** Scope limited to files created by the application (`drive.file`).
- **Data Retention:** Unresponsive leads are deleted after 6 months. `opt_outs` list is retained permanently.
- **Access Control:** Only admin users can execute bulk sends or modify Finder settings.

---

### 6.8 Running it (built 2026-10-14)

**Code:** `src/outreach/` holds `db.py` (schema, settings, quota ledger), `youtube.py` (finder, refresh, purge), `google.py` (OAuth, Gmail, Drive), `service.py` (lead lifecycle), `daemon.py` (the outreach process) and `routes.py` (`/outreach`). The page is `src/web/templates/pages/outreach.html`. Tests: `tests/test_outreach.py`.

**Setup, once:**

1. In the Google Cloud project that owns `YOUTUBE_API_KEY`, enable the Gmail API and the Google Drive API.
2. Create an OAuth client of type "Web application". Add the redirect URI `<SPIKE_PUBLIC_URL>/outreach/google/callback`. Finder settings shows the exact value.
3. On the consent screen, publish the app to "In production". In "Testing", Google expires the sign-in after 7 days. An unverified app works for your own account; Google shows a warning screen.
4. In `.env`, set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SPIKE_ENCRYPTION_KEY` and `SPIKE_PUBLIC_URL` (the Tailscale address). Restart Spike.
4b. Optional, Twitch finder: it uses Spike's existing `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`. Add Twitch searches and turn it on in Finder settings. Read §6.2 B first: this is an accepted terms risk to Spike's own Twitch app.
5. In Outreach > Finder settings: set the sender's first name and the proof link, add 3 to 5 saved searches, then click Connect Google.

**Processes:** `spike web` starts the outreach process next to the worker and watcher (`--no-outreach` turns it off). `spike outreach` runs it alone. `spike outreach --find-now` runs the finder once.

**What runs when:**

| Every | Work |
|---|---|
| Minute | Sync trial clips with Spike, queue new trial clips (daily cap), write drafts for approved clips, send due emails (daily cap, staggered) |
| Hour | Check replies, bounces and opt-outs in each thread; queue follow-ups on day 4 and day 11 |
| Night | Refresh API data, purge data older than 30 days, forget `seen` channels older than 30 days, delete shared clips after 30 days without a reply, delete silent leads after 180 days, then run the finder |

**Rules the code enforces:**

- A draft is written only after the sender name and proof link are set. A draft with an unfilled `{placeholder}` is never queued.
- `opt_outs` is checked before every queue and every send. A reply that is just "no", or asks to stop or unsubscribe, opts the lead out. Its shared clip is deleted.
- Auto-replies (out of office) do not count as replies. Bounces mark the lead `bounced`.
- Trial-clip sources are created with permission `none`, so Spike blocks posting. An existing Spike source for the same channel is reused unchanged.
- Gmail and Drive tokens are stored only when `SPIKE_ENCRYPTION_KEY` is set, never under the built-in fallback key.
- Every form post is checked for a same-site `Origin`. Tailscale adds identity headers to any request, so without this check another site could make a team member's browser send email.

**Size measure (build step 4):** subscribers are only a cheap pre-filter that saves quota before the activity calls. The real size check is views per stream, set per saved search. Defaults: live searches 10,000 to 300,000 subscribers and 1,000 to 100,000 views per stream; re-upload searches 0 to 300,000 subscribers and 100 to 20,000 views per stream. These are starting guesses; tune them after the first 30 leads. The Shorts count is YouTube only: TikTok and Reels are not checked, and the review table says so.

**Views per stream, measured live (2026-10-14, 2 search calls, 48 units):** live "just chatting live" (en): 222 to 15,644 views per stream; 3 leads passed (for example 38K subscribers, 12.6K views per stream). Re-upload "valorant twitch vod" (en): 25 of 27 channels had under 140 views per stream (top 545 and 4,280), so none passed. Re-uploads get few YouTube views because the audience watched live on Twitch. YouTube data cannot size these streamers; Twitch live viewers (build step 5) can.

**Re-upload searches, measured live (2026-10-14):** "twitch vod" (English) returned 34 channels; their YouTube subscriber counts had a median of about 30, and only 3 had 10,000 or more. 4 linked a Twitch channel. Subscribers are a poor size measure here because the audience watches on Twitch, so the form defaults re-upload searches to a 1,000 minimum. Name a game or category in the query. Average VOD views (build step 4) is the planned fix.

**Leads added by hand:**

- YouTube links (channel, `@handle`, `/user/`, or any of its videos) are resolved with the Data API (about 3 units). The clip target is the stream link if one is given, else the newest long stream in the look-back window, else the newest upload over 20 minutes (podcasts). With none of these, the form asks for a stream link. A stream a person chose is never replaced by the nightly refresh.
- Twitch links use yt-dlp, the same way the watcher finds VODs: the newest finished past broadcast, skipping the one still recording. No Helix calls.
- Kick links need a stream link: yt-dlp reads one Kick VOD but cannot list a channel's videos. The channel comes from the link, because Kick's `uploader_id` is a numeric user ID.
- Twitch and Kick leads are stored as `twitch:<login>` and `kick:<slug>`, so opt-outs and duplicate checks work across platforms. They hold no API data, so the nightly refresh and the 30-day purge skip them.
- No size filter or fit score: the person adding the lead already judged it. The lead's "where found" note shows under its name.

**Not verified yet:** whether `threads.get` with `format=metadata` returns the reply `snippet` under the `gmail.metadata` scope. If it does not, replies are tagged "Read in Gmail" and a person opts them out by hand.

## 7. When outreach changes Spike

| Change | Effect on Spike |
|---|---|
| Clients only receive files or links | No change. Stays T2 |
| Clients log in to Spike | Move to T3, Client-facing (re-run BLUEPRINT Phase 8 with T3 rows) |
| Spike posts to a client's own channel | Spike stores client OAuth tokens. Treat as T3 |
| More than a few clients | Re-check the one-PC capacity (BLUEPRINT §11) and the scaling decision |
