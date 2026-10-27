import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField } from '@/components/form';
import { Button, Card, Disclaimer, Screen } from '@/components/layout';
import { PickButton } from '@/components/term';
import { Colors, Radius } from '@/constants/theme';
import { ApiError, patchContract, type ApiContractPatch } from '@/lib/api';
import { contractToken, setLatestContract, useLatestContract } from '@/lib/contract';
import { dateOrderError, isDateText } from '@/lib/format';
import type { SpecialTermResult } from '@/lib/special-terms';

/**
 * 계약 정보 고치기 (UC-005, FR-021, FR-049·050, PATCH /api/contracts/{id}).
 * 잔금일이 미뤄졌거나 특약 결과가 바뀌면(넣기로 했다가 거절당함 등) 할 일과 순서를 서버가 다시 계산한다.
 */
export default function ContractEditScreen() {
  const contract = useLatestContract();
  const [contractDate, setContractDate] = useState(contract?.contract_date ?? '');
  const [balanceDate, setBalanceDate] = useState(contract?.balance_date ?? '');
  const [endDate, setEndDate] = useState(contract?.end_date ?? '');
  const [terms, setTerms] = useState<Record<string, SpecialTermResult>>(contract?.special_term_result ?? {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!contract) {
    return (
      <Screen title="계약 정보 고치기">
        <AppText size={14} color={Colors.textSub} leading={1.6} style={{ marginTop: 20 }}>
          고칠 계약이 없어요. 계약 당일 체크에서 할 일을 먼저 만들어 주세요.
        </AppText>
      </Screen>
    );
  }

  const cancelled = contract.status === 'cancelled';
  const datesValid = isDateText(contractDate) && isDateText(balanceDate) && isDateText(endDate);
  const orderError = datesValid ? dateOrderError(contractDate, balanceDate, endDate) : null;

  // 바뀐 칸만 보낸다 (서버는 보낸 칸만 바꾼다)
  const patch: ApiContractPatch = {};
  if (contractDate !== contract.contract_date) patch.contract_date = contractDate;
  if (balanceDate !== contract.balance_date) patch.balance_date = balanceDate;
  if (endDate !== contract.end_date) patch.end_date = endDate;
  const changedTerms = Object.fromEntries(
    Object.entries(terms).filter(([id, v]) => contract.special_term_result[id] !== v),
  );
  if (Object.keys(changedTerms).length) patch.special_term_result = changedTerms;
  const changed = Object.keys(patch).length > 0;
  const canSave = !cancelled && datesValid && !orderError && changed && !saving;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      setLatestContract(await patchContract(contract.id, contractToken(contract.id), patch));
      router.back();
    } catch (e) {
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '계약 정보를 바꾸지 못했어요');
    } finally {
      setSaving(false);
    }
  };

  const dateField = (label: string, value: string, onChange: (v: string) => void, helper?: string) => (
    <TextField
      label={label}
      value={value}
      onChange={onChange}
      placeholder="2026-10-20"
      keyboardType="numbers-and-punctuation"
      error={value && !isDateText(value) ? 'YYYY-MM-DD 형식으로 입력해 주세요' : undefined}
      helper={helper}
    />
  );

  return (
    <Screen
      title="계약 정보 고치기"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            {cancelled
              ? '무산된 계약이라 바꿀 수 없어요. 기록은 계속 볼 수 있어요.'
              : (error ?? orderError ?? '바꾸면 뒤 기한과 할 일 순서를 다시 계산해요. 끝낸 할 일은 그대로 남아요.')}
          </Disclaimer>
          <Button
            label={saving ? '다시 계산하는 중…' : '바꾸고 할 일 다시 계산'}
            onPress={canSave ? save : undefined}
            style={{ opacity: canSave ? 1 : 0.4 }}
          />
        </>
      }>
      <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
        계약 날짜
      </AppText>
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
        잔금일이 미뤄졌다면 여기서 바꿔 주세요. 신고·전입·보증 가입 기한이 같이 움직여요.
      </AppText>
      <Card style={{ marginTop: 14, gap: 14 }}>
        {dateField('계약일', contractDate, setContractDate)}
        {dateField('잔금일', balanceDate, setBalanceDate, '잔금을 치르고 이사하는 날')}
        {dateField('만기일', endDate, setEndDate)}
      </Card>

      {contract.special_term_effects.length ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 24 }}>
            특약 결과
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            넣기로 했던 특약이 계약서에서 빠졌다면 &quot;거절당함&quot;으로 바꿔 주세요. 먼저 챙길 할 일이 맨 위로 올라가요.
          </AppText>
          {contract.special_term_effects.map((t) => (
            <Card key={t.term_id} style={{ marginTop: 12, borderRadius: Radius.lg }}>
              <AppText size={15} weight="bold">
                {t.label}
              </AppText>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }} accessibilityRole="radiogroup">
                <PickButton
                  label="넣음"
                  selected={terms[t.term_id] === 'inserted'}
                  color={Colors.primary}
                  onPress={() => setTerms((p) => ({ ...p, [t.term_id]: 'inserted' }))}
                />
                <PickButton
                  label="거절당함"
                  selected={terms[t.term_id] === 'rejected'}
                  color={Colors.cautionStrong}
                  onPress={() => setTerms((p) => ({ ...p, [t.term_id]: 'rejected' }))}
                />
              </View>
            </Card>
          ))}
        </>
      ) : null}
    </Screen>
  );
}
