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
- 환경 변수는 `.env.example`을 참고한다. 실거래가 조회(2주차)에는 공공데이터포털 인증키가 필요하다 (`export DATA_GO_KR_SERVICE_KEY=...`, 포털의 일반 인증키 중 **Decoding 키**).
- 테이블은 서버가 시작할 때 `create_all`로 만들기 때문에 **이미 있는 테이블에는 새 칸이 생기지 않는다**. 모델(`app/models.py`)이 바뀐 브랜치를 받으면 로컬 DB를 다시 만든다: `docker compose down -v && docker compose up -d` (SQLite는 파일을 지운다). 배포 전까지는 이렇게 하고, 배포 서버에 데이터가 쌓이기 시작하면 Alembic을 들인다

## 테스트

```bash
pytest                      # 임시 SQLite 파일로 실행 (DB 설치 불필요)
TEST_DATABASE_URL=postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse_test pytest
```

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
| `app/engine/alert.py` | 경보 단계 (alert.yaml) |
| `app/engine/market.py` | 같은 단지·비슷한 면적의 최근 매매가, 주변 전세 시세 중앙값 (alert.yaml) |
| `app/trades/client.py` | 공공데이터포털 실거래가 API 4종 호출·응답 해석 |
| `app/trades/collect.py` | 실거래 수집·저장 (같은 거래는 한 번만) |
| `app/api/admin.py` | `POST /api/admin/trades` |
| `app/engine/special_terms.py` | 판정에 맞는 특약 예시와 넣음/거절당함 결과 (special_terms.yaml, linkage.yaml) |
| `app/api/checks.py` | `POST /api/checks`, `GET /api/checks/{id}`, `GET /api/checks/{id}/special-terms` |
| `app/api/contracts.py` | `POST /api/contracts`, `GET /api/contracts/{id}` |
| `app/registry/pdf.py` | 등기부 PDF → 요약 페이지 글자 ("부동산정보요약" 또는 증명서의 "주요 등기사항 요약", pdfplumber) |
| `app/registry/parser.py` | 요약 글자 → 소유자, 근저당 채권최고액, 압류 등, 신탁 (규칙 파서) |
| `app/api/registry.py` | `POST /api/registry/parse` |
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
  "special_term_result": {"S-NO-MORTGAGE": "rejected"}
}
```

- 주택 유형·보증금·공시가격·전용면적은 `check_id` 판정의 입력을 그대로 쓴다. 보증금이 바뀌었으면 계약 전 확인을 다시 한다
- 선택 입력과 기본값: `monthly_rent` 0, `loan` false, `guarantor` `none`(HUG / HF / SGI / none), `brokered` true(직거래면 false), `renewal_right_used` false, `co_tenant` false, `email`, `special_term_result`(키는 `special_terms.yaml`의 id, 값은 `inserted` / `rejected`)
- 날짜: 잔금일 ≥ 계약일, 만기일 > 잔금일. 대출이 없으면 `loan_execution_date`를 비워 둔다
- "문제 항목" 판정이면 409 `CHECK_BLOCKED`, 한 판정으로 계약을 두 번 만들면 409 `CHECK_ALREADY_USED`
- 응답: 입력한 계약 조건 + `id`, `check_id`, `level`(시작할 때의 판정 단계), 판정에서 가져온 주택 정보, `report_required`(임대차 신고 대상), `alert_level`(판정 때 비율로 정한 경보 단계, 정상이면 null), `todos`(할 일 목록)
- `todos`는 `sort_order` 순서다: 맨 위 규칙(특약 거절·경보, `moved_to_top`) → 고정(T5~T9, `pinned`) → 기한 빠른 순. 재알림(T6·T8)은 `due_date` 대신 `remind_date`, HF·SGI 반환보증(T5)은 기관 기준이 없어 `due_date`가 null. 대출은 있는데 `loan_execution_date`를 비우면 T5 시작일은 전입신고(T4) 다음 날
- 기한 계산은 `docs/validation/기한계산_정답표.md`의 계산 약속을 따르고, `tests/test_todos.py`가 정답표(`deadline_scenarios.yaml`) S1~S10·재계산 3개와 대조한다
- `contracts` 테이블에 `check_id`(unique)·`email`·`report_required`·`alert_level`, `todos`에 새 칸들을, `verdicts`에 `market` 칸과 `trades` 테이블을 넣었다. 금액 칸은 BigInteger로 바꿨다. 예전에 만든 DB는 위 안내대로 다시 만든다

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
