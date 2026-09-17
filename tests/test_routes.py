import io


def test_index_and_static_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b"DIANA" in page.data
    for path in ("/static/css/style.css", "/static/js/app.js", "/static/js/voice.js"):
        assert client.get(path).status_code == 200, path
        assert path.encode() in page.data


def test_health(client):
    data = client.get("/api/health").get_json()
    assert data["status"] == "ok"
    assert data["llm_configured"] in (True, False)


def test_chat_requires_user_message(client):
    assert client.post("/api/chat", json={}).status_code == 400
    assert client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 400


def test_chat_runs_agent(client, monkeypatch):
    monkeypatch.setattr("diana.agent.groq_chat", lambda *a, **k: {"content": "At your service."})
    response = client.post("/api/chat", json={"text": "Hello"})
    assert response.get_json()["reply"] == "At your service."


def test_export_download(client):
    response = client.post("/api/export", json={"title": "Plan", "content": "- step one", "format": "pdf"})
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "Plan.pdf" in response.headers["Content-Disposition"]
    assert client.post("/api/export", json={"title": "Plan", "content": "", "format": "pdf"}).status_code == 400


def test_tts_errors(client, monkeypatch):
    assert client.get("/api/tts?text=").status_code == 400

    def unavailable(text):
        raise ConnectionError("offline")

    monkeypatch.setattr("diana.routes.tts_stream", unavailable)
    assert client.get("/api/tts?text=Hello").status_code == 503


def test_transcribe(client, monkeypatch):
    assert client.post("/api/transcribe").status_code == 400
    monkeypatch.setattr("diana.routes.transcribe", lambda audio: "hello there")
    response = client.post("/api/transcribe", data={"audio": (io.BytesIO(b"fake"), "clip.webm")},
                           content_type="multipart/form-data")
    assert response.get_json() == {"text": "hello there"}
