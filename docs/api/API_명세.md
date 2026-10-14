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
| `CHECK_ALREADY_USED` | 409 | 이미 계약을 만든 판정 결과로 다시 계약을 만들려 함(동시 요청 포함). `hint`에 만든 계약 주소 |
| `CHECK_OUTDATED` | 409 | 판정 기준(규칙 파일)이 바뀌어 저장된 판정 단계 id를 찾을 수 없음 → 계약 전 확인을 다시. 단계 id 기준이라 `rules_version`만 달라지고 단계 id가 남아 있으면 걸리지 않음. `GET /api/checks/{id}`·`POST /api/contracts` |
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
- 등기부 PDF 10MB, 증빙 사진은 (예정) 10MB까지
- 주민등록번호가 보이는 파일은 받지 않도록 화면에서 가리고 올리라고 안내한다 (NFR-011). 서버는 등기부 원본을 저장하지 않는다 (`/api/registry/parse`)

### 1.7 가상 날짜 (FR-044, 시연용)

- 요청 헤더 `X-Virtual-Today: 2027-08-01`을 보내면 서버는 그날을 "오늘"로 보고 할 일·알림·경보를 계산한다
- 지금 쓰는 곳: `POST /api/checks`의 실거래 기준일(`as_of`). 할 일·알림·경보는 3주차 (#50)
- 헤더가 없으면 실제 오늘 날짜

### 1.8 로그인 (결정 필요)

- 계약 전 확인(`/api/checks`, `/api/registry/parse`)은 로그인 없이 쓴다 (UC-001)
- 패키지 이후(계약·할 일·기록함)의 사용자 확인 방식은 아직 정하지 않았다. 회원 식별은 이메일로 한정한다 (NFR-011). 2주차에 정한다 (#39)
- 출시 전: `GET /api/contracts/{id}`는 지금 인증이 없고 id가 순서대로 매겨져 번호만 바꾸면 남의 이메일·계약 날짜를 볼 수 있다. 로그인 방식을 정할 때 함께 막는다

## 2. API 목록

A = 개발 A(백엔드·규칙), B = 개발 B(화면). 주차는 노션 "할 일·일정" 기준.

### 2.1 만든 것

| 메서드·주소 | 하는 일 | FR | 화면 |
| --- | --- | --- | --- |
| `GET /health` | 서버·규칙 파일 상태 | | |
| `POST /api/checks` | 계약 전 확인: 입력 → 추정 주택가격·내 보증금 비율 → 판정. 결과 저장. `complex`(시군구 코드·법정동·단지 이름·지번, 아파트·연립다세대만)를 주면 저장된 실거래에서 같은 단지·비슷한 면적의 최근 매매가(`trade_basis`, 공시가격 × 140%와 낮은 값)와 주변 전세 시세(`nearby_jeonse`, 3건 미만이면 표본 부족)를 찾아 기준일(`as_of`)과 함께 돌려준다 | FR-001~004, 009~010 | UI-01, UI-02 |
| `GET /api/checks/{id}` | 저장된 판정 결과. 저장된 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED` | FR-009 | UI-02 |
| `GET /api/checks/{id}/special-terms` | 판정에 걸린 연동 규칙에 맞는 공공 자료 특약 예시(문구·출처·연결된 항목)와, 넣음/거절당함을 고르면 생기는 것(경고·서류·맨 위로 올라가는 할 일·상담 창구). 연동 규칙의 계약 당일 경고(`warnings`)·확인(`checks`)도 함께. MVP 연동 규칙(근저당, 비율 90% 이상, 신탁)에 연결된 MVP 특약만. "문제 항목"(결제 전 멈춤) 판정이면 409 `CHECK_BLOCKED`, 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED`. 특약 예시는 지금 규칙 파일 기준 | FR-022, 039, 049~050 | UI-02, UI-03 |
| `POST /api/admin/trades` | 실거래가 수집 (관리자): 공공데이터포털 API로 한 시군구(`lawd_cd`)의 아파트·연립다세대 매매·전월세를 `end_month`부터 거꾸로 `months`개월(기본 12) 받아 받은 시각(`fetched_at`)과 함께 저장. 같은 거래는 한 번만 저장. `X-Admin-Token` 헤더 = 서버 `ADMIN_TOKEN`이어야 함(없으면 401 `ADMIN_TOKEN_INVALID`, 서버에 `ADMIN_TOKEN`이 없으면 403 `ADMIN_DISABLED`). 인증키가 없으면 503 `SERVICE_KEY_MISSING`, 포털 오류는 502 `TRADE_API_ERROR`, 동시 수집이 겹치면 409 `TRADES_COLLECT_CONFLICT` | FR-046 | |
| `POST /api/registry/parse` | 등기부 PDF → 요약 추출 결과 (저장 안 함). `fields`를 확인·수정해 `POST /api/checks`의 `registry`로 보낸다. 을구 임차권·전세권 보증금은 `fields.lease_amount`(선순위 채권)에 들어 있고, 이미 돌려받았거나 내 계약이면 확인 화면에서 `leases` 항목별로 빼서 보낸다. 같은 보증금이 전세권·임차권으로 함께 있으면 한 항목만 넣고 나머지는 `same_deposit_as`(남긴 항목의 순위번호)를 달아 뺀 상태로 준다 | FR-005~006 | UI-01 |
| `POST /api/contracts` | 패키지 시작: `check_id` + 계약 조건(계약일·잔금일·만기일·월세·대출·보증기관·중개·갱신·공동 계약·알림 이메일) + 특약 넣음/거절당함 → 계약 생성. 주택 유형·보증금·공시가격·전용면적은 판정 입력에서 가져온다. "문제 항목" 판정이면 409 `CHECK_BLOCKED`, 이미 계약을 만든 판정이면 409 `CHECK_ALREADY_USED`, 판정 기준이 바뀌었으면 409 `CHECK_OUTDATED`. 특약 결과는 그 판정에서 안내한 특약(MVP 연동 규칙의 특약 예시)만 받고 나머지는 422. 계약을 만들면서 할 일 9종도 생성해 응답 `todos`에 순서대로 넣는다 (신고 대상 판별·조건별 분기·우선 노출·선행 조건, `rules/todos.yaml`). 응답에 `report_required`(신고 대상), `alert_level`(시작할 때의 경보 단계)도 넣는다 | FR-011, 014~015, 017~020, 049 | UI-03, UI-04 |
| `GET /api/contracts/{id}` | 계약 정보와 할 일 목록 | FR-014, 017 | UI-03, UI-04 |

입출력 예시는 `backend/README.md`, 전체 형식은 `openapi.json`.

### 2.2 만들 것 (안, 만들 때 확정해 2.1로 옮긴다)

GitHub 이슈와 마일스톤(2주차·3주차·4주차)으로 진행을 관리한다.

| 메서드·주소 | 하는 일 | FR | 화면 | 주차 | 이슈 |
| --- | --- | --- | --- | --- | --- |
| `PATCH /api/contracts/{id}` | 날짜 변경 → 할 일 재계산, 특약 넣음/거절당함 기록 → 할 일 분기, 계약 무산 (`status: "cancelled"`) | FR-016, 021, 049~050 | UI-03, UI-04 | 2 | #37 |
| `GET /api/demo-houses` | 시연 집 2채(수영구 빌라·해운대구 아파트)의 계약 전 확인 입력값(단지·공시가격·등기부 예시)을 미리 채워 돌려줌 | FR-001, 046 | UI-01 | 2 | #38 |
| `POST /api/contracts/{id}/registry-compare` | 계약 당일·잔금일 등기부를 다시 올려 점검 때와 비교, 바뀐 항목 표시 | FR-023, 048 | UI-03 | 3 | #41 |
| `GET /api/contracts/{id}/todos` | 할 일 목록에 오늘 기준 상태(시작 전·진행 중·지남)를 더해서. 그 전까지는 `GET /api/contracts/{id}`의 `todos`를 쓴다 | FR-040 | UI-04 | 3 | #42 |
| `PATCH /api/todos/{id}` | 완료 체크, "나중에 올리기". 선행 조건이 안 끝났으면 완료 불가 | FR-020, 029~030 | UI-04 | 3 | #43 |
| `POST /api/todos/{id}/evidence` | 증빙 사진 올리기 → 할 일 완료, 기록함에 자동 기록 | FR-029, 031 | UI-05 | 3 | #44 |
| `DELETE /api/todos/{id}/evidence` | 증빙 삭제 | FR-033 | UI-05 | 3 | #45 |
| `POST /api/contracts/{id}/documents` | 첫 계약 서류(계약서·이체 내역) 저장 | FR-051 | UI-03, UI-05 | 3 | #46 |
| `GET /api/contracts/{id}/calendar.ics` | 할 일 기한을 캘린더 파일로 (`text/calendar`) | FR-042 | UI-04 | 3 | #47 |
| `POST /api/contracts/{id}/move` | 갈아타기: 다음 집 날짜·보증금·계약금 → 자금 틈, 전입 순서 경고 (저장) | FR-025~028 | UI-07 | 3 | #48 |
| `POST /api/admin/notifications/run` | 알림 스케줄러를 지정한 날(가상 날짜)로 한 번 실행. 이메일 1종 실제 발송 (시연용, 평소에는 서버 안 스케줄러) | FR-041, 044 | | 3 | #49 |
| (공통) | 가상 날짜(`X-Virtual-Today`)를 할 일 상태·알림·경보 계산에도 적용 (1.7) | FR-044 | UI-04, UI-09 | 3 | #50 |
| `GET /api/contracts/{id}/timeline` | 계약 2년 기록을 날짜순으로 | FR-032 | UI-06 | 4 | #51 |
| `GET /api/contracts/{id}/return-guide` | 반환 대응 단계, 청구 서류 대조 | FR-024, 034~035 | UI-08 | 4 | #52 |
| `GET /api/contracts/{id}/alerts/latest` | 최근 역전세 경보 단계·계산 근거·기준일 | FR-036~038 | UI-09 | 4 | #53 |
| `POST /api/admin/alerts/recalculate` | 경보 재계산 (관리자, 스케줄러는 서버 안에서 직접 실행) | FR-037 | | 4 | #54 |

### 2.3 정할 것 (2주차)

| 무엇 | 안 | 이슈 |
| --- | --- | --- |
| 패키지 이후 로그인·사용자 확인 (1.8) | 계약별 접근 토큰 / 이메일 인증번호 / 매직링크 / 소셜 로그인. 정해지면 계약·할 일 API에 적용. 선택지 비교는 [`결정자료_로그인_테스트결제.md`](결정자료_로그인_테스트결제.md) | #39 |
| 테스트 결제 (FR-013) | 화면에서만 / 서버에 테스트 결제 기록(`POST /api/checks/{id}/payment`) / PG 테스트 모드. 선택지 비교는 같은 문서 | #40 |

### 2.4 여유 있을 때 (Should)

| 메서드·주소 | 하는 일 | FR | 이슈 |
| --- | --- | --- | --- |
| `GET /api/checks/{id}/todo-preview` | 결제 전에 생길 할 일 종류 미리보기. 화면이 규칙 파일로 그리면 생략 | FR-012 | #56 |
| (`POST /api/registry/parse` 응답) | 등기 항목 쉬운 말 설명 (LLM) | FR-007 | #57 |
| (`POST /api/contracts` 입력) | 공동 계약자 이메일, 같은 알림 발송 | FR-043 | #58 |

이미 있는 API로 되는 것: 다음 집 계약 전 확인(FR-028)은 `POST /api/checks`, 위반건축물 확인(FR-008)은 `POST /api/checks` 입력, 규칙 데이터 관리(FR-045)는 `rules/*.yaml`과 `/health`.

실거래가 API가 안 될 때 쓰는 내려받은 파일 적재(국토교통부 실거래가 공개시스템 파일)는 2주차 안에 API 연동이 끝나지 않을 때 만든다 (기획서 v4.35 범위 축소 규칙).
