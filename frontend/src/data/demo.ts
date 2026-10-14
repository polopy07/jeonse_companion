/**
 * 시연용 예시 값. 목업(docs/design)의 시나리오를 그대로 따른다.
 * 부산 수영구 근저당 빌라, 담보 설정 금지 특약 "거절당함".
 * 특약 문구는 lib/special-terms.ts(rules/special_terms.yaml)에 있다. 백엔드 API가 붙으면 이 파일 대신 응답을 쓴다. 필드 이름은 백엔드 CheckResult와 맞췄다.
 */

import type { SiteCheckState } from '@/lib/site-check';
import { runCheckLocal, type CheckInput, type CheckView, type HousingType, type RegistryLease } from '@/lib/check';

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

/**
 * 시연 집 2채. 공시가격·건축물대장은 미리 매칭해 둔 값이고(MVP 범위), 등기부는 올리면 이 값으로 추출된 것처럼 보여 준다.
 * 아파트 값은 화면 확인용 가상 값이라 시연 데이터가 정해지면 바꾼다.
 */
export type DemoHouse = {
  id: string;
  chip: string;
  label: string;
  address: string;
  housing_type: HousingType;
  depositManwon: string;
  area: string;
  official_price: number;
  officialBasis: string;
  trade_price: number | null;
  building_violation: boolean;
  registry: {
    owner: string;
    seizure: boolean;
    mortgage: boolean;
    mortgage_amount: number;
    /** 을구 임차권·전세권 (확인 화면에서 항목별로 뺄 수 있음) */
    leases: RegistryLease[];
    trust: boolean;
    source: string[];
    /** 근저당이 실제 등기부에 없는 시연용 가상 값 (docs/validation/경보계산_정답표.md). 화면에 "시연용 가상 근저당"으로 표시 */
    virtualMortgage?: boolean;
  };
};

export const demoHouses: DemoHouse[] = [
  {
    id: 'villa',
    chip: '수영구 빌라',
    label: house.name,
    address: '부산 수영구 ○○동 ○○빌라 201호',
    housing_type: 'row_house',
    depositManwon: '14000',
    area: '49.5',
    official_price: 150_000_000,
    officialBasis: '2026.01.01 기준',
    trade_price: null,
    building_violation: false,
    registry: {
      owner: '김○○',
      seizure: false,
      mortgage: true,
      mortgage_amount: 36_000_000,
      leases: [],
      trust: false,
      virtualMortgage: true,
      source: ['갑구 1 · 소유권보존 · 소유자 김○○', '을구 1 · 근저당권설정 · 채권최고액 금36,000,000원 · 근저당권자 ○○은행'],
    },
  },
  {
    id: 'apt',
    chip: '해운대구 아파트',
    label: '해운대구 ○○아파트 101동 1203호',
    address: '부산 해운대구 ○○동 ○○아파트 101동 1203호',
    housing_type: 'apartment',
    depositManwon: '25000',
    area: '84.9',
    official_price: 260_000_000,
    officialBasis: '2026.01.01 기준',
    trade_price: 340_000_000,
    building_violation: false,
    registry: {
      owner: '이○○',
      seizure: false,
      mortgage: false,
      mortgage_amount: 0,
      leases: [],
      trust: false,
      source: ['갑구 1 · 소유권이전 · 소유자 이○○', '을구 · 기록사항 없음'],
    },
  },
];

const villa = demoHouses[0];
const villaInput: CheckInput = {
  housing_type: villa.housing_type,
  deposit: house.deposit,
  official_price: villa.official_price,
  trade_price: villa.trade_price,
  exclusive_area: Number(villa.area),
  registry: { seizure: false, mortgage: true, mortgage_amount: house.mortgage, lease_amount: 0, trust: false },
  trust_consent: 'unknown',
  building_violation: false,
  guarantor_consult: 'not_yet',
};

/** 홈에서 "결과 다시 보기"로 여는 시연 집 결과 (계약 전 확인 2026.10.09) */
export const checkResult: CheckView = {
  ...runCheckLocal(villaInput, `${house.name} · ${house.type}`, '2026.10.09', villa.registry.owner),
  virtualMortgage: villa.registry.virtualMortgage,
  sourceLines: villa.registry.source,
  summary: '근저당이 있는 집이에요. 아래 확인 항목과 특약 예시를 계약 당일에 챙기면 돼요.',
  disclaimer: '조회 2026.10.09 · 공시가격 2026.01.01 기준. 정보 제공이며 보증하지 않습니다.',
};

/** 시연 집 계약 당일 현장 확인 (소유자 본인 참석, 모두 확인) */
export const siteCheckDemo: SiteCheckState = {
  attendee: 'owner',
  idName: '김철수',
  idChecked: true,
  poaChecked: false,
  sealChecked: false,
  agentIdChecked: false,
  ownerCallChecked: false,
  accountHolder: '김철수',
  accountChecked: true,
};

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
  // 담보 설정 금지 특약 "거절당함" → 전입신고를 맨 위로 (special_terms.yaml S-NO-MORTGAGE on_rejected, AC-016)
  {
    id: 'T4',
    title: '전입신고',
    when: '11.20(금) 잔금 직후',
    dday: 'D-10',
    badge: '특약 거절됨 · 잔금일 당일 필수',
    status: 'current',
    todayBefore: true,
  },
  { id: 'T3', title: '잔금일 아침 등기부 재비교', when: '11.20(금) 아침', dday: 'D-10', status: 'upcoming' },
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
