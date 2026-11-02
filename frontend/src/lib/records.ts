import { recordDocs, type RecordDoc } from '@/data/demo';
import type { ApiContract, ApiContractDocument, ApiTodo } from '@/lib/api';
import { specialTermRules, type SpecialTermResult } from '@/lib/special-terms';

/**
 * 기록함 칸 하나. todo가 있으면 그 할 일의 증빙, document가 있으면 첫 계약 서류(서버)라 눌러서 보고·올리고·지운다
 */
export type Slot = RecordDoc & { key: string; todo?: ApiTodo; document?: ApiContractDocument };

/**
 * 반환보증 청구·임차권등기명령에 필요한 서류를 남기는 할 일. 반환 대응 단계별 서류(todos.yaml return_response
 * documents, #52)와 같게: 확정일자 받은 계약서(T4)·임대차 신고필증(T1)·보증서(T5)와 반환 대응 단계의 증빙
 */
const CLAIM_TODOS = new Set(['T1', 'T4', 'T5', 'R1', 'R2', 'R3']);

/** "2026-10-20" → "10.20" */
const md = (s: string) => `${Number(s.slice(5, 7))}.${s.slice(8, 10)}`;

/** T1~T9 먼저 번호순, 그 뒤 반환 대응(R1~) */
const ruleOrder = (id: string) => (id.startsWith('T') ? 0 : 100) + Number(id.slice(1));

function slotMeta(t: ApiTodo): string {
  const which = t.rule_id.startsWith('T') ? `${t.rule_id.slice(1)}번 할 일` : '반환 대응';
  if (t.evidence_uploaded) return t.done_date ? `${md(t.done_date)} · ${which}` : which;
  if (t.status === 'skipped') return '나중에 올리기';
  if (t.due_date) return `${md(t.due_date)}까지 · ${which}`;
  return which;
}

/** 계약의 할 일 중 증빙이 있는 것 → 기록함 칸 (FR-031). 할 일을 끝낼 때 올린 사진이 여기 쌓인다 */
function slotsFromContract(contract: ApiContract): Slot[] {
  return contract.todos
    .filter((t): t is ApiTodo & { evidence: string } => t.evidence !== null)
    .sort((a, b) => ruleOrder(a.rule_id) - ruleOrder(b.rule_id))
    .map((t) => ({
      key: `todo-${t.id}`,
      name: t.evidence,
      meta: slotMeta(t),
      filled: t.evidence_uploaded,
      needForClaim: CLAIM_TODOS.has(t.rule_id),
      todo: t,
    }));
}

/** 계약 당일 "넣음"으로 고른 특약이 요구하는 서류 이름 (special_terms.yaml on_inserted require_document) */
export function termDocNames(results: Partial<Record<string, SpecialTermResult>>): string[] {
  const names = specialTermRules
    .filter((t) => results[t.id] === 'inserted')
    .flatMap((t) => t.ifInserted.documents);
  return [...new Set(names)];
}

/** 계약 전(앱에만 있는 특약 결과): 특약 서류는 올릴 계약이 없어 빈칸으로만 보여 준다 */
function termSlots(results: Partial<Record<string, SpecialTermResult>>): Slot[] {
  return termDocNames(results).map((name) => ({ key: `term-${name}`, name, meta: '계약 당일', filled: false, needForClaim: true }));
}

/**
 * 계약 당일 첫 계약 서류 → 기록함 칸 (FR-051, POST /api/contracts/{id}/documents). 할 일과 별개로 기록함에만 남고,
 * 반환보증 청구·임차권등기명령 서류로도 쓴다. "넣음"으로 고른 특약의 계약서 사진도 계약서(contract) 칸으로 남긴다
 * (todos.yaml first_documents). 날짜는 실제로 올린 날이 아니라 계약일(서버 타임라인과 같은 자리)
 */
function documentSlots(contract: ApiContract): Slot[] {
  return contract.documents.map((d) => ({
    key: `doc-${d.kind}`,
    name: d.label,
    meta: d.uploaded ? `${md(contract.contract_date)} · 계약 당일` : '계약 당일',
    filled: d.uploaded,
    needForClaim: true,
    document: d,
  }));
}

/**
 * 기록함 칸 (기록함 탭·홈 카드가 같이 쓴다). 계약이 있으면 첫 계약 서류와 할 일 증빙, 없으면 계약 전 특약 서류 빈칸.
 * 시연 서류 칸은 계약 없이 "시연 집으로 둘러보기"를 골랐을 때만 (내 기록과 섞지 않는다)
 */
export function recordSlots(
  contract: ApiContract | null,
  localTerms: Partial<Record<string, SpecialTermResult>>,
  demo: boolean,
): Slot[] {
  if (contract) return [...documentSlots(contract), ...slotsFromContract(contract)];
  return [...(demo ? recordDocs.map((d) => ({ ...d, key: d.name })) : []), ...termSlots(localTerms)];
}
