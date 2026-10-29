"""등기 항목 쉬운 말 설명 (POST /api/registry/explain, FR-007, AI-REQ-01~05). 실제 LLM은 부르지 않고 call_llm을 바꿔 끼운다."""
import pytest

from app import explain

ITEMS = [
    {"id": "을1", "kind": "mortgage", "purpose": "근저당권설정", "amount": 120_000_000},
    {"id": "을2", "kind": "lease", "purpose": "주택임차권", "amount": None},
    {"id": "갑3", "kind": "seizure", "purpose": "가압류"},
    {"id": "갑4", "kind": "trust", "purpose": "신탁"},
    {"id": "갑5", "kind": "other", "purpose": "가처분"},
]


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(explain, "_cache", explain._Cache(8))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_EXPLAIN", raising=False)


@pytest.fixture
def fake_llm(monkeypatch):
    """LLM을 켜고 call_llm 대신 정해 둔 답을 돌려준다. calls에 받은 항목을 남긴다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    state = {"answer": {}, "calls": []}

    def fake(items, cfg):
        state["calls"].append(items)
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(explain, "call_llm", fake)
    return state


def _post(client, items=ITEMS):
    return client.post("/api/registry/explain", json={"items": items})


def _by_id(r) -> dict:
    assert r.status_code == 200, r.text
    return {e["id"]: e for e in r.json()["explanations"]}


def test_money_label():
    assert explain.money_label(120_000_000) == "1억 2,000만 원"
    assert explain.money_label(200_000_000) == "2억 원"
    assert explain.money_label(35_000_000) == "3,500만 원"
    assert explain.money_label(1_234_567) == "1,234,567원"


def test_templates_without_llm(client):
    # 키가 없으면 LLM을 부르지 않고 템플릿 (AI-REQ-04, AC-013)
    out = _by_id(_post(client))
    assert list(out) == ["을1", "을2", "갑3", "갑4", "갑5"]
    assert all(e["source"] == "template" for e in out.values())
    assert "채권최고액 1억 2,000만 원" in out["을1"]["text"]
    assert "읽지 못했으니" in out["을2"]["text"]          # 금액이 없으면 _no_amount 템플릿
    assert "신탁회사" in out["갑4"]["text"] and "압류" in out["갑3"]["text"]
    assert _post(client).json()["disclaimer"] == "정보 제공이며 보증하지 않습니다."


def test_llm_text_used_when_checks_pass(client, fake_llm):
    fake_llm["answer"] = {"을1": "집주인이 이 집을 담보로 대출을 받았다는 표시예요. 최대 1억 2,000만 원까지 내 보증금보다 먼저 갚게 돼요.",
                          "갑4": "집 주인 대신 신탁회사가 소유자로 올라 있다는 뜻이에요."}
    out = _by_id(_post(client))
    assert out["을1"]["source"] == "llm" and out["갑4"]["source"] == "llm"
    assert out["갑3"]["source"] == "template"   # LLM이 빠뜨린 항목은 템플릿
    sent = fake_llm["calls"][0]
    # LLM에는 종류·등기 목적·금액만 (이름·원문 글자·주소 없음, AI-REQ-05)
    assert sent[0] == explain.Item("을1", "mortgage", "근저당권설정", 120_000_000)


@pytest.mark.parametrize("text", [
    "이 집은 안전해요. 걱정하지 마세요.",                      # 안전 단정 (verdict.yaml forbidden_phrases)
    "소송하세요. 그러면 돌려받을 수 있어요.",                  # 개별 법률 판단 (explain.yaml forbidden_phrases)
    "채권최고액 1억 5,000만 원까지 먼저 갚아요.",               # 입력에 없는 금액 (AI-REQ-01)
    "설명" * 200,                                                # 너무 김
    "   ",
])
def test_llm_text_rejected_falls_back(client, fake_llm, text):
    fake_llm["answer"] = {"을1": text}
    out = _by_id(_post(client))
    assert out["을1"]["source"] == "template" and "1억 2,000만 원" in out["을1"]["text"]


def test_llm_failure_falls_back_and_is_not_cached(client, fake_llm):
    fake_llm["answer"] = TimeoutError("8초 초과")
    out = _by_id(_post(client))
    assert all(e["source"] == "template" for e in out.values())
    fake_llm["answer"] = {"갑4": "신탁회사가 소유자로 올라 있다는 뜻이에요."}
    assert _by_id(_post(client))["갑4"]["source"] == "llm"   # 실패는 저장하지 않아 다음 요청에서 다시 부름
    assert len(fake_llm["calls"]) == 2


def test_same_items_use_cache(client, fake_llm):
    fake_llm["answer"] = {"갑4": "신탁회사가 소유자로 올라 있다는 뜻이에요."}
    _post(client)
    _post(client)
    assert len(fake_llm["calls"]) == 1
    _post(client, ITEMS[:2])   # 항목이 다르면 다시 부름
    assert len(fake_llm["calls"]) == 2


def test_llm_switch_off(client, fake_llm, monkeypatch):
    monkeypatch.setenv("LLM_EXPLAIN", "false")
    out = _by_id(_post(client))
    assert all(e["source"] == "template" for e in out.values()) and fake_llm["calls"] == []


def test_prompt_contains_only_given_facts(rules):
    items = [explain.Item("을1", "mortgage", "근저당권설정", 120_000_000)]
    prompt = explain._user_prompt(items, rules["explain"])
    assert "1억 2,000만 원" in prompt and "근저당권설정" in prompt and '"id": "을1"' in prompt


@pytest.mark.parametrize("items", [
    [ITEMS[0], {**ITEMS[1], "id": "을1"}],                              # id 겹침
    [{**ITEMS[0], "id": f"x{i}"} for i in range(21)],                  # 20개 초과
    [{"id": "a", "kind": "owner", "purpose": "소유권이전"}],             # 없는 종류
    [{"id": "a", "kind": "other", "purpose": "가" * 31}],               # 등기 목적 30자 초과
    [],
])
def test_invalid_input(client, items):
    assert _post(client, items).status_code == 422


def test_call_llm_request(monkeypatch, rules):
    # Claude API 요청 모양: 설정의 모델·짧은 시간 제한·재시도 없음, JSON 형식, 거절 시 서버 대체 모델. 거절이면 예외(→ 템플릿)
    anthropic = pytest.importorskip("anthropic")
    seen = {}

    class Block:
        type = "text"
        text = '{"explanations": [{"id": "을1", "text": "담보 대출 기록이에요."}]}'

    class Response:
        stop_reason = "end_turn"
        content = [Block()]

    class FakeClient:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.beta = self
            self.messages = self

        def create(self, **kwargs):
            seen["request"] = kwargs
            return Response()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5-5")
    items = [explain.Item("을1", "mortgage", "근저당권설정", 120_000_000)]
    assert explain.call_llm(items, rules["explain"]) == {"을1": "담보 대출 기록이에요."}
    assert seen["client"] == {"timeout": 8, "max_retries": 0}
    req = seen["request"]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["output_config"]["effort"] == "low" and req["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in req and "temperature" not in req

    Response.stop_reason = "refusal"
    with pytest.raises(RuntimeError):
        explain.call_llm(items, rules["explain"])
