# Eval baseline: 9 Twitch VODs

Spike does not yet find the moments viewers clip. Across 9 Twitch VODs, its top 10 picks covered 13% of the 10 most-clipped moments in each VOD. A plain chat-activity baseline covered 22%, and random picks covered 11%. Spike's single top pick is better than its list: it landed on a real top moment in 5 of 9 VODs. The failure splits in two. 38% of the top moments were never proposed as candidates at all, and 49% were proposed but ranked below 10th. Both have to be fixed. Better ranking alone cannot reach the moments that were never proposed.

## How the test worked

Each VOD's Twitch community clips were frozen as the answer key before Spike ran. A clip made live ends at the moment, while a clip cut from the VOD later starts at it, so each clip was reduced to that point. Clips within 20 seconds of each other were merged into one moment, and a moment needed at least two different clippers to count. The 10 moments with the most clippers per VOD are the targets.

Spike ran its normal pipeline on the first 90 minutes of each VOD (3 hours for the Fortnite VOD) with the community clips hidden from it. It still had chat, audio and the transcript. Scoring checked whether any of Spike's top 10 picks overlapped each target moment, with a strict (±5 s) and a loose (±20 s) tolerance.

Two baselines ran on the same VODs. The chat baseline takes the 10 busiest moments by number of distinct chatters, at least 45 s apart, with no tuning. The random baseline takes 10 random 35-second windows and averages over 20 draws.

The tool is `py spike.py evalset build | run | score`, and the frozen set lives in `data/eval/`.

## Results

All figures use the loose ±20 s tolerance unless marked otherwise. "Top 10 found" counts how many of the 10 most-clipped moments Spike's or chat's top 10 picks overlapped.

| VOD | Category | Spike top pick hit | Spike top 10 found | Chat top 10 found |
|---|---|---|---|---|
| Marlon, H&M fashion show | Just chatting | Yes | 1 | 2 |
| Kai Cenat, "Leave me alone" | Just chatting | Yes | 1 | 3 |
| ohnePixel, "Explaining myself" | Just chatting | No | 2 | 1 |
| Agent00, drifting with T-Pain | IRL | No | 0 | 2 |
| YonnaJay, Texas State Fair | IRL | Yes | 4 | 2 |
| Kai Cenat, spooky night | IRL | Yes | 0 | 2 |
| ohnePixel, CS2 last stream | FPS | Yes | 2 | 2 |
| Jerma985, NoPixel | RP / sandbox | No | 2 | 4 |
| Clix, Fortnite scrims | Battle royale | No | 0 | 1 |
| **Total** | | **5 of 9** | **12 of 90** | **19 of 90** |

Averaged per category so the three-VOD categories do not dominate, recall of the top 10 is:

| Tolerance | Spike | Chat | Random |
|---|---|---|---|
| Loose (±20 s) | 0.133 | 0.220 | 0.111 |
| Strict (±5 s) | 0.080 | 0.180 | 0.073 |

Spike beat chat on 2 VODs (ohnePixel just chatting, YonnaJay), tied on 1 (ohnePixel CS2) and lost on 6.

## Where the top moments went

For each of the 90 target moments, the check was where it sat in Spike's full ranked list of candidates (50 to 129 per VOD):

| Outcome | Moments | Share |
|---|---|---|
| Never proposed as a candidate | 34 | 38% |
| Proposed, but ranked 11th or lower | 44 | 49% |
| In Spike's top 10 | 12 | 13% |

The moments that were never proposed point at where candidates come from. Spike's candidates come mostly from the transcript. In every VOD, the transcript chunk scan supplied 35 to 89 candidates, while signal peaks and crowd seeds supplied a handful. A moment that is funny because of what happens on screen, or because of how something is said, does not show up in a transcript scan. The research report predicted this failure ("Funny moment detection by creator", the section on cheap signals choosing the windows).

The moments that were found but ranked low point at the scoring. The transcript judge scores each candidate on its own, out of 100, and its scores bunch up. Many target moments sat at ranks 20 to 60 in a list of about 70. Chat's own top picks hit several moments that Spike found but buried, so the chat signal Spike already has is not carrying enough weight in the final ranking.

One part works. Spike's first pick landed on a real top moment in 5 of 9 VODs, while chat's first pick did so in 4 of 9. The judge can tell the single best moment from filler. It cannot rank the next nine.

## By category

Just chatting (3 VODs) came close to chat on average and better on one VOD. This is the category where a transcript-led pipeline should do best, and it does.

IRL (3 VODs) had the widest spread: 4 of 10 on YonnaJay, 0 of 10 on both Agent00 and Kai Cenat's spooky night. IRL moments often hinge on a stranger, a stunt or a visual surprise, which the transcript scan misses.

Gaming had one VOD per genre. Spike found nothing on Fortnite. Jerma's NoPixel RP found 2 where chat found 4. The CS2 VOD tied chat at 2. The Fortnite result matches the research: gameplay moments that nobody talks over never become candidates.

## Caveats

- The sample is small. With one to three VODs per category, a single moment moves a category's score by 0.1, so read the numbers as direction rather than precise measurement.
- Community clips are a biased label. Viewers clip more when more people are watching, and some funny moments never get clipped, so a miss against this key is not always a bad pick.
- One VOD used mixed judges. Part of Agent00's scoring ran on Claude Haiku during a Gemini quota outage and the rest on Gemini Flash-Lite. The Claude editor pass ran on all 9.
- The chat baseline uses raw chat times with no lag correction, which if anything handicaps it slightly.
- Only the first 90 minutes were processed, so late-stream moments were out of range for every arm.

## What this points to

The two failure modes map onto two changes from the detection plan, and this baseline is what they will be measured against.

1. Add candidate sources that do not depend on the transcript. Promote chat and audio peaks to full candidates instead of letting them merge into transcript windows. Then let the multimodal judge look at short windows around those peaks. This is aimed at the 38% that are never proposed.
2. Replace per-candidate scores with comparative ranking. Keep the transcript score only as a coarse filter. Rank the shortlist by comparing candidates against each other, in shuffled order, and give the chat and audio evidence real weight in that step. This is aimed at the 49% that are found but ranked low.

Each change should be run on the same 9 frozen VODs and reported as lift over this baseline, per category. A reasonable first goal is to match the chat baseline (0.22). Until Spike beats it, counting chatters does the job better than the AI pipeline.
