/**
 * 서비스 안내(면책)·개인정보 수집·이용 동의 (NFR-010·011·014, FR-010). 계약 전 확인을 처음 시작할 때 한 번 받고
 * 휴대폰에 저장한다. 안내 내용을 바꾸면 CONSENT_VERSION을 올려 다시 받는다.
 * 서버에는 보내지 않는다 (회원·로그인이 없는 MVP, 결정 자료 결정 1)
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { dateKey } from '@/lib/clock';
import { createStore } from '@/lib/store';

const CONSENT_KEY = 'jeonse.consent';
export const CONSENT_VERSION = '2026-10-28';

export type Consent = { version: string; agreedOn: string };

/** undefined = 아직 휴대폰에서 불러오는 중, null = 동의하지 않음 */
const consent = createStore<Consent | null | undefined>(undefined);
export const useConsent = consent.use;

/** 지금 안내 버전에 동의했는지 */
export const hasConsent = (c: Consent | null | undefined): c is Consent => !!c && c.version === CONSENT_VERSION;

export function agreeConsent() {
  const c: Consent = { version: CONSENT_VERSION, agreedOn: dateKey(new Date()) };
  consent.set(c);
  AsyncStorage.setItem(CONSENT_KEY, JSON.stringify(c)).catch(() => {});
}

/** 동의 철회: 다음에 계약 전 확인을 시작할 때 다시 묻는다 (이미 만든 계약·기록은 기록함·할 일에서 직접 지운다) */
export function withdrawConsent() {
  consent.set(null);
  AsyncStorage.removeItem(CONSENT_KEY).catch(() => {});
}

/** 앱을 켤 때 한 번: 저장한 동의를 불러온다 */
export async function restoreConsent(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(CONSENT_KEY);
    const c = raw ? (JSON.parse(raw) as Consent) : null;
    consent.set(c?.version && c.agreedOn ? c : null);
  } catch {
    consent.set(null);
  }
}
