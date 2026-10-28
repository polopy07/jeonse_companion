import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Line, Polyline, Rect, Text as SvgText } from 'react-native-svg';

import { AppText } from '@/components/AppText';
import { Card, DashedBox, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Font, Radius } from '@/constants/theme';
import { alertReport } from '@/data/demo';
import { alertLevelOf, estimateFromOfficial, useLatestCheck, type AlertLevel, type CheckView } from '@/lib/check';
import { useLatestContract } from '@/lib/contract';
import { formatWon } from '@/lib/format';

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

function nearbyRow(view: CheckView): NearbyRow | null {
  const n = view.nearbyJeonse;
  if (!n) return null;
  if (n.low_sample || n.median === null) {
    return { value: '표본 부족', note: `같은 단지·비슷한 면적 전세 ${n.sample_count}건 (3건 미만)`, below: null };
  }
  return {
    value: `${formatWon(n.median)} 원`,
    note: `최근 12개월 전세 ${n.sample_count}건 중앙값 · 내 보증금 ${formatWon(view.input.deposit)} 원${n.below_deposit ? '보다 낮음' : ' 이상'}`,
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
    view.ratio_is_minimum ? '등기부를 올리기 전이라 앞선 빚을 0원으로 둔 최소 추정치예요.' : null,
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
    nearby: nearbyRow(view),
    disclaimer: `${view.marketAsOf ? `실거래 기준일 ${dotDate(view.marketAsOf)} · ` : ''}정보 제공이며 보증하지 않습니다.`,
  };
}

const demoReport: AlertReport = {
  ...alertReport,
  ...stageOf(levelFromRatio(alertReport.ratio)),
  reason: `${alertReport.reason} ${reasonOf(alertReport.ratio)}`,
  nearby: null,
  disclaimer: '시연용 가상 데이터 (근저당·2027년 공시가격) · 정보 제공이며 보증하지 않습니다.',
};

/** UI-09 역전세 경보 리포트: 마지막 판정 결과로 그리고, 없으면 시연 리포트 */
export default function AlertScreen() {
  const view = useLatestCheck();
  const contract = useLatestContract();
  // 이 판정으로 만든 계약이 있으면 서버가 정한 경보 단계를 쓴다
  const level = view ? (contract && contract.check_id === view.id ? contract.alert_level : alertLevelOf(view)) : null;
  const fromCheck = view ? reportFromCheck(view, level) : null;
  if (view && !fromCheck) return <NoRatio />;
  const r = fromCheck ?? demoReport;
  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20, marginBottom: 12 }}>
        역전세 경보
      </AppText>

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
              지난번 {r.previous}%에서 {r.ratio >= r.previous ? '올랐어요' : '내렸어요'}
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
        <AppText size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
          공시가격은 1년에 한 번 바뀌고, 실거래가는 신고까지 최대 30일 늦을 수 있어요. 빌라는 같은 단지 거래가 적어
          추정이 실제와 다를 수 있어요.
        </AppText>
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
          <SvgText key={h.label} x={x(i)} y={190} fontSize={10} fill={Colors.textHint} textAnchor="middle" {...textStyle}>
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
