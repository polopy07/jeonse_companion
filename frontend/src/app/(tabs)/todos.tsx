import { router } from 'expo-router';
import { Fragment, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Screen } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { today, todos as demoTodos, type Todo } from '@/data/demo';
import { clearContractNotice, todoViews, useContractNotice, useLatestContract } from '@/lib/contract';

/**
 * UI-04 할 일 목록: 세로 타임라인에 오늘 선을 긋고, 완료는 증빙 사진 1장으로.
 * 패키지를 시작해 만든 계약(POST /api/contracts)이 있으면 그 할 일을, 없으면 시연 할 일을 보여 준다.
 */
export default function TodosScreen() {
  const contract = useLatestContract();
  const notice = useContractNotice();
  const [items, setItems] = useState<Todo[]>(contract ? todoViews(contract.todos) : demoTodos);
  // 계약 날짜 입력에서 새 계약을 만들고 돌아오면 그 할 일로 바꾼다 (렌더 중 이전 값과 비교)
  const [shownContract, setShownContract] = useState(contract);
  if (shownContract !== contract) {
    setShownContract(contract);
    setItems(contract ? todoViews(contract.todos) : demoTodos);
  }
  const done = items.filter((t) => t.status === 'done').length;
  const todayLabel = contract ? `${new Date().getMonth() + 1}.${String(new Date().getDate()).padStart(2, '0')}` : today.label;

  // 실제 앱에서는 카메라로 증빙 1장을 찍은 뒤 완료 처리한다. 지금은 완료 상태만 바꾼다.
  const complete = (id: string) =>
    setItems((list) =>
      list.map((t) => (t.id === id ? { ...t, status: 'done', when: `${todayLabel} 완료 · 증빙 1장`, badge: undefined } : t)),
    );

  return (
    <Screen inTabs>
      <View style={styles.top}>
        <AppText size={22} weight="bold">
          할 일
        </AppText>
        <Pressable accessibilityRole="button" style={styles.calendarButton}>
          <Icon name="calendar" size={16} color={Colors.primary} strokeWidth={2} />
          <AppText size={13} weight="semibold" color={Colors.primary}>
            캘린더에 추가
          </AppText>
        </Pressable>
      </View>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        완료 {done} · 남은 일 {items.length - done} · 날짜를 바꾸면 뒤 기한이 같이 움직여요
      </AppText>
      {contract ? (
        // FR-015: 보증금 6천만 원 이하·월세 30만 원 이하면 신고 비대상이라 확정일자를 챙긴다
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
          {contract.report_required ? '임대차 신고 대상 계약이에요' : '임대차 신고 비대상이라 확정일자를 챙겨 드려요'}
        </AppText>
      ) : null}

      {notice ? (
        // 저장한 계약을 불러오지 못함 (토큰이 맞지 않거나 서버에 없는 계약, 404)
        <Pressable accessibilityRole="button" onPress={clearContractNotice} style={styles.notice}>
          <AppText size={13} color={Colors.cautionText} leading={1.6}>
            {notice}
          </AppText>
        </Pressable>
      ) : null}

      <View style={styles.list}>
        <View style={styles.rail} />
        {items.map((t) => (
          <Fragment key={t.id}>
            {t.todayBefore ? <TodayLine label={todayLabel} /> : null}
            <TodoItem todo={t} onComplete={() => complete(t.id)} />
          </Fragment>
        ))}
      </View>
    </Screen>
  );
}

function TodayLine({ label }: { label: string }) {
  return (
    <View style={styles.today}>
      <View style={styles.todayDot} />
      <AppText size={12} weight="bold">
        오늘 {label}
      </AppText>
      <View style={{ flex: 1, height: 1, backgroundColor: Colors.text }} />
    </View>
  );
}

function TodoItem({ todo, onComplete }: { todo: Todo; onComplete: () => void }) {
  const { status } = todo;
  const isDone = status === 'done';
  const isCurrent = status === 'current';
  const isLater = status === 'later';

  const body = (
    <View
      style={[
        styles.item,
        isCurrent && styles.itemCurrent,
        isLater && styles.itemLater,
        isDone && { opacity: 0.7 },
      ]}>
      <View style={styles.dotWrap}>
        {isDone ? (
          <View style={styles.dotDone}>
            <Icon name="check" size={10} color="#FFFFFF" strokeWidth={3} />
          </View>
        ) : isCurrent ? (
          <View style={styles.dotCurrent} />
        ) : (
          <View style={[styles.dotUpcoming, isLater && { backgroundColor: Colors.bg, borderColor: Colors.inputBorder }]} />
        )}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <AppText size={12} color={isLater ? Colors.textHint : Colors.textSub}>
          {todo.when}
        </AppText>
        {todo.dday && !isDone ? (
          <AppText size={12} weight={isCurrent ? 'bold' : 'regular'} color={isCurrent ? Colors.primary : Colors.textSub}>
            {todo.dday}
          </AppText>
        ) : null}
      </View>
      <AppText
        size={isCurrent ? 16 : 15}
        weight={isCurrent ? 'bold' : 'semibold'}
        color={isLater ? Colors.textSub : Colors.text}
        style={[{ marginTop: 2 }, isDone && { textDecorationLine: 'line-through' }]}>
        {todo.title}
      </AppText>
      {todo.badge && !isDone ? (
        <View style={styles.badge}>
          <AppText size={11} weight="bold" color={Colors.caution}>
            {todo.badge}
          </AppText>
        </View>
      ) : null}
      {isCurrent ? (
        <Button
          label="증빙 1장 남기고 완료"
          height={46}
          icon={<Icon name="camera" size={18} color="#FFFFFF" />}
          onPress={onComplete}
          style={{ marginTop: 12 }}
        />
      ) : null}
    </View>
  );

  if (todo.href) {
    const href = todo.href;
    return (
      <Pressable accessibilityRole="button" onPress={() => router.push(href)}>
        {body}
      </Pressable>
    );
  }
  return body;
}

const styles = StyleSheet.create({
  notice: { marginTop: 12, padding: 12, borderRadius: Radius.input, backgroundColor: Colors.cautionBg },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 20 },
  calendarButton: {
    height: 44,
    paddingHorizontal: 12,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  list: { marginTop: 16, gap: 10, paddingLeft: 28 },
  rail: { position: 'absolute', left: 8, top: 6, bottom: 6, width: 2, backgroundColor: Colors.timelineLine },
  today: { flexDirection: 'row', alignItems: 'center', gap: 8, marginVertical: 2 },
  todayDot: { position: 'absolute', left: -24, width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.text },
  item: {
    paddingVertical: 14,
    paddingHorizontal: 16,
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  itemCurrent: { padding: 16, borderWidth: 2, borderColor: Colors.primary },
  itemLater: { backgroundColor: 'transparent', borderWidth: 1.5, borderStyle: 'dashed', borderColor: Colors.inputBorder },
  dotWrap: { position: 'absolute', left: -29, top: 16, width: 18, alignItems: 'center' },
  dotDone: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: Colors.ok,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotCurrent: { width: 18, height: 18, borderRadius: 9, backgroundColor: '#FFFFFF', borderWidth: 3, borderColor: Colors.primary },
  dotUpcoming: {
    width: 12,
    height: 12,
    marginTop: 2,
    borderRadius: 6,
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    borderColor: '#9C968A',
  },
  badge: {
    alignSelf: 'flex-start',
    marginTop: 6,
    paddingVertical: 3,
    paddingHorizontal: 8,
    borderRadius: 4,
    backgroundColor: Colors.cautionBg,
  },
});
