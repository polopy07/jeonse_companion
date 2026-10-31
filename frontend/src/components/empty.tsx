import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button, Card, Screen } from '@/components/layout';
import { Colors, Touch } from '@/constants/theme';
import { setDemoMode } from '@/lib/demo-mode';

/**
 * 계약이 없을 때의 탭 화면 (할 일·기록함·경보). 시연 데이터를 내 계약처럼 보여 주지 않고,
 * 무엇이 생기는지와 시작 버튼, 시연 집으로 둘러보기를 보여 준다
 */
export function EmptyTab({ title, lines }: { title: string; lines: string[] }) {
  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20 }}>
        {title}
      </AppText>
      <Card style={{ marginTop: 16, gap: 8 }}>
        <AppText size={15} weight="semibold">
          아직 계약이 없어요
        </AppText>
        {lines.map((line) => (
          <AppText key={line} size={13} color={Colors.textSub} leading={1.6}>
            · {line}
          </AppText>
        ))}
      </Card>
      <View style={{ gap: 8, marginTop: 16 }}>
        <Button label="계약 전 확인 시작하기 (무료)" href="/precheck" />
        <Button variant="outline" height={Touch.min} label="내 계약 불러오기" href="/load-contract" />
      </View>
      <Pressable accessibilityRole="button" onPress={() => setDemoMode(true)} style={styles.link}>
        <AppText size={13} weight="semibold" color={Colors.textSub}>
          시연 집으로 둘러보기 →
        </AppText>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  link: { minHeight: Touch.min, justifyContent: 'center', marginTop: 4 },
});
