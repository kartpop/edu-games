#!/usr/bin/env python3
"""Record everything a game says as audio clips, with Gemini text-to-speech.

usage: python3 tools/voice_clips.py [game_dir] [--limit N] [--only REGEX] [--redo TEXT ...]
       python3 tools/voice_clips.py --review                 list the clips waiting for a listen
       python3 tools/voice_clips.py --approve TEXT ...       put reviewed clips into the game

Opens the game with #lines in headless Chrome to get every piece of speech (the
game's own allLines(), so the list can't drift from the game). Each piece without
a clip is recorded, trimmed of silence, converted to .m4a with afconvert, and
listed in voice/clips.json as {text: file}. voice/ sits at the root of the repo and
is shared by every game, so a piece like "Yes!" or "42" is recorded only once.

One request per clip, then one per check, and no automatic re-recording (the user's rule):
1. every piece is recorded once;
2. then every clip is transcribed once and compared with its text. The voice model sometimes
   reads its director's notes aloud or adds chatter, but the transcriber also mishears the
   accent ("make 14" as "MiG-14"), so a mismatch is only a doubt;
3. clips that match go in voice/clips.json and the game plays them. Doubtful ones are saved
   but listed in voice/review.json instead, for the user to listen to. --approve moves one into
   the game; --redo records one again. Until then the game says that piece with the device voice.
"""
import argparse, base64, io, json, re, subprocess, sys, tempfile, wave
from array import array
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tts_samples
from tts_samples import ROOT, STRONG, audio, call, request

MODEL, VOICE, LANG = 'gemini-3.8-flash-tts', 'Leda', 'en-IN'
CHECKER = 'gemini-3.8-flash'
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
    # some takes also start with a click: 10-20 ms of noise in the first 50 ms, then quiet, then the speech.
    # Only the first 50 ms count, so the start of a word ("six", "so") is never taken for a click
    rms = [(sum(v * v for v in a[i:i + w]) / w) ** .5 for i in range(0, len(a) - w + 1, w)]
    onset = next((i for i in range(len(rms) - 2) if min(rms[i:i + 3]) > 2000), None)  # loud for 30 ms
    if onset and onset >= 10 and max(rms[:5]) > 2000 and max(rms[5:onset - 5], default=0) < 2000:
        a = a[max(0, onset * w - int(pad * rate)):]
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
    text = re.sub(r'\b1s\b', 'ones', re.sub(r'\b10s\b', 'tens', text))  # "2 1s" is how it writes "2 ones"
    # the transcript may say "1 more minute" for "One more minute"
    return [str(NUMBER_WORDS.index(w)) if w in NUMBER_WORDS else w for w in re.sub(r'[^a-z0-9 ]', '', text).split()]


def heard(pcm, rate):
    res = call(f'models/{CHECKER}:generateContent', {'contents': [{'role': 'user', 'parts': [
        {'inlineData': {'mimeType': 'audio/wav', 'data': base64.b64encode(wav(pcm, rate)).decode()}},
        {'text': 'Transcribe this audio word for word. Write numbers as digits. Output only the transcript.'}]}]})
    return res['candidates'][0]['content']['parts'][0]['text'].strip()


# pieces the model kept talking about instead of reading, sent to it in other words
SPOKEN = {'make 14': 'make fourteen'}
# pieces read between two fixed sentences, so a bare phrase isn't taken as a prompt to talk about;
# the take is cut at its pauses and the middle part kept
CARRIED = {'make 14'}
CARRIER = ('Hello.', 'Goodbye.')


def middle(pcm, rate, threshold=600, gap=0.2, pad=0.05):
    """the middle of three parts split by pauses of `gap` seconds or more, or None if it isn't three parts"""
    a, w = array('h', pcm), rate // 100
    loud = [sum(abs(v) > threshold for v in a[i:i + w]) > w // 10 for i in range(0, len(a), w)]
    parts, start, quiet = [], None, 0
    for i, l in enumerate(loud + [False] * int(gap * 100)):
        if l:
            if start is None: start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet == int(gap * 100):
                parts.append((start, i - quiet + 1)); start = None
    if len(parts) != 3:
        return None
    p = int(pad * rate)
    return a[max(0, parts[1][0] * w - p):parts[1][1] * w + p].tobytes()


def record(key):
    """one request: (pcm, rate, None), or (None, None, why not)"""
    text = SPOKEN.get(key, key)
    text = text if text[-1] in '.!?,' else text + '.'  # stored without a full stop, but should sound finished
    text = re.sub(r'\b0\b', 'zero', text)  # given "0 ones." the model says just "ones"
    if key in CARRIED:
        text = f'{CARRIER[0]} {text} {CARRIER[1]}'
    try:
        pcm, rate = audio(call(f'models/{MODEL}:generateContent', request(VOICE, text, STRONG, LANG)))
    except (KeyError, IndexError):
        return None, None, 'a reply without audio'
    except OSError as e:
        return None, None, f'no reply ({e!r})'
    pcm = trim(pcm, rate)
    if key in CARRIED:  # keep the middle part; if the pauses don't give three parts, keep it all for the user to hear
        pcm = middle(pcm, rate) or pcm
    return pcm, rate, None


def check(key, pcm, rate):
    """one request: what the transcriber heard, or None if it didn't answer"""
    try:
        return heard(pcm, rate)
    except (OSError, KeyError, IndexError):
        return None


def save(pcm, rate, path):
    with tempfile.NamedTemporaryFile(suffix='.wav') as tmp:
        tmp.write(wav(pcm, rate)); tmp.flush()
        subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '32000', tmp.name, str(path)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', default=ROOT / 'junior-kg/math/numbers-till-100', type=Path)
    ap.add_argument('--limit', type=int, help='record at most this many pieces')
    ap.add_argument('--redo', nargs='+', default=[], help='record these pieces again')
    ap.add_argument('--only', help='record only missing pieces matching this regular expression')
    ap.add_argument('--review', action='store_true', help='list the clips waiting for a listen')
    ap.add_argument('--approve', nargs='+', default=[], help='put these reviewed clips into the game')
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--rpm', type=int, default=tts_samples.RPM, help='requests a minute, spread evenly')
    args = ap.parse_args()
    tts_samples.RPM = args.rpm

    out = VOICE_DIR
    out.mkdir(exist_ok=True)
    index_path, review_path = out / 'clips.json', out / 'review.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    review = json.loads(review_path.read_text()) if review_path.exists() else {}

    def write():
        index_path.write_text(json.dumps(dict(sorted(index.items())), indent=0, ensure_ascii=False))
        if review:
            review_path.write_text(json.dumps(dict(sorted(review.items())), indent=1, ensure_ascii=False))
        elif review_path.exists():
            review_path.unlink()

    if args.review or args.approve:
        for k in args.approve:
            if k not in review:
                sys.exit(f'{k!r} is not waiting for review')
            index[k] = review.pop(k)['file']
        write()
        for k, r in review.items():
            print(f'  {k!r:40} heard {r["heard"]!r:40} voice/{r["file"]}')
        print(f'{len(args.approve)} approved, {len(review)} waiting for a listen')
        return

    lines = game_lines(args.game)
    for k in args.redo:
        index.pop(k, None); review.pop(k, None)
    todo = [k for k in lines if (k not in index or not (out / index[k]).exists()) and k not in review
            and (not args.only or re.search(args.only, k))][:args.limit]
    # no "no longer used" count: other games share the folder, so a clip this game dropped may still be needed
    print(f'{len(lines)} pieces, recording {len(todo)} ({len(todo)} requests, then {len(todo)} to check them)', flush=True)

    # 1. record each piece once
    taken, failed, takes = set(index.values()) | {r['file'] for r in review.values()}, [], {}
    with ThreadPoolExecutor(args.workers) as ex:
        jobs = {ex.submit(record, k): k for k in todo}
        for job in as_completed(jobs):
            key = jobs[job]
            pcm, rate, why = job.result()
            if pcm is None:
                failed.append(f'{key!r}: {why}')
                continue
            name = index.get(key) or file_name(key, taken)
            save(pcm, rate, out / name)
            taken.add(name); takes[key] = (pcm, rate, name)
            if len(takes) % 50 == 0:
                print(f'  recorded {len(takes)}/{len(todo)}', flush=True)

    # 2. check each clip once; a mismatch waits for the user's ears instead of a new take
    doubtful = []
    with ThreadPoolExecutor(args.workers) as ex:
        jobs = {ex.submit(check, k, pcm, rate): k for k, (pcm, rate, _) in takes.items()}
        for job in as_completed(jobs):
            key, said = jobs[job], job.result()
            name = takes[key][2]
            if said is not None and words(said) == words(key):
                index[key] = name
            else:
                review[key] = {'file': name, 'heard': said or '(no transcript)'}
                index.pop(key, None); doubtful.append(key)
    write()

    print(f'Recorded {len(takes)}: {len(takes) - len(doubtful)} checked fine, {len(doubtful)} to listen to'
          + (f', {len(failed)} not recorded' if failed else ''))
    for k in sorted(doubtful):
        print(f'  listen: {k!r:40} heard {review[k]["heard"]!r:40} voice/{review[k]["file"]}')
    for f in failed:
        print(f'  not recorded: {f}')
    if doubtful:
        print('Then: --approve TEXT ... for the good ones, --redo TEXT ... to record one again.')


if __name__ == '__main__':
    main()
