# 백엔드 (FastAPI)

규칙 파일(`../rules/*.yaml`)을 읽어 판정·경보·할 일을 계산하는 API 서버. 기준값은 코드에 두지 않고 규칙 파일에서만 읽는다 (FR-045).

## 실행

```bash
cd backend
pip install -r requirements.txt

# PostgreSQL (Docker가 있으면)
docker compose up -d
export DATABASE_URL=postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse

# DB 설치 없이 해 볼 때
# export DATABASE_URL=sqlite:///./jeonse.db

uvicorn app.main:app --reload
```

- API 문서: http://localhost:8000/docs
- 테이블은 서버 시작 때 자동으로 만든다 (MVP). 스키마가 자주 바뀌기 시작하면 Alembic으로 옮긴다.
- `create_all`은 없는 테이블만 만들고 이미 있는 테이블의 칸은 바꾸지 않는다. 모델이 바뀌면(예: 금액 칸 `Integer` → `BigInteger`) 로컬 DB를 지우고 다시 띄운다 (데이터도 지워진다).

  ```bash
  docker compose down -v
  docker compose up -d
  ```

- 금액(원) 칸은 `BigInteger`로 둔다. PostgreSQL `integer`는 최대 2,147,483,647원(약 21.4억)이라 공시가격 15.3억이 넘으면 추정 주택가격(×1.4)부터 저장되지 않는다. SQLite는 정수 크기를 가리지 않아 테스트에서 드러나지 않으니 `tests/test_money_columns.py`가 칸 형식을 따로 검사한다.
- 배포 서버에서는 `DATABASE_URL`만 그 서버의 PostgreSQL 주소로 바꾸면 된다.
- 웹(`npx expo start --web`)은 개발 편의용이다. 브라우저가 API를 부르려면 `.env`에 `CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081`(Expo 웹 개발 서버, 쉼표로 더함)을 넣는다. 기본은 빈 값이라 꺼져 있다(배포 서버는 비워 둠). 서버 오류(500)에도 허용한 주소면 CORS 헤더를 붙인다. 휴대폰 앱(Expo Go)은 CORS와 상관없다. 쿠키는 쓰지 않고 계약 토큰은 헤더(`X-Contract-Token`)로 보낸다
- 환경 변수는 `.env.example`을 `backend/.env`로 복사해 채운다(`.env`는 git에 올리지 않음). 서버는 `.env`를 자동으로 읽지 않으므로 `uvicorn app.main:app --host 0.0.0.0 --env-file .env`로 띄운다. 실거래가 조회(2주차)에는 공공데이터포털 일반 인증키가 필요하다 (Encoding·Decoding 키 아무거나, 활용신청할 API 목록은 `.env.example`).
- 테이블은 서버가 시작할 때 `create_all`로 만들기 때문에 **이미 있는 테이블에는 새 칸이 생기지 않는다**. 모델(`app/models.py`)이 바뀐 브랜치를 받으면 로컬 DB를 다시 만든다: `docker compose down -v && docker compose up -d` (SQLite는 파일을 지운다). 배포 전까지는 이렇게 하고, 배포 서버에 데이터가 쌓이기 시작하면 Alembic을 들인다

## 테스트

```bash
pytest                      # 임시 SQLite 파일로 실행 (DB 설치 불필요)
TEST_DATABASE_URL=postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse_test pytest
```

시연 흐름만 돌려 보려면 `pytest tests/test_demo_flow.py -v`: 시연 집 2채로 계약 전 확인 → 결제 → 계약 당일(담보 설정 금지 "거절당함"으로 할 일 순서가 바뀌는 장면) → 가상 날짜로 계약 2년(증빙·반환보증 알림 이메일·경보 재계산·갈아타기·반환 확인)을 배포 서버처럼 결제·접근 토큰을 요구하는 설정으로 이어서 돌린다. 리허설 전에 서버 쪽 연결이 끊긴 곳이 없는지 본다.

PR을 열거나 main에 푸시하면 GitHub Actions(`.github/workflows/test.yml`)가 같은 테스트(SQLite)와 `rules/check_rules.py`를 자동으로 돌린다. 의존성은 `requirements.txt`에 버전을 정확히 고정했으니, 올릴 때는 PR로 바꾸고 CI 통과를 확인한다.

## 구조

| 경로 | 내용 |
| --- | --- |
| `app/main.py` | 앱, `/health` |
| `app/config.py` | 환경 변수 (`DATABASE_URL`, `RULES_DIR`, `DATA_GO_KR_SERVICE_KEY`) |
| `app/db.py` | DB 연결, 세션 |
| `app/models.py` | 데이터 모델: 계약(`contracts`), 판정(`verdicts`), 할 일(`todos`), 경보(`alerts`) |
| `app/schemas.py` | API 입출력 형식 |
| `app/errors.py` | 오류 응답 형식 (`{"detail": {code, message, hint, fields}}`) |
| `export_openapi.py` | `docs/api/openapi.json` 다시 만들기 |
| `measure_registry_accuracy.py` | 등기부 요약 추출 정확도 측정 (정답표 `docs/validation/registry_answers.yaml`, 결과 `docs/validation/등기부추출_정확도.md`) |
| `app/rules/loader.py` | 규칙 파일 불러오기 |
| `app/rules/conditions.py` | 규칙의 조건(`when`) 계산 |
| `app/engine/price.py` | 추정 주택가격, 내 보증금 비율 (alert.yaml) |
| `app/engine/verdict.py` | 판정 4단계 (verdict.yaml) |
| `app/engine/check.py` | 계약 전 확인: 입력 → 비율 → 판정 |
| `app/engine/todos.py` | 할 일 9종 생성: 기한·선행 조건·순서 (todos.yaml, guarantors.yaml, linkage.yaml) |
| `app/engine/return_response.py` | 반환 대응 단계(보증기관별)와 청구 서류 대조 (todos.yaml `return_response`) |
| `app/engine/alert.py` | 경보 단계 (alert.yaml) |
| `app/engine/move.py` | 갈아타기: 자금 틈·대출 순서·전입 순서 경고 (정답표 S10) |
| `app/engine/market.py` | 같은 단지·비슷한 면적의 최근 매매가, 주변 전세 시세 중앙값 (alert.yaml) |
| `app/trades/client.py` | 공공데이터포털 실거래가 API 4종 호출·응답 해석 |
| `app/trades/collect.py` | 실거래 수집·저장 (같은 거래는 한 번만) |
| `app/api/admin.py` | `POST /api/admin/trades` |
| `app/engine/special_terms.py` | 판정에 맞는 특약 예시와 넣음/거절당함 결과 (special_terms.yaml, linkage.yaml) |
| `app/api/checks.py` | `POST /api/checks`, `GET /api/checks/{id}`, `GET /api/checks/{id}/special-terms` |
| `app/api/contracts.py` | `POST /api/contracts`, `GET /api/contracts/{id}` |
| `app/api/moves.py` | `POST`·`GET /api/contracts/{id}/move` 갈아타기, `POST .../move/next` 다음 집 계약 연결, 전입 경고(`check_move_in`) |
| `app/api/recompare.py` | `POST`·`GET /api/contracts/{id}/registry-compare` 등기부 재비교 |
| `app/engine/registry_compare.py` | 등기부 재비교: 항목별 변동·보류 안내 |
| `app/api/todos.py` | `PATCH /api/todos/{id}` 할 일 끝내기·나중에 올리기·되돌리기, `POST`·`GET`·`DELETE /api/todos/{id}/evidence` 증빙 |
| `app/api/returns.py` | `POST`·`DELETE /api/contracts/{id}/return-response` "못 받음"·되돌리기, `GET /api/contracts/{id}/return-guide` 반환 대응 안내 |
| `app/engine/calendar.py` | 할 일 → ICS (앱 내보내기와 같은 UID·알림) |
| `app/api/calendar.py` | 캘린더 구독 주소 만들기·끊기(`/api/contracts/{id}/calendar-link`), 구독 파일(`/api/calendar/{token}.ics`) |
| `app/api/documents.py` | `POST /api/contracts/{id}/documents`, `GET`·`DELETE /api/contracts/{id}/documents/{kind}` 첫 계약 서류 |
| `app/evidence.py` | 증빙 파일 저장·삭제 (`EVIDENCE_DIR`, 기본 `backend/data/evidence`, git 제외) |
| `app/api/alerts.py` | `GET /api/contracts/{id}/alerts/latest` 경보 리포트 |
| `app/alerts.py` | 역전세 경보 재계산 (`POST /api/admin/alerts/recalculate`): 계약 중 비율·단계 다시 계산, 할 일·알림 |
| `app/registry/pdf.py` | 등기부 PDF → 요약 페이지 글자 ("부동산정보요약" 또는 증명서의 "주요 등기사항 요약", pdfplumber) |
| `app/registry/parser.py` | 요약 글자 → 소유자, 근저당 채권최고액, 압류 등, 신탁 (규칙 파서) |
| `app/api/registry.py` | `POST /api/registry/parse`, `POST /api/registry/explain` |
| `app/explain.py` | 등기 항목 쉬운 말 설명: Claude API 호출, 금지 표현·숫자 검사, 템플릿 대체 (rules/explain.yaml) |
| `app/api/demo.py` | `GET /api/demo-houses` 시연 집 2채 (`docs/validation/demo_houses.yaml`) |
| `load_demo_trades.py` | 시연 집 정답표의 실거래 저장본을 DB에 넣기 |
| `reset_demo_db.py` | 시연 전 DB 초기화 (모든 표를 다시 만들고 실거래 저장본 넣기) |
| `tests/fixtures/registry/` | 등기부 요약 샘플 (실제 샘플은 집을 찾을 수 없게 바꿈, 가상 샘플) |

## API

공통 규칙(주소, 상태 코드, 금액·날짜 표기, 오류 형식)과 전체 API 목록은 [`docs/api/API_명세.md`](../docs/api/API_명세.md). API를 바꾸면 `python export_openapi.py`로 `docs/api/openapi.json`을 다시 만든다. `tests/test_openapi.py`가 설명 문구(`description`)를 뺀 내용(주소, 요청·응답, 스키마 필드)이 서버 코드와 같은지 검사한다. 파일 서식은 검사하지 않는다.

### `POST /api/checks` 계약 전 확인

```json
{
  "housing_type": "row_house",
  "deposit": 150000000,
  "official_price": 200000000,
  "registry": {"mortgage": true, "mortgage_amount": 120000000}
}
```

- `housing_type`: `apartment` / `row_house` / `officetel` / `multi_household` / `detached`
- `registry`를 비워 두면 등기부를 올리기 전으로 보고 선순위 채권 0원으로 계산한 **최소 추정치**를 낸다 (`ratio_is_minimum: true`)
- 다가구·단독이 아니면 `official_price`가 있어야 한다 (없으면 422)
- 선택 입력: `trade_price`(같은 단지·비슷한 면적 매매 실거래가), `trust_consent`, `building_violation`, `guarantor_consult`

응답: 판정 단계(`level`, `label`, `next_step`, `block_payment`), 추정 주택가격, 내 보증금 비율, 걸린 규칙(`matched`, 항목마다 쉬운 말 설명 `explanation`), 연동 규칙(`linkages`), 확인 못 한 항목(`unchecked`, 확인 방법 `guide`), 안내 문구(`disclaimer`), 규칙 버전. `explanation`·`guide`는 판정을 만들 때 저장한 문구를 그대로 돌려준다(사용자가 그때 본 문구를 남김). 계약의 신고 대상·경보 단계·할 일도 같은 원칙으로 만들 때 저장한다.

### `POST /api/checks/{id}/payment` 테스트 결제 (FR-013)

본문 없음. 실제 돈은 나가지 않는다.

```json
{"payment_id": 1, "check_id": 1, "product": "package", "amount": 9900, "method": "test", "status": "paid"}
```

- 상품·금액은 판정 단계로 서버가 정한다: 다가구·단독(대상 아님)은 `todo_only` 4,900원, 나머지는 `package` 9,900원 (`app/engine/payment.py`)
- 같은 판정에 다시 누르면 새로 만들지 않고 앞서 한 결제를 200으로 돌려준다
- "문제 항목"이면 409 `CHECK_BLOCKED`, 이미 계약을 만든 판정이면 409 `CHECK_ALREADY_USED`
- 결제 상태: `paid`(결제함) → `used`(계약에 씀) → 계약 무산이면 `released`(다음 집 계약에 다시 씀) → 다시 쓰면 `used`

### `POST /api/contracts` 패키지 시작·계약 생성·할 일 생성 (FR-011·014·015·017~020·049)

```json
{
  "check_id": 1,
  "contract_date": "2026-11-02",
  "balance_date": "2026-12-01",
  "end_date": "2028-11-30",
  "loan": true,
  "loan_execution_date": "2026-12-01",
  "guarantor": "HUG",
  "email": "tenant@example.com",
  "special_term_result": {"S-NO-MORTGAGE": "rejected"},
  "payment_id": 1
}
```

- `payment_id`: 이 판정의 결제(`paid`)이거나 무산된 계약에서 풀린 결제(`released`)여야 한다. 아니면 402 `PAYMENT_REQUIRED`. 풀린 결제는 무산된 계약의 접근 토큰을 본문 `released_contract_token`으로 함께 보내야 다시 쓴다(없으면 402와 "접근 링크 다시 받기" 안내, 틀리면 402). 지금 만드는 계약의 토큰이 아니라서 `X-Contract-Token` 헤더로 받지 않는다. 풀린 결제가 할 일 관리만(4,900원)인데 이 집이 패키지면 402(다시 결제), 반대는 그대로 쓴다. 서버 설정 `REQUIRE_CONTRACT_AUTH`가 false(기본, 앱 연결 전)면 `payment_id` 없이도 만든다
- 응답의 `access_token`(계약 접근 토큰)은 **이 응답에서 한 번만** 준다. 서버에는 SHA-256 해시만 남는다. 앱은 계약 id와 함께 저장해 두고 계약 아래 요청에 `X-Contract-Token` 헤더로 보낸다
- 주택 유형·보증금·공시가격·전용면적은 `check_id` 판정의 입력을 그대로 쓴다. 보증금이 바뀌었으면 계약 전 확인을 다시 한다
- 선택 입력과 기본값: `monthly_rent` 0, `loan` false, `guarantor` `none`(HUG / HF / SGI / none), `brokered` true(직거래면 false), `renewal_right_used` false, `co_tenant` false, `email`, `special_term_result`(키는 `special_terms.yaml`의 id, 값은 `inserted` / `rejected`)
- 날짜: 잔금일 ≥ 계약일, 만기일 > 잔금일. 대출이 없으면 `loan_execution_date`를 비워 둔다
- "문제 항목" 판정이면 409 `CHECK_BLOCKED`, 한 판정으로 계약을 두 번 만들면 409 `CHECK_ALREADY_USED`(만든 계약 id는 `GET /api/checks/{id}`의 `contract_id`)
- 응답: 입력한 계약 조건 + `id`, `check_id`, `level`(시작할 때의 판정 단계), 판정에서 가져온 주택 정보, `report_required`(임대차 신고 대상), `alert_level`(판정 때 비율로 정한 경보 단계, 정상이면 null), `status`(`active` / `cancelled`), `payment_id`, `access_token`, `special_term_effects`, `todos`(할 일 목록)
- `special_term_effects`: 기록한 특약마다 `{term_id, label, result, warnings, documents, moves_to_top, adds_todos, link_counsel}` (명세서 부속표 E, `special_terms.yaml`의 `on_inserted`·`on_rejected`). 넣음이면 기록함에 남길 서류(특약이 보이는 계약서 사진), 거절당함이면 위험 안내·맨 위로 올라간 할 일(담보 설정 금지 → T4, 보증 거절 시 해제 → T2)·공공 상담 창구. 할 일 순서 자체는 `todos.yaml` `move_to_top_when`이 바꾸고, 두 파일이 서로 맞는지는 `rules/check_rules.py`가 검사한다
- `todos`는 `sort_order` 순서다: 맨 위 규칙(특약 거절·경보, `moved_to_top`) → 고정(T5~T9, `pinned`) → 기한 빠른 순. 재알림(T6·T8)은 `due_date` 대신 `remind_date`, HF·SGI 반환보증(T5)은 기관 기준이 없어 `due_date`가 null. 대출은 있는데 `loan_execution_date`를 비우면 T5 시작일은 전입신고(T4) 다음 날
- 기한 계산은 `docs/validation/기한계산_정답표.md`의 계산 약속을 따르고, `tests/test_todos.py`가 정답표(`deadline_scenarios.yaml`) S1~S10·재계산 3개와 대조한다
- `contracts` 테이블에 `check_id`(unique)·`email`·`report_required`·`alert_level`, `todos`에 새 칸들을, `verdicts`에 `market` 칸과 `trades` 테이블을 넣었다. 금액 칸은 BigInteger로 바꿨다. 예전에 만든 DB는 위 안내대로 다시 만든다

### `PATCH /api/contracts/{id}` 계약 조건·특약 결과 변경 → 할 일 재계산 (FR-021·049·050)

```json
{"balance_date": "2026-12-22", "loan_execution_date": "2026-12-22"}
```

```json
{"special_term_result": {"S-NO-MORTGAGE": "rejected"}}
```

- 보낸 칸만 바꾼다. 바꿀 수 있는 것: 날짜 3개, `monthly_rent`, `loan`, `loan_execution_date`, `guarantor`, `brokered`, `renewal_right_used`, `co_tenant`, `email`, `special_term_result`. 주택 유형·보증금은 판정에서 가져온 값이라 못 바꾼다 (보증금이 바뀌면 계약 전 확인부터 다시)
- `special_term_result`는 보낸 특약만 바꾸고 나머지는 그대로 둔다. 그 판정에서 안내한 특약만 받는다 (계약 생성과 같은 기준)
- `loan_execution_date`·`email`은 `null`을 보내면 지운다. 다른 칸에 `null`을 보내면 422
- 바꾼 뒤의 조건 전체가 계약 생성 때와 같은 규칙(잔금일 ≥ 계약일, 만기일 > 잔금일, 대출이 없으면 실행일 없음)을 지켜야 한다. 아니면 422이고 아무것도 바뀌지 않는다
- 할 일은 같은 엔진으로 다시 계산한다. 같은 할 일은 `id`·`status`·완료일을 그대로 두고 날짜·순서만 바꾼다. 끝낸 할 일의 완료일은 뒤 할 일의 기준일로 쓴다 (전입신고 완료 다음 날 → 반환보증 가입 시작). 조건이 바뀌어 더는 해당하지 않는 할 일(보증 미가입으로 바꾼 T5·T6, 신고 비대상이 된 T1)은 지우고, 이미 끝낸 것은 맨 뒤에 기록으로 남긴다
- 잔금일이 미뤄져 끝낸 잔금일 아침 등기부 재비교(T3)·전입신고(T4)의 완료일이 새 잔금일보다 앞서면 다시 `todo`로 돌린다 (`todos.yaml` `reopen_if_done_before_start`, PO 2026-10-15). 올린 증빙은 지우지 않는다. 전입신고가 다시 할 일이 되면 반환보증 가입(T5) 시작일도 새 잔금일 기준으로 다시 계산된다
- `alert_level`(시작할 때의 경보 단계)은 바꾸지 않는다. 계약 중 재계산은 4주차 (FR-037)
- `X-Contract-Token`을 확인한다 (아래). 무산된 계약이면 409 `CONTRACT_CANCELLED`

### 가상 날짜와 알림 실행 (FR-040·041·044)

- 계약 응답(`POST`·`GET`·`PATCH /api/contracts`, `/cancel`)에 `today`, 할 일마다 `state`(`done` / `upcoming` 시작 전 / `in_progress` / `overdue` 기한 지남)와 `days_left`. 헤더 `X-Virtual-Today: 2027-11-08`을 보내면 그날 기준 (`app/clock.py`, `app/engine/schedule.py`). 헤더가 없으면 한국 시간 오늘. 배포 서버는 `ALLOW_VIRTUAL_TODAY=false`로 헤더를 무시한다. 할 일 `status`가 `skipped`면 `state`는 `done`
- `POST /api/admin/notifications/run` (관리자, `X-Admin-Token`): 본문 `{"date": "2027-11-08"}`(없으면 `X-Virtual-Today`, 그것도 없으면 오늘)을 오늘로 보고 그날 보낼 알림을 만들어 `notifications` 표에 남긴다
  - 언제: 할 일 시작일(재알림 T6·T8은 알림일), 기한 7일 전·1일 전 (`rules/todos.yaml` `notifications`, 팀 제안 값)
  - 건너뛴 날: 알림일이 지났어도 7일 안이면 보낸다. 가상 날짜로 몇 달을 건너뛰어도 지난 알림이 쏟아지지 않는다
  - 경로: 앱 안 알림은 `sent`. 이메일은 MVP 1종(반환보증 가입 T5·마감 30일 전 재알림 T6)만 보낸다. 공동 계약자 이메일(`co_tenant_email`, FR-043)이 있으면 `email_co` 경로로 따로 보낸다(주소마다 기록·재시도). 못 보내면 `failed`로 남겨 다음 실행에서 3번까지 다시 보낸다(NFR-008). 알림 이메일이 없거나 그사이 무산·완료면 `skipped`
  - 같은 할 일·종류·알림일·경로는 한 번만 만든다. 무산된 계약·끝낸 할 일은 알리지 않는다
- 시연: 가상 날짜를 반환보증 가입 기한 7일 전으로 두고 알림 실행 → 반환보증 이메일이 나감 (AC-010)
- 이메일 보내는 방법은 `EMAIL_BACKEND` (`app/mailer.py`): `console`(기본, 보내지 않고 서버 로그에만), `smtp`(실제 발송, `SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_FROM`, Gmail은 앱 비밀번호), `memory`(테스트). `.env.example` 참고

### `PATCH /api/todos/{id}` 할 일 끝내기·나중에 올리기·되돌리기 (FR-020·029·030, #43)

- 본문 `{"status": "skipped"}`(나중에 올리기: 완료로 치고 기록함만 빈칸), `"done"`(증빙을 올린 할 일만), `"todo"`(되돌리기). `done_date`가 없으면 오늘(가상 날짜면 그날)
- 막는 것(409): 먼저 끝낼 할 일이 남음 `PREREQUISITE_NOT_DONE`, 증빙 없이 완료 `EVIDENCE_REQUIRED`, 3·4번을 잔금일 전 날짜로 `TODO_NOT_STARTED`, 뒤 할 일이 끝났는데 되돌리기 `DEPENDENT_DONE`, 목록에서 빠진 끝낸 할 일 되돌리기 `TODO_NOT_PLANNED`(재계산 때 `Todo.archived`로 표시, 이런 기록은 `DEPENDENT_DONE`에서 빼고 셈), 무산된 계약 `CONTRACT_CANCELLED`. 끝낸 날이 오늘보다 뒤거나 계약일(계약 전날 하는 할 일은 시작일)보다 앞서면 422. `PATCH /api/contracts/{id}`로 계약일을 뒤로 바꿔 끝낸 날이 앞서게 돼도 422
- 끝낸 날은 뒤 할 일의 기준일이라(전입신고 완료 다음 날 → 반환보증 시작) 바꿀 때마다 계약의 할 일을 다시 계산해 계약 전체를 돌려준다. `skipped`도 끝낸 할 일로 친다
- 할 일 `id`는 계약 응답 `todos[].id`. 헤더 `X-Contract-Token`은 그 할 일이 속한 계약의 토큰

### 증빙 사진 올리기·보기·삭제 (FR-029·031·033, #44·#45)

- `POST /api/todos/{id}/evidence` (multipart `file`, 선택 `done_date`): 사진 1장으로 할 일 완료(`done`). 형식·화질 제한 없이 20MB까지. 나중에 올리기였던 할 일은 끝낸 날 그대로 `done`, 다시 올리면 앞 사진을 바꿈. 끝낼 수 있는 조건은 `PATCH /api/todos/{id}`와 같음(이미 끝낸 할 일에 사진만 올리면 끝낸 날·앞 할 일은 다시 보지 않음). 20MB 검사는 업로드를 다 받은 뒤라, 배포 때는 프록시에서 요청 크기도 막음(출시 준비)
- `GET /api/todos/{id}/evidence`: 파일. 사진(jpg·jpeg·png·gif·webp·heic·heif)·PDF는 `inline`, 다른 형식(SVG·HTML 포함)은 내려받기(`X-Content-Type-Options: nosniff`)
- `DELETE /api/todos/{id}/evidence`: 언제든(무산된 계약도) 지움. 완료했던 할 일은 `skipped`(완료 그대로, 기록함만 빈칸)
- 파일은 `EVIDENCE_DIR`(기본 `backend/data/evidence/<계약 id>/`, git 제외)에 저장, DB에는 상대 경로만. `reset_demo_db.py`가 계약별 폴더(숫자 이름)만 같이 지움. 다시 열린 뒤 조건이 바뀌어 지워지는 할 일의 파일도 지움. 암호화 저장은 출시 준비
- 나중에 올리기 한 할 일은 나중에 올리기로 바꾼 날(증빙을 지운 날) 7일 뒤 "증빙을 아직 안 올렸어요" 앱 안 알림 (`todos.yaml` `notifications.evidence_after_days`, FR-030)

### 반환 대응 (FR-024·034·035, #52)

- `POST /api/contracts/{id}/return-response`: 9번(반환 확인)에서 "못 받음". 오늘(가상 날짜)을 `not_returned_date`로 저장하고 반환 대응 단계 R1~R4를 기한 없는 할 일로 맨 위에 붙인다(`todos.yaml` `return_response`). 만기일 전이면 409 `RETURN_NOT_DUE`, 9번을 이미 끝냈으면 409 `ALREADY_RETURNED`, 다시 보내면 그대로
- 단계는 할 일이라 끝내기·나중에 올리기·증빙(반환 요청 캡처, 내용증명 사본, 임차권등기가 된 등기부, 청구 접수 기록)은 `PATCH`·`POST /api/todos/{id}` 그대로. 시작일에 앱 안 알림. 나중에 돌려받으면 9번을 끝낸다(`return-guide`가 `ended`). 그러면 남은 단계는 할 일에서 빠지고 끝낸 단계는 맨 뒤 기록으로 남는다(맨 위·고정 표시도 풂). 9번을 되돌리면 단계가 다시 맨 위로
- `DELETE /api/contracts/{id}/return-response`: 잘못 고른 "못 받음" 되돌리기. 끝낸 단계가 있으면 409 `RETURN_STEP_DONE`
- `GET /api/contracts/{id}/return-guide`: 단계 진행(`state` done / current / todo), 단계별 창구 링크, 청구 서류 대조(단계마다 적은 할 일의 증빙을 기록함에 올렸는지, 이 계약에 없는 할 일의 서류는 뺌), 빠진 서류 수, 공공 상담 창구. "못 받음" 전에도 `preview`로 볼 수 있다(경보 위험일 때 미리 점검, 서류는 지금 준비할 수 있는 할 일(T) 서류만)
- 4단계는 보증기관에 따라 HUG·HF·SGI 청구 창구, 미가입은 공공 상담(증빙 없음). 단계별 서류는 팀 제안(`hypothesis: true`), 출시 전 보증기관 청구 서류·법률 자문으로 확인
- 반환 대응 중에는 만기일을 "못 받음"을 고른 날보다 뒤로 바꿀 수 없다 (`PATCH /api/contracts/{id}` 422 `end_date`)

### 캘린더 구독 (FR-042, #47)

- 앱 ICS 내보내기(#102)는 내보낸 때의 일정이라 날짜가 바뀌면 다시 내보내야 한다. 구독 주소를 캘린더에 넣으면 캘린더 앱이 주기적으로 불러와 바뀐 기한이 저절로 반영된다
- `POST /api/contracts/{id}/calendar-link` → `url`·`webcal_url`. 캘린더 앱은 헤더를 못 보내 주소에 **보기 전용 토큰**을 넣는다(`calendar_tokens`, 해시만 저장). 이 토큰으로는 계약 API를 쓸 수 없고, 다시 만들면 앞 주소는 끊긴다. `DELETE`로 끊기
- `GET /api/calendar/{token}.ics`: 끝나지 않은 할 일만, 앱 내보내기와 같은 UID·하루 종일 일정·7·1일 전 오전 9시 알림. 집 주소·이름은 넣지 않음. 무산된 계약은 일정 없는 캘린더
- 캘린더 앱(구글·애플)이 서버에 닿아야 하므로 실제 구독은 배포 서버에서 된다. 배포 서버가 프록시 뒤라 주소가 달라지면 `PUBLIC_BASE_URL`

### 첫 계약 서류 (FR-051, #46)

- 계약 당일 계약서 사진(`contract`)·계약금 이체 내역(`down_payment`)을 기록함의 첫 서류로 저장한다 (`todos.yaml` `first_documents`). 할 일 증빙이 아니라 할 일은 바뀌지 않는다
- `POST /api/contracts/{id}/documents` (multipart `kind`, `file`): 종류마다 1장, 다시 올리면 바꿈. 크기·빈 파일·보기 형식은 증빙 사진과 같음(`app/evidence.py` `read_upload`·`file_response`)
- `GET`·`DELETE /api/contracts/{id}/documents/{kind}`: 보기·지우기 (무산된 계약도). 계약 응답 `documents`에 종류마다 올렸는지
- 파일은 증빙과 같은 계약 폴더(`EVIDENCE_DIR/<계약 id>/`)라 `reset_demo_db.py`가 같이 지움

### `POST /api/contracts/access-link` 접근 링크 이메일로 다시 받기 (#39)

```json
{"email": "tenant@example.com"}
```

- 그 이메일(계약 이메일 또는 공동 계약자 이메일)로 만든 진행 중 계약마다 새 접근 토큰을 만들어 그 주소로 보낸다. 부부가 각자 휴대폰에서 같은 계약을 볼 수 있다(FR-043). 무산된 계약도 풀린 결제가 남아 있으면 보낸다(앱을 다시 설치해도 그 결제를 다음 집 계약에 쓸 수 있게). 처음 토큰은 그대로 둬서, 남이 이 요청을 보내도 원래 휴대폰은 계속 쓸 수 있다 (새 토큰은 `contract_tokens`에 해시로)
- 이메일이 없어도 같은 202 `{"message": ...}`. 계약마다 한 시간에 3번까지, 메일을 보내지 못하면 토큰을 남기지 않는다
- 메일 본문: `APP_LINK_BASE`가 있으면 `{APP_LINK_BASE}?contract={id}&token=...` 링크, 없으면 계약 번호와 접근 코드. 앱은 이 둘을 받아 저장하고 `X-Contract-Token`으로 쓴다

### 계약 접근 토큰과 계약 무산 (#39, FR-016)

- `GET`·`PATCH /api/contracts/{id}`, `POST /api/contracts/{id}/cancel`은 헤더 `X-Contract-Token`이 계약을 만들 때 받은 `access_token`과 맞아야 한다. 틀리면 계약이 없을 때와 같은 404 `NOT_FOUND` (번호를 바꿔 가며 계약이 있는지 알아내지 못하게). `REQUIRE_CONTRACT_AUTH`가 false면 헤더를 보내지 않은 요청은 통과시킨다
- `POST /api/contracts/{id}/cancel` (본문 없음): 계약 `status: "cancelled"`, 쓴 결제는 `released`. 할 일은 지우지 않고 기록으로 남긴다. 무산된 계약은 `GET`만 되고 `PATCH`·다시 무산은 409 `CONTRACT_CANCELLED`
- `contracts`에 `access_token_hash`·`payment_id`·`status`·`cancelled_at` 칸, `payments` 테이블을 넣었다. 예전 DB는 서버를 켤 때 새 칸을 자동으로 더한다(`init_db`). 예전 계약은 토큰이 없어 `REQUIRE_CONTRACT_AUTH=true`면 열 수 없으니 시연 전에는 `python reset_demo_db.py`

### `POST /api/contracts/{id}/move` 갈아타기 (FR-025~027)

- 만기 6개월 전 할 일(7번)에서 "이사할게요"를 고르면 다음 집 계약일·잔금일·만기일·보증금·계약금(과 대출·보증기관·전입 예정일)을 보낸다. `X-Contract-Token` 확인, 무산된 계약은 409
- 다음 집 입력만 `moves` 표에 저장하고(계약마다 1개, 다시 보내면 바꿈), 계산은 `GET`할 때마다 지금 계약 상태로 다시 한다 (지금 계약의 날짜를 바꾸거나 반환 확인을 끝내도 맞게)
- 다음 집 계약일·잔금일이 지금 계약일보다 앞서면 422, 대출 실행일은 다음 집 계약일과 잔금일 사이(아니면 422). 두 번 눌러 동시에 저장해도 먼저 저장한 행을 고친다. 저장한 입력이 나중에 바뀐 입력 규칙과 맞지 않으면 `GET`이 409 `MOVE_INPUT_OUTDATED`
- 반환 예정일 = 지금 계약 9번 할 일 기한(없으면 만기일). 9번을 끝냈으면(나중에 올리기 포함) 끝낸 날이 반환일이고, 이미 돌려받았으니 자금 틈은 0, 대출 순서·전입 순서 경고는 내지 않는다. 자금 틈 `gap_days` = 반환 예정일 − 다음 집 잔금일(늦지 않으면 0), `gap_amount` = min(지금 집 보증금, 다음 집 잔금 = 보증금 − 계약금) (PO 결정 Q5)
- 대출 순서 `loan_order`: 두 집 모두 전세대출일 때 새 대출 실행일(모르면 잔금일)이 반환 예정일보다 앞서면 `new_loan_first`, 아니면 `old_repayment_first`. 은행 확인 안내를 같이
- 전입 순서 `move_in_warning`: 다음 집 전입 예정일(없으면 잔금일)이 반환 예정일과 같거나 앞서면 true, 9번 할 일을 끝냈으면 false (FR-027). 앞서면 날짜를 다시 보라는 경고, 같은 날이면 "보증금 먼저 받고 전입신고" 순서 안내 (PO 결정 Q12)
- `next_todos`: 다음 집 날짜로 계산한 할 일 9종 (연동 규칙·특약은 다음 집 계약 전 확인 뒤 계약을 만들 때). `todos`: 지금 집 + 다음 집 할 일을 날짜순으로 묶은 목록 (FR-025)
- 정답표 S10·S10-b와의 대조는 `tests/test_move.py`
- 다음 집 계약 연결 `POST /api/contracts/{id}/move/next` (`{"next_contract_id", "next_contract_token"}`): 다음 집 계약 전 확인(FR-028)으로 계약을 만든 뒤 연결한다. 그 뒤 다음 집의 전입신고(4번)를 지금 집 반환 확인(9번)이나 임차권등기(반환 대응 R3) 전에 끝내려 하면 `PATCH`·증빙 올리기가 409 `MOVE_IN_BEFORE_RETURN`(FR-027, UC-008 *a). 앱은 경고 창을 띄우고, 그래도 끝내면 `confirm_move_in: true`로 다시 보낸다. 지금 계약이 무산됐으면 경고하지 않는다. `tests/test_move_in_warning.py`

### `POST /api/contracts/{id}/registry-compare` 등기부 재비교 (FR-023·048, #41)

```json
{"registry": {"mortgage": true, "mortgage_amount": 150000000, "seizure": false}, "stage": "balance_day"}
```

- 계약 당일(점검한 날과 계약일이 다를 때, FR-048)·잔금일 아침(3번 할 일, FR-023)에 등기부 요약을 다시 올려(`POST /api/registry/parse` → 확인) 계약 전 확인 판정과 비교한다. `stage`를 비우면 오늘(가상 날짜)이 계약일까지면 계약 당일, 계약 다음 날부터는 잔금일
- 항목별 `same` / `risk`(새로 생기거나 늘어남) / `eased`(없어지거나 줄어듦). `risk`가 있으면 `hold`와 "계약 보류 후 상담" / "잔금 보류 후 상담". 근저당 말소·감액은 변동으로만 보여 주고 보류는 안내하지 않는다 (잔금 때 말소하기로 한 근저당)
- 계약 전에 근저당이 있었으면 `mortgage_check`(채권최고액 비교)를 필수 확인으로 (L-MORTGAGE)
- 계약 전 확인과 같은 입력(보증금·공시가격도 그때 값)에 등기부만 바꿔 다시 판정해 계약의 판정 기록(`verdicts.stage`·`comparison`)으로 남긴다. 그래서 `level_after`·`deposit_ratio_after`가 달라지면 등기부 때문. `GET`은 재비교 기록
- 다시 판정해 새로 걸린 연동 규칙은 할 일에 더한다 (근저당 → 3번 근저당 금액 비교, 비율 90% 이상 → 2번 기한 계약일, 신탁 → 신탁사 동의서. PO 2026-10-28). 더하기만 하고, 근저당이 말소된 등기부를 올려도 빼지 않는다 (`contracts.todo_linkages`)
- 경보는 재비교한 날 기준으로 이 계약만 바로 다시 계산한다 (계약의 지금 보증금·공시가격 + 이 등기부의 선순위 채권, `alert_level`·경보 이력·올라가면 앱 알림). 경보 재계산의 선순위 채권은 그날까지 비교한 날이 가장 늦은 등기부 (가상 날짜를 되돌려 다시 비교해도 날짜로 고름, `alerts.senior_debt`)
- 3번 할 일 완료는 지금처럼 증빙(잔금일 등기부 열람본)으로 한다 (재비교가 할 일 상태를 바꾸지 않음)

### `POST /api/admin/trades` 실거래가 수집 (FR-046)

공공데이터포털 인증키가 있어야 한다 (`.env.example`). 시연 집이 있는 구를 한 번 받아 두면 판정·검증은 저장본으로 한다.

한 번에 공공데이터포털을 수십 번 부르므로 서버 환경 변수 `ADMIN_TOKEN`과 같은 값을 `X-Admin-Token` 헤더로 보내야 한다. `ADMIN_TOKEN`이 없으면 관리자 API는 꺼진다(403 `ADMIN_DISABLED`), 헤더가 없거나 다르면 401 `ADMIN_TOKEN_INVALID`. 같은 구를 동시에 두 번 수집해 겹치면 409 `TRADES_COLLECT_CONFLICT`(다시 부르면 이미 저장된 거래는 건너뜀).

```json
{"lawd_cd": "26500", "end_month": "2026-10", "months": 12, "housing_types": ["apartment", "row_house"]}
```

응답: 받은 달(`months`), 유형·종류별 받은 건수(`received`), 새로 저장한 건수(`added`), 받은 시각(`fetched_at`). 같은 거래는 다시 받아도 한 번만 저장하고, 나중에 해제 신고되면 해제 표시만 고친다.

공개 자료에는 동·호수가 없어서 같은 날 같은 층·면적·금액으로 거래한 다른 집이 똑같은 줄로 온다. 이런 줄은 합치지 않고 순번을 붙여 따로 저장한다 (수영구 12개월 8,999건을 받아 8,999건 저장, 다시 받으면 0건 추가로 확인).

`POST /api/checks`에 `complex`를 함께 보내면 저장된 거래에서 찾는다.

```json
"complex": {"lawd_cd": "26500", "umd_name": "광안동", "complex_name": "○○빌라", "jibun": "45-6"}
```

- 매매 실거래가: 같은 단지·전용면적 ±10%·기준일 이전 12개월 안의 가장 최근 매매(해제 신고 제외). `trade_price`를 직접 보내면 그 값을 쓴다
- 주변 전세 시세: 같은 조건의 전세(월세 0원) 보증금 중앙값. 갱신 계약은 빼고 신규·구분 없음만 쓴다. 3건 미만이면 표본 부족
- 기준일은 오늘, `X-Virtual-Today` 헤더가 있으면 그날. 응답 `as_of`에 남는다
- 연립다세대는 같은 이름이 많아 지번(`jibun`)이 필요하다
- `complex`는 아파트·연립다세대만 받는다. 오피스텔·다가구·단독이면 422 (수집하는 실거래 자료가 없음)

### `GET /api/demo-houses` 시연 집 2채 (FR-001·046)

`docs/validation/demo_houses.yaml`(경보 계산 정답표)의 시연 집 2채를 돌려준다. 화면은 받은 값을 그대로 다음 API에 넣는다.

- `input` → `POST /api/checks` (단지·공시가격·전용면적·등기부 확인값 포함)
- `registry`: 시연 등기부를 읽은 결과 (`POST /api/registry/parse`와 같은 형식). 등기부를 올린 것처럼 확인 화면을 채운다
- `virtual`: 시연용 가상 값 (빌라의 근저당 1,440만). 화면에 "시연용 가상 근저당"으로 표시
- `contract_day` → `POST /api/contracts` (계약일·잔금일·만기일, 특약 넣음/거절당함). 빌라만 있음

정답표와 같은 결과(실거래 매매가·주변 전세 시세까지)를 보려면 실거래 저장본을 넣고 판정할 때 `X-Virtual-Today: 2026-10-13`(응답 `as_of`)을 보낸다. 실거래가 없어도 판정·비율·경보 단계는 같다 (두 집 모두 공시가격 × 140%가 매매가보다 낮음).

```bash
python load_demo_trades.py   # DATABASE_URL을 서버와 같게. 여러 번 실행해도 같은 거래는 한 번만
```

시연 리허설·시연 직전에는 `python reset_demo_db.py`로 판정·계약·할 일을 모두 지우고 실거래 저장본만 넣은 상태로 되돌린다 (확인을 묻고, `--yes`면 바로. SQLite는 서버를 끄고 실행).

`tests/test_demo_houses.py`가 이 API의 입력으로 판정·계약을 만들어 정답표 기대값(비율·판정·연동 규칙·실거래·경보 단계·빌라의 할 일 순서)과 자동 대조한다.

### `GET /api/checks/{id}/special-terms` 특약 예시 (FR-039)

계약 당일 체크(UI-03)의 특약 화면용. 판정에 걸린 연동 규칙으로 특약 예시를 고른다.

```json
{
  "check_id": 1,
  "level": "check_needed",
  "terms": [{
    "id": "S-NO-MORTGAGE",
    "label": "잔금일 다음 날까지 담보 설정 금지",
    "text": "임대인은 잔금 지급일 다음 날까지 …",
    "source": "주택임대차표준계약서 특약 예시, …",
    "linked": [{"id": "L-MORTGAGE", "label": "근저당 있음"}],
    "if_inserted": {"warnings": [], "documents": ["특약이 보이는 계약서 사진"], "moves_to_top": [], "adds_todos": [], "link_counsel": false},
    "if_rejected": {"warnings": ["잔금 당일 설정되는 담보는 …"], "documents": [], "moves_to_top": [{"id": "T4", "title": "전입신고"}], "adds_todos": [], "link_counsel": false}
  }],
  "warnings": ["선순위 채권(근저당 채권최고액)을 반영한 내 보증금 비율을 다시 계산했습니다"],
  "checks": [],
  "disclaimer": "정보 제공이며 보증하지 않습니다.",
  "rules_version": "1.1"
}
```

- 사용자가 고른 넣음/거절당함은 `terms[].id`를 키로 `POST /api/contracts`의 `special_term_result`에 보낸다 (`inserted` / `rejected`)
- MVP는 근저당·비율 90% 이상·신탁 연동 규칙에 연결된 특약 2개(담보 설정 금지, 보증·대출 거절 시 해제)만 나온다. 신탁은 특약 대신 `checks`에 "신탁사 동의서 확인"
- 걸린 항목이 없으면(문제 항목 없음, 대상 아님) `terms`가 빈 목록
- "문제 항목"(결제 전 멈춤) 판정이면 409 `CHECK_BLOCKED`, 판정 단계가 지금 규칙에 없으면 409 `CHECK_OUTDATED`
- 판정의 `linkages`는 만들 때 저장한 값이고, 특약 예시·경고는 지금 규칙 파일로 만든다. `rules_version`은 `special_terms.yaml` 버전이다 (`warnings`·`checks`는 `linkage.yaml`에서 오지만 지금은 두 파일 버전이 같이 움직인다)

### `POST /api/registry/explain` 등기 항목 쉬운 말 설명 (FR-007, 명세서 8장)

```json
{"items": [{"id": "을1", "kind": "mortgage", "purpose": "근저당권설정", "amount": 120000000},
           {"id": "갑4", "kind": "trust", "purpose": "신탁"}]}
```

- 응답: 보낸 순서대로 `{"id", "kind", "text", "source"}`. `source`는 `llm`(LLM이 쓰고 검사 통과) / `template`(`rules/explain.yaml`)
- 흐름: 사용자가 확인한 항목(종류·등기 목적·금액)만 LLM에 보낸다. 항목마다 템플릿 설명을 사실 근거로 함께 보내고, 돌아온 설명은 금지 표현(`verdict.yaml` 안전 단정 + `explain.yaml` 법률 판단·상품 추천)과 숫자(템플릿에 없는 금액이면 탈락)·길이를 검사한다. 걸린 항목만 템플릿으로 바꾼다
- LLM은 `ANTHROPIC_API_KEY`가 있을 때만 켜진다(`LLM_EXPLAIN=false`로 끔, 모델은 `LLM_MODEL`, 기본 `explain.yaml` `llm.model`). 8초 넘거나 실패하면 템플릿, 재시도 없음. 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도(`fallbacks: "default"`)하고, 그래도 거절이면 템플릿
- 같은 항목 묶음의 LLM 설명은 서버 메모리에 저장해 다시 부르지 않는다(시연에서 같은 등기부를 여러 번 올려도 대기·비용 없이). 서버를 다시 띄우면 지워짐
- 판정·비율은 이 API와 관계없다 (AI-REQ-02). LLM이 안 돼도 판정·할 일은 그대로 (AC-013)
- 테스트는 실제 LLM을 부르지 않는다 (`call_llm`을 바꿔 끼움)

### `POST /api/registry/parse` 등기부 요약 추출 (FR-005·006)

`multipart/form-data`로 `file`에 등기부 PDF(10MB까지)를 올린다. 결과는 저장하지 않는다.

```json
{
  "fields": {"seizure": false, "mortgage": true, "mortgage_amount": 156000000, "trust": false},
  "owners": ["홍길동"],
  "mortgages": [{"rank": "1", "purpose": "근저당권설정", "amount": 120000000, "holder": "주식회사가상은행", "text": "..."}],
  "seizures": [], "trusts": [], "others": [],
  "warnings": []
}
```

- 확인 화면은 `fields`를 고칠 수 있게 보여 주고, 확인한 값을 `POST /api/checks`의 `registry`로 보낸다
- `others`·`warnings`: 변경 등기(예: 1-1), 전세권 등 자동으로 판단하지 않은 등기. 합계에 넣지 않았으니 사용자가 확인한다
- 읽는 양식: 인터넷등기소에서 열람한 뒤 **"부동산정보요약"을 PDF로 저장한 파일**(사용자 안내 기본값), 또는 등기사항증명서 끝에 "주요 등기사항 요약"이 붙은 파일. 둘 중 하나만 올리면 된다. 요약 없이 본문(갑구·을구)만 있는 전부증명서는 읽지 않는다
- 부동산정보요약의 "권리변동 예정사항"에 처리 중인 등기 신청이 있으면 `warnings`에 알린다 (새 근저당·압류일 수 있음)
- 요약 페이지를 못 읽으면 422, `detail.hint`에 부동산정보요약으로 다시 올리기·수동 입력 안내
- 실제 샘플 5건(부동산정보요약, 집을 찾을 수 없게 바꿈)과 가상 샘플 3건으로 테스트한다 (`tests/fixtures/registry/README.md`)
