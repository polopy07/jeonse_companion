/**
 * 패키지 시작으로 만든 계약 (POST /api/contracts 응답). 할 일 탭이 이 계약의 할 일을 그린다.
 * 없으면 할 일 탭은 시연 데이터(data/demo.ts)를 보여 준다.
 * 계약 id와 접근 토큰(access_token, 만들 때 한 번만 옴)은 휴대폰에 저장해 두고, 앱을 다시 켜면
 * GET /api/contracts/{id}에 X-Contract-Token으로 붙여 다시 불러온다 (API 명세 1.8).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError, apiEnabled, getContract, type ApiContract, type ApiTodo } from '@/lib/api';
import { parseDateKey } from '@/lib/clock';
import { createStore } from '@/lib/store';

const CONTRACT_ID_KEY = 'jeonse.contractId';
const CONTRACT_TOKEN_KEY = 'jeonse.contractToken';
/** 토큰이 없거나 틀려 서버가 404를 줄 때 안내 (결정 자료 결정 3) */
export const NOT_MY_CONTRACT = '이 휴대폰에서 만든 계약이 아니에요. 저장해 둔 계약을 지웠어요';

const latestContract = createStore<ApiContract | null>(null);
export const useLatestContract = latestContract.use;

/** 저장한 계약을 불러오지 못했을 때 할 일 탭 위에 보여 줄 안내 */
const contractNotice = createStore<string | null>(null);
export const useContractNotice = contractNotice.use;
export const clearContractNotice = () => contractNotice.set(null);

let savedToken: { contractId: number; token: string } | null = null;

/** 이 휴대폰에 저장한 그 계약의 접근 토큰 (계약 아래 API의 X-Contract-Token). 없으면 null */
export function contractToken(contractId: number): string | null {
  return savedToken?.contractId === contractId ? savedToken.token : null;
}

function forget() {
  savedToken = null;
  AsyncStorage.multiRemove([CONTRACT_ID_KEY, CONTRACT_TOKEN_KEY]).catch(() => {});
}

/**
 * 계약을 보여 주고 id를 저장한다. 새로 만든 계약이면 token(access_token)도 저장한다. null이면 지운다 (시연 할 일로).
 * token 없이 부르면(이미 있는 계약을 다시 불러온 경우) 같은 계약의 저장한 토큰은 그대로 둔다
 */
export function setLatestContract(contract: ApiContract | null, token?: string) {
  latestContract.set(contract);
  contractNotice.set(null);
  if (!contract) {
    forget();
    return;
  }
  if (token) savedToken = { contractId: contract.id, token };
  else if (savedToken?.contractId !== contract.id) savedToken = null;
  const save = savedToken
    ? AsyncStorage.multiSet([
        [CONTRACT_ID_KEY, String(contract.id)],
        [CONTRACT_TOKEN_KEY, savedToken.token],
      ])
    : AsyncStorage.setItem(CONTRACT_ID_KEY, String(contract.id)).then(() => AsyncStorage.removeItem(CONTRACT_TOKEN_KEY));
  save.catch(() => {}); // 저장에 실패해도 이번 실행 동안은 계약을 보여 준다
}

/**
 * 앱을 켤 때 한 번: 저장한 계약 id·토큰이 있으면 서버에서 다시 불러온다.
 * 404면(DB를 다시 만들었거나 토큰이 맞지 않음) 저장한 계약을 지우고 안내하고, 연결 실패면 남겨 다음에 다시 시도한다.
 */
export async function restoreContract(): Promise<void> {
  if (!apiEnabled || latestContract.get()) return;
  let id: number;
  let token: string | null;
  try {
    const [[, rawId], [, rawToken]] = await AsyncStorage.multiGet([CONTRACT_ID_KEY, CONTRACT_TOKEN_KEY]);
    id = Number(rawId);
    token = rawToken;
  } catch {
    return;
  }
  if (!Number.isInteger(id) || id <= 0) return;
  if (token) savedToken = { contractId: id, token };
  try {
    const contract = await getContract(id, token);
    if (!latestContract.get()) latestContract.set(contract);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      forget();
      contractNotice.set(NOT_MY_CONTRACT);
    }
  }
}

/**
 * 보고 있는 계약을 서버에서 다시 불러온다 (가상 날짜를 바꾼 뒤 할 일 상태·남은 날을 그날 기준으로).
 * 실패하면 보던 계약을 그대로 두고 오류를 던진다
 */
export async function refreshContract(): Promise<void> {
  const current = latestContract.get();
  if (!apiEnabled || !current) return;
  try {
    const contract = await getContract(current.id, contractToken(current.id));
    if (latestContract.get()?.id === contract.id) latestContract.set(contract);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      latestContract.set(null);
      forget();
      contractNotice.set(NOT_MY_CONTRACT);
      return;
    }
    throw e;
  }
}

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
  /** 서버 할 일 id (PATCH /api/todos/{id}). 시연 할 일이면 없음 */
  todoId?: number;
  /** 완료 증빙으로 올릴 것. 없으면 증빙 없이 끝내는 할 일 */
  evidence?: string | null;
  /** 나중에 올리기로 끝낸 할 일 (기록함이 빈칸이라 증빙을 올릴 수 있음) */
  skipped?: boolean;
};

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** "2026-11-20" → 올해면 "11.20(금)", 다른 해면 "2028.11.19(일)" */
function dateLabel(s: string, today: Date) {
  const d = parseDateKey(s);
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}(${WEEKDAYS[d.getDay()]})`;
  return d.getFullYear() === today.getFullYear() ? md : `${d.getFullYear()}.${md}`;
}

/** 서버가 계산한 남은 날 → "D-3" / "D-DAY" / "D+2" */
export const ddayLabel = (days: number) => (days === 0 ? 'D-DAY' : days > 0 ? `D-${days}` : `D+${-days}`);

function whenLabel(t: ApiTodo, today: Date) {
  if (t.status !== 'todo') {
    const proof = t.evidence_uploaded ? ' · 증빙 1장' : t.status === 'skipped' ? ' · 증빙은 나중에' : '';
    return `${t.done_date ? `${dateLabel(t.done_date, today)} ` : ''}완료${proof}`;
  }
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
 * 서버 할 일(sort_order 순서) → 할 일 화면 값. 순서는 서버(C7) 그대로 두고, 상태(state)·남은 날(days_left)은
 * 서버가 오늘(가상 날짜면 그날) 기준으로 계산한 값을 쓴다. "지금 할 일"은 할 때가 됐거나 기한이 지난 첫 할 일
 * (없으면 끝나지 않은 첫 할 일)이고, 시작 전인 고정 할 일은 흐리게 보여 준다. today는 날짜 표기(올해면 연도 생략)에만 쓴다.
 * 예: 특약 거절로 맨 위에 올라간 전입신고(잔금일)는 목록 맨 위에 두되, 계약일에는 오늘 기한인 할 일이 "지금 할 일"
 * 나중에 올리기(skipped)도 끝낸 할 일로 목록에 남긴다 (서버 state는 #95 전까지 done이 아니라 status로 본다)
 */
export function todoViews(todos: ApiTodo[], today: Date): TodoView[] {
  const open = (t: ApiTodo) => t.status === 'todo';
  const isLater = (t: ApiTodo) => t.pinned && t.state === 'upcoming';
  const due = todos.find((t) => open(t) && (t.state === 'in_progress' || t.state === 'overdue'));
  const current = due ?? todos.find((t) => open(t) && !isLater(t));
  return todos
    .map((t) => {
      let status: TodoViewStatus;
      if (!open(t)) status = 'done';
      else if (t === current) status = 'current';
      else if (isLater(t)) status = 'later';
      else status = 'upcoming';
      const badges = [
        t.state === 'overdue' ? '기한 지남' : null,
        t.moved_to_top ? '특약·경보로 맨 위' : null,
        ...t.required_checks,
      ].filter(Boolean);
      return {
        id: `${t.rule_id}-${t.id}`,
        title: t.title,
        when: whenLabel(t, today),
        // FR-040: 시작 전인 할 일도 기한과 남은 날을 보여 준다
        dday: t.days_left !== null && status !== 'done' ? ddayLabel(t.days_left) : undefined,
        badge: badges.length ? badges.join(' · ') : undefined,
        status,
        todayBefore: status === 'current',
        // 7번(만기 6개월 전 "이사할게요")·9번(반환 확인)에서 갈아타기로 (FR-025)
        href: t.rule_id === 'T7' || t.rule_id === 'T9' ? '/switch' : undefined,
        todoId: t.id,
        evidence: t.evidence,
        skipped: t.status === 'skipped',
      };
    });
}
