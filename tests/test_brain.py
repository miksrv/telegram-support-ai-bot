from core.brain import classify_and_reply


def _patch_llm(monkeypatch, raw_response=None, raise_exc=None):
    def fake_complete(messages, *, temperature, max_tokens, json_mode=True):
        if raise_exc:
            raise raise_exc
        return raw_response

    monkeypatch.setattr("core.brain.llm_engine.complete", fake_complete)


def test_classify_and_reply_returns_relevant_answer(monkeypatch):
    _patch_llm(monkeypatch, raw_response='{"relevant": true, "reply": "16 августа"}')
    verdict = classify_and_reply("Когда выезд?", "проект", "выезд 16 августа", [], False)
    assert verdict == {"relevant": True, "reply": "16 августа"}


def test_classify_and_reply_returns_not_relevant(monkeypatch):
    _patch_llm(monkeypatch, raw_response='{"relevant": false, "reply": ""}')
    verdict = classify_and_reply("Как дела?", "проект", "выезд", [], False)
    assert verdict == {"relevant": False, "reply": ""}


def test_classify_and_reply_falls_back_on_invalid_json(monkeypatch):
    _patch_llm(monkeypatch, raw_response="not json at all")
    verdict = classify_and_reply("Когда выезд?", "проект", "выезд", [], False)
    assert verdict == {"relevant": False, "reply": ""}


def test_classify_and_reply_falls_back_on_missing_keys(monkeypatch):
    _patch_llm(monkeypatch, raw_response='{"foo": "bar"}')
    verdict = classify_and_reply("Когда выезд?", "проект", "выезд", [], False)
    assert verdict == {"relevant": False, "reply": ""}


def test_classify_and_reply_falls_back_on_wrong_types(monkeypatch):
    _patch_llm(monkeypatch, raw_response='{"relevant": "yes", "reply": null}')
    verdict = classify_and_reply("Когда выезд?", "проект", "выезд", [], False)
    assert verdict == {"relevant": False, "reply": ""}


def test_classify_and_reply_falls_back_when_llm_call_raises(monkeypatch):
    _patch_llm(monkeypatch, raise_exc=RuntimeError("network error"))
    verdict = classify_and_reply("Когда выезд?", "проект", "выезд", [], False)
    assert verdict == {"relevant": False, "reply": ""}
