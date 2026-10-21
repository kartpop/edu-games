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
3. **Clips** go in `<game>/voice/*.m4a`, with `<game>/voice/clips.json` mapping each piece's text
   to its file.
4. **Playback.** Copy the "recorded clips" block from
   `junior-kg/math/numbers-till-100/index.html`: `clipPieces`, `loadClip`, `preload`,
   `playClips`, `stopSpeech`, `speak`, `speakDevice`. It plays through Web Audio, so the first tap
   (the Play button) unlocks sound on iOS. It leaves 0.05 s between pieces of a sentence and
   0.35 s between sentences. It turns the music down while speaking. When a clip is missing, it
   speaks the whole line with the device voice, with the `|` marks removed.
5. Call `preload()` for the lines likely to come next, such as the explanation and praise for the
   current question, so there's no pause before them.

## Recording

```sh
/usr/bin/python3 tools/voice_clips.py <grade>/<subject>/<game>   # records only pieces without a clip
/usr/bin/python3 tools/voice_clips.py <game> --redo "Tap 16"      # record pieces again
/usr/bin/python3 tools/tts_samples.py --voice Leda --model gemini-3.8-flash-tts --lang en-IN --style strong   # a sample, to compare voices or prompts
```

- Use `/usr/bin/python3`. The python.org Python on this Mac fails with SSL certificate errors.
- The key is `GEMINI_API_KEY` in the repo's `.env`, which is gitignored. Never print it or read the
  file; check that it exists with `grep -c`.
- Billing is on, paid from the user's Google AI Pro monthly Cloud credit. A full game of ~1,800
  pieces cost about $5. Agree with the user before a run much bigger than that.

## What the tool handles, and why

- **The model goes off script.** It reads the director's notes aloud ("…from the Bengaluru, a
  nursery school teacher…"), says a line twice, adds chatter ("So, shall we write 84 now?"), or
  rambles for 20+ seconds when given a bare "1.". So every take is transcribed by
  `gemini-3.8-flash` and compared word by word with the expected text (`words()` treats number
  words and digits as equal, and "all right" as "alright"). It records again up to 5 times. About
  1.4 takes per piece were needed, and roughly 3% fail all 5, so run the tool again to retry
  those. Pieces that never pass are left out and use the device voice.
- **Every take ends with 130 ms of loud static** (around 3–4 kHz, louder than the speech), after
  about 0.4 s of silence. `trim()` cuts the last 140 ms (`STATIC`), then trims the silence at both
  ends on 10 ms windows and keeps 50 ms of padding. If the static ever comes back, measure
  instead of guessing: decode with `afconvert -f WAVE -d LEI16`, then look at RMS and the
  zero-crossing rate in 5 ms windows over the last second.
- **Format:** AAC `.m4a` at 32 kbps, 24 kHz mono, made with `afconvert`, since there's no ffmpeg on
  this Mac. That's about 15 KB a clip, and pages fetch clips only when they're needed.
- **The transcriber sometimes mishears the accent** ("Tap" as "Tab" or "Tape"). If one piece keeps
  failing, it may be fine; the user can listen and decide.

## Before shipping

- Check every piece is covered: run the tool, and it reports how many pieces have no clip.
- Test with headless Chrome (served over http, because `fetch` doesn't work from `file://`), using
  `--autoplay-policy=no-user-gesture-required`. Stub `speakDevice` to record fallbacks, then
  check that `speak()` plays clips and falls back to the device voice when one is missing.
- The user listens on the iPad (`./local.sh up`) before anything is pushed.
