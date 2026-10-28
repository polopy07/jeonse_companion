import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField, Toggle } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
import { ApiError, apiEnabled, getMove, postMove, type ApiContract, type ApiMove, type ApiMoveTodo } from '@/lib/api';
import { dateKey, parseDateKey, useVirtualToday } from '@/lib/clock';
import { contractToken, ddayLabel, useLatestContract } from '@/lib/contract';
import { formatWon, parseManwon } from '@/lib/format';

const DAY = 24 * 60 * 60 * 1000;

/** "2028.11.24" → Date. 형식이 틀리면 null */
function parseDate(s: string): Date | null {
  const m = s.trim().match(/^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$/);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

const md = (d: Date) => `${d.getMonth() + 1}.${String(d.getDate()).padStart(2, '0')}`;

/** "2028-11-24" → "2028.11.24" */
const dotDate = (s: string) => s.replaceAll('-', '.');

/** 원 → 입력칸의 만 원 */
const manwon = (won: number) => String(Math.round(won / 10_000));

type NextForm = {
  contractDate: string;
  balanceDate: string;
  endDate: string;
  deposit: string;
  down: string;
  loan: boolean;
};

/** 계약이 있을 때 처음 보여 줄 다음 집 예시 값: 만기 2주 전 잔금(자금 틈 장면), 그 10주 전 계약, 2년 계약, 보증금은 지금과 같게 */
function exampleNext(contract: ApiContract): NextForm {
  const balance = new Date(parseDateKey(contract.end_date).getTime() - 14 * DAY);
  const signed = new Date(balance.getTime() - 70 * DAY);
  const end = new Date(balance.getFullYear() + 2, balance.getMonth(), balance.getDate() - 1);
  return {
    contractDate: dotDate(dateKey(signed)),
    balanceDate: dotDate(dateKey(balance)),
    endDate: dotDate(dateKey(end)),
    deposit: manwon(contract.deposit),
    down: manwon(Math.round(contract.deposit / 10 / 10_000) * 10_000),
    loan: false,
  };
}

const formFromMove = (m: ApiMove): NextForm => ({
  contractDate: dotDate(m.next.contract_date),
  balanceDate: dotDate(m.next.balance_date),
  endDate: dotDate(m.next.end_date),
  deposit: manwon(m.next.deposit),
  down: manwon(m.next.down_payment),
  loan: m.next.loan,
});

/** 시연 데이터 (계약이 없거나 서버 주소가 없을 때) */
const demoNext: NextForm = {
  contractDate: '2028.09.01',
  balanceDate: '2028.11.20',
  endDate: '2030.11.19',
  deposit: '16000',
  down: '1600',
  loan: false,
};

/**
 * UI-07 갈아타기 입력: 지금 집 만기와 다음 집 잔금 사이의 자금 틈을 계산한다.
 * 계약이 있으면 지금 집은 계약 값으로 고정하고, 저장(POST /api/contracts/{id}/move)하면 서버가 자금 틈·대출 순서·
 * 전입 순서 경고와 두 집 할 일을 계산한다 (FR-025~027). 입력을 고치면 저장 전까지 앱 안에서 같은 식으로 미리 계산한다
 */
export default function SwitchScreen() {
  const latest = useLatestContract();
  const contract = apiEnabled ? latest : null;
  // 계약이 바뀌면(앱을 켠 뒤 늦게 불러온 경우 포함) 그 계약의 만기로 입력을 새로 만든다
  return <SwitchForm key={contract?.id ?? 'demo'} contract={contract} />;
}

function SwitchForm({ contract }: { contract: ApiContract | null }) {
  const day = useVirtualToday();

  // 계약이 없을 때만 쓰는 지금 집 입력 (시연)
  const [demoEnd, setDemoEnd] = useState('2028.11.24');
  const [demoRefund, setDemoRefund] = useState('14000');
  const [form, setForm] = useState<NextForm>(() => (contract ? exampleNext(contract) : demoNext));
  const [keepRecords, setKeepRecords] = useState(true);
  const [plan, setPlan] = useState<ApiMove | null>(null);
  // 저장한 뒤 입력을 고쳤는지 (고쳤으면 서버 결과 대신 미리 계산을 보여 준다)
  const [dirty, setDirty] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 저장한 갈아타기가 있으면 불러온다 (가상 날짜가 바뀌면 반환 확인 여부·할 일 상태가 달라져 다시)
  const contractId = contract?.id ?? null;
  useEffect(() => {
    if (contractId === null) return;
    let alive = true;
    getMove(contractId, contractToken(contractId))
      .then((m) => {
        if (!alive) return;
        setPlan(m);
        setForm(formFromMove(m));
        setDirty(false);
      })
      .catch((e) => {
        // 404 = 아직 시작하지 않음 (예시 값으로 입력)
        if (alive && !(e instanceof ApiError && e.status === 404)) {
          setError(e instanceof ApiError ? e.message : '저장한 갈아타기를 불러오지 못했어요');
        }
      });
    return () => {
      alive = false;
    };
  }, [contractId, day]);

  const edit = (patch: Partial<NextForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
    setError(null);
  };

  const shown = plan && !dirty ? plan : null;
  const end = shown ? parseDateKey(shown.return_date) : contract ? parseDateKey(contract.end_date) : parseDate(demoEnd);
  const refundWon = contract ? contract.deposit : parseManwon(demoRefund);
  const bal = parseDate(form.balanceDate);

  // 자금 틈에 먼저 필요한 돈 = min(지금 집 보증금, 다음 집 잔금), 다음 집 잔금 = 보증금 − 계약금 (정답표 Q5)
  const depositWon = parseManwon(form.deposit);
  const downWon = parseManwon(form.down) ?? 0;
  const nextBalance = depositWon !== null ? Math.max(depositWon - downWon, 0) : null;
  const localGapDays = end && bal ? Math.round((end.getTime() - bal.getTime()) / DAY) : null;
  const gapDays = shown ? shown.gap_days : localGapDays;
  const gapMoney = shown
    ? shown.gap_amount
    : refundWon !== null && nextBalance !== null
      ? Math.min(refundWon, nextBalance)
      : null;

  const save = async () => {
    if (!contract || saving) return;
    const dates = [form.contractDate, form.balanceDate, form.endDate].map(parseDate);
    if (dates.some((d) => d === null) || depositWon === null) {
      setError('다음 집 계약일·잔금일·만기일을 2028.11.10처럼, 보증금을 만 원 단위로 입력해 주세요');
      return;
    }
    const [signed, balance, nextEnd] = dates as Date[];
    setSaving(true);
    try {
      const m = await postMove(contract.id, contractToken(contract.id), {
        contract_date: dateKey(signed),
        balance_date: dateKey(balance),
        end_date: dateKey(nextEnd),
        deposit: depositWon,
        down_payment: downWon,
        loan: form.loan,
        guarantor: contract.guarantor,
      });
      setPlan(m);
      setDirty(false);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '저장하지 못했어요');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen
      title="다음 집으로 갈아타기"
      footer={
        <View style={{ gap: 8 }}>
          {contract && (dirty || !plan) ? (
            <Button label={saving ? '계산하는 중…' : '자금 틈 계산하고 저장'} onPress={save} />
          ) : null}
          <Button
            label="다음 집 계약 전 확인하기"
            href="/precheck"
            variant={contract && (dirty || !plan) ? 'outline' : 'primary'}
          />
        </View>
      }>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 6 }}>
        지금 집 만기와 다음 집 잔금을 맞춰 볼게요
      </AppText>

      <Card style={{ marginTop: 14, gap: 12 }}>
        <AppText size={12} weight="bold" color={Colors.textSub}>
          지금 집
        </AppText>
        {contract ? (
          <View style={styles.fields}>
            <Fixed
              label={shown?.returned ? '돌려받은 날' : '반환 예정일'}
              value={end ? dotDate(dateKey(end)) : '-'}
            />
            <Fixed label="돌려받을 보증금" value={`${formatWon(contract.deposit)} 원`} />
          </View>
        ) : (
          <View style={styles.fields}>
            <TextField label="만기일" value={demoEnd} onChange={setDemoEnd} />
            <TextField
              label="돌려받을 보증금"
              value={demoRefund}
              onChange={setDemoRefund}
              suffix="만 원"
              keyboardType="number-pad"
              helper={refundWon ? `= ${formatWon(refundWon)} 원` : undefined}
            />
          </View>
        )}
        <AppText size={12} weight="bold" color={Colors.textSub} style={{ marginTop: 4 }}>
          다음 집
        </AppText>
        <View style={styles.fields}>
          <TextField label="계약일" value={form.contractDate} onChange={(v) => edit({ contractDate: v })} />
          <TextField
            label="잔금일"
            value={form.balanceDate}
            onChange={(v) => edit({ balanceDate: v })}
            warn={gapDays !== null && gapDays > 0}
          />
        </View>
        <View style={styles.fields}>
          <TextField
            label="보증금"
            value={form.deposit}
            onChange={(v) => edit({ deposit: v })}
            suffix="만 원"
            keyboardType="number-pad"
            helper={depositWon ? `= ${formatWon(depositWon)} 원` : undefined}
          />
          <TextField
            label="계약금 (이미 보낸 돈)"
            value={form.down}
            onChange={(v) => edit({ down: v })}
            suffix="만 원"
            keyboardType="number-pad"
            helper={nextBalance !== null ? `잔금 ${formatWon(nextBalance)} 원` : undefined}
          />
        </View>
        {contract ? (
          <>
            <View style={styles.fields}>
              <TextField label="만기일" value={form.endDate} onChange={(v) => edit({ endDate: v })} />
              <View style={{ flex: 1 }} />
            </View>
            <View style={styles.inlineToggle}>
              <AppText size={13} style={{ flex: 1 }}>
                다음 집도 전세대출을 받아요
              </AppText>
              <Toggle value={form.loan} onChange={(v) => edit({ loan: v })} label="다음 집 전세대출" />
            </View>
            {!plan ? (
              <AppText size={12} color={Colors.textHint}>
                예시 값이에요. 다음 집 계약서대로 고친 뒤 저장해 주세요.
              </AppText>
            ) : null}
          </>
        ) : null}
      </Card>

      {error ? (
        <AppText size={13} color={Colors.danger} style={{ marginTop: 10 }}>
          {error}
        </AppText>
      ) : null}

      <SectionLabel>날짜 맞춰 보기</SectionLabel>
      <Card style={{ paddingVertical: 18 }}>
        {end && bal ? (
          <GapChart end={end} bal={bal} />
        ) : (
          <AppText size={13} color={Colors.textSub}>
            날짜를 2028.11.24처럼 입력해 주세요.
          </AppText>
        )}
        {gapDays !== null ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12 }}>
            {gapDays > 0 ? <View style={styles.hatch} /> : <Icon name="check" size={14} color={Colors.ok} strokeWidth={2.2} />}
            <AppText size={13} style={{ flex: 1 }}>
              {gapDays > 0 ? (
                <>
                  <AppText size={13} weight="bold" color={Colors.caution}>
                    자금 틈 {gapDays}일
                  </AppText>
                  {gapMoney !== null
                    ? ` · 이 기간에 ${formatWon(gapMoney)} 원이 먼저 필요해요`
                    : ' · 보증금과 계약금을 입력하면 먼저 필요한 돈을 알려 드려요'}
                </>
              ) : (
                '지금 집 보증금을 받은 뒤 다음 집 잔금을 내요. 자금 틈이 없어요.'
              )}
            </AppText>
          </View>
        ) : null}
      </Card>

      {shown ? (
        shown.warnings.length ? (
          <View style={styles.warning}>
            <AppText size={14} weight="bold" color={Colors.caution}>
              확인할 것
            </AppText>
            {shown.warnings.map((w) => (
              <AppText key={w} size={13} color={Colors.cautionText} leading={1.6} style={{ marginTop: 4 }}>
                · {w}
              </AppText>
            ))}
          </View>
        ) : shown.returned ? (
          <View style={[styles.warning, { backgroundColor: Colors.bg }]}>
            <AppText size={13} leading={1.6}>
              지금 집 보증금 반환을 확인했어요. 다음 집으로 전입을 옮겨도 돼요.
            </AppText>
          </View>
        ) : null
      ) : (
        <View style={styles.warning}>
          <AppText size={14} weight="bold" color={Colors.caution}>
            전입신고 순서 주의
          </AppText>
          <AppText size={13} color={Colors.cautionText} leading={1.6} style={{ marginTop: 4 }}>
            지금 집 보증금을 받기 전에 다음 집으로 전입을 옮기면 지금 집의 대항력이 사라질 수 있어요. 반환을 확인하거나
            임차권등기가 끝난 뒤 옮기세요.
          </AppText>
        </View>
      )}

      {shown ? <MoveTodos todos={shown.todos} /> : null}

      <Card style={styles.toggleRow}>
        <AppText size={13} leading={1.5} style={{ flex: 1 }}>
          지금 집 기록을 다음 계약에도 남길까요?
        </AppText>
        <Toggle value={keepRecords} onChange={setKeepRecords} label="지금 집 기록을 다음 계약에도 남기기" />
      </Card>
    </Screen>
  );
}

/** 계약에서 가져와 고칠 수 없는 값 (입력칸과 같은 자리) */
function Fixed({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <AppText size={12} color={Colors.textSub}>
        {label}
      </AppText>
      <AppText size={15} weight="semibold" style={{ marginTop: 6 }}>
        {value}
      </AppText>
    </View>
  );
}

/** 남은 날(days_left)이 가리키는 날: 재알림이면 재알림일, 아니면 기한 */
const whenOf = (t: ApiMoveTodo) => t.remind_date ?? t.due_date ?? t.start_date;

/**
 * 두 집 할 일을 날짜순으로 (끝내지 않은 것만, FR-025). 서버 목록은 시작일 기준이라, 화면에 보여 주는 날짜와
 * 순서가 어긋나지 않게 그 날짜로 다시 정렬한다 (같은 날이면 서버 순서)
 */
function MoveTodos({ todos }: { todos: ApiMoveTodo[] }) {
  const open = todos
    .filter((t) => t.state !== 'done')
    .map((t, i) => ({ t, i, when: whenOf(t) ?? '9999-12-31' }))
    .sort((a, b) => a.when.localeCompare(b.when) || a.i - b.i)
    .map(({ t }) => t);
  if (!open.length) return null;
  return (
    <>
      <SectionLabel>두 집 할 일 (날짜순)</SectionLabel>
      <Card style={{ paddingVertical: 6 }}>
        {open.map((t, i) => {
          const when = whenOf(t);
          return (
            <View
              key={`${t.house}-${t.rule_id}`}
              style={[styles.todoRow, i < open.length - 1 && { borderBottomWidth: 1, borderBottomColor: Colors.divider }]}>
              <View style={[styles.house, t.house === 'next' && { backgroundColor: Colors.primary }]}>
                <AppText size={11} weight="semibold" color={t.house === 'next' ? '#FFFFFF' : Colors.text}>
                  {t.house === 'next' ? '다음 집' : '지금 집'}
                </AppText>
              </View>
              <AppText size={13} style={{ flex: 1 }} numberOfLines={1}>
                {t.title}
              </AppText>
              <AppText size={12} color={t.state === 'overdue' ? Colors.danger : Colors.textSub}>
                {when ? dotDate(when).slice(2) : ''}
                {t.days_left !== null ? ` · ${ddayLabel(t.days_left)}` : ''}
              </AppText>
            </View>
          );
        })}
      </Card>
    </>
  );
}

/** 두 날짜 앞뒤로 며칠씩 둔 구간에 지금 집(반환)·다음 집(잔금) 막대를 그린다 */
function GapChart({ end, bal }: { end: Date; bal: Date }) {
  const first = Math.min(end.getTime(), bal.getTime());
  const last = Math.max(end.getTime(), bal.getTime());
  const start = first - 5 * DAY;
  const stop = last + 6 * DAY;
  const pct = (t: number) => ((t - start) / (stop - start)) * 100;
  const gap = end.getTime() > bal.getTime();
  const ticks = [start, first, last, stop].map((t) => md(new Date(t)));

  return (
    <View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        {ticks.map((t, i) => (
          <AppText key={i} size={11} color={Colors.textHint}>
            {t}
          </AppText>
        ))}
      </View>
      <View style={{ height: 92, marginTop: 8 }}>
        {gap ? (
          <View
            style={[styles.gapArea, { left: `${pct(bal.getTime())}%`, width: `${pct(end.getTime()) - pct(bal.getTime())}%` }]}
          />
        ) : null}
        <View style={[styles.bar, { top: 14, left: 0, width: `${pct(end.getTime())}%`, backgroundColor: '#9FB3C8' }]}>
          <AppText size={11} weight="semibold" numberOfLines={1}>
            지금 집 · {md(end)} 반환
          </AppText>
        </View>
        <View style={[styles.bar, { top: 54, left: `${pct(bal.getTime())}%`, right: 0, backgroundColor: Colors.primary }]}>
          <AppText size={11} weight="semibold" color="#FFFFFF" numberOfLines={1}>
            다음 집 · {md(bal)} 잔금
          </AppText>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fields: { flexDirection: 'row', gap: 8 },
  inlineToggle: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  gapArea: { position: 'absolute', top: 0, bottom: 0, backgroundColor: '#F6DFC4', borderRadius: 6 },
  bar: { position: 'absolute', height: 24, borderRadius: 6, justifyContent: 'center', paddingLeft: 8, overflow: 'hidden' },
  hatch: { width: 14, height: 14, borderRadius: 3, backgroundColor: '#F6DFC4' },
  warning: { marginTop: 12, padding: 16, backgroundColor: Colors.cautionBg, borderRadius: Radius.card },
  todoRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10 },
  house: { paddingVertical: 3, paddingHorizontal: 8, borderRadius: 999, backgroundColor: Colors.bg },
  toggleRow: {
    marginTop: 12,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: Radius.sm,
  },
});
