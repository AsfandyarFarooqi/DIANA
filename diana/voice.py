"""Voice I/O: streamed neural TTS (edge-tts) and speech-to-text (Groq Whisper)."""
import asyncio
import queue
import re
import threading

import requests

from .config import GROQ_API_KEY, TTS_PITCH, TTS_RATE
from .config import GROQ_STT_MODEL as STT_MODEL
from .config import TTS_VOICE as VOICE_EN  # composed British male voice — the "JARVIS" register
from .config import TTS_VOICE_UR as VOICE_UR

MAX_SPEECH_CHARS = 1400

_http = requests.Session()


def speech_text(text):
    """Strip Markdown, links and code so the voice reads naturally."""
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_SPEECH_CHARS:
        cut = text[:MAX_SPEECH_CHARS]
        text = cut[: max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! ")) + 1] or cut
    return text


def pick_voice(text):
    return VOICE_UR if re.search(r"[؀-ۿ]", text) else VOICE_EN


class TTSStream:
    """Iterable of MP3 chunks. Synthesis runs on a worker thread with its own event loop;
    close() — called by the WSGI server when the client stops listening — cancels it cleanly.
    Waits for the first chunk up front so failures surface as an HTTP error, not a silent stream."""

    def __init__(self, text):
        self._text = text
        self._queue = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        try:
            first = self._queue.get(timeout=20)
        except queue.Empty:
            first = TimeoutError("TTS service timed out")
        if first is None or isinstance(first, BaseException):
            self._stop.set()
            raise first if isinstance(first, BaseException) else RuntimeError("TTS returned no audio")
        self._first = first

    def _put(self, item):
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.5)
                return
            except queue.Full:
                pass

    def _run(self):
        async def produce():
            import edge_tts

            communicate = edge_tts.Communicate(self._text, pick_voice(self._text), rate=TTS_RATE, pitch=TTS_PITCH)
            async for chunk in communicate.stream():
                if self._stop.is_set():
                    break
                if chunk["type"] == "audio":
                    self._put(chunk["data"])

        try:
            asyncio.run(produce())  # asyncio.run also finalizes the stream if we broke out early
        except Exception as e:
            self._put(e)
        self._put(None)

    def __iter__(self):
        return self

    def __next__(self):
        if self._first is not None:
            chunk, self._first = self._first, None
            return chunk
        try:
            item = self._queue.get(timeout=30)
        except queue.Empty:
            item = None
        if item is None or isinstance(item, BaseException):
            self._stop.set()
            raise StopIteration
        return item

    def close(self):
        self._stop.set()


def tts_stream(text):
    return TTSStream(text)


def transcribe(file_storage):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    files = {"file": (file_storage.filename or "audio.webm", file_storage.stream, file_storage.mimetype)}
    res = _http.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        data={"model": STT_MODEL, "response_format": "json"},
        files=files,
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Transcription failed ({res.status_code}): {res.text[:200]}")
    return res.json().get("text", "").strip()
