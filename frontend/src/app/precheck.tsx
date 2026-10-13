import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ChoiceChips, TextField, ToggleRow } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, DashedBox, Screen, SectionLabel } from '@/components/layout';
import { ratioBand } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { demoHouses, type DemoHouse } from '@/data/demo';
import {
  estimateFromOfficial,
  housingTypes,
  isNotApplicable,
  runCheckLocal,
  setLatestCheck,
  type CheckInput,
  type GuarantorConsult,
  type HousingType,
  type TrustConsent,
} from '@/lib/check';
import { formatWon, parseManwon, parseNumber } from '@/lib/format';

const steps = ['집 정보', '공시가격', '등기부', '확인·수정'];

type Violation = 'unknown' | 'no' | 'yes';
type RegistryMode = 'none' | 'loading' | 'filled' | 'manual';

const todayText = () => {
  const d = new Date();
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
};

const toManwonText = (won: number) => (won ? String(Math.round(won / 10_000)) : '');

/** 계약 전 확인 입력 (UI-01 입력 부분, FR-001~006). 집 정보 → 공시가격 → 등기부 → 추출 결과 확인·수정 → 결과 */
export default function PrecheckScreen() {
  const [step, setStep] = useState(0);
  const [preset, setPreset] = useState<DemoHouse | null>(null);

  // ① 집 정보
  const [address, setAddress] = useState('');
  const [housingType, setHousingType] = useState<HousingType | null>(null);
  const [depositText, setDepositText] = useState('');
  const [areaText, setAreaText] = useState('');

  // ② 공시가격 (시연 집은 미리 매칭)
  const [officialText, setOfficialText] = useState('');

  // ③④ 등기부
  const [registryMode, setRegistryMode] = useState<RegistryMode>('none');
  const [fileName, setFileName] = useState<string | null>(null);
  const [owner, setOwner] = useState('');
  const [seizure, setSeizure] = useState(false);
  const [mortgage, setMortgage] = useState(false);
  const [mortgageText, setMortgageText] = useState('');
  const [trust, setTrust] = useState(false);
  const [trustConsent, setTrustConsent] = useState<TrustConsent>('unknown');
  const [violation, setViolation] = useState<Violation>('unknown');
  const [guarantorConsult, setGuarantorConsult] = useState<GuarantorConsult>('not_yet');

  const deposit = parseManwon(depositText);
  const official = preset ? preset.official_price : parseManwon(officialText);
  const mortgageAmount = parseManwon(mortgageText);
  const na = housingType !== null && isNotApplicable(housingType);

  const fillPreset = (h: DemoHouse) => {
    setPreset(h);
    setAddress(h.address);
    setHousingType(h.housing_type);
    setDepositText(h.depositManwon);
    setAreaText(h.area);
    setOfficialText(toManwonText(h.official_price));
    setViolation(h.building_violation ? 'yes' : 'no');
    setRegistryMode('none');
    setFileName(null);
  };

  // 주소를 직접 고치면 시연 집 매칭을 푼다
  const editAddress = (v: string) => {
    setAddress(v);
    if (preset && v !== preset.address) setPreset(null);
  };

  const fillRegistry = (h: DemoHouse | null) => {
    if (h) {
      setOwner(h.registry.owner);
      setSeizure(h.registry.seizure);
      setMortgage(h.registry.mortgage);
      setMortgageText(toManwonText(h.registry.mortgage_amount));
      setTrust(h.registry.trust);
      setRegistryMode('filled');
    } else {
      setRegistryMode('manual');
    }
    setStep(3);
  };

  const pickPdf = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
    if (res.canceled) return;
    setFileName(res.assets[0].name);
    setRegistryMode('loading');
    // 백엔드 연결 전: POST /api/registry/parse 대신 시연 집이면 시연 등기부 값으로, 아니면 직접 입력으로 넘긴다
    setTimeout(() => fillRegistry(preset), 600);
  };

  const submit = (withRegistry: boolean) => {
    if (!housingType || !deposit) return;
    const input: CheckInput = {
      housing_type: housingType,
      deposit,
      official_price: official,
      trade_price: preset?.trade_price ?? null,
      exclusive_area: parseNumber(areaText),
      registry: withRegistry ? { seizure, mortgage, mortgage_amount: mortgage ? (mortgageAmount ?? 0) : 0, trust } : null,
      trust_consent: trust ? trustConsent : 'unknown',
      building_violation: violation === 'unknown' ? null : violation === 'yes',
      guarantor_consult: violation === 'yes' ? guarantorConsult : 'not_yet',
    };
    const typeLabel = housingTypes.find((t) => t.value === housingType)?.label ?? '';
    const label = `${preset ? preset.label : address.trim()} · ${typeLabel}`;
    setLatestCheck(runCheckLocal(input, label, todayText(), withRegistry && owner.trim() ? owner.trim() : null));
    router.push('/check');
  };

  // 단계별로 다음으로 넘어갈 수 있는지
  const canNext = [
    address.trim().length > 0 && housingType !== null && !!deposit,
    !!official,
    false, // 등기부 단계는 아래 버튼들로 넘어간다
    !mortgage || !!mortgageAmount,
  ][step];

  const next = () => {
    if (step === 0 && na) return submit(false);
    if (step === 3) return submit(true);
    setStep(step + 1);
  };

  const back = () => (step === 0 ? router.back() : setStep(step - 1));

  const footer =
    step === 2 ? (
      <Button variant="outline" label="이전" onPress={back} />
    ) : (
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button variant="outline" label="이전" onPress={back} style={{ paddingHorizontal: 20 }} />
        <Button
          label={step === 3 || (step === 0 && na) ? '결과 보기' : '다음'}
          onPress={canNext ? next : undefined}
          style={{ flex: 1, opacity: canNext ? 1 : 0.4 }}
        />
      </View>
    );

  return (
    <Screen title="계약 전 확인" footer={footer}>
      <View style={{ marginTop: 8 }}>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {steps.map((s, i) => (
            <View key={s} style={[styles.step, { backgroundColor: i <= step ? Colors.primary : Colors.inactiveDot }]} />
          ))}
        </View>
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 8 }}>
          {step + 1} / {steps.length} · {steps[step]} · 무료
        </AppText>
      </View>

      {step === 0 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            어떤 집을 보고 있나요?
          </AppText>

          <SectionLabel style={{ marginTop: 14 }}>시연 집으로 채우기</SectionLabel>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {demoHouses.map((h) => {
              const on = preset?.id === h.id;
              return (
                <Pressable
                  key={h.id}
                  accessibilityRole="button"
                  onPress={() => fillPreset(h)}
                  style={[styles.preset, on && { borderColor: Colors.primary, borderWidth: 2 }]}>
                  <AppText size={13} weight="semibold" color={on ? Colors.primary : Colors.text}>
                    {h.chip}
                  </AppText>
                </Pressable>
              );
            })}
          </View>

          <Card style={{ marginTop: 12, gap: 14 }}>
            <TextField label="주소" value={address} onChange={editAddress} placeholder="예: 부산 수영구 ○○동 ○○빌라 201호" />
            <ChoiceChips label="주택 유형" choices={housingTypes} value={housingType} onChange={setHousingType} />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TextField
                label="보증금"
                value={depositText}
                onChange={setDepositText}
                suffix="만 원"
                keyboardType="number-pad"
                placeholder="14000"
                helper={deposit ? `= ${formatWon(deposit)} 원` : undefined}
              />
              <TextField
                label="전용면적"
                value={areaText}
                onChange={setAreaText}
                suffix="㎡"
                keyboardType="decimal-pad"
                placeholder="49.5"
                helper="계약서·건축물대장에 있어요"
              />
            </View>
          </Card>

          {na ? (
            <View style={[styles.note, { backgroundColor: Colors.muted }]}>
              <AppText size={14} weight="bold">
                다가구·단독은 점검 대상이 아니에요
              </AppText>
              <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
                다른 세대의 보증금을 등기부로 알 수 없어서 판정·경보를 하지 않아요. 날짜별 할 일 관리는 이용할 수 있어요.
              </AppText>
            </View>
          ) : null}
        </>
      ) : null}

      {step === 1 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            공시가격으로 집값을 추정해요
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            추정 집값 = 공시가격 × 140%. 같은 단지·비슷한 면적 실거래가가 있으면 둘 중 낮은 값을 써요.
          </AppText>

          {preset ? (
            <Card style={{ marginTop: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Icon name="check" size={16} color={Colors.ok} strokeWidth={2.2} />
                <AppText size={13} weight="semibold" color={Colors.ok}>
                  주소로 찾았어요
                </AppText>
              </View>
              <Row label="공시가격" note={preset.officialBasis} value={`${formatWon(preset.official_price)} 원`} />
              <Row
                label="실거래가 · 전용 ±10%"
                note={preset.trade_price ? '최근 12개월 신고' : undefined}
                value={preset.trade_price ? `${formatWon(preset.trade_price)} 원` : '표본 부족'}
              />
            </Card>
          ) : (
            <Card style={{ marginTop: 14, gap: 8 }}>
              <TextField
                label="공시가격"
                value={officialText}
                onChange={setOfficialText}
                suffix="만 원"
                keyboardType="number-pad"
                placeholder="15000"
                helper={
                  official
                    ? `= ${formatWon(official)} 원 · 추정 집값 ${formatWon(estimateFromOfficial(official))} 원`
                    : '부동산 공시가격 알리미에서 주소로 찾을 수 있어요'
                }
              />
            </Card>
          )}

          {deposit && official ? <MinimumPreview deposit={deposit} official={official} trade={preset?.trade_price ?? null} /> : null}
        </>
      ) : null}

      {step === 2 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            등기부를 올려 주세요
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            인터넷등기소에서 뗀 등기부의 &quot;주요 등기사항 요약&quot; 페이지만 읽어요. 근저당·압류·신탁을 찾아 판정에 써요.
          </AppText>

          <Pressable accessibilityRole="button" onPress={pickPdf} disabled={registryMode === 'loading'}>
            <DashedBox style={styles.upload}>
              <Icon name="doc" size={28} color={Colors.primary} />
              <AppText size={15} weight="semibold" color={Colors.primary} style={{ marginTop: 8 }}>
                {registryMode === 'loading' ? '읽는 중이에요…' : '등기부 PDF 고르기'}
              </AppText>
              <AppText size={12} color={Colors.textHint} style={{ marginTop: 4 }}>
                {fileName ?? '주민등록번호는 가리고 올려 주세요'}
              </AppText>
            </DashedBox>
          </Pressable>

          <View style={{ gap: 8, marginTop: 12 }}>
            {preset ? <Button variant="outline" height={Touch.min} label="시연 등기부 불러오기" onPress={() => fillRegistry(preset)} /> : null}
            <Button variant="outline" height={Touch.min} label="등기부 내용 직접 입력" onPress={() => fillRegistry(null)} />
          </View>

          <Pressable onPress={() => submit(false)} style={styles.skip}>
            <AppText size={13} weight="semibold" color={Colors.textSub}>
              등기부 없이 결과 보기 (최소 추정치) →
            </AppText>
          </Pressable>
        </>
      ) : null}

      {step === 3 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            {registryMode === 'filled' ? '읽은 내용이 맞는지 확인해 주세요' : '등기부 내용을 입력해 주세요'}
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            판정은 여기서 확인한 값으로 해요. 원문과 다르면 고쳐 주세요.
          </AppText>

          {registryMode === 'filled' && preset ? (
            <Card style={{ marginTop: 14 }}>
              <AppText size={11} color={Colors.textHint}>
                등기부 주요 등기사항 요약 · 원문
              </AppText>
              <View style={styles.source}>
                {preset.registry.source.map((line) => (
                  <AppText key={line} size={12} color={Colors.textCode} leading={1.7}>
                    {line}
                  </AppText>
                ))}
              </View>
            </Card>
          ) : null}

          <Card style={{ marginTop: 12, paddingVertical: 6 }}>
            <View style={{ paddingVertical: 10 }}>
              <TextField label="소유자 이름" value={owner} onChange={setOwner} placeholder="계약 당일 임대인 이름과 대조해요" />
            </View>
            <View style={styles.divider} />
            <ToggleRow label="근저당" sub="을구에 근저당권설정이 있나요?" value={mortgage} onChange={setMortgage}>
              <TextField
                label="채권최고액 (여러 건이면 합계)"
                value={mortgageText}
                onChange={setMortgageText}
                suffix="만 원"
                keyboardType="number-pad"
                error={mortgage && !mortgageAmount ? '채권최고액을 입력해 주세요' : undefined}
                helper={mortgageAmount ? `= ${formatWon(mortgageAmount)} 원` : undefined}
              />
            </ToggleRow>
            <ToggleRow label="압류·가압류·가처분·경매" sub="갑구에 이런 등기가 있나요?" value={seizure} onChange={setSeizure} />
            <ToggleRow label="신탁등기" sub="소유자가 신탁회사인가요?" value={trust} onChange={setTrust} last>
              <ChoiceChips
                label="신탁사 동의서"
                choices={[
                  { value: 'unknown', label: '아직 모름' },
                  { value: 'obtained', label: '받을 수 있음' },
                  { value: 'unavailable', label: '받을 수 없음' },
                ]}
                value={trustConsent}
                onChange={setTrustConsent}
              />
            </ToggleRow>
          </Card>

          <SectionLabel>위반건축물 (건축물대장)</SectionLabel>
          <Card style={{ gap: 12 }}>
            {preset ? (
              <AppText size={13} color={Colors.textSub}>
                주소로 찾은 건축물대장: {preset.building_violation ? '위반건축물' : '위반 표시 없음'}
              </AppText>
            ) : (
              <ChoiceChips
                choices={[
                  { value: 'unknown', label: '모름' },
                  { value: 'no', label: '아님' },
                  { value: 'yes', label: '위반건축물' },
                ]}
                value={violation}
                onChange={setViolation}
              />
            )}
            {violation === 'yes' ? (
              <ChoiceChips
                label="보증기관 상담 결과"
                choices={[
                  { value: 'not_yet', label: '아직 안 함' },
                  { value: 'possible', label: '보증 가능' },
                  { value: 'impossible', label: '보증 불가' },
                ]}
                value={guarantorConsult}
                onChange={setGuarantorConsult}
              />
            ) : null}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}

function Row({ label, note, value }: { label: string; note?: string; value: string }) {
  return (
    <View style={styles.row}>
      <View>
        <AppText size={13} color={Colors.textSub}>
          {label}
        </AppText>
        {note ? (
          <AppText size={11} color={Colors.textHint}>
            {note}
          </AppText>
        ) : null}
      </View>
      <AppText size={14} weight="semibold">
        {value}
      </AppText>
    </View>
  );
}

/** 등기부 전 최소 추정치 미리보기 (근저당 0원으로 계산) */
function MinimumPreview({ deposit, official, trade }: { deposit: number; official: number; trade: number | null }) {
  const estimated = trade ? Math.min(estimateFromOfficial(official), trade) : estimateFromOfficial(official);
  const ratio = deposit / estimated;
  const band = ratioBand(ratio);
  return (
    <View style={[styles.note, { backgroundColor: Colors.card, borderWidth: 1, borderColor: Colors.border }]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <AppText size={13} weight="semibold">
          내 보증금 비율 (최소 추정치)
        </AppText>
        <AppText size={22} weight="bold" color={band.color}>
          {Math.round(ratio * 100)}%
        </AppText>
      </View>
      <AppText size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
        근저당을 0원으로 둔 값이에요. 등기부를 올리면 근저당까지 더해 다시 계산해요.
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  step: { flex: 1, height: 4, borderRadius: 2 },
  preset: {
    flex: 1,
    minHeight: Touch.min,
    paddingHorizontal: 12,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  note: { marginTop: 12, padding: 16, borderRadius: Radius.card },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    marginTop: 10,
  },
  upload: { marginTop: 14, paddingVertical: 28, alignItems: 'center', backgroundColor: Colors.card },
  skip: { minHeight: Touch.min, justifyContent: 'center', marginTop: 8 },
  source: { marginTop: 6, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: Colors.bg, borderRadius: 8 },
  divider: { height: 1, backgroundColor: Colors.divider },
});
