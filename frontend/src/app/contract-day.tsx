import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Card, Disclaimer, Screen } from '@/components/layout';
import { useCopy } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { siteChecks, specialTerms } from '@/data/demo';

type Pick = 'in' | 'out';

/** UI-03 계약 당일 체크: 현장 확인 → 특약 예시 → "넣음/거절당함" 기록 (특약 반영 분기) */
export default function ContractDayScreen() {
  const term = specialTerms[0];
  const [pick, setPick] = useState<Pick>('out');
  const { copied, copy } = useCopy(term.text);

  return (
    <Screen
      title="계약 당일 체크"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            특약 예시는 공공 자료를 바탕으로 한 참고 문구이며 법률 자문이 아닙니다.
          </Disclaimer>
          <Button label="다음 · 계약 날짜 입력" href="/todos" />
        </>
      }>
      <View style={{ marginTop: 8 }}>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <View key={i} style={[styles.step, { backgroundColor: i < 4 ? Colors.primary : Colors.inactiveDot }]} />
          ))}
        </View>
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
          4 / 5 · 특약 반영 기록
        </AppText>
      </View>

      <Card style={{ marginTop: 14, paddingVertical: 14, gap: 8, borderRadius: Radius.sm }}>
        {siteChecks.map((c) => (
          <View key={c} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Icon name="check" size={18} color={Colors.ok} strokeWidth={2.2} />
            <AppText size={14}>{c}</AppText>
          </View>
        ))}
      </Card>

      <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
        이 특약, 계약서에 넣었나요?
      </AppText>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        넣었는지에 따라 앞으로 할 일이 달라져요.
      </AppText>

      <Card padding={18} style={{ marginTop: 12, borderRadius: Radius.lg }}>
        <AppText size={15} weight="bold">
          {term.title}
        </AppText>
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
          근저당 있음 항목과 연결
        </AppText>
        <View style={styles.termText}>
          <AppText size={13} leading={1.7}>
            {term.text}
          </AppText>
        </View>
        <Button
          variant="outline"
          height={Touch.min}
          label={copied ? '복사했어요' : '특약 문구 복사'}
          icon={<Icon name={copied ? 'check' : 'copy'} size={16} color={Colors.primary} strokeWidth={2} />}
          onPress={copy}
          style={{ marginTop: 10 }}
        />
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }} accessibilityRole="radiogroup">
          <PickButton label="넣음" selected={pick === 'in'} color={Colors.primary} onPress={() => setPick('in')} />
          <PickButton label="거절당함" selected={pick === 'out'} color={Colors.cautionStrong} onPress={() => setPick('out')} />
        </View>
      </Card>

      {pick === 'out' ? (
        <View style={[styles.result, { backgroundColor: Colors.cautionBg }]}>
          <AppText size={14} weight="bold" color={Colors.caution}>
            할 일이 이렇게 바뀌어요
          </AppText>
          <AppText size={13} color={Colors.cautionText} leading={1.6} style={{ marginTop: 6 }}>
            잔금 당일 설정되는 담보는 잔금일 등기부 재비교로 잡을 수 없어요. 잔금일 당일 전입신고로 대항력을 확보하세요.
          </AppText>
          <View style={{ gap: 6, marginTop: 12 }}>
            <Change tag="앞당김" text="전입신고 · 잔금일 당일 필수" />
            <Change tag="강조" text="잔금일 아침 등기부 재비교" />
          </View>
        </View>
      ) : (
        <View style={[styles.result, { backgroundColor: Colors.primarySoft }]}>
          <AppText size={14} weight="bold" color={Colors.primary}>
            계약 기록에 남겼어요
          </AppText>
          <AppText size={13} color={Colors.primarySoftText} leading={1.6} style={{ marginTop: 6 }}>
            잔금일 아침 등기부 재비교에서 새 담보가 보이면, 이 특약으로 계약을 해제할 수 있다는 안내를 함께 보여 드려요.
          </AppText>
        </View>
      )}
    </Screen>
  );
}

function PickButton({ label, selected, color, onPress }: { label: string; selected: boolean; color: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.pick,
        selected ? { backgroundColor: color, borderColor: color } : { backgroundColor: Colors.card, borderColor: Colors.inputBorder },
      ]}>
      <AppText size={15} weight="bold" color={selected ? '#FFFFFF' : Colors.text}>
        {label}
      </AppText>
    </Pressable>
  );
}

function Change({ tag, text }: { tag: string; text: string }) {
  return (
    <View style={styles.change}>
      <View style={styles.tag}>
        <AppText size={11} weight="bold" color="#FFFFFF">
          {tag}
        </AppText>
      </View>
      <AppText size={13}>{text}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  step: { flex: 1, height: 4, borderRadius: 2 },
  termText: { marginTop: 12, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: Colors.bg, borderRadius: Radius.input },
  pick: { flex: 1, height: Touch.primary, borderRadius: Radius.button, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  result: { marginTop: 12, padding: 16, borderRadius: Radius.card },
  change: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: Colors.card,
    borderRadius: Radius.input,
  },
  tag: { paddingVertical: 2, paddingHorizontal: 6, borderRadius: 4, backgroundColor: Colors.cautionStrong },
});
