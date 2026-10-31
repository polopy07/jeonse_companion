import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Line, Polyline, Rect, Text as SvgText } from 'react-native-svg';

import { AppText } from '@/components/AppText';
import { EmptyTab } from '@/components/empty';
import { Card, DashedBox, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Font, Radius } from '@/constants/theme';
import { alertReport } from '@/data/demo';
import { ApiError, apiEnabled, getAlertReport, type ApiAlertReport, type ApiCheckResult, type ApiContract } from '@/lib/api';
import { alertLevelOf, estimateFromOfficial, useLatestCheck, type AlertLevel, type CheckView } from '@/lib/check';
import { useVirtualToday } from '@/lib/clock';
import { contractToken, useLatestContract } from '@/lib/contract';
import { formatWon } from '@/lib/format';
import { useDemoMode } from '@/lib/demo-mode';

type NearbyRow = { value: string; note: string; below: boolean | null };

type AlertReport = {
  stage: string;
  stageColor: string;
  stageBg: string;
  recalculatedAt: string;
  ratio: number;
  previous: number | null;
  reason: string;
  history: { label: string; ratio: number }[];
  basis: { label: string; note?: string; value: string; struck: boolean }[];
  estimated: string;
  /** 주변 전세 시세 (서버가 단지로 찾았을 때만) */
  nearby: NearbyRow | null;
  /** 데이터 한계 안내 (서버 alert.yaml). 없으면 화면 기본 문구 */
  dataLimits: string[] | null;
  disclaimer: string;
};

/** alert.yaml 단계: 주의 / 경고 / 위험 (정상은 null) */
function stageOf(level: AlertLevel | null) {
  if (level === 'danger') return { stage: '위험 단계', stageColor: Colors.danger, stageBg: Colors.dangerBg };
  if (level === 'warning') return { stage: '경고 단계', stageColor: '#7A3A05', stageBg: '#F9E1CC' };
  if (level === 'caution') return { stage: '주의 단계', stageColor: Colors.caution, stageBg: Colors.cautionBg };
  return { stage: '정상', stageColor: Colors.ok, stageBg: Colors.bg };
}

/** 비율만으로 정하는 단계 (시연 리포트용) */
const levelFromRatio = (ratio: number): AlertLevel | null =>
  ratio >= 100 ? 'danger' : ratio >= 90 ? 'warning' : ratio >= 80 ? 'caution' : null;

const reasonOf = (ratio: number) =>
  ratio >= 100
    ? '보증금과 앞선 빚을 합친 금액이 추정 집값보다 많아요. 집이 팔려도 보증금을 다 돌려받기 어려운 구간이에요.'
    : ratio >= 90
      ? '90%를 넘으면 반환보증 신규 가입이 어려운 구간이에요.'
      : ratio >= 80
        ? '집값이 조금만 내려가도 경고 구간에 들어갈 수 있어요. 계약 중에도 다시 계산해 알려 드려요.'
        : '보증금과 앞선 빚이 추정 집값보다 충분히 낮아요.';

const nearbyReason = '주변 전세 시세가 내 보증금보다 낮아요. 만기 때 새 세입자를 같은 보증금으로 구하기 어려울 수 있어요.';

/** "2026-09-30" → "2026.09.30" */
const dotDate = (s: string) => s.replaceAll('-', '.');

const minimumReason = '등기부를 올리기 전이라 앞선 빚을 0원으로 둔 최소 추정치예요.';

/** 0.9507 → 95 */
const percent = (ratio: number) => Math.round(ratio * 100);

/** "2027-05-01" → "27.05" (그래프 아래 이름) */
const monthLabel = (s: string) => `${s.slice(2, 4)}.${s.slice(5, 7)}`;

function nearbyRow(n: ApiCheckResult['nearby_jeonse'] | undefined, deposit: number): NearbyRow | null {
  if (!n) return null;
  if (n.low_sample || n.median === null) {
    return { value: '표본 부족', note: `같은 단지·비슷한 면적 전세 ${n.sample_count}건 (3건 미만)`, below: null };
  }
  return {
    value: `${formatWon(n.median)} 원`,
    note: `최근 12개월 전세 ${n.sample_count}건 중앙값 · 내 보증금 ${formatWon(deposit)} 원${n.below_deposit ? '보다 낮음' : ' 이상'}`,
    below: n.below_deposit,
  };
}

/**
 * 마지막 판정 결과(계약 전 확인) → 경보 리포트. 계약 중 재계산 API가 생기기 전이라 변화 기록은 판정 1건뿐이다.
 * level = 이 판정으로 만든 계약이 있으면 서버가 정한 계약의 경보 단계, 없으면 판정 값으로 같은 기준 계산
 */
function reportFromCheck(view: CheckView, level: AlertLevel | null): AlertReport | null {
  const { input } = view;
  if (view.deposit_ratio === null || view.estimated_price === null || !input.official_price) return null;
  const ratio = Math.round(view.deposit_ratio * 100);
  const senior = (input.registry?.mortgage_amount ?? 0) + (input.registry?.lease_amount ?? 0);
  const fromOfficial = estimateFromOfficial(input.official_price);
  const tradeUsed = view.tradePrice !== null && view.tradePrice < fromOfficial;
  const trade = view.tradeBasis;
  const [y, m] = view.checkedAt.split('.');
  const reasons = [
    // 주변 전세만으로 주의가 되면 비율 문장 대신 주변 전세 문장을 앞에
    ratio >= 80 || !view.nearbyJeonse?.below_deposit ? reasonOf(ratio) : null,
    view.nearbyJeonse?.below_deposit ? nearbyReason : null,
    view.ratio_is_minimum ? minimumReason : null,
  ];
  return {
    ...stageOf(level),
    recalculatedAt: `${view.checkedAt} 계약 전 확인`,
    ratio,
    previous: null,
    reason: reasons.filter(Boolean).join(' '),
    history: [{ label: `${(y ?? '').slice(2)}.${m ?? ''}`, ratio }],
    basis: [
      {
        label: senior ? '보증금 + 앞선 빚' : '보증금',
        note: senior ? `근저당·임차권 등 ${formatWon(senior)}` : undefined,
        value: formatWon(input.deposit + senior),
        struck: false,
      },
      { label: '공시가격 × 140%', value: formatWon(fromOfficial), struck: tradeUsed },
      ...(view.tradePrice !== null
        ? [
            {
              label: '실거래가 · 전용 ±10%',
              note: trade ? `${dotDate(trade.deal_date)} 거래 · ${trade.exclusive_area}㎡ · 표본 ${trade.sample_count}건` : undefined,
              value: formatWon(view.tradePrice),
              struck: !tradeUsed,
            },
          ]
        : view.marketAsOf
          ? [{ label: '실거래가 · 전용 ±10%', note: '최근 12개월 같은 단지 매매 없음', value: '없음', struck: true }]
          : []),
    ],
    estimated: formatWon(view.estimated_price),
    nearby: nearbyRow(view.nearbyJeonse, input.deposit),
    dataLimits: null,
    disclaimer: `${view.marketAsOf ? `실거래 기준일 ${dotDate(view.marketAsOf)} · ` : ''}정보 제공이며 보증하지 않습니다.`,
  };
}

/**
 * 계약의 최근 경보 (GET /api/contracts/{id}/alerts/latest) → 경보 리포트.
 * 계약 중 공시가격·실거래가가 바뀌어 다시 계산했으면 그 값과 변화 기록, 아니면 계약을 시작할 때의 값
 */
function reportFromApi(a: ApiAlertReport, deposit: number): AlertReport {
  const b = a.basis;
  const ratio = percent(a.deposit_ratio);
  const trade = b.trade_price_input ?? b.trade?.price ?? null;
  const tradeUsed = trade !== null && trade < b.official_estimate;
  const belowDeposit = b.nearby_jeonse?.below_deposit;
  const reasons = [
    ratio >= 80 || !belowDeposit ? reasonOf(ratio) : null,
    belowDeposit ? nearbyReason : null,
    b.ratio_is_minimum ? minimumReason : null,
  ];
  const tradeNote =
    b.trade_price_input !== null
      ? '계약 전 확인 때 직접 넣은 값'
      : b.trade
        ? `${dotDate(b.trade.deal_date)} 거래 · ${b.trade.exclusive_area}㎡ · 표본 ${b.trade.sample_count}건`
        : undefined;
  return {
    ...stageOf(a.level),
    recalculatedAt: `${dotDate(a.as_of)} ${a.recalculated ? '다시 계산' : '계약 시작'}`,
    ratio,
    previous: a.previous_ratio === null ? null : percent(a.previous_ratio),
    reason: reasons.filter(Boolean).join(' '),
    history: a.history.map((h) => ({ label: monthLabel(h.as_of), ratio: percent(h.deposit_ratio) })),
    basis: [
      {
        label: b.senior_debt ? '보증금 + 앞선 빚' : '보증금',
        note: b.senior_debt ? `근저당·임차권 등 ${formatWon(b.senior_debt)}` : undefined,
        value: formatWon(deposit + b.senior_debt),
        struck: false,
      },
      {
        label: `공시가격 × ${Math.round(b.multiplier * 100)}%`,
        note: `공시가격 ${formatWon(b.official_price)}`,
        value: formatWon(b.official_estimate),
        struck: tradeUsed,
      },
      ...(trade !== null
        ? [{ label: '실거래가 · 전용 ±10%', note: tradeNote, value: formatWon(trade), struck: !tradeUsed }]
        : b.complex_known
          ? [{ label: '실거래가 · 전용 ±10%', note: '최근 12개월 같은 단지 매매 없음', value: '없음', struck: true }]
          : []),
    ],
    estimated: formatWon(a.estimated_price),
    nearby: nearbyRow(b.nearby_jeonse, deposit),
    dataLimits: a.data_limits.length ? a.data_limits : null,
    disclaimer: `기준일 ${dotDate(b.as_of)} · 정보 제공이며 보증하지 않습니다.`,
  };
}

type RemoteAlert = { contractId: number; report: ApiAlertReport | null; notApplicable: boolean; error: string | null };

/**
 * 계약의 최근 경보를 서버에서 받는다. 탭을 열 때마다 다시 받아 관리자 재계산(공시가격 발표)·가상 날짜를 바로 반영한다.
 * 서버 주소가 없거나 계약이 없으면 null
 */
function useAlertReport(contract: ApiContract | null): RemoteAlert | null {
  const [remote, setRemote] = useState<RemoteAlert | null>(null);
  const day = useVirtualToday();
  const id = contract?.id ?? null;
  useFocusEffect(
    useCallback(() => {
      if (!apiEnabled || id === null) return;
      let alive = true;
      getAlertReport(id, contractToken(id))
        .then((report) => alive && setRemote({ contractId: id, report, notApplicable: false, error: null }))
        .catch((e) => {
          if (!alive) return;
          // 404 = 다가구·단독 등 경보를 계산하지 않는 계약 (토큰이 틀린 계약은 할 일 탭에서 먼저 안내)
          const notApplicable = e instanceof ApiError && e.status === 404;
          const error = notApplicable ? null : e instanceof ApiError ? e.message : '경보를 받지 못했어요';
          setRemote({ contractId: id, report: null, notApplicable, error });
        });
      return () => {
        alive = false;
      };
      // contract가 바뀌면(보증금 수정·다시 불러오기) 다시 받는다
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, day, contract]),
  );
  return remote?.contractId === id ? remote : null;
}

const demoReport: AlertReport = {
  ...alertReport,
  ...stageOf(levelFromRatio(alertReport.ratio)),
  reason: `${alertReport.reason} ${reasonOf(alertReport.ratio)}`,
  nearby: null,
  dataLimits: null,
  disclaimer: '시연용 가상 데이터 (근저당·2027년 공시가격) · 정보 제공이며 보증하지 않습니다.',
};

/**
 * UI-09 역전세 경보 리포트: 계약이 있으면 서버의 최근 경보(계약 중 재계산 포함), 계약 전이면 마지막 판정 결과,
 * 둘 다 없으면 시연 리포트
 */
export default function AlertScreen() {
  const view = useLatestCheck();
  const latest = useLatestContract();
  // 마지막 판정으로 만든 계약만 (계약 뒤 다른 집을 새로 확인했으면 그 판정을 보여 준다)
  const contract = latest && (!view || latest.check_id === view.id) ? latest : null;
  const remote = useAlertReport(contract);
  const demo = useDemoMode();
  // 계약 전 확인도 계약도 없으면 빈 화면 (계약 전 확인만 해도 그 판정으로 경보를 보여 준다)
  if (!view && !contract && !demo) {
    return (
      <EmptyTab
        title="역전세 경보"
        lines={['계약 전 확인을 하면 내 보증금 비율로 경보 단계를 무료로 보여 줘요', '계약하면 공시가격 발표·주변 거래가 생길 때 다시 계산해 알려요']}
      />
    );
  }
  if (remote?.notApplicable) return <NoRatio />;
  const fromServer = remote?.report && contract ? reportFromApi(remote.report, contract.deposit) : null;
  // 서버 경보를 받기 전·못 받았을 때: 계약이 있으면 서버가 정한 계약 시작 단계, 없으면 판정 값으로 같은 기준 계산
  const level = view ? (contract ? contract.alert_level : alertLevelOf(view)) : null;
  const fromCheck = view ? reportFromCheck(view, level) : null;
  if (!fromServer && view && !fromCheck) return <NoRatio />;
  const r = fromServer ?? fromCheck ?? demoReport;
  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20, marginBottom: 12 }}>
        역전세 경보
      </AppText>
      {remote?.error ? (
        <AppText size={12} color={Colors.danger} style={{ marginBottom: 8 }}>
          {remote.error} · 계약을 시작할 때의 값을 보여 드려요
        </AppText>
      ) : null}

      <Card padding={18}>
        <View style={styles.rowBetween}>
          <View style={[styles.stage, { backgroundColor: r.stageBg }]}>
            <AppText size={12} weight="bold" color={r.stageColor}>
              {r.stage}
            </AppText>
          </View>
          <AppText size={12} color={Colors.textHint}>
            {r.recalculatedAt}
          </AppText>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 10 }}>
          <AppText size={34} weight="bold" color={r.stageColor}>
            {r.ratio}%
          </AppText>
          {r.previous !== null ? (
            <AppText size={14} color={Colors.textSub}>
              {r.ratio === r.previous
                ? `지난번과 같은 ${r.previous}%예요`
                : `지난번 ${r.previous}%에서 ${r.ratio > r.previous ? '올랐어요' : '내렸어요'}`}
            </AppText>
          ) : null}
        </View>
        <AppText size={14} leading={1.6} style={{ marginTop: 6 }}>
          {r.reason}
        </AppText>
      </Card>

      <Card style={{ marginTop: 12, paddingHorizontal: 12, paddingBottom: 12 }}>
        <AppText size={13} weight="semibold" style={{ paddingHorizontal: 4 }}>
          내 보증금 비율 변화
        </AppText>
        {r.history.length > 1 ? (
          <RatioChart history={r.history} />
        ) : (
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 8, paddingHorizontal: 4 }}>
            지금은 계약 전 확인 1번의 값이에요. 계약 중 공시가격·실거래가가 바뀌면 다시 계산해 여기에 쌓여요.
          </AppText>
        )}
      </Card>

      <SectionLabel>계산 근거</SectionLabel>
      <View style={styles.table}>
        {r.basis.map((b) => (
          <View key={b.label} style={[styles.tableRow, styles.divider]}>
            <View>
              <AppText size={13} color={Colors.textSub}>
                {b.label}
              </AppText>
              {b.note ? (
                <AppText size={11} color={Colors.textSub}>
                  {b.note}
                </AppText>
              ) : null}
            </View>
            <AppText
              size={13}
              weight="semibold"
              color={b.struck ? Colors.textHint : Colors.text}
              style={b.struck ? { textDecorationLine: 'line-through' } : undefined}>
              {b.value}
            </AppText>
          </View>
        ))}
        <View style={[styles.tableRow, { backgroundColor: Colors.bg }]}>
          <AppText size={13}>추정 집값 (둘 중 낮은 값)</AppText>
          <AppText size={13} weight="bold">
            {r.estimated}
          </AppText>
        </View>
      </View>

      {r.nearby ? (
        <>
          <SectionLabel>주변 전세 시세</SectionLabel>
          <View style={styles.table}>
            <View style={styles.tableRow}>
              <View style={{ flex: 1, paddingRight: 12 }}>
                <AppText size={13} color={Colors.textSub}>
                  같은 단지 · 전용 ±10%
                </AppText>
                <AppText size={11} color={Colors.textSub}>
                  {r.nearby.note}
                </AppText>
              </View>
              <AppText size={13} weight="semibold" color={r.nearby.below ? Colors.caution : Colors.text}>
                {r.nearby.value}
              </AppText>
            </View>
          </View>
        </>
      ) : null}

      <DashedBox style={{ marginTop: 14, paddingVertical: 14, borderRadius: Radius.sm }}>
        <AppText size={13} weight="semibold">
          데이터 한계
        </AppText>
        {r.dataLimits ? (
          r.dataLimits.map((text) => (
            <AppText key={text} size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
              · {text}
            </AppText>
          ))
        ) : (
          <AppText size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            공시가격은 1년에 한 번 바뀌고, 실거래가는 신고까지 최대 30일 늦을 수 있어요. 빌라는 같은 단지 거래가 적어
            추정이 실제와 다를 수 있어요.
          </AppText>
        )}
      </DashedBox>

      <View style={{ flex: 1 }} />
      <Disclaimer>{r.disclaimer}</Disclaimer>
    </Screen>
  );
}

/** 공시가격이 없거나 다가구·단독이라 비율을 계산하지 못한 판정 */
function NoRatio() {
  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20, marginBottom: 12 }}>
        역전세 경보
      </AppText>
      <DashedBox>
        <AppText size={14} weight="semibold">
          내 보증금 비율을 계산하지 못했어요
        </AppText>
        <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
          다가구·단독주택은 경보 대상이 아니고, 공시가격을 넣지 않으면 추정 집값을 낼 수 없어요. 계약 전 확인에서 공시가격을
          넣으면 여기에 보여 드려요.
        </AppText>
      </DashedBox>
      <View style={{ flex: 1 }} />
      <Disclaimer>정보 제공이며 보증하지 않습니다.</Disclaimer>
    </Screen>
  );
}

/** 80·90·100% 구간을 칠한 선 그래프. 목업 좌표(342×200)를 viewBox로 그대로 쓴다 */
function RatioChart({ history }: { history: { label: string; ratio: number }[] }) {
  const x = (i: number) => 40 + i * 56;
  // 100% → y 33, 80% → y 124 (10%p = 45.5)
  const y = (ratio: number) => 124 - (ratio - 80) * 4.55;
  const last = history.length - 1;
  const changes = history.map((h, i) => i).filter((i) => i === 0 || history[i].ratio !== history[i - 1].ratio);
  const peak = changes[changes.length - 1];
  const textStyle = { fontFamily: Font.regular };

  return (
    <View style={{ width: '100%', aspectRatio: 342 / 200, marginTop: 8 }}>
      <Svg
        width="100%"
        height="100%"
        viewBox="0 0 342 200"
        accessibilityLabel={`내 보증금 비율이 ${history[0].ratio}%에서 ${history[last].ratio}%로 바뀐 추이`}>
        <Rect x={24} y={10} width={312} height={23} fill={Colors.dangerBg} />
        <Rect x={24} y={33} width={312} height={46} fill={Colors.cautionBg} />
        <Rect x={24} y={79} width={312} height={45} fill="#FDF7F0" />
        <Line x1={24} y1={33} x2={336} y2={33} stroke={Colors.danger} strokeWidth={1} strokeDasharray="3 3" />
        <Line x1={24} y1={79} x2={336} y2={79} stroke={Colors.cautionStrong} strokeWidth={1} strokeDasharray="3 3" />
        <Line x1={24} y1={124} x2={336} y2={124} stroke={Colors.inputBorder} strokeWidth={1} strokeDasharray="3 3" />
        {[100, 90, 80].map((v) => (
          <SvgText key={v} x={20} y={y(v) + 4} fontSize={10} fill={Colors.textHint} textAnchor="end" {...textStyle}>
            {v}
          </SvgText>
        ))}
        <Polyline
          points={history.map((h, i) => `${x(i)},${y(h.ratio)}`).join(' ')}
          fill="none"
          stroke={Colors.primary}
          strokeWidth={2.5}
          strokeLinejoin="round"
        />
        {changes.map((i) =>
          i === peak ? (
            <Circle key={i} cx={x(i)} cy={y(history[i].ratio)} r={5} fill="#FFFFFF" stroke="#9A4A07" strokeWidth={3} />
          ) : (
            <Circle key={i} cx={x(i)} cy={y(history[i].ratio)} r={4} fill={Colors.primary} />
          ),
        )}
        {changes.map((i) => (
          <SvgText
            key={`v${i}`}
            x={x(i)}
            y={y(history[i].ratio) - 10}
            fontSize={11}
            fill={i === peak ? '#9A4A07' : Colors.text}
            fontFamily={i === peak ? Font.bold : Font.regular}
            textAnchor="middle">
            {history[i].ratio}
          </SvgText>
        ))}
        {history.map((h, i) => (
          <SvgText key={i} x={x(i)} y={190} fontSize={10} fill={Colors.textHint} textAnchor="middle" {...textStyle}>
            {h.label}
          </SvgText>
        ))}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  stage: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 999 },
  table: {
    backgroundColor: Colors.card,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  tableRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, paddingHorizontal: 16 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
});
