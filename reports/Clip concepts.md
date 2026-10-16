# Clip concepts: POV, Story, Top N

Research date: 2026-10-14. Scope: how to make each non-single concept funny.
Single clips are covered by `Funny clip detection signals.md`.

**Evidence quality.** Peer-reviewed work exists for why reaction memes and
captions are funny (incongruity, relatability, aptness). Nothing peer-reviewed
covers POV clips, story edits, or countdowns on short-form platforms. Those
rules come from clipping-tool blogs and meme-format writeups, and from
judgment. Treat them as hypotheses. Post stats (Phase 7) decide.

---

## 1. POV (out-of-context reaction plus an unrelated caption)

### What it is

The caption is NOT about the clip. It names an everyday situation the
viewer knows. The clip is a streamer's reaction, shown with no context, used
as the face the viewer would make in that situation. Example (written for
this report): caption "POV: you said 'one more game' 4 hours ago", clip of
Speed screaming after conceding.

### Why it is funny (sourced)

- Reaction memes use a decontextualized image as a stand-in for how the
  viewer feels in a situation. They work through irony and the viewer
  identifying with the scenario (Methodological Directions for the Study of
  Memes).
- Relatability drives humor mostly through aptness: how well the image fits
  the situation (Wong and Holyoak 2021, two online studies). Memes join a
  source and target from distant domains, which creates incongruity and
  surprise (same paper, framing, not a tested variable).
- Meme humor often comes from moving media into a new context, a surprising
  juxtaposition (Memes-as-Replies, arXiv 2602.15842).
- The humor is the gap between what the footage really is and the label on
  it (POV explainer writeups). Specific captions work; vague ones fall flat.

So the formula: **funny = apt emotion match x distance between domains x
specific, relatable situation.** FIFA rage and a group project are far
apart. The emotion (betrayed fury) fits both exactly. That is the joke.

### Rules for the reaction clip

- One clear, universal emotion that reads in under 1 s from the face and
  voice: fury, despair, disbelief, panic, smug joy, hysterical laughing,
  slow realization. Facecam visible.
- 4 to 12 s. Starts 0.3 to 0.5 s before the reaction peak, so the change
  of face is on screen. Ends at the end of the outburst. Loop-friendly: the
  last frame can cut back to the first without a jump in energy.
- Few context words. Reject segments where the speech names the game, a
  player, a team, chat, or a donation. Those words break the illusion.
  Non-verbal audio (screams, laughs, "NO NO NO", "BRO") is best.
- No speech captions by default. The POV caption is the only text. The
  original audio stays.
- Baseline behaviors are the best source. Plain rage that is too common for
  a single clip is ideal POV material.

### Rules for the caption

- Formats: `POV: you ...`, `me when ...`, `when ...`, `nobody: / me:`,
  `my mom when ...`, `the teacher when ...`. Prefer the first two.
- One specific, everyday situation with a concrete detail. The audience is
  mostly 13 to 25: school, homework, group projects, parents, siblings,
  curfew, Wi-Fi, phone battery, gym, part-time job, gaming with friends,
  texting, sleep.
- Max 10 words. Readable in about 1 s.
- Must NOT describe the clip, mention the streamer, the game, or anything
  in the footage. If a viewer could guess the caption from the clip, it is
  wrong.
- The emotion in the caption's situation must match the reaction's emotion.
  Mismatch kills aptness.
- No punching down, no slurs, no real private people, no tragedy,
  no self-harm or mental-illness jokes.

### Making it reliably good (AI is weak at one-shot jokes)

1. **Caption bank.** The user pastes captions they saw and liked into a
   bank (`data/pov_bank.json`, one entry per caption, with the emotion it
   fits). Spike never scrapes Instagram or TikTok (their terms forbid it).
   Short phrases are generally not protected by copyright in the US
   (recalled: US Copyright Office Circular 33, verify). Exact reuse is the
   user's choice per clip. Default is to generate new captions in the
   style of the bank.
2. **Generate many, pick one.** The LLM writes 10 captions for the clip's
   emotion: 5 adapted from the closest bank entries (few-shot), 5 new. A
   second call scores each on aptness (does the face fit the situation),
   relatability (has most of the audience been there), specificity, and
   surprise (distance from the footage), 1 to 5 each, and returns the top 3.
   The UI shows all 3; the top one is the default.
3. **Emotion label first.** Before captions, the model names the one
   emotion the reaction shows. Captions are written for that emotion only.

---

## 2. Story (setup, then payoff later in the stream)

### What it is

Two or three moments from the same stream, in time order, where the first
makes the last funny. The common shape is hubris then fall (instant karma):
a brag, prediction, or promise, then the opposite happens.

### Why it is funny (sourced)

- Setup and payoff: an early element exists only to matter later. It works
  across scenes, not just inside one (storytelling reference).
- For gaming clips the face carries the punchline: gameplay is the setup,
  the face is the payoff (OpenClip clipping guide, a blog).
- "Subtle foreshadowing" edits show a flash of the fall first, then play
  the setup in order. The non-linear cut is the joke and makes viewers
  rewatch (No Strategy newsletter, describing a TikTok trend).
- Irony: the payoff contradicts the setup. The bigger and more confident
  the claim, the better the fall.

### Rules

- Setup must be a clear, quotable claim: a brag ("I'm literally
  thrashing"), a prediction ("easy win"), a promise ("I won't rage"), or a
  dare. Max 8 s. Cut everything around it.
- Payoff must contradict the claim directly, and show the reaction.
- Time-skip card between segments, 1 s, plain text: "3 goals later",
  "10 minutes later". Uses the real elapsed time or event count.
- Callback: during the payoff reaction, show the setup quote on screen
  ("'I'm literally thrashing'") for 1.5 s. It makes the irony land for
  viewers who skipped the setup.
- Optional foreshadow open: a 0.6 s flash of the payoff's peak before the
  setup. Use when the setup is calm and the hook would be weak.
- Hook text frames the irony without spoiling it: "He was SO confident".
- Total 20 to 45 s. 2 segments preferred, 3 only when the middle step
  escalates (first goal against, then the loss).

---

## 3. Top N (themed countdown)

### Top 3 or Top 5?

**Default Top 3. Allow Top 5 only when 5 strong entries share one theme.**

- No study compares the two on short-form (searched, none found).
- Fewer items means fewer transition points where viewers swipe away, and a
  shorter total, which helps completion (inference, not sourced).
- Listicle tools aim at 30 to 60 s for Shorts (vendor claim). Top 3 at
  8 to 15 s per entry fits; Top 5 needs very short entries.
- One stream rarely has 5 strong moments on one theme. A weak #5 or #4
  costs more viewers than it adds.
- Top 5 fits a full match or a long episode with many reactions, like the
  #38 Kvaratskhelia match (4 goals and the loss).

### Rules (sourced from vendor blogs, then judgment)

- One theme, stated in the title: "Every goal Kvaratskhelia scored on
  Speed". Random "best moments" lists do not work.
- Each entry needs a reason to be on the list. The rank card label says it,
  in a viewer's voice: "#2 he blamed the controller".
- Tease #1 in the first 1.5 s, with hook text. Viewers stay for the #1
  reveal (Social Media Examiner, VueReka).
- Escalate: weakest first, #1 last. Every entry must still be good on its
  own. Never pad.
- Entries 6 to 15 s (Top 3), 6 to 12 s (Top 5): setup plus payoff, no
  lead-in. Totals: Top 3 at most 60 s, Top 5 at most 100 s.
- End right after #1's reaction. A cut from #1 back into the tease loops
  cleanly, and listicles loop well (prepublish.ai guide).
- Same layout for all entries. Loudness matched per entry. Hard cuts.

---

## Sources

- Methodological Directions for the Study of Memes:
  https://www.researchgate.net/publication/354533192_Methodological_directions_for_the_study_of_memes
- Wong and Holyoak 2021, Cognitive and motivational factors driving sharing
  of internet memes: https://link.springer.com/article/10.3758/s13421-020-01134-1
- Memes-as-Replies (arXiv 2602.15842): https://arxiv.org/pdf/2602.15842
- Funniness, Offensiveness, and Relatability in Internet Memes (pilot, n=50):
  https://www.researchgate.net/publication/364651020_Exploring_Funniness_Offensiveness_and_Relatability_in_Internet_Memes_A_Pilot_Study_and_Literature_Review
- POV meaning writeup: https://synonymsvault.com/pov-mean/
- Socialkit POV format guide: https://socialk.it/en/blog/pov-content-format-guide
- Setup (storytelling): https://en.wikipedia.org/wiki/Setup_(storytelling)
- OpenClip gaming clipping: https://openclip.app/clipping/gaming-clipping
- Eklipse clipper guide: https://blog.eklipse.gg/streaming-tips/beginner-guide/how-to-become-a-clipper.html
- No Strategy, subtle foreshadowing: https://nostrategy.substack.com/p/no-strategy-1-subtle-foreshadowing
- Social Media Examiner, Shorts hooks and curiosity loops:
  https://www.socialmediaexaminer.com/youtube-shorts-hooks-and-curiosity-loops-that-explode-your-views/
- Revid listicle generator (vendor): https://www.revid.ai/tools/ai-listicle-generator
- Prepublish Shorts retention guide: https://prepublish.ai/guides/youtube-shorts-retention
- VueReka compilation formats: https://vuereka.com/blog/youtube-video-ideas-for-compilation-channels
