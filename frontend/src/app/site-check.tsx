import { router } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ChoiceChips, TextField } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, Disclaimer, Screen, SectionLabel, StepProgress } from '@/components/layout';
import { Colors, Radius, Touch } from '@/constants/theme';
import { checkResult } from '@/data/demo';
import { useLatestCheck } from '@/lib/check';
import { emptySiteCheck, nameMatches, setSiteCheck, siteCheckItems, useSiteCheck, type SiteCheckState } from '@/lib/site-check';

/** UI-03 계약 당일 체크 2/5 · 현장 확인 (FR-047). 소유자 본인인지, 대리인이면 위임 서류, 계약금 계좌 예금주 */
export default function SiteCheckScreen() {
  const owner = (useLatestCheck() ?? checkResult).owner;
  const saved = useSiteCheck();
  const [s, setS] = useState<SiteCheckState>(saved ?? emptySiteCheck);
  const set = (patch: Partial<SiteCheckState>) => setS((prev) => ({ ...prev, ...patch }));

  const idMatch = nameMatches(owner, s.idName);
  const accountMatch = nameMatches(owner, s.accountHolder);
  const items = siteCheckItems(s);
  const unchecked = items.filter((i) => !i.checked).length;
  const agent = s.attendee === 'agent';

  const next = () => {
    setSiteCheck(s);
    router.push('/contract-day');
  };

  return (
    <Screen
      title="계약 당일 체크"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            앱은 신분증·계좌를 직접 확인하지 않아요.{' '}
            {s.attendee && unchecked
              ? `체크하지 않은 ${unchecked}개는 기록함에 "확인 안 함"으로 남아요.`
              : '눈으로 보고 체크한 결과를 기록함에 남겨요.'}
          </Disclaimer>
          <Button
            label="다음 · 특약 반영 기록"
            onPress={s.attendee ? next : undefined}
            style={{ opacity: s.attendee ? 1 : 0.4 }}
          />
        </>
      }>
      <StepProgress current={1} total={5} label="현장 확인" />

      <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
        계약서 쓰기 전에 확인하세요
      </AppText>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        모든 항목은 직접 보고 체크하세요.
      </AppText>

      <Card style={{ marginTop: 14 }}>
        <AppText size={12} color={Colors.textSub}>
          등기부상 소유자
        </AppText>
        <AppText size={20} weight="bold" style={{ marginTop: 2 }}>
          {owner ?? '등기부를 올리지 않았어요'}
        </AppText>
        {!owner ? (
          <AppText size={12} color={Colors.caution} leading={1.6} style={{ marginTop: 4 }}>
            계약 당일 등기부를 떼어 소유자 이름을 먼저 확인하세요.
          </AppText>
        ) : null}
      </Card>

      <SectionLabel>계약하러 온 사람</SectionLabel>
      <ChoiceChips
        choices={[
          { value: 'owner', label: '소유자 본인' },
          { value: 'agent', label: '대리인' },
        ]}
        value={s.attendee}
        onChange={(attendee) => set({ attendee, idChecked: false })}
      />

      {s.attendee ? (
        <Card style={{ marginTop: 12, gap: 12 }}>
          <TextField
            label={agent ? '위임장에 적힌 임대인 이름' : '임대인 신분증 이름'}
            value={s.idName}
            onChange={(idName) => set({ idName })}
            placeholder="보이는 대로 입력"
            error={idMatch === false ? '등기부 소유자와 이름이 달라요' : undefined}
            helper={idMatch ? '등기부 소유자와 같아요' : undefined}
          />
          <CheckItem
            label={agent ? '위임장의 임대인 이름이 등기부 소유자와 같아요' : '신분증 이름·얼굴을 보고 등기부 소유자와 같은지 확인했어요'}
            checked={s.idChecked}
            onChange={(idChecked) => set({ idChecked })}
          />
        </Card>
      ) : null}

      {idMatch === false ? (
        <Warning title="계약을 멈추세요">
          등기부 소유자가 아닌 사람과 계약하면 보증금을 지킬 수 없어요. 소유자 본인이나 정식 위임을 받은 대리인인지 다시
          확인하세요.
        </Warning>
      ) : null}

      {agent ? (
        <>
          <Warning title="대리인 계약은 서류를 꼭 확인하세요" tone="caution">
            위임장과 인감증명서가 없거나 소유자와 연락이 안 되면 계약하지 마세요.
          </Warning>
          <Card style={{ marginTop: 12, gap: 4 }}>
            <CheckItem
              label="위임장"
              sub="계약 권한과 이 집 주소가 적혀 있어요"
              checked={s.poaChecked}
              onChange={(poaChecked) => set({ poaChecked })}
            />
            <CheckItem
              label="인감증명서"
              sub="위임장에 찍힌 도장과 같아요 · 발급 3개월 이내"
              checked={s.sealChecked}
              onChange={(sealChecked) => set({ sealChecked })}
            />
            <CheckItem
              label="대리인 신분증"
              sub="위임장에 적힌 대리인 이름과 같아요"
              checked={s.agentIdChecked}
              onChange={(agentIdChecked) => set({ agentIdChecked })}
            />
            <CheckItem
              label="소유자와 직접 통화"
              sub="위임한 게 맞는지 소유자에게 확인했어요"
              checked={s.ownerCallChecked}
              onChange={(ownerCallChecked) => set({ ownerCallChecked })}
            />
          </Card>
        </>
      ) : null}

      <SectionLabel>계약금 받을 계좌</SectionLabel>
      <Card style={{ gap: 12 }}>
        <TextField
          label="예금주"
          value={s.accountHolder}
          onChange={(accountHolder) => set({ accountHolder })}
          placeholder="이체 화면에 나온 이름"
          error={accountMatch === false ? '등기부 소유자와 예금주가 달라요' : undefined}
          helper={accountMatch ? '등기부 소유자와 같아요' : '이체 전 받는 사람 이름을 확인하세요'}
        />
        <CheckItem
          label="예금주가 등기부 소유자와 같아요"
          checked={s.accountChecked}
          onChange={(accountChecked) => set({ accountChecked })}
        />
      </Card>

      {accountMatch === false ? (
        <Warning title="이 계좌로 보내지 마세요">
          계약금·잔금은 등기부 소유자 명의 계좌로 보내야 해요. 대리인이나 중개사 계좌로 보내 달라고 하면 이유를 묻고, 소유자
          명의 계좌를 요청하세요.
        </Warning>
      ) : null}
    </Screen>
  );
}

function CheckItem({
  label,
  sub,
  checked,
  onChange,
}: {
  label: string;
  sub?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      style={styles.checkItem}>
      <View style={[styles.box, checked && { backgroundColor: Colors.ok, borderColor: Colors.ok }]}>
        {checked ? <Icon name="check" size={16} color="#FFFFFF" strokeWidth={2.6} /> : null}
      </View>
      <View style={{ flex: 1 }}>
        <AppText size={14} weight={checked ? 'semibold' : 'regular'} leading={1.45}>
          {label}
        </AppText>
        {sub ? (
          <AppText size={12} color={Colors.textHint} style={{ marginTop: 2 }}>
            {sub}
          </AppText>
        ) : null}
      </View>
    </Pressable>
  );
}

function Warning({ title, tone = 'danger', children }: { title: string; tone?: 'danger' | 'caution'; children: ReactNode }) {
  const danger = tone === 'danger';
  return (
    <View style={[styles.warning, { backgroundColor: danger ? Colors.dangerBg : Colors.cautionBg }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Icon name={danger ? 'stop' : 'warning'} size={16} color={danger ? Colors.dangerDeep : Colors.caution} strokeWidth={2} />
        <AppText size={14} weight="bold" color={danger ? Colors.dangerDeep : Colors.caution}>
          {title}
        </AppText>
      </View>
      <AppText size={13} color={danger ? Colors.dangerText : Colors.cautionText} leading={1.6} style={{ marginTop: 4 }}>
        {children}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  checkItem: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: Touch.min, paddingVertical: 6 },
  box: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  warning: { marginTop: 12, padding: 16, borderRadius: Radius.card },
});
