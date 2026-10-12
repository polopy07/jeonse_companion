import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Disclaimer, Screen } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { recordDocs, siteCheckDemo, type RecordDoc } from '@/data/demo';
import { siteCheckItems, useSiteCheck } from '@/lib/site-check';

/** UI-05 전세 기록함: 평소엔 계약 기록, 비상 모드에선 청구에 빠진 서류만 빨간 칸으로 */
export default function RecordsScreen() {
  const [emergency, setEmergency] = useState(false);
  const missing = recordDocs.filter((d) => d.needForClaim && !d.filled).length;

  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20 }}>
        전세 기록함
      </AppText>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        할 일을 완료할 때 남긴 증빙이 여기 쌓여요
      </AppText>

      <View style={styles.segment} accessibilityRole="tablist">
        <SegmentButton label="평소 · 계약 기록" on={!emergency} onPress={() => setEmergency(false)} />
        <SegmentButton label="비상 · 못 돌려받을 때" on={emergency} danger onPress={() => setEmergency(true)} />
      </View>

      {emergency ? (
        <Pressable onPress={() => router.push('/return')} style={styles.alert}>
          <AppText size={14} weight="bold" color={Colors.dangerDeep}>
            반환보증 청구에 빠진 서류 {missing}개
          </AppText>
          <AppText size={13} color={Colors.dangerText} leading={1.6} style={{ marginTop: 4 }}>
            빨간 칸부터 채우세요. 반환 대응 안내에서 다음 단계를 볼 수 있어요.
          </AppText>
        </Pressable>
      ) : null}

      {!emergency ? <SiteCheckRecord /> : null}

      <View style={styles.grid}>
        {recordDocs.map((d) => (
          <DocSlot key={d.name} doc={d} emergency={emergency} />
        ))}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>반환 확인 후 3개월 동안 보관해요. 주민등록번호는 가리고 올려 주세요.</Disclaimer>
    </Screen>
  );
}

/** 계약 당일 현장 확인 기록 (FR-047). 체크하지 않은 항목은 "확인 안 함"으로 남긴다 */
function SiteCheckRecord() {
  const items = siteCheckItems(useSiteCheck() ?? siteCheckDemo);
  const missed = items.filter((i) => !i.checked);
  return (
    <View style={styles.siteCheck}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <AppText size={13} weight="semibold">
          계약 당일 현장 확인
        </AppText>
        <AppText size={12} weight="semibold" color={missed.length ? Colors.caution : Colors.ok}>
          {items.length}개 중 {items.length - missed.length}개 확인
        </AppText>
      </View>
      {missed.map((m) => (
        <AppText key={m.label} size={12} color={Colors.caution} style={{ marginTop: 4 }}>
          확인 안 함 · {m.label}
        </AppText>
      ))}
    </View>
  );
}

function SegmentButton({ label, on, danger, onPress }: { label: string; on: boolean; danger?: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected: on }}
      onPress={onPress}
      style={[styles.segmentButton, on && { backgroundColor: Colors.card }]}>
      <AppText size={13} weight={on ? 'bold' : 'medium'} color={on ? (danger ? Colors.dangerDeep : Colors.text) : Colors.textSub}>
        {label}
      </AppText>
    </Pressable>
  );
}

function DocSlot({ doc, emergency }: { doc: RecordDoc; emergency: boolean }) {
  const missing = emergency && doc.needForClaim && !doc.filled;
  const dim = emergency && !doc.needForClaim;
  return (
    <View style={[styles.slotBox, dim && { opacity: 0.4 }]}>
      {doc.filled ? (
        <View style={styles.photo}>
          <Icon name="doc" size={22} color="#9C968A" />
        </View>
      ) : (
        <View style={[styles.empty, missing && styles.emptyMissing]}>
          <Icon name="plus" size={20} color={missing ? Colors.danger : '#9C968A'} />
        </View>
      )}
      <AppText size={12} weight="semibold" leading={1.35} style={{ marginTop: 8 }}>
        {doc.name}
      </AppText>
      <AppText
        size={11}
        weight={missing ? 'bold' : 'regular'}
        color={missing ? Colors.danger : Colors.textHint}
        style={{ marginTop: 2 }}>
        {missing ? '청구에 필요' : doc.meta}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  segment: {
    marginTop: 16,
    padding: 4,
    backgroundColor: Colors.muted,
    borderRadius: Radius.button,
    flexDirection: 'row',
    gap: 4,
  },
  segmentButton: { flex: 1, height: 44, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  alert: { marginTop: 12, paddingVertical: 14, paddingHorizontal: 16, backgroundColor: Colors.dangerBg, borderRadius: Radius.sm },
  siteCheck: {
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: Colors.card,
    borderRadius: Radius.item,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  grid: { marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  slotBox: {
    // 3열 격자: (100% - 간격 2개) / 3
    width: '31%',
    flexGrow: 1,
    padding: 8,
    borderRadius: Radius.item,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  photo: { height: 72, borderRadius: 8, backgroundColor: Colors.photo, alignItems: 'center', justifyContent: 'center' },
  empty: {
    height: 72,
    borderRadius: 8,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: Colors.inputBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyMissing: { borderWidth: 2, borderColor: Colors.danger, backgroundColor: Colors.dangerSlot },
});
