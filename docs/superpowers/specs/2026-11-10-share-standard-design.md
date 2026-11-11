# Share a standard from the iPhone share sheet

**Date:** 2026-11-10. **Builds on:** `2026-11-07-label-store-design.md` (gold labels).

## Goal

Add a short the team admires as a standard in one share from the TikTok,
YouTube or Instagram app, with no reasons and no copy and paste. The
Settings card stays as it is.

## Decisions

- **One iOS Shortcut, not a web app share target.** Safari on iOS does not
  support the Web Share Target manifest field (MDN, checked 2026-11-10). A
  Shortcut with "Show in Share Sheet" can receive the link and post it.
- **No Instagram DM bot.** It would need a Meta developer app, a Creator
  account for nexdev and a token that expires every 60 days. Instant
  delivery needs a public webhook URL, which the blueprint rules out
  (polling the Conversations API every few minutes would work instead).
  On iPhone the Shortcut costs about the same taps. yt-dlp 2026.08.19 read a
  public reel without a login (checked 2026-11-10), so Instagram links work
  through the same path. Build the bot only if the share sheet feels slow.
- **Reach:** the iPhone reaches Spike over Tailscale (`tailscale serve`),
  as every other screen does. The Tailscale login must be a Spike admin, the
  same rule as the Settings card.

## Endpoint

`POST /settings/standards/share`, admin only, a JSON object such as
`{"text": "..."}`.

1. Take every `http(s)` link that passes `gold_url_ok`, once each, from
   every string in the object under any key, lists included. iOS
   capitalizes a key typed in Shortcuts (`Text`), and a share can be a
   list. The Shortcut sends its whole queue (see below), so one post can
   carry many links.
2. Drop its query string and fragment: share links carry per-share
   tracking (`?si=`, `?igsh=`). A `v` parameter (YouTube watch links) is
   kept.
3. For each link: if a gold label with it is processing or ready, add nothing.
   If one failed, read it again. Otherwise save a gold label (category
   `any`, no reasons) and start `analyze_gold` in the background.
4. Reply with one plain-text line for the Shortcut to show, always
   starting with `Spike:`: `Spike: saved 2. Gemini is reading them.`,
   `Spike: already a standard.`,
   `Spike: no TikTok, YouTube or Instagram link in: <first 80 characters>`,
   or `Spike: nothing arrived...`. The phone is the only place the
   Shortcut's builder sees what was sent. The Shortcut clears its queue
   only on a reply that starts with `Spike:`, so an error page
   (`tailscale serve` gives 502 while Spike is down, a 403) keeps it.

**Cross-site posts:** FastAPI 0.142 parses a body as JSON only when the
`Content-Type` is JSON. A form from another site cannot send that without a
CORS preflight, which Spike never answers, so it gets 422.

## Shortcut ("Spike standard")

1. Show in Share Sheet, receives URLs and Text. If there's no input:
   Continue (run from the Shortcuts app, it sends the queue).
2. Get File `spike-queue.txt` from the Shortcuts folder, Error If Not
   Found off.
3. Text: File, a new line, Shortcut Input.
4. Save File: that Text as `spike-queue.txt`, overwriting. The share is
   on the phone before anything is sent.
5. Get Contents of URL: `<SPIKE_PUBLIC_URL>/settings/standards/share`,
   POST, JSON body, field `text` = Text.
6. Show Notification: Contents of URL.
7. If Contents of URL begins with `Spike:`: Delete Files on Saved File,
   Confirm Before Deleting off.

**Offline queue (2026-11-11):** while Spike or the PC is off, step 5 fails
and Shortcuts stops the run (it has no error handling), so the queue file
keeps the link. The next share sends the old links with the new one.
Shortcuts' Append to Text File is not used: users report it does not
create a missing file.

The Standards card shows these steps with Spike's address filled in.

## Tests (`tests/test_labels.py`)

- Link pulled from share text, tracking dropped, `v` kept.
- Same link twice gives one label. A failed one is read again.
- Text with no allowed link adds nothing.
- A form post and a `text/plain` post are refused.
- A non-admin is refused.

## Left out

- Discord alert when a shared standard fails: the Settings card shows it.
- Picking a category from the phone: shared standards are "any stream".
