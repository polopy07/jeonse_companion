/**
 * 백엔드 API 호출 (docs/api/API_명세.md, docs/api/openapi.json).
 *
 * 서버 주소는 EXPO_PUBLIC_API_URL (frontend/.env.local). 앱 시연은 휴대폰에서 PC의 서버를 부르므로
 * localhost가 아니라 PC의 내부 IP를 넣는다 (예: http://192.168.0.10:8000). 비워 두면 서버를 부르지 않고
 * 화면이 앱 안 임시 계산·시연 데이터로 동작한다.
 */
import { Platform } from 'react-native';

import type { CheckInput, RegistryLease } from '@/lib/check';

const API_URL = process.env.EXPO_PUBLIC_API_URL?.trim().replace(/\/+$/, '') || null;
const TIMEOUT_MS = 15_000;

/** 서버 주소가 설정돼 있는지 */
export const apiEnabled = API_URL !== null;

/** 오류 응답 detail (API 명세 1.5절). 연결 실패는 code = NETWORK_ERROR */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly hint: string | null = null,
    readonly status: number | null = null,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  if (!API_URL) throw new ApiError('API_URL_MISSING', '서버 주소가 설정되지 않았어요');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
  } catch {
    throw new ApiError(
      'NETWORK_ERROR',
      '서버에 연결하지 못했어요',
      'PC와 휴대폰이 같은 와이파이인지, 서버를 --host 0.0.0.0으로 띄웠는지 확인하세요',
    );
  } finally {
    clearTimeout(timer);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    throw new ApiError(
      typeof detail?.code === 'string' ? detail.code : `HTTP_${res.status}`,
      [
        typeof detail?.message === 'string' ? detail.message : `서버 오류 (HTTP ${res.status})`,
        // 입력 형식 오류(422)는 필드별 문제를 붙인다
        ...(Array.isArray(detail?.fields) ? detail.fields.map((f: { message?: string }) => f.message).filter(Boolean) : []),
      ].join(': '),
      typeof detail?.hint === 'string' ? detail.hint : null,
      res.status,
    );
  }
  return body as T;
}

// ---- POST /api/registry/parse ----

type RegistryEntry = { rank: string; purpose: string; text: string };

export type ApiRegistryParseResult = {
  fields: { seizure: boolean; mortgage: boolean; mortgage_amount: number; lease_amount?: number; trust: boolean };
  owners: string[];
  mortgages: (RegistryEntry & { amount: number | null; holder: string | null })[];
  /** 을구 임차권·전세권 (#65 이후 서버) */
  leases?: RegistryLease[];
  seizures: RegistryEntry[];
  trusts: RegistryEntry[];
  others: RegistryEntry[];
  warnings: string[];
};

/** 등기부 PDF(부동산정보요약) → 추출 결과. 저장하지 않는다 */
export async function parseRegistry(file: { uri: string; name: string; mimeType?: string | null }) {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(file.uri)).blob();
    form.append('file', blob, file.name);
  } else {
    // React Native의 FormData는 { uri, name, type }으로 파일을 보낸다
    form.append('file', { uri: file.uri, name: file.name, type: file.mimeType ?? 'application/pdf' } as unknown as Blob);
  }
  return request<ApiRegistryParseResult>('/api/registry/parse', { method: 'POST', body: form });
}

// ---- POST /api/checks ----

export type ApiCheckResult = {
  id: number;
  level: 'not_applicable' | 'problem' | 'check_needed' | 'no_problem';
  label: string;
  next_step: string;
  block_payment: boolean;
  estimated_price: number | null;
  deposit_ratio: number | null;
  ratio_is_minimum: boolean;
  matched: {
    id: string;
    label: string;
    level: ApiCheckResult['level'];
    linkage: string | null;
    explanation: string | null;
  }[];
  linkages: string[];
  unchecked: { id: string; label: string; linkage: string | null; guide: string | null }[];
  disclaimer: string;
  rules_version: string;
  as_of: string | null;
  trade_basis: { price: number; deal_date: string; exclusive_area: number; sample_count: number; used: boolean } | null;
  nearby_jeonse: { median: number | null; sample_count: number; low_sample: boolean; below_deposit: boolean | null } | null;
  /** 이 판정으로 만든 계약 id. 아직 없으면 null */
  contract_id: number | null;
};

/** 계약 전 확인 → 판정 (서버에 저장). virtualToday는 시연 가상 날짜 (YYYY-MM-DD) */
export function postCheck(input: CheckInput, virtualToday?: string) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (virtualToday) headers['X-Virtual-Today'] = virtualToday;
  return request<ApiCheckResult>('/api/checks', { method: 'POST', headers, body: JSON.stringify(input) });
}

/** 저장된 판정 (409 CHECK_ALREADY_USED 때 contract_id로 만든 계약을 찾는다) */
export function getCheck(checkId: number) {
  return request<ApiCheckResult>(`/api/checks/${checkId}`, { method: 'GET' });
}

// ---- GET /api/checks/{id}/special-terms ----

export type ApiTermOutcome = {
  warnings: string[];
  documents: string[];
  moves_to_top: { id: string; title: string }[];
  adds_todos: { id: string; title: string }[];
  link_counsel: boolean;
};

export type ApiSpecialTerms = {
  check_id: number;
  level: string;
  terms: {
    id: string;
    label: string;
    text: string;
    source: string;
    linked: { id: string; label: string }[];
    if_inserted: ApiTermOutcome;
    if_rejected: ApiTermOutcome;
  }[];
  /** 연동 규칙이 계약 당일에 보여 주는 경고 */
  warnings: string[];
  /** 연동 규칙이 계약 당일에 요구하는 확인 */
  checks: string[];
  disclaimer: string;
  rules_version: string;
};

/** 판정에 맞는 계약 당일 특약 예시 ("문제 항목" 판정이면 409 CHECK_BLOCKED) */
export function getSpecialTerms(checkId: number) {
  return request<ApiSpecialTerms>(`/api/checks/${checkId}/special-terms`, { method: 'GET' });
}

// ---- POST /api/contracts ----

export type Guarantor = 'HUG' | 'HF' | 'SGI' | 'none';

export type ApiContractInput = {
  check_id: number;
  /** YYYY-MM-DD */
  contract_date: string;
  balance_date: string;
  end_date: string;
  monthly_rent?: number;
  loan?: boolean;
  loan_execution_date?: string | null;
  guarantor?: Guarantor;
  brokered?: boolean;
  renewal_right_used?: boolean;
  co_tenant?: boolean;
  email?: string | null;
  /** 특약 id → 넣음/거절당함 (계약 당일 화면에서 보여 준 특약만) */
  special_term_result?: Record<string, 'inserted' | 'rejected'>;
};

export type ApiTodo = {
  id: number;
  /** todos.yaml id (T1~T9) */
  rule_id: string;
  title: string;
  detail: string | null;
  start_date: string | null;
  due_date: string | null;
  remind_date: string | null;
  prerequisites: string[];
  required_checks: string[];
  evidence: string | null;
  pinned: boolean;
  moved_to_top: boolean;
  sort_order: number;
  status: 'todo' | 'done' | 'skipped';
  rules_version: string;
};

export type ApiContract = {
  id: number;
  check_id: number;
  level: string;
  deposit: number;
  contract_date: string;
  balance_date: string;
  end_date: string;
  guarantor: Guarantor;
  special_term_result: Record<string, 'inserted' | 'rejected'>;
  /** 임대차 신고 대상인지 (비대상이면 신고 대신 확정일자 할 일) */
  report_required: boolean;
  /** 계약 시작 때 경보 단계 (alert.yaml id). 정상이면 null */
  alert_level: 'caution' | 'warning' | 'danger' | null;
  /** sort_order 순서 */
  todos: ApiTodo[];
};

/** 패키지 시작: 계약 생성 + 할 일 9종 생성 */
export function postContract(input: ApiContractInput) {
  return request<ApiContract>('/api/contracts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

/** 계약 정보와 할 일 목록 (앱을 다시 켰을 때 이어 보기) */
export function getContract(contractId: number) {
  return request<ApiContract>(`/api/contracts/${contractId}`, { method: 'GET' });
}

// ---- GET /api/demo-houses ----

export type ApiDemoHouse = {
  id: string;
  title: string;
  address: string;
  official_price_source: string;
  /** 그대로 POST /api/checks로 보내는 입력값 */
  input: CheckInput;
  /** 시연 등기부를 읽은 결과 (POST /api/registry/parse와 같은 형식) */
  registry: ApiRegistryParseResult;
  /** 실제 자료가 아닌 시연용 가상 값 */
  virtual: string[];
  /** 계약 당일 시연 장면의 날짜와 특약 결과 */
  contract_day: {
    contract_date: string;
    balance_date: string;
    end_date: string;
    special_term_result: Record<string, 'inserted' | 'rejected'>;
  } | null;
};

/** 시연 집 2채 (docs/validation/demo_houses.yaml, 경보 계산 정답표) */
export function getDemoHouses() {
  return request<{ as_of: string; houses: ApiDemoHouse[] }>('/api/demo-houses', { method: 'GET' });
}
