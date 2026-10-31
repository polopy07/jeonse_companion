import { Alert, Platform } from 'react-native';

import { setLatestCheck } from '@/lib/check';
import { setVirtualToday } from '@/lib/clock';
import { setLatestContract } from '@/lib/contract';
import { setDemoMode } from '@/lib/demo-mode';
import { setLatestPayment, setReleasedPayment } from '@/lib/payment';
import { setSiteCheck } from '@/lib/site-check';
import { setSpecialTermResults } from '@/lib/special-terms';

/**
 * 처음부터 다시하기: 이 휴대폰에 저장한 판정·계약(접근 토큰)·결제·현장 확인·특약 결과·시연 날짜를 지운다.
 * 서버의 계약은 그대로라 알림 이메일이 있으면 "내 계약 불러오기"로 다시 불러올 수 있다. 서비스 안내 동의는 남긴다
 */
export function resetLocalData() {
  setLatestContract(null);
  setLatestCheck(null);
  setLatestPayment(null);
  setReleasedPayment(null);
  setSiteCheck(null);
  setSpecialTermResults({});
  setVirtualToday(null);
  setDemoMode(false);
}

/** 확인 창 (웹은 Alert 버튼이 없어 브라우저 confirm) */
export function confirmAction(title: string, message: string, ok: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: '취소', style: 'cancel', onPress: () => resolve(false) },
      { text: ok, style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}

export const RESET_MESSAGE =
  '이 휴대폰에 저장한 계약 전 확인·계약·결제·시연 날짜를 지우고 처음 화면으로 돌아가요. ' +
  '계약은 서버에 남아 있어, 알림 이메일을 넣은 계약이면 "내 계약 불러오기"로 다시 불러올 수 있어요.';
