"""등기부 요약 글자 → 항목 (규칙 파서).

두 양식을 읽는다. 둘 다 말소되지 않은 사항만 보여 주고 항목 이름이 같다.

1) 인터넷등기소 "부동산정보요약" (열람 후 화면을 PDF로 저장, 사용자 안내 기본값)
    부동산정보요약
    소유지분현황(갑구)                              → 소유자
    소유지분을 제외한 소유권에 대한 사항 (갑구)      → 압류·가압류·가처분·경매개시결정, 신탁
    (근)저당권 및 전세권 등 (을구)                  → 근저당 채권최고액, 임차권·전세권 보증금
    권리변동 예정사항                                → 처리 중인 등기 신청이 있는지만 보고, 뒤는 읽지 않음

2) 등기사항증명서 마지막 페이지 "주요 등기사항 요약"
    주요 등기사항 요약 (참고용)
    1. 소유지분현황 ( 갑구 ) / 2. 소유지분을 제외한 ... / 3. (근)저당권 및 전세권 등 ( 을구 )
    [ 참 고 사 항 ]                                  → 여기서부터는 읽지 않음

표의 한 행은 PDF 글자로 바꾸면 여러 줄로 나뉘므로, "순위번호 + 등기목적"으로 시작하는 줄부터
다음 행 전까지를 한 항목으로 묶는다. 부동산정보요약은 접수일이 순위번호 줄보다 위에 찍혀서
날짜만 있는 줄은 다음 항목에 붙인다.

임차권·전세권 보증금은 새 세입자보다 먼저 돌려받는 돈이라 선순위 채권(lease_amount)에 넣고, 이미 돌려받았거나
내 계약이면 확인 화면(FR-006)에서 빼도록 warnings로 알린다. 자동으로 판단하기 어려운 것(변경 등기 등)은
합계에 넣지 않고 warnings로 돌려 사용자가 확인 화면에서 고치게 한다.

보증금을 못 돌려받은 세입자는 전세권설정에 더해 임차권등기를 하기도 해서, 같은 보증금이 두 항목으로 나온다.
같은 보증금으로 보이면 한 번만 넣는다 (PO 결정 2026-10-13):
    1) 임차권 줄에 "보증금 N원 중 반환되지…"가 있고 전세금 N원인 전세권이 있으면 → 임차권 금액(못 돌려받은 금액)만
    2) 전세권과 임차권의 권리자·금액이 같으면 → 하나만
뺀 항목은 same_deposit_as에 남긴 항목의 순위번호를 적고, 다른 보증금이면 확인 화면에서 다시 넣게 한다.
"""
import re
from dataclasses import dataclass, field


class RegistryParseError(ValueError):
    """요약 페이지를 읽지 못함 → 수동 입력 화면으로 (FR-006, NFR-007)."""

    NO_SUMMARY = '등기부 요약 페이지(인터넷등기소 "부동산정보요약" 또는 증명서의 "주요 등기사항 요약")를 찾지 못했습니다'


TITLE = re.compile(r"주\s*요\s*등\s*기\s*사\s*항\s*요\s*약|^\s*부\s*동\s*산\s*정\s*보\s*요\s*약\s*$", re.MULTILINE)
SECTION_OWNER = re.compile(r"(?:1\s*\.\s*)?소\s*유\s*지\s*분\s*현\s*황")
SECTION_GAPGU = re.compile(r"(?:2\s*\.\s*)?소\s*유\s*지\s*분\s*을\s*제\s*외\s*한")
SECTION_EULGU = re.compile(r"(?:3\s*\.\s*)?\(\s*근\s*\)\s*저\s*당\s*권\s*및\s*전\s*세\s*권")
NOTES = re.compile(r"\[\s*참\s*고\s*사\s*항\s*\]")
PENDING = re.compile(r"권\s*리\s*변\s*동\s*예\s*정\s*사\s*항")      # 부동산정보요약: 처리 중인 등기 신청
PENDING_END = re.compile(r"개\s*별\s*공\s*시\s*지\s*가|토\s*지\s*이\s*용\s*계\s*획|주\s*요\s*점\s*검\s*사\s*항")
NO_PENDING = re.compile(r"접\s*수\s*정\s*보\s*는\s*없\s*습\s*니\s*다")
# 부동산정보요약을 브라우저에서 PDF로 저장하면 페이지마다 붙는 머리말·꼬리말
PAGE_FURNITURE = re.compile(r"인터넷등기소\s*-\s*열람|iros\.go\.kr|^\s*\d+\s*페이지\s*/\s*\d+\s*페이지\s*$")
DATE_ONLY = re.compile(r"^\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일$")
# 행이 세 줄로 나뉘면 첫 줄이 "2021년8월20일 채권최고액 금…원"처럼 날짜로 시작한다. 날짜만 있는 줄처럼 다음 항목에 붙인다
DATE_FIRST = re.compile(r"^\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일")

ENTRY_START = re.compile(r"^\s*(\d+(?:-\d+)*)\s+([가-힣()]+)")
OWNER = re.compile(r"(\S+)\s*\(\s*(소유자|공유자|수탁자)\s*\)")
ID_LINE = re.compile(r"^\d{6}\s*-")                 # 주민등록번호(법인등록번호) 줄
NAME_PART = re.compile(r"^[^\s\d()]+$")           # 이름 조각만 있는 줄
MAX_AMOUNT = re.compile(r"채\s*권\s*최\s*고\s*액\s*금\s*([\d,]+)\s*원")
MORTGAGEE = re.compile(r"근저당권자\s*(.+)")
# 권리자 이름 뒤에 오는 것: 접수번호, 접수일, 주민(법인)등록번호, 가린 번호, 주소
HOLDER_END = re.compile(r"\s+(?:제\s*\d+\s*호|\d{4}\s*년|\d{6}\s*-|\*{3,}|[가-힣]+(?:특별시|광역시|특별자치시|도)\s)")
LEASE_AMOUNT = re.compile(r"(?:임\s*차\s*보\s*증\s*금|전\s*세\s*금)\s*금\s*([\d,]+)\s*원")
LESSEE = re.compile(r"(?:임차권자|전세권자)\s*(.+)")
# 임차권 줄의 "(보증금115,000,000원 중 반환되지 아니한 금액)": 원래 보증금 중 못 돌려받은 금액을 등기했다는 뜻
ORIGINAL_DEPOSIT = re.compile(r"보\s*증\s*금\s*금?\s*([\d,]+)\s*원\s*중")

SEIZURE_WORDS = ("압류", "가처분", "경매개시결정")   # "압류"는 가압류도 포함
TRUST_WORD = "신탁"
TRUST_NOTICE = "신탁원부"
MORTGAGE_WORDS = ("근저당권설정", "저당권설정")
LEASE_WORDS = ("임차권", "전세권설정")             # 임차권설정·주택임차권(임차권등기명령)·전세권설정


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
class Lease(Entry):
    amount: int | None = None     # 임차보증금·전세금 (원)
    holder: str | None = None     # 임차권자·전세권자
    same_deposit_as: str | None = None   # 같은 보증금으로 보고 합계에서 뺐으면 남긴 항목의 순위번호


@dataclass
class RegistrySummary:
    owners: list[str] = field(default_factory=list)
    seizures: list[Entry] = field(default_factory=list)
    trusts: list[Entry] = field(default_factory=list)
    mortgages: list[Mortgage] = field(default_factory=list)
    leases: list[Lease] = field(default_factory=list)   # 을구 임차권·전세권 (선순위 채권에 넣음)
    others: list[Entry] = field(default_factory=list)   # 분류하지 못한 등기 (사용자 확인)
    trustee_owner: bool = False                        # 소유자가 수탁자(신탁회사)로 나옴
    warnings: list[str] = field(default_factory=list)

    @property
    def trust(self) -> bool:
        return bool(self.trusts) or self.trustee_owner

    @property
    def mortgage_amount(self) -> int:
        return sum(m.amount or 0 for m in self.mortgages)

    @property
    def lease_amount(self) -> int:
        return sum(lease.amount or 0 for lease in self.leases if lease.same_deposit_as is None)

    def to_fields(self) -> dict:
        """fields.yaml의 registry.* 값 (schemas.RegistryInput과 같은 이름)."""
        return {
            "seizure": bool(self.seizures),
            "mortgage": bool(self.mortgages),
            "mortgage_amount": self.mortgage_amount,
            "lease_amount": self.lease_amount,
            "trust": self.trust,
        }


def parse_summary_text(text: str) -> RegistrySummary:
    """요약 페이지 글자를 항목으로 나눈다. 요약 페이지가 아니면 RegistryParseError."""
    title = TITLE.search(text)
    if title is None:
        raise RegistryParseError(RegistryParseError.NO_SUMMARY)
    body = "\n".join(line for line in text[title.end():].splitlines() if not PAGE_FURNITURE.search(line))
    pending_text = None
    pending = PENDING.search(body)
    if pending:
        rest = body[pending.end():]
        stop = PENDING_END.search(rest)
        pending_text = rest[:stop.start()] if stop else rest
    ends = [m.start() for m in (NOTES.search(body), pending) if m]
    if ends:
        body = body[:min(ends)]

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
    if pending_text is not None and not NO_PENDING.search(pending_text):
        result.warnings.append("처리 중인 등기 신청이 있습니다(권리변동 예정사항). 새 근저당·압류일 수 있으니 직접 확인하세요")
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
    waiting: list[str] = []   # 순위번호 줄보다 먼저 나온 접수일 (부동산정보요약)
    for line in section.splitlines():
        line = line.strip()
        if not line or "순위번호" in line or "기록사항 없음" in line:
            continue
        m = ENTRY_START.match(line)
        if m:
            entries.append(Entry(rank=m.group(1), purpose=m.group(2), text=" ".join([line, *waiting])))
            waiting = []
        elif DATE_ONLY.match(line) or DATE_FIRST.match(line):
            waiting.append(line)
        elif entries:
            entries[-1].text += " " + line
    return entries


def _parse_owners(section: str, result: RegistrySummary) -> None:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        for n, m in enumerate(OWNER.finditer(line)):
            name, role = m.groups()
            # 부동산정보요약은 긴 이름(신탁회사 등)이 주민등록번호 줄 위아래로 나뉜다: "가상자산신탁주" / 번호 줄 / "식회사 (수탁자)"
            if n == 0 and m.start() == 0 and i >= 2 and ID_LINE.match(lines[i - 1]) and NAME_PART.match(lines[i - 2]):
                name = lines[i - 2] + name
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
        elif TRUST_NOTICE in e.text:
            # 신탁 주의사항 부기 (부동산정보요약은 등기목적 "약정/금지사항/환매특약"이 행 위아래로 갈라져 나옴)
            result.trusts.append(Entry(rank=e.rank, purpose="신탁 주의사항", text=e.text))
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
                holder=_holder(holder.group(1), result.owners) if holder else None,
            ))
            if amount is None:
                result.warnings.append(f"을구 {e.rank}번 근저당의 채권최고액을 읽지 못했습니다. 직접 입력하세요")
        elif any(w in e.purpose for w in LEASE_WORDS) and "-" not in e.rank:
            amount = LEASE_AMOUNT.search(e.text)
            holder = LESSEE.search(e.text)
            lease = Lease(
                rank=e.rank, purpose=e.purpose, text=e.text,
                amount=int(amount.group(1).replace(",", "")) if amount else None,
                holder=_holder(holder.group(1), result.owners) if holder else None,
            )
            result.leases.append(lease)
        else:
            # 변경 등기(1-1 등) 등은 합계에 넣지 않고 사용자에게 확인을 맡긴다.
            result.others.append(e)
            result.warnings.append(f"을구 {e.rank}번 '{e.purpose}' 등기가 있습니다. 선순위 채권에 넣을지 직접 확인하세요")

    _mark_same_deposits(result.leases)
    by_rank = {lease.rank: lease for lease in result.leases}
    for lease in result.leases:
        if lease.amount is None:
            result.warnings.append(f"을구 {lease.rank}번 {lease.purpose}의 보증금을 읽지 못했습니다. 직접 입력하세요")
        elif lease.same_deposit_as is not None:
            kept = by_rank[lease.same_deposit_as]
            result.warnings.append(
                f"을구 {lease.rank}번 {lease.purpose} 보증금 {lease.amount:,}원은 을구 {kept.rank}번 {kept.purpose}과 "
                "같은 보증금으로 보여 한 번만 넣었습니다. 다른 보증금이면 다시 넣으세요")
        else:
            result.warnings.append(
                f"을구 {lease.rank}번 {lease.purpose} 보증금 {lease.amount:,}원을 선순위 채권에 넣었습니다. "
                "이미 돌려받았거나 내 계약이면 빼세요")


def _mark_same_deposits(leases: list[Lease]) -> None:
    """같은 보증금이 전세권과 임차권으로 함께 나오면 한 항목만 남기고 나머지에 same_deposit_as를 적는다."""
    jeonse = [lease for lease in leases if "전세권" in lease.purpose and lease.amount is not None]
    tenancy = [lease for lease in leases if "임차권" in lease.purpose and lease.amount is not None]
    for t in tenancy:
        original = ORIGINAL_DEPOSIT.search(t.text)
        for j in jeonse:
            if j.same_deposit_as is not None or t.same_deposit_as is not None:
                continue
            if original and int(original.group(1).replace(",", "")) == j.amount:
                j.same_deposit_as = t.rank        # 못 돌려받은 금액(임차권)만 센다
            elif t.holder and t.holder == j.holder and t.amount == j.amount:
                t.same_deposit_as = j.rank        # 권리자·금액이 같으면 먼저 등기한 전세권 하나만


def _holder(rest: str, owners: list[str]) -> str:
    """권리자 칸 뒤 글자에서 이름만. "주식회사 하나은행"처럼 띄어 쓴 이름도 남긴다."""
    end = HOLDER_END.search(rest)
    return _strip_owner((rest[: end.start()] if end else rest).strip(), owners)


def _strip_owner(holder: str, owners: list[str]) -> str:
    """부동산정보요약은 근저당권자 바로 옆 칸이 대상소유자라 띄어쓰기 없이 붙어 나올 때가 있다 ("은행홍길동")."""
    for name in owners:
        if holder.endswith(name) and holder != name:
            return holder[: -len(name)].rstrip()
    return holder
