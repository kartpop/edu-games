#!/usr/bin/env python3
"""Check that a Google Cloud API key works on Gemini Enterprise Agent Platform (formerly Vertex AI).

usage: /usr/bin/python3 tools/agent_platform_test.py [--location global] [--text-model M] [--tts-model M]

Reads from the environment or from edu-games/.env (gitignored):
  GOOGLE_CLOUD_API_KEY   an API key bound to a service account with the Vertex AI User role
  GOOGLE_CLOUD_LOCATION  optional, default "global"
The key already belongs to one project, which is the one billed, so no project ID is needed.

Runs three checks:
  1. text with generateContent
  2. speech with generateContent, written to voice-samples/agent-platform-test.wav
  3. text with the Interactions API (preview on Agent Platform; a failure here is reported, not fatal)
Standalone on purpose: it doesn't touch tts_samples.py or voice_clips.py.
"""
import argparse, base64, json, os, re, sys, urllib.error, urllib.request, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STRONG = ('# Director\'s notes\n'
          'Speaker: a woman from Bengaluru, a nursery-school teacher, talking to a four-year-old.\n'
          'Accent: a clear, natural Indian English accent, as heard in Indian schools. Not American, not British.\n'
          'Delivery: warm, calm, slow and clear, with a short pause between sentences.\n\n'
          '# Transcript (only this is spoken; the notes above are never read aloud)')
LINE = "Let's count! Tap 1. Or tap any number to start from there."


def setting(name):
    value = os.environ.get(name)
    env = ROOT / '.env'
    if not value and env.exists():
        m = re.search(rf'^\s*(?:export\s+)?{name}\s*=\s*["\']?([^"\'\s]+)', env.read_text(), re.M)
        value = m and m.group(1)
    return value


def call(url, key, body):
    """(response, None) or (None, error text)"""
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        return None, f'{e.code} from {url}\n{e.read().decode()[:800]}'


def texts(obj):
    """every "text" string in a response, wherever the API puts it"""
    if isinstance(obj, dict):
        return [v for k, v in obj.items() if k == 'text' and isinstance(v, str)] + \
               [t for v in obj.values() for t in texts(v)]
    return [t for v in obj for t in texts(v)] if isinstance(obj, list) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--location', default=setting('GOOGLE_CLOUD_LOCATION') or 'global')
    ap.add_argument('--text-model', default='gemini-3.8-flash')
    ap.add_argument('--tts-model', default='gemini-3.8-flash-tts')
    ap.add_argument('--voice', default='Leda')
    args = ap.parse_args()
    key = setting('GOOGLE_CLOUD_API_KEY') or sys.exit('No GOOGLE_CLOUD_API_KEY found (environment or edu-games/.env).')

    host = 'aiplatform.googleapis.com' if args.location == 'global' else f'{args.location}-aiplatform.googleapis.com'

    print(f'1. Text, generateContent, {args.text_model} ...')
    res, err = call(f'https://{host}/v1/publishers/google/models/{args.text_model}:generateContent', key,
                    {'contents': [{'role': 'user', 'parts': [{'text': 'Reply with just the word: ready'}]}]})
    if err:
        sys.exit(f'   FAILED {err}')
    print('   ->', ' '.join(texts(res)).strip())

    print(f'2. Speech, generateContent, {args.tts_model}, voice {args.voice}, en-IN ...')
    res, err = call(f'https://{host}/v1/publishers/google/models/{args.tts_model}:generateContent', key, {
        'contents': [{'role': 'user', 'parts': [{'text': f'{STRONG}\n\n{LINE}'}]}],
        'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {
            'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': args.voice}}, 'languageCode': 'en-IN'}},
    })
    if err:
        sys.exit(f'   FAILED {err}')
    part = res['candidates'][0]['content']['parts'][0]['inlineData']
    rate = int((re.search(r'rate=(\d+)', part.get('mimeType', '')) or [0, 24000])[1])
    out = ROOT / 'voice-samples' / 'agent-platform-test.wav'
    out.parent.mkdir(exist_ok=True)
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(base64.b64decode(part['data']))
    print(f'   -> {out}')

    print(f'3. Text, Interactions API (preview), {args.text_model} ...')
    res, err = call(f'https://{host}/v1beta1/locations/{args.location}/interactions', key, {
        'model': args.text_model,
        'input': [{'role': 'user', 'content': [{'type': 'text', 'text': 'Reply with just the word: ready'}]}],
    })
    print(f'   not available: {err}' if err else f'   -> {" ".join(texts(res)).strip()}')

    print('Agent Platform works with this key (checks 1 and 2 passed).')


if __name__ == '__main__':
    main()
