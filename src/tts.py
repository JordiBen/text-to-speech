"""Pure helpers for the Text to Speech Actor: input parsing, text cleanup, sentence chunking, subtitles, billing."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

# Kokoro-82M v1.0 voices that pass a speech-to-text round trip (espeak-ng phonemizer). Japanese and Chinese voices
# are left out on purpose: without the dedicated G2P they come out unintelligible.
LANG_BY_PREFIX = {'a': 'en-us', 'b': 'en-gb', 'e': 'es', 'f': 'fr-fr', 'h': 'hi', 'i': 'it', 'p': 'pt-br'}
LANG_NAMES = {'en-us': 'English (US)', 'en-gb': 'English (UK)', 'es': 'Spanish', 'fr-fr': 'French', 'hi': 'Hindi',
              'it': 'Italian', 'pt-br': 'Portuguese (Brazil)'}
VOICES = {
    'af_heart': 'Heart (US female, warm, best overall)', 'af_bella': 'Bella (US female, expressive)',
    'af_nicole': 'Nicole (US female, soft/ASMR)', 'af_aoede': 'Aoede (US female)', 'af_kore': 'Kore (US female)',
    'af_sarah': 'Sarah (US female)', 'af_nova': 'Nova (US female)', 'af_sky': 'Sky (US female)',
    'af_alloy': 'Alloy (US female)', 'af_jessica': 'Jessica (US female)', 'af_river': 'River (US female)',
    'am_michael': 'Michael (US male)', 'am_fenrir': 'Fenrir (US male, deep)', 'am_puck': 'Puck (US male, lively)',
    'am_echo': 'Echo (US male)', 'am_eric': 'Eric (US male)', 'am_liam': 'Liam (US male)', 'am_onyx': 'Onyx (US male)',
    'am_adam': 'Adam (US male)', 'am_santa': 'Santa (US male, jolly)',
    'bf_emma': 'Emma (UK female)', 'bf_isabella': 'Isabella (UK female)', 'bf_alice': 'Alice (UK female)',
    'bf_lily': 'Lily (UK female)', 'bm_george': 'George (UK male)', 'bm_fable': 'Fable (UK male, storyteller)',
    'bm_lewis': 'Lewis (UK male)', 'bm_daniel': 'Daniel (UK male)',
    'ef_dora': 'Dora (Spanish female)', 'em_alex': 'Alex (Spanish male)', 'em_santa': 'Santa (Spanish male)',
    'ff_siwis': 'Siwis (French female)',
    'hf_alpha': 'Alpha (Hindi female)', 'hf_beta': 'Beta (Hindi female)', 'hm_omega': 'Omega (Hindi male)',
    'hm_psi': 'Psi (Hindi male)',
    'if_sara': 'Sara (Italian female)', 'im_nicola': 'Nicola (Italian male)',
    'pf_dora': 'Dora (Portuguese BR female)', 'pm_alex': 'Alex (Portuguese BR male)', 'pm_santa': 'Santa (Portuguese BR male)',
}
FORMATS = {'mp3': ('audio/mpeg', ['-c:a', 'libmp3lame']), 'wav': ('audio/wav', ['-c:a', 'pcm_s16le']),
           'opus': ('audio/ogg', ['-c:a', 'libopus']), 'flac': ('audio/flac', ['-c:a', 'flac']),
           'm4a': ('audio/mp4', ['-c:a', 'aac'])}
EVENT = 'tts-100-characters'
CHARS_PER_UNIT = 100
MAX_CHARS_PER_TEXT = 200_000
MAX_CHARS_PER_RUN = 1_000_000
MAX_TEXTS = 1000


class InputError(ValueError):
    pass


@dataclass
class Job:
    id: str
    text: str
    voice: str
    speed: float
    source: str = 'input'


@dataclass
class Options:
    voice: str = 'af_heart'
    blend: list[tuple[str, float]] = field(default_factory=list)
    speed: float = 1.0
    fmt: str = 'mp3'
    bitrate: int = 128
    subtitles: list[str] = field(default_factory=lambda: ['srt'])
    strip_markdown: bool = True
    sentence_pause: float = 0.25
    paragraph_pause: float = 0.6
    merge: bool = False
    include_sentences: bool = False
    allow_private: bool = False


def lang_of(voice: str) -> str:
    return LANG_BY_PREFIX[voice[0]]


def parse_blend(raw: str | None, voice: str) -> list[tuple[str, float]]:
    """'af_heart:0.7, af_bella:0.3' -> normalized weights. All voices must share one language."""
    if not raw or not raw.strip():
        return []
    out = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        name, _, w = part.partition(':')
        name = name.strip()
        if name not in VOICES:
            raise InputError(f'Unknown voice in voice blend: {name!r}. Available: {", ".join(VOICES)}')
        try:
            weight = float(w) if w.strip() else 1.0
        except ValueError:
            raise InputError(f'Bad weight in voice blend: {part!r} (use name:weight, e.g. af_heart:0.6)') from None
        if weight <= 0:
            raise InputError(f'Voice blend weights must be positive: {part!r}')
        out.append((name, weight))
    if len({lang_of(n) for n, _ in out}) > 1:
        raise InputError('All voices in a blend must have the same language/accent (same first letter).')
    total = sum(w for _, w in out)
    return [(n, round(w / total, 4)) for n, w in out]


def _speed(v, default: float = 1.0) -> float:
    try:
        s = float(v if v is not None else default)
    except (TypeError, ValueError):
        raise InputError(f'Speed must be a number between 0.5 and 2.0, got {v!r}') from None
    if not 0.5 <= s <= 2.0:
        raise InputError(f'Speed must be between 0.5 and 2.0, got {s}')
    return s


def parse_input(inp: dict) -> tuple[list[Job], list[str], Options]:
    """Returns (jobs from text fields, text file URLs, options). Raises InputError on bad input."""
    voice = (inp.get('voice') or 'af_heart').strip()
    if voice not in VOICES:
        raise InputError(f'Unknown voice {voice!r}. Available: {", ".join(VOICES)}')
    opts = Options(voice=voice, speed=_speed(inp.get('speed')))
    opts.blend = parse_blend(inp.get('voiceBlend'), voice)
    if opts.blend:
        opts.voice = opts.blend[0][0]
    fmt = (inp.get('format') or 'mp3').lower()
    if fmt not in FORMATS:
        raise InputError(f'Unknown format {fmt!r}. Use one of: {", ".join(FORMATS)}')
    opts.fmt = fmt
    opts.bitrate = int(inp.get('bitrate') or 128)
    if opts.bitrate not in (48, 64, 96, 128, 192, 256):
        raise InputError('bitrate must be one of 48, 64, 96, 128, 192, 256')
    sub = (inp.get('subtitles') or 'srt').lower()
    opts.subtitles = {'none': [], 'srt': ['srt'], 'vtt': ['vtt'], 'both': ['srt', 'vtt']}.get(sub)
    if opts.subtitles is None:
        raise InputError('subtitles must be none, srt, vtt or both')
    opts.strip_markdown = inp.get('stripMarkdown', True) is not False
    opts.sentence_pause = max(0, min(3000, int(inp.get('sentencePauseMs', 250)))) / 1000
    opts.paragraph_pause = max(0, min(5000, int(inp.get('paragraphPauseMs', 600)))) / 1000
    opts.merge = bool(inp.get('mergeIntoOneFile'))
    opts.include_sentences = bool(inp.get('includeSentenceTimings'))

    jobs: list[Job] = []
    for t in inp.get('texts') or []:
        if isinstance(t, str) and t.strip():
            jobs.append(Job(id=f'text-{len(jobs) + 1}', text=t, voice=opts.voice, speed=opts.speed))
    for i, it in enumerate(inp.get('items') or [], 1):
        if not isinstance(it, dict) or not str(it.get('text') or '').strip():
            raise InputError(f'items[{i}] needs a non-empty "text" field')
        v = (it.get('voice') or opts.voice).strip()
        if v not in VOICES:
            raise InputError(f'items[{i}]: unknown voice {v!r}')
        jid = slug(str(it.get('id') or f'item-{i}'))
        jobs.append(Job(id=jid, text=str(it['text']), voice=v, speed=_speed(it.get('speed'), opts.speed)))
    urls = []
    for u in inp.get('textFileUrls') or []:
        u = (u.get('url') if isinstance(u, dict) else u) or ''
        if u.strip():
            urls.append(u.strip())
    if not jobs and not urls:
        raise InputError('Provide at least one text in "texts", "items" or "textFileUrls".')
    if len(jobs) + len(urls) > MAX_TEXTS:
        raise InputError(f'Too many texts ({len(jobs) + len(urls)}); the maximum per run is {MAX_TEXTS}.')
    seen: dict[str, int] = {}
    for j in jobs:  # unique ids -> unique file names
        if j.id in seen:
            seen[j.id] += 1
            j.id = f'{j.id}-{seen[j.id]}'
        else:
            seen[j.id] = 1
    return jobs, urls, opts


def slug(s: str, n: int = 60) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', s).strip('-.')
    return (s[:n] or 'text').rstrip('-.')


_MD = [
    (re.compile(r'```.*?```', re.S), ' '),                    # fenced code
    (re.compile(r'!\[([^\]]*)\]\([^)]*\)'), r'\1'),            # images -> alt text
    (re.compile(r'\[([^\]]+)\]\([^)]*\)'), r'\1'),             # links -> link text
    (re.compile(r'<[^>\n]+>'), ' '),                           # inline HTML tags
    (re.compile(r'^[ \t]{0,3}#{1,6}[ \t]*(.+?)[ \t]*#*[ \t]*$', re.M), r'\1.'),  # headings become sentences
    (re.compile(r'^[ \t]*>[ \t]?', re.M), ''),                       # blockquotes
    (re.compile(r'^[ \t]*([-*+]|\d+[.)])[ \t]+', re.M), ''),         # list bullets
    (re.compile(r'^[ \t]*([-*_][ \t]*){3,}$', re.M), ''),          # horizontal rules
    (re.compile(r'(\*\*|__)(.+?)\1'), r'\2'),                  # bold
    (re.compile(r'(?<![\w*])[*_](?!\s)(.+?)(?<!\s)[*_](?![\w*])'), r'\1'),  # italics
    (re.compile(r'`([^`]+)`'), r'\1'),                         # inline code
    (re.compile(r'^[ \t]*\|?[ \t]*:?-{2,}.*$', re.M), ''),          # table separator rows
    (re.compile(r'\|'), ', '),                                 # table cells
]


def clean_text(text: str, strip_markdown: bool = True) -> str:
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    text = ''.join(ch for ch in text if ch in '\n' or unicodedata.category(ch)[0] != 'C')
    if strip_markdown:
        for rx, rep in _MD:
            text = rx.sub(rep, text)
        text = re.sub(r'\.\.(?=\s|$)', '.', text)
    text = re.sub(r'[ \u00a0]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def billable_chars(clean: str) -> int:
    """Characters we bill for: the cleaned text without line breaks and repeated spaces."""
    return len(re.sub(r'\s+', ' ', clean).strip())


def units(chars: int) -> int:
    return max(1, math.ceil(chars / CHARS_PER_UNIT)) if chars else 0


_SENT = re.compile(r'(?<=[.!?…।])["\'”’)\]]*\s+')
MAX_CHUNK = 300


def _split_long(s: str, n: int = MAX_CHUNK) -> list[str]:
    if len(s) <= n:
        return [s]
    out, cur = [], ''
    for part in re.split(r'(?<=[,;:—–])\s+', s):
        while len(part) > n:  # no punctuation: cut at the last space
            cut = part.rfind(' ', 0, n)
            cut = cut if cut > n // 3 else n
            if cur:
                out.append(cur)
                cur = ''
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if cur and len(cur) + 1 + len(part) > n:
            out.append(cur)
            cur = part
        else:
            cur = f'{cur} {part}'.strip()
    if cur:
        out.append(cur)
    return [x for x in out if x]


def chunk_text(clean: str) -> list[tuple[str, bool]]:
    """Split into speakable chunks (<= ~300 chars). Returns (chunk, ends_paragraph) pairs."""
    out: list[tuple[str, bool]] = []
    for para in re.split(r'\n\s*\n', clean):
        lines = [ln.strip() for ln in para.split('\n') if ln.strip()]
        if not lines:
            continue
        sents: list[str] = []
        for ln in lines:  # a single line break inside a paragraph is a soft sentence boundary (lists, poems, scripts)
            sents += [s.strip() for s in _SENT.split(ln) if s.strip()]
        pieces = [p for s in sents for p in _split_long(s)]
        # merge very short fragments with the next one so the voice keeps its flow
        merged: list[str] = []
        for p in pieces:
            if merged and len(merged[-1]) < 40 and len(merged[-1]) + len(p) < MAX_CHUNK and not merged[-1].endswith(('.', '!', '?', ':')):
                merged[-1] = f'{merged[-1]} {p}'
            else:
                merged.append(p)
        out += [(m, i == len(merged) - 1) for i, m in enumerate(merged)]
    return out


def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}'


def _wrap(text: str, width: int = 42) -> str:
    words, lines, cur = text.split(), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        lines.append(cur)
    # subtitles: at most 2 lines per cue; longer cues keep all lines (rare, chunk <= 300 chars)
    return '\n'.join(lines)


def subtitle_cues(sentences: list[dict], max_chars: int = 84) -> list[dict]:
    """Split sentence timings into subtitle-sized cues (time split proportional to characters)."""
    cues = []
    for s in sentences:
        text, start, end = s['text'], s['start'], s['end']
        parts = _split_long(text, max_chars)
        total = sum(len(p) for p in parts) or 1
        t = start
        for p in parts:
            d = (end - start) * len(p) / total
            cues.append({'start': round(t, 3), 'end': round(t + d, 3), 'text': p})
            t += d
    return cues


def to_srt(sentences: list[dict]) -> str:
    return '\n'.join(f'{i}\n{_ts(c["start"], ",")} --> {_ts(c["end"], ",")}\n{_wrap(c["text"])}\n'
                     for i, c in enumerate(subtitle_cues(sentences), 1))


def to_vtt(sentences: list[dict]) -> str:
    return 'WEBVTT\n\n' + '\n'.join(f'{_ts(c["start"], ".")} --> {_ts(c["end"], ".")}\n{_wrap(c["text"])}\n'
                                    for c in subtitle_cues(sentences))
