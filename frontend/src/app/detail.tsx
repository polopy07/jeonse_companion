import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Card, DashedBox, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { SpecialTermRow, verdictStyle } from '@/components/verdict';
import { Colors, Radius } from '@/constants/theme';
import { checkResult, detailRows } from '@/data/demo';
import { termsFor } from '@/lib/special-terms';

/** UI-02 판정 상세 (정적) */
export default function DetailScreen() {
  return (
    <Screen title="판정 상세">
      <SectionLabel style={{ marginTop: 10 }}>항목별 결과</SectionLabel>
      <View style={styles.table}>
        {detailRows.map((row, i) => {
          const hit = row.level !== 'ok';
          return (
            <View
              key={row.label}
              style={[
                styles.row,
                i < detailRows.length - 1 && styles.divider,
                hit && row.label === '근저당' && { backgroundColor: Colors.cautionRow },
              ]}>
              <AppText size={14} weight={hit && row.label === '근저당' ? 'semibold' : 'regular'}>
                {row.label}
              </AppText>
              <AppText size={12} weight={hit ? 'bold' : 'semibold'} color={verdictStyle[row.level].fg}>
                {row.value}
              </AppText>
            </View>
          );
        })}
      </View>

      <SectionLabel>근저당, 쉬운 말로</SectionLabel>
      <Card>
        <AppText size={11} color={Colors.textHint}>
          등기부 주요 등기사항 요약 · 을구 1
        </AppText>
        <View style={styles.source}>
          <AppText size={12} color={Colors.textCode} leading={1.7}>
            근저당권설정 · 채권최고액 금36,000,000원 · 근저당권자 ○○은행
          </AppText>
        </View>
        <AppText size={14} leading={1.7} style={{ marginTop: 12 }}>
          집주인이 이 집을 담보로 은행에서 돈을 빌렸어요. 집이 경매로 넘어가면 은행이{' '}
          <AppText size={14} weight="bold">
            최대 3,600만 원
          </AppText>
          을 내 보증금보다 먼저 가져가요.
        </AppText>
        <AppText size={12} color={Colors.textHint} style={{ marginTop: 8 }}>
          자동 설명은 참고용이에요. 원문과 다르면 원문이 기준이에요.
        </AppText>
      </Card>

      <SectionLabel>이 판정에 맞는 특약 예시</SectionLabel>
      <View style={{ gap: 8 }}>
        {termsFor(checkResult.matched).map((t) => (
          <SpecialTermRow key={t.id} term={t} />
        ))}
      </View>

      <DashedBox style={{ marginTop: 20 }}>
        <AppText size={14} weight="semibold">
          확인 못 한 항목
        </AppText>
        <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
          임대인 국세·지방세 체납 · HUG 안심전세앱에서 임대인 위험도를 함께 조회해 보세요.
        </AppText>
      </DashedBox>

      <View style={{ flex: 1 }} />
      <Disclaimer>
        조회 2026.10.09 · 정보 제공이며 보증하지 않습니다. 개별 법률 판단이 필요하면 공공 상담 창구를 이용하세요.
      </Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  table: {
    backgroundColor: Colors.card,
    borderRadius: Radius.card,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
  },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  source: { marginTop: 6, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: Colors.bg, borderRadius: 8 },
});
