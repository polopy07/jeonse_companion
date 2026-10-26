import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Colors, Radius, Touch } from '@/constants/theme';
import type { ApiTermEffect } from '@/lib/api';

/** 특약 "넣음 / 거절당함" 고르기 버튼 (계약 당일 체크, 계약 정보 고치기) */
export function PickButton({ label, selected, color, onPress }: { label: string; selected: boolean; color: string; onPress: () => void }) {
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

/** 특약 결과로 바뀌는 것 한 줄 ("맨 위로", "기록함", "상담") */
export function Change({ tag, text, color = Colors.cautionStrong }: { tag: string; text: string; color?: string }) {
  return (
    <View style={styles.change}>
      <View style={[styles.tag, { backgroundColor: color }]}>
        <AppText size={11} weight="bold" color="#FFFFFF">
          {tag}
        </AppText>
      </View>
      <AppText size={13} style={{ flex: 1 }}>
        {text}
      </AppText>
    </View>
  );
}

/**
 * 계약에 기록한 특약 1개의 결과와 분기 (FR-050, 부속표 E, 계약 응답 special_term_effects).
 * 거절당함이면 위험 안내·맨 위로 올라간 할 일·상담 창구, 넣음이면 기록함에 남길 서류.
 */
export function TermEffectCard({ effect }: { effect: ApiTermEffect }) {
  const rejected = effect.result === 'rejected';
  const text = rejected ? Colors.cautionText : Colors.primarySoftText;
  return (
    <View style={[styles.effect, { backgroundColor: rejected ? Colors.cautionBg : Colors.primarySoft }]}>
      <AppText size={12} weight="bold" color={rejected ? Colors.caution : Colors.primary}>
        {rejected ? '특약 거절당함' : '특약 넣음'}
      </AppText>
      <AppText size={14} weight="bold" style={{ marginTop: 2 }}>
        {effect.label}
      </AppText>
      {effect.warnings.map((w) => (
        <AppText key={w} size={13} color={text} leading={1.6} style={{ marginTop: 6 }}>
          {w}
        </AppText>
      ))}
      {effect.moves_to_top.length || effect.adds_todos.length || effect.documents.length || effect.link_counsel ? (
        <View style={{ gap: 6, marginTop: 10 }}>
          {effect.moves_to_top.map((t) => (
            <Change key={t.id} tag="맨 위로" text={t.title} />
          ))}
          {effect.adds_todos.map((t) => (
            <Change key={t.id} tag="새 할 일" text={t.title} />
          ))}
          {effect.documents.map((d) => (
            <Change key={d} tag="기록함" text={`${d} 올리기`} color={Colors.primary} />
          ))}
          {effect.link_counsel ? <Change tag="상담" text="공공 상담 창구에 미리 물어보세요" /> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  pick: { flex: 1, height: Touch.primary, borderRadius: Radius.button, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  change: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: Colors.card,
    borderRadius: Radius.input,
  },
  tag: { paddingVertical: 2, paddingHorizontal: 6, borderRadius: 4 },
  effect: { padding: 16, borderRadius: Radius.card },
});
