# 전동기 API 명세

- 기준: 요구사항 명세서 v0.4, 규칙 파일 v1.0
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
| 금액 | 원 단위 정수 | `150000000` |
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
    "message": "\"주요 등기사항 요약\" 페이지를 찾지 못했습니다",
    "hint": "등기부 요약을 읽지 못했습니다. 수동 입력 화면에서 직접 입력하세요",
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
| `CHECK_BLOCKED` | 409 | (예정) "문제 항목" 판정이라 패키지를 시작할 수 없음 (FR-011) |

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

- 요청 헤더 `X-Virtual-Today: 2027-08-01`을 보내면 서버는 그날을 "오늘"로 보고 할 일·알림·경보를 계산한다 (예정)
- 헤더가 없으면 실제 오늘 날짜

### 1.8 로그인 (결정 필요)

- 계약 전 확인(`/api/checks`, `/api/registry/parse`)은 로그인 없이 쓴다 (UC-001)
- 패키지 이후(계약·할 일·기록함)의 사용자 확인 방식은 아직 정하지 않았다. 회원 식별은 이메일로 한정한다 (NFR-011). 2주차에 정한다

## 2. API 목록

A = 개발 A(백엔드·규칙), B = 개발 B(화면). 주차는 노션 "할 일·일정" 기준.

### 2.1 만든 것

| 메서드·주소 | 하는 일 | FR | 화면 |
| --- | --- | --- | --- |
| `GET /health` | 서버·규칙 파일 상태 | | |
| `POST /api/checks` | 계약 전 확인: 입력 → 추정 주택가격·내 보증금 비율 → 판정. 결과 저장 | FR-001~003, 009~010 | UI-01, UI-02 |
| `GET /api/checks/{id}` | 저장된 판정 결과 | FR-009 | UI-02 |
| `POST /api/registry/parse` | 등기부 PDF → 요약 추출 결과 (저장 안 함). `fields`를 확인·수정해 `POST /api/checks`의 `registry`로 보낸다 | FR-005~006 | UI-01 |

입출력 예시는 `backend/README.md`, 전체 형식은 `openapi.json`.

### 2.2 만들 것 (안, 만들 때 확정해 2.1로 옮긴다)

| 메서드·주소 | 하는 일 | FR | 화면 | 주차 |
| --- | --- | --- | --- | --- |
| `GET /api/checks/{id}/special-terms` | 판정에 걸린 연동 규칙에 맞는 공공 자료 특약 예시 | FR-039 | UI-02, UI-03 | 2 |
| `POST /api/contracts` | 패키지 시작: `check_id` + 계약 조건(계약일·잔금일·만기일·대출·보증기관 등) → 계약 생성, 할 일 생성. "문제 항목" 판정이면 409 `CHECK_BLOCKED` | FR-011, 013~015, 017~018 | UI-03 | 2 |
| `GET /api/contracts/{id}` | 계약 정보 | FR-014 | UI-03 | 2 |
| `PATCH /api/contracts/{id}` | 날짜 변경 → 할 일 재계산, 특약 넣음/거절당함 기록 → 할 일 분기, 계약 무산 (`status: "cancelled"`) | FR-016, 021, 049~050 | UI-03, UI-04 | 2~3 |
| `POST /api/contracts/{id}/registry-compare` | 계약 당일·잔금일 등기부를 다시 올려 점검 때와 비교, 바뀐 항목 표시 | FR-023, 048 | UI-03 | 3 |
| `GET /api/contracts/{id}/todos` | 할 일 목록 (기한·선행 조건·우선 노출 순서) | FR-017~020, 040 | UI-04 | 3 |
| `PATCH /api/todos/{id}` | 완료 체크, "나중에 올리기" | FR-029~030 | UI-04 | 3 |
| `POST /api/todos/{id}/evidence` | 증빙 사진 올리기 → 할 일 완료 | FR-029, 031 | UI-05 | 3 |
| `DELETE /api/todos/{id}/evidence` | 증빙 삭제 | FR-033 | UI-05 | 3 |
| `POST /api/contracts/{id}/documents` | 첫 계약 서류(계약서 등) 저장 | FR-051 | UI-03, UI-05 | 3 |
| `GET /api/contracts/{id}/calendar.ics` | 할 일 기한을 캘린더 파일로 (`text/calendar`) | FR-042 | UI-04 | 3 |
| `GET /api/contracts/{id}/timeline` | 계약 2년 기록을 날짜순으로 | FR-032 | UI-06 | 4 |
| `POST /api/contracts/{id}/move` | 갈아타기: 다음 집 날짜 → 자금 틈, 전입 순서 경고 (저장) | FR-025~028 | UI-07 | 3 |
| `GET /api/contracts/{id}/return-guide` | 반환 대응 단계, 청구 서류 대조 | FR-024, 034~035 | UI-08 | 4 |
| `GET /api/contracts/{id}/alerts/latest` | 최근 역전세 경보 단계·계산 근거·기준일 | FR-036~038 | UI-09 | 4 |
| `POST /api/admin/trades` | 실거래 CSV 적재 (관리자) | FR-046 | | 4 |
| `POST /api/admin/alerts/recalculate` | 경보 재계산 (관리자, 스케줄러는 서버 안에서 직접 실행) | FR-037 | | 4 |

주변 전세 시세 비교(FR-004)는 실거래 CSV 적재(FR-046) 뒤에 `POST /api/checks` 응답에 넣는다.
