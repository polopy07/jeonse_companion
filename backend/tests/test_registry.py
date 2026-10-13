"""등기부 요약 파서 (FR-005). 샘플은 tests/fixtures/registry의 가상 데이터."""
from pathlib import Path

import pytest

from app.registry import RegistryParseError, parse_registry_pdf, parse_summary_text
from app.registry.pdf import page_text

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


def test_iros_summary_apartment_with_two_mortgages():
    # 인터넷등기소 "부동산정보요약"을 PDF로 저장한 실제 샘플 (이름·주소·번호는 가림)
    s = parse_summary_text(load("iros_apartment_mortgage.txt"))
    assert s.owners == ["김가상"]
    assert [(m.rank, m.amount, m.holder) for m in s.mortgages] == [
        ("15", 40_200_000, "주식회사가상은행"),
        ("16", 50_000_000, "주식회사가상은행"),
    ]
    assert s.to_fields() == {"seizure": False, "mortgage": True, "mortgage_amount": 90_200_000, "trust": False}
    assert s.others == [] and s.warnings == []
    # 순위번호 줄보다 위에 찍힌 접수일은 그 행에 붙는다
    assert "2021년10월26일" in s.mortgages[0].text and "2024년10월28일" not in s.mortgages[0].text
    assert "2024년10월28일" in s.mortgages[1].text


def test_iros_summary_coowners_without_records():
    s = parse_summary_text(load("iros_villa_coowners.txt"))
    assert s.owners == ["이가상", "박가상"]
    assert s.to_fields() == {"seizure": False, "mortgage": False, "mortgage_amount": 0, "trust": False}
    assert s.others == [] and s.warnings == []


def test_iros_summary_trust():
    # 신탁회사 공매 중인 다세대 (실제 샘플). 수탁자 이름이 법인번호 줄 위아래로 갈라지고,
    # 갑구 신탁 주의사항은 등기목적("약정/금지사항/환매특약")이 행 위아래로 갈라져 나온다
    s = parse_summary_text(load("iros_trust.txt"))
    assert s.owners == ["가상자산신탁주식회사"] and s.trustee_owner
    assert [(e.rank, e.purpose) for e in s.trusts] == [("2-1", "신탁 주의사항")]
    assert s.to_fields() == {"seizure": False, "mortgage": False, "mortgage_amount": 0, "trust": True}
    assert s.others == [] and s.warnings == []


def test_iros_summary_auction_with_registered_lease():
    # 경매 진행 중인 다세대 (실제 샘플). 임차권설정은 근저당 합계에 넣지 않고 사용자 확인으로 넘긴다
    s = parse_summary_text(load("iros_auction_lease.txt"))
    assert s.owners == ["문가상"]
    assert [(e.rank, e.purpose) for e in s.seizures] == [("3", "임의경매개시결정")]
    assert [(e.rank, e.purpose) for e in s.others] == [("5", "임차권설정")]
    assert "임차보증금 금90,000,000원" in s.others[0].text
    assert s.to_fields() == {"seizure": True, "mortgage": False, "mortgage_amount": 0, "trust": False}
    assert s.warnings == ["을구 5번 '임차권설정' 등기가 있습니다. 선순위 채권에 넣을지 직접 확인하세요"]


def test_owner_name_split_only_around_id_line():
    # 이름 조각 → 번호 줄 → 나머지 이름일 때만 붙인다. 앞 사람 주소가 줄바꿈된 경우는 붙이지 않는다
    section = "센텀아이파크\n김가상 (공유자) 000000-******* 2분의 1 3\n"
    text = "부동산정보요약\n소유지분현황(갑구)\n" + section + "소유지분을 제외한 소유권에 대한 사항 (갑구)\n- 기록사항 없음\n"
    assert parse_summary_text(text).owners == ["김가상"]


def test_iros_summary_pending_registration_warns():
    text = load("iros_apartment_mortgage.txt").replace(
        "이 부동산 등기기록에 기재된 신청사건 접수 정보는 없습니다.", "2026년10월13일 제00000호 근저당권설정 처리 중")
    assert any("처리 중인 등기 신청" in w for w in parse_summary_text(text).warnings)


def test_iros_summary_ignores_checklists_after_summary():
    # 권리변동 예정사항 뒤의 점검사항 안내 글은 읽지 않는다
    text = load("iros_villa_coowners.txt") + "임대차 관련 주요 점검사항\n신탁 등기, 압류 등기가 있는지 확인하세요\n"
    assert parse_summary_text(text).to_fields()["trust"] is False
    assert parse_summary_text(text).to_fields()["seizure"] is False


def test_iros_summary_seizures_and_auctions():
    # 압류 3건·가압류 4건·강제경매·임의경매가 걸린 실제 샘플 (경매 진행 중인 집, 이름·주소·번호는 가림)
    s = parse_summary_text(load("iros_seizures_auction.txt"))
    assert s.owners == ["최가상"]
    assert [(e.rank, e.purpose) for e in s.seizures] == [
        ("9", "압류"), ("10", "가압류"), ("11", "가압류"), ("12", "강제경매개시결정"), ("13", "압류"),
        ("14", "가압류"), ("15", "가압류"), ("16", "압류"), ("17", "임의경매개시결정"),
    ]
    assert [(m.rank, m.amount, m.holder) for m in s.mortgages] == [("3", 220_000_000, "주식회사가상은행")]
    assert s.to_fields() == {"seizure": True, "mortgage": True, "mortgage_amount": 220_000_000, "trust": False}
    assert s.others == [] and s.warnings == []
    # 각 행에 자기 접수일이 붙는다 (다음 행 날짜가 섞이지 않음)
    assert "2024년10월10일" in s.seizures[0].text and "2024년10월25일" not in s.seizures[0].text
    assert "2025년11월5일" in s.seizures[-1].text


def test_iros_summary_holder_stuck_to_owner_name():
    # 근저당권자와 대상소유자가 띄어쓰기 없이 붙어 나와도 근저당권자만 남긴다
    text = load("iros_seizures_auction.txt").replace("주식회사가상은행 최가상", "주식회사가상은행최가상")
    assert parse_summary_text(text).mortgages[0].holder == "주식회사가상은행"


def test_iros_summary_holder_with_space():
    # "주식회사 하나은행"처럼 띄어 쓴 근저당권자도 이름 전체를 남긴다 (갑구에는 실제로 이렇게 나옴)
    text = load("iros_seizures_auction.txt").replace("근저당권자 주식회사가상은행 최가상", "근저당권자 주식회사 가상은행 최가상")
    assert parse_summary_text(text).mortgages[0].holder == "주식회사 가상은행"


def test_iros_summary_three_line_row():
    # 주요등기사항이 길어 행이 세 줄이면 첫 줄이 "날짜 + 채권최고액"이다. 다음 항목(15번)에 붙여야 금액을 읽는다
    text = load("iros_apartment_mortgage.txt").replace(
        "2021년10월26일\n15 근저당권설정 채권최고액 금40,200,000원 근저당권자 주식회사가상은행 김가상",
        "2021년10월26일 채권최고액 금40,200,000원\n15 근저당권설정 근저당권자 주식회사가상은행 김가상")
    s = parse_summary_text(text)
    assert [(m.rank, m.amount, m.holder) for m in s.mortgages] == [
        ("15", 40_200_000, "주식회사가상은행"), ("16", 50_000_000, "주식회사가상은행")]
    assert s.warnings == []


class _FakePage:
    def __init__(self, chars):
        self.chars = chars


def _chars(text: str, x: float, top: float, width: float = 11.0) -> list[dict]:
    return [{"text": t, "x0": x + i * width, "x1": x + i * width + width - 1, "top": top} for i, t in enumerate(text)]


def test_page_text_keeps_overflowing_column_apart():
    # 근저당권자 칸이 대상소유자 칸까지 넘쳐 x 좌표가 섞여도, PDF에 적힌 순서대로 두 조각으로 읽는다
    chars = (_chars("근저당권자", 476, 54) + _chars("주식회사가상은행", 534.2, 54)
             + _chars("김가상", 579.4, 54) + _chars("2021년10월26일", 218, 48, 7))
    assert page_text(_FakePage(chars)) == "2021년10월26일\n근저당권자 주식회사가상은행 김가상"


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
    detail = r.json()["detail"]
    assert detail["code"] == "REGISTRY_UNREADABLE"
    assert "수동 입력" in detail["hint"]
