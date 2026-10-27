# Read the dialogue first, then weight by genre

Spike should detect clippable anime moments with **one general pipeline whose weights and judge prompt are conditioned on the show's genre tags**, not with separate per-genre pipelines. **Scope: change clip selection only.** The user's own anime Short (section 3.1) already uses Spike's current render (`letterbox` layout, `letterbox_style = "title"`, hook question on the white title card, `bold_pop` captions), and the user wants that format kept. Stage 9 does not change. The strongest detector for the reference target (TeamFourStar's 32 s "A Win is a Win | Buu Bits" Short, about 4.6M views, published 2023-09-16) is a **transcript or subtitle LLM judge that finds a complete setup-and-punchline exchange**. Loudness, motion, cut rate and laughter detectors mostly miss that kind of quiet dialogue joke. Research on highlight detection shows that models trained on one category transfer poorly to another, but a shared model plus a conditioning signal (category, query or user) matches or beats separate per-category models. Spike's existing LLM judge already plays that role. Genre tags from AniList give a modest prior (a 0.8 to 1.2 multiplier per clip archetype), and a "dub, abridged or parody" flag must override them, because Dragon Ball Z is tagged Action but its abridged clips are comedy. The $0 path works with local signals alone (subtitle or Whisper text, YAMNet audio classes, scene cuts, AniSkip OP/ED skip times), and free-tier Gemini adds a text judge and a short video check for a few cents of paid-tier value per episode. **Spike must not auto-post raw anime clips.** Anime output must default to local files only, and posting must require a per-title allowlist entry backed by written permission or a published rights-holder guideline.

This report is written for an implementer. Sections 1 to 4 give the answer and the evidence. Sections 5 to 9 give the exact pipeline, parameters, formulas, JSON shapes and build order. Labels: **[V]** means a source verified this in the research notes. **[I]** means an inference or design choice from the research. **[R]** means recalled from training data and not checked; verify it before you rely on it. **[D]** means a starting default with no source number; tune it with the eval set in section 8.

## 1. One conditioned scorer beats per-genre pipelines

The highlight-detection literature splits into three designs, and the evidence ranks them clearly. A single unconditioned model is worst. Separate per-category models do well only when each category has its own labelled training data. A shared model with a conditioning input does as well as or better than per-category models, without needing per-category labels.

The cross-category penalty is real and large. In an ICCV 2021 study, a model trained on surfing videos and tested on dog videos scored **0.485 mAP, against 0.708 for a model trained on dog videos**, and a domain-adapted shared model recovered most of the gap at 0.649 ([arXiv 2108.11770](https://arxiv.org/html/2108.11770v1)). The authors say that highlights of one category "may be nuisance" for another. An AAAI 2023 paper argues for one model for all classes, while it admits that the shared model "does not gain the best performance in some specific categories" ([AAAI 2023](https://ojs.aaai.org/index.php/AAAI/article/view/25462/25234)). Its per-category TVSum scores ranged from 0.730 to 0.911 for one model, so difficulty varies a lot by category. QVHighlights reframed the task as query-dependent: one model, and a natural-language query says what counts as a highlight ([QVHighlights, NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf)). The cleanest evidence for conditioning comes from PHD-GIFs: conditioning a shared model on a user's history "substantially improves" accuracy, even with one example, and it **outperforms training one model per user** ([arXiv 1804.06604](https://arxiv.org/html/1804.06604v2)).

Commercial clippers reached the same design. OpusClip 3.0 added a "Genre-Specific Curation Model" where the user picks a genre and the curation approach changes ([OpusClip blog](https://www.opus.pro/blog/opusclip-clip-different)). Eklipse fuses game events, audio spikes and chat into one score, "with highlight detection tuned for each game category" ([Eklipse](https://eklipse.gg/)). Neither vendor publishes its per-genre weights. Independent testers say OpusClip's virality score "ranks clips well and predicts nothing" and works poorly outside continuous speech ([Techpresso review](https://academy.techpresso.co/reviews/is-opus-clip-worth-it)).

**Decision for Spike [I]:** build one anime pipeline. Condition it in three places: (a) the LLM judge prompt gets the show's genre tags and an archetype list, (b) a per-archetype show prior multiplies the final score within 0.8 to 1.2, and (c) the low-level signal fusion uses an archetype profile (action signals for fights, dialogue signals for jokes). Genre changes should be small for the judge, which already reads content, and larger for loudness and motion, which help action and mislead in comedy. Spike already has this shape for Twitch: `CREATOR_PRESETS` in `src/config.py` multiplies stage 6 weights within 0.5 to 2. None of the cited benchmarks contain anime, so the transfer of these numbers to anime is an inference. No anime highlight benchmark exists.

## 2. The clip archetype predicts performance better than the genre tag

Public per-genre view statistics for anime Shorts do not exist. Channel samples from the research show a clear pattern anyway. TeamFourStar (4.47M subscribers) Shorts are abridged parody dialogue beats. In the 48 most recent Shorts, Yu Yu Hakusho Abridged clips got **66K to 1M views** (most 110K to 310K) and Sailor Moon Abridged clips got 347K to 1.1M ([TeamFourStar channel](https://www.youtube.com/user/TeamFourStar)). Crunchyroll's 48 most recent Shorts got **5.4K to 35K views** each ([Crunchyroll Shorts](https://www.youtube.com/@crunchyroll/shorts)). The gap mixes brand, audience and English dialogue, so it is not a clean genre effect [I]. The titles tell the more useful story. TFS titles are punchline or meme phrases ("Skill Issue", "Because We're Blondes!"). Crunchyroll's clips from action and dark-fantasy shows are still framed as comedy or reaction beats ("Getting Roasted by Your Own Daemon Sidekick", "Subaru Needed That SLAP"), and romance clips are framed as relationship beats.

Two conclusions follow [I]. First, across genres, the hook is usually a comedic or emotional reaction. Pure spectacle (sakuga fight animation) is the one archetype tied mostly to action shows. Second, the audio track can override the show's genre. DBZ is tagged Action/Adventure, but its abridged dub produces comedy clips. Official dubs with joke-heavy localization behave the same way. So Spike needs a source override, not only a genre lookup.

Use these eight archetypes everywhere (judge output, priors and signal profiles) [I]:

| Archetype id | What it is | Main detector | Supporting signals |
|---|---|---|---|
| `comedy_beat` | Setup and punchline in dialogue or a visual gag | LLM text judge | Dense exchange, short pause after punchline, shout, SFX sting. Low motion is fine |
| `iconic_line` | A short quotable line people repeat | LLM text judge | Title-match prior, comment quotes |
| `fight_sakuga` | High-effort action animation | Motion and cut-rate signals | Loud audio, music, impact flashes, few words |
| `transformation` | Power-up, reveal of a form, big attack call | Loudness ramp plus shout | Brightness change, leitmotif, scream in transcript |
| `emotional` | Tearjerker, sacrifice, reunion | LLM judge | Soft music, crying, slow cuts, low motion |
| `twist_reveal` | Plot reveal | LLM judge | Music stop or sting, close-ups. Flag spoilers, do not boost |
| `romance_wholesome` | Confession, blush, sweet beat | LLM judge | Two-person dialogue, soft music, confession words |
| `cringe_reaction` | Exaggerated reaction, awkward silence | LLM judge | Abrupt silence, shout |

## 3. Why the reference Short is invisible to loudness and motion

The reference Short is "A Win is a Win | Buu Bits (DragonBall Z Abridged)" by TeamFourStar: 32 seconds, about 4.6M views, published 2023-09-16. The coordinator verified these facts through YouTube oEmbed and page data. The research notes did not find it in the 48 most recent TFS Shorts, and nobody in the research watched it, so its exact dialogue is not known. Per the brief, it is a self-contained comedic dialogue exchange with a punchline, from an English parody dub of an action anime. The title is very likely the quoted punchline line [I].

The table below scores each candidate signal against this clip. "Finds" means the signal would put the clip in the candidate list or rank it high.

| Signal | Finds the reference? | Reason |
|---|---|---|
| Transcript or subtitle LLM judge | **Yes, strongly** | The joke is in the words. A full exchange with setup and punchline inside 32 s is the exact pattern the judge rubric rewards [I] |
| Dialogue exchange window generator | **Yes** | Several short alternating lines, then a short final line and a pause, is the shape of a dialogue joke [I] |
| Title-match prior (viral clip titles matched to transcript lines) | **Yes, for this show** | "A Win is a Win" is itself a line. Matching titles of known Shorts to transcript text would land on it [I]. The YouTube Data API makes this legal and cheap (section 6) |
| YouTube heatmap or timestamped comments on the full abridged episode | Probably | Viewers replay and quote famous lines. Not tested [I] |
| Shout and Yell probability (YAMNet) | Partly | Dub comedy shouts often, so this can lift the punchline second. It also fires on every fight [I] |
| Gemini video verdict (pass 2) | Yes, as a check | It hears delivery and timing, which matter for humor ([FunnyNet-W](https://arxiv.org/html/2401.04210v1)) |
| Loudness (RMS, LUFS) and voice jump | **No** | Loudness overlaps heavily between highlight and non-highlight clips even in sports, and "loudness alone is insufficient" ([arXiv 2609.17923](https://arxiv.org/html/2609.17923)). A quiet joke sits below any fight |
| Motion, cut rate, optical flow | **No** | Dialogue scenes in anime use limited animation and held frames, so motion is low exactly where the joke is [I] |
| Music swell | No | Comedy dialogue is speech-dominant with little music [I] |
| Laughter detector | No | Anime has no laugh track. Laughter is diegetic (characters laugh), so it is weak evidence [I] |
| AniList genre prior without override | **Works against it** | DBZ's Action tags would boost fights over jokes. The parody override fixes this |
| AniSkip OP/ED lookup | Not applicable | Abridged parodies have no MAL ID, so AniSkip returns nothing [I] |
| Danmaku (Bilibili, Niconico) | No | No coverage for Western fan parody [I] |
| CLIP or SigLIP frame embeddings | No | The punchline is in the words, not in a frame [I] |

The lesson is direct. **If Spike ranks anime by loudness and motion, it will miss the best-performing clip type.** The transcript judge must be the primary ranker for dialogue archetypes, and the low-level signals must be archetype-gated. An Eklipse-style event and audio-spike detector misses "subtle highlights" for the same reason ([WayinVideo](https://wayin.ai/blog/eklipse-alternative/), a competitor claim).

### 3.1 The user's own Short: keep the format, improve the pick

The user's clip is "Piccolo takes way too long to charge his attack!" on the user's channel DragonSoulClips ([YouTube](https://www.youtube.com/shorts/SzeKL5Hd3m8)). Facts checked through YouTube oEmbed and page data on 2026-10-27 [V]: 21 to 22 s long, published 2026-10-27, 12 views at check time, hashtags `#animecomedy #dbzabridged #dragonball #dragonballz`, description "Goku fends of Raditz while piccolo charges an attack for 5 whole minutes!". The thumbnail frame shows Goku holding Raditz's tail with the caption word "TAIL!". It was posted the same day, so its view count says nothing about performance yet. Use it as the **format and taste reference**, and the TFS Short as the performance reference.

What the frame shows, mapped to Spike's existing render settings [V for the code, read in `src/pipeline/stage9c_render.py`, `src/pipeline/title_card.py`, `src/pipeline/stage9b_captions.py`]:

| What the clip shows | Existing Spike setting | Anime mode must |
|---|---|---|
| Full 16:9 frame in the middle, white bars above and below | `layout = "letterbox"`, `letterbox_style = "title"` (white `pad` plus `render_title_card`) | Use these as the anime defaults. Do not add a new layout |
| Black question text on the top white bar: "Why do anime attacks take forever?" | The title card text comes from `cand["hook_text"]` (falls back to `cand["title"]`) | Fill `hook_text` from the anime judge (see section 5.5, step 2) |
| Big yellow outlined word under the video ("TAIL!") | `caption_style = "bold_pop"` (Impact, uppercase, spoken word turns yellow) | Keep `bold_pop`. Feed it Whisper words (dub) or pseudo-word timings from subtitle cues (sub) |

What this clip teaches about **selection** [I]:

1. **The joke is a trope, not a line.** The hook names a well-known anime trope (attacks that take forever to charge). The funny part is the situation: a fight goes on while another character charges. This is a `comedy_beat` inside an action scene. A pure dialogue-exchange generator can miss it if the lines are short shouts with long gaps, and a pure action profile ranks it as a generic fight. So the judge must be told to look for trope moments, and the generators must not drop fight scenes that contain dialogue (see the `ANIME_GUIDE` and the mixed-scene rule in section 5.5).
2. **The hook is a question to a stranger, not a quote.** "Why do anime attacks take forever?" works for people who never watched DBZ. This matches the existing `hook_text` field rule in `src/models.py` ("3 to 8 word funny summary of what happens in the clip, not a quote"). Keep that rule for anime. A question or a trope observation is the preferred hook form.
3. **Short and tight.** About 21 s. The clip starts in the middle of the action. Dialogue clips of 12 to 30 s should score at least as well as 30 to 60 s clips; do not pad toward the 60 s maximum [D].
4. **Copyright still applies.** The clip uses DBZ footage on the user's own channel. The section 4 rules (local-only by default, allowlist to post) apply to it the same way.

## 4. Copyright: Spike must not auto-post raw anime clips

This section sets hard defaults. It is not legal advice.

The platforms let the rights holder decide. YouTube Content ID lets the owner **block, monetize or track** a matched video, and the choice can differ by country ([YouTube Help](https://support.google.com/youtube/answer/2797370)). Spike cannot see that choice before posting. YouTube's Shorts monetization policy excludes "unedited clips from others' movies or TV shows" ([YouTube Shorts monetization](https://support.google.com/youtube/answer/12504220?hl=en)). TikTok requires "proper authorization or legally valid reason" and may "immediately ban any account in cases of severe copyright violations" ([TikTok Copyright Policy](https://www.tiktok.com/legal/page/global/copyright-policy/en)). YouTube's fair use page says that credit lines and "no infringement intended" are myths, that a claim can happen "even if you only use a few seconds", and that fictional works weigh against fair use ([YouTube fair use](https://support.google.com/youtube/answer/9783148)).

Enforcement on anime is active and harsh. In Japan, three uploaders of edited "fast movie" cuts of films were convicted in 2021 ([CODA](https://coda-cj.jp/en/news/177/)), and the Tokyo District Court ordered **500 million yen** in damages against two of them in 2022 ([CODA](https://coda-cj.jp/en/news/177/)). Their added narration did not save them. Japan has no fair use. Its quotation exception (Article 32) requires the quoted part to be subordinate to the user's own work ([Monolith Law](https://monolith.law/en/?p=58999)). An auto-cut highlight with captions is neither. In September 2026, anti-piracy firm Remove Your Media struck anime reaction channels, removing over 60 videos from one channel, and its lawyer said "commentary, in this context, does not make the use transformative" ([Dexerto](https://www.dexerto.com/youtube/anime-youtuber-says-channel-faced-deletion-after-copyright-strikes-removed-60-videos-3408486/)). Even TFS, the reference creator, had its main YouTube channel terminated over third-party copyright claims at one point ([Attack of the Fanboy](https://attackofthefanboy.com/news/teamfourstars-dragon-ball-z-abridged-series-no-longer-available-on-youtube/)). TFS owns its script and voices, not the Toei footage [I].

Lawful paths exist but they are narrow. KADOKAWA publishes per-title secondary-use guidelines (for one show, up to 4 minutes of TV footage, with exclusions) ([Oricon US](https://us.oricon-group.com/news/5546/4/), snippet only). A creator posting its own work, as TFS does with its Shorts, is the lawful pattern. Clipping for a rights owner who commissions it is lawful for that owner's material [I].

**Safe defaults Spike must ship with [I]:**

1. Add a source kind `anime_episode`. For this kind, the auto-post path is disabled in code, not only in the UI. Rendered clips go to `data/videos/<id>/renders/` and stay local.
2. Posting an anime clip requires an allowlist entry for that title, stored in `data/anime_allowlist.json`. Each entry needs a `basis` of `written_permission` or `published_guideline` and an `evidence_url` or a stored permission file. Without a matching, unexpired entry, the post button is hidden and the API refuses.
3. The allowlist entry limits the clip: `max_clip_s`, allowed `platforms`, and `monetization_allowed`. Spike checks these before posting.
4. Reposting another creator's work (for example TFS) needs that creator's written permission. That follows Spike's existing rule for creators. It still carries the underlying footage risk.
5. A single batch of infringing posts can endanger the whole account, including the user's lawful Twitch clips, because YouTube reviews reused content channel-wide ([YouTube monetization policies](https://support.google.com/youtube/answer/1311392), snippet) [I]. Show this warning in the anime UI.
6. Spike must not download from pirate sources or strip DRM. Input is a local file the user supplies or an official upload URL [R for the Japanese private-use and DRM rules].
7. Sending episodes to Gemini free tier: Google may use free-tier data to improve its products [R]. Show a one-line notice and let the user choose paid tier or local-only.

Allowlist entry shape:

```json
{
  "anilist_id": 813,
  "title": "Example Show",
  "basis": "published_guideline",
  "evidence_url": "https://example.com/guideline",
  "permission_file": null,
  "max_clip_s": 60,
  "platforms": ["youtube"],
  "monetization_allowed": false,
  "expires": "2027-12-31",
  "notes": "Guideline excludes film footage"
}
```

## 5. The anime pipeline, mapped onto Spike's stages

The pipeline keeps Spike's nine stages. Most anime work lands in stages 1, 4, 5, 6 and 7. Stage 3 (chat) is skipped for local episodes. The table is the map, and the subsections give the exact steps.

| Stage | File | Anime change |
|---|---|---|
| 1 meta | `stage1_meta.py` | Resolve the show (AniList, MAL id), episode number, dub or sub, parody flag, allowlist status. Write `anime.json` |
| 2 audio | `stage2_audio.py` | No change. Also extract text subtitle streams to `subs/` with ffmpeg |
| 3 chat | `stage3_chat.py` | Skip for local files. Optional danmaku is off by default (ToS risk) |
| 4 crowd | `stage4_crowd.py` | AniSkip skip times. YouTube comment timestamps for an official upload of the same episode. Viral Short titles for the title-match prior |
| 5 transcribe | `stage5_transcribe.py` | Text-track priority: English subs, then dub Whisper, then Japanese ASR plus LLM translation |
| 6 signals | `stage6_signals.py` | Add skip mask, music and speech probability, scream and explosion, scene cuts, motion, exchange windows, punchline gaps |
| 7 moments | `stage7_moments.py` | Anime candidate generators, anime judge prompt and JSON, show prior, archetype signal profiles, boundary snapping, Gemini video check |
| 8 sections | `stage8_sections.py` | No change (local slicing with padding) |
| 9a face track | `stage9a_face_track.py` | Not used for anime (layout is fixed to `letterbox`) |
| 9b captions | `stage9b_captions.py` | No code change. Keep `bold_pop`. Feed it subtitle cues for sub clips. Skip captions if the source is hard-subbed |
| 9c render | `stage9c_render.py` | No code change. Source defaults only: `letterbox` + `title` style, `cut_pauses = "off"` (section 5.6) |

### 5.1 Stage 1: identify the show and set source flags

Steps:

1. Parse the filename for title and episode number. Let the user override with fields `anilist_id`, `episode`, `audio_kind` (`dub`, `sub`, `abridged`) and `hardsubbed`.
2. Query AniList GraphQL. Endpoint: `POST https://graphql.anilist.co`, JSON body, no API key for reads ([AniList docs](https://docs.anilist.co/guide/graphql/queries/media)). Query:

```graphql
query ($id: Int, $search: String) {
  Media(id: $id, search: $search, type: ANIME) {
    id
    idMal
    title { romaji english }
    format
    episodes
    duration
    genres
    isAdult
    tags { name rank category isMediaSpoiler isAdult }
  }
}
```

`MediaTag.rank` is the tag's relevance "out of the 100 for this media" ([AniList MediaTag](https://docs.anilist.co/reference/object/mediatag)) [V]. The field `idMal` is [R]. Rate limit: 90 requests per minute normally, currently "degraded" to 30 per minute, with a 1-minute timeout when exceeded ([AniList rate limiting](https://docs.anilist.co/guide/rate-limiting)) [V]. Spike needs one call per show, so cache the result forever in `data/anime_cache/<anilist_id>.json`.

3. Fallback when AniList fails: Jikan `GET https://api.jikan.moe/v4/anime/{mal_id}/full`. It returns genres, explicit genres, themes and demographics ([Jikan docs](https://docs.api.jikan.moe/)). Limit 3 per second and 60 per minute per secondary docs ([animedex](https://animedex.readthedocs.io/en/latest/tutorials/raw_passthrough.html)). The base URL is [R].
4. Set `parody = true` if the user set `audio_kind = abridged`, or AniList has a `Parody` tag with rank at least 50 [D], or the file or channel name contains "abridged" (case-insensitive).
5. Set `dub = true` if `audio_kind = dub`, or the default audio stream language tag is `eng` (read with `ffprobe -show_streams`).
6. Look up the allowlist (section 4). Store `post_allowed` and the limits.
7. Write `data/videos/<id>/anime.json`:

```json
{
  "anilist_id": 813, "mal_id": 813, "title": "Dragon Ball Z", "episode": 12,
  "genres": ["Action", "Adventure", "Comedy"],
  "tags": [{"name": "Shounen", "rank": 90, "category": "Demographic", "isMediaSpoiler": false}],
  "audio_kind": "abridged", "dub": true, "parody": true, "hardsubbed": false,
  "post_allowed": false, "allowlist": null
}
```

(The ids in the example are placeholders. Do not hardcode them.)

### 5.2 Stage 2 and 5: get the best text track

The text track drives the main detector, so pick it carefully. Priority order [I]:

1. **English text subtitles** (embedded or sidecar `.ass`, `.srt`, `.vtt`), only when the audio is Japanese (sub). Extract with ffmpeg: `ffmpeg -i in.mkv -map 0:s:<n> subs/<n>.ass`. Image subtitles (PGS, VobSub) cannot become text. ffmpeg silently drops non-UTF-8 sidecars, so detect the charset and write a UTF-8 copy first ([intro-skipper analysis](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)) [V].
2. **English dub audio through faster-whisper.** Stage 5 already runs faster-whisper `small` int8 on CPU with word timestamps. That is the $0 default. If the user's CPU allows, `large-v3-turbo` int8 gives better text [R]. For a dub, prefer Whisper over the subtitle file, because dub subtitles ("dubtitles") often do not match the dub script [I].
3. **Japanese audio with no English subs:** transcribe with `litagin/anime-whisper` (13.0% average CER on anime and game speech, against 16.5% for whisper-large-v3) ([anime-whisper card](https://huggingface.co/litagin/anime-whisper)) [V]. Do not set an initial prompt: the author warns that it causes hallucination and severe quality loss [V]. Qwen3-ASR-1.7B ranked best in a small 2026 benchmark (CER 0.140); kotoba-whisper ranked worst on emotional speech ([Neosophie benchmark](https://neosophie.com/en/blog/20260226-japanese-asr-benchmark)) [V, small sample]. Then translate to English inside the LLM judge call (one call does both) [I]. Loading anime-whisper in faster-whisper needs a `ct2-transformers-converter` step [R]. A Japanese CER of 13 to 18% is fine for finding candidates and not fine for captions.

Subtitle cleaning before any scoring [I]:

1. Strip ASS override tags (`{\...}`) and collapse whitespace, so multi-line cues read as one line.
2. Drop sign and typesetting lines: style name matches `/sign|title|op|ed|kara|romaji|song|insert/i`, or the line contains `\pos(` and is not in the main dialogue style. Song-style lines (with `\k` karaoke tags) mark OP and ED bounds for free [R].
3. Pad windowed reads by 15 s, because Matroska can store a cue up to about 10 s after its audio ([intro-skipper analysis](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)) [V].
4. Convert cues to Spike's transcript shape. Each cue becomes a segment with `start`, `end`, `text` and `speaker` (from the ASS `Name` field when filled). Make pseudo-word timings by spreading the cue duration across its words in proportion to character count, so stage 9b captions still work [I].

### 5.3 Stage 4: skip times and crowd seeds

**AniSkip (all shows with a MAL id).** Call:

```
GET https://api.aniskip.com/v2/skip-times/{mal_id}/{episode}?types=op&types=ed&types=mixed-op&types=mixed-ed&types=recap&episodeLength={local_duration_s}
```

A live call for Cowboy Bebop episode 1 returned OP 57.397 to 145.737 s and ED 1357.923 to 1480 s, each with a `skipId` and the `episodeLength` it was measured on ([AniSkip live response](https://api.aniskip.com/v2/skip-times/1/1?types=op&types=ed&types=recap&episodeLength=0)) [V]. It returns 404 when nothing is found ([AniSkip wrapper](https://greasyfork.org/en/scripts/457460-aniskip/code)) [V]. The response field names (`results[].interval.startTime`, `endTime`, `skipType`) are [R]; log one real response and check them. Rules [I]: pass the local duration as `episodeLength`; keep a result only if its `episodeLength` is within 5 s of the local duration [D]; otherwise shift every interval by the difference between the AniSkip OP start and a locally detected OP start. If the duration ratio is near 25/23.976 (about 1.043), the file has PAL speed-up, so scale the times instead of shifting ([CoEDL tutorial](https://coedl-knowledgebase.readthedocs.io/en/latest/posts/20170509_av_align-intro-tutorial/index.html), on stretch) [I]. AniSkip terms and rate limits were not found, so cache every response and make at most one call per episode.

**YouTube comment timestamps (optional, official API).** If the user supplies a URL of an official upload of the same episode, reuse `fetch_youtube_comments` and `TIMESTAMP_RE` in `stage4_crowd.py`. `commentThreads.list` costs 1 quota unit per page from a 10,000-unit daily quota ([YouTube quota](https://developers.google.com/youtube/v3/determine_quota_cost)) [V]. Align the upload's timeline to the local file by the OP start difference [I]. Keep the existing `compute_comment_heat` in stage 6.

**YouTube "Most replayed" heatmap.** Spike's stage 1 already reads the yt-dlp `heatmap` field (about 100 normalized buckets) ([yt-dlp commit](https://bytes.keithhacks.cyou/etc/yt-dlp/commit/5caf30dbc34f10b0be60676fece635b5c59f0d72)) [V]. No official API exposes it. YouTube's Terms prohibit automated access by scrapers without permission ([YouTube Terms](https://www.youtube.com/static?template=terms)) [V]. This is an existing project decision; the anime mode should not widen it. A 24-minute episode gives about 14 s buckets, so treat a heatmap peak as a window, not a cut point [I].

**Title-match prior (new, cheap, legal).** For shows the user wants to mine:

1. `search.list?part=snippet&q="<show title> clip"&type=video&videoDuration=short&maxResults=50` (100 units per call) ([YouTube quota](https://developers.google.com/youtube/v3/determine_quota_cost)) [V].
2. `videos.list?part=statistics,contentDetails&id=<ids>` (1 unit) for view counts.
3. Keep titles with at least 50,000 views [D]. Strip channel tags and text after `|` or `(`. Lower-case and remove punctuation.
4. Fuzzy-match each title against every transcript line and every 2-line join, using `rapidfuzz.fuzz.partial_ratio` (or `difflib.SequenceMatcher` from the standard library to avoid a new dependency). A match at 85 or above [D] becomes a crowd seed at that line's time, with weight `log10(views)` normalized to 0 to 1 across the matches.

This needs no downloads, so it avoids the ToS problem of fetching clip audio [I]. It would have found the reference line [I]. TikTok has no free API and is out of scope.

**Danmaku (off by default).** Bilibili danmaku (`https://api.bilibili.com/x/v2/dm/web/seg.so`, protobuf in about 6-minute segments) and Niconico comments are the closest analogue to Twitch chat ([aardio example](https://www.aardio.com/zh-cn/doc/example/Network/protobuf/QuickStart.html.md); [Apify description](https://apify.com/xtracto/bilibili-danmaku.md)) [V]. Both endpoints are undocumented and reverse-engineered, so they carry ToS and breakage risk. Do not ship them in the default build. If added later, reuse the chat path in stage 6 and shift peaks earlier, because comments lag the moment ([Ping and Chen 2017](https://arxiv.org/pdf/1708.02210)) [V]. Start with a 3 s lag [D] and tune it with `estimate_chat_lag`. Do not install the gitea project "bilibili_video_down": it links to an unrelated download domain.

**Reddit, MAL, AniList scores.** These are episode-level. Use AniList popularity or MAL episode scores only to pick which episodes to process first. New Reddit OAuth tokens need manual approval since November 2025 ([r/redditdev mirror](https://r.datuan.dev/r/redditdev/comments/1oug31u/introducing_the_responsible_builder_policy_new/noh6fun)), so skip Reddit.

### 5.4 Stage 6: new per-second series

Stage 6 already computes `laugh`, `shout`, `audio_loud`, `voice_jump`, `rage_words`, `speech_rate`, `replay_heat` and `comment_heat`, and it has `robust_z_score`. YAMNet already runs (`compute_yamnet_series`). YAMNet outputs 521 AudioSet classes per 0.96 s window with a 0.48 s hop on 16 kHz mono ([TensorFlow YAMNet tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio)) [V]. Add these series in the same YAMNet pass, taking the per-second max of class probabilities [I]:

| New series | YAMNet classes (by display name) | Use |
|---|---|---|
| `speech_p` | Speech, Conversation, Narration | Dialogue windows, punchline gaps |
| `music_p` | Music, plus the top music genre classes | OP/ED confirm, swells |
| `scream_p` | Screaming, Yell, Bellow, Shout | Fights, transformations, comedic overreaction |
| `cry_p` | Crying, sobbing | Emotional archetype |
| `boom_p` | Explosion, Bang, Smash/crash | Fights |

Look up class indices by display name from the class map CSV (the code already loads it in `load_yamnet_classmap`). Do not hardcode index numbers.

Add these visual series with PySceneDetect on a downscaled decode [I]. Use `AdaptiveDetector(adaptive_threshold=3.0, window_width=2, min_content_val=15.0)` for cuts, because its rolling average helps with fast camera motion, and keep the `StatsManager` per-frame `content_val`, `delta_lum` and `delta_edges` ([PySceneDetect detectors](https://www.scenedetect.com/docs/latest/api/detectors.html)) [V for the defaults]. Decode at about 320 px width (`downscale` option or an ffmpeg pipe) [I]. Anime is drawn on twos and threes with held frames, so raw frame difference is spiky. Smooth it [I]:

| Series | Formula [I, D for numbers] |
|---|---|
| `cuts` | List of shot boundary times |
| `cut_rate` | Number of cuts in a centered 10 s window |
| `motion` | `content_val` averaged per second, then a 2 s moving average |
| `flash` | 1 if a frame's `delta_lum` robust z-score is above 4 and the spike lasts under 3 frames, else 0 |
| `swell` | Short-term LUFS (ffmpeg `ebur128`) slope over 3 s, counted only where `music_p` > 0.5 and `speech_p` < 0.4 |
| `hush` | 1 where short-term LUFS drops 15 dB or more below the previous 5 s median for 0.5 to 2 s inside a scene |

The research found no source for sakuga, impact-frame, chibi or anime face detection. Treat `motion`, `cut_rate` and `flash` as rough proxies. Optical flow (OpenCV Farneback at 320 px, 6 to 8 fps) is better and much slower; run it only on the top 10 action candidates, if at all [I]. No source measured PySceneDetect or YAMNet runtime on a 24-minute episode; the expectation is minutes for scene detection at low resolution and under a minute for YAMNet [I].

**Skip mask.** Build a boolean per-second `skip` array. A candidate whose window overlaps a skip span by more than 20% [D] is dropped. Sources, cheapest first, matching the intro-skipper chain (chapters, then Chromaprint, then subtitle and black-frame fallbacks) ([intro-skipper analysis](https://raw.githubusercontent.com/intro-skipper/intro-skipper/12.0/docs/analysis.md)) [V]:

1. AniSkip intervals, padded 2 s each side [D]. For parody or abridged sources, accept an AniSkip span only if mean `music_p` > 0.6 and mean `speech_p` < 0.3 inside it [D], because parody dubs often change or drop the OP [I].
2. Embedded chapters named like `^(opening|op|intro|ending|ed|credits|preview|next episode)\b` (case-insensitive, anchored at the start). For recaps, anchor the pattern at the start of the title; intro-skipper cut wrong recap matches from 99 to 3 of 197 titles that way ([intro-skipper repo](https://github.com/intro-skipper/intro-skipper)) [V].
3. Preview rule: everything from the end of the ED to the end of the episode is a preview (intro-skipper's `AnimePreviewFromCreditsEnd`) [V].
4. Song-styled ASS lines (step 2 in section 5.2) mark OP and ED [R].
5. Music-dominant fallback: a run of 60 to 120 s in the first 25% or last 25% of the episode with mean `music_p` > 0.7 and `speech_p` < 0.2 is a likely OP or ED [D]. The search windows match the Plex-style rule (intros inside the first 25% or first 10 minutes; credits in the last 25%) ([media_preview_generator issue](https://github.com/stevezau/media_preview_generator/issues/157)) [V].
6. Chromaprint (`fpcalc`) matching across 2 or more episodes of the same season, only when the user loads a season. One episode cannot be fingerprint-matched. Users report it is "very CPU intensive" ([same issue](https://github.com/stevezau/media_preview_generator/issues/157)) [V].
7. Eyecatch heuristic: a near-static run of 2 to 8 s (smoothed `motion` below the episode's 5th percentile) between 40% and 60% of runtime, bracketed by cuts [I, D]. No source covers eyecatches.

**Dialogue exchange windows.** Compute from the text track [I, D for all numbers]:

1. Sort cleaned lines by start time. Start a new exchange when the gap to the previous line is at least 2.0 s, or when a scene cut falls in a gap of at least 0.8 s.
2. Keep exchanges with at least 3 lines and length between 8 s and 60 s. Split longer runs at their largest internal gap.
3. For each exchange compute:
   `density` = lines per 10 s;
   `turns` = number of speaker changes (use the ASS `Name` field when present; else count alternating short lines under 2.5 s as turns);
   `short_end` = 1 if the last line has 6 words or fewer;
   `punch_gap` = 1 if `speech_p` stays below 0.3 for 0.3 to 1.5 s after the last line ends;
   `exclaim` = count of `!`, `?!`, all-caps words and stutters, per 10 s.
4. `exchange_score` = mean of the robust z-scores of `density`, `turns`, `exclaim`, plus 0.5 × `short_end` plus 0.5 × `punch_gap`. Store `exchanges.json`.

Save all new series into `signals.npz` next to the existing ones.

### 5.5 Stage 7: candidates, judge, scores and boundaries

The Twitch eval showed that **38% of the top moments were never proposed as candidates** ([local report: reports/Eval baseline 9 Twitch VODs.md]). So the anime path must generate candidates from several independent sources before any judge runs.

**Step 1. Candidate generators.** Produce up to 40 candidates per 24-minute episode [D], after removing anything in the skip mask:

| Generator | Count [D] | Window |
|---|---|---|
| Top dialogue exchanges by `exchange_score` | 20 | The exchange itself |
| Intensity peaks: `find_peaks` on smoothed `scream_p + boom_p + 0.5 × motion_z` | 8 | Peak -15 s to +10 s |
| Music swell with high motion | 4 | Swell start -5 s to swell peak +8 s |
| Crowd seeds (title matches, comment timestamps, heatmap peaks) | up to 10 | Seed ±15 s |

Merge candidates whose windows overlap by more than 50% (reuse `merge_candidate_sources` and `dedupe`). Keep the source tags on each candidate.

**Step 2. Whole-episode text judge (one call).** A 24-minute transcript fits in one prompt. Reuse the `read_whole_stream` pattern. Send the episode as numbered timed lines, `[idx] MM:SS-MM:SS SPEAKER: text`, in English (translated if the source is Japanese). Mark seeded lines with `[seed:<id>]`. Ask for up to 15 candidates as JSON. The judge may propose moments the generators missed; add those as candidates too. Use Gemini Flash-Lite or Flash on free tier, or Claude Haiku through `claude_instead` [I]. The context-plus-target framing (a few prior lines, then the candidate line) is the standard setup in humor datasets ([LREC 2024](https://aclanthology.org/2024.lrec-main.1037.pdf)) [V]. Converting video to rich text before asking an LLM improved humor explanation in ExFunTube ([arXiv 2310.14159](https://arxiv.org/abs/2310.14159)) [V]. Explanation before score is an inference for this rubric, not a measured result.

Add an `ANIME_GUIDE` constant next to `FUNNY_GUIDE` [I]:

```text
What makes an anime moment work as a short clip for a stranger who never saw the show:
- a complete joke: the setup and the punchline are both inside the clip, and it ends on the punchline or the reaction to it
- a quotable line: short, said by a named character, the kind of line people repeat
- a spectacular fight beat or transformation with a clear peak (only if it reads without plot context)
- a strong emotional beat: a confession, a reunion, a sacrifice, with its build-up inside the clip
- an exaggerated reaction or an awkward silence that is funny on its own
- a moment that shows a well-known anime trope a stranger recognizes (an attack that takes forever to charge, screaming to power up,
  long speeches mid-fight, a villain explaining the plan), even if it happens inside a fight. Label it comedy_beat
For each clip, write hook_text: a 3 to 8 word question or observation for a stranger (example: "Why do anime attacks take forever?").
It is not a quote from the clip. It is shown on the title card above the video.
Not clips: opening and ending songs, recaps, next-episode previews, exposition, a reply whose question is outside the clip,
a fight that only matters if you know the plot, and late-series reveals (flag these as spoilers).
Show context: {genres}; top tags: {tags_with_rank}; audio: {audio_kind}.
If audio is dub or abridged, expect most good clips to be dialogue comedy even in an action show.
```

Text judge response shape (add a Pydantic `AnimeJudgeResponse` in `src/models.py`, and pass it as the response schema the way the existing judges do):

```json
{
  "candidates": [
    {
      "start": "07:41",
      "end": "08:13",
      "setup_line_idx": [112, 113, 114],
      "punchline_line_idx": 117,
      "archetype": "comedy_beat",
      "why": "One sentence: why a stranger laughs or cares.",
      "scores": {
        "self_contained": 9,
        "payoff": 9,
        "setup_present": 10,
        "delivery": 7,
        "quotability": 9
      },
      "needs_prior_context": false,
      "spoiler": false,
      "hook_line_idx": 112,
      "hook_text": "When winning is all that matters",
      "seed_ids": ["title_3"]
    }
  ]
}
```

`archetype` must be one of the eight ids in section 2. Every score is an integer 0 to 10. Put `why` before `scores` in the schema so the model explains first. Copy `hook_text` into the candidate's `hook_text` field unchanged, because stage 9c already draws `cand["hook_text"]` on the white title card. Do not rename the field.

**Mixed-scene rule [I, D].** A fight scene that contains a trope joke (section 3.1) has few, short lines and high motion. To keep it in the candidate list: (a) the intensity-peak generator below must pass its windows to the text judge with the lines inside them, the same as exchange windows; (b) when the judge labels an intensity-peak candidate `comedy_beat`, score it with the dialogue profile, not the action profile; (c) the exchange generator uses a 3.0 s gap (not 2.0 s) inside windows where smoothed `motion` z-score is above 1, so shouted lines across a fight still join into one exchange.

**Step 3. Judge score J (0 to 100).**

```
J = 10 × (0.30 × payoff + 0.25 × self_contained + 0.15 × setup_present + 0.15 × delivery + 0.15 × quotability)
```

Veto (J = 0) if any of these is true: `needs_prior_context` is true; `self_contained` < 4; `setup_present` < 4 for `comedy_beat`; the punchline line falls outside the clip window [I, D]. Keep the existing floor `MIN_RAW_LLM_SCORE = 65` for clips that enter the final list. The weights are [D]: payoff and self-containment lead because a Short must work for a stranger.

**Step 4. Signal score S (0 to 100), archetype-gated.** For each candidate, take the mean robust z-score of each feature over its window, combine with the profile for its archetype, then convert to a percentile rank among this episode's candidates (reuse `percentile_avg_rank`) [I, D for weights]:

| Profile | Archetypes | Weights |
|---|---|---|
| dialogue | `comedy_beat`, `iconic_line`, `cringe_reaction`, `romance_wholesome` | `exchange_score` 0.35, `punch_gap` 0.20, `speech_p` 0.15, `scream_p` 0.10, `laugh` 0.10, `comment_heat`+`replay_heat` 0.10 |
| action | `fight_sakuga`, `transformation` | `motion` 0.25, `cut_rate` 0.15, `scream_p` 0.15, `boom_p` 0.10, `swell` 0.15, `flash` 0.05, `comment_heat`+`replay_heat` 0.15 |
| quiet | `emotional`, `twist_reveal` | `music_p` 0.20, `hush` 0.20, `cry_p` 0.20, `speech_p` 0.10, low motion (negative `motion` z) 0.10, `comment_heat`+`replay_heat` 0.20 |

Note that the dialogue profile gives motion and loudness no positive weight. That is the fix for the reference case.

**Step 5. Crowd score C (0 to 100).** If any crowd seed overlaps the candidate: C = 100 × max(seed weight). If the episode has crowd data but none overlaps: C = 0. If the episode has no crowd data at all, drop C from the blend.

**Step 6. Show prior P (0.8 to 1.2).** Map tags and genres to archetypes [I]:

| Archetype | AniList genres or tags that raise it |
|---|---|
| `comedy_beat` | Comedy, Parody, Slapstick, Satire, Gag |
| `iconic_line` | any (base), plus Parody |
| `fight_sakuga` | Action, Shounen, Martial Arts, Super Power, Mecha |
| `transformation` | Super Power, Magical Girl (Mahou Shoujo), Shounen |
| `emotional` | Drama, Tragedy |
| `twist_reveal` | Mystery, Psychological, Thriller |
| `romance_wholesome` | Romance, Shoujo, Slice of Life, Iyashikei |
| `cringe_reaction` | Comedy, Ecchi |

```
tag_weight(t) = rank_t / 100 for tags; 0.8 for genres (genres have no rank) [D]
raw_a  = max tag_weight over the genres and tags mapped to archetype a (0 if none)
P_a    = clamp(0.9 + 0.3 × raw_a, 0.8, 1.2)
P_comedy_beat = max(P_comedy_beat, 1.0)          # comedy wins in every genre (section 2)
if parody or abridged: P_comedy_beat = 1.2; P_iconic_line = max(P_iconic_line, 1.1); P_fight_sakuga = min(P_fight_sakuga, 1.0)
if dub (not parody): P_comedy_beat = max(P_comedy_beat, 1.1)
```

Ignore tags with `isMediaSpoiler = true` for the prior. A candidate the judge flags `spoiler: true` gets `P = 0.8` and a visible spoiler badge in the UI; it is never boosted [I].

**Step 7. Blend and rank.**

```
no crowd data:    blend = P × (0.70 × J + 0.30 × S)
with crowd data:  blend = P × (0.55 × J + 0.15 × S + 0.30 × C)
blend = min(blend, 100)
```

The 0.70 judge weight matches the existing `LLM_WEIGHT_WITHOUT_CHAT`. The crowd split mirrors the Twitch finding that crowd activity deserves a large share when it exists, but anime crowd data is sparse, so the judge keeps the lead [D]. Then reuse `ranking_score(blend, video_gated, peak)` and `PICK_SPACING_S = 45` [I].

**Step 8. $0 path with no LLM.** When no judge is available, set the archetype from the generator (exchanges are `comedy_beat`, intensity peaks are `fight_sakuga`, swells are `transformation`) and rank by `blend = P × (0.60 × S + 0.40 × C)`, or `P × S` with no crowd data [D]. Expect this to be weak. It is a fallback, not the target.

**Step 9. Boundary snapping.** Apply this to every judged candidate [I, D for numbers]:

1. Start: the start of the setup cue (the first of `setup_line_idx`), minus 0.5 s. If a scene cut lies within 1.5 s before that, move the start to the cut.
2. Reject if the first line starts with a reply word (`and`, `but`, `yeah`, `so`, `well`, `no`) and the judge did not include an earlier setup line.
3. End: the punchline cue end plus a reaction tail of 1.0 to 3.0 s (stop at the next line start if it comes sooner). If a scene cut lies within 1.0 s after that, move the end to the cut.
4. Reject if either edge cuts a subtitle cue mid-line.
5. Length limits: dialogue archetypes 12 to 60 s; action archetypes 10 to 45 s. The reference is 32 s. Shorts guidance says a hook should land in the first 1 to 3 s ([Captions.ai](https://captions.ai/blog/video-hooks-how-to-write-a-scroll-stopping-opening)) [V]. If `hook_line_idx` starts more than 3 s after the clip start, move the start forward to 0.5 s before the hook line, unless that drops a setup line.
6. Use `trim_to_max` for overlong windows.

Add an `anime` entry to `CREATOR_PRESETS` with `min_len 12`, `max_len 60`, `setup_pad_s 1`, `end_extend_max_s 3`, `zoom_scale 1.0` [D]. The snapping above does the padding work.

**Step 10. Gemini video check (pass 2, optional).** Reuse `video_judge` and `clip_video_part`, which already send a local file as a small 360p mp4 or a YouTube URL with `start_offset` and `end_offset`. Send the top 12 candidates (`VIDEO_POOL = 12`) with ±2 s padding. Keep the existing `VideoVerdict` schema; change only the prompt to the anime guide and add "a stranger who never saw this anime" to the standalone question. Mapping: `standalone = false` or `visible = false` sets `video_gated` (score capped by `GATED_SCORE = 40`); `reaction = peak` and `score >= 70` sets `peak = true` [I]. Audio matters for humor delivery ([FunnyNet-W](https://arxiv.org/html/2401.04210v1)) [V], so keep the audio track in the clip.

Gemini costs, from current docs: video frames cost 70 tokens each at default or low resolution and audio costs 25 tokens per second ([media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)) [V]. Default sampling is 1 fps, and `fps`, `start_offset` and `end_offset` can be set per request ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)) [V]. Flash and Flash-Lite models have a free tier; Gemini 3.5 Flash-Lite is $0.30 per million input tokens and Gemini 3.8 Flash is $0.75 through 2026-12-31 ([pricing](https://ai.google.dev/gemini-api/docs/pricing)) [V]. So a 40 s check at 1 fps is about 3,800 tokens, about $0.001 on Flash-Lite, and 12 checks cost about $0.015 per episode on paid tier [I]. Free-tier rate limits are only visible in the user's AI Studio console ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)) [V]. The exact model id strings are not in the notes; read them from the models list before coding [R].

**Optional pass 1 (whole-episode video).** For visual gags and fights with no dialogue, send the whole episode at 0.5 fps and default resolution to Flash-Lite and ask for up to 10 candidate windows in `MM:SS`. That is about 86k tokens, about $0.026 on Flash-Lite paid tier, or $0 within free-tier caps [I, from the verified per-token prices]. Add its picks as candidates with source tag `video_pass1`. Build this last (phase 6); the text judge covers the reference archetype.

**Local VLM fallback.** Qwen3-VL-8B claims timestamp-grounded event localization and has GGUF builds ([Qwen3-VL-8B card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)) [V]. It is feasible on an 8 to 12 GB GPU for a handful of candidates, and impractical on CPU [I]. Treat it as an option, not a default.

**Skip for now.** DETR-family highlight models (Moment-DETR, QD-DETR, CG-DETR) are trained on live action and score query relevance, not humor ([SG-DETR](https://arxiv.org/html/2410.01615v2)). Training a FunnyNet-style model needs labels Spike does not have. CLIP or SigLIP embeddings help only to match user-supplied meme screenshots, and perceptual hashing may do that more cheaply [I].

### 5.6 Stage 9: render changes

**Keep the current render. Do not build new render code.** The user's own Short (section 3.1) is the target look, and Spike already produces it. For `anime_episode`, set these source defaults and nothing else:

| Setting | Value | Why |
|---|---|---|
| `layout` | `letterbox` | Full 16:9 frame, no speaker cropped out. MediaPipe face detection is trained on real faces and is unreliable on anime [I], so skip `stage9a_face_track` and do not use `auto`, `face_track` or `split` |
| `letterbox_style` | `title` | White bars with the hook on the title card, as in the user's clip |
| `caption_style` | `bold_pop` | Matches the yellow uppercase word captions in the user's clip |
| title card text | judge `hook_text` | Already wired: stage 9c passes `cand.get("hook_text") or cand.get("title")` |
| `cut_pauses` | `off` (stored on the source as `silence_trim = 0`) | See "Minimal cutting" below |

**Minimal cutting [I].** Anime is the opposite of a stream. A stream clip needs many cuts because it has dead air, filler talk and long pauses. An anime scene is already edited by the studio: the timing is scripted, and the pauses are deliberate. The 0.3 to 1.5 s pause before a punchline is part of the joke, and cutting it kills the joke. So for anime:

1. The **Cut pauses** control (`cut_pauses`: `auto`, `tight`, `natural`, `off`; the global default in `DEFAULT_PRESETS` in `src/moment_render.py` is `auto`) defaults to `off` for anime. Do not use `auto`: `auto` lets the LLM judge choose per clip, and the Twitch judge is tuned to cut pauses.
2. Spike has no anime tab yet. When the anime tab or the `anime_episode` source kind is added, it must preselect `off` in the form (`src/web/routes/new.py`, `src/web/routes/sources.py`) and store `silence_trim = 0`. Do not change the global default, because Twitch still needs `auto`.
3. Each anime clip is **one continuous range** from the source: no pause cuts, no stitched sections, no jump cuts. The only edits are the start and end points from boundary snapping (section 5.5, step 9).
4. The user can still turn pause cutting on for one clip in the clip editor (the existing `silence_trim` switch on the clip page). That is a manual choice, not a default.

Caption source: for sub clips, captions come from the cleaned subtitle cues with pseudo-word timings (section 5.2). If `hardsubbed` is true, render no captions. For dub or abridged clips, keep Whisper word captions. The user can still change any setting per clip in the existing editor.

### 5.7 Other stream defaults that must change for anime

Several Spike defaults are tuned for streams and would run on anime unless the anime source overrides them. Each one below was checked in the code [V]; the recommended anime value is [I]. Set all of them as `anime_episode` source defaults. Do not change the global defaults, because Twitch still needs them.

| Setting | Current default (where) | Anime default | Why |
|---|---|---|---|
| Background music | `"music": "auto"` in `DEFAULT_PRESETS` (`src/moment_render.py`) | `off` | Anime already has its own score and sound design. Added music muddies the dialogue and covers the comic pause. It also adds a second copyrighted audio track on top of the footage |
| Punch-in zoom | `default_zooms(...)` runs at the payoff when `zooms` is `None` (`stage9c_render.py`) | off (`zooms = []`) | Minimal editing, same reason as `cut_pauses = off`. Anime framing is drawn on purpose, and a zoom inside the letterbox can crop out the second character. The user can add a zoom per clip in the editor |
| Concepts | `DEFAULT_AUTO_CONCEPTS = ["single", "story", "pov", "top3"]` (`src/concepts.py`) | `["single"]` only | `story` stitches a setup and a payoff with a skip card, `top3` joins several moments, and `pov` cuts a 4 to 12 s reaction. All three break the "one continuous range" rule (section 5.6). Revisit after the anime eval set exists |
| Title and hashtags | Judge example hashtags `["gaming", "clips"]` (`stage7_moments.py`); `hashtags` field in `src/models.py` | Add `title` and `hashtags` to `AnimeJudgeResponse` | The user's own Short shows the target. The title names a character and the situation ("Piccolo takes way too long to charge his attack!"). The hashtags name the genre and the show (`#animecomedy #dbzabridged #dragonball #dragonballz`). The title is different from `hook_text`, which is the question on the title card |

Rules for the title and hashtags [I, D]:

1. `title`: 5 to 12 words. Name the main character and say what happens. Use names from the AniList characters list or the subtitle `Name` field. Do not invent names.
2. `hashtags`: 3 to 6 tags, without `#`. Always include one genre tag (`animecomedy` for comedy archetypes, `anime` otherwise). Add the show title in lower case without spaces, from AniList `title.english` or `title.romaji`. Add `<show>abridged` only if `parody` is true. Never add tags for a show other than the source.
3. To get character names, add `characters(sort: ROLE, perPage: 10) { nodes { name { full } } }` to the AniList query in section 5.1 [R for the exact field names; check with one real query]. Pass the names to the judge prompt.

## 6. Recommended pipeline order and runtime budget

Run anime processing in this order. Each step reads only the outputs of earlier steps.

1. Stage 1: resolve show, flags, allowlist (one AniList call, cached).
2. Stage 2: extract audio and text subtitle streams.
3. Stage 4: AniSkip call, optional YouTube comments, optional title-match search.
4. Stage 5: build the text track by the priority in section 5.2.
5. Stage 6: YAMNet pass (adds five series), PySceneDetect pass at 320 px, LUFS pass, skip mask, exchange windows.
6. Stage 7: generators, skip-mask filter, whole-episode text judge, J, S, C, P, blend, snapping, Gemini video check on the top 12, final pick with 45 s spacing.
7. Stage 8: slice sections.
8. Stage 9: existing render with the anime source defaults (section 5.6), captions per source.
9. Posting gate: refuse unless an allowlist entry matches (section 4).

LLM calls per episode: one text-judge call and up to 12 short video calls. On a dub, Whisper `small` on CPU is the slowest local step; PySceneDetect is second [I]. None of the runtimes were measured in the research.

## 7. Phased build order, cheapest and most valuable first

| Phase | Build | Why first | Done when |
|---|---|---|---|
| 0 | `anime_episode` source kind, local-only output, allowlist file and posting gate | Legal risk is the largest risk and the code is small | The post API refuses anime clips with no allowlist entry; a unit check proves it |
| 1 | Stage 1 AniList lookup and flags; stage 2 subtitle extraction; stage 5 text-track priority | The text track feeds the main detector | `anime.json` and a cleaned transcript exist for a test episode |
| 2 | Skip mask (AniSkip, chapters, preview rule, music-dominant fallback) | Cheap, and removes the most common bad picks | OP, ED and preview never appear in candidates on the eval set |
| 3 | Exchange windows, `ANIME_GUIDE`, `AnimeJudgeResponse`, J, show prior P, boundary snapping, dialogue signal profile | Finds the reference archetype | The eval set's dialogue targets are found (section 8) |
| 4 | Anime eval set and script | Every later weight needs it | `eval_anime` prints recall and boundary scores |
| 5 | Gemini video check with the anime prompt; anime source defaults (`letterbox`, `title`, `bold_pop`, `cut_pauses = "off"`, one continuous range per clip, and the section 5.7 overrides: music off, zoom off, `single` concept only, anime title and hashtags); caption source rules | Reuses existing code, no new render code | Gated clips drop out; renders look like the user's Short in section 3.1 |
| 6 | Action signals (`motion`, `cut_rate`, `flash`, `swell`, `scream_p`, `boom_p`) and the action profile; optional whole-episode video pass 1 | Adds fights and transformations | Action targets on the eval set improve without dialogue recall dropping |
| 7 | Crowd seeds: title-match prior, comment timestamps on official uploads | Legal and cheap, but needs user input | Seeds raise recall on shows with known Shorts |
| 8 | Japanese ASR (anime-whisper) for raw Japanese audio | Only needed when no English subs exist | A raw Japanese episode yields judged candidates |
| 9 | Security and hardening (below) | Required final phase | Checklist rows pass |

**Phase 9: Security and hardening (tier T1, personal).** Spike runs on one PC for one user, so T1 applies. The user base is fixed and small, so no scaling work is needed. Rows to do: keep Gemini, Claude and YouTube keys in `.env`, out of git, and rotate any key that was ever committed; validate user inputs (AniList id and episode as integers, file paths inside the data folder, URLs matched against an allowed host list) on the server side; never build ffmpeg or shell commands from judge output or subtitle text, and pass timestamps only after parsing them to floats and clamping them to the episode duration; treat LLM output as untrusted and escape it before showing it in the UI; escape subtitle text and titles before writing them to log lines; run `pip-audit` before shipping and after adding PySceneDetect or any ASR package, and confirm each new package name on PyPI first (the package for PySceneDetect is `scenedetect` [R]); keep the allowlist file and permission files out of any shared folder.

## 8. Measure on a small labelled anime set before tuning weights

No public anime highlight benchmark exists, and no source measured LLM timestamp accuracy on anime. Every [D] number in this report needs this eval. Build it the way `scripts/eval_stage7.py` and the Twitch eval set work: freeze inputs, re-run stage 7, score against an answer key. intro-skipper uses the same pattern with its labelled `tools/CreditsRunner` ([intro-skipper repo](https://github.com/intro-skipper/intro-skipper)).

Steps [I, D]:

1. Pick 8 episodes across 4 groups: 2 abridged or dub comedy (the reference type), 2 shounen action, 2 romance or slice of life, 2 drama or mystery. Use files the user lawfully owns.
2. Build the answer key by hand. For each episode, find official or creator Shorts cut from it (by title and description), and write down the source start and end time of each. Add moments quoted in timestamped comments. Aim for 5 to 10 targets per episode. Store them in `data/eval_anime/<episode>/targets.json` as `{"start_s": 461.0, "end_s": 493.0, "archetype": "comedy_beat", "source": "youtube_short", "views": 4600000}`.
3. Metrics: recall of targets in the top 10 picks at ±20 s (the Twitch `TOL = 20.0`) and at ±5 s; top-1 hit rate; boundary quality as the share of hits whose window overlaps the target with IoU of at least 0.5; and the share of picks inside the skip mask (must be 0).
4. Baselines: random 35 s windows (20 draws), and a loudness-only ranker (top `voice_jump` peaks, 45 s apart). The anime pipeline must beat both on every group. If loudness-only wins on the action group, raise the action profile's motion weight; if it wins on the comedy group, the judge or the exchange generator is broken.
5. Report per group and averaged per group, so one genre does not dominate. Also report candidate recall (targets present anywhere in the candidate list), because on Twitch 38% of targets were never proposed.
6. Tune in this order: candidate counts, then J weights, then profile weights, then P strength (try ±0.1 and ±0.3 around the default 0.3 slope). Change one group of numbers per run.

## Conclusion

The research shifts the question. "Which genre is this show" matters less than "what kind of moment is this, and is the audio a dub or a parody". Show tags are multi-valued and show-level, so they cannot tell a fight scene from a joke inside one episode; the per-scene archetype decides, and the genre only nudges it. The best-performing anime Shorts in the sampled data are spoken exchanges with a punchline, which favors a cheap text pipeline over expensive video models. This plays to Spike's strength: its transcript judge, chat-style peak boosts and eval harness all transfer, and the new work is mostly plumbing (AniList, AniSkip, subtitle cleaning, a skip mask) plus one new candidate generator for dialogue exchanges.

The harder constraint is legal, not technical. The pipeline can find good clips for almost nothing, but the posting step is where users get hurt, and enforcement against edited anime excerpts has included prison sentences and nine-figure yen damages. Building the local-only default and the allowlist gate before any detector work is the cheapest way to make the feature safe to ship. The open unknown is quality: until the 8-episode eval exists, every weight in this report is a reasoned starting point, not a measured one.
