#!/usr/bin/env python3
"""Carousel Studio pictures: makes photos for slides with the buyer's own image-generation key. Run it with PY.

  PY imagegen.py check                                 which generators work right now, and the default. STATUS lines
  PY imagegen.py key set <openai|gemini|fal> [--clipboard]
                                                       saves a key: piped in on stdin, typed at the hidden prompt, or
                                                       (--clipboard) taken from what the buyer just copied. Never an argument
  PY imagegen.py default <provider> [--model <id>] [--quality low|medium|high]
                                                       the generator plain "make pictures" uses
  PY imagegen.py make "<prompt>" --out <file.png|.jpg|carousel folder> [--size 3:4|4:5|1:1|9:16|16:9]
                     [--provider X] [--model Y] [--ref <picture> ...] [--quality ...] [--allow-text] [--dry-run]
                                                       one picture (a carousel folder as --out: assets/gen-NN.png in it)
  PY imagegen.py batch <plan.json> [--yes] [--provider X] [--model Y] [--quality ...] [--dry-run]
                                                       [{"prompt", "out", "size", "ref"}, ...] one after another.
                                                       Without --yes it only prints the count and the total cost
  PY imagegen.py cost --count N [--provider X] [--model Y] [--size 3:4] [--quality ...] [--refs N]

Keys live in <Studio state>/carousels/keys.env (only this computer, permissions 600), or come from the usual
environment variables. No key is ever printed, logged or put on a command line. Standard library (+ Pillow if there).
"""
import base64
import json
import math
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, 'engine'))
import render as R  # noqa: E402
skillenv = R.skillenv

PROVIDERS = {   # preference order when the buyer has not picked one
    'openai': {'name': 'OpenAI', 'env': ('OPENAI_API_KEY',), 'model': 'gpt-image-2.5-flare', 'quality': 'medium'},
    'gemini': {'name': 'Google Gemini', 'env': ('GEMINI_API_KEY', 'GOOGLE_API_KEY'), 'model': 'gemini-nano-banana-2.1',
               'quality': 'medium'},
    'fal': {'name': 'fal.ai', 'env': ('FAL_KEY', 'FAL_API_KEY'), 'model': 'bytedance/seedream/v5/lite', 'quality': 'medium'},
}
RATIOS = ('3:4', '4:5', '1:1', '9:16', '16:9')
QUALITIES = ('low', 'medium', 'high', 'xhigh', 'max')
NO_TEXT = ' No text, no letters, no numbers, no logos, no watermarks anywhere in the image.'

# OpenAI GPT Image 2 / 2.5: any size in multiples of 16 (about the slide's pixels). Older models: 3 fixed sizes.
OPENAI_SIZES = {'3:4': '1152x1536', '4:5': '1088x1360', '1:1': '1088x1088', '9:16': '1008x1792', '16:9': '1792x1008'}
OPENAI_OLD_SIZES = {'3:4': '1024x1536', '4:5': '1024x1536', '9:16': '1024x1536', '1:1': '1024x1024', '16:9': '1536x1024'}
# $ per 1M tokens: (image out, image in, text in). developers.openai.com/api/docs/pricing
OPENAI_RATES = {'gpt-image-2.5': (30, 8, 5), 'gpt-image-2': (30, 8, 5), 'gpt-image-1.5': (32, 8, 5),
                'gpt-image-1-mini': (8, 2.5, 2), 'gpt-image-1': (40, 10, 5)}
# image output tokens per megapixel, for the estimate before a call (the call itself reports the real count)
OPENAI_TOKENS = {'gpt-image-2.5': {'low': 130, 'medium': 260, 'high': 1040, 'xhigh': 2100, 'max': 4200},  # medium measured
                 'gpt-image-2': {'low': 190, 'medium': 1690, 'high': 6710},
                 'gpt-image-1.5': {'low': 260, 'medium': 1010, 'high': 3970},
                 'gpt-image-1-mini': {'low': 260, 'medium': 1010, 'high': 3970},
                 'gpt-image-1': {'low': 260, 'medium': 1010, 'high': 3970}}
# Gemini: $ per picture by size. ai.google.dev/gemini-api/docs/pricing
GEMINI_PRICES = {'gemini-nano-banana-2.1': {'1K': 0.0336, '2K': 0.0504, '4K': 0.113},
                 'gemini-3.1-flash-image': {'1K': 0.067, '2K': 0.101, '4K': 0.151},
                 'gemini-3.1-flash-lite-image': {'1K': 0.0336},
                 'gemini-3-pro-image': {'1K': 0.134, '2K': 0.134, '4K': 0.24}}
GEMINI_SIZE = {'low': '1K', 'medium': '2K', 'high': '4K', 'xhigh': '4K', 'max': '4K'}
# fal: model -> (text-to-image endpoint, reference endpoint, sizes, price). fal.ai/models/<endpoint>/llms.txt
SEEDREAM_4MP = {'3:4': (1728, 2304), '4:5': (1792, 2240), '1:1': (2048, 2048), '9:16': (1440, 2560), '16:9': (2560, 1440)}
SEEDREAM_2MP = {'3:4': (1328, 1776), '4:5': (1368, 1712), '1:1': (1536, 1536), '9:16': (1152, 2048), '16:9': (2048, 1152)}
PLAIN_SIZES = {k: tuple(int(x) for x in v.split('x')) for k, v in OPENAI_SIZES.items()}
FAL_MODELS = {
    'bytedance/seedream/v5/lite': ('bytedance/seedream/v5/lite/text-to-image', 'bytedance/seedream/v5/lite/edit',
                                   SEEDREAM_4MP, lambda w, h, refs: 0.035),
    'bytedance/seedream/v5/pro': ('bytedance/seedream/v5/pro/text-to-image', 'bytedance/seedream/v5/pro/edit',
                                  SEEDREAM_2MP, lambda w, h, refs: 0.0675 + 0.0045 * max(0, refs - 1)),
    'fal-ai/flux-2-pro': ('fal-ai/flux-2-pro', 'fal-ai/flux-2-pro/edit', PLAIN_SIZES,
                          lambda w, h, refs: 0.03 + 0.015 * (math.ceil(w * h / 1e6) - 1 + refs)),
}


def say(line):
    print(line, flush=True)


VALUED = ('--out', '--size', '--provider', '--model', '--quality', '--count', '--refs')


def opt(name, default=None):
    a = sys.argv
    if name in a:
        i = a.index(name)
        return a[i + 1] if i + 1 < len(a) else default
    return default


def opts(name):
    a = sys.argv
    return [a[i + 1] for i in range(len(a) - 1) if a[i] == name]


def flag(name):
    return name in sys.argv


def positional(n):
    out, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a.startswith('--'):
            skip = a in VALUED or a == '--ref'
            continue
        out.append(a)
    return out[n] if len(out) > n else None


class Fail(Exception):
    """kind: auth, credit, verify, refused, transient, other. The message is plain words for the buyer."""
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


# ------------------------------------------------------------------ keys and settings
def keys_file():
    return os.path.join(R.state_root(), 'keys.env')


def settings_file():
    return os.path.join(R.state_root(), 'imagegen.json')


def saved_keys():
    out = {}
    try:
        with open(keys_file(), encoding='utf-8') as f:
            for line in f:
                m = re.match(r'\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$', line)
                if m and m.group(2):
                    out[m.group(1)] = m.group(2).strip('\'"')
    except OSError:
        pass
    return out


def find_key(provider):
    """-> (key, where) or (None, None). The buyer's saved key first, then the environment."""
    saved = saved_keys()
    for var in PROVIDERS[provider]['env']:
        if saved.get(var):
            return saved[var], 'saved key'
    for var in PROVIDERS[provider]['env']:
        if os.environ.get(var, '').strip():
            return os.environ[var].strip(), f'key from environment {var}'
    return None, None


def scrub(text, key=None):
    """Error text from a server, made safe to show: no key, no key-shaped strings."""
    text = str(text or '')
    if key:
        text = text.replace(key, '[key]')
    text = re.sub(r'(sk-[A-Za-z0-9_\-*]{4,}|AIza[0-9A-Za-z_\-]{10,}|[0-9a-f\-]{20,}:[0-9a-f]{16,}|[A-Za-z0-9_\-]{32,})',
                  '[hidden]', text)
    return re.sub(r'\s+', ' ', text).strip()[:240]


def choice(args_provider=None, args_model=None, args_quality=None):
    """-> (provider, model, quality). The command line, then the buyer's saved pick, then the first with a key."""
    conf = R.read_json(settings_file(), {})
    provider = (args_provider or '').lower() or conf.get('provider')
    if not provider:
        provider = next((p for p in PROVIDERS if find_key(p)[0]), 'openai')
    if provider not in PROVIDERS:
        raise SystemExit(f'STATUS imagegen FAILED: unknown provider "{provider}". One of: ' + ', '.join(PROVIDERS))
    same = conf.get('provider') == provider
    model = args_model or (conf.get('model') if same else None) or PROVIDERS[provider]['model']
    quality = (args_quality or (conf.get('quality') if same else None) or PROVIDERS[provider]['quality']).lower()
    if quality not in QUALITIES:
        raise SystemExit('STATUS imagegen FAILED: quality is one of ' + ', '.join(QUALITIES))
    return provider, model, quality


# ------------------------------------------------------------------ prices
def openai_family(model):
    for fam in sorted(OPENAI_RATES, key=len, reverse=True):
        if model.startswith(fam):
            return fam
    return None


def openai_size(model, ratio):
    fam = openai_family(model) or ''
    return (OPENAI_SIZES if fam.startswith('gpt-image-2') else OPENAI_OLD_SIZES)[ratio]


def fal_spec(model):
    if model in FAL_MODELS:
        return FAL_MODELS[model]
    return (model, model.rstrip('/') + '/edit', PLAIN_SIZES, None)   # any other fal model: price unknown


def estimate(provider, model, ratio, quality, refs=0):
    """-> dollars for one picture, or None when unknown."""
    if provider == 'openai':
        fam = openai_family(model)
        if not fam:
            return None
        w, h = (int(x) for x in openai_size(model, ratio).split('x'))
        q = quality if quality in OPENAI_TOKENS[fam] else 'high'
        out_rate, img_in, txt_in = OPENAI_RATES[fam]
        return (OPENAI_TOKENS[fam][q] * w * h / 1e6 * out_rate + refs * 1500 * img_in + 150 * txt_in) / 1e6
    if provider == 'gemini':
        table = GEMINI_PRICES.get(model)
        if not table:
            return None
        return table.get(GEMINI_SIZE[quality]) or max(table.values())
    _, _, sizes, price = fal_spec(model)
    return price(*sizes[ratio], refs) if price else None


def money(x):
    return '?' if x is None else f'${x:.2f}' if x >= 0.1 or x == 0 else f'${x:.3f}'


# ------------------------------------------------------------------ http
def ssl_context():
    ctx = ssl.create_default_context()
    try:   # a python.org Python on a Mac ships without certificates: the system ones work
        if sys.platform == 'darwin' and os.path.isfile('/etc/ssl/cert.pem'):
            ctx.load_verify_locations('/etc/ssl/cert.pem')
    except (OSError, ssl.SSLError):
        pass
    return ctx


def http(method, url, headers, body=None, timeout=240):
    """-> (status, bytes). Network trouble raises Fail('transient')."""
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=dict(headers, **{'User-Agent': 'claude-creator-studio-carousels'}))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, 'reason', e)
        if 'timed out' in str(reason).lower() or isinstance(e, TimeoutError):
            raise Fail('transient', 'the generator took too long to answer (timeout)')
        raise Fail('transient', f'could not reach the generator ({scrub(reason)}). Is the internet on?')


def explain(provider, status, raw, key):
    """A failed answer -> Fail with plain words."""
    name = PROVIDERS[provider]['name']
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw)
    low = text.lower()
    if status == 401 or 'invalid_api_key' in low or 'api_key_invalid' in low or 'api key not valid' in low \
            or 'incorrect api key' in low or 'unauthorized' in low:
        return Fail('auth', f'the {name} key was turned down (wrong, expired or deleted). Make a new key and save it '
                            'again with key set')
    if 'must be verified' in low or 'organization verification' in low or 'verify your organization' in low:
        return Fail('verify', 'OpenAI wants the account verified before its image models work: '
                              'platform.openai.com > Settings > Organization > General > Verify Organization '
                              '(a few minutes, needs an ID). Then try again')
    if provider == 'gemini' and status == 429 and ('free_tier' in low or 'limit: 0' in low):
        return Fail('credit', 'this Google key is on the free plan, and Google only makes pictures with billing turned '
                              'on: aistudio.google.com > the key > Set up billing (pay as you go), then try again')
    if status == 402 or 'insufficient_quota' in low or 'exhausted balance' in low or 'billing_hard_limit' in low \
            or ('credit' in low and status != 429):
        return Fail('credit', f'the {name} account is out of credit or has no billing set up. Add credit / turn on '
                              'billing on their site, then try again')
    if 'moderation' in low or 'safety' in low or 'content_policy' in low or 'content policy' in low \
            or 'prohibited' in low or 'nsfw' in low:
        return Fail('refused', f'{name} refused this picture (its content rules). Change the description and try again')
    if status == 404 or 'model_not_found' in low or 'does not exist' in low or 'not found' in low:
        return Fail('other', f'{name} does not offer that model on this key ({scrub(text, key)})')
    if status in (408, 409, 425, 429, 500, 502, 503, 504, 529) or 'overloaded' in low:
        return Fail('transient', f'{name} is busy right now ({status})')
    return Fail('other', f'{name} said: {scrub(text, key) or status}')


def call(provider, key, method, url, headers, body, retry=True):
    """One request with one retry on a transient problem. -> parsed JSON."""
    for attempt in (1, 2):
        try:
            status, raw = http(method, url, headers, body)
            if 200 <= status < 300:
                try:
                    return json.loads(raw.decode('utf-8'))
                except ValueError:
                    raise Fail('other', f'{PROVIDERS[provider]["name"]} answered with something that is not a picture')
            err = explain(provider, status, raw, key)
        except Fail as e:
            err = e
        if err.kind != 'transient' or not retry or attempt == 2:
            raise err
        say(f'NOTE {err}: trying once more in 8 seconds')
        time.sleep(8)


# ------------------------------------------------------------------ pictures in and out
def load_ref(path):
    """A reference picture -> (bytes, mime, name), at most 2048 px and JPEG (PNG kept when it has see-through parts)."""
    path = skillenv.path_arg(path)
    if not os.path.isfile(path):
        raise Fail('other', f'no picture at {path}')
    name = os.path.basename(path)
    try:
        from PIL import Image, ImageOps
        import io
        im = ImageOps.exif_transpose(Image.open(path))
        im.thumbnail((2048, 2048))
        buf = io.BytesIO()
        if im.mode in ('RGBA', 'LA', 'P') and 'A' in im.getbands():
            im.save(buf, 'PNG')
            return buf.getvalue(), 'image/png', os.path.splitext(name)[0] + '.png'
        im.convert('RGB').save(buf, 'JPEG', quality=92)
        return buf.getvalue(), 'image/jpeg', os.path.splitext(name)[0] + '.jpg'
    except ImportError:
        ext = os.path.splitext(name)[1].lower()
        mime = {'.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
        return open(path, 'rb').read(), mime, name
    except Exception:
        raise Fail('other', f'could not read the picture {name} (iPhone HEIC? export it as JPG and try again)')


def save_picture(data, out):
    """Bytes of any picture -> out, as PNG or JPG by its extension."""
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    want = 'JPEG' if out.lower().endswith(('.jpg', '.jpeg')) else 'PNG'
    is_png = data[:8] == b'\x89PNG\r\n\x1a\n'
    is_jpg = data[:3] == b'\xff\xd8\xff'
    if (want == 'PNG' and is_png) or (want == 'JPEG' and is_jpg):
        with open(out, 'wb') as f:
            f.write(data)
        return
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        (im.convert('RGB') if want == 'JPEG' else im).save(out, want, **({'quality': 93} if want == 'JPEG' else {}))
    except ImportError:
        out2 = os.path.splitext(out)[0] + ('.png' if is_png else '.jpg')
        with open(out2, 'wb') as f:
            f.write(data)
        raise Fail('other', f'saved as {out2} (could not convert without Pillow)')


def next_gen_path(folder):
    assets = os.path.join(folder, 'assets')
    n = 1
    while any(os.path.exists(os.path.join(assets, f'gen-{n:02d}{e}')) for e in ('.png', '.jpg')):
        n += 1
    return os.path.join(assets, f'gen-{n:02d}.png')


def multipart(fields, files):
    boundary = 'studio' + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (name, data, mime) in files:
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode() + data + b'\r\n'
    out += f'--{boundary}--\r\n'.encode()
    return bytes(out), f'multipart/form-data; boundary={boundary}'


def shown(refs):
    return [f'<{n}, {len(d) // 1024} KB>' for d, _, n in refs]


# ------------------------------------------------------------------ the three generators
def gen_openai(key, model, prompt, ratio, quality, refs, out, dry):
    fam = openai_family(model) or ''
    size = openai_size(model, ratio)
    q = quality if quality in OPENAI_TOKENS.get(fam, {'low': 1, 'medium': 1, 'high': 1}) else 'high'
    fmt = 'jpeg' if out.lower().endswith(('.jpg', '.jpeg')) else 'png'
    fields = {'model': model, 'prompt': prompt, 'size': size, 'quality': q, 'output_format': fmt, 'n': '1'}
    if refs:
        url = 'https://api.openai.com/v1/images/edits'
        if dry:
            return {'POST': url, 'multipart': fields, 'image[]': shown(refs)}
        body, ctype = multipart(fields, [('image[]', (n, d, m)) for d, m, n in refs])
    else:
        url = 'https://api.openai.com/v1/images/generations'
        fields['n'] = 1
        if dry:
            return {'POST': url, 'json': fields}
        body, ctype = json.dumps(fields).encode(), 'application/json'
    res = call('openai', key, 'POST', url, {'Authorization': f'Bearer {key}', 'Content-Type': ctype}, body)
    item = (res.get('data') or [{}])[0]
    if not item.get('b64_json'):
        raise Fail('other', 'OpenAI answered without a picture')
    save_picture(base64.b64decode(item['b64_json']), out)
    u = res.get('usage') or {}
    if u.get('output_tokens') is not None and fam:
        out_rate, img_in, txt_in = OPENAI_RATES[fam]
        d = u.get('input_tokens_details') or {}
        img_tokens = d.get('image_tokens', 0)
        txt_tokens = d.get('text_tokens', max(0, u.get('input_tokens', 0) - img_tokens))
        return (u['output_tokens'] * out_rate + img_tokens * img_in + txt_tokens * txt_in) / 1e6
    return None


def gen_gemini(key, model, prompt, ratio, quality, refs, out, dry):
    image_size = GEMINI_SIZE[quality] if GEMINI_SIZE[quality] in GEMINI_PRICES.get(model, {'1K': 0, '2K': 0, '4K': 0}) \
        else '1K'
    parts = [{'text': prompt}] + [{'inlineData': {'mimeType': m, 'data': base64.b64encode(d).decode()}} for d, m, _ in refs]
    body = {'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': {'responseModalities': ['IMAGE'],
                                 'imageConfig': {'aspectRatio': ratio, 'imageSize': image_size}}}
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    if dry:
        shown_body = json.loads(json.dumps(body))
        shown_body['contents'][0]['parts'] = [{'text': prompt}] + [{'inlineData': s} for s in shown(refs)]
        return {'POST': url, 'json': shown_body}
    res = call('gemini', key, 'POST', url, {'x-goog-api-key': key, 'Content-Type': 'application/json'},
               json.dumps(body).encode())
    if (res.get('promptFeedback') or {}).get('blockReason'):
        raise Fail('refused', 'Google Gemini refused this picture (its content rules). Change the description and try again')
    cand = (res.get('candidates') or [{}])[0]
    for p in (cand.get('content') or {}).get('parts') or []:
        data = (p.get('inlineData') or p.get('inline_data') or {}).get('data')
        if data:
            save_picture(base64.b64decode(data), out)
            return GEMINI_PRICES.get(model, {}).get(image_size)
    reason = str(cand.get('finishReason', ''))
    if any(w in reason for w in ('SAFETY', 'PROHIBITED', 'BLOCK', 'RECITATION', 'IMAGE_OTHER')):
        raise Fail('refused', f'Google Gemini refused this picture ({reason}). Change the description and try again')
    said = ' '.join(p.get('text', '') for p in (cand.get('content') or {}).get('parts') or [])
    raise Fail('other', 'Google Gemini answered without a picture' + (f': {scrub(said)}' if said else ''))


def gen_fal(key, model, prompt, ratio, quality, refs, out, dry):
    t2i, edit, sizes, price = fal_spec(model)
    w, h = sizes[ratio]
    body = {'prompt': prompt, 'image_size': {'width': w, 'height': h}, 'num_images': 1, 'sync_mode': True}
    if 'flux' in model:
        body['output_format'] = 'jpeg' if out.lower().endswith(('.jpg', '.jpeg')) else 'png'
    if refs:
        body['image_urls'] = [f'data:{m};base64,' + base64.b64encode(d).decode() for d, m, _ in refs]
    url = 'https://fal.run/' + (edit if refs else t2i)
    if dry:
        return {'POST': url, 'json': dict(body, **({'image_urls': shown(refs)} if refs else {}))}
    res = call('fal', key, 'POST', url, {'Authorization': f'Key {key}', 'Content-Type': 'application/json'},
               json.dumps(body).encode())
    if any(res.get('has_nsfw_concepts') or []):
        raise Fail('refused', 'fal.ai refused this picture (its content rules). Change the description and try again')
    src = ((res.get('images') or [{}])[0]).get('url') or ''
    if src.startswith('data:'):
        data = base64.b64decode(src.split(',', 1)[1])
    elif src:
        status, data = http('GET', src, {})
        if status != 200:
            raise Fail('transient', 'fal.ai made the picture but it could not be downloaded')
    else:
        raise Fail('other', 'fal.ai answered without a picture')
    save_picture(data, out)
    return price(w, h, len(refs)) if price else None


GENERATORS = {'openai': gen_openai, 'gemini': gen_gemini, 'fal': gen_fal}


def make_one(provider, model, quality, prompt, out, ratio, ref_paths, dry, allow_text=False):
    """-> dollars (estimate or real). Raises Fail."""
    if ratio not in RATIOS:
        raise Fail('other', 'size is one of ' + ', '.join(RATIOS))
    if not prompt or not prompt.strip():
        raise Fail('other', 'no description given for the picture')
    if not allow_text and 'no text' not in prompt.lower():
        prompt = prompt.rstrip().rstrip('.') + '.' + NO_TEXT   # the slide sets every word; the picture carries none
    refs = [load_ref(p) for p in ref_paths]
    key = None
    if not dry:
        key, _ = find_key(provider)
        if not key:
            raise Fail('auth', f'no {PROVIDERS[provider]["name"]} key on this computer yet (key set {provider})')
    est = estimate(provider, model, ratio, quality, len(refs))
    if dry:
        req = GENERATORS[provider](None, model, prompt, ratio, quality, refs, out, True)
        say('DRY-RUN ' + json.dumps(req, indent=1, ensure_ascii=False))
        return est
    real = GENERATORS[provider](key, model, prompt, ratio, quality, refs, out, False)
    return real if real is not None else est


# ------------------------------------------------------------------ commands
def cmd_check():
    conf = R.read_json(settings_file(), {})
    ready = []
    for p, info in PROVIDERS.items():
        key, where = find_key(p)
        if key:
            ready.append(p)
            say(f'STATUS imagegen {p} READY ({where})')
        else:
            say(f'STATUS imagegen {p} NO KEY ({" or ".join(info["env"])} not set, nothing saved)')
    if not ready:
        say('STATUS imagegen default NONE (no generator yet: offer to set one up, references/images.md)')
        return
    provider, model, quality = choice()
    picked = conf.get('provider') == provider
    say(f'STATUS imagegen default {provider} {model} quality {quality} ' +
        ('(the buyer picked it)' if picked else '(not picked yet' + (': more than one works, ask the buyer once)'
                                                                       if len(ready) > 1 else ')')) +
        f', about {money(estimate(provider, model, "3:4", quality))} per 3:4 picture')
    if picked and provider not in ready:
        say(f'STATUS imagegen WARNING the picked generator {provider} has no key now')


def read_secret(provider):
    if flag('--clipboard'):
        cmd = (['pbpaste'] if sys.platform == 'darwin' else
               ['powershell', '-NoProfile', '-Command', 'Get-Clipboard'] if os.name == 'nt' else
               ['sh', '-c', 'wl-paste 2>/dev/null || xclip -o -selection clipboard 2>/dev/null || xsel -b'])
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            raise SystemExit('STATUS key FAILED: could not read the clipboard on this computer')
    if sys.stdin is not None and sys.stdin.isatty():
        import getpass
        return getpass.getpass(f'Paste the {PROVIDERS[provider]["name"]} key (it stays hidden) and press Enter: ').strip()
    return (sys.stdin.read() if sys.stdin else '').strip()


def validate(provider, key):
    """A free call that only says whether the key works. -> None when fine, else Fail."""
    if provider == 'openai':
        req = ('https://api.openai.com/v1/models', {'Authorization': f'Bearer {key}'})
    elif provider == 'gemini':
        req = ('https://generativelanguage.googleapis.com/v1beta/models?pageSize=1', {'x-goog-api-key': key})
    else:
        req = ('https://api.fal.ai/v1/account/billing?expand=credits', {'Authorization': f'Key {key}'})
    try:
        status, raw = http('GET', req[0], req[1], timeout=30)
    except Fail as e:
        return e
    if 200 <= status < 300:
        return None
    if provider == 'fal' and status == 403:
        return None   # a fal key without billing-read permission still makes pictures
    return explain(provider, status, raw, key)


def cmd_key():
    if positional(1) != 'set' or (positional(2) or '').lower() not in PROVIDERS:
        raise SystemExit('key set <' + '|'.join(PROVIDERS) + '>   (the key comes in on stdin, the hidden prompt or --clipboard)')
    provider = positional(2).lower()
    key = read_secret(provider)
    key = re.sub(r'^(export\s+)?[A-Z_]+=', '', key).strip().strip('\'"')   # a whole "OPENAI_API_KEY=..." line is fine too
    if not key or len(key) < 20 or re.search(r'\s', key):
        raise SystemExit(f'STATUS key FAILED {provider}: that does not look like a key (nothing copied, or more than the key)')
    problem = validate(provider, key)
    if problem and problem.kind in ('auth', 'other'):
        raise SystemExit(f'STATUS key FAILED {provider}: {problem}. Nothing saved')
    var = PROVIDERS[provider]['env'][0]
    lines = []
    try:
        with open(keys_file(), encoding='utf-8') as f:
            lines = [l.rstrip('\n') for l in f if not re.match(rf'\s*{var}\s*=', l)]
    except OSError:
        pass
    lines.append(f'{var}={key}')
    path = keys_file()
    fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Creator Studio: image keys. Private, this computer only. Never share this file.\n' if
                not lines or not lines[0].startswith('#') else '')
        f.write('\n'.join(lines) + '\n')
    os.replace(path + '.tmp', path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    note = f' (checked: {problem})' if problem else ' (checked: it works)'
    say(f'STATUS key SAVED {provider}{note}')


def cmd_default():
    provider = (positional(1) or '').lower()
    if provider not in PROVIDERS:
        raise SystemExit('default <' + '|'.join(PROVIDERS) + '> [--model <id>] [--quality low|medium|high]')
    conf = {'provider': provider, 'model': opt('--model') or PROVIDERS[provider]['model'],
            'quality': (opt('--quality') or PROVIDERS[provider]['quality']).lower()}
    R.write_json(settings_file(), conf)
    say(f'STATUS imagegen default SAVED {provider} {conf["model"]} quality {conf["quality"]}'
        + ('' if find_key(provider)[0] else ' (no key for it yet)'))


def cmd_make():
    prompt, out = positional(1), opt('--out')
    if not prompt or not out:
        raise SystemExit('make "<prompt>" --out <file.png|carousel folder> [--size 3:4] [--ref <picture>] [--dry-run]')
    out = skillenv.path_arg(out)
    if os.path.isdir(out):
        out = next_gen_path(out)
    elif not out.lower().endswith(('.png', '.jpg', '.jpeg')):
        out += '.png'
    provider, model, quality = choice(opt('--provider'), opt('--model'), opt('--quality'))
    try:
        cost = make_one(provider, model, quality, prompt, out, opt('--size', '3:4'), opts('--ref'), flag('--dry-run'),
                        flag('--allow-text'))
    except Fail as e:
        say(f'STATUS image FAILED ({e.kind}): {e}')
        sys.exit(1)
    if flag('--dry-run'):
        say(f'STATUS dry-run {out} ({provider} {model}, about {money(cost)}, nothing sent)')
    else:
        say(f'STATUS image {out} ({provider} {model}, about {money(cost)})')


def cmd_batch():
    plan_path = skillenv.path_arg(positional(1) or '')
    plan = R.read_json(plan_path)
    if isinstance(plan, dict):
        plan = plan.get('images')
    if not isinstance(plan, list) or not plan:
        raise SystemExit('batch <plan.json>: a list of {"prompt", "out", "size", "ref"}')
    base = os.path.dirname(os.path.abspath(plan_path))
    provider, model, quality = choice(opt('--provider'), opt('--model'), opt('--quality'))
    jobs, total = [], 0.0
    for i, item in enumerate(plan, 1):
        refs = item.get('ref') or []
        refs = [refs] if isinstance(refs, str) else refs
        refs = [r if os.path.isabs(skillenv.path_arg(r)) else os.path.join(base, r) for r in refs]
        out = item.get('out') or f'gen-{i:02d}.png'
        out = out if os.path.isabs(skillenv.path_arg(out)) else os.path.join(base, out)
        missing = [r for r in refs if not os.path.isfile(r)]
        if missing or not item.get('prompt'):
            raise SystemExit(f'STATUS batch FAILED: picture {i} ' + (f'has no reference at {missing[0]}' if missing
                                                                       else 'has no prompt'))
        ratio = item.get('size', '3:4')
        est = estimate(provider, model, ratio, quality, len(refs))
        total += est or 0
        jobs.append((item['prompt'], out, ratio, refs))
    say(f'STATUS batch {len(jobs)} pictures, about {money(total)} in total ({provider} {model}, quality {quality})')
    if not flag('--yes') and not flag('--dry-run'):
        say('STATUS batch WAITING: show the buyer the list and the total, then run again with --yes')
        return
    spent, made = 0.0, 0
    for i, (prompt, out, ratio, refs) in enumerate(jobs, 1):
        try:
            cost = make_one(provider, model, quality, prompt, out, ratio, refs, flag('--dry-run'))
        except Fail as e:
            say(f'STATUS image {i}/{len(jobs)} FAILED ({e.kind}): {e}')
            if e.kind in ('auth', 'credit', 'verify'):
                say(f'STATUS batch STOPPED after {made} pictures, about {money(spent)} spent')
                sys.exit(1)
            continue
        spent += cost or 0
        made += 1
        say(f'STATUS {"dry-run" if flag("--dry-run") else "image"} {i}/{len(jobs)} {out} ({provider} {model}, about {money(cost)}; {money(spent)} so far)')
    say(f'STATUS batch DONE {made} of {len(jobs)} pictures, about {money(spent)}' + (' (dry run)' if flag('--dry-run') else ''))


def cmd_cost():
    try:
        count = int(opt('--count', '1'))
    except ValueError:
        raise SystemExit('cost --count N')
    ratio, refs = opt('--size', '3:4'), int(opt('--refs', '0'))
    if ratio not in RATIOS:
        raise SystemExit('size is one of ' + ', '.join(RATIOS))
    picked = choice(opt('--provider'), opt('--model'), opt('--quality'))
    rows = [picked] if opt('--provider') else [picked] + [choice(p) for p in PROVIDERS if p != picked[0]]
    for provider, model, quality in rows:
        each = estimate(provider, model, ratio, quality, refs)
        total = None if each is None else each * count
        say(f'STATUS cost {count} x {ratio} {provider} {model} quality {quality}: about {money(total)} '
            f'({money(each)} each){" (current pick)" if (provider, model, quality) == picked else ""}')


def main():
    skillenv.utf8_stdio()
    table = {'check': cmd_check, 'key': cmd_key, 'default': cmd_default, 'make': cmd_make, 'batch': cmd_batch,
             'cost': cmd_cost}
    cmd = positional(0)
    if cmd not in table:
        sys.exit(__doc__)
    table[cmd]()


if __name__ == '__main__':
    main()
