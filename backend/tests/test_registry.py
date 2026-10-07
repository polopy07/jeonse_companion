"""등기부 요약 파서 (FR-005). 샘플은 tests/fixtures/registry의 가상 데이터."""
from pathlib import Path

import pytest

from app.registry import RegistryParseError, parse_registry_pdf, parse_summary_text

FIXTURES = Path(__file__).parent / "fixtures" / "registry"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_villa_with_two_mortgages():
    s = parse_summary_text(load("villa_mortgage.txt"))
    assert s.owners == ["홍길동"]
    assert [(m.rank, m.amount, m.holder) for m in s.mortgages] == [
        ("1", 120_000_000, "주식회사가상은행"),
        ("4", 36_000_000, "가상캐피탈주식회사"),
    ]
    assert s.to_fields() == {"seizure": False, "mortgage": True, "mortgage_amount": 156_000_000, "trust": False}
    assert s.warnings == []


def test_apartment_without_records():
    s = parse_summary_text(load("apartment_clean.txt"))
    assert s.owners == ["김가상", "이가상"]
    assert s.to_fields() == {"seizure": False, "mortgage": False, "mortgage_amount": 0, "trust": False}
    assert s.others == [] and s.warnings == []


def test_trust_seizure_and_entries_left_to_user():
    s = parse_summary_text(load("trust_seizure.txt"))
    assert s.owners == ["가상신탁주식회사"]
    assert s.trustee_owner
    assert [e.purpose for e in s.trusts] == ["신탁"]
    assert [e.purpose for e in s.seizures] == ["가압류"]
    # 변경 등기(2-1)와 전세권은 합계에 넣지 않고 사용자 확인으로 넘긴다
    assert [(m.rank, m.amount) for m in s.mortgages] == [("2", 240_000_000)]
    assert [(e.rank, e.purpose) for e in s.others] == [("2-1", "근저당권변경"), ("3", "전세권설정")]
    assert len(s.warnings) == 2
    assert s.to_fields() == {"seizure": True, "mortgage": True, "mortgage_amount": 240_000_000, "trust": True}


def test_continuation_lines_join_into_one_entry():
    s = parse_summary_text(load("trust_seizure.txt"))
    assert "채권자 가상대부주식회사" in s.seizures[0].text


def test_notes_section_is_ignored():
    # 참고사항에 "신탁"이 있어도 신탁 등기로 보지 않는다
    text = load("apartment_clean.txt") + "다. 신탁 등기가 있는 경우 신탁원부를 확인하시기 바랍니다.\n"
    assert parse_summary_text(text).trust is False


def test_unreadable_amount_warns():
    text = load("villa_mortgage.txt").replace("채권최고액 금36,000,000원", "채권최고액 (읽을 수 없음)")
    s = parse_summary_text(text)
    assert s.mortgages[1].amount is None
    assert s.mortgage_amount == 120_000_000
    assert any("채권최고액을 읽지 못했습니다" in w for w in s.warnings)


def test_spaced_amount():
    text = load("villa_mortgage.txt").replace("금120,000,000원", "금 120,000,000 원")
    assert parse_summary_text(text).mortgages[0].amount == 120_000_000


def test_missing_section_warns():
    text = load("villa_mortgage.txt").replace("3. (근)저당권 및 전세권 등 ( 을구 )", "")
    s = parse_summary_text(text)
    assert any("을구" in w for w in s.warnings)


@pytest.mark.parametrize("text", ["등기사항전부증명서\n【 갑 구 】", "주요 등기사항 요약 (참고용)\n내용 없음"])
def test_not_a_summary_page(text):
    with pytest.raises(RegistryParseError):
        parse_summary_text(text)


def test_pdf_finds_summary_page():
    s = parse_registry_pdf((FIXTURES / "villa_mortgage.pdf").read_bytes())
    assert s.owners == ["홍길동"]
    assert s.mortgage_amount == 156_000_000


def test_broken_pdf():
    with pytest.raises(RegistryParseError):
        parse_registry_pdf(b"not a pdf")


def test_api_parse(client):
    pdf = (FIXTURES / "villa_mortgage.pdf").read_bytes()
    r = client.post("/api/registry/parse", files={"file": ("registry.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fields"] == {"seizure": False, "mortgage": True, "mortgage_amount": 156_000_000, "trust": False}
    assert body["owners"] == ["홍길동"]
    assert [m["amount"] for m in body["mortgages"]] == [120_000_000, 36_000_000]


def test_api_parse_result_feeds_check(client):
    pdf = (FIXTURES / "villa_mortgage.pdf").read_bytes()
    fields = client.post("/api/registry/parse", files={"file": ("r.pdf", pdf, "application/pdf")}).json()["fields"]
    r = client.post("/api/checks", json={
        "housing_type": "row_house", "deposit": 100_000_000, "official_price": 200_000_000, "registry": fields,
    })
    assert r.status_code == 201, r.text
    assert r.json()["ratio_is_minimum"] is False


def test_api_parse_failure_points_to_manual_input(client):
    r = client.post("/api/registry/parse", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 422
    assert "수동 입력" in r.json()["detail"]["hint"]
