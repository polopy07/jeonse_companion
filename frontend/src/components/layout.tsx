import { router, type Href } from 'expo-router';
import { useEffect, useRef, type ReactNode } from 'react';
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Colors, Gutter, Radius, Touch } from '@/constants/theme';

type ScreenProps = {
  /** 뒤로 버튼이 있는 하위 화면 제목 */
  title?: string;
  /** 하단에 붙는 흰 막대 (고지 문구 + 주 버튼) */
  footer?: ReactNode;
  /** 탭 화면은 하단 안전 영역을 탭 막대가 처리한다 */
  inTabs?: boolean;
  children: ReactNode;
};

/** 키보드가 올라오면 입력 중인 칸이 화면 위쪽에 오게 스크롤할 여백 */
const FOCUS_OFFSET = 120;

/**
 * 키보드가 입력 칸을 가리지 않게 (iOS는 숫자 키패드가 칸을 덮는다).
 * 키보드가 뜨면 입력 중인 칸을 스크롤 영역 위쪽으로 올린다. 안드로이드는 창이 줄어들어 칸이 보이지만 같은 동작을 한다
 */
function useScrollToFocusedInput(scrollRef: React.RefObject<ScrollView | null>) {
  useEffect(() => {
    const sub = Keyboard.addListener('keyboardDidShow', () => {
      const input = TextInput.State.currentlyFocusedInput();
      // getInnerViewRef는 런타임에 있지만 타입 선언에 빠져 있다. 새 아키텍처의 measureLayout은 숫자 핸들이 아니라 ref를 받는다
      const scroll = scrollRef.current as (ScrollView & { getInnerViewRef?: () => View | null }) | null;
      const inner = scroll?.getInnerViewRef?.();
      if (!input || !inner) return;
      input.measureLayout(
        inner,
        (_x, y) => scrollRef.current?.scrollTo({ y: Math.max(0, y - FOCUS_OFFSET), animated: true }),
        () => {},
      );
    });
    return () => sub.remove();
  }, [scrollRef]);
}

/** 모든 화면의 바탕. 바탕색, 안전 영역, 스크롤, 하단 막대, 키보드 피하기를 맡는다. */
export function Screen({ title, footer, inTabs, children }: ScreenProps) {
  const scrollRef = useRef<ScrollView>(null);
  useScrollToFocusedInput(scrollRef);
  return (
    <SafeAreaView style={styles.safe} edges={inTabs || footer ? ['top'] : ['top', 'bottom']}>
      {title ? <ScreenHeader title={title} /> : null}
      {/* iOS: 키보드만큼 줄여 하단 막대(다음 버튼)도 키보드 위로. 안드로이드는 창이 줄어들어 따로 하지 않는다 */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.scroll}
          // 숫자 키패드에는 닫기 키가 없어, 칸 밖을 누르거나 아래로 끌면 키보드를 닫는다
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}>
          {children}
        </ScrollView>
        {footer ? (
          <SafeAreaView edges={['bottom']} style={styles.footer}>
            {footer}
          </SafeAreaView>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function ScreenHeader({ title }: { title: string }) {
  const goBack = () => (router.canGoBack() ? router.back() : router.replace('/'));
  return (
    <View style={styles.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="뒤로" onPress={goBack} style={styles.back}>
        <Icon name="back" />
      </Pressable>
      <AppText size={16} weight="semibold">
        {title}
      </AppText>
    </View>
  );
}

export function Card({ children, style, padding = 16 }: { children: ReactNode; style?: ViewStyle; padding?: number }) {
  return <View style={[styles.card, { padding }, style]}>{children}</View>;
}

/** 확인 못 한 항목 등 판정과 상관없이 보이는 점선 박스 */
export function DashedBox({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.dashed, style]}>{children}</View>;
}

/** 실제 자료가 아닌 시연용 값 표시 (예: "시연용 가상 근저당"). 판정 색은 쓰지 않는다 */
export function DemoTag({ label, style }: { label: string; style?: ViewStyle }) {
  return (
    <View style={[styles.demoTag, style]}>
      <AppText size={11} weight="semibold" color={Colors.textSub}>
        {label}
      </AppText>
    </View>
  );
}

export function SectionLabel({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return (
    <View style={[{ marginTop: 20, marginBottom: 8 }, style]}>
      <AppText size={14} weight="semibold" color={Colors.textSub}>
        {children}
      </AppText>
    </View>
  );
}

type ButtonProps = {
  label: string;
  onPress?: () => void;
  href?: Href;
  variant?: 'primary' | 'outline';
  height?: number;
  icon?: ReactNode;
  style?: ViewStyle;
};

export function Button({ label, onPress, href, variant = 'primary', height = Touch.primary, icon, style }: ButtonProps) {
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      onPress={href ? () => router.push(href) : onPress}
      style={({ pressed }) => [
        styles.button,
        { height, borderRadius: height >= Touch.primary ? Radius.sm : Radius.input },
        primary ? styles.buttonPrimary : styles.buttonOutline,
        pressed && { opacity: 0.8 },
        style,
      ]}>
      {icon}
      <AppText
        size={height >= Touch.primary ? 16 : 14}
        weight="semibold"
        color={primary ? '#FFFFFF' : Colors.primary}>
        {label}
      </AppText>
    </Pressable>
  );
}

/** 여러 단계 화면 위쪽 진행 막대 ("2 / 5 · 현장 확인") */
export function StepProgress({ current, total, label }: { current: number; total: number; label: string }) {
  return (
    <View style={{ marginTop: 8 }}>
      <View style={{ flexDirection: 'row', gap: 4 }}>
        {Array.from({ length: total }, (_, i) => (
          <View
            key={i}
            style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i <= current ? Colors.primary : Colors.inactiveDot }}
          />
        ))}
      </View>
      <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
        {current + 1} / {total} · {label}
      </AppText>
    </View>
  );
}

/** 모든 결과 화면 맨 아래 고지: 조회 시점 + "정보 제공이며 보증하지 않습니다" */
export function Disclaimer({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return (
    <View style={[{ paddingTop: 16 }, style]}>
      <AppText size={11} color={Colors.textHint} leading={1.5}>
        {children}
      </AppText>
    </View>
  );
}

export const styles = StyleSheet.create({
  demoTag: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: Colors.dashed,
    backgroundColor: Colors.muted,
  },
  safe: { flex: 1, backgroundColor: Colors.bg },
  scroll: { flexGrow: 1, paddingHorizontal: Gutter, paddingBottom: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingTop: 12, paddingHorizontal: 8 },
  back: { width: Touch.min, height: Touch.min, alignItems: 'center', justifyContent: 'center' },
  footer: {
    backgroundColor: Colors.card,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    paddingHorizontal: Gutter,
    paddingTop: 16,
    paddingBottom: 20,
  },
  card: {
    backgroundColor: Colors.card,
    borderRadius: Radius.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  dashed: {
    padding: 16,
    borderRadius: Radius.card,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: Colors.dashed,
  },
  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  buttonPrimary: { backgroundColor: Colors.primary },
  buttonOutline: { backgroundColor: Colors.card, borderWidth: 1, borderColor: Colors.inputBorder },
});
