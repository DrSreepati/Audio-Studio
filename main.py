import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import re
import asyncio
import wave
import subprocess
import json
from datetime import datetime
import pygame
import edge_tts
import webbrowser
import sys
import time

from enhancer import enhance_text, basic_clean

# =========================
# FFmpeg Configuration (unchanged)
# =========================
def _get_ffmpeg_exe():
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    common_paths = [
        r"C:\AI research Model\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return "ffmpeg"

FFMPEG_EXE = _get_ffmpeg_exe()
if os.path.isfile(FFMPEG_EXE):
    ffmpeg_dir = os.path.dirname(FFMPEG_EXE)
    if ffmpeg_dir and ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

# =========================
# Settings
# =========================
SETTINGS_FILE = "audio_studio_settings.json"
PRESET_PACKS_DIR = "preset_packs"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Failed to save settings:", e)

# =========================
# Helper Functions (unchanged)
# =========================
def _safe_slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r"[^a-zA-Z0-9\u0980-\u09FF _-]", "", s)
    s = s.replace(" ", "_").strip("_")
    return (s[:max_len] or "text").strip("_") or "text"

def _auto_filename(text: str, voice_label: str, preset_name: str, ext: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snippet = _safe_slug((text or "")[:60], max_len=35)
    voice = _safe_slug(voice_label, max_len=25)
    preset = _safe_slug(preset_name, max_len=18)
    return f"{voice}__{preset}__{snippet}__{ts}.{ext}"

def _fmt_rate(val: int) -> str:
    val = max(-50, min(50, int(val)))
    return f"{val:+d}%"

def _fmt_pitch(val: int) -> str:
    val = max(-80, min(80, int(val)))
    return f"{val:+d}Hz"

def _fmt_volume(val: int) -> str:
    val = max(-50, min(50, int(val)))
    return f"{val:+d}%"

def run_coro_in_new_loop(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except:
            pass

async def tts_async_mp3(text: str, voice: str, rate: int, pitch: int, volume: int, out_mp3: str):
    clean_text = basic_clean(text)
    communicate = edge_tts.Communicate(
        text=clean_text, voice=voice,
        rate=_fmt_rate(rate), pitch=_fmt_pitch(pitch), volume=_fmt_volume(volume)
    )
    await communicate.save(out_mp3)

def split_text_into_chunks(text: str, max_chars: int = 1200):
    text = (text or "").strip()
    if not text: return []
    parts = re.split(r"(?<=[\.\!\?\u0964\u0965])\s+|\n+", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    chunks, buf = [], ""
    for p in parts:
        if len(p) > max_chars:
            if buf: chunks.append(buf.strip()); buf = ""
            start = 0
            while start < len(p):
                chunks.append(p[start:start + max_chars].strip())
                start += max_chars
            continue
        if not buf:
            buf = p
        elif len(buf) + 1 + len(p) <= max_chars:
            buf = buf + " " + p
        else:
            chunks.append(buf.strip())
            buf = p
    if buf: chunks.append(buf.strip())
    return chunks

def merge_wav_files(wav_paths, out_path):
    if not wav_paths: raise ValueError("No WAV parts")
    with wave.open(wav_paths[0], "rb") as w0:
        params = w0.getparams()
        fmt = (params.nchannels, params.sampwidth, params.framerate, params.comptype, params.compname)
    with wave.open(out_path, "wb") as wout:
        wout.setparams(params)
        for wp in wav_paths:
            with wave.open(wp, "rb") as w:
                wf = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype(), w.getcompname())
                if wf != fmt: raise ValueError("WAV format mismatch")
                wout.writeframes(w.readframes(w.getnframes()))

def merge_mp3_files(mp3_paths, out_path):
    if not mp3_paths: raise ValueError("No MP3 files to merge")
    list_file = out_path + ".txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for mp3 in mp3_paths:
            safe = mp3.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
    cmd = [
        FFMPEG_EXE if os.path.isfile(FFMPEG_EXE) else "ffmpeg",
        "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        detail = (r.stderr or "").strip().splitlines()
        os.remove(list_file)
        raise RuntimeError("Failed to merge MP3 files: " + (detail[-1] if detail else "unknown ffmpeg error"))
    os.remove(list_file)

def open_folder_in_explorer(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def ffmpeg_exists() -> bool:
    if os.path.isfile(FFMPEG_EXE): return True
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return r.returncode == 0
    except:
        return False

def convert_mp3_to_wav(mp3_path: str, wav_path: str):
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg not found!")
    exe = FFMPEG_EXE if os.path.isfile(FFMPEG_EXE) else "ffmpeg"
    cmd = [exe, "-y", "-i", mp3_path, wav_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg convert failed.")

def synthesize_text(text, voice_id, rate, pitch, volume, out_path,
                    do_split, max_chars, want_wav, merge_single, progress_cb=None):
    base = os.path.splitext(out_path)[0]
    chunks = split_text_into_chunks(text, max_chars=max_chars) if do_split and len(text) > max_chars else [text]
    total = len(chunks)
    part_mp3s = []
    for i, ch in enumerate(chunks, 1):
        mp3_path = f"{base}__part{i:03d}.mp3"
        last_err = None
        for attempt in range(1, 4):
            try:
                run_coro_in_new_loop(tts_async_mp3(ch, voice_id, rate, pitch, volume, mp3_path))
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < 3:
                    time.sleep(2 * attempt)
        if last_err is not None:
            raise RuntimeError(
                f"TTS failed after 3 attempts: {last_err}\n"
                "If you see 403 'Invalid response status': run 'python -m pip install -U edge-tts' "
                "and make sure your PC date/time is synced (Settings > Time & language > Sync now)."
            )
        part_mp3s.append(mp3_path)
        if progress_cb:
            progress_cb(int((i / total) * 100))
    if total == 1:
        if want_wav:
            convert_mp3_to_wav(part_mp3s[0], out_path)
            os.remove(part_mp3s[0])
        else:
            os.replace(part_mp3s[0], out_path)
        final = out_path
    elif merge_single:
        if want_wav:
            part_wavs = []
            for p in part_mp3s:
                w = os.path.splitext(p)[0] + ".wav"
                convert_mp3_to_wav(p, w)
                part_wavs.append(w)
            merge_wav_files(part_wavs, out_path)
            for w in part_wavs:
                if os.path.exists(w):
                    os.remove(w)
        else:
            merge_mp3_files(part_mp3s, out_path)
        final = out_path
    else:
        final = part_mp3s[0]
    for p in part_mp3s:
        if p != final and os.path.exists(p):
            os.remove(p)
    return final, total


# =========================
# Main Application - v6.0
# =========================
class AudioStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Audio Studio Pro v6.0 — Hindi + Bangla + English + Sanskrit Workaround")
        self.root.geometry("1220x1080")

        os.makedirs(PRESET_PACKS_DIR, exist_ok=True)

        # =========================
        # VOICE LIBRARY v6.0 (Sanskrit workaround added)
        # =========================
        self.voice_map = {
            # Bangla
            "Bangla (Pradeep - Default Male)": "bn-BD-PradeepNeural",
            "Bangla (Nabanita - Female)": "bn-BD-NabanitaNeural",
            "Bangla (Bashkar - Male)": "bn-IN-BashkarNeural",
            "Bangla (Tanishaa - Female)": "bn-IN-TanishaaNeural",

            # Hindi
            "Hindi (Madhur - Warm Male)": "hi-IN-MadhurNeural",
            "Hindi (Swara - Sweet Female)": "hi-IN-SwaraNeural",

            # Sanskrit Workaround (uses Hindi voice)
            "Sanskrit (via Hindi Madhur - Recommended)": "hi-IN-MadhurNeural",   # NEW

            # English - US
            "US Christopher (Default)": "en-US-ChristopherNeural",
            "US Guy (Passion)": "en-US-GuyNeural",
            "US Roger (Lively)": "en-US-RogerNeural",
            "US Aria (Educational)": "en-US-AriaNeural",
            "US Jenny (Friendly)": "en-US-JennyNeural",
            "US Ava (Clear Female)": "en-US-AvaNeural",
            "US Andrew (Professional)": "en-US-AndrewNeural",
            "US Emma (Natural Female)": "en-US-EmmaNeural",
            "US Brian (Deep Male)": "en-US-BrianNeural",
            "US Ana (Young Female)": "en-US-AnaNeural",
            "US Davis (Clear Male)": "en-US-DavisNeural",

            # English - UK
            "UK Ryan (Formal)": "en-GB-RyanNeural",
            "UK Libby (Refined Female)": "en-GB-LibbyNeural",
            "UK Sonia (Warm Female)": "en-GB-SoniaNeural",
            "UK Thomas (Professional Male)": "en-GB-ThomasNeural",

            # Canadian
            "Canadian Clara (Clear Female)": "en-CA-ClaraNeural",
            "Canadian Liam (Warm Male)": "en-CA-LiamNeural",

            # Australian
            "Australian Natasha (Natural Female)": "en-AU-NatashaNeural",
            "Australian William (Friendly Male)": "en-AU-WilliamNeural",
			
			# English - Indian
            "Indian English (Neerja - Clear Female)": "en-IN-NeerjaNeural",
            "Indian English (Prabhat - Professional Male)": "en-IN-PrabhatNeural",
        }

        self.bangla_keys = [k for k in self.voice_map if k.startswith("Bangla ")]
        self.hindi_keys = [k for k in self.voice_map if k.startswith("Hindi ")]
        self.english_keys = [k for k in self.voice_map if not k.startswith(("Bangla ", "Hindi ", "Sanskrit "))]

        self.presets = {
            "Lecture": (-5, -1, +1), "Devotional": (-11, -3, +1),
            "Documentary": (-8, -2, +1), "News Broadcast": (-6, -1, +2),
            "Audiobook (Slow)": (-12, -2, +1), "Podcast (Warm)": (-7, -1, +2),
            "YouTube (Energetic)": (-4, -1, +3), "Corporate Training": (-6, -2, +2),
            "Kids / Fun": (-3, +6, +6), "Deep Narration": (-9, -4, +1),
        }

        self.preset_mode_map = {
            "Lecture": "lecture", "Devotional": "devotional", "Documentary": "documentary",
            "News Broadcast": "documentary", "Audiobook (Slow)": "devotional",
            "Podcast (Warm)": "lecture", "YouTube (Energetic)": "lecture",
            "Corporate Training": "lecture", "Kids / Fun": "lecture", "Deep Narration": "lecture",
        }

        # Variables
        self.language = tk.StringVar(value="English")
        self.voice_label = tk.StringVar()
        self.selected_preset = tk.StringVar(value="Lecture")
        self.rate = tk.IntVar(value=-5)
        self.pitch = tk.IntVar(value=-1)
        self.volume = tk.IntVar(value=1)
        self.auto_enhance = tk.BooleanVar(value=True)
        self.output_type = tk.StringVar(value="MP3")
        self.split_chunks = tk.BooleanVar(value=True)
        self.max_chars = tk.IntVar(value=1200)
        self.merge_into_single = tk.BooleanVar(value=True)
        self.output_dir = tk.StringVar(value=os.path.abspath("data"))
        self.last_file = None
        self.is_generating = False
        self.status = tk.StringVar(value="Ready.")

        self.settings = load_settings()
        self._apply_saved_settings()

        self._build_ui()
        self._apply_language_filter()
        try:
            pygame.mixer.init()
        except Exception as e:
            print("Audio playback unavailable:", e)

    def _apply_saved_settings(self):
        s = self.settings
        if s.get("last_voice"): self.voice_label.set(s["last_voice"])
        if s.get("last_preset"): self.selected_preset.set(s["last_preset"])
        if s.get("rate") is not None: self.rate.set(s["rate"])
        if s.get("pitch") is not None: self.pitch.set(s["pitch"])
        if s.get("volume") is not None: self.volume.set(s["volume"])
        if s.get("output_dir"): self.output_dir.set(s["output_dir"])
        if s.get("language"): self.language.set(s["language"])

    def _save_current_settings(self):
        save_settings({
            "last_voice": self.voice_label.get(),
            "last_preset": self.selected_preset.get(),
            "rate": self.rate.get(), "pitch": self.pitch.get(),
            "volume": self.volume.get(),
            "output_dir": self.output_dir.get(),
            "language": self.language.get(),
        })

    def _build_ui(self):
        tk.Label(self.root, text="AI Audio Studio Pro v6.0", font=("Segoe UI", 16, "bold")).pack(pady=(8, 2))

        tk.Label(self.root, text="Text (English / বাংলা / हिन्दी / संस्कृत)").pack(anchor="w", padx=12, pady=(8, 2))
        self.text = scrolledtext.ScrolledText(self.root, height=15, font=("Segoe UI", 11))
        self.text.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        top = tk.Frame(self.root)
        top.pack(fill="x", padx=12, pady=4)
        tk.Label(top, text="Language:").pack(side="left")
        tk.Radiobutton(top, text="English", variable=self.language, value="English", command=self._apply_language_filter).pack(side="left", padx=6)
        tk.Radiobutton(top, text="Bangla", variable=self.language, value="Bangla", command=self._apply_language_filter).pack(side="left", padx=6)
        tk.Radiobutton(top, text="Hindi", variable=self.language, value="Hindi", command=self._apply_language_filter).pack(side="left", padx=6)

        tk.Label(top, text="   Voice:").pack(side="left", padx=(15, 4))
        self.voice_menu = tk.OptionMenu(top, self.voice_label, "")
        self.voice_menu.pack(side="left", fill="x", expand=True)

        quick = tk.Frame(self.root)
        quick.pack(fill="x", padx=12, pady=3)
        tk.Button(quick, text="Default English", command=self.set_default_english, width=15).pack(side="left", padx=2)
        tk.Button(quick, text="Default Bangla", command=self.set_default_bangla, width=15).pack(side="left", padx=2)

        outf = tk.Frame(self.root)
        outf.pack(fill="x", padx=12, pady=4)
        tk.Label(outf, text="Output Folder:").pack(side="left")
        tk.Entry(outf, textvariable=self.output_dir, width=50).pack(side="left", padx=6)
        tk.Button(outf, text="Browse...", command=self.choose_output_folder).pack(side="left")

        opt = tk.Frame(self.root)
        opt.pack(fill="x", padx=12, pady=3)
        tk.Checkbutton(opt, text="Auto-Enhance Text", variable=self.auto_enhance).pack(side="left")
        tk.Label(opt, text="   Format:").pack(side="left", padx=(12, 4))
        tk.Radiobutton(opt, text="MP3", variable=self.output_type, value="MP3").pack(side="left")
        tk.Radiobutton(opt, text="WAV", variable=self.output_type, value="WAV").pack(side="left")

        ch = tk.Frame(self.root)
        ch.pack(fill="x", padx=12, pady=2)
        tk.Checkbutton(ch, text="Split long text", variable=self.split_chunks).pack(side="left")
        tk.Label(ch, text="Max chars:").pack(side="left", padx=(8, 2))
        tk.Entry(ch, textvariable=self.max_chars, width=6).pack(side="left")
        tk.Checkbutton(ch, text="Merge into single file", variable=self.merge_into_single).pack(side="left", padx=15)

        pros = tk.Frame(self.root)
        pros.pack(fill="x", padx=12, pady=6)
        tk.Label(pros, text="Rate (-50..+50)").grid(row=0, column=0, sticky="w")
        tk.Scale(pros, from_=-50, to=50, variable=self.rate, orient="horizontal", length=280).grid(row=0, column=1)
        tk.Label(pros, text="Pitch (-80..+80)").grid(row=1, column=0, sticky="w")
        tk.Scale(pros, from_=-80, to=80, variable=self.pitch, orient="horizontal", length=280).grid(row=1, column=1)
        tk.Label(pros, text="Volume (-50..+50)").grid(row=2, column=0, sticky="w")
        tk.Scale(pros, from_=-50, to=50, variable=self.volume, orient="horizontal", length=280).grid(row=2, column=1)

        pres_frame = tk.LabelFrame(self.root, text="Presets", padx=8, pady=6)
        pres_frame.pack(fill="x", padx=12, pady=6)
        btn_frame = tk.Frame(pres_frame)
        btn_frame.pack()
        for i, name in enumerate(self.presets.keys()):
            tk.Button(btn_frame, text=name, width=17, command=lambda n=name: self.apply_preset(n)).grid(row=i//4, column=i%4, padx=3, pady=3)

        prog_frame = tk.Frame(self.root)
        prog_frame.pack(fill="x", padx=12, pady=4)
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate", length=450)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.Label(prog_frame, text="0%", width=5)
        self.progress_label.pack(side="left", padx=6)

        act = tk.Frame(self.root)
        act.pack(pady=10)
        tk.Button(act, text="Enhance Text", command=self.enhance, width=16).pack(side="left", padx=3)
        self.btn_generate = tk.Button(act, text="▶ Generate Audio", command=self.generate, bg="#4CAF50", fg="white", width=18)
        self.btn_generate.pack(side="left", padx=3)
        tk.Button(act, text="▶ Play Last", command=self.play_last, width=12).pack(side="left", padx=3)
        tk.Button(act, text="Open Folder", command=self.open_output_folder, width=12).pack(side="left", padx=3)

        tk.Button(act, text="🧾 Batch Processing", command=self.open_batch_window, width=16, bg="#2196F3", fg="white").pack(side="left", padx=3)
        tk.Button(act, text="🎛 Preset Packs", command=self.open_preset_manager, width=14, bg="#9C27B0", fg="white").pack(side="left", padx=3)
        tk.Button(act, text="📺 YouTube Tools", command=self.open_youtube_tools, width=14, bg="#FF5722", fg="white").pack(side="left", padx=3)

        tk.Label(self.root, textvariable=self.status, fg="#333").pack(fill="x", padx=12, pady=4)

    def choose_output_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get())
        if folder: self.output_dir.set(folder)

    def open_output_folder(self):
        if os.path.isdir(self.output_dir.get()):
            open_folder_in_explorer(self.output_dir.get())

    def _apply_language_filter(self):
        lang = self.language.get()
        if lang == "Bangla":
            keys = self.bangla_keys
        elif lang == "Hindi":
            keys = self.hindi_keys
        else:
            keys = self.english_keys

        menu = self.voice_menu["menu"]
        menu.delete(0, "end")
        for k in keys:
            menu.add_command(label=k, command=lambda kk=k: self.voice_label.set(kk))

        if self.voice_label.get() not in keys:
            if lang == "Bangla":
                default = "Bangla (Pradeep - Default Male)"
            elif lang == "Hindi":
                default = "Hindi (Madhur - Warm Male)"
            else:
                default = "US Christopher (Default)"
            self.voice_label.set(default)

    def set_default_english(self):
        self.language.set("English")
        self._apply_language_filter()
        self.voice_label.set("US Christopher (Default)")

    def set_default_bangla(self):
        self.language.set("Bangla")
        self._apply_language_filter()
        self.voice_label.set("Bangla (Pradeep - Default Male)")

    def apply_preset(self, name):
        if name not in self.presets: return
        r, p, v = self.presets[name]
        self.selected_preset.set(name)
        self.rate.set(int(r))
        self.pitch.set(int(p))
        self.volume.set(int(v))

    def _enhance_mode(self):
        return self.preset_mode_map.get(self.selected_preset.get(), "lecture")

    def enhance(self):
        t = self.text.get("1.0", "end").strip()
        if not t: return
        self.text.delete("1.0", "end")
        self.text.insert("end", enhance_text(t, self._enhance_mode()))

    def generate(self):
        if self.is_generating: return
        raw_text = self.text.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning("Warning", "Please enter text.")
            return

        voice_id = self.voice_map.get(self.voice_label.get())
        if not voice_id:
            messagebox.showerror("Error", "Please select a voice.")
            return

        os.makedirs(self.output_dir.get(), exist_ok=True)
        mode = self._enhance_mode()
        text = enhance_text(raw_text, mode) if self.auto_enhance.get() else basic_clean(raw_text)

        rate = int(self.rate.get())
        pitch = int(self.pitch.get())
        volume = int(self.volume.get())

        do_split = self.split_chunks.get()
        maxc = max(300, int(self.max_chars.get() or 1200))
        want_wav = self.output_type.get() == "WAV"
        ext = "wav" if want_wav else "mp3"
        out_path = os.path.join(self.output_dir.get(), _auto_filename(text, self.voice_label.get(), self.selected_preset.get(), ext))

        self.is_generating = True
        self.btn_generate.config(state="disabled", text="Generating...")
        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self.status.set("Generating...")

        def task():
            try:
                final, total = synthesize_text(
                    text, voice_id, rate, pitch, volume, out_path,
                    do_split, maxc, want_wav, self.merge_into_single.get(),
                    progress_cb=lambda v: self.root.after(0, lambda vv=v: self._update_progress(vv)),
                )
                self.last_file = final
                self.root.after(0, lambda: self._on_success(f"Saved: {os.path.basename(final)} ({total} chunk(s))"))
            except Exception as e:
                self.root.after(0, lambda err=str(e): self._on_error(err))

        threading.Thread(target=task, daemon=True).start()

    def _update_progress(self, value):
        self.progress["value"] = value
        self.progress_label.config(text=f"{value}%")

    def _on_success(self, msg):
        self.is_generating = False
        self.btn_generate.config(state="normal", text="▶ Generate Audio")
        self.progress["value"] = 100
        self.progress_label.config(text="100%")
        self.status.set("Done! " + msg)
        self._save_current_settings()
        messagebox.showinfo("Success", msg)

    def _on_error(self, err):
        self.is_generating = False
        self.btn_generate.config(state="normal", text="▶ Generate Audio")
        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self.status.set("Error occurred.")
        messagebox.showerror("Error", err)

    def play_last(self):
        if self.last_file and os.path.exists(self.last_file):
            try:
                pygame.mixer.music.load(self.last_file)
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror("Playback Error", str(e))

    def open_batch_window(self):
        win = tk.Toplevel(self.root)
        win.title("Batch Processing - AI Audio Studio v6.0")
        win.geometry("750x520")

        tk.Label(win, text="Batch Process Multiple Text Files", font=("Segoe UI", 14, "bold")).pack(pady=10)

        self.batch_files = []
        self.batch_listbox = tk.Listbox(win, height=12, width=80)
        self.batch_listbox.pack(padx=15, pady=10)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Add .txt Files", command=self._add_batch_files, width=18).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Remove Selected", command=self._remove_batch_file, width=18).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Clear All", command=self._clear_batch, width=12).pack(side="left", padx=5)

        tk.Button(win, text="▶ PROCESS ALL FILES (Same Settings)", command=self._process_batch, 
                  bg="#4CAF50", fg="white", width=35, height=2).pack(pady=15)

        tk.Label(win, text="All files will use current Voice + Preset + Rate/Pitch/Volume settings", 
                 fg="#666").pack()

    def _add_batch_files(self):
        files = filedialog.askopenfilenames(title="Select text files", filetypes=[("Text Files", "*.txt")])
        for f in files:
            if f not in self.batch_files:
                self.batch_files.append(f)
                self.batch_listbox.insert("end", os.path.basename(f))

    def _remove_batch_file(self):
        sel = self.batch_listbox.curselection()
        if sel:
            idx = sel[0]
            self.batch_listbox.delete(idx)
            del self.batch_files[idx]

    def _clear_batch(self):
        self.batch_listbox.delete(0, "end")
        self.batch_files = []

    def _process_batch(self):
        if not self.batch_files:
            messagebox.showwarning("No Files", "Please add some .txt files first.")
            return

        voice_id = self.voice_map.get(self.voice_label.get())
        if not voice_id:
            messagebox.showerror("Error", "Please select a voice in main window.")
            return

        rate = int(self.rate.get())
        pitch = int(self.pitch.get())
        volume = int(self.volume.get())
        mode = self._enhance_mode()
        want_wav = self.output_type.get() == "WAV"
        ext = "wav" if want_wav else "mp3"

        os.makedirs(self.output_dir.get(), exist_ok=True)

        def batch_task():
            total = len(self.batch_files)
            for i, filepath in enumerate(self.batch_files, 1):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_text = f.read().strip()
                    if not raw_text: continue

                    text = enhance_text(raw_text, mode) if self.auto_enhance.get() else basic_clean(raw_text)
                    base_name = os.path.splitext(os.path.basename(filepath))[0]
                    out_path = os.path.join(self.output_dir.get(), f"{base_name}__batch__{datetime.now().strftime('%H%M%S')}.{ext}")
                    maxc = max(300, int(self.max_chars.get() or 1200))
                    synthesize_text(text, voice_id, rate, pitch, volume, out_path,
                                    self.split_chunks.get(), maxc, want_wav,
                                    self.merge_into_single.get())

                    self.root.after(0, lambda msg=f"Processed {i}/{total}: {base_name}": self.status.set(msg))

                except Exception as e:
                    self.root.after(0, lambda err=str(e): messagebox.showerror("Batch Error", err))

            self.root.after(0, lambda: messagebox.showinfo("Batch Complete", f"Successfully processed {total} files!"))

        threading.Thread(target=batch_task, daemon=True).start()
        messagebox.showinfo("Batch Started", "Batch processing started in background. Check status bar.")

    def open_preset_manager(self):
        win = tk.Toplevel(self.root)
        win.title("Preset Packs Manager - v6.0")
        win.geometry("600x400")

        tk.Label(win, text="Save & Load Your Favorite Settings", font=("Segoe UI", 13, "bold")).pack(pady=10)

        exp_frame = tk.LabelFrame(win, text="Export Current Settings as Preset Pack")
        exp_frame.pack(fill="x", padx=15, pady=8)
        tk.Label(exp_frame, text="Pack Name:").pack(side="left", padx=5)
        self.pack_name_var = tk.StringVar(value="My_Custom_Preset")
        tk.Entry(exp_frame, textvariable=self.pack_name_var, width=25).pack(side="left", padx=5)
        tk.Button(exp_frame, text="💾 Export Pack", command=self._export_preset_pack, bg="#9C27B0", fg="white").pack(side="left", padx=10)

        imp_frame = tk.LabelFrame(win, text="Load Saved Preset Packs")
        imp_frame.pack(fill="both", expand=True, padx=15, pady=8)

        self.pack_listbox = tk.Listbox(imp_frame, height=10)
        self.pack_listbox.pack(fill="both", expand=True, padx=10, pady=5)
        self._refresh_preset_list()

        btns = tk.Frame(imp_frame)
        btns.pack(pady=5)
        tk.Button(btns, text="✔ Apply Selected Pack", command=self._import_preset_pack, width=20).pack(side="left", padx=5)
        tk.Button(btns, text="🗑 Delete Pack", command=self._delete_preset_pack, width=15).pack(side="left", padx=5)
        tk.Button(btns, text="↻ Refresh List", command=self._refresh_preset_list, width=15).pack(side="left", padx=5)

    def _export_preset_pack(self):
        name = self.pack_name_var.get().strip() or "Custom_Preset"
        safe_name = _safe_slug(name) + ".json"
        path = os.path.join(PRESET_PACKS_DIR, safe_name)

        pack_data = {
            "name": name,
            "voice": self.voice_label.get(),
            "preset": self.selected_preset.get(),
            "rate": self.rate.get(),
            "pitch": self.pitch.get(),
            "volume": self.volume.get(),
            "language": self.language.get(),
            "auto_enhance": self.auto_enhance.get(),
            "output_type": self.output_type.get(),
            "merge_into_single": self.merge_into_single.get(),
            "created": datetime.now().isoformat()
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(pack_data, f, indent=2, ensure_ascii=False)

        messagebox.showinfo("Success", f"Preset Pack saved as: {safe_name}")
        self._refresh_preset_list()

    def _refresh_preset_list(self):
        self.pack_listbox.delete(0, "end")
        if os.path.exists(PRESET_PACKS_DIR):
            for f in os.listdir(PRESET_PACKS_DIR):
                if f.endswith(".json"):
                    self.pack_listbox.insert("end", f)

    def _import_preset_pack(self):
        sel = self.pack_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a pack to load.")
            return
        filename = self.pack_listbox.get(sel[0])
        path = os.path.join(PRESET_PACKS_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                pack = json.load(f)

            self.voice_label.set(pack.get("voice", self.voice_label.get()))
            self.selected_preset.set(pack.get("preset", "Lecture"))
            self.rate.set(pack.get("rate", -5))
            self.pitch.set(pack.get("pitch", -1))
            self.volume.set(pack.get("volume", 1))
            self.language.set(pack.get("language", "English"))
            self.auto_enhance.set(pack.get("auto_enhance", True))
            self.output_type.set(pack.get("output_type", "MP3"))
            self.merge_into_single.set(pack.get("merge_into_single", True))

            self._apply_language_filter()
            messagebox.showinfo("Loaded", f"Preset Pack '{pack.get('name')}' applied successfully!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _delete_preset_pack(self):
        sel = self.pack_listbox.curselection()
        if not sel: return
        filename = self.pack_listbox.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete {filename}?"):
            os.remove(os.path.join(PRESET_PACKS_DIR, filename))
            self._refresh_preset_list()

    def open_youtube_tools(self):
        if not self.last_file or not os.path.exists(self.last_file):
            messagebox.showwarning("No Audio", "Please generate audio first.")
            return

        win = tk.Toplevel(self.root)
        win.title("🎬 YouTube Upload Ready - v6.0")
        win.geometry("620x480")

        tk.Label(win, text="Create YouTube-Ready Package", font=("Segoe UI", 14, "bold")).pack(pady=10)

        tk.Label(win, text="Video Title:").pack(anchor="w", padx=20)
        self.yt_title = tk.Entry(win, width=70)
        self.yt_title.pack(padx=20, pady=3)
        self.yt_title.insert(0, os.path.splitext(os.path.basename(self.last_file))[0][:70])

        tk.Label(win, text="Description:").pack(anchor="w", padx=20, pady=(10,0))
        self.yt_desc = scrolledtext.ScrolledText(win, height=6, width=70)
        self.yt_desc.pack(padx=20, pady=3)
        self.yt_desc.insert("end", "Created with AI Audio Studio Pro v6.0\n\n#Voiceover #AI #ContentCreation")

        tk.Label(win, text="Tags (comma separated):").pack(anchor="w", padx=20, pady=(10,0))
        self.yt_tags = tk.Entry(win, width=70)
        self.yt_tags.pack(padx=20, pady=3)
        self.yt_tags.insert(0, "ai, voiceover, bangla, hindi, sanskrit, content, youtube")

        tk.Button(win, text="🚀 Create Package + Open YouTube Studio", 
                  command=self._create_youtube_package, bg="#FF5722", fg="white", width=45, height=2).pack(pady=20)

    def _create_youtube_package(self):
        title = self.yt_title.get().strip() or "Untitled_Voiceover"
        desc = self.yt_desc.get("1.0", "end").strip()
        tags = self.yt_tags.get().strip()

        safe_title = _safe_slug(title)[:50]
        folder_name = f"YouTube_Ready_{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        folder_path = os.path.join(self.output_dir.get(), folder_name)
        os.makedirs(folder_path, exist_ok=True)

        import shutil
        dest_audio = os.path.join(folder_path, os.path.basename(self.last_file))
        shutil.copy2(self.last_file, dest_audio)

        meta_path = os.path.join(folder_path, "metadata.txt")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"Title: {title}\n\n")
            f.write(f"Description:\n{desc}\n\n")
            f.write(f"Tags: {tags}\n\n")
            f.write(f"Audio File: {os.path.basename(self.last_file)}\n")
            f.write(f"Generated by: AI Audio Studio Pro v6.0\n")

        messagebox.showinfo("Success", f"YouTube package created:\n{folder_path}")
        open_folder_in_explorer(folder_path)
        webbrowser.open_new("https://studio.youtube.com/upload")

    def on_closing(self):
        self._save_current_settings()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AudioStudio(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()