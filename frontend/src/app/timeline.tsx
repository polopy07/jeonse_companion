import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Disclaimer, Screen } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { house, timeline, type TimelineKind } from '@/data/demo';

const kinds: Record<TimelineKind, { label: string; color: string }> = {
  contract: { label: '계약·점검', color: Colors.primary },
  todo: { label: '할 일 완료', color: Colors.ok },
  alert: { label: '경보·특약', color: Colors.cautionStrong },
};

/** UI-06 계약 타임라인 (정적) */
export default function TimelineScreen() {
  return (
    <Screen title="계약 타임라인">
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        {house.name} · {house.contractDate} ~ {house.endDate}
      </AppText>

      <View style={styles.legend}>
        {Object.values(kinds).map((k) => (
          <View key={k.label} style={styles.chip}>
            <View style={[styles.chipDot, { backgroundColor: k.color }]} />
            <AppText size={12} color={Colors.textSub}>
              {k.label}
            </AppText>
          </View>
        ))}
      </View>

      <View style={styles.list}>
        <View style={styles.rail} />
        {timeline.map((e, i) => (
          <View key={i} style={styles.row}>
            <View style={styles.date}>
              <AppText size={10} color={Colors.textHint}>
                {e.year}
              </AppText>
              <AppText size={12} weight="semibold">
                {e.md}
              </AppText>
            </View>
            <View style={[styles.dot, { backgroundColor: kinds[e.kind].color }]} />
            <View style={styles.event}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <AppText size={14} weight="semibold">
                  {e.title}
                </AppText>
                <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
                  {e.sub}
                </AppText>
              </View>
              {e.photo ? (
                <View style={styles.photo} accessibilityLabel="증빙 사진 있음">
                  <Icon name="camera" size={16} color="#9C968A" />
                </View>
              ) : null}
            </View>
          </View>
        ))}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>이 기록은 반환 확인 후 3개월 동안 보관돼요.</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  legend: { marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipDot: { width: 8, height: 8, borderRadius: 4 },
  list: { marginTop: 16, gap: 4 },
  rail: { position: 'absolute', left: 57, top: 8, bottom: 8, width: 2, backgroundColor: Colors.timelineLine },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  date: { width: 40, alignItems: 'flex-end', paddingTop: 12 },
  dot: { width: 12, height: 12, borderRadius: 6, marginTop: 18, borderWidth: 2, borderColor: Colors.bg },
  event: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: Colors.card,
    borderRadius: Radius.item,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  photo: { width: 36, height: 36, borderRadius: 6, backgroundColor: Colors.photo, alignItems: 'center', justifyContent: 'center' },
});
