# AI Audio Studio Pro v6.0

Tkinter desktop app: text-to-speech (Microsoft Edge neural voices via `edge-tts`) for
English, Bangla, Hindi and Sanskrit (via Hindi voice), with presets, batch processing,
preset packs and a YouTube-ready package exporter.

## Run

```bat
pip install -r requirements.txt
python main.py
```

FFmpeg is optional but recommended (needed for WAV output and multi-chunk merging).
Set `FFMPEG_PATH` env var or place ffmpeg at one of the default locations in `main.py`.

## Changes in v6.0 (bug fixes + modernization)

- Fixed `merge_wav_files`: compared full `wave.getparams()` (includes `nframes`), so
  merging multi-chunk WAV always raised "WAV format mismatch". Now compares only
  channel/sample-width/rate/compression.
- Single-chunk MP3 output is now saved with the proper final filename
  (previously kept the `__part001.mp3` temp name).
- Temporary `__part*` files are deleted after merging/conversion.
- Rate/Pitch/Volume of `0` are now honored (`+0%`/`+0Hz` are valid for edge-tts);
  removed `_nonzero_int` which silently turned 0 into +1.
- `merge_mp3_files`: ffmpeg concat list now escapes Windows paths/quotes and the
  real ffmpeg error (stderr) is shown on failure.
- Text chunking splits on Bengali danda (`।`, `॥`) as well.
- Batch processing now uses the same chunk+merge pipeline as single generation
  (long files no longer fail; temp files cleaned).
- Restored corrupted UI strings: window title separator, language label
  (বাংলা / हिन्दी / संस्कृत) and all button emojis.
- Cross-platform folder opening (`os.startfile` guarded for win32/macOS/Linux).
- `pygame.mixer.init()` guarded so the app still starts on PCs without audio output.
- Shared `synthesize_text()` pipeline for single + batch generation.

## Files

- `main.py` — application
- `enhancer.py` — text cleaning/enhancement (SSML stripping, Bengali danda, pauses)
- `requirements.txt` — dependencies (edge-tts==7.2.8 verified on PyPI, pygame>=2.5.0)
- `audio_studio_settings.json` — saved settings (compatible with v5.1)
