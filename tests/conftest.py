import pytest

from diana import create_app


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never touch the network or depend on the developer's real keys."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted during tests")

    monkeypatch.setattr("requests.Session.request", blocked)
    monkeypatch.setattr("diana.agent.GROQ_API_KEY", "test-key")
    monkeypatch.setattr("diana.agent.SERPER_API_KEY", "")
    monkeypatch.setattr("diana.voice.GROQ_API_KEY", "test-key")


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()
