"""패키지 시작·계약 당일 체크: 계약 생성과 할 일 9종 생성 (UC-003, FR-011, FR-014, FR-015, FR-017~020, FR-049).

계약 조건·특약 결과 변경 → 할 일 재계산 (UC-005, FR-021, FR-049·050).
테스트 결제 확인(FR-013), 계약 접근 토큰(#39)·접근 링크 다시 받기, 계약 무산(FR-016) — API 명세 1.8.
"""
import hashlib
import hmac
import logging
import secrets
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, object_session

from app import evidence, mailer
from app.clock import today as today_dep
from app.config import app_link_base, require_contract_auth
from app.db import get_db
from app.engine.alert import alert_level
from app.engine.payment import PRODUCTS, covers, product_for
from app.engine.schedule import FINISHED, days_left, todo_state   # FINISHED: 끝낸 할 일 (skipped = 나중에 올리기)
from app.engine.special_terms import contract_day_guide, term_effects
from app.engine.todos import build_todos, report_required
from app.errors import api_error, responses
from app.models import Contract, ContractToken, Payment, Todo, Verdict
from app.rules.loader import get_rules
from app.schemas import (AccessLinkInput, AccessLinkResult, ContractCreatedOut, ContractDocumentOut, ContractInput,
                         ContractOut, ContractPatch, SpecialTermEffectOut, TodoOut)

router = APIRouter(prefix="/api/contracts", tags=["계약"])
logger = logging.getLogger(__name__)
# 화면에 그대로 보이는 안내. 만든 계약 id는 GET /api/checks/{id}의 contract_id로 찾는다
ALREADY_USED_HINT = "할 일 탭에서 이 계약의 할 일을 볼 수 있습니다. 다른 집이면 계약 전 확인을 다시 하세요"
_PRODUCT_LABEL = {"package": "전동기 패키지", "todo_only": "할 일 관리만"}
ACCESS_LINK_MESSAGE = "이 이메일로 만든 계약이 있으면 접근 링크를 보냈습니다. 메일함을 확인하세요"
ACCESS_LINK_PER_HOUR = 3   # 계약마다 한 시간에 다시 보내는 횟수 (메일 폭탄 막기)
TOKEN_HEADER_DESC = "계약 접근 토큰 (계약을 만들 때 받은 access_token, API 명세 1.8)"
PAYMENT_HINT = "결과 화면에서 패키지 시작을 눌러 결제를 확인하세요"

# 판정 입력에서 그대로 가져오는 값 (fields.yaml 이름)
_FROM_CHECK = ("housing_type", "deposit", "official_price", "exclusive_area")
# 할 일 규칙(todos.yaml)이 읽는 계약 조건
_TODO_FIELDS = ("contract_date", "balance_date", "end_date", "deposit", "monthly_rent", "loan",
                "loan_execution_date", "guarantor", "brokered", "renewal_right_used")


def shown_special_terms(linkages: list[str], rules: dict) -> set[str]:
    """계약 당일 특약 예시(GET /api/checks/{id}/special-terms)로 보여 준 특약 id. 보여 준 기준과 받는 기준을 같게."""
    return {t.id for t in contract_day_guide(linkages, rules).terms}


def _check_special_terms(result: dict, linkages: list[str], rules: dict) -> None:
    """판정에서 보여 준 특약의 결과만 받는다. 보여 주지 않은 특약의 거절로 할 일이 바뀌지 않게."""
    known = {t["id"] for t in rules["special_terms"]["terms"]}
    shown = shown_special_terms(linkages, rules)
    errors = []
    for key in result:
        if key not in known:
            msg = f"규칙 파일에 없는 특약입니다: {key}"
        elif key not in shown:
            msg = f"이 판정에서 안내하지 않은 특약입니다: {key}"
        else:
            continue
        errors.append({"type": "value_error", "loc": ("body", "special_term_result", key),
                       "msg": f"Value error, {msg}", "input": key})
    if errors:
        raise RequestValidationError(errors)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _token_matches(row: Contract, token: str, db: Session) -> bool:
    """처음 받은 토큰이거나 접근 링크로 다시 받은 토큰이면 맞다."""
    given = _token_hash(token)
    return (row.access_token_hash is not None and hmac.compare_digest(row.access_token_hash, given)) or \
        db.scalar(select(ContractToken.id).where(ContractToken.contract_id == row.id,
                                                 ContractToken.token_hash == given)) is not None


def _contract_for(contract_id: int, token: str | None, db: Session) -> Contract:
    """계약을 찾고 접근 토큰을 확인한다. 토큰이 없거나 틀리면 계약이 없을 때와 같은 404 (계약이 있는지 알아내지 못하게).

    REQUIRE_CONTRACT_AUTH가 false면(앱 연결 전) 토큰을 보내지 않은 요청은 통과시킨다. 보냈는데 틀리면 언제나 404.
    """
    row = db.get(Contract, contract_id)
    if row is not None:
        ok = not require_contract_auth() if token is None else _token_matches(row, token, db)
        if ok:
            return row
    raise api_error(404, "NOT_FOUND", "계약이 없습니다", "이 휴대폰에서 만든 계약이 아니면 볼 수 없습니다")


def _active(row: Contract) -> None:
    if row.status == "cancelled":
        raise api_error(409, "CONTRACT_CANCELLED", "무산된 계약이라 바꿀 수 없습니다",
                        "기록은 계속 볼 수 있습니다. 다음 집은 계약 전 확인부터 다시 하세요")


def _released_by_owner(p: Payment, token: str, db: Session) -> bool:
    """풀린 결제는 그 결제를 썼던 무산된 계약의 접근 토큰을 함께 보내야 다시 쓴다. 결제 번호만 바꿔 남의 풀린 결제를
    가져가지 못하게. 풀린 결제(released)는 계약 무산으로만 생기므로 계약 상태는 다시 보지 않는다.

    REQUIRE_CONTRACT_AUTH와 상관없이 언제나 확인한다 (풀린 결제를 다시 쓰는 앱 화면은 토큰 저장과 함께 만든다).
    """
    cancelled = db.get(Contract, p.contract_id) if p.contract_id is not None else None
    return cancelled is not None and _token_matches(cancelled, token, db)


def _take_payment(payment_id: int | None, check: Verdict, db: Session, released_token: str | None) -> Payment | None:
    """계약 생성에 쓸 테스트 결제를 확인한다 (402 판단, 결정 자료 "세부 규칙").

    통과: 이 판정에 한 결제(paid), 또는 무산된 계약에서 풀린 결제(released)와 그 계약의 접근 토큰.
    풀린 결제는 같거나 낮은 상품의 계약에만 (패키지 → 할 일 관리만 OK, 할 일 관리만 → 패키지는 다시 결제).
    """
    if payment_id is None:
        if require_contract_auth():
            raise api_error(402, "PAYMENT_REQUIRED", "테스트 결제를 먼저 해야 합니다", PAYMENT_HINT)
        return None
    # PostgreSQL은 확인부터 사용(커밋)까지 이 결제 행을 잠근다. SQLite는 잠금이 없어 사용할 때 조건부 UPDATE로 막는다
    p = db.scalars(select(Payment).where(Payment.id == payment_id).with_for_update()).one_or_none()
    if p is not None and p.status == "released":
        if released_token is None:
            raise api_error(402, "PAYMENT_REQUIRED", "무산된 계약에서 풀린 결제는 그 계약의 접근 토큰과 함께 써야 합니다",
                            "앱을 다시 설치했거나 휴대폰을 바꿨으면 접근 링크를 이메일로 다시 받으세요")
        if not _released_by_owner(p, released_token, db):   # 틀린 토큰은 남의 결제인지 드러나지 않게 아래와 같은 문구
            p = None
    elif p is not None and not (p.status == "paid" and p.check_id == check.id):
        p = None
    if p is None:
        raise api_error(402, "PAYMENT_REQUIRED", "이 판정에 쓸 수 있는 결제가 아닙니다", PAYMENT_HINT)
    needed = product_for(check.level)
    if not covers(p.product, needed):
        raise api_error(402, "PAYMENT_REQUIRED",
                        f"{_PRODUCT_LABEL[p.product]}({PRODUCTS[p.product]:,}원) 결제로는 "
                        f"{_PRODUCT_LABEL[needed]}({PRODUCTS[needed]:,}원)을 시작할 수 없습니다",
                        f"{_PRODUCT_LABEL[needed]}으로 다시 결제하세요")
    return p


def _payment_taken():
    return api_error(402, "PAYMENT_REQUIRED", "이미 다른 계약에 쓴 결제입니다", PAYMENT_HINT)


def _alert_level(check: Verdict, rules: dict) -> str | None:
    # 시작할 때의 경보 단계는 판정 때 계산한 내 보증금 비율로 정한다. 계약 중에는 app.alerts.recalculate가 바꾼다 (FR-037)
    values = {"deposit_ratio": check.deposit_ratio, "deposit": check.inputs.get("deposit"),
              "nearby_jeonse_median": check.inputs.get("nearby_jeonse_median")}
    return alert_level(values, rules["alert"])


def _todo_values(row: Contract) -> dict:
    return {name: getattr(row, name) for name in _TODO_FIELDS}


def todo_linkages(row: Contract, check: Verdict) -> list[str]:
    """할 일에 쓰는 연동 규칙: 계약 전 확인 판정 + 등기부 재비교로 새로 걸린 것 (FR-023, PO 2026-10-28).

    더하기만 한다. 재비교에서 근저당이 말소돼 연동이 풀려도 빼지 않는다 (잔금 때 말소하기로 한 근저당이라도
    3번 할 일의 근저당 금액 비교는 그대로 해야 하고, 끝낸 할 일의 필수 확인이 사라지지 않게).
    """
    linkages = list(check.linkages or [])
    for v in row.verdicts:
        if v.stage is not None:
            linkages += [lid for lid in v.linkages or [] if lid not in linkages]
    return linkages


def _sync_todos(row: Contract, check: Verdict, rules: dict) -> None:
    """계약 조건으로 할 일을 만들거나 다시 계산한다.

    같은 할 일(rule_id)은 id·상태·완료일·증빙을 그대로 두고 날짜·순서만 바꾼다. 끝낸 할 일의 완료일은
    뒤 할 일의 기준일로 쓴다 (T5 시작 = 전입신고 완료 다음 날). 조건이 바뀌어 더는 해당하지 않는 할 일은
    지우되, 이미 끝낸 것은 기록으로 맨 뒤에 남긴다. 잔금일이 미뤄져 완료일이 새 시작일보다 앞서게 된
    할 일(todos.yaml reopen_if_done_before_start: T3·T4)은 다시 할 일로 돌리고 뒤 할 일 날짜도 다시 계산한다.
    """
    row.report_required = report_required(_todo_values(row), rules["todos"])
    existing = {t.rule_id: t for t in row.todos}
    # "나중에 올리기"(skipped)도 끝낸 할 일이다 (FR-030: 완료 처리하되 기록함만 빈칸)
    done_dates = {t.rule_id: t.done_date for t in row.todos if t.status in FINISHED and t.done_date}
    linkages = todo_linkages(row, check)

    def plan():
        return build_todos(_todo_values(row), linkages, row.special_term_result, row.alert_level, rules,
                           done_dates=done_dates)

    planned = plan()
    reopenable = {t["id"] for t in rules["todos"]["todos"] if t.get("reopen_if_done_before_start")}
    reopen = [p.rule_id for p in planned if p.rule_id in reopenable and p.rule_id in done_dates
              and p.start_date and done_dates[p.rule_id] < p.start_date]
    if reopen:
        for rule_id in reopen:   # 증빙(evidence_path)은 지우지 않고 남긴다
            existing[rule_id].status, existing[rule_id].done_date = "todo", None
            del done_dates[rule_id]
        planned = plan()
    version = str(rules["todos"]["version"])
    todos = []
    for p in planned:
        t = existing.pop(p.rule_id, None) or Todo(rule_id=p.rule_id, status="todo")
        t.title, t.detail, t.evidence = p.title, p.detail, p.evidence
        t.start_date, t.due_date, t.remind_date = p.start_date, p.due_date, p.remind_date
        t.prerequisites, t.required_checks = p.prerequisites, p.required_checks
        t.sort_order, t.pinned, t.moved_to_top = p.sort_order, p.pinned, p.moved_to_top
        t.rules_version, t.archived = version, False
        todos.append(t)
    db = object_session(row)
    for t in sorted(existing.values(), key=lambda t: t.sort_order):
        if t.status in FINISHED:
            t.sort_order, t.archived = len(todos) + 1, True
            todos.append(t)
        elif db is not None:   # 다시 연 뒤 지워지는 할 일의 증빙 파일도 (볼 수도 지울 수도 없게 남지 않게)
            evidence.remove_after_commit(db, t.evidence_path)
    row.todos = todos   # 남기지 않은 할 일은 delete-orphan으로 지워진다


def done_floor(row: Contract, t: Todo) -> date:
    """끝낸 날로 넣을 수 있는 가장 이른 날. 끝낸 날은 뒤 할 일의 기준일이라 계약일보다 앞서면 뒤 기한이 모두 당겨진다.
    계약 전날 하는 할 일(X-FIXED-DATE-STATUS 시작 = 계약일 −1일)은 그 시작일까지."""
    return min(row.contract_date, t.start_date) if t.start_date else row.contract_date


def _todo_out(t: Todo, today: date) -> TodoOut:
    computed = ("state", "days_left", "evidence_uploaded")
    fields = {name: getattr(t, name) for name in TodoOut.model_fields if name not in computed}
    return TodoOut(**fields, state=todo_state(t.status, t.start_date, t.due_date, t.remind_date, today),
                   days_left=days_left(t.due_date, t.remind_date, today), evidence_uploaded=t.evidence_path is not None)


def _to_out(row: Contract, db: Session, rules: dict, today: date) -> ContractOut:
    check = db.get(Verdict, row.check_id)
    return ContractOut(
        id=row.id,
        today=today,
        check_id=check.id,
        level=check.level,
        housing_type=row.housing_type,
        deposit=row.deposit,
        monthly_rent=row.monthly_rent,
        exclusive_area=row.exclusive_area,
        official_price=row.official_price,
        contract_date=row.contract_date,
        balance_date=row.balance_date,
        end_date=row.end_date,
        loan=row.loan,
        loan_execution_date=row.loan_execution_date,
        guarantor=row.guarantor,
        brokered=row.brokered,
        renewal_right_used=row.renewal_right_used,
        co_tenant=row.co_tenant,
        email=row.email,
        special_term_result=row.special_term_result,
        report_required=row.report_required,
        alert_level=row.alert_level,
        status=row.status or "active",
        payment_id=row.payment_id,
        special_term_effects=[
            SpecialTermEffectOut(term_id=e.term_id, label=e.label, result=e.result, **asdict(e.outcome))
            for e in term_effects(row.special_term_result or {}, rules)
        ],
        todos=[_todo_out(t, today) for t in row.todos],
        documents=_documents_out(row, rules),
    )


def _documents_out(row: Contract, rules: dict) -> list[ContractDocumentOut]:
    saved = {d.kind: d for d in row.documents}
    return [ContractDocumentOut(kind=k["id"], label=k["label"], detail=k.get("detail"), uploaded=k["id"] in saved,
                                uploaded_at=saved[k["id"]].uploaded_at if k["id"] in saved else None)
            for k in rules["todos"]["first_documents"]]


@router.post("", response_model=ContractCreatedOut, status_code=201, responses=responses(402, 404, 409, 422))
def create_contract(inp: ContractInput, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep)):
    check = db.get(Verdict, inp.check_id)
    if check is None:
        raise api_error(404, "NOT_FOUND", "판정 결과가 없습니다", "계약 전 확인을 먼저 하세요")
    level = next((lv for lv in rules["verdict"]["levels"] if lv["id"] == check.level), None)
    if level is None:
        raise api_error(409, "CHECK_OUTDATED", "판정 기준이 바뀌어 이 판정 결과로는 시작할 수 없습니다",
                        "계약 전 확인을 다시 하세요")
    if level.get("block_payment"):
        raise api_error(409, "CHECK_BLOCKED", f"\"{level['label']}\" 판정이라 패키지를 시작할 수 없습니다",
                        "계약을 다시 검토하고 공공 상담 창구에 문의하세요")
    if check.contract_id is not None:
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다", ALREADY_USED_HINT)
    _check_special_terms(inp.special_term_result, check.linkages, rules)
    payment = _take_payment(inp.payment_id, check, db, inp.released_contract_token)

    token = secrets.token_urlsafe(32)
    row = Contract(
        **{name: check.inputs.get(name) for name in _FROM_CHECK},
        **inp.model_dump(exclude={"payment_id", "released_contract_token"}),
        access_token_hash=_token_hash(token),
        status="active",
    )
    row.verdicts.append(check)
    row.alert_level = _alert_level(check, rules)
    _sync_todos(row, check, rules)
    db.add(row)
    try:
        db.flush()
        if payment is not None:
            # 확인한 그대로(상태·쓴 계약)일 때만 쓴다. 같은 풀린 결제로 동시에 들어온 요청 중 늦은 쪽, 또는 그사이
            # 다른 계약에 쓰였다가 다시 풀린 결제(상태는 같아도 contract_id가 다름)는 0행
            same_owner = (Payment.contract_id.is_(None) if payment.contract_id is None
                          else Payment.contract_id == payment.contract_id)
            taken = db.execute(update(Payment).where(Payment.id == payment.id, Payment.status == payment.status, same_owner)
                               .values(status="used", contract_id=row.id))
            if taken.rowcount != 1:
                raise _payment_taken()
            row.payment_id = payment.id
        db.commit()
    except IntegrityError:   # 같은 판정으로 동시에 들어온 요청 중 늦은 쪽 (check_id unique)
        db.rollback()
        first = db.query(Contract).filter_by(check_id=inp.check_id).one_or_none()
        if first is None:   # check_id가 아닌 다른 제약 위반이면 그대로 올린다
            raise
        raise api_error(409, "CHECK_ALREADY_USED", "이미 계약을 만든 판정 결과입니다", ALREADY_USED_HINT) from None
    except OperationalError:   # SQLite: 동시에 쓰던 다른 요청을 기다리다 잠금 대기 시간이 지남 (database is locked)
        db.rollback()
        if payment is not None and db.get(Payment, payment.id).status == "used":
            raise _payment_taken() from None
        raise
    except Exception:
        db.rollback()
        raise
    return ContractCreatedOut(**_to_out(row, db, rules, today).model_dump(), access_token=token)


@router.post("/access-link", response_model=AccessLinkResult, status_code=202, responses=responses(422))
def send_access_link(inp: AccessLinkInput, db: Session = Depends(get_db)):
    """접근 링크 이메일로 다시 받기 (#39, 휴대폰을 바꾸거나 앱을 지웠을 때).

    그 이메일로 만든 진행 중 계약마다 새 접근 토큰을 만들어 계약 이메일로 보낸다. 처음 토큰은 그대로 둔다
    (남이 다시 받기를 눌러도 원래 휴대폰이 쫓겨나지 않게). 이메일이 없어도 같은 202를 돌려준다.
    무산된 계약도 풀린 결제(released)가 남아 있으면 보낸다: 그 토큰이 있어야 다음 집 계약에 결제를 다시 쓴다(FR-016).
    """
    now = datetime.now(timezone.utc)
    released = select(Payment.id).where(Payment.contract_id == Contract.id, Payment.status == "released").exists()
    rows = db.scalars(select(Contract).where(
        func.lower(Contract.email) == inp.email.strip().lower(),
        or_(Contract.status == "active", Contract.status.is_(None), (Contract.status == "cancelled") & released),
    ).order_by(Contract.id)).all()
    issued = []
    for row in rows:
        recent = db.scalar(select(func.count(ContractToken.id)).where(
            ContractToken.contract_id == row.id, ContractToken.created_at > now - timedelta(hours=1)))
        if recent >= ACCESS_LINK_PER_HOUR:
            continue
        token = secrets.token_urlsafe(32)
        db.add(ContractToken(contract_id=row.id, token_hash=_token_hash(token), created_at=now))
        issued.append((row, token))
    if issued:
        try:
            mailer.send(mailer.Mail(issued[0][0].email, "[전동기] 계약 접근 링크", _access_link_body(issued)))
        except mailer.MailError as e:
            db.rollback()   # 보내지 못한 토큰은 남기지 않는다. 응답은 같게
            logger.warning("접근 링크 이메일 실패 (계약 %s): %s", [r.id for r, _ in issued], e)
            return AccessLinkResult(message=ACCESS_LINK_MESSAGE)
        db.commit()
    return AccessLinkResult(message=ACCESS_LINK_MESSAGE)


def _access_link_body(issued: list[tuple[Contract, str]]) -> str:
    base = app_link_base()
    lines = ["안녕하세요, 전동기입니다.", "", "요청하신 계약 접근 링크예요. 앱에서 계약을 다시 불러올 때 쓰세요.", ""]
    for row, token in issued:
        note = " (무산된 계약, 결제를 다음 집 계약에 다시 쓸 때)" if row.status == "cancelled" else ""
        lines.append(f"- 계약 {row.id}: 보증금 {row.deposit:,}원, 잔금일 {row.balance_date.isoformat()}{note}")
        lines.append(f"  {base}?contract={row.id}&token={token}" if base else f"  접근 코드: {token}")
    lines += ["", "직접 요청하지 않았다면 이 메일은 지워도 됩니다. 원래 쓰던 휴대폰은 그대로 쓸 수 있어요.",
              "이 링크를 가진 사람은 계약을 볼 수 있으니 다른 사람에게 보내지 마세요."]
    return "\n".join(lines)


@router.get("/{contract_id}", response_model=ContractOut, responses=responses(404, 422))
def get_contract(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                 today: date = Depends(today_dep),
                 x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """계약과 할 일. 무산된 계약도 기록으로 볼 수 있다."""
    return _to_out(_contract_for(contract_id, x_contract_token, db), db, rules, today)


@router.patch("/{contract_id}", response_model=ContractOut, responses=responses(404, 409, 422))
def update_contract(contract_id: int, inp: ContractPatch, db: Session = Depends(get_db),
                    rules: dict = Depends(get_rules), today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """계약 조건·특약 결과를 바꾸고 할 일을 다시 계산한다 (FR-021, FR-049·050). 무산된 계약이면 409."""
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    check = db.get(Verdict, row.check_id)
    changes = inp.model_dump(exclude_unset=True)
    terms = changes.pop("special_term_result", None) or {}
    _check_special_terms(terms, check.linkages, rules)

    # 바꾼 뒤의 계약 조건 전체가 계약 생성 때와 같은 규칙(날짜 순서, 대출 없으면 실행일 없음)을 지켜야 한다
    current = {name: getattr(row, name) for name in ContractInput.model_fields
               if name not in ("check_id", "special_term_result", "released_contract_token")}
    try:
        ContractInput(check_id=row.check_id, **{**current, **changes})
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from None

    for name, value in changes.items():
        setattr(row, name, value)
    if terms:
        row.special_term_result = {**row.special_term_result, **terms}
    _sync_todos(row, check, rules)
    # 계약일을 뒤로 바꿔 끝낸 날이 계약일보다 앞서게 되면 뒤 할 일의 기준일이 당겨진다 (PATCH /api/todos의 422와 같은 기준)
    early = [t for t in row.todos if not t.archived and t.status in FINISHED and t.done_date
             and t.done_date < done_floor(row, t)]
    if early:
        new_date = row.contract_date.isoformat()
        db.rollback()
        raise RequestValidationError([{
            "type": "value_error", "loc": ("body", "contract_date"), "input": new_date,
            "msg": f"Value error, 끝낸 날이 새 계약일({new_date})보다 앞서는 할 일이 있습니다: "
                   f"{', '.join(t.title for t in early)}. 그 할 일을 되돌리거나 끝낸 날을 고친 뒤 바꾸세요"}])
    db.commit()
    return _to_out(row, db, rules, today)


@router.post("/{contract_id}/cancel", response_model=ContractOut, responses=responses(404, 409, 422))
def cancel_contract(contract_id: int, db: Session = Depends(get_db), rules: dict = Depends(get_rules),
                    today: date = Depends(today_dep),
                    x_contract_token: str | None = Header(None, description=TOKEN_HEADER_DESC)):
    """계약 무산 (FR-016). 계약은 cancelled, 쓴 결제는 released로 풀어 다음 계약에 다시 쓴다.

    할 일은 지우지 않고 기록으로 남기되 알림은 보내지 않는다. 이미 무산된 계약이면 409.
    """
    row = _contract_for(contract_id, x_contract_token, db)
    _active(row)
    row.status, row.cancelled_at = "cancelled", datetime.now(timezone.utc)
    if row.payment_id is not None:
        payment = db.get(Payment, row.payment_id)
        if payment is not None and payment.contract_id == row.id:
            payment.status = "released"
    db.commit()
    return _to_out(row, db, rules, today)
