/**
 * 계약 전 확인: 입력값 → 내 보증금 비율 → 판정.
 *
 * 백엔드 연결 전 임시 계산이다. backend/app/engine(check.py, price.py, verdict.py)과
 * rules/verdict.yaml·alert.yaml을 그대로 옮겼다(선순위 채권 = 근저당 + 임차권·전세권 보증금, alert.yaml v1.2). 2주차에 POST /api/checks 응답으로 바꾸고 이 계산은 지운다.
 * 입력 필드 이름은 백엔드 CheckInput과 같다.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { ApiCheckResult } from '@/lib/api';
import { formatWon } from '@/lib/format';
import { termTitleFor } from '@/lib/special-terms';
import { createStore } from '@/lib/store';

export type HousingType = 'apartment' | 'row_house' | 'officetel' | 'multi_household' | 'detached';
export type TrustConsent = 'unknown' | 'obtained' | 'unavailable';
export type GuarantorConsult = 'not_yet' | 'possible' | 'impossible';

export const housingTypes: { value: HousingType; label: string }[] = [
  { value: 'apartment', label: '아파트' },
  { value: 'row_house', label: '연립다세대' },
  { value: 'officetel', label: '오피스텔' },
  { value: 'multi_household', label: '다가구' },
  { value: 'detached', label: '단독' },
];

export const isNotApplicable = (t: HousingType) => t === 'multi_household' || t === 'detached';

export type RegistryInput = {
  seizure: boolean;
  mortgage: boolean;
  mortgage_amount: number;
  /** 을구 임차권·전세권 보증금 합계. 선순위 채권에 넣는다 (확인 화면에서 뺀 항목은 빼고 보냄) */
  lease_amount: number;
  trust: boolean;
};

/** 을구 임차권·전세권 한 건 (POST /api/registry/parse 응답 leases와 같은 이름) */
export type RegistryLease = {
  rank: string;
  purpose: string;
  text: string;
  amount: number | null;
  holder: string | null;
  /** 같은 보증금으로 보이는 남긴 항목의 순위번호. 있으면 합계에서 빠진 항목이라 처음엔 빼 둔다 */
  same_deposit_as?: string | null;
};

/** 실거래를 찾을 단지 (공공데이터포털 실거래가 이름 그대로). 시연 집만 미리 매칭해 둔다 */
export type ComplexInput = { lawd_cd: string; umd_name: string; complex_name: string; jibun?: string | null };

export type CheckInput = {
  housing_type: HousingType;
  deposit: number;
  official_price: number | null;
  trade_price: number | null;
  exclusive_area: number | null;
  registry: RegistryInput | null;
  trust_consent: TrustConsent;
  building_violation: boolean | null;
  guarantor_consult: GuarantorConsult;
  /** 주면 서버가 저장된 실거래에서 매매 실거래가(trade_price가 비었을 때)와 주변 전세 시세를 찾는다 */
  complex?: ComplexInput | null;
};

export type VerdictLevel = 'na' | 'problem' | 'check' | 'ok';

export type MatchedRule = {
  key: string;
  label: string;
  level: VerdictLevel;
  explanation: string;
  /** linkage.yaml id. 계약 당일 특약 예시를 고를 때 쓴다 */
  linkage?: string;
  specialTerm?: string;
};

export type UncheckedItem = { label: string; guide: string };

/** 결과 화면(UI-01)이 그리는 값 */
export type CheckView = {
  /** 서버에 저장된 판정 id (POST /api/checks). 앱에서 임시 계산했으면 null */
  id: number | null;
  /** 서버에 연결하지 못해 앱에서 계산한 경우 등 화면 위에 보여 줄 안내 */
  notice?: string;
  houseLabel: string;
  /** 시연 빌라처럼 근저당이 시연용 가상 값이면 true ("시연용 가상 근저당" 표시) */
  virtualMortgage?: boolean;
  /** 등기부 소유자 이름. 계약 당일 현장 확인에서 신분증·계좌 예금주와 대조한다 */
  owner: string | null;
  level: VerdictLevel;
  label: string;
  next_step: string;
  summary: string;
  block_payment: boolean;
  deposit_ratio: number | null;
  ratio_is_minimum: boolean;
  estimated_price: number | null;
  formula: string[];
  matched: MatchedRule[];
  unchecked: UncheckedItem[];
  disclaimer: string;
  /** 판정에 쓴 입력값. 상세·경보 화면의 계산 근거에 쓴다 */
  input: CheckInput;
  /** 비교에 쓴 매매 실거래가 (없으면 null) */
  tradePrice: number | null;
  /** 조회일 "2026.10.09" */
  checkedAt: string;
  /** 확인 화면에서 본 등기부 원문 줄 (상세 화면 "쉬운 말로"에 보여 줌) */
  sourceLines?: string[];
  /** 시연 집이면 계약 당일 시연 장면 날짜 (계약 날짜 입력 화면의 처음 값) */
  demoDates?: { contract_date: string; balance_date: string; end_date: string };
};

/**
 * alert.yaml: 추정 주택가격 = 공시가격 × 140%, 실거래가가 있으면 둘 중 낮은 값.
 * official * 1.4는 부동소수점 때문에 1원 작게 나오는 값이 있어(비율 경계에서 백엔드 Decimal 계산과 갈림) 정수로 계산한다.
 */
export const estimateFromOfficial = (official: number) => Math.floor((official * 14) / 10);

type Rule = {
  id: string;
  label: string;
  when: (v: Values) => boolean;
  explanation: (v: Values) => string;
  linkage?: string;
};

type Values = CheckInput & { deposit_ratio: number | null };

const won = (n: number) => formatWon(n);

// verdict.yaml의 단계별 규칙. 설명 문장은 화면용 문구, 특약 예시는 연동 규칙(linkage)으로 lib/special-terms.ts에서 고른다.
const problemRules: Rule[] = [
  {
    id: 'P-1',
    label: '압류·가압류·가처분·경매개시결정 등기',
    when: (v) => v.registry?.seizure === true,
    explanation: () => '집에 압류나 경매 절차가 걸려 있어요. 이 상태로 계약하면 보증금을 돌려받지 못할 수 있어요.',
  },
  {
    id: 'P-2',
    label: '내 보증금 비율 100% 이상',
    when: (v) => v.deposit_ratio !== null && v.deposit_ratio >= 1,
    explanation: () => '보증금과 앞선 빚을 합친 금액이 추정 집값보다 많아요. 집이 팔려도 보증금을 다 돌려받기 어려워요.',
  },
  {
    id: 'P-3',
    label: '신탁등기인데 신탁사 동의서를 받을 수 없음',
    when: (v) => v.registry?.trust === true && v.trust_consent === 'unavailable',
    explanation: () => '집의 실제 소유자는 신탁회사예요. 신탁사 동의 없이 맺은 계약은 보호받기 어려워요.',
  },
  {
    id: 'P-4',
    label: '위반건축물이고 보증기관 상담에서 보증 불가 답변',
    when: (v) => v.building_violation === true && v.guarantor_consult === 'impossible',
    explanation: () => '위반건축물이라 반환보증에 가입할 수 없다는 답을 받았어요.',
  },
];

const checkRules: Rule[] = [
  {
    id: 'C-1',
    label: '근저당 있음',
    when: (v) => v.registry?.mortgage === true,
    explanation: (v) =>
      `채권최고액 ${won(v.registry?.mortgage_amount ?? 0)} 원. 집이 경매로 넘어가면 은행이 내 보증금보다 먼저 받아 가요.`,
    linkage: 'L-MORTGAGE',
  },
  {
    id: 'C-2',
    label: '내 보증금 비율 90% 이상',
    when: (v) => v.deposit_ratio !== null && v.deposit_ratio >= 0.9,
    explanation: () => '반환보증 가입이 어려운 구간이에요. 계약 전에 보증기관에 가입 가능 여부를 먼저 물어보세요.',
    linkage: 'L-RATIO90',
  },
  {
    id: 'C-3',
    label: '신탁등기 (동의서 확인 전)',
    when: (v) => v.registry?.trust === true && v.trust_consent === 'unknown',
    explanation: () => '집의 실제 소유자는 신탁회사예요. 계약 전에 신탁사 동의서를 받을 수 있는지 확인하세요.',
    linkage: 'L-TRUST',
  },
  {
    id: 'C-4',
    label: '위반건축물 (보증기관 상담 전)',
    when: (v) => v.building_violation === true && v.guarantor_consult === 'not_yet',
    explanation: () => '위반건축물은 반환보증 가입이 거절될 수 있어요. 보증기관에 먼저 상담해 보세요.',
    linkage: 'L-VIOLATION',
  },
];

const levelText: Record<VerdictLevel, { label: string; next_step: string; summary: string }> = {
  na: {
    label: '대상 아님',
    next_step: '할 일 관리만 이용할 수 있어요',
    summary: '다가구·단독주택은 다른 세대 보증금을 알 수 없어 점검·경보 대상이 아니에요. 날짜별 할 일은 챙겨 드려요.',
  },
  problem: {
    label: '문제 항목',
    next_step: '결제 전에 멈추세요',
    summary: '이대로 계약하면 보증금을 돌려받지 못할 수 있어요. 계약을 다시 검토하고 공공 상담 창구에 물어보세요.',
  },
  check: {
    label: '확인 필요',
    next_step: '특약을 넣고 진행하세요',
    summary: '아래 확인 항목과 특약 예시를 계약 당일에 챙기면 돼요.',
  },
  ok: {
    label: '문제 항목 없음',
    next_step: '기본 할 일로 진행하세요',
    summary: '등기부와 보증금 비율에서 걸린 항목이 없어요. 확인 못 한 항목은 따로 챙겨 주세요.',
  },
};

const uncheckedTax: UncheckedItem = {
  label: '임대인 국세·지방세 체납',
  guide:
    '이 서비스로는 확인할 수 없어요. 임대인에게 완납증명서를 요청하고, HUG 안심전세앱에서 임대인 위험도도 함께 조회해 보세요.',
};

const uncheckedOtherDeposits: UncheckedItem = {
  label: '다가구 다른 세대의 보증금',
  guide: '등기부에 나오지 않아요. 임대인에게 다른 세대의 보증금과 계약 기간을 서면으로 받아 두세요.',
};

/** 결과 화면의 계산식 줄. estimated = 추정 집값, tradePrice = 비교에 쓴 매매 실거래가 */
function buildFormula(input: CheckInput, estimated: number, tradePrice: number | null): string[] {
  if (!input.official_price) return [];
  const isMinimum = input.registry === null;
  const mortgageAmount = input.registry?.mortgage_amount ?? 0;
  const leaseAmount = input.registry?.lease_amount ?? 0;
  return [
    isMinimum
      ? `보증금 ${won(input.deposit)} ÷ 추정 집값 ${won(estimated)} (등기부 전이라 근저당 0원)`
      : leaseAmount
        ? `(보증금 ${won(input.deposit)} + 근저당 ${won(mortgageAmount)} + 임차권·전세권 보증금 ${won(leaseAmount)}) ÷ 추정 집값 ${won(estimated)}`
        : `(보증금 ${won(input.deposit)} + 근저당 ${won(mortgageAmount)}) ÷ 추정 집값 ${won(estimated)}`,
    `공시가격 ${won(input.official_price)} × 140% = ${won(estimateFromOfficial(input.official_price))}`,
    tradePrice ? `실거래가 ${won(tradePrice)} · 둘 중 낮은 값 사용` : '실거래가: 같은 단지·비슷한 면적 표본 부족',
  ];
}

const disclaimerText = (today: string, isMinimum: boolean) =>
  `조회 ${today}${isMinimum ? ' · 등기부 전 최소 추정치' : ''}. 정보 제공이며 보증하지 않습니다.`;

export function runCheckLocal(
  input: CheckInput,
  houseLabel: string,
  today: string,
  owner: string | null = null,
): CheckView {
  let ratio: number | null = null;
  let estimated: number | null = null;
  let formula: string[] = [];
  const isMinimum = input.registry === null;

  if (input.official_price) {
    const fromOfficial = estimateFromOfficial(input.official_price);
    estimated = input.trade_price ? Math.min(fromOfficial, input.trade_price) : fromOfficial;
    const mortgageAmount = input.registry?.mortgage_amount ?? 0;
    const leaseAmount = input.registry?.lease_amount ?? 0;
    ratio = (input.deposit + mortgageAmount + leaseAmount) / estimated;
    formula = buildFormula(input, estimated, input.trade_price);
  }

  const values: Values = { ...input, deposit_ratio: ratio };
  const toMatched = (level: VerdictLevel) => (r: Rule) => ({
    key: r.id,
    label: r.label,
    level,
    explanation: r.explanation(values),
    linkage: r.linkage,
    specialTerm: termTitleFor(r.linkage),
  });

  let level: VerdictLevel;
  let matched: MatchedRule[] = [];
  if (isNotApplicable(input.housing_type)) {
    level = 'na';
  } else {
    const problems = problemRules.filter((r) => r.when(values)).map(toMatched('problem'));
    const checks = checkRules.filter((r) => r.when(values)).map(toMatched('check'));
    matched = [...problems, ...checks];
    level = problems.length ? 'problem' : checks.length ? 'check' : 'ok';
  }

  const t = levelText[level];
  return {
    id: null,
    houseLabel,
    owner,
    level,
    label: t.label,
    next_step: t.next_step,
    summary: t.summary,
    block_payment: level === 'problem',
    deposit_ratio: level === 'na' ? null : ratio,
    ratio_is_minimum: isMinimum,
    estimated_price: estimated,
    formula,
    matched,
    unchecked: level === 'na' ? [uncheckedOtherDeposits, uncheckedTax] : [uncheckedTax],
    disclaimer: disclaimerText(today, isMinimum),
    input,
    tradePrice: input.official_price ? input.trade_price : null,
    checkedAt: today,
  };
}

/** 서버 판정 단계 id(rules/verdict.yaml) → 화면 단계 */
const levelFromApi: Record<ApiCheckResult['level'], VerdictLevel> = {
  not_applicable: 'na',
  problem: 'problem',
  check_needed: 'check',
  no_problem: 'ok',
};

/**
 * POST /api/checks 응답 → 결과 화면 값. 판정·비율·걸린 항목·확인 못 한 항목은 서버 값을 쓰고,
 * 단계 이름·다음 할 일·요약 문장과 계산식 줄은 화면 문구로 채운다.
 */
export function checkViewFromApi(
  r: ApiCheckResult,
  input: CheckInput,
  houseLabel: string,
  today: string,
  owner: string | null = null,
): CheckView {
  const level = levelFromApi[r.level] ?? 'check';
  const t = levelText[level];
  const localRules = new Map([...problemRules, ...checkRules].map((rule) => [rule.id, rule]));
  const values: Values = { ...input, deposit_ratio: r.deposit_ratio };
  const tradePrice = r.trade_basis?.price ?? input.trade_price;
  return {
    id: r.id,
    houseLabel,
    owner,
    level,
    label: t.label,
    next_step: t.next_step,
    summary: t.summary,
    block_payment: r.block_payment,
    deposit_ratio: level === 'na' ? null : r.deposit_ratio,
    ratio_is_minimum: r.ratio_is_minimum,
    estimated_price: r.estimated_price,
    formula: r.estimated_price ? buildFormula(input, r.estimated_price, tradePrice) : [],
    matched: r.matched.map((m) => ({
      key: m.id,
      label: m.label,
      level: levelFromApi[m.level] ?? 'check',
      explanation: m.explanation ?? localRules.get(m.id)?.explanation(values) ?? '',
      linkage: m.linkage ?? undefined,
      specialTerm: termTitleFor(m.linkage ?? undefined),
    })),
    unchecked: r.unchecked.map((u) => ({ label: u.label, guide: u.guide ?? '' })),
    disclaimer: disclaimerText(today, r.ratio_is_minimum),
    input,
    tradePrice,
    checkedAt: today,
  };
}

export type DetailRow = { label: string; value: string; level: VerdictLevel };

/** 판정 상세(UI-02)의 항목별 결과 줄. 걸린 규칙(verdict.yaml id)과 입력값으로 만든다 */
export function detailRowsFor(view: CheckView): DetailRow[] {
  const hit = (...ids: string[]) => view.matched.find((m) => ids.includes(m.key));
  const reg = view.input.registry;
  const notRead: DetailRow['value'] = '등기부 전 · 확인 못 함';
  const row = (label: string, ids: string[], has: boolean | null | undefined, hitText: string): DetailRow => {
    const m = hit(...ids);
    if (m) return { label, value: `있음 · ${m.level === 'problem' ? '문제 항목' : '확인 필요'}`, level: m.level };
    if (has === null || has === undefined) return { label, value: notRead, level: 'check' };
    return { label, value: has ? hitText : '없음', level: 'ok' };
  };
  const ratio = view.deposit_ratio;
  const ratioHit = hit('P-2', 'C-2');
  const ratioLevel: VerdictLevel = ratioHit ? ratioHit.level : ratio !== null && ratio >= 0.8 ? 'check' : 'ok';
  const band = ratio === null ? '' : ratio >= 1 ? '위험 구간' : ratio >= 0.9 ? '경고 구간' : ratio >= 0.8 ? '주의 구간' : '80% 미만';
  return [
    row('압류·가압류·경매', ['P-1'], reg?.seizure, '있음'),
    row('근저당', ['C-1'], reg?.mortgage, '있음'),
    row('신탁등기', ['P-3', 'C-3'], reg?.trust, '있음 · 동의서 받음'),
    {
      label: '내 보증금 비율',
      value:
        ratio === null
          ? '공시가격이 없어 계산 못 함'
          : `${Math.round(ratio * 100)}% · ${band}${view.ratio_is_minimum ? ' (최소 추정치)' : ''}`,
      level: ratio === null ? 'check' : ratioLevel,
    },
    view.input.building_violation === null
      ? { label: '위반건축물', value: '확인 못 함', level: 'check' }
      : row('위반건축물', ['P-4', 'C-4'], view.input.building_violation, '해당 · 보증 가능 답변'),
  ];
}

// 입력 화면 → 결과 화면으로 넘기는 마지막 결과. 앱을 다시 켜도 홈·경보 화면이 이어 보이게 휴대폰에 저장한다.
// 소유자 이름·등기부 원문 줄(근저당권자·임차권자 이름)은 저장하지 않고 이번 실행 동안만 둔다 (등기부는 서버에도 저장하지 않음)
const CHECK_KEY = 'jeonse.latestCheck';
const latestCheck = createStore<CheckView | null>(null);
export const useLatestCheck = latestCheck.use;

export function setLatestCheck(view: CheckView | null) {
  latestCheck.set(view);
  const save = view
    ? AsyncStorage.setItem(CHECK_KEY, JSON.stringify({ ...view, owner: null, sourceLines: undefined }))
    : AsyncStorage.removeItem(CHECK_KEY);
  save.catch(() => {}); // 저장에 실패해도 이번 실행 동안은 결과를 보여 준다
}

/** 앱을 켤 때 한 번: 저장해 둔 마지막 판정 결과를 불러온다 (입력값이 없는 예전 형식은 버린다) */
export async function restoreCheck(): Promise<void> {
  if (latestCheck.get()) return;
  try {
    const raw = await AsyncStorage.getItem(CHECK_KEY);
    const view = raw ? (JSON.parse(raw) as CheckView) : null;
    if (view?.input && !latestCheck.get()) latestCheck.set(view);
  } catch {
    // 읽지 못하면 시연 결과를 보여 준다
  }
}
