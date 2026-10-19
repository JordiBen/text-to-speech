"""Apify entrypoint: text to natural speech with Kokoro-82M (ONNX, CPU). MP3/WAV/Opus/FLAC/M4A + SRT/VTT subtitles."""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlsplit

import httpx
import numpy as np
from apify import Actor

from .netguard import BlockedAddressError, assert_public_url
from .tts import (EVENT, FORMATS, LANG_NAMES, MAX_CHARS_PER_RUN, MAX_CHARS_PER_TEXT, InputError, Job, Options,
                  billable_chars, chunk_text, clean_text, lang_of, parse_input, slug, to_srt, to_vtt, units)

MODEL_DIR = os.environ.get('KOKORO_MODEL_DIR', '/models')
SAMPLE_RATE = 24000
MAX_FILE_BYTES = 2 * 1024 * 1024
_engine = None


def cpu_threads() -> int:
    if Actor.is_at_home():
        mem = int(os.environ.get('ACTOR_MEMORY_MBYTES') or os.environ.get('APIFY_MEMORY_MBYTES') or 4096)
        return max(1, mem // 4096)  # Apify gives 1 CPU core per 4 GB of memory
    return min(4, os.cpu_count() or 1)


# int8 is ~25% faster than fp32 on Apify CPUs (benchmark 2026-10-19: 50 vs 68 s per 1,000 characters at 4 GB) and passes
# the same speech-to-text round trip. fp32 is only used if present and int8 is missing (e.g. local dev).
MODEL_FILES = ['kokoro-v1.0.int8.onnx', 'kokoro-v1.0.onnx']


def cpu_info() -> dict:
    info = {'cpuCount': os.cpu_count(), 'threads': cpu_threads()}
    for f in ('/sys/fs/cgroup/cpu.max', '/sys/fs/cgroup/cpu/cpu.cfs_quota_us'):
        try:
            info[f.rsplit('/', 1)[-1]] = open(f).read().strip()
        except OSError:
            pass
    try:
        flags = next(ln for ln in open('/proc/cpuinfo') if ln.startswith('flags')).split()
        info['avx2'], info['avx512f'], info['vnni'] = 'avx2' in flags, 'avx512f' in flags, any('vnni' in f for f in flags)
        info['model'] = next(ln for ln in open('/proc/cpuinfo') if ln.startswith('model name')).split(':', 1)[1].strip()
    except (OSError, StopIteration):
        pass
    return info


def engine():
    global _engine
    if _engine is None:
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
        so = rt.SessionOptions()
        so.intra_op_num_threads = cpu_threads()
        so.inter_op_num_threads = 1
        path = next((os.path.join(MODEL_DIR, f) for f in MODEL_FILES if os.path.exists(os.path.join(MODEL_DIR, f))),
                    os.path.join(MODEL_DIR, MODEL_FILES[0]))
        sess = rt.InferenceSession(path, so, providers=['CPUExecutionProvider'])
        _engine = Kokoro.from_session(sess, os.path.join(MODEL_DIR, 'voices-v1.0.bin'))
    return _engine


def style_for(job: Job, opts: Options):
    k = engine()
    if opts.blend and job.voice == opts.voice:
        return sum(w * k.get_voice_style(n) for n, w in opts.blend)
    return job.voice


def synthesize(job: Job, clean: str, opts: Options) -> tuple[np.ndarray, list[dict]]:
    """Synthesize chunk by chunk so every sentence gets an exact start/end time for subtitles."""
    k = engine()
    voice, lang = style_for(job, opts), lang_of(job.voice)
    parts, sents, t = [], [], 0.0
    chunks = chunk_text(clean)
    for i, (chunk, para_end) in enumerate(chunks):
        audio, _ = k.create(chunk, voice=voice, speed=job.speed, lang=lang, trim=True,
                            sentence_pause=opts.sentence_pause, clause_pause=0.1)
        audio = audio.astype(np.float32)
        dur = len(audio) / SAMPLE_RATE
        sents.append({'start': round(t, 3), 'end': round(t + dur, 3), 'text': chunk})
        parts.append(audio)
        t += dur
        if i < len(chunks) - 1:
            gap = opts.paragraph_pause if para_end else opts.sentence_pause
            if gap:
                parts.append(np.zeros(int(gap * SAMPLE_RATE), dtype=np.float32))
                t += gap
    if not parts:
        raise InputError('Nothing to read aloud after cleaning the text.')
    return np.concatenate(parts), sents


def encode(raw_path: str, out_path: str, opts: Options) -> None:
    _, args = FORMATS[opts.fmt]
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SAMPLE_RATE), '-ac', '1', '-i', raw_path, *args]
    if opts.fmt in ('mp3', 'opus', 'm4a'):
        cmd += ['-b:a', f'{opts.bitrate}k']
    r = subprocess.run(cmd + [out_path], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f'Audio encoding failed: {r.stderr[-300:]}')


async def fetch_text(client: httpx.AsyncClient, url: str, allow_private: bool) -> str:
    await assert_public_url(url, allow_private=allow_private)
    async with client.stream('GET', url, follow_redirects=True) as r:
        if r.status_code >= 400:
            raise InputError(f'Download failed: HTTP {r.status_code}')
        await assert_public_url(str(r.url), allow_private=allow_private)
        ctype = (r.headers.get('content-type') or '').lower()
        if 'html' in ctype:
            raise InputError('The link returned a web page. Give a link to a plain .txt or .md file, or convert the '
                             'page to text first (e.g. with the Web Page to Markdown Actor).')
        if ctype and not (ctype.startswith('text/') or 'markdown' in ctype or 'octet-stream' in ctype or 'json' in ctype):
            raise InputError(f'Unsupported file type {ctype.split(";")[0]}: use a plain text (.txt) or Markdown (.md) file.')
        buf = bytearray()
        async for chunk in r.aiter_bytes(1 << 16):
            buf += chunk
            if len(buf) > MAX_FILE_BYTES:
                raise InputError('Text file too large (max 2 MB per file).')
    if b'\x00' in buf[:4096]:
        raise InputError('This does not look like a text file.')
    return buf.decode('utf-8', errors='replace').lstrip('\ufeff')


def file_id(url: str, n: int) -> str:
    name = unquote(urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1])
    name = name.rsplit('.', 1)[0] if '.' in name else name
    return slug(name) if name else f'file-{n}'


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        try:
            jobs, urls, opts = parse_input(inp)
        except InputError as e:
            await Actor.fail(status_message=str(e))
            return
        if inp.get('_debug'):  # undocumented: log CPU info and per-text timing
            Actor.log.info(f'CPU: {cpu_info()}')
        if os.environ.get('ALLOW_PRIVATE_NETWORK_FOR_LOCAL_DEV') == '1' and not Actor.is_at_home():
            opts.allow_private = True
        kvs = await Actor.open_key_value_store()
        cm = Actor.get_charging_manager()
        mime, _ = FORMATS[opts.fmt]
        total_chars = done = billed_total = 0
        budget_hit = False
        merged_raw = tempfile.NamedTemporaryFile(delete=False, suffix='.f32') if opts.merge else None
        merged_sents: list[dict] = []
        merged_t = 0.0
        queue: list[Job | tuple[str, int]] = [*jobs, *[(u, i) for i, u in enumerate(urls, 1)]]
        used_ids = {j.id for j in jobs}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=60),
                                     headers={'User-Agent': 'Mozilla/5.0 (compatible; TextToSpeechActor/1.0)'}) as client:
            for n, q in enumerate(queue, 1):
                rec: dict = {}
                try:
                    if isinstance(q, tuple):
                        url, i = q
                        rec.update(id=file_id(url, i), source=url)
                        while rec['id'] in used_ids:
                            rec['id'] += '-f'
                        used_ids.add(rec['id'])
                        await Actor.set_status_message(f'Text {n}/{len(queue)}: downloading')
                        job = Job(id=rec['id'], text=await fetch_text(client, url, opts.allow_private),
                                  voice=opts.voice, speed=opts.speed, source=url)
                    else:
                        job = q
                        rec.update(id=job.id, source=job.source)
                    clean = clean_text(job.text, opts.strip_markdown)
                    chars = billable_chars(clean)
                    rec.update(voice=job.voice, language=LANG_NAMES[lang_of(job.voice)], speed=job.speed,
                               characters=chars, textPreview=clean[:200])
                    if opts.blend and job.voice == opts.voice:
                        rec['voiceBlend'] = ', '.join(f'{v}:{w}' for v, w in opts.blend)
                    if not chars:
                        raise InputError('Text is empty after cleanup (not charged).')
                    if chars > MAX_CHARS_PER_TEXT:
                        raise InputError(f'Text too long ({chars:,} characters; max {MAX_CHARS_PER_TEXT:,} per text). '
                                         'Split it into chapters (not charged).')
                    if total_chars + chars > MAX_CHARS_PER_RUN:
                        raise InputError(f'Run limit of {MAX_CHARS_PER_RUN:,} characters reached; start another run for the rest (not charged).')
                    need = units(chars)
                    allowed = cm.calculate_max_event_charge_count_within_limit(EVENT)
                    if allowed is not None and allowed < need:
                        budget_hit = True
                        raise InputError(f'Skipped: needs {need} x 100 characters but your max charge per run allows {allowed}. '
                                         'Raise the run\'s max cost limit (not charged).')
                    await Actor.set_status_message(f'Text {n}/{len(queue)}: speaking {chars:,} characters ({job.voice})')
                    t0 = time.time()
                    audio, sents = await asyncio.to_thread(synthesize, job, clean, opts)
                    with tempfile.TemporaryDirectory() as td:
                        raw = os.path.join(td, 'a.f32')
                        audio.tofile(raw)
                        out = os.path.join(td, f'a.{opts.fmt}')
                        await asyncio.to_thread(encode, raw, out, opts)
                        key = f'{job.id}.{opts.fmt}'
                        with open(out, 'rb') as f:
                            data = f.read()
                        await kvs.set_value(key, data, content_type=mime)
                    rec['audioUrl'] = await kvs.get_public_url(key)
                    if inp.get('_debug'):
                        Actor.log.info(f'{job.id}: {chars} chars -> {len(audio) / SAMPLE_RATE:.1f} s audio in {time.time() - t0:.1f} s')
                    rec.update(format=opts.fmt, fileSizeKB=round(len(data) / 1024, 1),
                               durationSeconds=round(len(audio) / SAMPLE_RATE, 2), sentenceCount=len(sents),
                               processingSeconds=round(time.time() - t0, 1))
                    for sub, fn, ctype in (('srt', to_srt, 'application/x-subrip; charset=utf-8'),
                                           ('vtt', to_vtt, 'text/vtt; charset=utf-8')):
                        if sub in opts.subtitles:
                            await kvs.set_value(f'{job.id}.{sub}', fn(sents), content_type=ctype)
                            rec[f'{sub}Url'] = await kvs.get_public_url(f'{job.id}.{sub}')
                    if opts.include_sentences:
                        rec['sentences'] = sents
                    res = await Actor.charge(EVENT, count=need)
                    rec['billedUnits'] = res.charged_count
                    billed_total += res.charged_count
                    total_chars += chars
                    done += 1
                    if merged_raw:
                        if merged_sents:
                            gap = np.zeros(SAMPLE_RATE, dtype=np.float32)
                            merged_raw.write(gap.tobytes())
                            merged_t += 1.0
                        merged_raw.write(audio.tobytes())
                        merged_sents += [{**s, 'start': round(s['start'] + merged_t, 3), 'end': round(s['end'] + merged_t, 3)} for s in sents]
                        merged_t += len(audio) / SAMPLE_RATE
                except (InputError, BlockedAddressError) as e:
                    rec['error'] = str(e)[:300]
                except httpx.HTTPError as e:
                    rec['error'] = f'Download failed: {type(e).__name__}'
                except Exception as e:  # noqa: BLE001 - one bad text must not kill the batch
                    Actor.log.exception('Text failed')
                    rec['error'] = f'Processing failed: {str(e)[:200]}'
                if 'error' in rec:
                    rec['billedUnits'] = 0
                await Actor.push_data(rec)
        if merged_raw:
            merged_raw.close()
            try:
                if merged_sents:
                    with tempfile.TemporaryDirectory() as td:
                        out = os.path.join(td, f'all.{opts.fmt}')
                        await asyncio.to_thread(encode, merged_raw.name, out, opts)
                        with open(out, 'rb') as f:
                            await kvs.set_value(f'all-texts.{opts.fmt}', f.read(), content_type=mime)
                    if 'srt' in opts.subtitles:
                        await kvs.set_value('all-texts.srt', to_srt(merged_sents), content_type='application/x-subrip; charset=utf-8')
                    if 'vtt' in opts.subtitles:
                        await kvs.set_value('all-texts.vtt', to_vtt(merged_sents), content_type='text/vtt; charset=utf-8')
                    Actor.log.info(f'Merged file: {await kvs.get_public_url(f"all-texts.{opts.fmt}")}')
            finally:
                os.unlink(merged_raw.name)
        msg = f'Done: {done}/{len(queue)} text(s), {total_chars:,} characters, {billed_total} x 100 characters billed'
        if budget_hit:
            msg += ' (some texts skipped: max charge reached)'
        await Actor.set_status_message(msg, is_terminal=True)
