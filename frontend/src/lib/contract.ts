/**
 * 패키지 시작으로 만든 계약 (POST /api/contracts 응답). 할 일 탭이 이 계약의 할 일을 그린다.
 * 없으면 할 일 탭은 시연 데이터(data/demo.ts)를 보여 준다.
 */
import type { ApiContract, ApiTodo } from '@/lib/api';
import { createStore } from '@/lib/store';

const latestContract = createStore<ApiContract | null>(null);
export const setLatestContract = latestContract.set;
export const useLatestContract = latestContract.use;

/** 할 일 화면 상태: 완료 / 지금 할 일 / 다음 / 아직 시작 전(고정 할 일) */
export type TodoViewStatus = 'done' | 'current' | 'upcoming' | 'later';

export type TodoView = {
  id: string;
  title: string;
  when: string;
  dday?: string;
  badge?: string;
  status: TodoViewStatus;
  todayBefore?: boolean;
  href?: '/switch';
};

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

const parseDate = (s: string) => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/** "2026-11-20" → 올해면 "11.20(금)", 다른 해면 "2028.11.19(일)" */
function dateLabel(s: string, today: Date) {
  const d = parseDate(s);
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}(${WEEKDAYS[d.getDay()]})`;
  return d.getFullYear() === today.getFullYear() ? md : `${d.getFullYear()}.${md}`;
}

function ddayLabel(s: string, today: Date) {
  const days = Math.round((parseDate(s).getTime() - startOfDay(today).getTime()) / 86_400_000);
  return days === 0 ? 'D-DAY' : days > 0 ? `D-${days}` : `D+${-days}`;
}

function whenLabel(t: ApiTodo, today: Date) {
  if (t.due_date) {
    return t.start_date && t.start_date !== t.due_date
      ? `${dateLabel(t.start_date, today)} ~ ${dateLabel(t.due_date, today)}`
      : dateLabel(t.due_date, today);
  }
  if (t.remind_date) return `${dateLabel(t.remind_date, today)} 알림`;
  if (t.start_date) return `${dateLabel(t.start_date, today)}부터 · 기한은 보증기관 기준 확정 후`;
  return '기한은 보증기관 기준 확정 후';
}

/**
 * 서버 할 일(sort_order 순서) → 할 일 화면 값. 순서는 서버(C7) 그대로 두고,
 * 끝나지 않은 첫 할 일을 "지금 할 일"로, 시작일 전인 고정 할 일은 흐리게 보여 준다.
 */
export function todoViews(todos: ApiTodo[], today: Date = new Date()): TodoView[] {
  const todayKey = startOfDay(today).getTime();
  // 고정 할 일은 시작일(재알림은 알림일) 전이면 흐리게
  const notStarted = (t: ApiTodo) => {
    const from = t.start_date ?? t.remind_date;
    return t.pinned && from !== null && parseDate(from).getTime() > todayKey;
  };
  let currentSet = false;
  return todos
    .filter((t) => t.status !== 'skipped')
    .map((t) => {
      let status: TodoViewStatus;
      if (t.status === 'done') status = 'done';
      else if (notStarted(t)) status = 'later';
      else if (!currentSet) {
        status = 'current';
        currentSet = true;
      } else status = 'upcoming';
      const badges = [t.moved_to_top ? '특약·경보로 맨 위' : null, ...t.required_checks].filter(Boolean);
      const target = t.due_date ?? t.remind_date;
      return {
        id: `${t.rule_id}-${t.id}`,
        title: t.title,
        when: whenLabel(t, today),
        dday: target && status !== 'later' ? ddayLabel(target, today) : undefined,
        badge: badges.length ? badges.join(' · ') : undefined,
        status,
        todayBefore: status === 'current',
        href: t.rule_id === 'T9' ? '/switch' : undefined,
      };
    });
}
