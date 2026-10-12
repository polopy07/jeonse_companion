/**
 * 계약 전 확인: 입력값 → 내 보증금 비율 → 판정.
 *
 * 백엔드 연결 전 임시 계산이다. backend/app/engine(check.py, price.py, verdict.py)과
 * rules/verdict.yaml·alert.yaml v1.0을 그대로 옮겼다. 2주차에 POST /api/checks 응답으로 바꾸고 이 계산은 지운다.
 * 입력 필드 이름은 백엔드 CheckInput과 같다.
 */
import { useSyncExternalStore } from 'react';

import { formatWon } from '@/lib/format';

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
  trust: boolean;
};

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
};

export type VerdictLevel = 'na' | 'problem' | 'check' | 'ok';

export type MatchedRule = {
  key: string;
  label: string;
  level: VerdictLevel;
  explanation: string;
  specialTerm?: string;
};

export type UncheckedItem = { label: string; guide: string };

/** 결과 화면(UI-01)이 그리는 값 */
export type CheckView = {
  houseLabel: string;
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
};

// alert.yaml: 추정 주택가격 = 공시가격 × 140%, 실거래가가 있으면 둘 중 낮은 값
const OFFICIAL_MULTIPLIER = 1.4;

type Rule = {
  id: string;
  label: string;
  when: (v: Values) => boolean;
  explanation: (v: Values) => string;
  specialTerm?: string;
};

type Values = CheckInput & { deposit_ratio: number | null };

const won = (n: number) => formatWon(n);

// verdict.yaml의 단계별 규칙. 설명 문장과 특약 예시는 화면용 문구다 (서버가 내려줄지 2주차에 정한다).
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
    specialTerm: '잔금일 다음 날까지 담보 설정 금지',
  },
  {
    id: 'C-2',
    label: '내 보증금 비율 90% 이상',
    when: (v) => v.deposit_ratio !== null && v.deposit_ratio >= 0.9,
    explanation: () => '반환보증 가입이 어려운 구간이에요. 계약 전에 보증기관에 가입 가능 여부를 먼저 물어보세요.',
    specialTerm: '보증·대출 거절 시 계약 해제',
  },
  {
    id: 'C-3',
    label: '신탁등기 (동의서 확인 전)',
    when: (v) => v.registry?.trust === true && v.trust_consent === 'unknown',
    explanation: () => '집의 실제 소유자는 신탁회사예요. 계약 전에 신탁사 동의서를 받을 수 있는지 확인하세요.',
  },
  {
    id: 'C-4',
    label: '위반건축물 (보증기관 상담 전)',
    when: (v) => v.building_violation === true && v.guarantor_consult === 'not_yet',
    explanation: () => '위반건축물은 반환보증 가입이 거절될 수 있어요. 보증기관에 먼저 상담해 보세요.',
    specialTerm: '보증·대출 거절 시 계약 해제',
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

export function runCheckLocal(input: CheckInput, houseLabel: string, today: string): CheckView {
  let ratio: number | null = null;
  let estimated: number | null = null;
  const formula: string[] = [];
  const isMinimum = input.registry === null;

  if (input.official_price) {
    const fromOfficial = Math.floor(input.official_price * OFFICIAL_MULTIPLIER);
    estimated = input.trade_price ? Math.min(fromOfficial, input.trade_price) : fromOfficial;
    const senior = input.registry?.mortgage_amount ?? 0;
    ratio = (input.deposit + senior) / estimated;

    formula.push(
      isMinimum
        ? `보증금 ${won(input.deposit)} ÷ 추정 집값 ${won(estimated)} (등기부 전이라 근저당 0원)`
        : `(보증금 ${won(input.deposit)} + 근저당 ${won(senior)}) ÷ 추정 집값 ${won(estimated)}`,
    );
    formula.push(`공시가격 ${won(input.official_price)} × 140% = ${won(fromOfficial)}`);
    formula.push(
      input.trade_price
        ? `실거래가 ${won(input.trade_price)} · 둘 중 낮은 값 사용`
        : '실거래가: 같은 단지·비슷한 면적 표본 부족',
    );
  }

  const values: Values = { ...input, deposit_ratio: ratio };
  const toMatched = (level: VerdictLevel) => (r: Rule) => ({
    key: r.id,
    label: r.label,
    level,
    explanation: r.explanation(values),
    specialTerm: r.specialTerm,
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
  const asOf = `조회 ${today}`;
  return {
    houseLabel,
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
    disclaimer: `${asOf}${isMinimum ? ' · 등기부 전 최소 추정치' : ''}. 정보 제공이며 보증하지 않습니다.`,
  };
}

// 입력 화면 → 결과 화면으로 넘기는 마지막 결과. 앱을 다시 켜면 사라진다.
let latest: CheckView | null = null;
const listeners = new Set<() => void>();

export function setLatestCheck(view: CheckView) {
  latest = view;
  listeners.forEach((l) => l());
}

export function useLatestCheck() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => latest,
    () => latest,
  );
}
