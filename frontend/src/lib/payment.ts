/**
 * 테스트 결제 (FR-013, API 명세 1.8). 판정 결과 화면의 확인 창에서 결제하고, 계약을 만들 때 payment_id로 보낸다.
 * 결제와 계약 생성 사이에 앱을 다시 켜도 이어지도록 휴대폰에 저장한다.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { ApiPayment } from '@/lib/api';
import { createStore } from '@/lib/store';

const PAYMENT_KEY = 'jeonse.payment';
const RELEASED_KEY = 'jeonse.releasedPayment';

/** 상품 이름과 서버에 연결하지 않았을 때(시연 데이터) 보여 줄 금액. 실제 금액은 서버 응답 amount */
export const products = {
  package: { label: '전동기 패키지', amount: 9_900, includes: ['계약 당일 체크', '2년 맞춤 할 일', '전세 기록함', '계약 중 역전세 경보'] },
  todo_only: { label: '할 일 관리', amount: 4_900, includes: ['2년 맞춤 할 일', '전세 기록함'] },
} as const;

const latestPayment = createStore<ApiPayment | null>(null);
export const useLatestPayment = latestPayment.use;

export function setLatestPayment(p: ApiPayment | null) {
  latestPayment.set(p);
  const save = p ? AsyncStorage.setItem(PAYMENT_KEY, JSON.stringify(p)) : AsyncStorage.removeItem(PAYMENT_KEY);
  save.catch(() => {});
}

export type ProductId = keyof typeof products;

/**
 * 계약 무산으로 풀린 결제 (FR-016). 다음 계약을 만들 때 payment_id와 그 무산된 계약의 접근 토큰을 함께 보내야
 * 다시 쓸 수 있어서(API 명세 1.8), 새 계약이 지금 계약 토큰을 덮어써도 남도록 따로 저장한다 (#98 리뷰 1번)
 */
export type ReleasedPayment = { payment_id: number; product: ProductId; contract_id: number; token: string };

const releasedPayment = createStore<ReleasedPayment | null>(null);
export const useReleasedPayment = releasedPayment.use;

export function setReleasedPayment(p: ReleasedPayment | null) {
  releasedPayment.set(p);
  const save = p ? AsyncStorage.setItem(RELEASED_KEY, JSON.stringify(p)) : AsyncStorage.removeItem(RELEASED_KEY);
  save.catch(() => {});
}

/** 풀린 결제로 이 상품을 시작할 수 있는지 (패키지 결제 → 할 일 관리만도 OK, 반대는 다시 결제. 서버 covers와 같음) */
export function releasedFor(product: ProductId, p: ReleasedPayment | null = releasedPayment.get()): ReleasedPayment | null {
  return p && (p.product === 'package' || product === 'todo_only') ? p : null;
}

/** 이 판정에 한 결제의 id. 없으면 null (계약 생성 때 보내지 않음) */
export function paymentIdFor(checkId: number): number | null {
  const p = latestPayment.get();
  return p && p.check_id === checkId && p.status === 'paid' ? p.payment_id : null;
}

/** 앱을 켤 때 한 번: 저장한 결제·풀린 결제를 불러온다 */
export async function restorePayment(): Promise<void> {
  try {
    const [[, raw], [, rawReleased]] = await AsyncStorage.multiGet([PAYMENT_KEY, RELEASED_KEY]);
    const p = raw ? (JSON.parse(raw) as ApiPayment) : null;
    if (p?.payment_id && !latestPayment.get()) latestPayment.set(p);
    const r = rawReleased ? (JSON.parse(rawReleased) as ReleasedPayment) : null;
    if (r?.payment_id && r.token && !releasedPayment.get()) releasedPayment.set(r);
  } catch {}
}
