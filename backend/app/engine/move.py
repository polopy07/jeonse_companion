"""갈아타기: 지금 집 보증금 반환과 다음 집 잔금·대출·전입 순서 (FR-025~027, UC-008, 정답표 S10).

지금 집 반환 예정일은 지금 계약의 9번 할 일(보증금 반환 확인) 기한, 없으면 만기일이다.
- 자금 틈: 반환 예정일이 다음 집 잔금일보다 늦으면 그 일수와, 그동안 비는 금액
  min(지금 집 보증금, 다음 집 잔금 = 보증금 − 계약금) (PO 결정 Q5)
- 대출 순서: 두 집 모두 전세대출이면 새 대출 실행일(모르면 잔금일)과 기존 대출 상환일(= 반환 예정일)을 비교
- 전입 순서: 다음 집 전입 예정일이 반환 예정일과 같거나 앞서면 경고 (반환을 이미 확인했으면 경고하지 않음)
"""
from dataclasses import dataclass, field
from datetime import date

GAP_WARNING = "보증금 반환({ret})이 다음 집 잔금일({bal})보다 {days}일 늦어요. 그동안 {amount:,}원이 비니 자금 계획을 세우세요"
LOAN_NEW_FIRST = "새 대출 실행({new})이 기존 대출 상환({old})보다 {days}일 먼저예요. 대출 이전 가능 여부는 은행에 확인하세요"
LOAN_OLD_FIRST = "기존 대출 상환({old}) 뒤에 새 대출을 실행({new})해요. 대출 이전 가능 여부는 은행에 확인하세요"
MOVE_IN_WARNING = ("지금 집 보증금 반환을 확인하거나 임차권등기를 마치기 전에 다음 집으로 전입신고하면 "
                   "지금 집의 대항력·우선변제권을 잃을 수 있어요. 반환을 확인한 뒤 전입신고하세요")


@dataclass
class MovePlan:
    return_date: date                 # 지금 집 보증금 반환 예정일
    next_balance: int                 # 다음 집 잔금 (보증금 − 계약금)
    gap_days: int                     # 반환이 잔금보다 늦은 일수 (없으면 0)
    gap_amount: int                   # 그동안 비는 금액 (없으면 0)
    loan_order: str | None            # new_loan_first / old_repayment_first, 두 집 모두 대출이 아니면 None
    loan_gap_days: int | None         # 새 대출이 먼저일 때 그 일수
    move_in_date: date
    move_in_warning: bool
    warnings: list[str] = field(default_factory=list)


def _d(day: date) -> str:
    return day.isoformat()


def plan_move(current: dict, nxt: dict, return_date: date, returned: bool = False) -> MovePlan:
    """current: 지금 계약 {deposit, loan}. nxt: 다음 집 {balance_date, deposit, down_payment, loan,
    loan_execution_date, move_in_date}. returned: 지금 집 반환 확인(9번 할 일)을 이미 끝냈는지."""
    balance_date = nxt["balance_date"]
    next_balance = nxt["deposit"] - nxt["down_payment"]
    warnings = []

    gap_days = max(0, (return_date - balance_date).days)
    gap_amount = min(current["deposit"], next_balance) if gap_days else 0
    if gap_days:
        warnings.append(GAP_WARNING.format(ret=_d(return_date), bal=_d(balance_date), days=gap_days, amount=gap_amount))

    loan_order = loan_gap_days = None
    if current["loan"] and nxt["loan"]:
        new = nxt["loan_execution_date"] or balance_date
        if new < return_date:
            loan_order, loan_gap_days = "new_loan_first", (return_date - new).days
            warnings.append(LOAN_NEW_FIRST.format(new=_d(new), old=_d(return_date), days=loan_gap_days))
        else:
            loan_order = "old_repayment_first"
            warnings.append(LOAN_OLD_FIRST.format(new=_d(new), old=_d(return_date)))

    move_in = nxt["move_in_date"] or balance_date
    move_in_warning = not returned and move_in <= return_date
    if move_in_warning:
        warnings.append(MOVE_IN_WARNING)

    return MovePlan(return_date, next_balance, gap_days, gap_amount, loan_order, loan_gap_days,
                    move_in, move_in_warning, warnings)
