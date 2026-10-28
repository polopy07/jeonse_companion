# 브랜치·PR 규칙

전동기 저장소에서 브랜치를 만들고 PR을 올려 병합하는 규칙입니다.

## 브랜치

- `main`: 최상위 브랜치. 직접 커밋하지 않고 PR로만 병합
- `feature/<작업명>`: 기능 개발 (예: `feature/todo-engine`)
- `docs/<작업명>`: 문서 작성·수정 (예: `docs/srs-v0.2`, 작업일지는 `docs/worklog-1028-hwang`)
- `fix/<작업명>`: 버그 수정
- 위 세 가지 외의 접두사(예: `claude/`)는 쓰지 않음

## PR

- 제목: `<종류>: <한국어 한 줄 요약>` (종류: `feat` / `fix` / `docs` / `refactor` / `test` / `chore`). 예: `feat: 등기부 요약 파서 뼈대 추가`
- 본문: Summary / 변경 파일 / Test plan 세 절. PR을 열면 [템플릿](.github/pull_request_template.md)이 자동으로 채워짐
- 이슈를 해결하는 PR은 본문에 `Closes #번호`를 적어 병합 때 이슈가 닫히게 함
- CI: PR마다 백엔드 테스트와 규칙 파일 검사가 자동으로 돌아감 ([`test.yml`](.github/workflows/test.yml))
- **base는 항상 `main`**. 다른 PR의 브랜치를 base로 두지 않음 (아래 PR이 먼저 병합되면 위 PR이 중간 브랜치로 병합돼 main에 들어가지 않음, #99·#100·#102)

## 리뷰

- 리뷰 본문은 "꼭 볼 것 / 정리하면 좋은 것 / 확인한 것"으로 나눔
- 고칠 것이 있으면 **Approve 대신 Request changes**. 자동 병합이 걸린 PR은 승인하는 순간 병합됨
- 승인한 뒤 PR에 새 커밋이 푸시되면 승인이 풀림(main 보호 규칙). 다시 보고 재승인

## 병합

- **PR을 올린 사람이** 팀원 승인(Approve 1개)과 CI(`test`) 통과를 확인한 뒤 병합. 방식은 merge commit
- **자동 병합**: 저장소에 Allow auto-merge가 켜져 있음(2026-10-28). PR을 올린 사람이 자기 PR에 걸어 두면 승인과 CI 통과 순간 GitHub가 병합함. 승인된 뒤 병합을 기다리는 사이 main이 바뀌어 충돌 정리 → 재승인이 반복되는 것을 막으려고 씀
  - PR 화면 아래쪽 **Enable auto-merge** → Create a merge commit, 또는 `gh pr merge <번호> --auto --merge`
  - 끄려면 PR 화면의 **Disable auto-merge**
  - 다른 사람의 PR에는 걸지 않음
- 병합한 브랜치는 병합한 사람이 지움 (저장소의 병합 뒤 브랜치 자동 삭제는 꺼져 있음)

## 이어지는 작업

- 내 PR이 아직 열려 있으면 그 위에 새 작업을 쌓지 않고, **병합된 뒤 새 `main`에서 분기**함. 앞 PR이 고쳐질 때마다 다시 합쳐야 하고, 리뷰 diff에 앞 PR 내용이 섞이기 때문
- 이미 앞 PR 브랜치 위에 만든 작업이 있으면 base는 `main`으로 두고 PR 설명 맨 위에 "#번호 위에 만듦"이라고 적음. 앞 PR이 병합되면 diff가 이 PR 내용만으로 줄어듦. 위 PR이 먼저 병합되면 아래 PR도 함께 병합된 것으로 처리됨
- 승인된 여러 PR이 공통 문서(README, API 명세, `openapi.json` 등)에서만 서로 충돌하면, PR마다 정리하지 않고 통합 PR 하나로 합쳐 한 번만 재승인받음 (#113)

## main 보호 규칙 (저장소 Rulesets)

- PR 없이 직접 푸시 금지
- 승인 1개 필수, 새 커밋을 푸시하면 승인이 풀림
- `test` 통과 필수
- 강제 푸시·삭제 금지

## 작업일지

- `worklog/YYYY-MM-DD-이름.md`에 한 명당 하루 1개 ("오늘 한 일 / 결정한 것과 이유 / 막힌 것·상대에게 부탁할 것 / 다음에 할 일"). `docs/` 브랜치로 PR
- 노션 작업일지에도 같은 내용을 남김
