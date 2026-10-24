# edu-games

Small, calm learning games for young kids. Each game is a single HTML file with no build step and no dependencies. Open it in a browser.

The games use soft pastel colours and quiet music, and each session stops after about 5 minutes.

**Play online:** https://kartpop.github.io/edu-games/

Games live at `<grade>/<subject>/<game>/`.

| Game | Grade | Subject | What it practises |
|---|---|---|---|
| [numbers-till-100](https://kartpop.github.io/edu-games/junior-kg/math/numbers-till-100/) | Junior KG | Math | Counting 1–100 (or 1–50) on a column grid; before/after, bigger/smaller, 10 more/less, missing numbers |

## Play on a phone or tablet at home

```sh
./local.sh up      # start a server and print the address for iPhone/iPad
./local.sh status
./local.sh down
```

The phone or tablet must be on the same Wi-Fi as the Mac.

## Voice

Games speak with recorded clips in a single Indian English voice (Gemini TTS, voice Leda), stored in the `voice/` folder at the root, which every game shares. Lines without a clip use the device's own voice. `tools/voice_clips.py` records any missing clips through Google Cloud's Gemini Enterprise Agent Platform. It needs `GOOGLE_CLOUD_API_KEY` in a `.env` file, which is gitignored. `.claude/skills/game-voice/SKILL.md` has the exact settings and the reasons behind them.
