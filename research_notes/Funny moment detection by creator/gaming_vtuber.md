# Funny and viral moments in gaming streamer and VTuber clips: anatomy and detection signals

Scope note: the earlier report (`reports/Funny clip detection signals.md`) already covers laughter detection (YAMNet, PANNs), transcript humor judging, Gemini AV judging, YouTube heatmap and comments, fusion and boundaries. These notes cover only the gaming and VTuber specifics it skips. Research date: 2026-10-21. About 20 tool calls; several questions had thin sources, flagged under Gaps.

## 1. Which moment types dominate top clips, per genre?

### Takeaway
Across genres, the most-viewed clips are driven by the streamer's reaction and personality more than by the game or by skill. Genre changes the trigger (a kill feed event, a fall, a scare, a proximity-chat death), but the payoff is the human reaction. Only competitive FPS has a large share of pure skill clips, and even there commercial tools now weight voice reaction.

### Cited Findings
- General: Kotaku's analysis of Twitch's top 15 all-time clips (each over 1.5M views) found their viral potential "has very little to do with the game being played"; most featured big-name streamers. Dated (circa 2020), opinion plus counting. ([Kotaku](https://kotaku.com/twitchs-most-watched-clips-have-almost-nothing-to-do-wi-1842038158))
- General: Livestream Fails catalogues "anything that goes wrong on a live broadcast": misplays, technical failures, unintended reactions, ranked by score. Shows fails are a primary clip genre. ([Livestream Fails](https://livestreamfails.com/))
- General: Streams Charts' 7-day top-clip chart (Sept 2026) mixes World of Warcraft, IRL and Just Chatting; the top weekly clip had about 55,000 views. ([Streams Charts](https://streamscharts.com/clips))
- Competitive FPS and esports: EsCharts' top 2025 esports Twitch clips mix Counter-Strike plays, caster moments and fails. ([EsCharts](https://escharts.com/news/most-viewed-twitch-esports-clips-2025))
- Competitive FPS: Medal's auto-clip event lists are skill events: CS2 aces, clutches, 4K/3K, knife kills, headshots; Valorant Kill, 2K, Ace, Knife Kill. ([Medal CS2](https://medal.tv/developer/cs2); [Medal Valorant](https://medal.tv/developer/valorant))
- Competitive FPS, battle royale, tactical: Eklipse's 2026 per-genre tuning prioritizes kill density, kill feed, spray context (FPS); drop spots, zone collapse, third-party fights, victory states (BR); round economy, clutch detection, plant/defuse (tactical). Vendor claim, page modified May 26, 2026. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- Rage/platformer: Only Up! went viral with streamers in June 2023 via gameplay and fail clips; xQc's video got over 415,000 YouTube views in ten days, a Cr1TiKaL speedrun video over 2.1M. It was explicitly inspired by Getting Over It. ([Know Your Meme](https://knowyourmeme.com/memes/subcultures/only-up))
- Rage/platformer: Spanish coverage says the difficulty creates tension able to produce "all kinds of reactions" from the player; much content was also speedruns and records. 2023. ([El Pais Colombia](https://www.elpais.com.co/tecnologia/que-es-only-up-el-juego-que-esta-causando-sensacion-entre-los-streamers-1204))
- Rage/platformer: a whole content genre exists of streamers famous for rage quits. Editorial. ([Looper](https://www.looper.com/452247/streamers-who-became-famous-for-their-rage-quits))
- Horror: reaction compilations show screams, cursing and physical responses (jumping out of chair, covering face). Weak source (search summary of compilation pages). ([Glasp summary](https://glasp.ai/youtube/wKrxoau0NwE))
- Horror: jumpscares in game design are usually paired with a loud sound effect plus a sudden visual cue. ([Yahaha horror docs](https://developer.yahaha.com/horror/jumpscares/intro))
- Sandbox/social (Lethal Company, 2023): dead players are cut off from comms abruptly with no in-game warning, so last words end mid-sentence; this powers "perfectly cut screams" compilations. Acoustics make death screams sound real; distant teammates' deaths are heard like "a radio drama"; players ham it up; TikTok "was flooded with hilarious clips". Compared to Among Us and Phasmophobia. ([PC Gamer via Yahoo](https://tech.yahoo.com/general/articles/lethal-company-viral-hit-no-140028148.html); [inkl mirror](https://www.inkl.com/news/lethal-company-is-a-viral-hit-in-no-small-part-thanks-to-all-the-intense-shouting))
- VTubers: one full-time clipper (VTubers I Love, June 2023) says most of his clips are stories VTubers tell about their lives, plus funny or lewd moments; he curates for a consistent audience. ([VTuber NewsDrop](https://vtubernewsdrop.com/behind-the-model-vtubers-i-love/))
- VTubers: Maliuk (2025) frames clippers as fans who select, translate and edit notable moments from long streams; clips are entry points for new viewers and build shared in-jokes. Abstract only. ([KUBG eLibrary](https://elibrary.kubg.edu.ua/id/eprint/54533/))

### Inferences
- Moment-type map (synthesis, not measured): FPS = clutch/ace/multi-kill plus "hubris then death" and whiffs; rage = the fall plus the scream or silent despair; horror = scare plus scream plus physical flinch; sandbox/proximity = social chaos, cut-off death screams, betrayals, bugs; sports = last-minute goals, glitches, rage at the game (see gaps); VTuber = talk/story segments, reactions, and lewd or chaotic banter more than gameplay.
- "Hubris then death" (boast, then immediate death) is a cross-genre pattern that needs both transcript (the boast) and game state (the death) to detect. No source measured it.

### Gaps
- No systematic study classifying top Twitch clips or Shorts by moment type per genre. All evidence is editorial, vendor or anecdotal.
- Sports games (EA FC, NBA 2K): I found no source on clip anatomy or detection. Overwolf and Medal coverage of sports titles was not checked.
- No source quantified funny bugs or glitches as a share of sandbox clips.

## 2. Which moments are visual-only, and how large is that share?

### Takeaway
No source measures the share. The likely visual-only moments are silent skill plays (FPS), silent falls and despair (rage games), physics bugs, and sports-game glitches. In horror, proximity chat and VTuber content, the funny part is almost always audible, so a transcript plus audio tags covers most of it.

### Cited Findings
- Eklipse says its old trigger-plus-window engine had "thin signal" for games without a clear kill feed (strategy, talk-heavy, IRL, reaction), implying game-state visuals carry most of the signal in FPS and voice carries it elsewhere. Vendor, 2026. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- Eklipse's new engine reads the screen to decide where clips start and end, and recommends 1080p so the AI can read in-game text and kill feeds. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html); [Eklipse help](https://eklipse.gg/help/how-does-eklipse-ai-choose-highlights/))
- A 2016 Yahoo Esports paper used visuals only, noting that game UIs show text overlays at key moments (for example "triple kill"). ([arXiv 1611.08780](https://arxiv.org/pdf/1611.08780))

### Inferences
- For a transcript-first pipeline, the main visual-only misses are: FPS multi-kills with no callout, silent fails, and physics or ragdoll bugs. A cheap mitigation is that most streamers vocalize after these moments (scream, laugh, "no way"), so audio tags catch the aftermath; the clip start then needs extending backward to include the visual cause.
- VTuber clips are the most transcript-friendly genre, because the clipper's chosen content is mostly talk.

### Gaps
- No measured percentage of visual-only funny moments in any genre. A Phase 0 labeling pass on a few VODs per genre would answer it.

## 3. Game event detection methods

### Takeaway
There are three tiers: official or overlay event APIs (exact, live only, needs the player's PC), game-specific vision models on the VOD (what Powder, Eklipse, Medal-style tools sell, costly per game), and generic audio/visual cues (cheap, noisy). For an offline VOD clipper like Spike, live APIs do not apply; only VOD vision (kill-feed OCR, HUD text) and audio are usable.

### Cited Findings
- Overwolf GEP for Valorant exposes live events: match_start, match_end, spike_defused, spike_detonated, kill_feed, kill, assist, headshot, death, plus info updates (round_number, round_phase, score, round_report, health, abilities). No round_end event; use round_phase. match_end does not fire in custom or training matches. ([Overwolf Valorant GEP](https://dev.overwolf.com/ow-native/live-game-data-gep/supported-games/valorant))
- Overwolf also has GEP pages for CS2, Fortnite (kill, killed, killer, revived, death, assist), Overwatch, PUBG, Halo Infinite, Dota 2. ([Overwolf CS2](https://dev.overwolf.com/ow-native/live-game-data-gep/supported-games/counter-strike-2); [Overwolf Fortnite](https://dev.overwolf.com/ow-native/live-game-data-gep/supported-games/fortnite))
- Overwolf gives real-time events; Riot's API gives data only after the match, per a developer forum thread. ([Overwolf forum](https://discuss.overwolf.com/t/valorant-match-id-related-to-riot/2160))
- League's Live Client Data API runs locally at `https://127.0.0.1:2999/liveclientdata`; `/eventdata` returns events such as ChampionKill and exists only during a match. Nothing found for a Valorant equivalent. ([Go package docs](https://beta.pkg.go.dev/github.com/Jonchun/lige/liveclientdata); [lol-livegame-client README](https://cdn.jsdelivr.net/npm/lol-livegame-client@1.0.1/README.md))
- Medal: auto-detects the game, keeps a replay buffer, cuts clips on events; "most" auto-clip games use the game's replay system as a base; Streamer Mode can break detection by hiding info; Windows only. Custom games can POST events to Medal's local API. ([Medal support](https://support.medal.tv/support/solutions/articles/48001167701-what-is-automatic-event-detection-auto-clipping-); [Medal developer](https://medal.tv/developer/auto-clipping))
- Powder (TechCrunch, Nov 2023): over 40 proprietary game-specific models (Fortnite, Valorant, Apex, CoD, Rocket League, Fall Guys, Elden Ring, Among Us; CS2 coming) detect kills and wins in Twitch/YouTube/MP4 recordings; laughter detection existed; yelling detection was due mid-December 2023; "Community Hype" detects chat spikes. ([TechCrunch](https://techcrunch.com/2023/11/20/powder-an-ai-clipping-tool-for-gaming-can-detect-when-a-creator-yells-during-a-stream))
- A later competitor blog says Powder's universal game support used shouts and volume spikes "as a rough stand-in for a kill feed". ([GameClipper Advanced](https://gameclipperadvanced.com/blog/powder-gg-alternatives/))
- Eklipse Gameplay Intelligence (Premium from June 1, 2026): routes by game metadata into five buckets (FPS, BR, MOBA, tactical, strategy/non-action), weighs game-state events, audio composition (streamer voice vs in-game vs background), on-screen action density and continuity. Old engine failures: Discord yelling, long voice lines, and hype at events that did not happen created false clips; fixed windows cut the setup. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- A third-party comparison claims Eklipse has deep game-specific CV models for roughly 30 to 50 games. Unverified. ([Two Average Gamers](https://www.twoaveragegamers.com/eklipse-vs-opusclip-head-to-head-for-gaming-streamers-2026/))
- Academic: MediaEval 2018 CS:GO killstreak extraction found inaccurate tournament metadata timestamps made detection "almost unusable", a warning about trusting event logs for alignment. ([MediaEval 2018 paper 43](https://ceur-ws.org/Vol-2283/MediaEval_18_paper_43.pdf))
- Academic: Ringer et al., "Autohighlight" (Machine Learning with Applications, 2022) detects LoL esports highlights from crowd-sourced data; Ringer's York PhD thesis (2022) builds multimodal highlight detection for personality-driven livestreams and esports using audio, visual and chat. I could not open the full text (PDF too large, server unreachable). ([Autohighlight PDF](https://repository.cyi.ac.cy/bitstream/CyI/1884/1/Autohighlight%20Highlight%20detection%20in%20League%20of%20Legends%20esports%20broadcasts%20via%20crowd-sourced%20data.pdf); [York thesis](https://etheses.whiterose.ac.uk/32406/))
- Academic, audio: a 2026 comparative study of audio for sports highlight detection exists, and Costa et al. combine YAMNet audio with commentary transcripts (validated on SoccerNet, aimed at esports too). ([arXiv 2609.17923](https://arxiv.org/pdf/2609.17923))
- Older baseline (from the earlier report, still relevant): Fu et al. 2017 LoL study, chat alone 43.2 F vs video 72.2. ([ACL 2017](https://aclanthology.org/D17-1102.pdf))

### Inferences
- Overwolf and Medal events only exist when software runs on the streamer's PC during play. Spike processes VODs after the fact, so these are references for event taxonomies, not usable inputs, unless a streamer exports Medal/Overwolf event logs (not researched).
- Kill-feed OCR on the VOD is the only game-state source for FPS that fits Spike. It is per-game (feed position, icons), breaks with Streamer Mode and custom overlays, and needs 1080p. Cost and accuracy were not found.
- Game audio events (gunshot bursts, round-end stingers, death sounds) are per-game too; generic YAMNet classes (Gunshot, Explosion) exist but would fire constantly in shooters. Better as density features than triggers.

### Gaps
- No public accuracy numbers for Powder, Eklipse or Medal detection.
- No open-source kill-feed OCR project with published accuracy was found in this pass.
- Whether Medal/Overwolf event logs can be exported alongside a VOD was not researched.

## 4. How facecam reaction and voice combine with gameplay; reaction vs skill

### Takeaway
Vendors moved from game events alone to game events plus voice reaction, and the only multimodal horror study uses face plus voice plus narration. Direct evidence that reaction, not skill, makes clips funny is editorial (Kotaku), not experimental.

### Cited Findings
- "The Scream Stream" (Xylakis, Liapis, Yannakakis, ACII Workshops 2024) extracted surprise, fear and arousal from Outlast let's-play streamers' facial expressions, voice and verbal narration, and matched them to level design. Dataset on OSF; results not on the project page. ([Project page](https://antoniosliapis.com/projects/project_scream_stream.php))
- Eklipse separates streamer voice from in-game audio so it can tell "a frustrated scream from a clutch reaction". Vendor. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- Eklipse warns that English-tuned audio analysis can misclassify other languages, and background music at voice level degrades separation. ([Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- Powder's CEO frames the goal as capturing "the emotion of playing games". ([TechCrunch](https://techcrunch.com/2023/11/20/powder-an-ai-clipping-tool-for-gaming-can-detect-when-a-creator-yells-during-a-stream))
- A Steam game (驚いたら負け) uses microphone input to detect a startled player, showing scream/startle detection from voice is practical. ([Steam](https://store.steampowered.com/app/4698630/_/))

### Inferences
- A useful fused pattern: game event (death, fall, scare sound) followed within about 0 to 3 s by a voice spike (scream, laugh, shout). The event gives the start anchor, the reaction gives the "funny" label. This is an inference from the vendor designs, not tested.
- Discord or teammate voice is a known false-positive source; sandbox/proximity content is all teammate voice, so speaker separation matters more there.

### Gaps
- No experiment comparing skill clips vs reaction clips on views or retention.
- No measured facecam (expression or motion) contribution to gaming highlight detection was found; the Ringer thesis may contain it but could not be read.

## 5. VTuber signals, chat culture, length and subtitle norms

### Takeaway
VTuber clippers lean on talk content and chat reaction. JP chat laughter markers (草, w, www) are used by at least one chat-highlight tool, but no research validates them. Translated clip culture includes long-form clips (5 to 20 minutes) alongside short gags, and agency rules cap clip share.

### Cited Findings
- An Apify actor built and tested on Japanese VTuber streams extracts chat peaks from YouTube live chat replay, with 草 and w as examples, and shifts timestamps 15 s earlier by default because chat lags the moment. Paid, little usage history, unverified. ([Apify actor](https://apify.com/hitokawa/youtube-livechat-highlights.md))
- Eklipse watches chat velocity such as sudden waves of "POG" or "KEKW"; Powder has Community Hype for chat spikes. ([Eklipse help](https://eklipse.gg/help/how-does-eklipse-automatically-create-clips/); [TechCrunch](https://techcrunch.com/2023/11/20/powder-an-ai-clipping-tool-for-gaming-can-detect-when-a-creator-yells-during-a-stream))
- Clip length: VTubers I Love often makes about five-minute highlights, his most popular run up to 20 minutes, and says stories "can't be cut down to 30 seconds"; shorter clips suit quick funny moments; clips should be snappy and end on a punchline; trimming dead air helps. June 2023. ([VTuber NewsDrop](https://vtubernewsdrop.com/behind-the-model-vtubers-i-love/))
- Agency rules: a subber site says Hololive guidelines allow clipping at most about 25% of a stream and that subtitled clips fall under the same rules. Secondhand; verify against hololive.tv. ([Good VTuber Subs](https://goodvtubersubs.com/guidelines))
- A freelance clipper offers English subtitles only for English streams and charges extra for translation. One person's policy. ([Aobashizuu](https://aobashizuu.carrd.co/))
- A creator surveyed clippers about building auto-dubbing of JP VTuber clips into English, a sign that translation is the workflow bottleneck. ([Tally survey](https://tally.so/r/pbDxJJ))

### Inferences
- For VTubers, avatar expression tracking is weak, so chat (with JP and EN laughter lexicons: 草, w/www, kusa, LMAO, KEKW, and streamer-specific emotes) plus voice laughter and transcript should carry detection. Lexicon matching is cheap and fits Spike's `chat_hype`.
- Translated clips need subtitles burned in, which makes the transcript a required output, not just a detection input. JP transcription quality would then gate the clip.
- VTuber clip length is bimodal: under 60 s gags for Shorts, and multi-minute story clips for long-form channels. A single length target fits poorly.

### Gaps
- No sources from r/VirtualYoutubers or r/Hololive surfaced in search; community norms are unverified.
- No research on 草/www density as a highlight predictor, nor on EN vs JP chat behavior differences.
- No data on how VTuber clippers find moments in practice (tools, chat replay, timestamps from viewers).

## 6. Clip length and setup norms per genre

### Takeaway
Length follows the moment type: instant skill plays are 5 to 8 s, setup-heavy plays 20 to 40 s, and story clips run minutes. Fixed windows cut setup, a failure vendors now name explicitly.

### Cited Findings
- Eklipse: clean no-scope 5 to 8 s; round-deciding play with setup 25 to 40 s (help page); examples of a no-scope at about 6 s and a 1v4 clutch with comeback at about 22 s (blog); old engine used fixed 15 to 30 s windows that cut setup. ([Eklipse help](https://eklipse.gg/help/how-gameplay-intelligence-picks-moments/); [Eklipse blog](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html))
- Generic platform heuristics: Vizard treats under 30 s as TikTok/quick highlights; another tool targets 25 to 60 s. Not gaming-specific. ([Vizard docs](https://docs.vizard.ai/docs/basic))
- VTuber story clips: 5 to 20 minutes (see section 5). ([VTuber NewsDrop](https://vtubernewsdrop.com/behind-the-model-vtubers-i-love/))
- Chat lags the moment; one tool shifts back 15 s. ([Apify actor](https://apify.com/hitokawa/youtube-livechat-highlights.md))

### Inferences
- Suggested per-genre defaults (inferred, to tune): FPS skill 6 to 25 s; FPS hubris-death 15 to 40 s (boast included); rage fall 15 to 45 s (start before the climb section is lost); horror 10 to 30 s (a few seconds of quiet tension before the scare); proximity chat 20 to 60 s; VTuber gag 15 to 60 s, VTuber story 1 to 10 minutes for long-form.

### Gaps
- No sourced per-genre length norms for rage, horror, sandbox or sports clips. No retention data by length per genre.
