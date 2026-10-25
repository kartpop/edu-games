---
name: game-voice
description: The recorded Indian English voice for edu-games — Gemini TTS settings, how lines become clips, trimming, checking and playback. Use when adding speech to a new game, adding or changing a spoken line in an existing game, re-recording clips, or touching speak()/voice code.
---

# Game voice

Every game speaks with one recorded voice, so they all sound the same. Don't use the browser's
`speechSynthesis` as the main voice: Safari on iPad hides the good downloaded voices from web
pages, so only robotic ones are left. The device voice is only a fallback for lines with no clip.

## The voice (locked — don't change without asking the user)

| Setting | Value |
|---|---|
| Model | `gemini-3.8-flash-tts` |
| Voice | `Leda` |
| `speechConfig.languageCode` | `en-IN` |
| Style prompt | `STRONG` in `tools/tts_samples.py` (director's notes: a nursery-school teacher from Bengaluru, Indian English accent, "not American, not British", warm, calm, slow) |

The user picked this by listening to samples on 2026-10-20. The 3.x models speak American
English unless they get both `en-IN` and the strong notes. Keep the transcript header
"only this is spoken; the notes above are never read aloud", because it cut down how often the
model reads the notes aloud.

`tools/voice_clips.py` sets these as `MODEL`, `VOICE`, `LANG`. Use them as they are.

## How a game uses it

1. **Lines are cut into pieces.** `speak(text)` splits on sentence ends, and ` | ` marks extra cuts
   inside a sentence (`Which is bigger, | 34 | or 43?`), so a line with many combinations reuses
   the same short clips. A key drops its final full stop, so "34." and "34" share one clip.
   Shared pieces (numbers, praise) keep the clip count small.
2. **`allLines()`** returns every piece the game can say, and the page shows that list as JSON in
   `<pre id="lines">` when opened with `#lines`. Generate it from the same templates and
   functions the game speaks with, so the list can't drift from the game.
3. **Clips** go in the shared `voice/` folder at the root of the repo, with `voice/clips.json`
   mapping each piece's text to its file. Every game uses the same folder (a game at
   `<grade>/<subject>/<game>/` sets `CLIPS = '../../../voice/'`), so a piece like "Yes!" or "42"
   is recorded once. Never delete a clip because one game stopped using it: another may need it.
4. **Playback.** Copy the "recorded clips" block from
   `junior-kg/math/numbers-till-100/index.html`: `clipPieces`, `loadClip`, `preload`,
   `playClips`, `stopSpeech`, `speak`, `speakDevice`. It plays through Web Audio, so the first tap
   (the Play button) unlocks sound on iOS. It leaves 0.05 s between pieces of a sentence and
   0.35 s between sentences. It turns the music down while speaking. When a clip is missing, it
   speaks the whole line with the device voice, with the `|` marks removed.
5. Call `preload()` for the lines likely to come next, such as the explanation and praise for the
   current question, so there's no pause before them.

## Recording

**The user's rule (2026-10-25): N clips cost N recording requests, then N checking requests.**
Record each piece once. Then transcribe each clip once. When a transcript doesn't match, don't
record again: the clip goes to `voice/review.json`, and at the end you list those for the user
to hear, in the session, with an `afplay` command, and wait. The user decides: `--approve` for the
good ones, `--redo` for the bad ones, then you show the new takes, until the user is happy. Don't
commit or push while clips are still waiting for review (see CLAUDE.md). Never re-record
or re-check automatically, and never run checking passes of your own over clips that already
exist. The transcriber mishears the accent often ("make 14" as "MiG-14"), so most doubts are
fine clips. `voice_clips.py` works this way; keep it that way.

```sh
/usr/bin/python3 tools/voice_clips.py <grade>/<subject>/<game>   # records only pieces without a clip
/usr/bin/python3 tools/voice_clips.py <game> --only '^Bye bye'  # only the missing pieces that match
/usr/bin/python3 tools/voice_clips.py --review                   # clips waiting for the user to listen
/usr/bin/python3 tools/voice_clips.py --approve "make 14"        # the user listened: put it in the game
/usr/bin/python3 tools/voice_clips.py <game> --redo "Tap 16"      # record pieces again (only when the user says so)
/usr/bin/python3 tools/tts_samples.py --voice Leda --model gemini-3.8-flash-tts --lang en-IN --style strong   # a sample, to compare voices or prompts
```

- Use `/usr/bin/python3`. The python.org Python on this Mac fails with SSL certificate errors.
- The tools call Gemini on Google Cloud's **Gemini Enterprise Agent Platform** (formerly Vertex AI):
  `https://aiplatform.googleapis.com/v1/publishers/google/models/<model>:generateContent`, with
  `"role": "user"` on each message. The key is `GOOGLE_CLOUD_API_KEY` in the repo's `.env`, which is
  gitignored (optional `GOOGLE_CLOUD_LOCATION`, default `global`). Never print it or read the file;
  check that it exists with `grep -c`. Don't use the old AI Studio `GEMINI_API_KEY`, even if it's
  still in `.env`. `tools/agent_platform_test.py` checks that the key works.
- Requests are paced: at most `--rpm` a minute (default 30), spread evenly with jitter, across all
  threads. Each take is 2 requests (record, then check). Bursts get slowed down by Agent Platform's
  shared capacity even well inside the project quota, so don't remove the pacing to go faster.
  The timeout is 300 s, because a request we give up on is still billed.
- Billing goes to the key's Google Cloud project. A full game of ~1,800 pieces cost about $5.
  Agree with the user before a run much bigger than that.

## What the tool handles, and why

- **The model goes off script.** It reads the director's notes aloud ("…from the Bengaluru, a
  nursery school teacher…"), says a line twice, adds chatter ("So, shall we write 84 now?"), or
  rambles for 20+ seconds when given a bare "1.". So every take is transcribed by
  `gemini-3.8-flash` and compared word by word with the expected text (`words()` treats number
  words and digits as equal, and "all right" as "alright"). A mismatch goes to the user to hear
  (see the rule above). Until it's approved, the game says that piece with the device voice.
- **Every take ends with loud static** (around 3–4 kHz, louder than the speech), after about
  0.4 s of silence: 130 ms through AI Studio, 160 ms through Agent Platform. `trim()` cuts the last
  200 ms (`STATIC`), then trims the silence at both ends on 10 ms windows and keeps 50 ms of
  padding. Don't detect the static by "a loud burst after a pause"; that cut real words, like the
  "2" in "Find 82". If the static ever comes back, measure
  instead of guessing: decode with `afconvert -f WAVE -d LEI16`, then look at RMS and the
  zero-crossing rate in 5 ms windows over the last second.
- **Format:** AAC `.m4a` at 32 kbps, 24 kHz mono, made with `afconvert`, since there's no ffmpeg on
  this Mac. That's about 15 KB a clip, and pages fetch clips only when they're needed.
- **A short piece can set the model talking** ("make 14" came back as "Once we finish the circle…"
  four times). Two fixes in `voice_clips.py`, for the user to choose from: `SPOKEN` sends it in other
  words ("make fourteen"), and `CARRIED` reads it between "Hello." and "Goodbye.", then keeps the
  middle part, cut at the pauses. That got "make 14" right first time. A lone "0" is always sent as
  "zero", because given "0 ones." the model says just "ones".
- **The transcriber sometimes mishears the accent** ("Tap" as "Tab" or "Tape"). If one piece keeps
  failing, it may be fine; the user can listen and decide.

## Before shipping

- Check every piece is covered: run the tool, and it reports how many pieces have no clip and which
  ones are waiting for the user to listen.
- Test with headless Chrome (served over http, because `fetch` doesn't work from `file://`), using
  `--autoplay-policy=no-user-gesture-required`. Stub `speakDevice` to record fallbacks, then
  check that `speak()` plays clips and falls back to the device voice when one is missing.
- The user listens on the iPad (`./local.sh up`) before anything is pushed.
