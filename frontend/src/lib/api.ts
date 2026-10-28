/**
 * 백엔드 API 호출 (docs/api/API_명세.md, docs/api/openapi.json).
 *
 * 서버 주소는 EXPO_PUBLIC_API_URL (frontend/.env.local). 앱 시연은 휴대폰에서 PC의 서버를 부르므로
 * localhost가 아니라 PC의 내부 IP를 넣는다 (예: http://192.168.0.10:8000). 비워 두면 서버를 부르지 않고
 * 화면이 앱 안 임시 계산·시연 데이터로 동작한다.
 */
import { Platform } from 'react-native';

import type { CheckInput, RegistryLease } from '@/lib/check';
import { virtualToday } from '@/lib/clock';

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

type RawResponse = { ok: boolean; status: number; body: unknown };

/** fetch로 보낸다 (네트워크 실패·시간 초과면 throw) */
async function sendFetch(url: string, init: RequestInit): Promise<RawResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    return { ok: res.ok, status: res.status, body: await res.json().catch(() => null) };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * XMLHttpRequest로 FormData를 보낸다 (휴대폰 파일 업로드).
 * Expo의 fetch는 React Native FormData의 { uri, name, type } 파일을 받지 않고, expo-file-system으로 읽으면
 * Expo Go에서 문서 선택기가 복사한 파일에 읽기 권한이 없다. XMLHttpRequest는 uri를 네이티브에서 직접 읽어 보낸다
 */
function sendXhr(url: string, method: string, form: FormData, headers: Record<string, string>): Promise<RawResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
    xhr.timeout = TIMEOUT_MS;
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {}
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, body });
    };
    xhr.onerror = () => reject(new Error('XMLHttpRequest 네트워크 오류'));
    xhr.ontimeout = () => reject(new Error('XMLHttpRequest 시간 초과'));
    xhr.send(form);
  });
}

async function request<T>(path: string, init: RequestInit, { xhr = false }: { xhr?: boolean } = {}): Promise<T> {
  if (!API_URL) throw new ApiError('API_URL_MISSING', '서버 주소가 설정되지 않았어요');
  const url = `${API_URL}${path}`;
  // 시연 가상 날짜 (FR-044): 서버가 그날을 오늘로 보고 계산한다 (증빙 업로드도 그날 끝낸 것으로)
  const day = virtualToday();
  const headers = { ...(init.headers as Record<string, string> | undefined), ...(day ? { 'X-Virtual-Today': day } : {}) };
  init = { ...init, headers };
  let res: RawResponse;
  try {
    res = xhr ? await sendXhr(url, init.method ?? 'GET', init.body as FormData, headers) : await sendFetch(url, init);
  } catch (e) {
    // 연결 실패의 실제 원인 (Expo 터미널에 찍힌다)
    if (__DEV__) console.warn(`[api] ${init.method ?? 'GET'} ${path} 실패:`, e);
    throw new ApiError(
      'NETWORK_ERROR',
      '서버에 연결하지 못했어요',
      'PC와 휴대폰이 같은 와이파이인지, 서버를 --host 0.0.0.0으로 띄웠는지 확인하세요',
    );
  }
  const body = res.body as { detail?: any } | null;
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

/** 문서 선택기·사진 선택기에서 고른 파일 */
export type PickedFile = { uri: string; name: string; mimeType?: string | null };

/** 고른 파일을 multipart `file` 칸에 넣는다 */
async function appendFile(form: FormData, file: PickedFile, defaultType: string) {
  if (Platform.OS === 'web') {
    const blob = await (await fetch(file.uri)).blob();
    form.append('file', blob, file.name);
  } else {
    // React Native의 FormData는 { uri, name, type }으로 파일을 보낸다 (fetch가 아니라 XMLHttpRequest로, sendXhr 참고)
    form.append('file', { uri: file.uri, name: file.name, type: file.mimeType ?? defaultType } as unknown as Blob);
  }
}

/** 등기부 PDF(부동산정보요약) → 추출 결과. 저장하지 않는다 */
export async function parseRegistry(file: PickedFile) {
  const form = new FormData();
  await appendFile(form, file, 'application/pdf');
  return request<ApiRegistryParseResult>(
    '/api/registry/parse',
    { method: 'POST', body: form },
    { xhr: Platform.OS !== 'web' },
  );
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

/** 계약 전 확인 → 판정 (서버에 저장). 가상 날짜가 있으면 그날 기준 실거래로 비교한다 */
export function postCheck(input: CheckInput) {
  return request<ApiCheckResult>('/api/checks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
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

// ---- POST /api/checks/{id}/payment ----

export type ApiPayment = {
  payment_id: number;
  check_id: number;
  /** package(전동기 패키지 9,900원) / todo_only(다가구·단독 할 일 관리만 4,900원) */
  product: 'package' | 'todo_only';
  /** 원. 판정 단계로 서버가 정한다 */
  amount: number;
  method: 'test';
  status: 'paid' | 'used' | 'released';
};

/**
 * 테스트 결제 (실제 돈은 나가지 않음, API 명세 1.8). 같은 판정에 다시 부르면 앞서 한 결제를 돌려준다.
 * "문제 항목"이면 409 CHECK_BLOCKED, 이미 계약을 만든 판정이면 409 CHECK_ALREADY_USED
 */
export function postPayment(checkId: number) {
  return request<ApiPayment>(`/api/checks/${checkId}/payment`, { method: 'POST' });
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
  /** 테스트 결제 (postPayment). 없거나 이 판정에 쓸 수 없으면 402 PAYMENT_REQUIRED (서버 설정에 따라 없어도 통과) */
  payment_id?: number | null;
  /** 무산된 계약에서 풀린 결제를 payment_id로 다시 쓸 때만: 그 무산된 계약의 access_token (헤더가 아니라 본문) */
  released_contract_token?: string | null;
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
  /** 증빙 사진을 올렸는지 (보기는 GET /api/todos/{id}/evidence) */
  evidence_uploaded: boolean;
  pinned: boolean;
  moved_to_top: boolean;
  sort_order: number;
  /** todo / done 완료 / skipped 나중에 올리기 (완료로 치고 기록함만 빈칸) */
  status: 'todo' | 'done' | 'skipped';
  /** 끝낸 날 (done·skipped). 뒤 할 일의 기준일 */
  done_date: string | null;
  rules_version: string;
  /** 오늘(가상 날짜면 그날) 기준: done 끝냄 / upcoming 시작 전 / in_progress 할 때 / overdue 기한 지남 */
  state: 'done' | 'upcoming' | 'in_progress' | 'overdue';
  /** 기한(재알림은 알림일)까지 남은 날. 지났으면 음수, 기한이 없으면 null */
  days_left: number | null;
};

/** 계약에 기록한 특약 1개의 결과와 분기 (부속표 E, FR-050) */
export type ApiTermEffect = ApiTermOutcome & {
  /** special_terms.yaml id */
  term_id: string;
  label: string;
  result: 'inserted' | 'rejected';
};

export type ApiContract = {
  id: number;
  /** 할 일 상태를 계산한 오늘 (가상 날짜를 보냈으면 그날) */
  today: string;
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
  /** active / cancelled (계약 무산) */
  status: 'active' | 'cancelled';
  /** 이 계약에 쓴 테스트 결제. 결제 없이 만든 계약이면 null */
  payment_id: number | null;
  /** 기록한 특약 결과의 분기: 거절당함이면 위험 안내·맨 위로 올라간 할 일·상담 창구, 넣음이면 기록함 서류 */
  special_term_effects: ApiTermEffect[];
  /** sort_order 순서 */
  todos: ApiTodo[];
};

/** 계약을 만들 때만 오는 응답: 계약 접근 토큰은 이때 한 번만 준다 (휴대폰에 저장해 X-Contract-Token으로 보냄) */
export type ApiContractCreated = ApiContract & { access_token: string };

/** 계약 아래 API에 붙이는 접근 토큰 헤더. 토큰이 없거나 틀리면 서버는 계약이 없을 때와 같은 404를 준다 */
const contractHeaders = (token: string | null): Record<string, string> => (token ? { 'X-Contract-Token': token } : {});

/** 패키지 시작: 계약 생성 + 할 일 9종 생성 */
export function postContract(input: ApiContractInput) {
  return request<ApiContractCreated>('/api/contracts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

/** 계약 정보와 할 일 목록 (앱을 다시 켰을 때 이어 보기). token은 계약을 만들 때 받은 access_token */
export function getContract(contractId: number, token: string | null) {
  return request<ApiContract>(`/api/contracts/${contractId}`, { method: 'GET', headers: contractHeaders(token) });
}

/**
 * 계약 무산 (FR-016). 계약은 cancelled, 쓴 결제는 released로 풀려 다음 계약에 다시 쓴다(그 계약의 토큰과 함께).
 * 할 일은 기록으로 남고 알림은 보내지 않는다. 이미 무산된 계약이면 409 CONTRACT_CANCELLED
 */
export function cancelContract(contractId: number, token: string | null) {
  return request<ApiContract>(`/api/contracts/${contractId}/cancel`, { method: 'POST', headers: contractHeaders(token) });
}

/** PATCH로 바꿀 수 있는 칸. 보낸 칸만 바꾸고, 특약은 보낸 특약만 바꾼다 */
export type ApiContractPatch = Partial<Omit<ApiContractInput, 'check_id' | 'payment_id' | 'released_contract_token'>>;

/**
 * 계약 조건·특약 결과를 바꾸고 할 일을 다시 계산한다 (FR-021, FR-049·050).
 * 무산된 계약이면 409 CONTRACT_CANCELLED, 날짜 순서가 틀리면 422 (아무것도 안 바뀜)
 */
export function patchContract(contractId: number, token: string | null, patch: ApiContractPatch) {
  return request<ApiContract>(`/api/contracts/${contractId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...contractHeaders(token) },
    body: JSON.stringify(patch),
  });
}

// ---- PATCH /api/todos/{id}, POST /api/todos/{id}/evidence ----

/**
 * 할 일 끝내기·되돌리기 (FR-020, FR-029·030). done은 증빙을 올린 할 일만(아니면 409 EVIDENCE_REQUIRED),
 * skipped는 나중에 올리기, todo는 되돌리기. 먼저 끝낼 할 일이 남았으면 409 PREREQUISITE_NOT_DONE,
 * 뒤 할 일을 이미 끝냈으면 409 DEPENDENT_DONE. 끝낸 날로 뒤 기한을 다시 계산해 계약 전체를 돌려준다
 */
export function patchTodo(todoId: number, token: string | null, status: ApiTodo['status']) {
  return request<ApiContract>(`/api/todos/${todoId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...contractHeaders(token) },
    body: JSON.stringify({ status }),
  });
}

/**
 * 증빙 사진 1장을 올려 할 일을 끝낸다 (FR-029, 기록함 FR-031). 나중에 올리기였던 할 일은 끝낸 날 그대로 완료로,
 * 다시 올리면 앞 사진을 바꾼다. 20MB가 넘으면 413 FILE_TOO_LARGE. 끝낼 수 있는 조건은 patchTodo와 같다
 */
export async function uploadEvidence(todoId: number, token: string | null, file: PickedFile) {
  const form = new FormData();
  await appendFile(form, file, 'image/jpeg');
  return request<ApiContract>(
    `/api/todos/${todoId}/evidence`,
    { method: 'POST', headers: contractHeaders(token), body: form },
    { xhr: Platform.OS !== 'web' },
  );
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
