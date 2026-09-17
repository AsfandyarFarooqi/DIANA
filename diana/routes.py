"""HTTP routes: the single-page console and its JSON / audio API."""
from flask import Blueprint, Response, jsonify, render_template, request, send_file

from . import config
from .agent import run_agent
from .documents import export_document
from .voice import speech_text, transcribe, tts_stream

bp = Blueprint("diana", __name__)


@bp.get("/")
def index():
    return render_template("index.html", model=config.GROQ_MODEL)


@bp.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "model": config.GROQ_MODEL,
        "llm_configured": bool(config.GROQ_API_KEY),
        "search_configured": bool(config.SERPER_API_KEY),
    })


@bp.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    history = data.get("messages") or []
    if not history and data.get("text"):
        history = [{"role": "user", "content": data["text"]}]
    if not history or history[-1].get("role") != "user" or not str(history[-1].get("content", "")).strip():
        return jsonify({"error": "No message provided."}), 400
    return jsonify(run_agent(history, mode=data.get("mode", "chat")))


@bp.post("/api/transcribe")
def api_transcribe():
    audio = request.files.get("audio")
    if not audio:
        return jsonify({"error": "No audio uploaded."}), 400
    try:
        return jsonify({"text": transcribe(audio)})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.get("/api/tts")
def api_tts():
    text = speech_text(request.args.get("text", ""))
    if not text:
        return jsonify({"error": "Nothing to say."}), 400
    try:
        stream = tts_stream(text)
    except Exception as e:
        return jsonify({"error": f"TTS unavailable: {e}"}), 503
    return Response(stream, mimetype="audio/mpeg", headers={"Cache-Control": "no-store"})


@bp.post("/api/export")
def api_export():
    data = request.get_json(silent=True) or {}
    try:
        buf, mime, filename = export_document(
            data.get("title") or "Untitled Document", data.get("content", ""), data.get("format", "docx"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return send_file(buf, mimetype=mime, as_attachment=True, download_name=filename)
