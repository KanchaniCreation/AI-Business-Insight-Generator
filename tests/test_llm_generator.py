import json

import pytest
import requests

from src import llm_generator as lg
from src.exceptions import LLMConfigError, LLMRateLimitError, LLMResponseError
from src.pipeline import run_analysis

GOOD = {"executive_summary": "Revenue rose 20.0% in September 2026, led by North.",
        "key_growth_drivers": ["North grew 50.0%."], "negative_contributors": ["West fell 10.0%."],
        "risks_to_investigate": ["Investigate West."], "recommended_actions": ["Review West pricing."]}


class FakeResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        return self._body


def anthropic_ok(payload_dict):
    return FakeResponse(200, {"content": [{"type": "text", "text": json.dumps(payload_dict)}]})


@pytest.fixture
def payload(small_clean_df):
    return run_analysis(small_clean_df).payload


@pytest.fixture
def cfg():
    return lg.LLMConfig(provider="anthropic", api_key="test-key", backoff_seconds=0, max_retries=2)


def patch_post(monkeypatch, responses):
    calls = {"n": 0}

    def fake_post(*a, **k):
        r = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(lg.requests, "post", fake_post)
    return calls


# ---------------- parsing / validation
def test_parse_json_with_code_fences():
    assert lg.parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_surrounding_text():
    assert lg.parse_json_response('Sure! Here it is: {"a": 1} Hope that helps.') == {"a": 1}


@pytest.mark.parametrize("bad", ["", "no json here", "{broken json"])
def test_parse_json_rejects_garbage(bad):
    with pytest.raises(LLMResponseError):
        lg.parse_json_response(bad)


def test_validate_report_requires_summary():
    with pytest.raises(LLMResponseError):
        lg.validate_report({"key_growth_drivers": []})


def test_lists_are_normalised():
    r = lg.validate_report({"executive_summary": "A long enough summary.", "key_growth_drivers": "single string", "risks_to_investigate": None})
    assert r.key_growth_drivers == ["single string"] and r.risks_to_investigate == []


# ---------------- hallucination guard
def test_unsupported_numbers_are_detected(payload):
    report = lg.AIInsightReport(executive_summary="Revenue rose 87.3% which is great news for everyone.")
    assert 87.3 in lg.find_unsupported_numbers(report, payload)


def test_supported_numbers_pass(payload):
    report = lg.AIInsightReport(executive_summary="Revenue grew 20.0% to ₹2,400 from ₹2,000 in 2026.")
    assert lg.find_unsupported_numbers(report, payload) == []


# ---------------- API behaviour
def test_successful_call(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [anthropic_ok(GOOD)])
    report, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "llm" and report.key_growth_drivers == ["North grew 50.0%."]


def test_openai_style_response(monkeypatch, payload):
    cfg = lg.LLMConfig(provider="openai", api_key="k", model="x", backoff_seconds=0)
    patch_post(monkeypatch, [FakeResponse(200, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "llm"


def test_retry_then_success(monkeypatch, payload, cfg):
    calls = patch_post(monkeypatch, [FakeResponse(500), FakeResponse(429), anthropic_ok(GOOD)])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "llm" and calls["n"] == 3


def test_rate_limit_falls_back(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [FakeResponse(429)])
    report, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "fallback" and "rate limit" in meta["warnings"][0].lower()
    assert report.executive_summary


def test_rate_limit_raises_when_fallback_disabled(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [FakeResponse(429)])
    with pytest.raises(LLMRateLimitError):
        lg.generate_insights(payload, cfg, allow_fallback=False)


def test_network_failure_falls_back(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [requests.ConnectionError("down")])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "fallback"


def test_bad_key_gives_config_error(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [FakeResponse(401, text="unauthorized")])
    with pytest.raises(LLMConfigError):
        lg.generate_insights(payload, cfg, allow_fallback=False)


def test_missing_key_falls_back_without_calling_api(monkeypatch, payload):
    calls = patch_post(monkeypatch, [anthropic_ok(GOOD)])
    _, meta = lg.generate_insights(payload, lg.LLMConfig(api_key=""))
    assert meta["source"] == "fallback" and calls["n"] == 0


def test_invalid_json_then_repair_succeeds(monkeypatch, payload, cfg):
    bad = FakeResponse(200, {"content": [{"type": "text", "text": "I cannot do JSON, sorry"}]})
    calls = patch_post(monkeypatch, [bad, anthropic_ok(GOOD)])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "llm" and calls["n"] == 2


def test_always_invalid_json_falls_back(monkeypatch, payload, cfg):
    bad = FakeResponse(200, {"content": [{"type": "text", "text": "nope"}]})
    patch_post(monkeypatch, [bad])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "fallback"


def test_unexpected_response_shape_falls_back(monkeypatch, payload, cfg):
    patch_post(monkeypatch, [FakeResponse(200, {"weird": True})])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "fallback"


def test_hallucinated_number_creates_warning(monkeypatch, payload, cfg):
    bad = dict(GOOD, executive_summary="Revenue exploded by 87.3% this month, a record result.")
    patch_post(monkeypatch, [anthropic_ok(bad)])
    _, meta = lg.generate_insights(payload, cfg)
    assert meta["source"] == "llm" and 87.3 in meta["unsupported_numbers"] and meta["warnings"]


# ---------------- prompt + secrets
def test_prompt_contains_grounding_rules_and_no_raw_rows(payload):
    assert "Do NOT invent" in lg.SYSTEM_PROMPT and "unsupported causal claims" in lg.SYSTEM_PROMPT
    assert "ORD-" not in lg.build_user_prompt(payload)


def test_api_key_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc123")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    c = lg.LLMConfig.from_env()
    assert c.api_key == "abc123" and c.provider == "openai"


def test_placeholder_key_is_rejected():
    with pytest.raises(LLMConfigError):
        lg.LLMConfig(api_key="your_key_here").validate()


def test_fallback_report_uses_only_payload(payload):
    report = lg.generate_fallback_report(payload)
    assert "20.0%" in report.executive_summary
    assert lg.find_unsupported_numbers(report, payload) == []


def test_warning_shows_readable_number_and_the_sentence(monkeypatch, payload, cfg):
    bad = dict(GOOD, executive_summary="Revenue rose to about 3,700,000 this month, a strong result overall.")
    patch_post(monkeypatch, [anthropic_ok(bad)])
    _, meta = lg.generate_insights(payload, cfg)
    text = meta["warnings"][0]
    assert "3,700,000" in text and "e+06" not in text and "strong result" in text


def test_format_number_never_uses_scientific_notation():
    assert lg.format_number(3700000.0) == "3,700,000" and lg.format_number(87.3) == "87.3" and lg.format_number(12.0) == "12"


def test_prompt_forbids_rounding_and_new_numbers():
    assert "do NOT round" in lg.SYSTEM_PROMPT and "Do NOT calculate new numbers" in lg.SYSTEM_PROMPT
