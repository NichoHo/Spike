# Funny / viral moment anatomy and detection signals for talk-centric creators (podcasts, stand-up, sports talk, educational, panels)

Scope note: the earlier report (`reports/Funny clip detection signals.md`) already covers UR-FUNNY, FunnyNet-W, StandUp4AI, MHD, YAMNet/PANNs, Whisper laughter tags, LLM humor-judge weakness, YouTube heatmap, and OpusClip complaints. These notes add what it lacks: group/overlapping laughter, spontaneous (no-audience) humor data, clip boundary and editing evidence, and sports-rights handling. Research run 2026-10-21. Tool budget was tight (Firecrawl rate-limited mid-run), so several questions remain gaps, listed explicitly.

## 1. Which moment types dominate viral clips per category

### Takeaway
No source analyzed top Shorts from Flagrant, H3, Theo Von, Impaulsive, JRE, or Diary of a CEO. The available evidence is practitioner opinion: confrontation or bold opinion, genuine laughter, vulnerability, and self-contained context. Sports watchalongs are sold on "unfiltered" rants and reactions. No measured per-category breakdown of moment types was found.

### Cited Findings
- Practitioner guides name bold or controversial viewpoints, genuine laughter, and vulnerability as the strongest clip candidates. One claims that when a guest challenges the host (or vice versa) "audio energy spikes" and these exchanges have the highest emotional engagement (opinion, no data). — [Podshop guide 2025](https://www.podshoponline.co.uk/the-ultimate-guide-to-podcast-clips-that-go-viral); [listenerstoclients](https://listenerstoclients.com/blog/the-science-of-viral-podcast-clips-a-proven-framework-for-high-impact-content); [repurposeyourcontent](https://www.repurposeyourcontent.com/blog/how-to-make-viral-podcast-clips)
- Guides agree a clip must stand alone: viewers "shouldn't need to have heard the full episode" (opinion). — [repurposeyourcontent](https://www.repurposeyourcontent.com/blog/how-to-make-viral-podcast-clips); [Reap blog](https://reap.video/blog/ai-video-editing-for-podcasters)
- Sports watchalong style is described as "unfiltered, provocative, and authentic". Mark Goldbridge (1.41M subscribers) is credited for comedic, analogy-packed rants. No moment-level performance data (WSC Sports blog, 2025-09-09, vendor). — [WSC Sports](https://wsc-sports.com/blog/industry-insights/stream-react-repeat-turning-watchalong-moments-into-a-content-pipeline/)
- OpusClip-style scoring is described by users as weighting hooks, complete thoughts, emphatic language, and "questions and their punchlines" (third-party description, not OpusClip documentation). — [techsy.io](https://www.techsy.io/en/blog/how-to-make-podcast-clips-with-ai); [kompozy](https://kompozy.io/ai-podcasting/clip-detection-podcasts)
- Spontaneous humor is sparse. In Bundesliga coach press conferences (a sports-talk analogue with no comedy intent), only about 6% of 2-second segments were humorous, versus at least 24% in scripted datasets (TED, sitcom, stand-up). — [Passau-SFCH, arXiv 2209.14272v3 (rev. 2024)](https://arxiv.org/html/2209.14272v3)
- Provine's field observations: only about 10 to 20% of conversational laughter followed anything resembling a joke. Most followed ordinary remarks (popular-press summaries of Provine's 2000 book, primary paper not checked). — [Discover](https://www.discovermagazine.com/whats-so-friggin-funny-16028); [APA Monitor 2006](https://www.apa.org/monitor/jun06/laughing)

### Inferences
- Category anatomy, as a hypothesis to test (not sourced as measured):
  - (a) comedy podcasts: roast, group laughter breakdown, absurd story payoff.
  - (a) interview podcasts: guest's surprising answer, hot take, quotable line.
  - (b) stand-up: setup and punchline, where audience laughter is ground truth.
  - (c) sports: live reaction to a goal or bad call, debate hot take.
  - (d) educational: counterintuitive claim plus payoff explanation.
  - (e) panels: crosstalk escalation that ends in group laughter.
- The Provine and Passau-SFCH findings mean that in podcasts most laughter is social, not a reaction to a joke. A laugh detector alone over-triggers there. It needs gating by strength, by how many speakers laugh, or by an LLM check of the preceding line.

### Gaps
- No source measured which moment types dominate top Shorts on the named channels. Answering this needs a scrape and hand-labeling of the top 50 Shorts per clip channel (the Firecrawl youtube-com `channel_shorts` capability exists but was not run, and popularity ordering is not confirmed).
- No sourced data was found for educational/commentary clip anatomy.

## 2. Detectable signals: group laughter, turn-taking, prosody, lexical, setup-punchline

### Takeaway
Overlapping (shared) laughter is acoustically distinct and measurable. It is longer, higher-pitched, louder, and more voiced, and it gets stronger as more people join. Listeners join about 500 ms after the first laugh. That makes "multi-speaker laughter intensity and duration" a stronger funny label than any single laugh, especially in panels. Laughter duration has been used as an intensity label, and models predict it to about 0.6 s MAE.

### Cited Findings
- Overlapping laughs are "stronger prosodically marked" than solo laughs: higher duration, mean F0, mean and max intensity, and more voicing. The effect grows with the number of people joining. Group size increases the amount of overlapping laughter (contagion). People join a laugh about 500 ms after it starts (Truong and Trouvain, Interspeech 2012, older than the preferred window but the primary source). — [ISCA archive](https://www.isca-archive.org/interspeech_2012/truong12b_interspeech.html)
- Provine's "punctuation effect": laughter falls almost only at phrase breaks, not mid-utterance. Speakers laughed about 46% more than listeners ("more likely" or "more frequently" depending on the summary, primary not checked). — [APA Monitor](https://www.apa.org/monitor/jun06/laughing); [Vice](https://www.vice.com/en/article/a-scientist-spent-decades-studying-laughter-and-found-something-weird-about-humans/)
- Laughter duration has been used as a humor intensity label. On Friends (16,710 clips), audience laughter was auto-labeled with Gillick's detector (minimum 0.2 s, 80% confidence). The 10 s before each laugh was the humorous context. Text-only BERT got 62% accuracy and BERT+HuBERT got 78%. Laughter-duration regression (BERT+VGGish) got about 600 ms MAE (Alnajjar et al., 2022). — [Helsinki repository PDF](https://helda.helsinki.fi/bitstreams/ebd13670-4d9c-4cd5-83a8-607352f1d5dd/download)
- In stand-up, laughter "frequently follows an utterance, occurring either immediately afterward or slightly within the pause between utterances". The label window runs to the next subtitle pause, or to the subtitle end plus 0.7 s if the pause is under 0.2 s. Vocals were removed with a vocal-remover before detecting crowd laughter. Laughter detection F-score was 77% (English) and 71% (Russian). Text-only BERT got 69.2% (EN) on humor classification. Visual features helped most (Kuznetsova and Strapparava, LREC-COLING 2024). — [ACL Anthology](https://aclanthology.org/2024.lrec-main.1037.pdf)
- In spontaneous sports-talk humor (Passau-SFCH, 11 h, 59 Bundesliga press conferences), face video was the strongest modality (AUC about .90). Text (ELECTRA) got about .80 and audio (Wav2Vec2) about .75. Fusion reached about .92. Annotator agreement was low (Krippendorff alpha about .16 to .19). — [arXiv 2209.14272v3](https://arxiv.org/html/2209.14272v3)
- Classic transcript approach: the Laughbot (Stanford) built punchlines from Switchboard phone calls, defining a punchline as an utterance followed by laughter. — [Laughbot PDF](https://cs.stanford.edu/~katepark/Laughbot.pdf)
- Podcast laughter is speaker-specific enough to support speaker verification. Haha-Pod (2023) extracted laughter clips for over 240 speakers from podcasts with a semi-automatic pipeline. This implies laughter can be attributed to a speaker with embeddings. — [arXiv 2309.14109](https://arxiv.org/abs/2309.14109)
- An annotation guide for laughter in multi-party conversation exists (perceptual and contextual features), not read in full. — [Academia.edu](https://www.academia.edu/116530233/Annotation_guide_for_laughter_in_multi_party_conversation)

### Inferences
- A cheap "group laugh" proxy without full diarization:
  - laughter run length over about 1 to 1.5 s,
  - higher laugh-class probability with louder intensity,
  - and, where a stereo or multi-track podcast exists, laughter on two or more channels within about 0.5 to 1 s.

  This follows Truong and Trouvain's duration, intensity, and 500 ms join findings. The thresholds are guesses to tune.
- Punctuation effect: a speaker laughing at their own phrase end is common and weak evidence. A listener (other speaker) laughing right after a turn ends is stronger evidence. Diarization of only the candidate windows (not the whole VOD) is enough to tell these apart.
- For no-audience solo creators (educational, solo commentary), laughter is rare and weak. Lexical cues and the LLM judge carry more of the signal there, as Passau-SFCH's sparse spontaneous humor suggests.
- In face-on-camera podcasts, video face features could matter more than in prior evidence: they were the top modality in Passau-SFCH and the stand-up dataset. This contrasts with the earlier report's view that visual adds little. The difference is likely real faces in frame versus gameplay.

### Gaps
- No source measured interruption or overlapping-speech rate (crosstalk) as a predictor of clip-worthiness. The "guest challenges host, energy spikes" claim is opinion.
- The "pause before punchline" prosody evidence was not re-examined here. The earlier report already flags it as contested (Pickering 2011).
- No 2021 to 2026 paper was found on humor detection on podcasts specifically, with laughter as label. Haha-Pod is about speaker verification, not humor.

## 3. Setup length, start/end choice, jump cuts, and hook evidence

### Takeaway
Typical podcast clips run about a minute: the average OpusClip podcast clip on YouTube was 58.5 s across 308,462 clips (April 2026). That is a descriptive figure, not an optimum. Pro advice is to start at a clean sentence boundary, trim 1 to 3 s off the start, sometimes move the payoff line to the front, and never end before the answer. The one controlled experiment on cuts found that moderate pacing helps and more cutting hurts sustained engagement. So jump-cutting every pause inside a story is not supported.

### Cited Findings
- OpusClip public YouTube dataset (April 2026): podcast clips averaged 58.5 s (n = 308,462) and were 10.7% of categorized clips, the largest category. The source warns this does not show the duration caused better reach or retention. — [Bytecap research page, updated 2026-07-17](https://www.bytecap.io/research/podcast-clips-benchmarks)
- Practitioner: clips of 45 s to 1:20 "do really well" (anecdote). Mux's clipping workflow defaults to 30 to 60 s candidates. — [Podshop](https://www.podshoponline.co.uk/the-ultimate-guide-to-podcast-clips-that-go-viral); [Mux docs](https://www.mux.com/docs/prompts/podcast-clips)
- Boundary failures: AI clips "start or end a beat too early". Nudge in/out to a breath or sentence boundary. AI sometimes leads with setup instead of payoff, so the strongest line should be moved to the opening seconds. — [marcandrews.com, 2026](https://marcandrews.com/how-to-use-opus-clip-for-youtube-shorts-2026-guide/)
- A Shorts guide author "almost always" shaves 1 to 3 s off the start to tighten the hook (opinion). — [marcandrews.com](https://marcandrews.com/how-to-use-opus-clip-for-youtube-shorts-2026-guide/)
- Named problems in podcast clips: "cutting just before the answer" and "ending before the example". — [Reap blog](https://reap.video/blog/ai-video-editing-for-podcasters)
- Hook: "the first 1 to 3 seconds decide whether someone keeps watching" (practitioner consensus). A "65% higher engagement for 3 s hooks" figure attributed to Meta has no traceable source, so treat it as unverified. — [Whop guide](https://whop.com/blog/what-is-content-clipping/); [Podshop](https://www.podshoponline.co.uk/the-ultimate-guide-to-podcast-clips-that-go-viral)
- Practical hook test: mute and watch the first 3 s, then watch with sound. If neither version grabs, re-cut (opinion). — [BlitzReels](https://blitzreels.com/blog/podcast-clips-maker)
- Controlled experiment on cuts (Dost and Huang, Marketing Trends Congress 2026). N = 242 viewers, a 2x3 design, seven variants of one 20 s talking-head clip.
  - Seamless cuts (pauses removed with continuity kept) raised likes over the unedited and overlapping versions.
  - Overlapping cuts (deliberate continuity breaks) improved completion and rewatch, but the benefit shrank as cut frequency rose.
  - Higher pacing lowered sustained engagement overall.
  - Their advice: seamless cuts at moderate pace for likes, overlapping cuts at low pace for completion. (Details come from a search summary. The PDF text could not be extracted, so verify before citing exact effects.) — [Paper PDF](https://archives.marketing-trends-congress.com/2026/pages/PDF/paper_professor_DOST_HUANG.pdf)
- Vendor jump-cut and silence-removal pages claim retention lifts without data. — [OpenClip glossary](https://openclip.app/learn/jump-cut); [Klap](https://klap.app/blog/jump-cut-definition)
- Instagram's "First Draft" tool (2026) auto-trims dead air into a rough Reel. Podcast-focused commentary warns that podcast clips "live or die" on choices automated trimming can miss. — [Poddster](https://www.poddster.com/blog/instagram-first-draft-reel-editing-podcast-clips)
- Research label windows for setup: 8 s before laughter (FunnyNet-W, in the earlier report) and 10 s before laughter (Alnajjar 2022, above). These are training windows, far shorter than the roughly 60 s clips practitioners publish. — [Helsinki PDF](https://helda.helsinki.fi/bitstreams/ebd13670-4d9c-4cd5-83a8-607352f1d5dd/download)

### Inferences
- Use two different windows: a short window (8 to 10 s before the laugh) to detect and score, and a longer window (about 30 to 80 s, sentence-bounded) to publish. The published clip starts at the sentence that opens the setup.
- For a story-payoff clip, "hook first" and "keep the setup" conflict. One option is a cold-open: put the payoff line (or a 1 to 3 s teaser) at the front, then play the setup and payoff in order. This is common practitioner advice but untested here.
- Jump cuts: tighten dead air (long silences) with continuity-preserving cuts. Do not strip pauses right before a punchline or before a laugh, since comic timing and the 0.5 s laugh join window live there. This is inferred from Truong and Trouvain and from the Dost and Huang pacing ceiling.

### Gaps
- No public retention-curve data was found for talk clips (first-3-s drop-off, average view duration by clip length). YouTube Studio data from a creator's own channel would resolve it.
- No primary documentation from a clipping agency or from OpusClip, Riverside, or Descript on start/end rules was fetched. OpusClip's help center is the next source to check.
- Loop endings (clip ends where it starts) were not covered by any source found.

## 4. Live-audience laughter vs no-audience podcasts: how the label changes

### Takeaway
With a live audience (stand-up, studio, TED), crowd laughter is a reliable and dense label that follows the line almost immediately, and it can be isolated by removing the vocals. Without an audience, laughter comes from the participants themselves. It is sparse for real humor, mostly social, and speakers laugh at their own lines more than listeners do. So the label must shift to listener and group laughter, and to non-laughter signals (face, text, annotation).

### Cited Findings
- Audience-laughter datasets label the line just before the laugh: the 10 s window on Friends and the utterance-to-pause window in stand-up. Laughter detection on crowd audio reaches 71 to 77% F. — [Alnajjar 2022](https://helda.helsinki.fi/bitstreams/ebd13670-4d9c-4cd5-83a8-607352f1d5dd/download); [Kuznetsova and Strapparava 2024](https://aclanthology.org/2024.lrec-main.1037.pdf)
- Vocal removal before laugh detection separates crowd laughter from the performer's voice (stand-up). — [LREC 2024](https://aclanthology.org/2024.lrec-main.1037.pdf)
- For spontaneous talk, Passau-SFCH deliberately removed audience-laughter segments and used human continuous annotations, noting that "laughter doesn't necessarily imply humor". Agreement was low and positives only about 6%. — [arXiv 2209.14272v3](https://arxiv.org/html/2209.14272v3)
- In conversation, speakers laugh more than listeners (about 46%), and most laughter is not joke-driven. — [APA Monitor](https://www.apa.org/monitor/jun06/laughing); [Discover](https://www.discovermagazine.com/whats-so-friggin-funny-16028)
- Shared laughter grows with group size and intensity. Panels and multi-host podcasts therefore produce stronger, more detectable laugh events than 1-on-1 interviews. — [Truong and Trouvain 2012](https://www.isca-archive.org/interspeech_2012/truong12b_interspeech.html)

### Inferences
- Label rules by setting (a design proposal, not tested):
  - Live audience: laugh onset marks the punchline end, and laugh duration is the intensity.
  - Multi-host, no audience: count laughter from at least one non-speaking participant, weighted by how many join and for how long.
  - 1-on-1 interview: laughter weight is low. Lean on the LLM judge for surprising answers and hot takes, plus emphatic prosody.
  - Solo creator: near-zero laughter weight.
- Applause or "applause break" in stand-up and live shows is a separate label for strong lines (AudioSet has an Applause class). Not researched here.

### Gaps
- No study compares the predictive value of host self-laughter versus guest laughter for clip performance.

## 5. Sports content: reaction as the moment, and game feed rights

### Takeaway
The goal reaction is the clip, but the match feed is the liability. Watchalongs are legal reaction streams only when they do not show the broadcast. Content ID flags live sports footage within minutes. The licensed exception is rights-holder deals, such as AFL watchalongs that integrate official vision. So for sports, a clip should be built from the creator's camera and audio, with detection from the creator's reaction, not from the game feed.

### Cited Findings
- A watchalong is "a curated reaction stream", not the game. The common workaround is to watch the official broadcast on a separate TV or phone, so the stream is "the pub table". YouTube Content ID reportedly flags live broadcast footage within minutes, and restreaming is not covered by fair use (blog guide, 2026, not legal advice). — [KeepTheScore World Cup 2026 guide](https://keepthescore.com/blog/posts/world-cup-2026-watch-party/)
- Licensed route: the AFL ran a creator watchalong that integrates official AFL match vision into the live stream. — [AFL.com.au](https://www.afl.com.au/news/1556693/tonight-at-8pm-aest-the-ultimate-footy-watchalong)
- Rights holders enforce strictly, from the Premier League's 2007 legal action against YouTube to its threats against pirates. — [SVG 2007](https://www.sportsvideo.org/2007/05/08/premier-league-gets-kicks-out-of-youtube-lawsuit/); [Pinsent Masons](https://pinsentmasons.com/out-law/news/premier-league-threatens-to-sue-internet-pirates)
- Rights holders are moving toward creators. CazéTV has a FIFA agreement to stream all 104 matches of the 2026 World Cup. Vendors now pitch auto-generated "real-time creator reaction cuts" to rights holders (WSC Sports, 2025-09). — [WSC Sports](https://wsc-sports.com/blog/industry-insights/stream-react-repeat-turning-watchalong-moments-into-a-content-pipeline/)
- iShowSpeed headlined the YouTube FIFA Creator Cup (July 2026), while US 2030/2034 World Cup rights are being bid on. The article does not say how creator footage rights are handled. — [Tubefilter 2026-07-08](https://www.tubefilter.com/2026/07/08/youtube-world-cup-broadcast-rights-i-show-speed-fifa-creator/)
- iShowSpeed has been accused by others of abusing copyright claims against reuploaders of his content (community allegations, unverified). — [Reddit r/Asmongold](https://www.reddit.com/r/Asmongold/comments/1dy5ncb/ishowspeed_abusing_youtube_copyright_strike_again/)
- Passau-SFCH shows sports-talk humor can be detected from the speaker's own face and speech, with no game footage. — [arXiv 2209.14272v3](https://arxiv.org/html/2209.14272v3)

### Inferences
- For sports, the signals are a sudden shout or scream onset (AudioSet Shout/Yell/Screaming), a jump in loudness, fast speech, standing or leaping motion, and chat spikes. The output should crop to the facecam or creator camera and mute or blur any broadcast audio and video region.
- Detection from the game feed (score change, crowd roar in the broadcast audio) would locate goals well, but rendering that feed into the clip is a rights risk. Use it at most as a timing hint, never in the output.
- Broadcast commentary audio leaking into the creator mic can trigger Content ID. Audio source separation, or a policy to warn the user, may be needed (inferred, not verified).

### Gaps
- No source documented how pro sports clip channels (Speed clip channels, First Take or Undisputed clip accounts) handle feed rights in practice. Debate shows own their studio footage, so they likely differ from watchalongs, but this was not sourced.
- No sources were found on moment types for sports debate shows (hot take, heated exchange, meltdown).
