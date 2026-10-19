import os
import re

import pytest

from src import tts
from src.tts import InputError


def test_parse_minimal_and_defaults():
    jobs, urls, o = tts.parse_input({'texts': ['Hello there.', '  ', 'Second.']})
    assert [j.id for j in jobs] == ['text-1', 'text-2'] and urls == []
    assert o.voice == 'af_heart' and o.fmt == 'mp3' and o.subtitles == ['srt'] and o.speed == 1.0


@pytest.mark.parametrize('inp', [{}, {'texts': ['x'], 'voice': 'jf_alpha'}, {'texts': ['x'], 'speed': 3},
                                 {'texts': ['x'], 'format': 'aiff'}, {'items': [{'id': 'a'}]},
                                 {'texts': ['x'], 'voiceBlend': 'af_heart:0.5,bf_emma:0.5'},
                                 {'texts': ['x'], 'subtitles': 'ass'}])
def test_parse_rejects(inp):
    with pytest.raises(InputError):
        tts.parse_input(inp)


def test_items_overrides_and_unique_ids():
    jobs, _, _ = tts.parse_input({'items': [{'id': 'Intro clip!', 'text': 'a', 'voice': 'bm_george', 'speed': 1.2},
                                            {'id': 'Intro clip!', 'text': 'b'}]})
    assert jobs[0].id == 'Intro-clip' and jobs[1].id == 'Intro-clip-2'
    assert jobs[0].voice == 'bm_george' and jobs[0].speed == 1.2 and jobs[1].voice == 'af_heart'


def test_blend_normalized():
    _, _, o = tts.parse_input({'texts': ['x'], 'voiceBlend': 'af_heart:3, af_bella:1'})
    assert o.blend == [('af_heart', 0.75), ('af_bella', 0.25)] and o.voice == 'af_heart'


def test_every_voice_has_supported_language():
    assert len(tts.VOICES) == 41
    assert all(v[0] in tts.LANG_BY_PREFIX for v in tts.VOICES)


def test_clean_markdown():
    md = ('# Big News\n\nThis is **bold**, *italic* and a [link](https://x.y).\n\n- item one\n- item two\n\n'
          '```python\nprint(1)\n```\n| a | b |\n|---|---|\n| 1 | 2 |')
    c = tts.clean_text(md)
    assert 'Big News.' in c and 'bold' in c and '**' not in c and 'https' not in c and 'print' not in c
    assert '- item' not in c and 'item one' in c and '---' not in c
    assert tts.clean_text('**x**', strip_markdown=False) == '**x**'


def test_billing_units():
    assert tts.units(0) == 0 and tts.units(1) == 1 and tts.units(100) == 1 and tts.units(101) == 2
    assert tts.billable_chars('a  b\n\nc ') == 5


def test_chunking_limits_and_paragraphs():
    text = ('One. Two is here! ' * 30) + '\n\n' + ('word ' * 200)
    ch = tts.chunk_text(tts.clean_text(text))
    assert all(len(c) <= tts.MAX_CHUNK for c, _ in ch)
    assert sum(1 for _, p in ch if p) == 2
    joined = ' '.join(c for c, _ in ch)
    assert re.sub(r'\s+', '', joined) == re.sub(r'\s+', '', tts.clean_text(text))


def test_subtitles_format():
    sents = [{'start': 0.0, 'end': 2.5, 'text': 'Hello world.'},
             {'start': 2.75, 'end': 3661.2, 'text': 'A much longer sentence ' * 6}]
    srt = tts.to_srt(sents)
    assert srt.startswith('1\n00:00:00,000 --> 00:00:02,500\nHello world.')
    assert '01:01:01,200' in srt
    vtt = tts.to_vtt(sents)
    assert vtt.startswith('WEBVTT') and '00:00:02.750 -->' in vtt


MODEL_DIR = os.environ.get('KOKORO_MODEL_DIR', '/models')


@pytest.mark.skipif(not os.path.exists(os.path.join(MODEL_DIR, 'kokoro-v1.0.onnx')), reason='Kokoro model not available')
def test_end_to_end_synthesis(tmp_path):
    from src import main
    jobs, _, o = tts.parse_input({'texts': ['Hello from the cloud. This is a short test!\n\nSecond paragraph.'],
                                  'voiceBlend': 'af_heart:0.6,af_bella:0.4'})
    audio, sents = main.synthesize(jobs[0], tts.clean_text(jobs[0].text), o)
    assert len(sents) == 3 and audio.dtype.name == 'float32'
    assert all(a['end'] > a['start'] for a in sents) and sents[1]['start'] >= sents[0]['end']
    assert abs(len(audio) / main.SAMPLE_RATE - sents[-1]['end']) < 0.05
    raw = tmp_path / 'a.f32'
    audio.tofile(raw)
    for fmt in ('mp3', 'opus'):
        o.fmt = fmt
        out = tmp_path / f'a.{fmt}'
        main.encode(str(raw), str(out), o)
        assert out.stat().st_size > 1000


def test_heading_keeps_paragraph_break():
    ch = tts.chunk_text(tts.clean_text('# Title\n\nBody text here.'))
    assert ch == [('Title.', True), ('Body text here.', True)]
