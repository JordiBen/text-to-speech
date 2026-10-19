# Text to Speech: Natural AI Voices, MP3 + SRT Subtitles (Kokoro TTS, No API Key)

[![Run on Apify](https://img.shields.io/badge/Run%20on-Apify-1f6feb?logo=apify)](https://apify.com/manageable_gully/text-to-speech) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Run it in the cloud with no setup:** [Text to Speech: AI Voices, MP3 + SRT Subtitles, No API Key on the Apify Store](https://apify.com/manageable_gully/text-to-speech).  
> Pay only per result, export to JSON/CSV/Excel, schedule runs and call it from the API.
<!-- Note: the Apify Store page goes live once the Actor is published. -->
<!-- AFFILIATE_LINK_PLACEHOLDER: replace the Apify links above with the affiliate link when available -->

Turn **text, scripts, articles and Markdown into natural-sounding speech** with **Kokoro**, the open-source AI voice model that tops community TTS rankings for its size. Choose from **41 voices in 7 languages** (US and UK English, Spanish, French, Italian, Brazilian Portuguese, Hindi), get **MP3, WAV, Opus, M4A or FLAC** audio plus **SRT/WebVTT subtitles with exact sentence timings**, and convert **hundreds of texts in one run**. No ElevenLabs or OpenAI account, no API key, no setup. You pay only for what you convert: **$0.04 per 1,000 characters**.

## What you can use it for
- **YouTube, TikTok and Reels voiceovers:** turn a script into a clean voice track plus matching SRT captions for your editor.
- **Faceless video channels and shorts automation:** generate dozens of voiceovers in one batch from n8n, Make, Zapier or your own code.
- **Audiobooks and article narration:** read long chapters (up to 200,000 characters per text) and merge them into one file.
- **E-learning and product demos:** consistent narration for courses, explainer videos and onboarding flows.
- **Podcast intros, ads and IVR / phone menus:** short prompts in MP3 or WAV.
- **Accessibility:** listen-to-this-article audio for blogs and newsletters.
- **AI agents:** give an LLM agent a voice via the Apify API or MCP server.

## How to use it
1. Paste one or more texts (each becomes its own audio file), or pass `items` with an id, voice and speed per text, or link `.txt`/`.md` files.
2. Pick a **voice**, **speed** and **audio format**. Optionally blend two voices into your own custom voice.
3. Click **Start**. Each text becomes one result row with links to the audio file and subtitle files.

## Pricing
Billing is per started 100 characters of each text ($0.004), counted after Markdown cleanup, plus a tiny start fee. **Subtitles, merged files and texts that fail are free.**

| Job | Characters | Price |
|---|---|---|
| A 60-second YouTube Short script | ~900 | **$0.036** |
| 50 product video voiceovers | 50 x 600 = 30,000 | **$1.20** |
| A 10-minute explainer narration | ~9,000 | **$0.36** |
| A full 60,000-word audiobook | ~350,000 (split into chapters) | **$14.00** |

That's less than half the price of the other Kokoro Actor on the Store, and a fraction of what ElevenLabs charges per character.

## Voices
| Language | Voices (female / male) |
|---|---|
| English (US) | `af_heart` (best), `af_bella`, `af_nicole`, `af_aoede`, `af_kore`, `af_sarah`, `af_nova`, `af_sky`, `af_alloy`, `af_jessica`, `af_river` / `am_michael`, `am_fenrir`, `am_puck`, `am_echo`, `am_eric`, `am_liam`, `am_onyx`, `am_adam`, `am_santa` |
| English (UK) | `bf_emma`, `bf_isabella`, `bf_alice`, `bf_lily` / `bm_george`, `bm_fable`, `bm_lewis`, `bm_daniel` |
| Spanish | `ef_dora` / `em_alex`, `em_santa` |
| French | `ff_siwis` |
| Italian | `if_sara` / `im_nicola` |
| Portuguese (Brazil) | `pf_dora` / `pm_alex`, `pm_santa` |
| Hindi | `hf_alpha`, `hf_beta` / `hm_omega`, `hm_psi` |

The first letter of the voice sets the language and accent. **Voice blending:** `af_heart:0.6, af_bella:0.4` mixes two (or more) voices of the same language into a new voice that nobody else on your niche is using.

## Features
- **Natural AI voices** from the Kokoro-82M model (Apache-2.0, 8-bit quantized), run inside the Actor on CPU. Your text is never sent to a third-party AI API.
- **5 audio formats:** MP3, WAV, Opus (OGG), M4A/AAC and FLAC, with selectable bitrate.
- **Exact SRT and WebVTT subtitles:** every sentence is generated separately and timed to the millisecond, then split into readable 2-line captions.
- **Bulk:** up to 1,000 texts and 1,000,000 characters per run; per-text voice and speed overrides.
- **Markdown-aware:** headings, bold, bullet points, code blocks and link URLs are cleaned up so they are not read aloud (ChatGPT/Claude scripts work as-is).
- **Natural pacing:** configurable pauses between sentences and paragraphs; speed from 0.5x to 2.0x.
- **Merge into one file:** optional `all-texts.mp3` with merged subtitles, for audiobooks and playlists.
- **Sentence timings in JSON** for karaoke captions, video editors and word highlighting.
- **Budget safe:** before each text it checks your run's max cost and skips texts that would exceed it (not charged).

## Input example
```json
{
  "texts": ["# Why speed matters\n\nA slow page loses visitors before they ever see your offer. This **tool** checks every page on your site and tells you what to fix first."],
  "items": [
    {"id": "es-promo", "text": "El informe mensual estará listo el próximo lunes por la mañana.", "voice": "ef_dora"},
    {"id": "uk-intro", "text": "Please check the website before the meeting on Thursday.", "voice": "bm_george", "speed": 1.1}
  ],
  "voice": "af_heart",
  "format": "mp3",
  "subtitles": "both",
  "mergeIntoOneFile": true
}
```

## Output example (one item per text)
```json
{
  "id": "text-1",
  "source": "input",
  "voice": "af_heart",
  "language": "English (US)",
  "speed": 1.0,
  "characters": 206,
  "textPreview": "Why speed matters.\n\nA slow page loses visitors before they ever see your offer. This tool checks every page on your site and tells you what to fix first. ...",
  "audioUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/text-1.mp3",
  "format": "mp3",
  "fileSizeKB": 207.0,
  "durationSeconds": 13.16,
  "sentenceCount": 4,
  "processingSeconds": 3.6,
  "srtUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/text-1.srt",
  "vttUrl": "https://api.apify.com/v2/key-value-stores/<store-id>/records/text-1.vtt",
  "billedUnits": 3
}
```
SRT file:
```
1
00:00:00,000 --> 00:00:01,173
Why speed matters.

2
00:00:01,773 --> 00:00:05,421
A slow page loses visitors before they
ever see your offer.
```

## Use it from code, n8n or AI agents
Call it through the Apify API (`POST https://api.apify.com/v2/acts/manageable_gully~text-to-speech/run-sync-get-dataset-items`), the Apify Python/JavaScript clients, the Apify n8n/Make/Zapier integrations, or as a tool for AI agents through the Apify MCP server. The `audioUrl` in each result is a direct download link.

## FAQ
**Do I need an ElevenLabs, OpenAI or Google API key?** No. The voice model runs inside the Actor.

**Can I use the audio commercially (YouTube monetization, ads, courses)?** The Kokoro model and its voices are released under the Apache-2.0 license, which allows commercial use. You are responsible for the text you convert.

**Can it clone my voice or a celebrity voice?** No, on purpose. You can only use the built-in voices or blend them.

**Japanese or Chinese?** Not yet. Kokoro needs a special phonemizer for them and the quality isn't good enough to charge for.

**How long can a text be?** Up to 200,000 characters per text (about 3.5 hours of speech) and 1,000,000 characters per run. Split whole books into chapters.

**How fast is it?** Roughly 50-75 seconds of processing per 1,000 characters (about 1 minute of speech) at the default 4 GB memory. Long jobs run unattended in the cloud; schedule them or call the API and collect the files when the run finishes.

**Can I read a web page aloud?** Convert it to clean text first with [Web Page to Markdown](https://apify.com/manageable_gully/page-to-markdown), then pass the text here.

## More tools from WebIntel Tools
- [Audio & Video Transcriber (speech to text)](https://apify.com/manageable_gully/audio-video-transcriber)
- [Web Page to Markdown for LLMs](https://apify.com/manageable_gully/page-to-markdown)
- [PDF & Image OCR to Text/Markdown](https://apify.com/manageable_gully/pdf-ocr-extractor)
- [URL to PDF & Screenshot](https://apify.com/manageable_gully/url-to-pdf-screenshot)

## Run from source
This repository is the full source of the [Text to Speech: AI Voices, MP3 + SRT Subtitles, No API Key](https://apify.com/manageable_gully/text-to-speech) Actor.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest
# run locally with the Apify CLI (https://docs.apify.com/cli):
apify run --input '{...}'
```

Deploy your own copy with `apify push`. The easiest way to use it is the hosted version on the [Apify Store](https://apify.com/manageable_gully/text-to-speech).

<!-- AFFILIATE_LINK_PLACEHOLDER: "New to Apify? Sign up here" link goes here -->

## License
MIT, see [LICENSE](LICENSE).
