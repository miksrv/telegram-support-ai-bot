from core.prompts import build_system_prompt


def test_prompt_includes_project_and_trip_context():
    prompt = build_system_prompt("Общая инфа про сообщество", "Выезд 16 августа", [], False)
    assert "Общая инфа про сообщество" in prompt
    assert "Выезд 16 августа" in prompt


def test_prompt_omits_empty_context_blocks():
    prompt = build_system_prompt("", "", [], False)
    assert "Project context:" not in prompt
    assert "Current trip context:" not in prompt


def test_prompt_includes_history():
    history = [{"text": "Когда выезд?", "reply_text": "16 августа"}]
    prompt = build_system_prompt("", "", history, False)
    assert "Когда выезд?" in prompt
    assert "16 августа" in prompt


def test_prompt_adds_reply_to_bot_instruction_only_when_true():
    prompt_true = build_system_prompt("", "", [], True)
    prompt_false = build_system_prompt("", "", [], False)
    assert "ALWAYS" in prompt_true
    assert "ALWAYS" not in prompt_false


def test_prompt_requests_strict_json_contract():
    prompt = build_system_prompt("", "", [], False)
    assert '"relevant"' in prompt
    assert '"reply"' in prompt
