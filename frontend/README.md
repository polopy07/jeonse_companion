# 전동기 프론트엔드 (Expo)

Expo(React Native) + Expo Router 앱이다. 한 코드로 웹(PWA)·안드로이드·iOS를 함께 낸다. 화면 구성·문구·색은 [`docs/design/`](../docs/design/) 목업(UI-01~09 + 홈)을 기준으로 한다.

## 실행

```bash
cd frontend
npm install
npx expo start          # 터미널에서 w = 웹, a = 안드로이드, QR = Expo Go
npx expo start --web    # 웹만
```

- 검사: `npx tsc --noEmit` (타입), `npx expo lint` (린트). PR 올리기 전에 둘 다 통과시킨다.
- 패키지 추가는 `npm install` 대신 `npx expo install <패키지>` (SDK에 맞는 버전으로 설치됨).
- 지금은 백엔드에 연결하지 않고 `src/data/demo.ts`의 시연 데이터(부산 근저당 빌라, 담보 설정 금지 특약 "거절당함")로 그린다.

## 구조

```
src/
  app/                    화면 (파일 = 주소)
    _layout.tsx           글꼴 로드, 전체 스택, 웹에서 모바일 폭(최대 480px)으로 가운데 정렬
    (tabs)/               하단 탭 4개
      index.tsx           홈
      todos.tsx           UI-04 할 일 목록 (동작)
      records.tsx         UI-05 전세 기록함 (동작, 평소/비상)
      alert.tsx           UI-09 경보 리포트 (정적)
    precheck.tsx          UI-01 계약 전 확인 입력 (동작: 집 정보 → 공시가격 → 등기부 → 확인·수정)
    check.tsx             UI-01 계약 전 확인 결과 (동작, 입력 결과 또는 시연 집 결과)
    detail.tsx            UI-02 판정 상세 (정적)
    contract-day.tsx      UI-03 계약 당일 체크 (동작, 넣음/거절당함)
    timeline.tsx          UI-06 계약 타임라인 (정적)
    switch.tsx            UI-07 갈아타기 입력 (동작, 자금 틈 계산)
    return.tsx            UI-08 반환 대응 안내 (정적)
  components/
    AppText.tsx           IBM Plex Sans KR 굵기별 글자
    Icon.tsx              목업과 같은 선 아이콘 (선 굵기 1.8, react-native-svg)
    layout.tsx            Screen(뒤로·하단 막대), Card, DashedBox, SectionLabel, Button, Disclaimer
    verdict.tsx           VerdictBadge/Card, RatioGauge, MatchedItem, UncheckedBox, SpecialTermRow
    form.tsx              TextField(단위·안내), ChoiceChips, Toggle, ToggleRow
  constants/theme.ts      색·모서리·터치 영역 토큰 (docs/design/README.md 디자인 규칙)
  lib/check.ts            계약 전 확인 임시 계산 (백엔드 engine·rules v1.0을 옮긴 것, 2주차에 POST /api/checks로 교체)
  lib/format.ts           금액 표기 (1억 4,000만), 만 원 입력 변환
  data/demo.ts            시연 데이터 (시연 집 2채 포함). 필드 이름은 백엔드 CheckResult, 특약 문구는 rules/special_terms.yaml과 같다
```

## 화면 흐름

- 홈 → 지금 할 일(할 일 탭), 진행 단계 카드(UI-06 타임라인), 보증금 비율 카드(경보 탭), 기록함 카드, "새 집 계약 전 확인"(입력), "지난 확인 결과"(UI-01)
- 계약 전 확인 입력: "시연 집으로 채우기"(수영구 빌라·해운대구 아파트)로 한 번에 채울 수 있다. 등기부 단계에서 PDF 고르기 / 시연 등기부 불러오기 / 직접 입력 / 등기부 없이 결과 보기(최소 추정치) 중 하나
- 판정에 따라 UI-01 하단 버튼이 바뀐다: 확인 필요·문제 없음 → 패키지 9,900원, 문제 항목 → 결제 막고 상담 창구, 대상 아님(다가구·단독) → 할 일 관리 4,900원
- UI-01 → 걸린 항목 누르면 UI-02, 하단 버튼으로 UI-03 → "다음 · 계약 날짜 입력"으로 할 일 탭
- 할 일 마지막 "보증금 반환 확인 → 갈아타기" → UI-07
- 기록함 비상 모드 안내 → UI-08

## 디자인 규칙 (요약)

- 판정은 색만으로 구분하지 않고 아이콘·글자를 같이 쓴다 (문제 항목 / 확인 필요 / 문제 항목 없음). "안전합니다"는 쓰지 않는다.
- 확인 못 한 항목은 판정과 상관없이 점선 박스(`DashedBox`)로 항상 보인다.
- 결과 화면 맨 아래에 조회 시점과 "정보 제공이며 보증하지 않습니다"(`Disclaimer`)를 둔다.
- 버튼·링크 높이 44 이상, 주 버튼 52.

## 다음에 할 일

- 백엔드 API 연결 (`docs/api/API_명세.md`): 등기부 PDF → `POST /api/registry/parse`, 입력값 → `POST /api/checks`(그 뒤 `lib/check.ts` 임시 계산 삭제), 할 일 → UI-04
- 걸린 항목 설명·확인 못 한 항목 안내 문장을 서버가 내려줄지 정하기 (지금은 `lib/check.ts`에 화면 문구로 있음)
- UI-03 나머지 단계: 테스트 결제, 현장 확인 체크, 계약서·이체 내역 업로드, 계약 날짜 입력(FR-014)
- 가상 날짜 전환(`X-Virtual-Today`)으로 시연 날짜 바꾸기
- 할 일 완료 시 카메라로 증빙 1장 찍기(expo-image-picker), 기록함에 저장
- 캘린더에 추가(ICS), 개인정보 동의·면책 문구 화면
