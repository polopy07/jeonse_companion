import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Line, Polyline, Rect, Text as SvgText } from 'react-native-svg';

import { AppText } from '@/components/AppText';
import { Card, DashedBox, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Font, Radius } from '@/constants/theme';
import { alertReport } from '@/data/demo';

/** UI-09 역전세 경보 리포트 (정적) */
export default function AlertScreen() {
  const r = alertReport;
  return (
    <Screen inTabs>
      <AppText size={22} weight="bold" style={{ marginTop: 20, marginBottom: 12 }}>
        역전세 경보
      </AppText>

      <Card padding={18}>
        <View style={styles.rowBetween}>
          <View style={styles.stage}>
            <AppText size={12} weight="bold" color="#7A3A05">
              {r.stage}
            </AppText>
          </View>
          <AppText size={12} color={Colors.textHint}>
            {r.recalculatedAt}
          </AppText>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 10 }}>
          <AppText size={34} weight="bold" color="#9A4A07">
            {r.ratio}%
          </AppText>
          <AppText size={14} color={Colors.textSub}>
            지난번 {r.previous}%에서 올랐어요
          </AppText>
        </View>
        <AppText size={14} leading={1.6} style={{ marginTop: 6 }}>
          {r.reason}
        </AppText>
      </Card>

      <Card style={{ marginTop: 12, paddingHorizontal: 12, paddingBottom: 12 }}>
        <AppText size={13} weight="semibold" style={{ paddingHorizontal: 4 }}>
          내 보증금 비율 변화
        </AppText>
        <RatioChart history={r.history} />
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
      <Disclaimer>시연용 가상 데이터 · 정보 제공이며 보증하지 않습니다.</Disclaimer>
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
  stage: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 999, backgroundColor: '#F9E1CC' },
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
