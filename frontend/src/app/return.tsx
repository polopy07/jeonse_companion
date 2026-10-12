import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { helpDesks, returnSteps } from '@/data/demo';

/** UI-08 반환 대응 안내 (정적). 일반 절차 안내이며 개별 법률 판단이 아니다 */
export default function ReturnScreen() {
  return (
    <Screen title="반환 대응 안내">
      <View style={styles.hero}>
        <AppText size={12} weight="semibold" color={Colors.dangerDeep}>
          2028.11.19 만기 · 보증금 못 받음
        </AppText>
        <AppText size={19} weight="bold" color={Colors.dangerText} leading={1.4} style={{ marginTop: 6 }}>
          아직 이사 가지 마세요. 순서대로 함께 챙길게요.
        </AppText>
      </View>

      <View style={{ marginTop: 18, gap: 8 }}>
        {returnSteps.map((s, i) => {
          const current = s.state === 'current';
          const done = s.state === 'done';
          return (
            <View key={s.title} style={[styles.step, current && styles.stepCurrent, done && { opacity: 0.7 }]}>
              <View
                style={[
                  styles.num,
                  done && { backgroundColor: Colors.ok },
                  current && { backgroundColor: Colors.primary },
                  !done && !current && styles.numTodo,
                ]}>
                {done ? (
                  <Icon name="check" size={14} color="#FFFFFF" strokeWidth={2.5} />
                ) : (
                  <AppText size={13} weight="bold" color={current ? '#FFFFFF' : Colors.textSub}>
                    {i + 1}
                  </AppText>
                )}
              </View>
              <View style={{ flex: 1 }}>
                <AppText size={15} weight={current ? 'bold' : 'semibold'}>
                  {s.title}
                </AppText>
                <AppText
                  size={done ? 12 : 13}
                  color={Colors.textSub}
                  leading={done ? undefined : 1.6}
                  style={{ marginTop: done ? 2 : 4 }}>
                  {s.body}
                </AppText>
                {current ? (
                  <Pressable style={styles.smallButton} onPress={() => router.push('/records')}>
                    <AppText size={13} weight="semibold" color="#FFFFFF">
                      보낸 뒤 사본 올리기
                    </AppText>
                  </Pressable>
                ) : null}
              </View>
            </View>
          );
        })}
      </View>

      <Card style={{ marginTop: 18 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <AppText size={14} weight="bold">
            청구 서류 대조
          </AppText>
          <AppText size={13} weight="bold" color={Colors.danger}>
            6개 중 1개 빠짐
          </AppText>
        </View>
        <View style={styles.progress}>
          <View style={{ width: '83%', height: 8, backgroundColor: Colors.ok }} />
        </View>
        <AppText size={13} color={Colors.textSub} style={{ marginTop: 10 }}>
          빠진 서류:{' '}
          <AppText size={13} weight="bold" color={Colors.danger}>
            내용증명 사본
          </AppText>
        </AppText>
        <Pressable onPress={() => router.push('/records')} style={{ minHeight: 44, justifyContent: 'center' }}>
          <AppText size={13} weight="semibold" color={Colors.primary}>
            비상 서류함 열기 →
          </AppText>
        </Pressable>
      </Card>

      <SectionLabel>상담 창구</SectionLabel>
      <View style={styles.links}>
        {helpDesks.map((h, i) => (
          <Pressable
            key={h.url}
            accessibilityRole="link"
            onPress={() => WebBrowser.openBrowserAsync(h.url)}
            style={[styles.link, i < helpDesks.length - 1 && styles.divider]}>
            <AppText size={14}>{h.label}</AppText>
            <AppText size={14} color={Colors.textHint}>
              ↗
            </AppText>
          </Pressable>
        ))}
      </View>

      <View style={{ flex: 1 }} />
      <Disclaimer>일반 절차 안내이며 개별 법률 판단이 아닙니다.</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { marginTop: 8, padding: 18, backgroundColor: Colors.dangerBg, borderRadius: Radius.card },
  step: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  stepCurrent: { padding: 16, borderWidth: 2, borderColor: Colors.primary },
  num: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  numTodo: { borderWidth: 2, borderColor: Colors.inputBorder },
  smallButton: {
    alignSelf: 'flex-start',
    marginTop: 10,
    height: 44,
    paddingHorizontal: 14,
    borderRadius: Radius.input,
    backgroundColor: Colors.primary,
    justifyContent: 'center',
  },
  progress: { height: 8, borderRadius: 4, backgroundColor: Colors.track, marginTop: 10, overflow: 'hidden' },
  links: {
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  link: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 48, paddingHorizontal: 16 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
});
