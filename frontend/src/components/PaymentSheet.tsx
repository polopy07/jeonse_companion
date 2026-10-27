import { router } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/layout';
import { Colors, Gutter, MaxAppWidth, Radius } from '@/constants/theme';
import { ApiError, apiEnabled, getCheck, getContract, postPayment } from '@/lib/api';
import { contractToken, setLatestContract } from '@/lib/contract';
import { formatWon } from '@/lib/format';
import { products, setLatestPayment, useLatestPayment } from '@/lib/payment';

type Props = {
  visible: boolean;
  product: keyof typeof products;
  /** 서버에 저장된 판정 id. null이면(앱 안 계산·시연 데이터) 서버를 부르지 않고 넘어간다 */
  checkId: number | null;
  onClose: () => void;
  /** 결제를 확인한 뒤 (다음 화면으로) */
  onPaid: () => void;
};

/**
 * 테스트 결제 확인 창 (FR-013, 결정 자료 결정 5). 판정 결과 화면에서 "패키지 시작"을 누르면 아래에서 올라온다.
 * 금액은 서버가 판정 단계로 정하고(POST /api/checks/{id}/payment), 실제 돈은 나가지 않는다.
 */
export function PaymentSheet({ visible, product, checkId, onClose, onPaid }: Props) {
  const payment = useLatestPayment();
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const p = products[product];
  // 같은 판정에 이미 결제했으면 다시 눌러도 결제 1건 (서버도 앞서 한 결제를 돌려준다)
  const paid = checkId !== null && payment?.check_id === checkId && payment.status === 'paid';
  const amount = paid ? payment.amount : p.amount;

  const close = () => {
    if (paying) return;
    setError(null);
    onClose();
  };

  const confirm = async () => {
    if (paying) return;
    if (!apiEnabled || checkId === null) {
      onPaid();
      return;
    }
    setPaying(true);
    setError(null);
    try {
      setLatestPayment(await postPayment(checkId));
      onPaid();
    } catch (e) {
      // 이미 이 판정으로 계약을 만들었으면 그 계약의 할 일로 간다 (계약 날짜 입력과 같게)
      if (e instanceof ApiError && e.code === 'CHECK_ALREADY_USED') {
        const contractId = await getCheck(checkId)
          .then((c) => c.contract_id)
          .catch(() => null);
        const existing =
          contractId === null ? null : await getContract(contractId, contractToken(contractId)).catch(() => null);
        if (existing) {
          setLatestContract(existing);
          onClose();
          router.push('/todos');
          return;
        }
      }
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '결제를 확인하지 못했어요');
    } finally {
      setPaying(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable accessibilityLabel="닫기" style={styles.backdrop} onPress={close} />
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <AppText size={18} weight="bold">
          {p.label}
        </AppText>
        <View style={styles.amountRow}>
          <AppText size={28} weight="bold">
            {formatWon(amount)}
          </AppText>
          <AppText size={16} weight="semibold">
            원
          </AppText>
        </View>
        <AppText size={13} color={Colors.textSub} leading={1.6}>
          계약 당일부터 만기 후 3개월까지
        </AppText>

        <View style={styles.includes}>
          {p.includes.map((item) => (
            <AppText key={item} size={14} leading={1.6}>
              · {item}
            </AppText>
          ))}
        </View>

        <View style={styles.testNotice}>
          <AppText size={13} weight="semibold" color={Colors.primarySoftText}>
            테스트 결제라 돈이 나가지 않아요
          </AppText>
        </View>

        {error ? (
          <AppText size={13} color={Colors.danger} leading={1.6} style={{ marginTop: 12 }}>
            {error}
          </AppText>
        ) : null}

        <Button
          label={paying ? '확인하는 중…' : paid ? '결제했어요 · 계속하기' : `${formatWon(amount)}원 결제 확인`}
          onPress={confirm}
          style={{ marginTop: 16, opacity: paying ? 0.6 : 1 }}
        />
        <Pressable accessibilityRole="button" onPress={close} style={styles.cancel}>
          <AppText size={14} weight="semibold" color={Colors.textSub}>
            나중에 할게요
          </AppText>
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(23, 32, 42, 0.4)' },
  // 웹에서 넓은 화면으로 열어도 앱 폭에 맞춘다 (_layout.tsx)
  sheet: {
    width: '100%',
    maxWidth: MaxAppWidth,
    alignSelf: 'center',
    backgroundColor: Colors.card,
    borderTopLeftRadius: Radius.lg,
    borderTopRightRadius: Radius.lg,
    paddingHorizontal: Gutter,
    paddingTop: 10,
    paddingBottom: 28,
  },
  grabber: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: Colors.inactiveDot, marginBottom: 16 },
  amountRow: { flexDirection: 'row', alignItems: 'baseline', gap: 2, marginTop: 8 },
  includes: { marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: Colors.divider },
  testNotice: {
    marginTop: 14,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: Radius.input,
    backgroundColor: Colors.primarySoft,
  },
  cancel: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
});
