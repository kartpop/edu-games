# edu-games

Small, calm learning games for young children, in `<grade>/<subject>/<game>/index.html`, served by
GitHub Pages from `main`. Voice work follows `.claude/skills/game-voice/SKILL.md`.

## Rules from the user

- **Games are gender neutral.** Nothing the child sees or hears assumes a gender: say "the child",
  "you", or nothing ("Taps Done", not "He taps Done"). The same goes for settings labels, tooltips
  and code comments.
- **The user is the QA for voice clips, in the session.** Record each clip once and check it once
  (to save API cost). Then show the user the doubtful clips, with a command to play them (`afplay`),
  and wait. The user listens and says which are fine. Approve those, re-record the rest once each,
  and show the new takes. Repeat until the user is happy.
- **Don't commit or push to `main` while clips are waiting for that QA.** Commit and push only
  after the user has signed off on the clips, together with the code that uses them.
