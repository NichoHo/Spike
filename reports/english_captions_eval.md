# English captions: translation check on 5 real windows

Run on 2026-11-16 for plan Task 5 (docs/superpowers/plans/2026-11-16-english-captions.md).

## What was run

- **Sources:** the four links you sent, plus a second VOD from `prxf0rsaken` (the channel was offline and its newest VOD was nearly all English). Eight minutes of audio were downloaded from each, transcribed with Spike's own stage 5 (Whisper `small`, int8, multilingual, VAD), and one 60 second window was cut from each.
- **Models:** `gemini-3.1-flash-lite` (the default) and `gemini-3.8-flash`, through the real `english_words` and prompt, with the 360p clip and its sound attached and a text-only retry. The Claude fallback was off. Nothing under `data/` was touched.

| Clip | Source | Window (stream time) | What Whisper reported |
|---|---|---|---|
| A1 | itsmandyG, Twitch 2929381775 | 44:15 to 45:15 | English, with Indonesian lines mixed in |
| A2 | itsmandyG, Twitch 2929381775 | 45:30 to 46:30 | Indonesian food talk with English agent names |
| B | prxf0rsaken, Twitch 2914891596 | 23:15 to 24:15 | Indonesian (the first guess for the whole 8 minutes), plus one Thai line |
| C | KIRI & MAX, YouTube ncnaVB_ggPE | 46:00 to 47:00 | Hindi in Devanagari, no Latin words at all |
| D | Mettacha, Twitch 2919718649 | 45:45 to 46:45 | Mostly English (Whisper first guessed Arabic), used as a control |

## Reliability

| | Flash-Lite | Flash |
|---|---|---|
| Answered with the clip attached on the first call | 5 of 5 | 1 of 5 (B) |
| Needed the text-only retry | 0 | 3 (A1, A2, C) |
| No answer at all | 0 | 1 (D: 503 "high demand" twice) |
| Time per clip | 24 to 57 s | 154 s for B; the others hit timeouts, and one call hit a DNS failure on this PC |

The Flash failures were a mix of Google 503/504 errors and a dropped connection on this PC, so one run does not prove Flash is always this flaky. The failed calls still counted against its quota, which is now at 0 of 15 for today.

## How to read the lines

`HEARD` is the line Whisper produced. `LITE` and `FLASH` are the English captions. A line the model returns unchanged (ignoring punctuation) keeps the spoken words and their real timing. A blank line is hidden in the video. Flash has no entries for D.

I do not speak Indonesian or Hindi, so none of this is marked right or wrong yet. Differences I noticed:

- **B:** Whisper heard English speech as Indonesian. Four of the "Ayo" lines were really "hi": Flash-Lite wrote "Let's go" for each and Flash hid them, so neither caught it. Flash-Lite also turned "Penong" into "Let's go, let's go, let's go".
- **A2:** "seblock" is "seblak", an Indonesian dish. Flash got it right from text alone; Flash-Lite wrote "blocky". Flash-Lite kept "Hush" (a Valorant agent); Flash dropped it.
- **A1:** both fixed "Max found" to "Match found". For "Thank a club at Shadyra", Flash wrote "a collab", Flash-Lite wrote "clubbing".
- **A1 line 11:** "Berapa ya?" became "How long was it?" (Flash-Lite) and "and what?" (Flash).
- **Names:** both fixed "Jack Soba" to "Jett, Sova".
- **D:** Flash-Lite changed "freetomnet" to "frites omelette" and "Only say yes" to "Only CS". Please check both against the audio.

## Marks from the user (clips B and A2)

Ground truth for B (30 lines) and A2 (14 lines). A blank or "." mark counts as correct. B lines 29 and 30 ("Penong") and A2 line 5 were marked unknown and are left out.

| | Flash-Lite | Flash |
|---|---|---|
| B, lines right or close (of 28) | 14 | 13 |
| A2, lines right or close (of 13) | 6 | 5 |

- **Flash was better on:** B 1, 6, 25, 26, 28 and A2 12 ("seblak"). It also hid lines it could not match instead of writing a wrong word.
- **Flash-Lite was better on:** B 11, 17, the four "Thank you for the subprime Shelby" lines, and A2 4 and 6. Flash wrote "Thank you for the sub, um...".
- **Both wrong:** B 2, 5 and 12 (Whisper made them up and both models kept them), B 27, A2 1 to 3, A2 8, A2 11 (Whisper dropped "ga", so "not tasty at all" became "tastes so good" in both) and A2 14 ("anjay" stayed "hello").
- **Prompt variant (not applied):** "trust the audio over the transcript, keep negations, hide a line you cannot hear", run on Flash-Lite. On A2 it fixed "seblak" and "your map" but broke "Sova", and the "ga" and "anjay" errors stayed. On B the call fell back to text-only after a 503, so it is not a fair test, and it still kept the never-said lines. The repo prompt is unchanged.
- **Reading:** the two models are level. The limit is the Whisper transcript, and the models rarely repair it even with the audio attached.

## Side by side

```
=== A1  (lite calls: [{'media': True, 'ok': True, 'lines': 16, 's': 51.2}]; flash calls: [{'media': True, 'ok': False, 'lines': None, 's': 3021.7}, {'media': False, 'ok': True, 'lines': 16, 's': 1165.5}])
 1. HEARD : Ask your boyfriend to teach you Teach me what?
    LITE  : Ask your boyfriend to teach you. Teach me what?
    FLASH : Ask your boyfriend to teach you Teach me what?
 2. HEARD : Valorant?
    LITE  : Valorant?
    FLASH : Valorant?
 3. HEARD : They gave out the RR buddy 1 or 2 1 this one
    LITE  : They gave out the RR buddy 1 or 2. 1, this one.
    FLASH : They gave out the RR buddy 1 or 2 1 this one
 4. HEARD : Max found Oh my god good luck Valik Good luck good luck
    LITE  : Match found. Oh my god, good luck Valik. Good luck, good luck.
    FLASH : Match found Oh my god good luck Valik Good luck good luck
 5. HEARD : Have you ever Thank a club at Shadyra Both of you look
    LITE  : Have you ever thought of clubbing with Shadyra? Both of you look
    FLASH : Have you ever thought of a collab with Shadyra Both of you look
 6. HEARD : alike I mean I would love to But I don't think she
    LITE  : alike. I mean, I would love to, but I don't think she
    FLASH : alike I mean I would love to But I don't think she
 7. HEARD : knows I exist
    LITE  : knows I exist.
    FLASH : knows I exist
 8. HEARD : All the time in the world
    LITE  : All the time in the world.
    FLASH : All the time in the world
 9. HEARD : Bukan dari kapan tuh dari tahun
    LITE  : Not since when, from the year
    FLASH : Wait, since when was it? Since the year
10. HEARD : 2000
    LITE  : 2000
    FLASH : 2000
11. HEARD : Berapa ya?
    LITE  : How long was it?
    FLASH : and what?
12. HEARD : 2022?
    LITE  : 2022?
    FLASH : 2022?
13. HEARD : Kapan sama sama lagi Kalian mau ngeliat kita
    LITE  : When will we be together again? Do you guys want to see us
    FLASH : When are we collabing again? You guys want to see us
14. HEARD : Kalian
    LITE  : You guys
    FLASH : You guys
15. HEARD : mau ngeliat kita sama sama lagi guys serius Kalian ga ngeliat orange
    LITE  : want to see us together again, guys, seriously? You didn't see the orange
    FLASH : want to see us together again, guys, seriously? Did you not see the orange
16. HEARD : chickennya Hasilnya kayak gimana
    LITE  : chicken? How it turned out?
    FLASH : chicken? How it turned out?

=== A2  (lite calls: [{'media': True, 'ok': True, 'lines': 14, 's': 41.4}]; flash calls: [{'media': True, 'ok': False, 'lines': None, 's': 609.4}, {'media': False, 'ok': True, 'lines': 14, 's': 161.6}])
 1. HEARD : Ini map ya
    LITE  : Is this map?
    FLASH : What map is
 2. HEARD : Apa
    LITE  : What
    FLASH : this
 3. HEARD : ini?
    LITE  : is this?
    FLASH : even?
 4. HEARD : Kinder Bueno Memang
    LITE  : Kinder Bueno
    FLASH : Kinder Bueno. Honestly,
 5. HEARD : lucu masakannya sebab matikan itu Memang separah itu ya guys
    LITE  : It's so funny how the food turned out, it was actually that bad, guys.
    FLASH : the cooking was hilarious, but was it really that bad, guys?
 6. HEARD : Baiklah kita ada hush
    LITE  : Alright, we've got Hush,
    FLASH : Alright we have...
 7. HEARD : Jack Soba, cypher, clove
    LITE  : Jett, Sova, Cypher, Clove.
    FLASH : Jett, Sova, Cypher, Clove.
 8. HEARD : Buenable
    LITE  : Win-able.
    FLASH : Bueno-able.
 9. HEARD : Kinder Bueno
    LITE  : Kinder Bueno.
    FLASH : Kinder Bueno.
10. HEARD : Orange chicken
    LITE  : Orange chicken.
    FLASH : Orange chicken.
11. HEARD : Mana rasanya enak banget lagi
    LITE  : It actually tastes so good.
    FLASH : And it actually tasted so good, too!
12. HEARD : Kayak seblock
    LITE  : Like, it's so blocky.
    FLASH : Like seblak.
13. HEARD : Ada yang bilang aku bikin cilung
    LITE  : Someone said I made cilung.
    FLASH : Someone said I made cilung.
14. HEARD : Orange chickennya kayak cilung Hello
    LITE  : The orange chicken is like cilung, hello.
    FLASH : The orange chicken looked like cilung? Hello?!

=== B  (lite calls: [{'media': True, 'ok': True, 'lines': 30, 's': 34.0}]; flash calls: [{'media': True, 'ok': True, 'lines': 30, 's': 153.8}])
 1. HEARD : kamu nge-smoke bomb untuk saya?
    LITE  : Did you smoke bomb for me?
    FLASH : Can you smoke bomb, uh, for me on A?
 2. HEARD : Saya mampu.
    LITE  : I got you.
    FLASH : I can.
 3. HEARD : Go to the wall.
    LITE  : Go to the wall.
    FLASH : Go to the wall.
 4. HEARD : Go to the wall.
    LITE  : Go to the wall.
    FLASH : Go to the wall.
 5. HEARD : Go to the wall.
    LITE  : Go to the wall.
    FLASH : Go to the wall.
 6. HEARD : Lihat saya.
    LITE  : Look at me.
    FLASH : Look at me, look at me.
 7. HEARD : Ayo.
    LITE  : Let's go.
    FLASH : 
 8. HEARD : Bye.
    LITE  : Bye.
    FLASH : Bye.
 9. HEARD : Baby, boleh kamu beritahu semua kamera?
    LITE  : Baby, can you say hi to my camera?
    FLASH : Baby, can you say hi to my camera?
10. HEARD : Halo.
    LITE  : Hello.
    FLASH : Hello.
11. HEARD : Kita tidak bisa melihatnya.
    LITE  : We can't see it.
    FLASH : I am.
12. HEARD : Kita tidak bisa melihatnya.
    LITE  : We can't see it.
    FLASH : I am.
13. HEARD : Ayo.
    LITE  : Let's go.
    FLASH : 
14. HEARD : Ayo.
    LITE  : Let's go.
    FLASH : 
15. HEARD : Ayo.
    LITE  : Let's go.
    FLASH : 
16. HEARD : Ayo.
    LITE  : Let's go.
    FLASH : 
17. HEARD : Ya.
    LITE  : Yeah.
    FLASH : Yeah, I see.
18. HEARD : Terima kasih untuk subprime Shelby.
    LITE  : Thank you for the sub, Prime Shelby.
    FLASH : Thank you for the sub, um...
19. HEARD : Terima kasih untuk subprime Shelby.
    LITE  : Thank you for the sub, Prime Shelby.
    FLASH : Thank you for the sub, um...
20. HEARD : Tira, Leo.
    LITE  : Tira, Leo.
    FLASH : Tira, Leo.
21. HEARD : Apa?
    LITE  : What?
    FLASH : What?
22. HEARD : Terima kasih untuk subprime Shelby.
    LITE  : Thank you for the sub, Prime Shelby.
    FLASH : Thank you for the sub, um...
23. HEARD : Terima kasih untuk subprime Shelby.
    LITE  : Thank you for the sub, Prime Shelby.
    FLASH : Thank you for the sub, um...
24. HEARD : Shelby.
    LITE  : Shelby.
    FLASH : Shelby.
25. HEARD : Halo, F4 sekian.
    LITE  : Hello, F4rsaken.
    FLASH : Hello, I'm f0rsakeN's...
26. HEARD : Barat.
    LITE  : West.
    FLASH : ...favorite.
27. HEARD : Destruksi prime.
    LITE  : Destruction prime.
    FLASH : Distraction primed.
28. HEARD : Kenapa kamu beritahu?
    LITE  : Why are you telling me?
    FLASH : Where are you going?
29. HEARD : Penong, penong, penong.
    LITE  : Let's go, let's go, let's go.
    FLASH : Pee nong, pee nong, pee nong.
30. HEARD : Penong, penong, penong.
    LITE  : Let's go, let's go, let's go.
    FLASH : Pee nong, pee nong, pee nong.

=== D  (lite calls: [{'media': True, 'ok': True, 'lines': 17, 's': 23.7}]; flash calls: [{'media': True, 'ok': False, 'lines': None, 's': 30.5}, {'media': False, 'ok': False, 'lines': None, 's': 39.0}])
 1. HEARD : Valorant, it's time for Valorant No, just kidding My background is back
    LITE  : Valorant, it's time for Valorant. No, just kidding. My background is back.
 2. HEARD : ladies and gentlemen My background is back I don't know how to
    LITE  : ladies and gentlemen. My background is back. I don't know how to
 3. HEARD : explain it I don't know how to explain it When I went
    LITE  : explain it. I don't know how to explain it. When I went
 4. HEARD : to Tunisia in 2021 And I introduced the The freetomnet to my
    LITE  : to Tunisia in 2021. And I introduced the, the frites omelette to my
 5. HEARD : Tunisian friends They were like
    LITE  : Tunisian friends. They were like,
 6. HEARD : Really ?
    LITE  : Really?
 7. HEARD : It's a comfort food for us Algerians For example, when we eat
    LITE  : It's a comfort food for us Algerians. For example, when we eat,
 8. HEARD : We eat with the freetomnet And they want to eat the freet
    LITE  : We eat with the frites omelette. And they want to eat the frites
 9. HEARD : The freetomnet
    LITE  : The frites omelette.
10. HEARD : It's obvious Go last premiere Go last premiere I can't, sorry I
    LITE  : It's obvious. Go, Last Premiere. Go, Last Premiere. I can't, sorry. I
11. HEARD : promised the viewers That I should go for another game
    LITE  : promised the viewers that I should go for another game.
12. HEARD : Because that's the only thing I stream Only say yes And they
    LITE  : Because that's the only thing I stream. Only CS. And they
13. HEARD : are sick of it They are enough Look, enough is enough
    LITE  : are sick of it. They are enough. Look, enough is enough.
14. HEARD : Okay
    LITE  : Okay.
15. HEARD : What do we have ?
    LITE  : What do we have?
16. HEARD : We have shipy, we have stray Do you want me to go
    LITE  : We have Shipy, we have Stray. Do you want me to go
17. HEARD : to stray And
    LITE  : to Stray? And

=== C  (lite calls: [{'media': True, 'ok': True, 'lines': 22, 's': 56.6}]; flash calls: [{'media': True, 'ok': False, 'lines': None, 's': 326.9}, {'media': False, 'ok': True, 'lines': 22, 's': 221.4}])
 1. HEARD : अग, गो लोग बवामाल दो.
    LITE  : Ugh, go kill that golem.
    FLASH : Dude, give me blocks to hit it.
 2. HEARD : अग, तरोड चार बलोग यह तीन बलोग लगा के माल दे.
    LITE  : Ugh, place three blocks and kill it.
    FLASH : Dude, break it, place three or four blocks and kill it.
 3. HEARD : दोरा दोरा दोरा दा.
    LITE  : Run, run, run, run.
    FLASH : Run, run, run!
 4. HEARD : आई दी दी.
    LITE  : I did it.
    FLASH : 
 5. HEARD : मही साभ तो आपके गर में चैस नहीं है.
    LITE  : Wait, you don't have a chest in your house?
    FLASH : Bro, you don't even have a chest in your house.
 6. HEARD : ये कोंसी भाशा थी.
    LITE  : What language was that?
    FLASH : What language was that?
 7. HEARD : गरीप बुले जासे ये करीप.
    LITE  : Poor villager, so poor.
    FLASH : Calling me broke like he's not broke.
 8. HEARD : तो तो दिखाय चार भी नहीं.
    LITE  : You didn't even show me.
    FLASH : You can't even show four.
 9. HEARD : गो भी जी.
    LITE  : Go, geez.
    FLASH : Gobhi ji.
10. HEARD : लिसपन पुन लगा.
    LITE  : Set your spawn point.
    FLASH : Set your respawn point.
11. HEARD : पहले रिस्पन पुन काई कर कोने में.
    LITE  : First, set your spawn point in the corner.
    FLASH : First set your respawn point in the corner.
12. HEARD : ळिस के रिसल लगा.
    LITE  : Set your spawn point.
    FLASH : Set the respawn on this.
13. HEARD : तरा पहने बरोसा नहीं.
    LITE  : I don't trust you.
    FLASH : I don't trust you at all.
14. HEARD : अब आब कर.
    LITE  : Now, do it.
    FLASH : Now do it.
15. HEARD : बाख बाख
    LITE  : Run, run.
    FLASH : Run, run!
16. HEARD : कर कर कर ब्लोग दे.
    LITE  : Do it, do it, place the blocks.
    FLASH : Do it, do it, give me blocks.
17. HEARD : उत.
    LITE  : Get up.
    FLASH : 
18. HEARD : इत, तो तीन छाँ बाज बस.
    LITE  : Up, one, two, three, four, that's enough.
    FLASH : One, two, three, four, that's enough.
19. HEARD : बहुत है.
    LITE  : That's enough.
    FLASH : That's plenty.
20. HEARD : बहुत है.
    LITE  : That's enough.
    FLASH : That's plenty.
21. HEARD : तुत्रा तुलज़ा रेड कर भायगा तुए सको तुत्रा तुलज़ा
    LITE  : You're going to hit it, you're going to hit it.
    FLASH : You're gonna get trapped, bro, you're trapped.
22. HEARD : मैं दूरी हो या ल्याध ने कुज़ कर नीडा
    LITE  : I'm staying back, I'm not doing anything.
    FLASH : I'm staying away so you don't do anything to me.
```
