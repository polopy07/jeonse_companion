/**
 * 오늘 날짜와 시연용 가상 날짜 (FR-044, API 명세 1.7).
 * 가상 날짜를 정하면 모든 API 요청에 X-Virtual-Today로 붙고(lib/api.ts), 서버가 그날 기준으로 할 일 상태·남은 날을 계산한다.
 * 앱을 다시 켜도 이어지도록 휴대폰에 저장한다.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useMemo } from 'react';

import { createStore } from '@/lib/store';

const VIRTUAL_TODAY_KEY = 'jeonse.virtualToday';

const virtual = createStore<string | null>(null);
/** 가상 날짜 "2026-11-10". 실제 오늘이면 null */
export const useVirtualToday = virtual.use;
export const virtualToday = virtual.get;

/** 가상 날짜를 정한다. null이면 실제 오늘로 */
export function setVirtualToday(day: string | null) {
  virtual.set(day);
  const save = day ? AsyncStorage.setItem(VIRTUAL_TODAY_KEY, day) : AsyncStorage.removeItem(VIRTUAL_TODAY_KEY);
  save.catch(() => {});
}

/** 앱을 켤 때 한 번: 저장한 가상 날짜를 불러온다 (계약을 불러오기 전에) */
export async function restoreVirtualToday(): Promise<void> {
  try {
    const day = await AsyncStorage.getItem(VIRTUAL_TODAY_KEY);
    if (day && /^\d{4}-\d{2}-\d{2}$/.test(day) && virtual.get() === null) virtual.set(day);
  } catch {}
}

/** "2026-11-10" → 그날 0시 (기기 시간대) */
export function parseDateKey(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

const pad = (n: number) => String(n).padStart(2, '0');

/** 날짜 → "2026-11-10" */
export const dateKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** 날짜 → "2026.11.10" */
export const dottedDate = (d: Date) => `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;

/** 오늘 0시 (가상 날짜가 있으면 그날) */
export function todayDate(day: string | null = virtual.get()): Date {
  if (day) return parseDateKey(day);
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/** 화면용 오늘. 가상 날짜가 바뀌면 다시 그린다 */
export function useToday(): Date {
  const day = useVirtualToday();
  return useMemo(() => todayDate(day), [day]);
}

/** "2026-11-10"에 days일을 더한 날 */
export function addDays(s: string, days: number): string {
  const d = parseDateKey(s);
  d.setDate(d.getDate() + days);
  return dateKey(d);
}
