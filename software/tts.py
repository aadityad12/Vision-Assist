#!/usr/bin/env python3
"""
tts.py — Threaded, non-blocking Piper TTS wrapper for VisionAssist.

Runs Piper's local neural TTS engine (no cloud, no internet dependency) and
plays the resulting audio through whatever ALSA is currently routed to —
the Bluetooth earbuds, once paired and connected. Speech requests are queued
and spoken on a background thread so the main detection loop never blocks
waiting on audio.

NOTE: This file was rebuilt from the project's design notes (Piper,
en_US-lessac-medium voice, length_scale=1.2, threaded, non-blocking) rather
than recovered from the deployed device. It is faithful to the documented
interface — speak() queues text and returns immediately — but has not been
run on hardware in this form. See README, "Reproducibility notes".
"""

import os
import queue
import subprocess
import tempfile
import threading

import pygame

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
VOICE_MODEL  = os.path.join(SCRIPT_DIR, "en_US-lessac-medium.onnx")
LENGTH_SCALE = 1.2  # >1.0 slows speech slightly for clarity while walking

pygame.mixer.init()

_speech_queue: "queue.Queue[str]" = queue.Queue()


def _synthesize_to_file(text: str, wav_path: str) -> None:
    """Run the Piper CLI and write synthesized speech to wav_path."""
    subprocess.run(
        [
            "piper",
            "--model", VOICE_MODEL,
            "--length_scale", str(LENGTH_SCALE),
            "--output_file", wav_path,
        ],
        input=text.encode("utf-8"),
        check=True,
        capture_output=True,
    )


def _worker():
    while True:
        text = _speech_queue.get()
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            _synthesize_to_file(text, wav_path)

            sound = pygame.mixer.Sound(wav_path)
            sound.play()
            while pygame.mixer.get_busy():
                pygame.time.wait(50)
        except Exception as exc:
            print(f"[tts] error speaking '{text}': {exc}")
        finally:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)
            _speech_queue.task_done()


_worker_thread = threading.Thread(target=_worker, daemon=True)
_worker_thread.start()


def speak(text: str) -> None:
    """Queue text to be spoken. Returns immediately — does not block."""
    _speech_queue.put(text)
