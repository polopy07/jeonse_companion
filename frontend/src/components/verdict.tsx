import * as Clipboard from 'expo-clipboard';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon, type IconName } from '@/components/Icon';
import { Card, DashedBox } from '@/components/layout';
import { Colors, Radius, Touch } from '@/constants/theme';
import type { MatchedRule, UncheckedItem, VerdictLevel } from '@/lib/check';
import type { ShownTerm } from '@/lib/special-terms';

/** 판정 3단계. 색만으로 구분하지 않고 아이콘과 글자를 같이 쓴다. "안전합니다"는 쓰지 않는다. */
export const verdictStyle: Record<VerdictLevel, { label: string; fg: string; bg: string; icon: IconName }> = {
  na: { label: '대상 아님', fg: Colors.textSub, bg: Colors.muted, icon: 'info' },
  problem: { label: '문제 항목', fg: Colors.danger, bg: Colors.dangerBg, icon: 'stop' },
  check: { label: '확인 필요', fg: Colors.caution, bg: Colors.cautionBg, icon: 'warning' },
  ok: { label: '문제 항목 없음', fg: Colors.ok, bg: Colors.primarySoft, icon: 'check' },
};

/** 내 보증금 비율 구간: 80% 주의 / 90% 경고 / 100% 위험 */
export function ratioBand(ratio: number) {
  if (ratio >= 1) return { label: '위험 구간', color: Colors.danger };
  if (ratio >= 0.9) return { label: '경고 구간', color: '#9A4A07' };
  if (ratio >= 0.8) return { label: '주의 구간', color: Colors.cautionStrong };
  return { label: '80% 미만', color: Colors.ok };
}

export function VerdictBadge({ level }: { level: VerdictLevel }) {
  const v = verdictStyle[level];
  return (
    <View style={[styles.badge, { backgroundColor: v.bg }]}>
      <Icon name={v.icon} size={16} color={v.fg} strokeWidth={2} />
      <AppText size={13} weight="bold" color={v.fg}>
        {v.label}
      </AppText>
    </View>
  );
}

export function VerdictCard({ level, title, summary }: { level: VerdictLevel; title: string; summary: string }) {
  return (
    <Card padding={20} style={{ borderRadius: Radius.lg }}>
      <VerdictBadge level={level} />
      <AppText size={21} weight="bold" leading={1.4} style={{ marginTop: 12 }}>
        {title}
      </AppText>
      <AppText size={14} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
        {summary}
      </AppText>
    </Card>
  );
}

/** 0~120% 막대에 80·90·100% 구간을 칠하고 내 비율을 세로 표시로 찍는다 */
export function RatioGauge({
  ratio,
  isMinimum,
  children,
}: {
  ratio: number;
  /** 등기부를 올리기 전이라 근저당을 0원으로 둔 최소 추정치 */
  isMinimum?: boolean;
  children?: React.ReactNode;
}) {
  const band = ratioBand(ratio);
  const at = (r: number) => `${(r / 1.2) * 100}%` as const;
  return (
    <Card padding={20} style={{ borderRadius: Radius.lg }}>
      <View style={styles.rowBetween}>
        <View>
          <AppText size={14} weight="semibold">
            내 보증금 비율
          </AppText>
          {isMinimum ? (
            <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
              최소 추정치 · 등기부를 올리면 정확해져요
            </AppText>
          ) : null}
        </View>
        <AppText size={30} weight="bold" color={band.color}>
          {Math.round(ratio * 100)}%
        </AppText>
      </View>
      <View style={styles.gauge} accessibilityLabel={`내 보증금 비율 ${Math.round(ratio * 100)}%, ${band.label}`}>
        <View style={styles.gaugeTrack}>
          <View style={{ width: at(0.8), backgroundColor: '#DCE5EE' }} />
          <View style={{ width: at(0.1), backgroundColor: '#F6D9B8' }} />
          <View style={{ width: at(0.1), backgroundColor: '#EFB27A' }} />
          <View style={{ flex: 1, backgroundColor: '#D99A9A' }} />
        </View>
        <View style={[styles.gaugeMarker, { left: at(Math.min(ratio, 1.2)) }]} />
        {[0.8, 0.9, 1].map((r) => (
          <AppText key={r} size={11} color={Colors.textSub} style={[styles.gaugeTick, { left: at(r) }]}>
            {r === 1 ? '100%' : r * 100}
          </AppText>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
        {['80% 주의', '90% 경고', '100% 위험'].map((t) => (
          <AppText key={t} size={12} color={Colors.textSub}>
            {t}
          </AppText>
        ))}
      </View>
      {children}
    </Card>
  );
}

export function MatchedItem({ item, onPress }: { item: MatchedRule; onPress?: () => void }) {
  const v = verdictStyle[item.level];
  return (
    <Pressable onPress={onPress} accessibilityRole={onPress ? 'button' : undefined}>
      <Card>
        <View style={styles.rowBetween}>
          <AppText size={15} weight="semibold">
            {item.label}
          </AppText>
          <AppText size={12} weight="semibold" color={v.fg}>
            {v.label}
          </AppText>
        </View>
        <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
          {item.explanation}
        </AppText>
        {item.specialTerm ? (
          <View style={styles.inset}>
            <AppText size={13} weight="semibold" leading={1.6} style={{ marginBottom: 4 }}>
              계약 당일 넣을 특약 예시
            </AppText>
            <AppText size={13} leading={1.6}>
              {item.specialTerm}
            </AppText>
          </View>
        ) : null}
      </Card>
    </Pressable>
  );
}

export function UncheckedBox({ item }: { item: UncheckedItem }) {
  return (
    <DashedBox>
      <AppText size={15} weight="semibold">
        {item.label}
      </AppText>
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
        {item.guide}
      </AppText>
    </DashedBox>
  );
}

/** 특약 문구 복사 버튼. 누르면 "복사했어요"로 바뀐다 */
export function useCopy(text: string) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await Clipboard.setStringAsync(text);
    setCopied(true);
  };
  return { copied, copy };
}

export function SpecialTermRow({ term }: { term: ShownTerm }) {
  const { copied, copy } = useCopy(term.text);
  return (
    <Card padding={0} style={styles.termRow}>
      <View style={{ flex: 1 }}>
        <AppText size={14} weight="semibold">
          {term.title}
        </AppText>
        <AppText size={12} color={Colors.textHint} style={{ marginTop: 2 }}>
          {copied ? '문구를 복사했어요' : term.link}
        </AppText>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="특약 문구 복사" onPress={copy} style={styles.iconButton}>
        <Icon name={copied ? 'check' : 'copy'} size={18} color={Colors.primary} strokeWidth={2} />
      </Pressable>
    </Card>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 999,
  },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gauge: { height: 40, marginTop: 12 },
  gaugeTrack: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 8,
    height: 12,
    borderRadius: 6,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  gaugeMarker: { position: 'absolute', top: 0, width: 4, height: 28, marginLeft: -2, borderRadius: 2, backgroundColor: Colors.text },
  gaugeTick: { position: 'absolute', top: 26, marginLeft: -8 },
  inset: { marginTop: 12, padding: 12, backgroundColor: Colors.bg, borderRadius: 10 },
  termRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: Radius.sm,
  },
  iconButton: {
    width: Touch.min,
    height: Touch.min,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
