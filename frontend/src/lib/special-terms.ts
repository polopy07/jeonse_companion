/**
 * 계약 당일 특약 예시와 "넣음/거절당함" 기록 (FR-039, FR-049, FR-050).
 *
 * rules/special_terms.yaml·linkage.yaml(v1.1)을 옮긴 것이다. 백엔드 GET /api/checks/{id}/special-terms(#32)와 같은 기준으로,
 * 판정에 걸린 MVP 연동 규칙(근저당, 비율 90% 이상, 신탁)에 연결된 MVP 특약만 보여 준다.
 * 서버 판정(id가 있는 결과)은 GET /api/checks/{id}/special-terms 응답을 termsFromApi로 바꿔 쓰고,
 * 서버 없이 앱에서 계산한 결과일 때만 이 파일의 규칙으로 고른다.
 */
import type { ApiSpecialTerms, ApiTermOutcome } from '@/lib/api';
import { createStore } from '@/lib/store';

/** 백엔드 POST /api/contracts의 special_term_result 값과 같다 */
export type SpecialTermResult = 'inserted' | 'rejected';
export type SpecialTermId = 'S-NO-MORTGAGE' | 'S-GUARANTEE-CANCEL' | 'S-TAX-CERT';

/** linkage.yaml에서 mvp: true인 연동 규칙 */
const MVP_LINKAGES = ['L-MORTGAGE', 'L-RATIO90', 'L-TRUST'];

/** 넣었을 때 / 거절당했을 때 생기는 것 (special_terms.yaml on_inserted / on_rejected) */
export type TermOutcome = {
  warnings: string[];
  documents: string[];
  /** 할 일 목록 맨 위로 올라가는 할 일 */
  movesToTop: string[];
  /** 새로 생기는 할 일 */
  addsTodos?: string[];
  linkCounsel: boolean;
};

export type SpecialTermRule = {
  /** special_terms.yaml id. 서버 응답의 새 특약도 받을 수 있게 string */
  id: SpecialTermId | (string & {});
  title: string;
  text: string;
  source: string;
  shownWhen: string[];
  mvp: boolean;
  ifInserted: TermOutcome;
  ifRejected: TermOutcome;
};

const SOURCE = '주택임대차표준계약서 특약 예시, 공공기관 배포 자료';

export const specialTermRules: SpecialTermRule[] = [
  {
    id: 'S-NO-MORTGAGE',
    title: '잔금일 다음 날까지 담보 설정 금지',
    text: '임대인은 잔금 지급일 다음 날까지 이 주택에 저당권 등 담보권을 설정하지 않는다. 이를 위반하면 임차인은 계약을 해제할 수 있으며 임대인은 손해를 배상한다.',
    source: SOURCE,
    shownWhen: ['L-MORTGAGE'],
    mvp: true,
    ifInserted: { warnings: [], documents: ['특약이 보이는 계약서 사진'], movesToTop: [], linkCounsel: false },
    ifRejected: {
      warnings: ['잔금 당일 설정되는 담보는 잔금일 등기부 재비교로 잡을 수 없어요. 잔금일 당일 전입신고로 대항력을 확보하세요.'],
      documents: [],
      movesToTop: ['전입신고 · 잔금일 당일'],
      linkCounsel: false,
    },
  },
  {
    id: 'S-GUARANTEE-CANCEL',
    title: '보증·대출 거절 시 계약 해제',
    text: '임차인의 전세자금대출 또는 전세보증금 반환보증이 거절되면 임차인은 계약을 해제할 수 있고, 임대인은 받은 계약금을 즉시 반환한다.',
    source: SOURCE,
    shownWhen: ['L-RATIO90', 'L-VIOLATION'],
    mvp: true,
    ifInserted: {
      warnings: ['보증이 거절되면 계약 해제 절차를 안내해 드려요.'],
      documents: ['특약이 보이는 계약서 사진'],
      movesToTop: [],
      linkCounsel: false,
    },
    ifRejected: {
      warnings: ['보증이 거절되면 계약금을 돌려받지 못할 수 있어요.'],
      documents: [],
      movesToTop: ['보증 가입 여부 확정 · 잔금 전 사전심사·상담'],
      linkCounsel: true,
    },
  },
  {
    id: 'S-TAX-CERT',
    title: '국세·지방세 완납증명 제출',
    text: '임대인은 잔금 지급 전까지 국세·지방세 완납증명서를 임차인에게 제출한다.',
    source: SOURCE,
    shownWhen: ['L-TAX'],
    mvp: false,
    ifInserted: { warnings: [], documents: ['국세·지방세 완납증명서'], movesToTop: [], linkCounsel: false },
    ifRejected: { warnings: [], documents: [], movesToTop: [], linkCounsel: false },
  },
];

/** 판정에 걸린 항목 (연동 규칙이 있는 것만 쓴다) */
type LinkedItem = { label: string; linkage?: string };

export type ShownTerm = SpecialTermRule & {
  /** 이 특약을 보여 주게 한 걸린 항목 ("근저당 있음 항목과 연결") */
  link: string;
};

/** 판정에 걸린 항목으로 계약 당일 특약 예시를 고른다 (백엔드 contract_day_guide와 같은 기준) */
export function termsFor(matched: LinkedItem[]): ShownTerm[] {
  const active = matched.filter((m) => m.linkage && MVP_LINKAGES.includes(m.linkage));
  return specialTermRules.flatMap((t) => {
    const linked = active.filter((m) => t.shownWhen.includes(m.linkage!));
    if (!t.mvp || !linked.length) return [];
    return [{ ...t, link: `${linked.map((m) => m.label).join(', ')} 항목과 연결` }];
  });
}

const outcomeFromApi = (o: ApiTermOutcome): TermOutcome => ({
  warnings: o.warnings,
  documents: o.documents,
  movesToTop: o.moves_to_top.map((t) => t.title),
  addsTodos: o.adds_todos.map((t) => t.title),
  linkCounsel: o.link_counsel,
});

/** GET /api/checks/{id}/special-terms 응답 → 계약 당일 화면의 특약 카드 */
export function termsFromApi(r: ApiSpecialTerms): ShownTerm[] {
  return r.terms.map((t) => ({
    id: t.id,
    title: t.label,
    text: t.text,
    source: t.source,
    shownWhen: t.linked.map((l) => l.id),
    mvp: true,
    ifInserted: outcomeFromApi(t.if_inserted),
    ifRejected: outcomeFromApi(t.if_rejected),
    link: `${t.linked.map((l) => l.label).join(', ')} 항목과 연결`,
  }));
}

/** 걸린 연동 규칙 하나가 보여 주는 특약 제목 (결과 화면 UI-01의 "계약 당일 넣을 특약 예시") */
export function termTitleFor(linkage: string | undefined): string | undefined {
  if (!linkage || !MVP_LINKAGES.includes(linkage)) return undefined;
  return specialTermRules.find((t) => t.mvp && t.shownWhen.includes(linkage))?.title;
}

// 계약 당일에 고른 "넣음/거절당함". 계약 날짜 입력(5/5)에서 POST /api/contracts의 special_term_result로 보낸다
const termResults = createStore<Partial<Record<string, SpecialTermResult>>>({});
export const setSpecialTermResults = termResults.set;
export const useSpecialTermResults = termResults.use;
