import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField } from '@/components/form';
import { Button, Card, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius, Touch } from '@/constants/theme';
import { ApiError } from '@/lib/api';
import { addDays, dateKey, dottedDate, parseDateKey, setVirtualToday, todayDate, useVirtualToday } from '@/lib/clock';
import { refreshContract, useLatestContract } from '@/lib/contract';
import { isDateText } from '@/lib/format';

type Jump = { day: string; label: string };

/**
 * 가상 날짜 전환 (FR-044, 시연용). 날짜를 정하면 서버가 그날을 오늘로 보고 할 일 상태·남은 날을 다시 계산한다.
 * 계약이 있으면 계약 날짜와 할 일 시작일·알림일로 바로 건너뛸 수 있다.
 */
export default function VirtualDateScreen() {
  const contract = useLatestContract();
  const current = useVirtualToday();
  const today = dateKey(todayDate(current));
  const [text, setText] = useState(today);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 계약 날짜와, 끝나지 않은 할 일마다 시작일(재알림은 알림일, 없으면 기한)
  const jumps: Jump[] = [];
  if (contract) {
    jumps.push({ day: contract.contract_date, label: '계약일' }, { day: contract.balance_date, label: '잔금일' });
    for (const t of contract.todos) {
      const day = t.remind_date ?? t.start_date ?? t.due_date;
      if (day && t.state !== 'done' && t.status !== 'skipped') jumps.push({ day, label: t.title });
    }
    jumps.push({ day: contract.end_date, label: '만기일' });
  }
  const sortedJumps = jumps
    .sort((a, b) => a.day.localeCompare(b.day))
    .filter((j, i, list) => list.findIndex((k) => k.day === j.day && k.label === j.label) === i);

  const apply = async (day: string | null) => {
    setApplying(true);
    setError(null);
    setVirtualToday(day);
    try {
      await refreshContract();
      router.back();
    } catch (e) {
      // 날짜는 바뀌었고 할 일만 못 불러옴. 할 일 탭을 다시 열면 다시 부른다
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '할 일을 다시 불러오지 못했어요');
    } finally {
      setApplying(false);
    }
  };

  const valid = isDateText(text);

  return (
    <Screen
      title="시연 날짜"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            {error ?? '시연용 기능이에요. 날짜를 바꾸면 할 일 상태와 남은 날을 그날 기준으로 다시 계산해요.'}
          </Disclaimer>
          <Button
            label={applying ? '바꾸는 중…' : `${valid ? dottedDate(parseDateKey(text)) : '날짜'}로 바꾸기`}
            onPress={valid && !applying ? () => apply(text) : undefined}
            style={{ opacity: valid && !applying ? 1 : 0.4 }}
          />
          {current ? (
            <Pressable accessibilityRole="button" onPress={() => apply(null)} style={styles.reset}>
              <AppText size={14} weight="semibold" color={Colors.textSub}>
                실제 오늘로 돌아가기
              </AppText>
            </Pressable>
          ) : null}
        </>
      }>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 14 }}>
        {current ? '지금 시연 날짜' : '지금은 실제 오늘'}
      </AppText>
      <AppText size={24} weight="bold" style={{ marginTop: 2 }}>
        {dottedDate(todayDate(current))}
      </AppText>

      <Card style={{ marginTop: 14, gap: 12 }}>
        <TextField
          label="바꿀 날짜"
          value={text}
          onChange={setText}
          placeholder="2026-11-20"
          keyboardType="numbers-and-punctuation"
          error={text && !valid ? 'YYYY-MM-DD 형식으로 입력해 주세요' : undefined}
        />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[
            { label: '+1일', days: 1 },
            { label: '+7일', days: 7 },
            { label: '+30일', days: 30 },
          ].map((s) => (
            <Pressable
              key={s.label}
              accessibilityRole="button"
              onPress={() => setText(addDays(valid ? text : today, s.days))}
              style={styles.step}>
              <AppText size={14} weight="semibold" color={Colors.primary}>
                {s.label}
              </AppText>
            </Pressable>
          ))}
        </View>
      </Card>

      {sortedJumps.length ? (
        <>
          <SectionLabel>계약 날짜로 건너뛰기</SectionLabel>
          <Card padding={0}>
            {sortedJumps.map((j, i) => (
              <Pressable
                key={`${j.day}${j.label}`}
                accessibilityRole="button"
                onPress={() => setText(j.day)}
                style={[styles.jump, i > 0 && { borderTopWidth: 1, borderTopColor: Colors.divider }]}>
                <AppText size={13} color={j.day === text ? Colors.primary : Colors.textSub} style={{ width: 92 }}>
                  {dottedDate(parseDateKey(j.day))}
                </AppText>
                <AppText
                  size={14}
                  weight={j.day === text ? 'semibold' : 'regular'}
                  color={j.day === text ? Colors.primary : Colors.text}
                  style={{ flex: 1 }}>
                  {j.label}
                </AppText>
              </Pressable>
            ))}
          </Card>
        </>
      ) : (
        <AppText size={13} color={Colors.textHint} leading={1.6} style={{ marginTop: 16 }}>
          계약을 만들면 계약 날짜와 할 일 시작일로 바로 건너뛸 수 있어요.
        </AppText>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  step: {
    flex: 1,
    height: Touch.min,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  jump: { minHeight: Touch.min, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10 },
  reset: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
});
