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
    check.tsx             UI-01 계약 전 확인 결과 (동작)
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
  constants/theme.ts      색·모서리·터치 영역 토큰 (docs/design/README.md 디자인 규칙)
  data/demo.ts            시연 데이터. 필드 이름은 백엔드 CheckResult, 특약 문구는 rules/special_terms.yaml과 같다
```

## 화면 흐름

- 홈 → 지금 할 일(할 일 탭), 진행 단계 카드(UI-06 타임라인), 보증금 비율 카드(경보 탭), 기록함 카드, "계약 전 확인 결과 다시 보기"(UI-01)
- UI-01 → 걸린 항목 누르면 UI-02, 하단 버튼으로 UI-03 → "다음 · 계약 날짜 입력"으로 할 일 탭
- 할 일 마지막 "보증금 반환 확인 → 갈아타기" → UI-07
- 기록함 비상 모드 안내 → UI-08

## 디자인 규칙 (요약)

- 판정은 색만으로 구분하지 않고 아이콘·글자를 같이 쓴다 (문제 항목 / 확인 필요 / 문제 항목 없음). "안전합니다"는 쓰지 않는다.
- 확인 못 한 항목은 판정과 상관없이 점선 박스(`DashedBox`)로 항상 보인다.
- 결과 화면 맨 아래에 조회 시점과 "정보 제공이며 보증하지 않습니다"(`Disclaimer`)를 둔다.
- 버튼·링크 높이 44 이상, 주 버튼 52.

## 다음에 할 일

- 백엔드 API 연결 (`docs/api/API_명세.md`): 판정 결과 → UI-01/02, 할 일 → UI-04
- 가상 날짜 전환(`X-Virtual-Today`)으로 시연 날짜 바꾸기
- 할 일 완료 시 카메라로 증빙 1장 찍기(expo-image-picker), 기록함에 저장
- 캘린더에 추가(ICS), 개인정보 동의·면책 문구 화면
