import sys
import types

import pytest

from diana import voice


class FakeCommunicate:
    def __init__(self, text, voice_name, rate, pitch):
        self.voice_name = voice_name

    async def stream(self):
        yield {"type": "WordBoundary"}
        for i in range(3):
            yield {"type": "audio", "data": b"mp3-%d" % i}


def test_speech_text_strips_markdown_links_and_code():
    text = "**Hello** [docs](https://x.test) see https://y.test\n```\ncode\n```\n- item"
    assert voice.speech_text(text) == "Hello docs see (code omitted) item"


def test_speech_text_truncates_at_sentence_boundary():
    out = voice.speech_text("This is a sentence. " * 200)
    assert len(out) <= voice.MAX_SPEECH_CHARS
    assert out.endswith(".")


def test_pick_voice_detects_urdu():
    assert voice.pick_voice("Hello there") == voice.VOICE_EN
    assert voice.pick_voice("سلام، آپ کیسے ہیں؟") == voice.VOICE_UR


def test_tts_stream_yields_audio(monkeypatch):
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    assert b"".join(voice.tts_stream("Hello")) == b"mp3-0mp3-1mp3-2"


def test_tts_stream_raises_when_service_fails(monkeypatch):
    class Broken(FakeCommunicate):
        async def stream(self):
            if True:
                raise ConnectionError("offline")
            yield {}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Broken))
    with pytest.raises(ConnectionError):
        voice.tts_stream("Hello")


def test_transcribe_requires_key(monkeypatch):
    monkeypatch.setattr(voice, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError):
        voice.transcribe(object())
