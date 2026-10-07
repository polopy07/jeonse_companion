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
- 배포 서버에서는 `DATABASE_URL`만 그 서버의 PostgreSQL 주소로 바꾸면 된다.

## 테스트

```bash
pytest                      # 임시 SQLite 파일로 실행 (DB 설치 불필요)
TEST_DATABASE_URL=postgresql+psycopg://jeonse:jeonse@localhost:5432/jeonse_test pytest
```

## 구조

| 경로 | 내용 |
| --- | --- |
| `app/main.py` | 앱, `/health` |
| `app/config.py` | 환경 변수 (`DATABASE_URL`, `RULES_DIR`) |
| `app/db.py` | DB 연결, 세션 |
| `app/models.py` | 데이터 모델: 계약(`contracts`), 판정(`verdicts`), 할 일(`todos`), 경보(`alerts`) |
| `app/schemas.py` | API 입출력 형식 |
| `app/errors.py` | 오류 응답 형식 (`{"detail": {code, message, hint, fields}}`) |
| `export_openapi.py` | `docs/api/openapi.json` 다시 만들기 |
| `app/rules/loader.py` | 규칙 파일 불러오기 |
| `app/rules/conditions.py` | 규칙의 조건(`when`) 계산 |
| `app/engine/price.py` | 추정 주택가격, 내 보증금 비율 (alert.yaml) |
| `app/engine/verdict.py` | 판정 4단계 (verdict.yaml) |
| `app/engine/check.py` | 계약 전 확인: 입력 → 비율 → 판정 |
| `app/api/checks.py` | `POST /api/checks`, `GET /api/checks/{id}` |
| `app/registry/pdf.py` | 등기부 PDF → "주요 등기사항 요약" 페이지 글자 (pdfplumber) |
| `app/registry/parser.py` | 요약 글자 → 소유자, 근저당 채권최고액, 압류 등, 신탁 (규칙 파서) |
| `app/api/registry.py` | `POST /api/registry/parse` |
| `tests/fixtures/registry/` | 등기부 요약 가상 샘플 (실제 샘플이 오면 추가) |

## API

공통 규칙(주소, 상태 코드, 금액·날짜 표기, 오류 형식)과 전체 API 목록은 [`docs/api/API_명세.md`](../docs/api/API_명세.md). API를 바꾸면 `python export_openapi.py`로 `docs/api/openapi.json`을 다시 만든다 (`tests/test_openapi.py`가 검사).

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

응답: 판정 단계(`level`, `label`, `next_step`, `block_payment`), 추정 주택가격, 내 보증금 비율, 걸린 규칙(`matched`), 연동 규칙(`linkages`), 확인 못 한 항목(`unchecked`), 안내 문구(`disclaimer`), 규칙 버전.

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
- 요약 페이지를 못 읽으면 422, `detail.hint`에 수동 입력 안내
- 양식은 가상 샘플로 맞춘 것이다. 실제 샘플(개발용 3건)을 받으면 `parser.py`의 정규식을 맞춘다
