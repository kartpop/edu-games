#!/usr/bin/env python3
"""Generate voice samples with Gemini text-to-speech, to pick a voice for the games.

usage: python3 tools/tts_samples.py [--model M ...] [--voice V ...] [--lang en-IN] [--style strong] [--out DIR]

Reads GEMINI_API_KEY from the environment or from edu-games/.env (gitignored).
Writes one .wav per voice, each reading the same few game lines.
"""
import argparse, base64, json, os, re, sys, time, urllib.error, urllib.request, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = 'https://generativelanguage.googleapis.com/v1beta'

# female Gemini voices, with Google's one-word description
VOICES = {'Sulafat': 'warm', 'Achernar': 'soft', 'Vindemiatrix': 'gentle', 'Leda': 'youthful', 'Aoede': 'breezy'}

STYLE = ('Read this aloud as a kind, cheerful Indian preschool teacher talking to a four-year-old: '
         'Indian English accent, warm and calm, slow and clear, with a short pause between sentences.')
# the newer models ignored the gentle hint above and spoke American English
STRONG = ('# Director\'s notes\n'
          'Speaker: a woman from Bengaluru, a nursery-school teacher, talking to a four-year-old.\n'
          'Accent: a clear, natural Indian English accent, as heard in Indian schools. Not American, not British.\n'
          'Delivery: warm, calm, slow and clear, with a short pause between sentences.\n\n'
          '# Transcript (only this is spoken; the notes above are never read aloud)')
STYLES = {'teacher': STYLE, 'strong': STRONG}
LINES = """Let's count! Tap 1. Or tap any number to start from there.
What comes before 21?
Let's look together. 21 is at the top. So we go back, to the bottom of the line before. Before 21 comes 20.
Yes! 43 is bigger.
All done! See you tomorrow. Bye bye from the elephant!"""


def api_key():
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    env = ROOT / '.env'
    if not key and env.exists():
        m = re.search(r'^\s*(?:export\s+)?GEMINI_API_KEY\s*=\s*["\']?([^"\'\s]+)', env.read_text(), re.M)
        key = m and m.group(1)
    return key or sys.exit('No GEMINI_API_KEY found (environment or edu-games/.env).')


KEY = api_key()


def call(path, body=None):
    req = urllib.request.Request(f'{API}/{path}', data=json.dumps(body).encode() if body else None,
                                 headers={'x-goog-api-key': KEY, 'Content-Type': 'application/json'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 4:
                wait = 20 * (attempt + 1)
                print(f'  {e.code}, retrying in {wait}s')
                time.sleep(wait)
                continue
            sys.exit(f'{e.code}: {e.read().decode()[:400]}')


def tts_model():
    names = [m['name'].split('/')[-1] for m in call('models?pageSize=1000')['models'] if 'tts' in m['name']]
    if not names:
        sys.exit('This key has no text-to-speech models available.')
    # prefer pro over flash, then the newest version
    return sorted(names, key=lambda n: ('pro' in n, re.findall(r'\d+(?:\.\d+)?', n)), reverse=True)[0]


def request(voice, text, style=STYLE, lang=None):
    speech = {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}
    if lang:
        speech['languageCode'] = lang
    return {
        'contents': [{'parts': [{'text': f'{style}\n\n{text}'}]}],
        'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': speech},
    }


def audio(res):
    """(16-bit mono PCM, sample rate) from a generateContent response"""
    part = res['candidates'][0]['content']['parts'][0]['inlineData']
    rate = int((re.search(r'rate=(\d+)', part.get('mimeType', '')) or [0, 24000])[1])
    return base64.b64decode(part['data']), rate


def speak(model, voice, text, style=STYLE, lang=None):
    return audio(call(f'models/{model}:generateContent', request(voice, text, style, lang)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', nargs='+', help='TTS model(s); default: the best one available')
    ap.add_argument('--voice', nargs='+', default=list(VOICES), help='voice name(s)')
    ap.add_argument('--lang', help='speechConfig.languageCode, e.g. en-IN')
    ap.add_argument('--style', choices=STYLES, default='teacher')
    ap.add_argument('--out', default=ROOT / 'voice-samples', type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    models = args.model or [tts_model()]
    for model in models:
        print(f'Model: {model}')
        for voice in args.voice:
            pcm, rate = speak(model, voice, LINES, STYLES[args.style], args.lang)
            name = f'{voice}-{VOICES[voice]}' if voice in VOICES else voice
            name += f'-{args.lang}' * bool(args.lang) + f'-{args.style}' * (args.style != 'teacher')
            path = args.out / (f'{name}.wav' if len(models) == 1 and not args.model else f'{name}-{model}.wav')
            with wave.open(str(path), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
            print(f'  {path}  ({len(pcm) / 2 / rate:.0f}s)')


if __name__ == '__main__':
    main()
