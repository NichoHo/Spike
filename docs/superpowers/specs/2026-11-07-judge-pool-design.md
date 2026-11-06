# Judge pool: parallel LLM calls across Gemini and Claude

Step 1 of the detection overhaul. Later steps: label store, eval chat and replay, learned first-stage scorer, batched judge.

## Goal

1. Make stage 7 faster without a change to the results.
2. Keep a job running when Gemini is unavailable. Do not wait for Gemini, and do not move the whole job to Claude.

## What the data shows

- Stage 7 takes a median of 71 min per job (16 runs in `stage_timings`). That is about 80% of the job time.
- All stage 7 LLM calls run one at a time, with a 2 s pause before each call.
- A 90-min slice makes about 22 chunk calls, 2 judge calls for each of 55 to 140 moments, and 12 video calls.
- Most Gemini 503 errors are short. `data/eval_worker.log` has 98 503 retries across 251 judged moments, and 0 calls that failed after all retries. The re-run logs have 1 to 19 retries per ~600 judge lines.
- A 503 that lasts through all 4 retries skips the moment. When more than 25% of moments are skipped, the job fails.
- Claude is slow and uses your Pro plan. On Oct 22, 80 judge calls ran on Claude Haiku. Each call took about 2.3 min and used 14.1k input and 6.2k output tokens on average. The total was $4.16 at API prices.

## Design

### Two lanes, one queue

- Stage 7 puts its text calls into one queue: the chunk calls and the per-moment judge calls.
- The **Gemini lane** has 3 worker threads. Each worker takes the next task and calls Gemini with the existing retries.
- The **Claude lane** has 1 worker thread. It calls Claude Haiku through `run_claude`.
- One task is one moment. The worker that takes a moment does all of its judge runs on its own provider. A moment never gets one score from Gemini and one from Claude.
- On Claude, a moment gets one run, not two. The research report shows that the average of two runs adds little.
- The workers take tasks in a shuffled order (seed: the video id). The shuffle gives each provider a random sample of moments, not one part of the stream.
- After the queue is empty, stage 7 uses the results in the original candidate order. The steps after the judge do not change.

### When Claude helps

A new setting on the Settings page, "Claude help for the judge", has three values:

| Value | What happens |
|---|---|
| When Gemini is down (default) | The Claude lane takes tasks only while the Gemini lane is down |
| Always | The Claude lane takes tasks all the time, next to Gemini |
| Off | Claude never judges. The Gemini lane waits for Gemini |

The Gemini lane is **down** when a task fails all its retries with 503 or "unavailable", or when Gemini's daily quota is used up. A down lane puts the task back at the front of the queue. Then it waits 60 s and sends one probe call. Each failed probe doubles the wait, to a maximum of 5 min. A successful probe brings the lane back up.

### Approval, limits and pause

- The per-call approval popup is not used for pool tasks. Instead, the first time Claude helps in a job, `claude_fallback.ask` shows one popup for the job. "Deny" stops the Claude lane for that job. "Don't ask again today" works as it does now.
- The sidebar Pause button stops the Claude lane. A paused call puts its task back in the queue.
- `CLAUDE_LANE_DAILY_CAP = 100` (in `config.py`) limits Claude lane calls per day. This protects your Pro plan, which your own Claude use shares. At the cap, the Claude lane stops.
- When no lane can run, the queue waits for Gemini. After 30 min with no progress, the job fails with a clear message, as it does now.
- Pool calls to Gemini do not start the old Claude fallback inside `generate_content_with_retry`. A new `allow_claude=False` argument switches it off.

### Fair ranking with two judges

- Each judged moment stores `judge_model`, for example `gemini-3.1-flash-lite` or `claude-haiku`. A new nullable `judge_model` column in `candidates` holds it. The judge cache entry stores it too.
- The ranking blend uses the percentile of `text_score` within each `judge_model` group, not across all moments. Because of the shuffle, each group is a random sample, so its percentiles are fair.
- The keep or reject verdict does not change. The eval can check later whether Claude keeps more or fewer moments than Gemini.
- The `MIN_RAW_LLM_SCORE` floor applies to the video judge's score, and that judge is always Gemini. So the floor needs no change.
- Exception: when no moment was watched, the floor applies to text scores. With this design, that happens only when the clip video cannot be fetched. This step does not change that case.

### Video judge

- Claude cannot watch video, so the video judge stays on Gemini.
- The 12 video calls run on the Gemini lane workers, 3 at a time.
- When the Gemini lane is down, video tasks wait for it. They do not skip as they do now. The 30 min limit applies.

### Claude call size

- Claude lane calls use the real response schema (`LLMJudgeResponse`, with `require_all`), not the loose `{"type": "object"}` schema.
- Claude used 6.2k output tokens per judge call on Oct 22, which is much more than the answer needs. A strict schema should make calls shorter and faster. The cold run (see Acceptance) measures this.

## Not in this step

- Batched or comparative judging. That is step 5.
- A second Gemini model as the first fallback. Add it later if the logs show that 503s affect one model at a time.
- Claude judging video from still frames. Frames lose the audio, which the video judge needs.
- The whole-stream read and the editor pass. Each is one call, so they stay as they are.

## Files

- `src/judge_pool.py` (new): the queue, the two lanes, and the down/probe state.
- `src/pipeline/stage7_moments.py`: send chunk, judge and video calls through the pool. Use per-model percentiles in the blend.
- `src/config.py`: worker counts, `CLAUDE_LANE_DAILY_CAP`, the 30 min limit.
- `src/db.py`: the `judge_model` column.
- `src/web/routes/settings.py` and its template: the "Claude help for the judge" select.

## Testing and acceptance

1. `tests/test_judge_pool.py`, with fake providers:
   - Gemini fails for a period in the middle of the run. All tasks finish, and the results come back in the original order.
   - In the default mode, Claude takes tasks only while Gemini is down.
   - With Claude off and Gemini down past the limit, the pool raises the job error.
   - Per-group percentiles: two groups with different score scales give the same order inside each group.
2. `scripts/stage7_snapshot.py` runs stage 7 on one frozen eval VOD with a fixed fake judge (answers from a hash of each window) and no live calls. Its output before and after the change is the same. This proves the change does not alter results. (The saved judge answers cannot do this check: they use the v2 prompt, and the current judge uses v3, so a replay would call the LLM for every moment.)
3. One cold run on one eval VOD. Report the stage 7 time against the 71 min median, and the count of 503s, 429s and Claude calls.
4. The full test suite stays green (328 passed before this change).

## Risks

- The free tier may not allow 3 parallel Gemini calls. A 429 backs off as it does now. If the cold run shows many 429s, use 2 workers.
- Worker threads write the Gemini budget counters to SQLite. These writes must stay under the existing `gemini_budget` lock, to prevent "database is locked" errors.
- Claude may keep more or fewer moments than Gemini. `judge_model` makes this measurable in the eval.
- Transcript text stays untrusted data in both lanes. The prompts and the empty working folder for Claude do not change.
