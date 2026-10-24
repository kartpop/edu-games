#!/usr/bin/env python3
"""Record everything a game says as audio clips, with Gemini text-to-speech.

usage: python3 tools/voice_clips.py [game_dir] [--limit N] [--redo TEXT ...]

Opens the game with #lines in headless Chrome to get every piece of speech (the
game's own allLines(), so the list can't drift from the game). Each piece without
a clip is recorded, trimmed of silence, converted to .m4a with afconvert, and
listed in voice/clips.json as {text: file}. voice/ sits at the root of the repo and
is shared by every game, so a piece like "Yes!" or "42" is recorded only once.

The voice model sometimes reads its director's notes aloud or says a line twice,
so every clip is transcribed by a text model and recorded again until the words
match. Pieces that never match are left out, and the game says them with the
device voice instead.
"""
import argparse, base64, io, json, re, subprocess, sys, tempfile, wave
from array import array
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tts_samples import ROOT, STRONG, audio, call, request

MODEL, VOICE, LANG = 'gemini-3.8-flash-tts', 'Leda', 'en-IN'
CHECKER = 'gemini-3.8-flash'
TRIES = 5
VOICE_DIR = ROOT / 'voice'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def game_lines(game):
    out = subprocess.run([CHROME, '--headless=new', '--virtual-time-budget=5000', '--dump-dom',
                          (game / 'index.html').resolve().as_uri() + '#lines'],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r'<pre id="lines">(.*?)</pre>', out, re.S)
    return json.loads(unescape(m.group(1))) if m else sys.exit('The game has no #lines list.')


def file_name(key, taken):
    base = re.sub(r'[^a-z0-9]+', '-', key.lower().replace("'", '')).strip('-')
    base += {'?': '-q', '!': '-x', ',': '-c'}.get(key[-1], '')
    name, i = base, 2
    while name + '.m4a' in taken:
        name, i = f'{base}-{i}', i + 1
    return name + '.m4a'


# Every take ends with a burst of loud static (~3 kHz), after about 0.4 s of silence: 130 ms through
# AI Studio, 160 ms through Agent Platform. Cutting a little more than that only takes off silence.
# (Looking for "a loud burst after a long pause" instead cut real words, like the "2" of "82".)
STATIC = 0.2


def trim(pcm, rate, threshold=600, pad=0.05, static=STATIC):
    """cut the static off the end, then the silence at both ends (judged on 10 ms windows)"""
    a, w = array('h', pcm), rate // 100
    a = a[:len(a) - int(static * rate)]
    loud = [i for i in range(0, len(a), w) if sum(abs(v) > threshold for v in a[i:i + w]) > w // 10]
    if not loud:
        return pcm
    p = int(pad * rate)
    return a[max(0, loud[0] - p):loud[-1] + w + p].tobytes()


def wav(pcm, rate):
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return b.getvalue()


NUMBER_WORDS = 'zero one two three four five six seven eight nine ten'.split()


def words(text):
    text = text.lower().replace('-', ' ').replace('all right', 'alright')
    # the transcript may say "1 more minute" for "One more minute"
    return [str(NUMBER_WORDS.index(w)) if w in NUMBER_WORDS else w for w in re.sub(r'[^a-z0-9 ]', '', text).split()]


def heard(pcm, rate):
    res = call(f'models/{CHECKER}:generateContent', {'contents': [{'role': 'user', 'parts': [
        {'inlineData': {'mimeType': 'audio/wav', 'data': base64.b64encode(wav(pcm, rate)).decode()}},
        {'text': 'Transcribe this audio word for word. Write numbers as digits. Output only the transcript.'}]}]})
    return res['candidates'][0]['content']['parts'][0]['text'].strip()


def record(key):
    """(pcm, rate, None) once a take says exactly `key`, else (None, None, what the last take said)"""
    text = key if key[-1] in '.!?,' else key + '.'  # stored without a full stop, but should sound finished
    said = ''
    for _ in range(TRIES):
        try:
            pcm, rate = audio(call(f'models/{MODEL}:generateContent', request(VOICE, text, STRONG, LANG)))
        except (KeyError, IndexError):  # a reply without audio
            continue
        pcm = trim(pcm, rate)
        said = heard(pcm, rate)
        if words(said) == words(key):
            return pcm, rate, None
    return None, None, said


def save(pcm, rate, path):
    with tempfile.NamedTemporaryFile(suffix='.wav') as tmp:
        tmp.write(wav(pcm, rate)); tmp.flush()
        subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '32000', tmp.name, str(path)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', default=ROOT / 'junior-kg/math/numbers-till-100', type=Path)
    ap.add_argument('--limit', type=int, help='record at most this many pieces')
    ap.add_argument('--redo', nargs='+', default=[], help='record these pieces again')
    ap.add_argument('--workers', type=int, default=10)
    args = ap.parse_args()

    out = VOICE_DIR
    out.mkdir(exist_ok=True)
    index_path = out / 'clips.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    lines = game_lines(args.game)
    for k in args.redo:
        index.pop(k, None)
    todo = [k for k in lines if k not in index or not (out / index[k]).exists()][:args.limit]
    # no "no longer used" count: other games share the folder, so a clip this game dropped may still be needed
    print(f'{len(lines)} pieces, recording {len(todo)}', flush=True)

    taken, failed, done = set(index.values()), [], 0
    with ThreadPoolExecutor(args.workers) as ex:
        jobs = {ex.submit(record, k): k for k in todo}
        for job in as_completed(jobs):
            key = jobs[job]
            pcm, rate, said = job.result()
            if pcm is None:
                failed.append(f'{key!r} -> {said[:80]!r}')
                continue
            name = index.get(key) or file_name(key, taken)
            save(pcm, rate, out / name)
            taken.add(name); index[key] = name; done += 1
            index_path.write_text(json.dumps(dict(sorted(index.items())), indent=0, ensure_ascii=False))
            if done % 50 == 0:
                print(f'  {done}/{len(todo)}', flush=True)
    print(f'Recorded {done}, {len(failed)} never came out right (the game uses the device voice for those)')
    print(*failed, sep='\n  ')


if __name__ == '__main__':
    main()
