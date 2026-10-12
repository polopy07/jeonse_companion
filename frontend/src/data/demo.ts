/**
 * 시연용 예시 값. 목업(docs/design)의 시나리오를 그대로 따른다.
 * 부산 수영구 근저당 빌라, 담보 설정 금지 특약 "거절당함".
 * 특약 문구는 rules/special_terms.yaml과 같다. 백엔드 API가 붙으면 이 파일 대신 응답을 쓴다. 필드 이름은 백엔드 CheckResult와 맞췄다.
 */

export type VerdictLevel = 'problem' | 'check' | 'ok';

export type MatchedRule = {
  key: string;
  label: string;
  level: VerdictLevel;
  explanation: string;
  specialTerm?: string;
};

export type UncheckedItem = {
  label: string;
  guide: string;
};

export type CheckResult = {
  level: VerdictLevel;
  label: string;
  next_step: string;
  summary: string;
  block_payment: boolean;
  deposit_ratio: number;
  estimated_price: number;
  matched: MatchedRule[];
  unchecked: UncheckedItem[];
  disclaimer: string;
};

export const house = {
  name: '수영구 ○○동 빌라 201호',
  type: '다세대',
  deposit: 140_000_000,
  mortgage: 36_000_000,
  officialPrice: 150_000_000,
  contractDate: '2026.10.20',
  balanceDate: '2026.11.20',
  endDate: '2028.11.19',
};

/** 시연 기준 가상 날짜 */
export const today = { label: '11.10', full: '2026.11.10' };

export const checkResult: CheckResult = {
  level: 'check',
  label: '확인 필요',
  next_step: '특약을 넣고 진행하세요',
  summary: '근저당이 있는 집이에요. 아래 확인 항목과 특약 예시를 계약 당일에 챙기면 돼요.',
  block_payment: false,
  deposit_ratio: 0.84,
  estimated_price: 210_000_000,
  matched: [
    {
      key: 'mortgage',
      label: '근저당 있음',
      level: 'check',
      explanation: '채권최고액 3,600만 원. 집이 경매로 넘어가면 은행이 내 보증금보다 먼저 받아 가요.',
      specialTerm: '잔금일 다음 날까지 담보 설정 금지',
    },
  ],
  unchecked: [
    {
      label: '임대인 국세·지방세 체납',
      guide:
        '이 서비스로는 확인할 수 없어요. 임대인에게 완납증명서를 요청하고, HUG 안심전세앱에서 임대인 위험도도 함께 조회해 보세요.',
    },
  ],
  disclaimer: '조회 2026.10.09 · 공시가격 2026.01.01 기준. 정보 제공이며 보증하지 않습니다.',
};

export type DetailRow = { label: string; value: string; level: VerdictLevel };

export const detailRows: DetailRow[] = [
  { label: '압류·가압류·경매', value: '없음', level: 'ok' },
  { label: '근저당', value: '있음 · 확인 필요', level: 'check' },
  { label: '신탁등기', value: '없음', level: 'ok' },
  { label: '내 보증금 비율', value: '84% · 주의 구간', level: 'check' },
  { label: '위반건축물', value: '해당 없음', level: 'ok' },
];

export type SpecialTerm = { title: string; link: string; text: string };

export const specialTerms: SpecialTerm[] = [
  {
    title: '잔금일 다음 날까지 담보 설정 금지',
    link: '근저당 있음과 연결',
    text: '임대인은 잔금 지급일 다음 날까지 이 주택에 저당권 등 담보권을 설정하지 않는다. 이를 위반하면 임차인은 계약을 해제할 수 있으며 임대인은 손해를 배상한다.',
  },
  {
    title: '보증·대출 거절 시 계약 해제',
    link: '모든 계약 공통',
    text: '임차인의 전세자금대출 또는 전세보증금 반환보증이 거절되면 임차인은 계약을 해제할 수 있고, 임대인은 받은 계약금을 즉시 반환한다.',
  },
  {
    title: '국세·지방세 완납증명 제출',
    link: '확인 못 한 항목: 체납과 연결',
    text: '임대인은 잔금 지급 전까지 국세·지방세 완납증명서를 임차인에게 제출한다.',
  },
];

export const siteChecks = [
  '등기부 소유자 이름 = 계약서 임대인',
  '대리인 없음 (임대인 본인 참석)',
  '계약금 계좌 명의 = 소유자',
];

export type TodoStatus = 'done' | 'current' | 'upcoming' | 'later';

export type Todo = {
  id: string;
  title: string;
  when: string;
  dday?: string;
  badge?: string;
  status: TodoStatus;
  /** 오늘 선을 이 항목 앞에 긋는다 */
  todayBefore?: boolean;
  href?: '/switch';
};

export const todos: Todo[] = [
  { id: 'T1', title: '임대차 신고', when: '10.21 완료 · 증빙 1장', status: 'done' },
  { id: 'T2', title: '보증 가입 여부 확정', when: '10.28 완료 · HUG', status: 'done' },
  {
    id: 'T3',
    title: '잔금일 아침 등기부 재비교',
    when: '11.20(금) 아침',
    dday: 'D-10',
    badge: '특약 거절됨 · 꼭 확인',
    status: 'current',
    todayBefore: true,
  },
  { id: 'T4', title: '전입신고', when: '11.20(금) 잔금 직후', dday: 'D-10', badge: '잔금일 당일 필수', status: 'upcoming' },
  { id: 'T5', title: '반환보증 가입', when: '보증기관 가입 마감 기준', status: 'upcoming' },
  { id: 'T7', title: '갱신 또는 이사 의사 통보', when: '2028.09.19 · 만기 2개월 전', status: 'later' },
  { id: 'T9', title: '보증금 반환 확인 → 갈아타기', when: '2028.11.19 · 만기일', status: 'later', href: '/switch' },
];

export type RecordDoc = { name: string; meta: string; filled: boolean; needForClaim: boolean };

export const recordDocs: RecordDoc[] = [
  { name: '계약서', meta: '10.20', filled: true, needForClaim: true },
  { name: '계약금 이체 내역', meta: '10.20', filled: true, needForClaim: true },
  { name: '계약 당일 등기부', meta: '10.20', filled: true, needForClaim: false },
  { name: '임대차 신고 확인', meta: '10.21', filled: true, needForClaim: true },
  { name: '잔금일 등기부', meta: '11.20 예정', filled: false, needForClaim: false },
  { name: '잔금 이체 내역', meta: '11.20 예정', filled: false, needForClaim: true },
  { name: '전입신고 확인', meta: '11.20 예정', filled: false, needForClaim: true },
  { name: '반환보증 가입증서', meta: '가입 후', filled: false, needForClaim: false },
  { name: '반환 요청 기록', meta: '만기 때', filled: false, needForClaim: true },
];

export type TimelineKind = 'contract' | 'todo' | 'alert';

export type TimelineEvent = {
  year: string;
  md: string;
  kind: TimelineKind;
  title: string;
  sub: string;
  photo: boolean;
};

export const timeline: TimelineEvent[] = [
  { year: '2026', md: '10.09', kind: 'contract', title: '계약 전 확인', sub: '확인 필요 · 근저당 있음', photo: false },
  { year: '2026', md: '10.20', kind: 'contract', title: '계약 당일 현장 확인', sub: '소유자·대리인·계좌 명의 확인', photo: true },
  { year: '2026', md: '10.20', kind: 'alert', title: '특약 거절당함', sub: '잔금일 다음 날까지 담보 설정 금지', photo: false },
  { year: '2026', md: '10.21', kind: 'todo', title: '임대차 신고', sub: '확정일자 함께 받음', photo: true },
  { year: '2026', md: '10.28', kind: 'todo', title: '보증 가입 여부 확정', sub: 'HUG 반환보증 가입 예정', photo: false },
  { year: '2026', md: '11.20', kind: 'todo', title: '잔금일 등기부 재비교', sub: '새 담보 없음', photo: true },
  { year: '2026', md: '11.20', kind: 'todo', title: '전입신고', sub: '잔금 당일 완료', photo: true },
  { year: '2027', md: '04.30', kind: 'alert', title: '경보 단계 변화', sub: '84% → 88% · 공시가격 하락', photo: false },
  { year: '2028', md: '09.10', kind: 'todo', title: '이사 의사 통보', sub: '내용증명 사본 저장', photo: true },
];

export const alertReport = {
  stage: '경고 단계',
  recalculatedAt: '2027.10.15 재계산',
  ratio: 91,
  previous: 88,
  reason:
    '같은 단지 실거래가가 추정 집값보다 낮게 신고돼 다시 계산했어요. 90%를 넘으면 반환보증 신규 가입이 어려운 구간이에요.',
  history: [
    { label: '26.10', ratio: 84 },
    { label: '27.01', ratio: 84 },
    { label: '27.04', ratio: 88 },
    { label: '27.07', ratio: 88 },
    { label: '27.10', ratio: 91 },
    { label: '28.01', ratio: 91 },
  ],
  basis: [
    { label: '보증금 + 근저당', note: undefined, value: '1억 7,600만', struck: false },
    { label: '공시가격 × 140%', note: '2027.01.01 기준', value: '2억 20만', struck: true },
    { label: '실거래가 · 전용 ±10%', note: '2027.09 신고 · 표본 3건', value: '1억 9,300만', struck: false },
  ],
  estimated: '1억 9,300만',
};

export const returnSteps = [
  { title: '반환 요청 기록', body: '11.19 문자 캡처 저장됨', state: 'done' as const },
  {
    title: '내용증명 보내기',
    body: '반환을 요청했다는 사실을 공식 기록으로 남기는 일반 절차예요. 우체국 방문이나 인터넷우체국으로 보낼 수 있어요.',
    state: 'current' as const,
  },
  {
    title: '임차권등기명령',
    body: '대법원 전자소송에서 신청할 수 있어요. 등기 완료를 확인한 뒤에 이사해야 대항력이 유지돼요.',
    state: 'todo' as const,
  },
  {
    title: '반환보증 청구',
    body: 'HUG 반환보증 가입자예요. 보증기관 청구 창구에서 절차를 안내받으세요.',
    state: 'todo' as const,
  },
];

export const helpDesks = [
  { label: '대법원 전자소송', url: 'https://ecfs.scourt.go.kr' },
  { label: '주택도시보증공사 보증 청구', url: 'https://www.khug.or.kr' },
  { label: '대한법률구조공단 상담', url: 'https://www.klac.or.kr' },
];
