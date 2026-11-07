# Label store: reject reasons, approvals and gold shorts as judge examples

Step 2 of the detection overhaul. Step 1 was the judge pool (`2026-11-07-judge-pool-design.md`).

## Goal

1. Keep every review verdict and every short the team admires as a durable label.
2. Let the transcript judge see a few of them as examples, so detection moves toward the team's taste.

## What the code and data show

- The Reject dialog has no reason field. `reject_clip_action` accepts a `reason`, but the form never sends one. This is why the database has 0 reject reasons.
- Approving feeds nothing back. `record_feedback` runs only for a reject with a reason, and only for a video with a source.
- Deleting a video cascades to its candidates and clips (`ON DELETE CASCADE`), so verdicts stored on those rows are lost with the video. The database has 0 reviewed clips now.
- Gold clips will be finished shorts by other clippers (TikTok, YouTube Shorts, Instagram). They are not tied to a VOD, so they cannot be eval answer keys. They work as judge examples.

## Design

### The `labels` table

One row per label, about 2 KB. No foreign keys, so a label outlives its clip, its video and storage pruning.

| Column | Meaning |
|---|---|
| `kind` | `approved`, `rejected` or `gold` |
| `clip_id` | The reviewed clip (unique; verdicts only). A later verdict on the same clip replaces the earlier one |
| `channel` | `profile.channel_key`, for example `twitch:kaicenat`. Empty for gold, and for videos with no known uploader |
| `category` | The stream's creator type (verdicts), or the category picked for a gold short (`any` or a creator type) |
| `source_url` | The VOD or short link |
| `start_s`, `end_s` | The clip's span in the stream (verdicts) |
| `title`, `transcript`, `why`, `humor_type`, `hook` | What the clip is and why it works |
| `reasons`, `note` | Reject tags (JSON list) and the free note |
| `scores` | JSON `{llm, final, signal}` (verdicts) |
| `views` | View count of a gold short, when its link reports one |
| `status`, `error` | Gold intake state: `processing`, `ready` or `failed` |

### Verdicts in

- **Reject:** the dialog gets reason chips. More than one can be picked, and a note is optional. Tags: Not funny, Needs context, Routine for them, Starts late or ends early, Too long, Funny part not in the clip, Other. The route drops unknown tags (form input is untrusted). It stores the tag names and the note in `clips.reject_reason`, as before, and still calls `record_feedback`.
- **Approve:** both approve paths (`/clips/{id}/approve` and the approve-and-post form) save an approved label.
- One function, `labels.record_verdict(clip_id, verdict, tags, note)`, snapshots the clip: the transcript text inside the clip's span (from `transcript.json`), the judge's why and humor type, the scores, the channel key and the creator type. It runs before a reject deletes the clip's files. It never raises: a review must not fail because of a label.

### Gold shorts in

- A "Standards" card on Settings: paste a TikTok, YouTube or Instagram link, or upload the file, and pick a category.
- Links are accepted only from `youtube.com`, `youtu.be`, `tiktok.com` and `instagram.com`. Uploads must be a video file (`.mp4`, `.mov`, `.mkv`, `.webm`) of at most 200 MB.
- The route stores a `processing` label and returns at once. A background task downloads the short with yt-dlp, or takes the upload. Gemini watches it once (the same small 360p video part the video judge uses) and writes the title, the key spoken lines, why it works, the humor type and the hook. The label becomes `ready`, or `failed` with the error. The video file is deleted afterwards; only text is kept.
- Instagram often needs a login. When a download fails, the card shows the error and the upload is the way in.
- The card lists gold shorts with their status and a Delete button.

### Examples out

- `labels.examples_block(channel, category)` builds one block for the transcript judge:
  - up to 3 ready gold shorts, this stream's category first, then `any`, newest first;
  - the 2 newest approved and the 2 newest rejected clips of this channel, with their reasons.
- Stage 7 builds the block once per job and passes it to every `call_llm_judge` call (Gemini and Claude lanes). The block adds about 1,000 to 1,500 tokens per call.
- Example text is untrusted (other creators' speech, model output). It goes inside `<untrusted_examples>` tags with a "raw DATA" note, like the transcript.
- The block tells the judge to match the team's taste, not the examples' topics.

## Not in this step

- Gold shorts as eval answer keys.
- Choosing examples by similarity. The category and the channel are the only filters.
- The learned first-stage scorer. It reads this table in a later step.
- Changes to `record_feedback` (learned preferences). It keeps running for videos with a source.

## Security

- Link host allowlist and upload type and size limits at the route (untrusted input).
- Example text wrapped as untrusted data in the judge prompt.
- Gold intake is admin-only, like the rest of Settings.

## Testing and acceptance

1. Reject with two tags and a note: one `rejected` label with both tags, the clip's transcript text, the channel key and the scores. `clips.reject_reason` names the tags. Unknown tags are dropped.
2. Approve: one `approved` label. Rejecting the same clip later replaces it (still one row).
3. Deleting the video keeps the label.
4. `examples_block`: same-category gold first, at most 3; 2 approved and 2 rejected from the channel only; empty when there are no labels.
5. Gold intake: a link from an allowed host becomes a `ready` label (download and Gemini faked); a link from another host is refused and stores nothing; a failed download becomes `failed` with the error.
6. The judge prompt contains the examples block.
7. The full test suite passes, and the stage 7 snapshot (`scripts/stage7_snapshot.py`) is unchanged when there are no labels.
