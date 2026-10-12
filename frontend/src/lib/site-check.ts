/**
 * 계약 당일 현장 확인 (FR-047). 앱이 신원·계좌를 직접 확인하지 않고, 사용자가 보고 체크한 결과를 남긴다.
 * 체크하지 않은 항목은 기록함에 "확인 안 함"으로 남긴다.
 */
import { createStore } from '@/lib/store';

export type Attendee = 'owner' | 'agent';

export type SiteCheckState = {
  attendee: Attendee | null;
  /** 계약하러 온 임대인(또는 대리인이 가져온 위임장)의 이름 */
  idName: string;
  idChecked: boolean;
  poaChecked: boolean;
  sealChecked: boolean;
  agentIdChecked: boolean;
  ownerCallChecked: boolean;
  accountHolder: string;
  accountChecked: boolean;
};

export const emptySiteCheck: SiteCheckState = {
  attendee: null,
  idName: '',
  idChecked: false,
  poaChecked: false,
  sealChecked: false,
  agentIdChecked: false,
  ownerCallChecked: false,
  accountHolder: '',
  accountChecked: false,
};

export type SiteCheckItem = { label: string; checked: boolean };

/** 기록함에 남길 항목 목록. 대리인이면 위임 서류 항목이 더해진다 */
export function siteCheckItems(s: SiteCheckState): SiteCheckItem[] {
  const items: SiteCheckItem[] = [
    {
      label: s.attendee === 'agent' ? '위임장의 임대인 이름 = 등기부 소유자' : '임대인 신분증 이름 = 등기부 소유자',
      checked: s.idChecked,
    },
  ];
  if (s.attendee === 'agent') {
    items.push(
      { label: '위임장 (계약 권한·집 주소가 적혀 있음)', checked: s.poaChecked },
      { label: '인감증명서 (위임장 도장과 같음)', checked: s.sealChecked },
      { label: '대리인 신분증', checked: s.agentIdChecked },
      { label: '소유자와 직접 통화해 위임 확인', checked: s.ownerCallChecked },
    );
  }
  items.push({ label: '계약금 계좌 예금주 = 등기부 소유자', checked: s.accountChecked });
  return items;
}

const MASK = /[○●*＊xX]/;

/**
 * 이름 대조. 띄어쓰기는 무시하고, 가린 글자(○, *)는 어떤 글자와도 같다고 본다.
 * 비교할 수 없으면(둘 중 하나가 비었으면) null.
 */
export function nameMatches(a: string | null, b: string | null): boolean | null {
  const x = (a ?? '').replace(/\s/g, '');
  const y = (b ?? '').replace(/\s/g, '');
  if (!x || !y) return null;
  if (x.length !== y.length) return false;
  return [...x].every((ch, i) => ch === y[i] || MASK.test(ch) || MASK.test(y[i]));
}

// 현장 확인 결과. 특약 반영 기록·기록함 화면에서 읽는다
const siteCheck = createStore<SiteCheckState | null>(null);
export const setSiteCheck = siteCheck.set;
export const useSiteCheck = siteCheck.use;
