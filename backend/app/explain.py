"""등기 항목 쉬운 말 설명 (FR-007, 명세서 8장 AI-REQ-01~05, rules/explain.yaml).

사용자가 확인한 등기 항목(종류·등기 목적·금액)만 LLM에 보낸다. 소유자·권리자 이름, 원문 글자, 주소는 보내지 않는다
(AI-REQ-05). 항목마다 템플릿 설명을 사실 근거로 함께 보내고, 돌아온 설명은 금지 표현과 숫자를 검사한다.
LLM이 꺼져 있거나 실패·시간 초과·검사 탈락이면 템플릿 설명을 쓴다 (AI-REQ-04). 판정·비율은 여기서 바뀌지 않는다.
"""
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from app.config import llm_explain_enabled, llm_model

logger = logging.getLogger(__name__)
_CACHE_SIZE = 256


@dataclass(frozen=True)
class Item:
    id: str
    kind: str             # mortgage / lease / seizure / trust / other
    purpose: str          # 등기 목적 (예: 근저당권설정)
    amount: int | None    # 채권최고액·보증금 (원)


@dataclass
class Explanation:
    id: str
    kind: str
    text: str
    source: str           # llm / template


def money_label(won: int) -> str:
    """1억 2,000만 원 / 3,500만 원 / 1,234,567원 (만 원 단위가 아니면 원 단위 그대로)."""
    if won % 10_000:
        return f"{won:,}원"
    eok, man = divmod(won // 10_000, 10_000)
    if eok and man:
        return f"{eok}억 {man:,}만 원"
    return f"{eok}억 원" if eok else f"{man:,}만 원"


def template(item: Item, cfg: dict) -> str:
    templates = cfg["templates"]
    if item.kind in ("mortgage", "lease"):
        if not item.amount:
            return templates[f"{item.kind}_no_amount"]
        return templates[item.kind].format(amount=money_label(item.amount))
    return templates.get(item.kind, templates["other"])


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text.replace(",", "")))


def passes_checks(text: str, item: Item, rules: dict) -> bool:
    """금지 표현이 없고(AI-REQ-03), 템플릿에 없는 숫자를 새로 쓰지 않았고(AI-REQ-01), 길이 안이면 통과."""
    cfg = rules["explain"]
    text = text.strip()
    if not text or len(text) > cfg["llm"]["max_chars"]:
        return False
    forbidden = rules["verdict"]["display"]["forbidden_phrases"] + cfg["forbidden_phrases"]
    if any(phrase in text for phrase in forbidden):
        return False
    return _numbers(text) <= _numbers(template(item, cfg))


class _Cache:
    """같은 항목 묶음은 다시 부르지 않는다 (시연에서 같은 등기부를 여러 번 올려도 비용·대기 없이)."""

    def __init__(self, size: int):
        self.size, self.data, self.lock = size, OrderedDict(), Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
            return self.data.get(key)

    def put(self, key, value) -> None:
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


_cache = _Cache(_CACHE_SIZE)


def _user_prompt(items: list[Item], cfg: dict) -> str:
    rows = [{"id": i.id, "등기 목적": i.purpose, "금액": money_label(i.amount) if i.amount else None,
             "기준 설명": template(i, cfg)} for i in items]
    return "다음 등기 항목들을 쉬운 말로 설명해 주세요.\n" + json.dumps(rows, ensure_ascii=False, indent=1)


_SCHEMA = {
    "type": "object",
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["explanations"],
    "additionalProperties": False,
}


def call_llm(items: list[Item], cfg: dict) -> dict[str, str]:
    """Claude API 1회 호출 → {id: 설명}. 실패하면 예외 (부르는 쪽에서 템플릿으로 바꿈). 테스트는 이 함수를 바꿔 끼운다."""
    import anthropic   # LLM을 끈 환경(테스트·CI)에서는 불러오지 않는다

    llm = cfg["llm"]
    client = anthropic.Anthropic(timeout=llm["timeout_seconds"], max_retries=0)   # 재시도하면 대기가 늘어 템플릿으로
    response = client.beta.messages.create(
        model=llm_model(llm["model"]),
        max_tokens=4000,
        system=cfg["system_prompt"],
        messages=[{"role": "user", "content": _user_prompt(items, cfg)}],
        output_config={"effort": llm["effort"], "format": {"type": "json_schema", "schema": _SCHEMA}},
        # 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도 (거절 범주별 기본 경로)
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason != "end_turn":   # refusal·max_tokens 등은 템플릿
        raise RuntimeError(f"LLM stop_reason={response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    return {e["id"]: e["text"] for e in json.loads(text)["explanations"]}


def explain(items: list[Item], rules: dict) -> list[Explanation]:
    """항목마다 설명. LLM 결과가 없거나 검사에 걸린 항목은 템플릿 (AI-REQ-03·04)."""
    cfg = rules["explain"]
    llm_texts: dict[str, str] = {}
    if items and llm_explain_enabled():
        key = (llm_model(cfg["llm"]["model"]), str(cfg["version"]),
               tuple((i.id, i.kind, i.purpose, i.amount) for i in items))
        llm_texts = _cache.get(key)
        if llm_texts is None:
            try:
                llm_texts = call_llm(items, cfg)
                _cache.put(key, llm_texts)
            except Exception as e:   # 어떤 실패든 판정·화면은 계속 (NFR-007)
                logger.warning("LLM 설명 실패, 템플릿으로 대체: %s", e)
                llm_texts = {}
    out = []
    for item in items:
        text = (llm_texts.get(item.id) or "").strip()
        if text and passes_checks(text, item, rules):
            out.append(Explanation(item.id, item.kind, text, "llm"))
        else:
            out.append(Explanation(item.id, item.kind, template(item, cfg), "template"))
    return out
