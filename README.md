# jeonse_companion

2인 학과 프로젝트 **전동기(전세동행기록)** 저장소입니다. 전세 계약 전 점검부터 계약 후 2년 관리, 다음 집까지 이어서 관리하는 세입자용 서비스입니다.

## 문서

| 문서 | 최신 버전 | 위치 |
| --- | --- | --- |
| 서비스 기획안 | v4.32 | [`docs/plan/`](docs/plan/) |
| 요구사항 명세서(SRS) | v0.2 (기획안 v4.32 기준) | [`docs/srs/`](docs/srs/) |
| Use Case Diagram | SRS v0.2 5.1절 | [`docs/srs/usecase_전동기.puml`](docs/srs/usecase_전동기.puml) |

각 문서는 원본(.docx)과 읽기용 마크다운 변환본(.md)을 함께 둡니다. 기획안과 명세서가 다르면 기획안을 먼저 고치고 명세서에 반영합니다.

## 브랜치 규칙

- `main`: 최상위 브랜치. 직접 커밋하지 않고 PR로만 병합
- `feature/<작업명>`: 기능 개발 (예: `feature/todo-engine`)
- `docs/<작업명>`: 문서 작성·수정 (예: `docs/srs-v0.2`)
- `fix/<작업명>`: 버그 수정
