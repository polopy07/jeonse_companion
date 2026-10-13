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
};

/** 계약 전 확인 → 판정 (서버에 저장). virtualToday는 시연 가상 날짜 (YYYY-MM-DD) */
export function postCheck(input: CheckInput, virtualToday?: string) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (virtualToday) headers['X-Virtual-Today'] = virtualToday;
  return request<ApiCheckResult>('/api/checks', { method: 'POST', headers, body: JSON.stringify(input) });
}
