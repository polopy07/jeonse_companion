# 규칙 설정 파일 (rules/)

판정 기준, 경보 단계, 연동 규칙, 특약 분기, 할 일 9종, 보증기관별 기준을 **코드와 분리해** 적어 둔 파일이다. 판정 엔진과 할 일 엔진은 이 파일을 읽어 계산한다. 제도가 바뀌면 코드가 아니라 이 파일을 고친다 (요구사항 명세서 FR-045, NFR-013).

- 근거 문서: 서비스 기획안 v4.34, 요구사항 명세서 v0.4
- 상태: v1.0 (2026-10-07 PO 확정)
- 관리: PO. 규칙을 바꾸면 `version`과 해당 규칙의 `basis`(근거)·`as_of`(기준일)를 함께 고친다.
- `hypothesis: true`가 남아 있는 것은 외부 기준 확인이 필요한 값이다 (HUG 마감 기산일, HF·SGI 마감 기준, 추정 주택가격 산식, 임대차 신고 대상 기준, 판정 기준 전반).

## 파일

| 파일 | 내용 | 명세서 |
| --- | --- | --- |
| `fields.yaml` | 규칙에서 쓰는 입력 값 이름(계약 조건, 등기부, 건축물대장, 계산 값) | FR-001, 005, 014 |
| `verdict.yaml` | 판정 4단계: 문제 항목 / 확인 필요 / 문제 항목 없음 / 대상 아님 | 부속표 B, FR-009 |
| `alert.yaml` | 추정 주택가격 산식, 역전세 경보 3단계 | 부속표 C, FR-003, 036 |
| `linkage.yaml` | 연동 규칙 6개 ("확인 필요" → 계약 당일·계약 후) | 부속표 D, FR-022 |
| `special_terms.yaml` | 특약 예시 3개와 넣음/거절당함 분기 | 부속표 E, FR-039, 050 |
| `todos.yaml` | 할 일 9종(시점·기한·선행 조건·증빙·맨 위로 올리는 조건), 임대차 신고 대상 기준 | 부속표 A, FR-015, 017~021 |
| `guarantors.yaml` | 보증기관(HUG·HF·SGI·미가입)별 기준 | FR-018 |
| `check_rules.py` | 위 파일들의 형식과 서로 참조하는 ID를 검사 | — |

## 조건 쓰는 법

```yaml
when:
  all:                       # 모두 만족 (any: 는 하나라도)
    - {field: registry.trust, op: "==", value: true}
    - {field: trust_consent, op: "==", value: unavailable}
```

- `field`는 `fields.yaml`에 있는 이름만 쓴다.
- `op`: `==`, `!=`, `>=`, `>`, `<=`, `<`, `in`

## 동작(action) 이름

| 이름 | 하는 일 |
| --- | --- |
| `show_special_term` | 계약 당일에 특약 예시를 보여 줌 (`term` = special_terms.yaml의 id) |
| `show_warning` | 경고 문구 표시 |
| `require_check` | 확인 항목 추가 (계약 당일 또는 잔금일 재비교) |
| `require_document` | 기록함 필수 서류로 지정 |
| `add_todo` | 할 일 추가 (`todo` = todos.yaml의 id 또는 추가 할 일 id) |
| `move_to_top` | 할 일을 목록 맨 위로 |
| `move_next` | 할 일을 바로 다음 순서로 |
| `move_before` | 할 일 기한을 다른 날짜 앞으로 당김 (`before` = 날짜 필드) |
| `escalate_verdict` | 판정을 한 단계 올림 (예: 확인 필요 → 문제 항목) |
| `link_counsel` | 공공 상담 창구 안내 |

## 검사

```bash
python3 rules/check_rules.py
```

YAML 문법, 필수 항목, 규칙끼리 서로 가리키는 ID(할 일·특약·필드 이름)가 맞는지 확인한다.
