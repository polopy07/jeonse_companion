"""등기부 "주요 등기사항 요약" 글자 → 항목 (규칙 파서).

요약 페이지 구성 (인터넷등기소 등기사항증명서 마지막 페이지):
    주요 등기사항 요약 (참고용)
    1. 소유지분현황 ( 갑구 )                         → 소유자
    2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )  → 압류·가압류·가처분·경매개시결정, 신탁
    3. (근)저당권 및 전세권 등 ( 을구 )              → 근저당 채권최고액
    [ 참 고 사 항 ]                                  → 여기서부터는 읽지 않음

요약 페이지는 말소되지 않은 사항만 보여 준다. 표의 한 행은 PDF 글자로 바꾸면 여러 줄로
나뉘므로, "순위번호 + 등기목적"으로 시작하는 줄부터 다음 행 전까지를 한 항목으로 묶는다.

양식은 가상 샘플로 맞춘 것이다. 실제 샘플(1주차)을 받으면 정규식을 맞춘다.
자동으로 판단하기 어려운 것(변경 등기, 전세권 등)은 합계에 넣지 않고 warnings로 돌려
사용자가 확인 화면(FR-006)에서 고치게 한다.
"""
import re
from dataclasses import dataclass, field


class RegistryParseError(ValueError):
    """요약 페이지를 읽지 못함 → 수동 입력 화면으로 (FR-006, NFR-007)."""


TITLE = re.compile(r"주\s*요\s*등\s*기\s*사\s*항\s*요\s*약")
SECTION_OWNER = re.compile(r"1\s*\.\s*소\s*유\s*지\s*분\s*현\s*황")
SECTION_GAPGU = re.compile(r"2\s*\.\s*소\s*유\s*지\s*분\s*을\s*제\s*외\s*한")
SECTION_EULGU = re.compile(r"3\s*\.\s*\(\s*근\s*\)\s*저\s*당\s*권\s*및\s*전\s*세\s*권")
NOTES = re.compile(r"\[\s*참\s*고\s*사\s*항\s*\]")

ENTRY_START = re.compile(r"^\s*(\d+(?:-\d+)*)\s+([가-힣()]+)")
OWNER = re.compile(r"(\S+)\s*\(\s*(소유자|공유자|수탁자)\s*\)")
MAX_AMOUNT = re.compile(r"채\s*권\s*최\s*고\s*액\s*금\s*([\d,]+)\s*원")
MORTGAGEE = re.compile(r"근저당권자\s*(\S+)")

SEIZURE_WORDS = ("압류", "가처분", "경매개시결정")   # "압류"는 가압류도 포함
TRUST_WORD = "신탁"
MORTGAGE_WORDS = ("근저당권설정", "저당권설정")


@dataclass
class Entry:
    rank: str        # 순위번호 (예: "1", "1-1")
    purpose: str     # 등기목적 (예: "근저당권설정")
    text: str        # 행 전체 글자 (확인 화면에 원문으로 보여 줌)


@dataclass
class Mortgage(Entry):
    amount: int | None = None     # 채권최고액 (원)
    holder: str | None = None     # 근저당권자


@dataclass
class RegistrySummary:
    owners: list[str] = field(default_factory=list)
    seizures: list[Entry] = field(default_factory=list)
    trusts: list[Entry] = field(default_factory=list)
    mortgages: list[Mortgage] = field(default_factory=list)
    others: list[Entry] = field(default_factory=list)   # 분류하지 못한 등기 (사용자 확인)
    trustee_owner: bool = False                        # 소유자가 수탁자(신탁회사)로 나옴
    warnings: list[str] = field(default_factory=list)

    @property
    def trust(self) -> bool:
        return bool(self.trusts) or self.trustee_owner

    @property
    def mortgage_amount(self) -> int:
        return sum(m.amount or 0 for m in self.mortgages)

    def to_fields(self) -> dict:
        """fields.yaml의 registry.* 값 (schemas.RegistryInput과 같은 이름)."""
        return {
            "seizure": bool(self.seizures),
            "mortgage": bool(self.mortgages),
            "mortgage_amount": self.mortgage_amount,
            "trust": self.trust,
        }


def parse_summary_text(text: str) -> RegistrySummary:
    """요약 페이지 글자를 항목으로 나눈다. 요약 페이지가 아니면 RegistryParseError."""
    title = TITLE.search(text)
    if title is None:
        raise RegistryParseError('"주요 등기사항 요약" 페이지를 찾지 못했습니다')
    body = text[title.end():]
    notes = NOTES.search(body)
    if notes:
        body = body[:notes.start()]

    sections = _split_sections(body)
    if not sections:
        raise RegistryParseError("요약 페이지의 항목(소유지분현황, 갑구, 을구)을 찾지 못했습니다")

    result = RegistrySummary()
    for name, label in (("owner", "소유지분현황"), ("gapgu", "갑구"), ("eulgu", "을구")):
        if name not in sections:
            result.warnings.append(f"요약 페이지에서 {label} 항목을 찾지 못했습니다. 직접 확인하세요")
    if "owner" in sections:
        _parse_owners(sections["owner"], result)
    _parse_gapgu(sections.get("gapgu", ""), result)
    _parse_eulgu(sections.get("eulgu", ""), result)
    return result


def _split_sections(body: str) -> dict[str, str]:
    """찾은 항목만 담는다 (항목 이름 → 그 항목 머리말 뒤부터 다음 항목 전까지의 글자)."""
    marks = []
    for name, pattern in (("owner", SECTION_OWNER), ("gapgu", SECTION_GAPGU), ("eulgu", SECTION_EULGU)):
        m = pattern.search(body)
        if m:
            marks.append((m.start(), m.end(), name))
    marks.sort()
    sections = {}
    for i, (_, end, name) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        sections[name] = body[end:stop]
    return sections


def _entries(section: str) -> list[Entry]:
    entries: list[Entry] = []
    for line in section.splitlines():
        line = line.strip()
        if not line or "순위번호" in line or "기록사항 없음" in line:
            continue
        m = ENTRY_START.match(line)
        if m:
            entries.append(Entry(rank=m.group(1), purpose=m.group(2), text=line))
        elif entries:
            entries[-1].text += " " + line
    return entries


def _parse_owners(section: str, result: RegistrySummary) -> None:
    for name, role in OWNER.findall(section):
        result.owners.append(name)
        if role == "수탁자":
            result.trustee_owner = True
    if not result.owners:
        result.warnings.append("소유자를 찾지 못했습니다. 등기부의 소유자 이름을 직접 입력하세요")


def _parse_gapgu(section: str, result: RegistrySummary) -> None:
    for e in _entries(section):
        if any(w in e.purpose for w in SEIZURE_WORDS):
            result.seizures.append(e)
        elif TRUST_WORD in e.purpose:
            result.trusts.append(e)
        else:
            result.others.append(e)
            result.warnings.append(f"갑구 {e.rank}번 '{e.purpose}' 등기는 자동으로 판단하지 않았습니다. 직접 확인하세요")


def _parse_eulgu(section: str, result: RegistrySummary) -> None:
    for e in _entries(section):
        if any(w in e.purpose for w in MORTGAGE_WORDS) and "-" not in e.rank:
            amount = MAX_AMOUNT.search(e.text)
            holder = MORTGAGEE.search(e.text)
            result.mortgages.append(Mortgage(
                rank=e.rank, purpose=e.purpose, text=e.text,
                amount=int(amount.group(1).replace(",", "")) if amount else None,
                holder=holder.group(1) if holder else None,
            ))
            if amount is None:
                result.warnings.append(f"을구 {e.rank}번 근저당의 채권최고액을 읽지 못했습니다. 직접 입력하세요")
        else:
            # 변경 등기(1-1 등), 전세권·임차권 등은 합계에 넣지 않고 사용자에게 확인을 맡긴다.
            result.others.append(e)
            result.warnings.append(f"을구 {e.rank}번 '{e.purpose}' 등기가 있습니다. 선순위 채권에 넣을지 직접 확인하세요")
