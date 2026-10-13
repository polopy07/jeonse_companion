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
- 시연은 앱(Expo Go 등)으로 한다. 서버 주소(`EXPO_PUBLIC_API_URL`)를 넣으면 계약 전 확인이 백엔드를 부르고, 비워 두면 `src/data/demo.ts` 시연 데이터와 앱 안 임시 계산으로 동작한다.

### 백엔드 연결 (휴대폰에서)

1. PC에서 백엔드를 외부 접속 가능하게 띄운다: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. `frontend/.env.example`을 `frontend/.env.local`로 복사하고 `EXPO_PUBLIC_API_URL`에 PC의 내부 IP를 넣는다 (Windows `ipconfig`의 IPv4 주소, 예: `http://192.168.0.10:8000`). 휴대폰에서 `localhost`는 휴대폰 자신이다
3. PC와 휴대폰을 같은 와이파이에 두고 `npx expo start`. 안 되면 휴대폰 브라우저로 `http://<PC IP>:8000/health`를 열어 보고, 안 열리면 Windows 방화벽에서 8000번 포트(Python)를 허용한다
4. `.env.local`을 바꾸면 `npx expo start -c`로 다시 띄운다 (`EXPO_PUBLIC_` 값은 번들에 들어감)

- 연결된 것: 등기부 PDF → `POST /api/registry/parse`(확인 화면을 서버가 읽은 값·원문·경고로 채움), 계약 전 확인 → `POST /api/checks`(판정·비율·걸린 항목은 서버 값, 문구는 화면 것), 계약 당일 특약 예시 → `GET /api/checks/{id}/special-terms`, 계약 날짜 입력 → `POST /api/contracts`(할 일 탭이 받은 할 일 9종을 서버 순서대로 그림)
- 만든 계약 id는 휴대폰에 저장해 두고(AsyncStorage), 앱을 다시 켜면 `GET /api/contracts/{id}`로 할 일을 다시 불러온다. 서버에 그 계약이 없으면(로컬 DB를 지운 경우) 저장한 id를 지운다
- 서버 판정이 없는 결과(서버 주소 없음·연결 실패)는 특약 예시를 앱 안 규칙으로 고르고, 계약 날짜 입력 뒤 시연 할 일 목록으로 간다
- 서버에 연결하지 못하면(`NETWORK_ERROR`) 앱 안 임시 계산으로 결과를 보여 주고 결과 화면에 그렇게 표시한다. 서버가 답한 오류(입력 오류 등)는 화면에 그대로 보여 준다
- Expo Go가 아닌 설치 파일(APK·개발 빌드)로 시연하면 Android가 `http://` 주소를 막을 수 있다. 그때는 https 서버를 쓰거나 `app.json`에서 허용을 켠다

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
    precheck.tsx          UI-01 계약 전 확인 입력 (동작: 집 정보 → 공시가격 → 등기부(부동산정보요약 올리기 안내) → 확인·수정(임차권·전세권 항목별 빼기))
    check.tsx             UI-01 계약 전 확인 결과 (동작, 입력 결과 또는 시연 집 결과)
    detail.tsx            UI-02 판정 상세 (정적)
    site-check.tsx        UI-03 계약 당일 체크 2/5 현장 확인 (동작: 소유자 본인/대리인, 위임 서류, 계약금 계좌 예금주)
    contract-day.tsx      UI-03 계약 당일 체크 4/5 특약 반영 기록 (동작, 넣음/거절당함)
    contract-dates.tsx    UI-03 계약 당일 체크 5/5 계약 날짜·조건 입력 → 계약 생성·할 일 9종 (동작)
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
  lib/api.ts              백엔드 호출 (EXPO_PUBLIC_API_URL, 오류 형식 detail.code·message·hint)
  lib/contract.ts         만든 계약 저장·앱을 켤 때 다시 불러오기, 서버 할 일 → 할 일 화면 값 (지금 할 일·시작 전 고정 할 일·D-day)
  lib/check.ts            계약 전 확인 결과 값: 서버 응답 → 화면 값(checkViewFromApi), 서버가 없을 때 쓰는 임시 계산(runCheckLocal)
  lib/site-check.ts       현장 확인 항목·이름 대조(가린 글자 ○는 어떤 글자와도 같다고 봄)
  lib/store.ts            화면 사이 값 전달용 작은 저장소 (앱을 다시 켜면 사라짐)
  lib/format.ts           금액 표기 (1억 4,000만), 만 원 입력 변환
  data/demo.ts            시연 데이터 (시연 집 2채 포함). 필드 이름은 백엔드 CheckResult, 특약 문구는 rules/special_terms.yaml과 같다
```

## 화면 흐름

- 홈 → 지금 할 일(할 일 탭), 진행 단계 카드(UI-06 타임라인), 보증금 비율 카드(경보 탭), 기록함 카드, "새 집 계약 전 확인"(입력), "지난 확인 결과"(UI-01)
- 계약 전 확인 입력: "시연 집으로 채우기"(수영구 빌라·해운대구 아파트)로 한 번에 채울 수 있다. 등기부 단계에서 PDF 고르기 / 시연 등기부 불러오기 / 직접 입력 / 등기부 없이 결과 보기(최소 추정치) 중 하나
- 판정에 따라 UI-01 하단 버튼이 바뀐다: 확인 필요·문제 없음 → 패키지 9,900원, 문제 항목 → 결제 막고 상담 창구, 대상 아님(다가구·단독) → 할 일 관리 4,900원
- UI-01 → 걸린 항목 누르면 UI-02, 하단 버튼으로 UI-03 현장 확인 → 특약 반영 기록 → "다음 · 계약 날짜 입력"으로 할 일 탭
- 현장 확인: 등기부 소유자 이름을 보여 주고, 신분증(대리인이면 위임장) 이름·계좌 예금주를 입력하면 소유자와 다를 때 경고. 체크하지 않은 항목은 특약 화면·기록함에 "확인 안 함"으로 보임
- 할 일 마지막 "보증금 반환 확인 → 갈아타기" → UI-07
- 기록함 비상 모드 안내 → UI-08

## 디자인 규칙 (요약)

- 판정은 색만으로 구분하지 않고 아이콘·글자를 같이 쓴다 (문제 항목 / 확인 필요 / 문제 항목 없음). "안전합니다"는 쓰지 않는다.
- 확인 못 한 항목은 판정과 상관없이 점선 박스(`DashedBox`)로 항상 보인다.
- 결과 화면 맨 아래에 조회 시점과 "정보 제공이며 보증하지 않습니다"(`Disclaimer`)를 둔다.
- 버튼·링크 높이 44 이상, 주 버튼 52.

## 다음에 할 일

- 백엔드 API 연결 나머지: 할 일 완료(API 생기면), 시연 집은 `complex`(단지)를 보내 저장된 실거래로 매매가·주변 전세 시세 받기
- 걸린 항목 설명·확인 못 한 항목 안내 문장을 서버가 내려줄지 정하기 (지금은 `lib/check.ts`에 화면 문구로 있음)
- UI-03 나머지 단계: 1/5 테스트 결제, 3/5 계약 당일 등기부 재비교(FR-048), 5/5 계약서·이체 내역 업로드와 계약 날짜 입력(FR-014, FR-051)
- 가상 날짜 전환(`X-Virtual-Today`)으로 시연 날짜 바꾸기
- 할 일 완료 시 카메라로 증빙 1장 찍기(expo-image-picker), 기록함에 저장
- 캘린더에 추가(ICS), 개인정보 동의·면책 문구 화면
- 현장 확인 공동 소유: 등기부 소유자가 2명 이상이면(파서 응답 `owners`가 목록) 소유자마다 신분증·위임 확인. 지금은 소유자 1명만 대조 (시연 집은 단독 소유)
- 서버 없이(시연 데이터) 고른 특약 결과도 할 일 목록에 반영. 서버 계약은 `special_term_result`로 이미 반영되고, 시연 할 일 탭은 시연 시나리오(담보 설정 금지 거절)로 고정
