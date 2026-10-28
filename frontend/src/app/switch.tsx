import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField, Toggle } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius } from '@/constants/theme';
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

/** UI-07 갈아타기 입력: 지금 집 만기와 다음 집 잔금 사이의 자금 틈을 계산한다 */
export default function SwitchScreen() {
  const [endDate, setEndDate] = useState('2028.11.24');
  const [refund, setRefund] = useState('14000');
  const [balanceDate, setBalanceDate] = useState('2028.11.20');
  const [nextDeposit, setNextDeposit] = useState('16000');
  const [nextDown, setNextDown] = useState('1600');
  const [keepRecords, setKeepRecords] = useState(true);

  const end = parseDate(endDate);
  const bal = parseDate(balanceDate);
  const gapDays = end && bal ? Math.round((end.getTime() - bal.getTime()) / DAY) : null;

  // 자금 틈에 먼저 필요한 돈 = min(지금 집 보증금, 다음 집 잔금), 다음 집 잔금 = 보증금 − 계약금 (정답표 Q5)
  const refundWon = parseManwon(refund);
  const depositWon = parseManwon(nextDeposit);
  const downWon = parseManwon(nextDown) ?? 0;
  const nextBalance = depositWon !== null ? Math.max(depositWon - downWon, 0) : null;
  const gapMoney = refundWon !== null && nextBalance !== null ? Math.min(refundWon, nextBalance) : null;

  return (
    <Screen title="다음 집으로 갈아타기" footer={<Button label="다음 집 계약 전 확인하기" href="/precheck" />}>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 6 }}>
        지금 집 만기와 다음 집 잔금을 맞춰 볼게요
      </AppText>

      <Card style={{ marginTop: 14, gap: 12 }}>
        <AppText size={12} weight="bold" color={Colors.textSub}>
          지금 집
        </AppText>
        <View style={styles.fields}>
          <TextField label="만기일" value={endDate} onChange={setEndDate} />
          <TextField
            label="돌려받을 보증금"
            value={refund}
            onChange={setRefund}
            suffix="만 원"
            keyboardType="number-pad"
            helper={refundWon ? `= ${formatWon(refundWon)} 원` : undefined}
          />
        </View>
        <AppText size={12} weight="bold" color={Colors.textSub} style={{ marginTop: 4 }}>
          다음 집
        </AppText>
        <View style={styles.fields}>
          <TextField label="잔금일" value={balanceDate} onChange={setBalanceDate} warn={gapDays !== null && gapDays > 0} />
          <TextField
            label="보증금"
            value={nextDeposit}
            onChange={setNextDeposit}
            suffix="만 원"
            keyboardType="number-pad"
            helper={depositWon ? `= ${formatWon(depositWon)} 원` : undefined}
          />
        </View>
        <View style={styles.fields}>
          <TextField
            label="계약금 (이미 보낸 돈)"
            value={nextDown}
            onChange={setNextDown}
            suffix="만 원"
            keyboardType="number-pad"
            helper={nextBalance !== null ? `잔금 ${formatWon(nextBalance)} 원` : undefined}
          />
        </View>
      </Card>

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

      <View style={styles.warning}>
        <AppText size={14} weight="bold" color={Colors.caution}>
          전입신고 순서 주의
        </AppText>
        <AppText size={13} color={Colors.cautionText} leading={1.6} style={{ marginTop: 4 }}>
          지금 집 보증금을 받기 전에 다음 집으로 전입을 옮기면 지금 집의 대항력이 사라질 수 있어요. 반환을 확인하거나
          임차권등기가 끝난 뒤 옮기세요.
        </AppText>
      </View>

      <Card style={styles.toggleRow}>
        <AppText size={13} leading={1.5} style={{ flex: 1 }}>
          지금 집 기록을 다음 계약에도 남길까요?
        </AppText>
        <Toggle value={keepRecords} onChange={setKeepRecords} label="지금 집 기록을 다음 계약에도 남기기" />
      </Card>
    </Screen>
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
  gapArea: { position: 'absolute', top: 0, bottom: 0, backgroundColor: '#F6DFC4', borderRadius: 6 },
  bar: { position: 'absolute', height: 24, borderRadius: 6, justifyContent: 'center', paddingLeft: 8, overflow: 'hidden' },
  hatch: { width: 14, height: 14, borderRadius: 3, backgroundColor: '#F6DFC4' },
  warning: { marginTop: 12, padding: 16, backgroundColor: Colors.cautionBg, borderRadius: Radius.card },
  toggleRow: {
    marginTop: 12,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: Radius.sm,
  },
});
