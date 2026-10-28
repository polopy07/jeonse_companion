# 전동기 API 명세

- 기준: 요구사항 명세서 v0.5 (기획안 v4.35), 규칙 파일 `rules/` (파일마다 `version`)
- 서버: `backend/` (FastAPI). 실행하면 http://localhost:8000/docs 에서 직접 호출해 볼 수 있다
- 입출력 세부 형식의 기준은 `docs/api/openapi.json` (서버 코드에서 자동 생성). 이 문서는 공통 규칙과 API 목록을 정한다
- 새 API를 만들거나 바꾸면 이 문서와 `openapi.json`을 같은 PR에서 고친다

## 1. 공통 규칙

### 1.1 주소

- 모든 API는 `/api`로 시작한다. 버전 번호는 붙이지 않는다 (MVP 기간에는 프론트·백엔드를 같이 바꾼다)
- 자원 이름은 영문 소문자 복수형: `/api/checks`, `/api/contracts`, `/api/todos`
- 한 계약에 딸린 자원은 계약 아래에 둔다: `/api/contracts/{id}/todos`
- 저장하지 않는 계산·변환은 `/api/<자원>/<동작>`: `/api/registry/parse`
- 여러 단어는 하이픈: `/api/special-terms`

### 1.2 메서드와 상태 코드

| 메서드 | 쓰는 곳 | 성공 코드 |
| --- | --- | --- |
| `GET` | 조회 | 200 |
| `POST` | 새로 만들기 | 201 (만든 것을 응답 본문으로 돌려줌) |
| `POST` | 저장하지 않는 계산 (`/parse` 등) | 200 |
| `PATCH` | 일부 고치기 (날짜 변경, 완료 체크, 특약 결과, 계약 무산 등 상태 변경 포함) | 200 |
| `DELETE` | 삭제 | 204 (본문 없음) |

`PUT`은 쓰지 않는다.

| 오류 코드 | 언제 |
| --- | --- |
| 401 | 관리자 토큰이 없거나 틀림 (관리자 API) |
| 403 | 관리자 API가 꺼져 있음 (서버에 `ADMIN_TOKEN` 없음) |
| 404 | 대상이 없음 |
| 405 | 그 주소에서 허용되지 않는 메서드 |
| 402 | 테스트 결제가 없거나 이 판정에 쓸 수 없는 결제 (계약 생성, 1.8) |
| 409 | 지금 상태에서 할 수 없음 (예: "문제 항목" 판정이라 패키지 시작 불가, FR-011) |
| 413 | 파일이 너무 큼 |
| 422 | 입력 형식이 틀렸거나 계산에 필요한 값이 없음, 파일을 읽지 못함 |
| 500 | 서버 오류 |

### 1.3 값 표기

| 종류 | 표기 | 예 |
| --- | --- | --- |
| 필드 이름 | `snake_case`, `rules/fields.yaml`과 같은 이름. 점(.)이 든 이름은 객체로 나눈다 | `registry.mortgage_amount` → `{"registry": {"mortgage_amount": …}}` |
| 금액 | 원 단위 정수, 입력은 1조 원(`10**12`) 이하 | `150000000` |
| 비율 | 소수 (퍼센트 아님) | `0.9643` = 96.43% |
| 면적 | ㎡, 소수 | `59.8` |
| 날짜 | `YYYY-MM-DD` | `2026-10-20` |
| 시각 | ISO 8601, 한국 시간 | `2026-10-07T18:30:00+09:00` |
| 선택지 | 규칙 파일의 영문 코드. 화면 문구는 응답의 `label`을 쓴다 | `"level": "check_needed", "label": "확인 필요"` |
| 모르는 값 | `null` (응답에서 필드를 빼지 않는다) | `"building_violation": null` |

### 1.4 판정·경보 응답에 항상 넣는 것 (NFR-014)

- `disclaimer`: "정보 제공이며 보증하지 않음" 안내 문구 (규칙 파일에서 읽음)
- `rules_version`: 계산에 쓴 규칙 파일 버전
- 경보·시세처럼 기준일이 있는 값은 기준일을 같이 보낸다

### 1.5 오류 형식

모든 오류는 같은 모양이다. 프론트는 `code`로 분기하고 `message`는 그대로 보여 줘도 된다.

```json
{
  "detail": {
    "code": "REGISTRY_UNREADABLE",
    "message": "등기부 요약 페이지(인터넷등기소 \"부동산정보요약\" 또는 증명서의 \"주요 등기사항 요약\")를 찾지 못했습니다",
    "hint": "인터넷등기소에서 열람한 뒤 \"부동산정보요약\"을 PDF로 저장해 다시 올리거나, 수동 입력 화면에서 직접 입력하세요",
    "fields": []
  }
}
```

입력 형식이 틀리면 `code`는 `INVALID_INPUT`이고 `fields`에 필드별 문제가 들어간다.

```json
{
  "detail": {
    "code": "INVALID_INPUT",
    "message": "입력 값이 올바르지 않습니다",
    "hint": null,
    "fields": [{"field": "registry", "message": "근저당이 있으면 채권최고액 합계를 입력해야 합니다"}]
  }
}
```

| code | 상태 | 뜻 |
| --- | --- | --- |
| `INVALID_INPUT` | 422 | 입력 형식 오류 (`fields` 참고) |
| `MISSING_OFFICIAL_PRICE` | 422 | 공시가격이 없어 비율을 계산할 수 없음 |
| `REGISTRY_UNREADABLE` | 422 | 등기부 요약을 읽지 못함 → 수동 입력 화면 (FR-006, NFR-007) |
| `FILE_TOO_LARGE` | 413 | 올린 파일이 너무 큼 |
| `NOT_FOUND` | 404 | 대상이 없음 (없는 주소도 같은 코드) |
| `METHOD_NOT_ALLOWED` | 405 | 그 주소에서 허용되지 않는 메서드 |
| `INTERNAL_ERROR` | 500 | 서버 오류. 내부 내용은 응답에 싣지 않는다 |
| `HTTP_ERROR` | 그 외 | 위에 없는 상태 코드의 오류 |
| `CHECK_BLOCKED` | 409 | "문제 항목" 판정이라 패키지를 시작할 수 없음 (FR-011) |
| `CHECK_ALREADY_USED` | 409 | 이미 계약을 만든 판정 결과로 다시 계약을 만들려 함(동시 요청 포함). `hint`는 화면에 그대로 보여 주는 안내이고, 만든 계약 id는 `GET /api/checks/{id}`의 `contract_id`로 찾는다 |
| `MOVE_IN_BEFORE_RETURN` | 409 | 갈아타기 다음 집 계약의 전입신고(4번)를 지금 집 반환 확인(9번)·임차권등기 전에 끝내려 함. 지금 집의 대항력·우선변제권을 잃을 수 있다는 경고 (FR-027). 경고를 보고 그래도 끝내면 `confirm_move_in: true`로 다시 보냄 |
| `NEXT_CONTRACT_LINKED` | 409 | 다음 집 계약이 이미 다른 갈아타기에 연결돼 있음 |
| `MOVE_INPUT_OUTDATED` | 409 | 저장한 갈아타기 다음 집 입력이 지금 입력 규칙과 맞지 않음(규칙이 바뀐 뒤) → 다음 집 정보를 다시 입력. `GET /api/contracts/{id}/move` |
| `CHECK_OUTDATED` | 409 | 판정 기준(규칙 파일)이 바뀌어 저장된 판정 단계 id를 찾을 수 없음 → 계약 전 확인을 다시. 단계 id 기준이라 `rules_version`만 달라지고 단계 id가 남아 있으면 걸리지 않음. `GET /api/checks/{id}`·`POST /api/contracts` |
| `PAYMENT_REQUIRED` | 402 | 계약 생성에 쓸 테스트 결제가 없음, 다른 판정의 결제, 이미 쓴 결제(같은 풀린 결제로 동시에 들어온 요청 중 늦은 쪽, 확인한 뒤 그사이 다른 계약에 쓰였다가 다시 풀린 결제 포함), 풀린 결제인데 무산된 계약의 접근 토큰이 없거나 틀림, 또는 풀린 결제의 상품이 모자람(할 일 관리만 → 패키지). `hint`는 다시 결제 안내 (1.8) |
| `CONTRACT_CANCELLED` | 409 | 무산된 계약이라 바꿀 수 없음 (`PATCH`, 다시 무산, 할 일 완료). `GET`은 됨 (FR-016) |
| `PREREQUISITE_NOT_DONE` | 409 | 먼저 끝낼 할 일(`prerequisites`)이 남아 이 할 일을 끝낼 수 없음. `message`에 먼저 할 일 이름 (FR-020) |
| `EVIDENCE_REQUIRED` | 409 | 증빙이 필요한 할 일을 증빙 없이 `done`으로 바꾸려 함. `hint`는 증빙 올리기 또는 "나중에 올리기"(`skipped`) (FR-029·030) |
| `TODO_NOT_STARTED` | 409 | 잔금일에 하는 할 일(3번 재비교·4번 전입신고)을 시작일 전 날짜로 끝내려 함 |
| `DEPENDENT_DONE` | 409 | 이 할 일을 먼저 끝내야 하는 뒤 할 일이 이미 끝나 있어 되돌릴 수 없음. 뒤 할 일부터 되돌림 |
| `TODO_NOT_PLANNED` | 409 | 계약 조건이 바뀌어 지금 계약에는 없는 끝낸 할 일(기록으로만 남은 것, 예: 5번을 끝내 빠진 6번)을 되돌리려 함. 되돌리면 재계산에서 기록째 지워져서 막음. 기록으로만 남은 할 일은 `DEPENDENT_DONE`의 뒤 할 일로 치지 않음 |
| `ADMIN_TOKEN_INVALID` | 401 | 관리자 API에 `X-Admin-Token` 헤더가 없거나 서버 `ADMIN_TOKEN`과 다름 |
| `ADMIN_DISABLED` | 403 | 서버에 `ADMIN_TOKEN`이 없어 관리자 API가 꺼져 있음 |
| `TRADES_COLLECT_CONFLICT` | 409 | 같은 거래를 동시에 수집한 다른 요청과 겹쳐 저장하지 못함 → 다시 시도 |
| `SERVICE_KEY_MISSING` | 503 | 서버에 공공데이터포털 인증키(`DATA_GO_KR_SERVICE_KEY`)가 없음 |
| `TRADE_API_ERROR` | 502 | 공공데이터포털 실거래가 API 오류(인증키·호출 한도·연결). `message`에 포털이 준 오류 또는 HTTP 상태 코드·연결 오류 종류 (요청 주소·인증키는 싣지 않음) |

`fields`의 규칙:

- `field`는 입력 필드 이름이다 (`registry.mortgage_amount`). 요청 본문 전체가 문제일 때(객체가 아님, JSON이 깨짐, 본문 없음)는 `"body"`이고, 헤더 문제는 헤더 이름(`x-virtual-today`)이다.
- `message`는 한국어 문장이다. 자주 나오는 종류(필수 값 없음, 선택지 아님, 숫자 아님, 범위 벗어남, JSON 깨짐 등)는 번역해 두었고, 번역이 없는 종류는 영어 원문이 나갈 수 있으니 화면에서는 `field` 옆에 그대로 붙이는 용도로만 쓴다.
  - 금액처럼 정수인 필드에 소수를 보내면 "정수로 입력하세요", 파일 필드에 파일이 아닌 값을 보내면 "파일을 올려야 합니다"가 나온다.

`api_error`를 거치지 않고 `HTTPException(상태, "이유")`로 올린 오류는 `code`가 `HTTP_ERROR`이고 `message`에 그 이유가 들어가며 서버 로그에 경고가 남는다. 새 오류는 `api_error`로 코드를 정해서 올린다.

새 오류 코드를 만들면 이 표에 추가한다.

### 1.6 파일 올리기

- `multipart/form-data`, 파일 필드 이름은 `file`
- 등기부 PDF 10MB, 증빙 사진은 20MB까지
- 주민등록번호가 보이는 파일은 받지 않도록 화면에서 가리고 올리라고 안내한다 (NFR-011). 서버는 등기부 원본을 저장하지 않는다 (`/api/registry/parse`)

### 1.7 가상 날짜 (FR-044, 시연용)

- 요청 헤더 `X-Virtual-Today: 2027-08-01`을 보내면 서버는 그날을 "오늘"로 보고 할 일·알림·경보를 계산한다
- 쓰는 곳: `POST /api/checks`의 실거래 기준일(`as_of`), 계약 응답(`POST`·`GET`·`PATCH /api/contracts`, `/cancel`)의 `today`와 할 일 `state`·`days_left`, 알림 실행(`POST /api/admin/notifications/run`, 본문 `date`가 없을 때). 계약 중 경보 재계산은 4주차 (#53·#54)
- 헤더가 없으면 실제 오늘 날짜(한국 시간). 서버가 UTC여도 한국 날짜로 계산한다
- 서버 설정 `ALLOW_VIRTUAL_TODAY`(기본 true): **배포 서버는 `false`**로 두어 헤더를 무시하고 실제 오늘로만 계산한다 (아무 앱이나 다른 날짜 기준 결과를 받지 않게, 형식이 틀린 값도 무시). 시연을 배포 서버에서 하면 **시연 서버는 `true`**로 둔다(가상 날짜 시연·정답표 `as_of` 대조). 관리자 알림 실행의 본문 `date`는 관리자 토큰이 있어야 하므로 그대로 쓴다

### 1.8 로그인·테스트 결제 (2026-10-17 확정, 백엔드 2026-10-22)

결정과 이유는 [`결정자료_로그인_테스트결제.md`](결정자료_로그인_테스트결제.md) 맨 위 "결정"·"세부 규칙". API는 2.1, 오류 코드는 1.5. 앱 연결(배승환)은 3주차.

- 계약 전 확인(`/api/checks`, `/api/registry/parse`)은 그대로 로그인 없이 쓴다 (UC-001)
- **계약별 접근 토큰 (#39)**: `POST /api/contracts` 응답에 `access_token`을 한 번만 준다(서버는 해시만 저장). 계약 아래 API(`GET·PATCH /api/contracts/{id}`, 앞으로 만들 할 일 완료·증빙·서류)는 헤더 `X-Contract-Token`이 맞아야 한다. 토큰이 없거나 틀리면 계약이 없을 때와 같은 404 `NOT_FOUND`(번호를 바꿔 가며 계약이 있는지 알아내지 못하게). 회원 식별은 이메일만 (NFR-011). 휴대폰을 바꾸거나 앱을 지우면 "접근 링크 이메일로 다시 받기"(`POST /api/contracts/access-link`, 2.1)로 다시 들어온다. 다시 받은 토큰은 `contract_tokens`에 해시로 더하고 처음 토큰은 그대로 쓸 수 있다
- 캘린더 파일(`calendar.ics`, #47)은 캘린더 앱이 헤더를 못 보내므로 주소에 별도 구독용 토큰을 넣는다
- **테스트 결제 (#40, FR-013)**: `POST /api/checks/{id}/payment` → `{payment_id, product: "package" | "todo_only", amount, method: "test", status: "paid"}`. 금액은 서버가 판정 단계로 정한다(9,900원, 다가구·단독 할 일 관리만 4,900원). "문제 항목" 판정이면 409 `CHECK_BLOCKED`. 실제 돈은 나가지 않는다
- `POST /api/contracts`에 `payment_id`. 이 판정의 결제이거나 무산된 계약에서 풀린 결제(`released`)여야 하고, 아니면 402 `PAYMENT_REQUIRED`. 풀린 결제는 그 결제를 썼던 무산된 계약의 접근 토큰을 본문 `released_contract_token`으로 함께 보내야 한다(지금 만드는 계약의 토큰이 아니라 `X-Contract-Token` 헤더와 뜻이 달라서. 없으면 402와 접근 링크 다시 받기 안내, 결제 번호만 바꿔 남의 풀린 결제를 쓰지 못하게, `REQUIRE_CONTRACT_AUTH`와 상관없이 언제나). 풀린 결제가 할 일 관리만(4,900원)인데 다음 집이 패키지면 402(다시 결제). 결제 화면은 UI-02의 확인 창
- 계약 무산(FR-016): `POST /api/contracts/{id}/cancel` → 계약 `cancelled`, 결제 `released`. 무산된 계약은 `GET`만 되고 바꾸는 요청은 409 `CONTRACT_CANCELLED`, 알림은 보내지 않는다
- 계약을 만들 때 준 토큰은 서버에 SHA-256 해시만 남는다. 이 기능 전에 만든 계약은 토큰이 없어 `REQUIRE_CONTRACT_AUTH=true`면 열 수 없다 (시연 전 `reset_demo_db.py`로 지움)
- 앱 연결 전까지: 서버 설정 `REQUIRE_CONTRACT_AUTH=false`면 `payment_id`·`X-Contract-Token`이 없는 요청도 통과시킨다(보냈는데 틀리면 402·404). **배포 서버는 처음부터 `true`**. 앱 연결(배승환)이 끝나면 기본값을 `true`로 바꾸고 여기에 날짜를 적는다

## 2. API 목록

A = 개발 A(백엔드·규칙), B = 개발 B(화면). 주차는 노션 "할 일·일정" 기준.

### 2.1 만든 것

| 메서드·주소 | 하는 일 | FR | 화면 |
| --- | --- | --- | --- |
| `GET /health` | 서버·규칙 파일 상태 | | |
| `POST /api/checks` | 계약 전 확인: 입력 → 추정 주택가격·내 보증금 비율 → 판정. 결과 저장. `complex`(시군구 코드·법정동·단지 이름·지번, 아파트·연립다세대만)를 주면 저장된 실거래에서 같은 단지·비슷한 면적의 최근 매매가(`trade_basis`, 공시가격 × 140%와 낮은 값)와 주변 전세 시세(`nearby_jeonse`, 3건 미만이면 표본 부족)를 찾아 기준일(`as_of`)과 함께 돌려준다 | FR-001~004, 009~010 | UI-01, UI-02 |
| `GET /api/checks/{id}` | 저장된 판정 결과. 이 판정으로 만든 계약이 있으면 `contract_id`(없으면 null). 저장된 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED` | FR-009 | UI-02 |
| `GET /api/checks/{id}/special-terms` | 판정에 걸린 연동 규칙에 맞는 공공 자료 특약 예시(문구·출처·연결된 항목)와, 넣음/거절당함을 고르면 생기는 것(경고·서류·맨 위로 올라가는 할 일·상담 창구). 연동 규칙의 계약 당일 경고(`warnings`)·확인(`checks`)도 함께. MVP 연동 규칙(근저당, 비율 90% 이상, 신탁)에 연결된 MVP 특약만. "문제 항목"(결제 전 멈춤) 판정이면 409 `CHECK_BLOCKED`, 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED`. 특약 예시는 지금 규칙 파일 기준 | FR-022, 039, 049~050 | UI-02, UI-03 |
| `GET /api/checks/{id}/todo-preview` | 결제 전 할 일 종류 미리보기: 이 판정으로 패키지를 시작하면 생길 할 일의 종류·시점(`timing`)·증빙·맨 위로 올라가는지(`moved_to_top`)·생기는 조건(`note`, 반환보증 가입 시 등), 상품·금액, 임대차 신고 대상(`report_required`), 가정·안내 문구. **날짜는 주지 않음**(기한·알림·기록함은 패키지에서만). 전세(월세 없음)·반환보증 가입·대출 없음 가정, 판정의 연동 규칙(비율 90% 이상이면 2번 "계약 당일까지")·경보 단계(주의 이상이면 5번 맨 위)는 계약 때와 같게. 순서는 맨 위 할 일 → 번호순. "문제 항목"이면 409 `CHECK_BLOCKED`, 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED` | FR-012 | UI-02 |
| `POST /api/checks/{id}/payment` | 테스트 결제 (실제 돈은 나가지 않음): 판정 단계로 상품·금액을 서버가 정함(패키지 9,900원, 다가구·단독 할 일 관리만 4,900원) → `payment_id`. 같은 판정에 다시 누르면 앞서 한 결제를 200으로 돌려줌. "문제 항목"이면 409 `CHECK_BLOCKED`, 이미 계약을 만든 판정이면 409 `CHECK_ALREADY_USED` | FR-011, 013 | UI-02 (확인 창) |
| `POST /api/admin/trades` | 실거래가 수집 (관리자): 공공데이터포털 API로 한 시군구(`lawd_cd`)의 아파트·연립다세대 매매·전월세를 `end_month`부터 거꾸로 `months`개월(기본 12) 받아 받은 시각(`fetched_at`)과 함께 저장. 같은 거래는 한 번만 저장. `X-Admin-Token` 헤더 = 서버 `ADMIN_TOKEN`이어야 함(없으면 401 `ADMIN_TOKEN_INVALID`, 서버에 `ADMIN_TOKEN`이 없으면 403 `ADMIN_DISABLED`). 인증키가 없으면 503 `SERVICE_KEY_MISSING`, 포털 오류는 502 `TRADE_API_ERROR`, 동시 수집이 겹치면 409 `TRADES_COLLECT_CONFLICT` | FR-046 | |
| `POST /api/registry/parse` | 등기부 PDF → 요약 추출 결과 (저장 안 함). `fields`를 확인·수정해 `POST /api/checks`의 `registry`로 보낸다. 을구 임차권·전세권 보증금은 `fields.lease_amount`(선순위 채권)에 들어 있고, 이미 돌려받았거나 내 계약이면 확인 화면에서 `leases` 항목별로 빼서 보낸다. 같은 보증금이 전세권·임차권으로 함께 있으면 한 항목만 넣고 나머지는 `same_deposit_as`(남긴 항목의 순위번호)를 달아 뺀 상태로 준다 | FR-005~006 | UI-01 |
| `POST /api/contracts` | 패키지 시작: `check_id` + 계약 조건(계약일·잔금일·만기일·월세·대출·보증기관·중개·갱신·공동 계약·알림 이메일·공동 계약자 이메일 `co_tenant_email`(공동 계약일 때만, 알림 이메일과 다른 주소, 아니면 422, FR-043)) + 특약 넣음/거절당함 → 계약 생성. 주택 유형·보증금·공시가격·전용면적은 판정 입력에서 가져온다. "문제 항목" 판정이면 409 `CHECK_BLOCKED`, 이미 계약을 만든 판정이면 409 `CHECK_ALREADY_USED`, 판정 기준이 바뀌었으면 409 `CHECK_OUTDATED`. 특약 결과는 그 판정에서 안내한 특약(MVP 연동 규칙의 특약 예시)만 받고 나머지는 422. 계약을 만들면서 할 일 9종도 생성해 응답 `todos`에 순서대로 넣는다 (신고 대상 판별·조건별 분기·우선 노출·선행 조건, `rules/todos.yaml`). 응답에 `report_required`(신고 대상), `alert_level`(지금 경보 단계, 시작할 때 판정으로 정하고 경보 재계산으로 바뀜)도 넣는다 `payment_id`(테스트 결제)를 확인해 아니면 402 `PAYMENT_REQUIRED`(1.8), 응답에 계약 접근 토큰 `access_token`(이 응답에서 한 번만)과 `status`·`payment_id`, 특약 반영 분기 `special_term_effects`(특약별 넣음/거절당함에 따른 위험 안내·기록함 서류·맨 위로 올라간 할 일·상담 창구, 부속표 E). `GET`·`PATCH` 응답에도 같은 칸 | FR-011, 013~015, 017~020, 049~050 | UI-03, UI-04 |
| `GET /api/contracts/{id}` | 계약 정보와 할 일 목록. 응답 `today`(가상 날짜면 그날)와 할 일마다 `state`(done / upcoming / in_progress / overdue)·`days_left`(1.7). `X-Contract-Token` 확인(1.8), 무산된 계약도 기록으로 볼 수 있음 | FR-014, 017 | UI-03, UI-04 |
| `POST /api/contracts/{id}/move` | 갈아타기 저장: 다음 집 계약일·잔금일·만기일·보증금·계약금(·대출·보증기관·전입 예정일). 지금 집 반환 예정일(9번 할 일 기한)과 비교해 자금 틈 `gap_days`·`gap_amount`(min(지금 집 보증금, 다음 집 잔금), Q5), 두 집 모두 대출이면 대출 순서 `loan_order`, 전입 예정일이 반환 예정일과 같거나 앞서면 `move_in_warning`(반환 확인을 끝냈으면 false), 안내 문구 `warnings`, 다음 집 할 일 9종 `next_todos`, 두 집 할 일을 날짜순으로 묶은 `todos`. 다시 보내면 다음 집 입력을 바꿈(두 번 눌러 동시에 저장해도 하나만 남음). 다음 집 계약일·잔금일이 지금 계약일보다 앞서거나, 대출 실행일이 다음 집 계약일~잔금일 밖이면 422. 반환 확인(9번)을 끝냈으면 그 끝낸 날이 반환일이고 자금 틈·대출 순서·전입 순서 경고는 없음. `X-Contract-Token` 확인, 무산된 계약은 409 | FR-025~027 | UI-07 |
| `POST /api/contracts/{id}/move/next` | 다음 집으로 만든 계약을 갈아타기에 연결: 본문 `next_contract_id`·`next_contract_token`(다음 집 계약을 만들 때 받은 `access_token`). 연결하면 그 계약의 전입신고(4번)를 지금 집 반환 확인(9번) 전에 끝낼 때 409 `MOVE_IN_BEFORE_RETURN`으로 경고(지금 집 무산이면 경고 없음). 갈아타기를 저장하지 않았거나 다음 집 계약이 없거나 토큰이 틀리면 404, 지금 계약과 같으면 422, 무산된 계약 409, 다른 갈아타기에 이미 연결된 계약 409 `NEXT_CONTRACT_LINKED`. 갈아타기 결과(`next_contract_id` 포함)를 돌려줌 | FR-027 | UI-07 |
| `GET /api/contracts/{id}/move` | 저장한 갈아타기를 지금 계약 상태로 다시 계산 (지금 계약의 만기·반환 확인이 바뀌어도 맞게). 저장한 적이 없으면 404, 저장한 입력이 지금 입력 규칙과 맞지 않으면 409 `MOVE_INPUT_OUTDATED`(다시 입력) | FR-025~027 | UI-07 |
| `POST /api/contracts/{id}/registry-compare` | 등기부 재비교 (계약 당일·잔금일): 본문 `registry`(`POST /api/registry/parse` 결과를 확인·수정한 `fields`)와 `stage`(`contract_day` / `balance_day`, 비우면 오늘이 계약일까지면 계약 당일, 그 뒤는 잔금일). 계약 전 확인 판정과 항목별 비교(`items`: 압류·근저당·채권최고액·임차권·전세권·신탁, `change` = `same` / `risk` 새로 생기거나 늘어남 / `eased` 없어지거나 줄어듦). `risk`가 있으면 `hold: true`와 `advice` "계약 보류 후 상담" / "잔금 보류 후 상담"·`hint`. 근저당이 말소되거나 줄어든 것은 변동(`changed`)으로만. 계약 전에 근저당이 있었으면 `mortgage_check_required: true`와 채권최고액 비교 `mortgage_check`(FR-023 필수 확인). 계약 전 확인에서 등기부를 올리지 않았으면 `baseline_missing: true`(다시 올린 등기부에 있는 것은 모두 `risk`). 계약 전 확인 입력에 등기부만 바꿔 같은 규칙으로 다시 판정해 `level_after`·`deposit_ratio_after`(달라지면 등기부 때문), 계약의 판정 기록으로 남김. 새로 걸린 연동 규칙(근저당·비율 90% 이상·신탁)은 할 일에 더하고(빼지는 않음), 경보는 그날 기준으로 이 계약만 바로 다시 계산(`alert_level`·경보 이력, 선순위 채권은 비교한 날이 가장 늦은 등기부). 201, `X-Contract-Token` 확인, 무산된 계약은 409 | FR-023, 048 | UI-03 |
| `GET /api/contracts/{id}/registry-compare` | 이 계약의 등기부 재비교 기록 (올린 순서, 무산된 계약도) | FR-023, 048 | UI-03, UI-05 |
| `PATCH /api/todos/{id}` | 할 일 끝내기·되돌리기: 본문 `status`(`done` 완료 / `skipped` 나중에 올리기 / `todo` 되돌리기)와 `done_date`(없으면 오늘, 가상 날짜면 그날, 오늘보다 뒤거나 계약일보다 앞서면 422, 계약 전날 하는 할 일은 그 시작일까지). `done`은 증빙을 올린 할 일만(아니면 409 `EVIDENCE_REQUIRED`), `skipped`는 완료로 치고 기록함만 빈칸. 먼저 끝낼 할 일이 남았으면 409 `PREREQUISITE_NOT_DONE`, 3·4번을 잔금일 전 날짜로 끝내면 409 `TODO_NOT_STARTED`, 되돌리기는 뒤 할 일부터(409 `DEPENDENT_DONE`), 조건이 바뀌어 목록에서 빠진 끝낸 할 일은 되돌릴 수 없음(409 `TODO_NOT_PLANNED`). 끝낸 날로 뒤 할 일 날짜를 다시 계산해 계약 전체를 돌려줌(`ContractOut`, 할 일마다 `done_date`). 할 일이 속한 계약의 `X-Contract-Token` 확인, 무산된 계약은 409. 갈아타기 다음 집의 전입신고를 지금 집 반환 확인·임차권등기 전에 끝내면 409 `MOVE_IN_BEFORE_RETURN`(본문 `confirm_move_in: true`면 경고를 본 것으로 보고 끝냄) | FR-020, 027, 029~030 | UI-04 |
| `POST /api/todos/{id}/evidence` | 증빙 사진 1장 올리기 → 할 일 완료(`done`), 기록함에 남음. multipart `file`(형식·화질 제한 없음, 20MB까지, 넘으면 413 `FILE_TOO_LARGE`, 빈 파일 422), `done_date`(form, 선택). 아직 안 끝낸 할 일은 오늘(가상 날짜) 끝낸 것으로, 나중에 올리기(`skipped`)였던 할 일은 끝낸 날 그대로 `done`. 다시 올리면 앞 사진을 바꿈. 끝낼 수 있는 조건은 `PATCH /api/todos/{id}`와 같음(선행 조건·3·4번 잔금일 전·미래 날짜). 이미 끝낸 할 일에 `done_date` 없이 사진만 올리면 저장된 끝낸 날·앞 할 일은 다시 보지 않음. 계약 전체를 돌려줌(할 일마다 `evidence_uploaded`). 무산된 계약은 409. 전입 경고는 `PATCH`와 같음(form `confirm_move_in`) | FR-027, 029, 031 | UI-04, UI-05 |
| `GET /api/todos/{id}/evidence` | 올린 증빙 파일 (기록함 보기). 사진(jpg·jpeg·png·gif·webp·heic·heif)·PDF는 화면에 바로(`inline`), 다른 형식(SVG·HTML 포함)은 내려받기(`attachment`, `application/octet-stream`). 없으면 404. 무산된 계약도 볼 수 있음 | FR-029 | UI-05 |
| `DELETE /api/todos/{id}/evidence` | 증빙 삭제 (언제든, 무산된 계약도). 파일을 지우고 완료했던 할 일은 나중에 올리기(`skipped`)로: 완료는 그대로, 기록함만 빈칸. 계약 전체를 돌려줌. 올린 증빙이 없으면 404 | FR-033 | UI-05 |
| `POST /api/contracts/{id}/cancel` | 계약 무산 → 계약 `status: "cancelled"`, 쓴 결제는 `released`(다음 집 계약에 다시 씀). 할 일은 기록으로 남김. `X-Contract-Token` 확인, 이미 무산이면 409 `CONTRACT_CANCELLED` | FR-016 | UI-03 |
| `POST /api/admin/notifications/run` | 알림 실행 (관리자, 시연용): 날짜(본문 `date` → `X-Virtual-Today` → 실제 오늘)를 오늘로 보고 그날 보낼 알림을 만든다. 할 일 시작일·기한 7일 전·1일 전·재알림일(`todos.yaml` `notifications`), 건너뛴 날의 알림은 7일 안의 것만. 나중에 올리기(`skipped`)한 증빙이 필요한 할 일은 나중에 올리기로 바꾼 날(증빙을 지운 날) 7일 뒤 `kind: "evidence"` 앱 안 알림(`evidence_after_days`, FR-030). 앱 안 알림은 `sent`, 이메일은 반환보증(T5·T6)만 보내고(`EMAIL_BACKEND`), 공동 계약자 이메일이 있으면 `channel: "email_co"`로 따로 한 통 더(FR-043, 한쪽이 실패해도 다른 쪽은 보냄), 못 보내면 `failed`로 남겨 다음 실행에서 3번까지 다시 보냄(NFR-008). 알림 이메일이 없거나 그사이 무산·완료, 또는 알림일이 7일보다 지났으면(남은 날 문구가 틀려서) `skipped`. 응답에 `email_sent`·`email_failed`. 같은 알림은 한 번만 | FR-040, 041, 044 | |
| `GET /api/contracts/{id}/alerts/latest` | 최근 역전세 경보: 단계 `level`·`label`, 추정 주택가격, 내 보증금 비율, 기준일 `as_of`, 바로 앞 계산(`previous_level`·`previous_ratio`), 계산 근거 `basis`(공시가격·공시가격 × 140%·같은 단지 매매 실거래와 쓴 여부 `used`·주변 전세 시세·선순위 채권·최소 추정치 여부·단지를 아는지), 계약 시작부터의 이력 `history`(기준일 순서, 같은 날이면 계약 시작 먼저), 데이터 한계 안내 `data_limits`(`alert.yaml` `recalculation.data_limits`). 재계산한 적이 없으면 계약을 시작할 때(계약 전 확인)의 값(`recalculated: false`). 공시가격이 없는 집(다가구·단독)은 404. `X-Contract-Token` 확인, 무산된 계약도 볼 수 있음 | FR-036~038 | UI-09 |
| `POST /api/admin/alerts/recalculate` | 경보 재계산 (관리자): 본문 `date`(→ `X-Virtual-Today` → 실제 오늘)를 기준일로 진행 중 계약의 추정 주택가격·내 보증금 비율·경보 단계를 계약 전 확인과 같은 규칙으로 다시 계산해 이력(`alerts`)에 남긴다. 실거래는 저장된 것(`POST /api/admin/trades`로 수집)에서 판정 때 단지로 찾고(판정 때 사용자가 매매 실거래가를 직접 넣었으면 판정처럼 그 값을 씀, `basis.trade_price_input`), 선순위 채권은 마지막으로 올린 등기부. 이 기능 전에 만든 판정에는 단지 정보가 없어 공시가격으로만 계산하니 시연 DB는 `reset_demo_db.py`로 초기화. `contract_ids`로 일부만, `official_prices`(`{계약 id: 새 공시가격}`)로 공시가격 새 발표를 적재한 뒤 계산. 같은 날 다시 부르면 그날 계산을 바꿈(가상 날짜를 되돌려 앞선 날을 부르면 그날 기록을 바꾸고, 앞 단계는 그날보다 앞선 기록). 단계가 바뀌면 계약 `alert_level`과 할 일을 다시 계산(주의 이상이면 T5 맨 위), 올라가면 앱 안 알림(`kind: "alert"`, 하루 한 건: 같은 날 한 번 더 오르면 그 알림을 새 단계로 고침, `raised`는 그날 앞서 계산한 단계보다도 높을 때만 true). 지금 `alert.yaml`에 없는 예전 단계는 정상으로 봄. 공시가격이 없는 계약·무산된 계약은 건너뜀 | FR-037, 046 | |
| `POST /api/contracts/access-link` | 접근 링크 이메일로 다시 받기: 본문 `{"email"}`(계약 이메일 또는 공동 계약자 이메일, 요청한 주소로 보냄). 그 이메일로 만든 진행 중 계약(무산된 계약도 풀린 결제가 남아 있으면)마다 새 접근 토큰을 만들어 계약 이메일로 보냄(처음 토큰은 그대로, 계약마다 한 시간에 3번). 이메일이 없어도 같은 202 (계약이 있는지 알아내지 못하게). 링크는 `APP_LINK_BASE`가 있으면 `{APP_LINK_BASE}?contract={id}&token=...`, 없으면 접근 코드 | NFR-011 | UI-04 |
| `PATCH /api/contracts/{id}` | 계약 조건(날짜·월세·대출·보증기관·중개·갱신·공동 계약·이메일)과 특약 넣음/거절당함을 바꾸고 할 일을 다시 계산. 보낸 칸만 바꾸고, 특약은 보낸 특약만 바꾼다(그 판정에서 안내한 특약만). 바꾼 뒤 조건이 계약 생성 규칙(날짜 순서·대출 실행일)을 어기거나 꼭 있어야 하는 칸에 null이면 422(아무것도 안 바뀜). 계약일을 뒤로 바꿔 목록에 있는 끝낸 할 일의 끝낸 날이 새 계약일보다 앞서게 되면 422 `contract_date`(그 할 일을 되돌리거나 끝낸 날을 고친 뒤 바꿈), 없는 계약이면 404. 같은 할 일은 `id`·상태·완료일을 유지하고, 끝낸 할 일의 완료일을 뒤 할 일의 기준일로 쓴다. 더는 해당하지 않는 할 일은 지우되 끝낸 것은 맨 뒤에 남긴다. 잔금일이 미뤄져 끝낸 T3·T4의 완료일이 새 잔금일보다 앞서면 다시 할 일로 돌린다. 주택 유형·보증금·`alert_level`은 바꾸지 않는다(경보 단계는 경보 재계산으로만 바뀜) `X-Contract-Token` 확인, 무산된 계약이면 409 `CONTRACT_CANCELLED` | FR-021, 049~050 | UI-03, UI-04 |
| `POST /api/contracts/{id}/documents` | 계약 당일 첫 계약 서류 올리기 (기록함의 첫 서류, 할 일과 별개): multipart `kind`(`contract` 계약서 / `down_payment` 계약금 이체 내역, `todos.yaml` `first_documents`)와 `file`. 종류마다 1장, 다시 올리면 바꿈. 형식·화질 제한 없이 20MB까지(넘으면 413 `FILE_TOO_LARGE`), 빈 파일·없는 종류 422. 계약 전체를 돌려줌(`documents`: 종류마다 `label`·`detail`·`uploaded`·`uploaded_at`, `GET`·`PATCH` 응답에도). `X-Contract-Token` 확인, 무산된 계약은 409 | FR-051 | UI-03, UI-05 |
| `GET /api/contracts/{id}/documents/{kind}` | 올린 첫 계약 서류 파일 (기록함 보기). 사진·PDF는 `inline`, 다른 형식은 내려받기(증빙과 같음). 없으면 404. 무산된 계약도 볼 수 있음 | FR-051 | UI-05 |
| `DELETE /api/contracts/{id}/documents/{kind}` | 첫 계약 서류 삭제 (언제든, 무산된 계약도). 계약 전체를 돌려줌. 올린 서류가 없으면 404 | FR-033 | UI-05 |
| `GET /api/demo-houses` | 시연 집 2채(해운대구 아파트·수영구 빌라, `docs/validation/demo_houses.yaml`): 계약 전 확인 입력값(`input`, 단지·공시가격·전용면적·등기부 확인값 포함. 그대로 `POST /api/checks`로), 시연 등기부를 읽은 결과(`registry`, `POST /api/registry/parse`와 같은 형식, 이름·주소는 가린 값), 시연용 가상 값(`virtual`, 화면에 "시연용 가상" 표시), 계약 당일 장면(`contract_day`, 날짜·특약 결과. 그대로 `POST /api/contracts`로). 정답표와 같은 결과를 보려면 기준일(`as_of`)의 실거래 저장본을 넣고(`cd backend && python load_demo_trades.py`) `X-Virtual-Today`에 그 날짜를 보낸다. `tests/test_demo_houses.py`가 정답표 기대값과 자동 대조 | FR-001, 046 | UI-01, UI-03 |

입출력 예시는 `backend/README.md`, 전체 형식은 `openapi.json`.

### 2.2 만들 것 (안, 만들 때 확정해 2.1로 옮긴다)

GitHub 이슈와 마일스톤(2주차·3주차·4주차)으로 진행을 관리한다.

| 메서드·주소 | 하는 일 | FR | 화면 | 주차 | 이슈 |
| --- | --- | --- | --- | --- | --- |
| `GET /api/contracts/{id}/calendar.ics` | 할 일 기한을 캘린더 파일로 (`text/calendar`) | FR-042 | UI-04 | 3 | #47 |
| `GET /api/contracts/{id}/timeline` | 계약 2년 기록을 날짜순으로 | FR-032 | UI-06 | 4 | #51 |
| `GET /api/contracts/{id}/return-guide` | 반환 대응 단계, 청구 서류 대조 | FR-024, 034~035 | UI-08 | 4 | #52 |

### 2.3 정할 것 (2주차)

로그인(#39)·테스트 결제(#40)는 2026-10-17에 정해 만들었다 → 1.8, 2.1. 지금 정할 것은 없다.

### 2.4 여유 있을 때 (Should)

| 메서드·주소 | 하는 일 | FR | 이슈 |
| --- | --- | --- | --- |
| (`POST /api/registry/parse` 응답) | 등기 항목 쉬운 말 설명 (LLM) | FR-007 | #57 |

이미 있는 API로 되는 것: 다음 집 계약 전 확인(FR-028)은 `POST /api/checks`, 위반건축물 확인(FR-008)은 `POST /api/checks` 입력, 규칙 데이터 관리(FR-045)는 `rules/*.yaml`과 `/health`.

실거래가 API가 안 될 때 쓰는 내려받은 파일 적재(국토교통부 실거래가 공개시스템 파일)는 2주차 안에 API 연동이 끝나지 않을 때 만든다 (기획서 v4.35 범위 축소 규칙).
