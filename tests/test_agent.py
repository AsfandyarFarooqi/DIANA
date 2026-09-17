import json

import pytest
import requests

from diana import agent


def tool_call(name, args, call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeGroq:
    """Replays scripted assistant messages and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, messages, tool_choice="auto", use_tools=True):
        self.calls.append({"messages": list(messages), "tool_choice": tool_choice, "use_tools": use_tools})
        return self.responses.pop(0)


def user(text):
    return [{"role": "user", "content": text}]


def test_calculate_is_exact_and_safe():
    assert agent.calculate("(12.5*4)/2 + 2^3") == "33.0"
    with pytest.raises(ValueError):
        agent.calculate("__import__('os').system('echo hi')")
    with pytest.raises(ValueError):
        agent.calculate("2**5000")


def test_direct_answer(monkeypatch):
    monkeypatch.setattr(agent, "groq_chat", FakeGroq({"content": "Good evening."}))
    result = agent.run_agent(user("Hello"))
    assert result == {"reply": "Good evening.", "documents": [], "trace": []}


def test_tool_result_is_fed_back_to_model(monkeypatch):
    fake = FakeGroq(
        {"content": "", "tool_calls": [tool_call("calculate", {"expression": "0.18*2450+375"})]},
        {"content": "That comes to **816**."},
    )
    monkeypatch.setattr(agent, "groq_chat", fake)
    result = agent.run_agent(user("What is 18% of 2450 plus 375?"))
    assert result["reply"] == "That comes to **816**."
    assert result["trace"] == [{"tool": "calculate", "detail": "0.18*2450+375"}]
    tool_messages = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"]
    assert tool_messages[0]["content"] == "816.0"


def test_document_mode_forces_tool_and_skips_extra_round(monkeypatch):
    fake = FakeGroq({"content": "", "tool_calls": [tool_call("create_document", {
        "title": "Thank-You Note", "content": "# Thank You\n\nDear team,\nWell done."})]})
    monkeypatch.setattr(agent, "groq_chat", fake)
    result = agent.run_agent(user("Write a thank-you note"), mode="document")
    assert len(fake.calls) == 1
    assert fake.calls[0]["tool_choice"] == {"type": "function", "function": {"name": "create_document"}}
    doc = result["documents"][0]
    assert doc["title"] == "Thank-You Note"
    assert doc["content"] == "Dear team,\nWell done."  # repeated title heading removed
    assert "Thank-You Note" in result["reply"]


def test_document_mode_falls_back_to_plain_text(monkeypatch):
    monkeypatch.setattr(agent, "groq_chat", FakeGroq({"content": "Dear Sir,\nI resign."}))
    result = agent.run_agent(user("Resignation letter"), mode="document")
    assert result["documents"][0]["content"] == "Dear Sir,\nI resign."


def test_malformed_tool_call_retries_without_tools(monkeypatch):
    calls = []

    def fake(messages, tool_choice="auto", use_tools=True):
        calls.append(use_tools)
        if use_tools:
            raise agent.ToolUseFailed("bad tool call")
        return {"content": "Plain answer."}

    monkeypatch.setattr(agent, "groq_chat", fake)
    assert agent.run_agent(user("Hi"))["reply"] == "Plain answer."
    assert calls == [True, False]


def test_history_is_trimmed(monkeypatch):
    fake = FakeGroq({"content": "ok"})
    monkeypatch.setattr(agent, "groq_chat", fake)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(21)]
    agent.run_agent(history)
    assert len(fake.calls[0]["messages"]) == 1 + agent.MAX_HISTORY  # system prompt + recent messages


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.setattr(agent, "GROQ_API_KEY", "")
    assert "GROQ_API_KEY" in agent.run_agent(user("Hi"))["reply"]


def test_network_failure_is_graceful(monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(agent, "groq_chat", down)
    result = agent.run_agent(user("Hi"))
    assert result["error"] is True
    assert "trouble" in result["reply"]


def test_web_search_without_key():
    assert "not configured" in agent.web_search("anything")


def test_web_search_summarises_results(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"answerBox": {"answer": "42"},
                    "organic": [{"title": "Result", "snippet": "Snippet", "link": "https://example.test"}]}

    monkeypatch.setattr(agent, "SERPER_API_KEY", "key")
    monkeypatch.setattr(agent._http, "post", lambda *a, **k: FakeResponse())
    out = agent.web_search("meaning of life")
    assert "Answer box: 42" in out
    assert "https://example.test" in out
