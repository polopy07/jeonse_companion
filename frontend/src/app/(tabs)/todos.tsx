import { router } from 'expo-router';
import { Fragment, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { EmptyTab } from '@/components/empty';
import { Icon } from '@/components/Icon';
import { Button, Disclaimer, Screen } from '@/components/layout';
import { TermEffectCard } from '@/components/term';
import { Colors, Radius } from '@/constants/theme';
import { today, todos as demoTodos } from '@/data/demo';
import { ApiError, MOVE_IN_BEFORE_RETURN, patchTodo, uploadEvidence, type ApiContract, type PickedFile } from '@/lib/api';
import { useLatestCheck } from '@/lib/check';
import { useToday } from '@/lib/clock';
import {
  clearContractNotice,
  contractToken,
  setLatestContract,
  switchHouse,
  todoViews,
  useContractNotice,
  useLatestContract,
  useOtherHouse,
  type TodoView,
} from '@/lib/contract';
import { pickEvidence, type EvidenceSource } from '@/lib/evidence';
import { exportIcs, icsEventCount } from '@/lib/ics';
import { useReleasedPayment } from '@/lib/payment';
import { useDemoMode } from '@/lib/demo-mode';

/** 할 일 하나에 대한 동작 (계약이 있을 때만) */
type TodoActions = {
  /** 증빙 사진을 골라 올려 끝낸다. 증빙이 없는 할 일은 바로 끝낸다 */
  complete: (source: EvidenceSource) => void;
  /** 나중에 올리기: 완료로 치고 기록함만 빈칸 (FR-030) */
  skip: () => void;
  /** 끝낸 할 일 되돌리기 */
  reopen: () => void;
  busy: boolean;
  error: string | null;
  /** 다음 집 전입신고를 지금 집 반환 확인 전에 끝내려 할 때 경고 (409 MOVE_IN_BEFORE_RETURN, FR-027). 누르면 그래도 끝낸다 */
  confirmMoveIn: (() => void) | null;
};

/** 서버를 부르는 동작. confirmMoveIn이면 전입 경고를 보고 그래도 끝내는 것 */
type TodoCall = (token: string | null, confirmMoveIn: boolean) => Promise<ApiContract | null>;

/**
 * UI-04 할 일 목록: 세로 타임라인에 오늘 선을 긋고, 완료는 증빙 사진 1장으로.
 * 패키지를 시작해 만든 계약(POST /api/contracts)이 있으면 그 할 일을, 없으면 시연 할 일을 보여 준다.
 * 계약의 할 일은 서버에서 끝내고(PATCH /api/todos/{id}, 증빙은 POST /api/todos/{id}/evidence) 돌아온 계약으로 다시 그린다.
 */
export default function TodosScreen() {
  const contract = useLatestContract();
  const released = useReleasedPayment();
  const notice = useContractNotice();
  const now = useToday();
  const check = useLatestCheck();
  const [calendarMessage, setCalendarMessage] = useState<string | null>(null);
  const [demoItems, setDemoItems] = useState<TodoView[]>(demoTodos);
  const items = contract ? todoViews(contract.todos, now) : demoItems;
  const [busyId, setBusyId] = useState<number | null>(null);
  const [failed, setFailed] = useState<{ todoId: number; message: string; retry: (() => void) | null } | null>(null);
  const other = useOtherHouse();
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const demo = useDemoMode();

  // 갈아타기 중 두 집 오가기 (지금 집 9번 반환 확인은 지금 집에서, 다음 집 할 일은 다음 집에서)
  const toggleHouse = async () => {
    if (switching) return;
    setSwitching(true);
    setSwitchError(null);
    try {
      await switchHouse();
    } catch (e) {
      setSwitchError(e instanceof ApiError ? e.message : '다른 집 계약을 불러오지 못했어요');
    } finally {
      setSwitching(false);
    }
  };
  const done = items.filter((t) => t.status === 'done').length;
  const todayLabel = contract ? `${now.getMonth() + 1}.${String(now.getDate()).padStart(2, '0')}` : today.label;

  // FR-042: 끝나지 않은 할 일 기한을 ICS로 (휴대폰은 공유 창 → 캘린더 앱, 웹은 내려받기)
  const addToCalendar = async () => {
    if (!contract) {
      setCalendarMessage('계약을 만들면 할 일 기한을 캘린더에 넣을 수 있어요');
      return;
    }
    if (!icsEventCount(contract)) {
      setCalendarMessage('캘린더에 넣을 남은 할 일이 없어요');
      return;
    }
    try {
      await exportIcs(contract, check && check.id === contract.check_id ? check.houseLabel : null);
      setCalendarMessage(null);
    } catch (e) {
      setCalendarMessage(e instanceof Error ? e.message : '캘린더 파일을 만들지 못했어요');
    }
  };

  // 시연 할 일(계약 없음)은 앱 안에서 완료 상태만 바꾼다
  const completeDemo = (id: string) =>
    setDemoItems((list) =>
      list.map((t) => (t.id === id ? { ...t, status: 'done', when: `${todayLabel} 완료 · 증빙 1장`, badge: undefined } : t)),
    );

  // 서버에서 바꾸고 돌아온 계약(뒤 기한 재계산 포함)으로 다시 그린다. 실패하면 그 할 일 아래에 이유를 보여 준다
  // 전입 경고(409 MOVE_IN_BEFORE_RETURN)면 경고를 보여 주고, "그래도 끝내기"는 같은 동작을 confirm_move_in으로 다시 보낸다
  const run = async (todoId: number, call: TodoCall, confirmMoveIn = false) => {
    if (!contract || busyId !== null) return;
    setBusyId(todoId);
    setFailed(null);
    try {
      const updated = await call(contractToken(contract.id), confirmMoveIn);
      if (updated) setLatestContract(updated);
    } catch (e) {
      const message =
        e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : e instanceof Error ? e.message : '';
      const moveIn = e instanceof ApiError && e.code === MOVE_IN_BEFORE_RETURN;
      setFailed({
        todoId,
        message: message || '할 일을 바꾸지 못했어요',
        retry: moveIn ? () => run(todoId, call, true) : null,
      });
    } finally {
      setBusyId(null);
    }
  };

  const actionsFor = (t: TodoView): TodoActions | undefined => {
    const id = t.todoId;
    if (!contract || contract.status === 'cancelled' || id === undefined) return undefined;
    return {
      complete: (source) => {
        // 전입 경고 뒤 "그래도 끝내기"는 고른 사진을 다시 고르지 않고 그대로 보낸다
        let file: PickedFile | null = null;
        run(id, async (token, confirm) => {
          if (!t.evidence) return patchTodo(id, token, 'done', confirm);
          file ??= await pickEvidence(source);
          return file ? uploadEvidence(id, token, file, confirm) : null;
        });
      },
      skip: () => run(id, (token, confirm) => patchTodo(id, token, 'skipped', confirm)),
      reopen: () => run(id, (token) => patchTodo(id, token, 'todo')),
      busy: busyId === id,
      error: failed?.todoId === id ? failed.message : null,
      confirmMoveIn: failed?.todoId === id ? failed.retry : null,
    };
  };

  if (!contract && !demo) {
    return (
      <EmptyTab
        title="할 일"
        lines={['계약 날짜(계약일·잔금일·만기일)로 2년 동안 할 일 9종이 기한 순서대로 생겨요', '계약 당일 체크에서 날짜를 넣고 패키지를 시작하면 여기에 보여요']}
      />
    );
  }

  return (
    <Screen inTabs>
      <View style={styles.top}>
        <AppText size={22} weight="bold">
          할 일
        </AppText>
        <Pressable accessibilityRole="button" onPress={addToCalendar} style={styles.calendarButton}>
          <Icon name="calendar" size={16} color={Colors.primary} strokeWidth={2} />
          <AppText size={13} weight="semibold" color={Colors.primary}>
            캘린더에 추가
          </AppText>
        </Pressable>
      </View>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
        완료 {done} · 남은 일 {items.length - done} · 날짜를 바꾸면 뒤 기한이 같이 움직여요
      </AppText>
      {calendarMessage ? (
        <AppText size={12} color={Colors.caution} style={{ marginTop: 2 }}>
          {calendarMessage}
        </AppText>
      ) : null}
      {contract ? (
        // FR-015: 보증금 6천만 원 이하·월세 30만 원 이하면 신고 비대상이라 확정일자를 챙긴다
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
          {contract.report_required ? '임대차 신고 대상 계약이에요' : '임대차 신고 비대상이라 확정일자를 챙겨 드려요'}
        </AppText>
      ) : null}

      {contract && other ? (
        // FR-025·027: 갈아타기 중 두 집 (지금 집 9번 반환 확인 → 다음 집 전입신고 순서)
        <View style={styles.house}>
          <AppText size={13} weight="semibold">
            {other.role === 'current' ? '다음 집 계약을 보고 있어요' : '지금 집 계약을 보고 있어요'}
          </AppText>
          <TextAction
            label={switching ? '불러오는 중…' : other.role === 'current' ? '지금 집 할 일 보기' : '다음 집 할 일 보기'}
            onPress={toggleHouse}
          />
        </View>
      ) : null}
      {switchError ? (
        <AppText size={12} color={Colors.caution} style={{ marginTop: 4 }}>
          {switchError}
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

      {contract?.status === 'cancelled' ? (
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
          무산된 계약이에요. 할 일은 기록으로만 남고 알림은 보내지 않아요.
          {released ? ' 다음 집은 계약 전 확인부터 다시 하면 이 계약의 결제를 그대로 써요' : ''}
        </AppText>
      ) : contract ? (
        // FR-021·049·050: 잔금일이 미뤄지거나 특약 결과가 바뀌면 할 일을 다시 계산한다
        <Button
          variant="outline"
          height={44}
          label="계약 날짜·특약 결과 고치기"
          onPress={() => router.push('/contract-edit')}
          style={{ marginTop: 12 }}
        />
      ) : null}

      {contract && contract.status !== 'cancelled' ? (
        // FR-048·023: 계약 당일(점검한 날과 계약일이 다를 때)·잔금일 아침(3번 할 일) 등기부 재비교
        <Button
          variant="outline"
          height={44}
          label="등기부 다시 비교 (계약 당일·잔금일)"
          onPress={() => router.push('/registry-compare')}
          style={{ marginTop: 8 }}
        />
      ) : null}

      {contract && contract.status !== 'cancelled' && contract.documents.some((d) => !d.uploaded) ? (
        // FR-051: 계약 당일 첫 계약 서류(계약서·계약금 이체 내역)는 할 일과 별개로 기록함에 올린다
        <Button
          variant="outline"
          height={44}
          label={`계약 당일 서류 올리기 (${contract.documents.filter((d) => d.uploaded).length}/${contract.documents.length})`}
          onPress={() => router.push('/records')}
          style={{ marginTop: 8 }}
        />
      ) : null}

      {contract?.special_term_effects.length ? (
        // FR-050: 특약 결과별 안내 (거절당함 → 위험 안내·맨 위 할 일·상담, 넣음 → 기록함 서류)
        <View style={{ marginTop: 12, gap: 8 }}>
          {contract.special_term_effects.map((e) => (
            <TermEffectCard key={e.term_id} effect={e} />
          ))}
        </View>
      ) : null}

      <View style={styles.list}>
        <View style={styles.rail} />
        {items.map((t) => (
          <Fragment key={t.id}>
            {t.todayBefore ? <TodayLine label={todayLabel} /> : null}
            <TodoItem todo={t} actions={actionsFor(t)} onCompleteDemo={() => completeDemo(t.id)} />
          </Fragment>
        ))}
      </View>
      {/* NFR-008: 알림은 보조 수단 고지 */}
      <Disclaimer>알림·캘린더는 보조 수단이에요. 기한은 이 목록과 보증기관 안내를 함께 확인하세요.</Disclaimer>
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

function TodoItem({
  todo,
  actions,
  onCompleteDemo,
}: {
  todo: TodoView;
  actions?: TodoActions;
  onCompleteDemo: () => void;
}) {
  const { status } = todo;
  const isDone = status === 'done';
  const isCurrent = status === 'current';
  const isLater = status === 'later';
  const needsPhoto = !actions || !!todo.evidence;

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
        <>
          <Button
            label={actions?.busy ? '올리는 중…' : needsPhoto ? '증빙 1장 남기고 완료' : '완료'}
            height={46}
            icon={needsPhoto ? <Icon name="camera" size={18} color="#FFFFFF" /> : undefined}
            onPress={actions ? () => actions.complete('camera') : onCompleteDemo}
            style={{ marginTop: 12, opacity: actions?.busy ? 0.6 : 1 }}
          />
          {actions && todo.evidence ? (
            // FR-029·030: 찍기 어려우면 앨범에서, 지금 증빙이 없으면 나중에 올리기
            <View style={styles.subActions}>
              <TextAction label="앨범에서 고르기" onPress={() => actions.complete('library')} />
              <TextAction label="나중에 올리기" onPress={actions.skip} />
            </View>
          ) : null}
          {actions && todo.evidence ? (
            <AppText size={12} color={Colors.textSub} style={{ marginTop: 4 }}>
              증빙: {todo.evidence}
            </AppText>
          ) : null}
        </>
      ) : null}
      {isDone && actions ? (
        <View style={styles.subActions}>
          {todo.skipped && todo.evidence ? (
            <TextAction label="증빙 올리기" onPress={() => actions.complete('library')} />
          ) : null}
          {/* 계약 조건이 바뀌어 기록으로만 남은 할 일은 되돌리면 서버가 409 TODO_NOT_PLANNED (#135) */}
          {todo.archived ? (
            <AppText size={12} color={Colors.textHint} style={{ alignSelf: 'center' }}>
              지금 계약엔 없는 할 일 · 기록으로 남김
            </AppText>
          ) : (
            <TextAction label="되돌리기" muted onPress={actions.reopen} />
          )}
        </View>
      ) : null}
      {actions?.error ? (
        <AppText size={12} color={actions.confirmMoveIn ? Colors.danger : Colors.caution} leading={1.5} style={{ marginTop: 6 }}>
          {actions.error}
        </AppText>
      ) : null}
      {actions?.confirmMoveIn ? (
        <View style={styles.subActions}>
          <TextAction label="그래도 끝내기" onPress={actions.confirmMoveIn} />
        </View>
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

function TextAction({ label, muted, onPress }: { label: string; muted?: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={8} style={styles.textAction}>
      <AppText size={13} weight="semibold" color={muted ? Colors.textSub : Colors.primary}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  notice: { marginTop: 12, padding: 12, borderRadius: Radius.input, backgroundColor: Colors.cautionBg },
  house: {
    marginTop: 12,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: Radius.input,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
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
  subActions: { flexDirection: 'row', gap: 16, marginTop: 8 },
  textAction: { minHeight: 32, justifyContent: 'center' },
  badge: {
    alignSelf: 'flex-start',
    marginTop: 6,
    paddingVertical: 3,
    paddingHorizontal: 8,
    borderRadius: 4,
    backgroundColor: Colors.cautionBg,
  },
});
