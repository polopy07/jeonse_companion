import type { ReactNode } from 'react';
import { Pressable, StyleSheet, TextInput, View, type KeyboardTypeOptions, type ViewStyle } from 'react-native';

import { AppText } from '@/components/AppText';
import { Colors, Font, Radius, Touch } from '@/constants/theme';

type TextFieldProps = {
  label: string;
  value: string;
  onChange: (v: string) => void;
  /** 입력을 마치고 칸을 벗어날 때 */
  onBlur?: () => void;
  placeholder?: string;
  /** 칸 오른쪽 단위 (만 원, ㎡) */
  suffix?: string;
  /** 칸 아래 작은 안내 (예: "= 1억 4,000만 원") */
  helper?: string;
  keyboardType?: KeyboardTypeOptions;
  /** 주의가 필요한 값이면 테두리를 주의 색으로 */
  warn?: boolean;
  error?: string;
  style?: ViewStyle;
};

export function TextField({ label, value, onChange, onBlur, placeholder, suffix, helper, keyboardType, warn, error, style }: TextFieldProps) {
  return (
    <View style={[{ flex: 1, gap: 4 }, style]}>
      <AppText size={12} color={Colors.textSub}>
        {label}
      </AppText>
      <View
        style={[
          styles.inputBox,
          warn && { borderWidth: 1.5, borderColor: Colors.cautionStrong },
          error && { borderWidth: 1.5, borderColor: Colors.danger },
        ]}>
        <TextInput
          value={value}
          onChangeText={onChange}
          onBlur={onBlur}
          placeholder={placeholder}
          placeholderTextColor="#9C968A"
          keyboardType={keyboardType}
          accessibilityLabel={label}
          style={styles.input}
        />
        {suffix ? (
          <AppText size={14} color={Colors.textSub}>
            {suffix}
          </AppText>
        ) : null}
      </View>
      {error ? (
        <AppText size={12} color={Colors.danger}>
          {error}
        </AppText>
      ) : helper ? (
        <AppText size={12} color={Colors.textHint}>
          {helper}
        </AppText>
      ) : null}
    </View>
  );
}

type Choice<T extends string> = { value: T; label: string };

/** 여러 개 중 하나 고르기 (주택 유형 등). 고른 칩은 주 색으로 채운다 */
export function ChoiceChips<T extends string>({
  label,
  choices,
  value,
  onChange,
}: {
  label?: string;
  choices: Choice<T>[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <View style={{ gap: 6 }}>
      {label ? (
        <AppText size={12} color={Colors.textSub}>
          {label}
        </AppText>
      ) : null}
      <View style={styles.chips} accessibilityRole="radiogroup">
        {choices.map((c) => {
          const on = c.value === value;
          return (
            <Pressable
              key={c.value}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => onChange(c.value)}
              style={[styles.chip, on && { backgroundColor: Colors.primary, borderColor: Colors.primary }]}>
              <AppText size={14} weight={on ? 'semibold' : 'regular'} color={on ? '#FFFFFF' : Colors.text}>
                {c.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      hitSlop={8}
      style={[styles.toggle, { backgroundColor: value ? Colors.primary : Colors.inputBorder }]}>
      <View style={[styles.knob, value ? { right: 3 } : { left: 3 }]} />
    </Pressable>
  );
}

/** 글자 + 오른쪽 스위치 한 줄. 켜면 아래 children을 펼친다 */
export function ToggleRow({
  label,
  sub,
  value,
  onChange,
  children,
  last,
}: {
  label: string;
  sub?: string;
  value: boolean;
  onChange: (v: boolean) => void;
  children?: ReactNode;
  last?: boolean;
}) {
  return (
    <View style={[styles.toggleRow, !last && styles.divider]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: Touch.min }}>
        <View style={{ flex: 1 }}>
          <AppText size={14} weight="semibold">
            {label}
          </AppText>
          {sub ? (
            <AppText size={12} color={Colors.textHint} style={{ marginTop: 2 }}>
              {sub}
            </AppText>
          ) : null}
        </View>
        <Toggle value={value} onChange={onChange} label={label} />
      </View>
      {value && children ? <View style={{ marginTop: 10 }}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  inputBox: {
    height: Touch.min,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  input: { flex: 1, minWidth: 0, height: '100%', fontFamily: Font.regular, fontSize: 15, color: Colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minHeight: Touch.min,
    paddingHorizontal: 14,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  toggle: { width: 48, height: 28, borderRadius: 14 },
  knob: { position: 'absolute', top: 3, width: 22, height: 22, borderRadius: 11, backgroundColor: '#FFFFFF' },
  toggleRow: { paddingVertical: 10 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
});
