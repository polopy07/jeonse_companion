import * as DocumentPicker from 'expo-document-picker';
import { Redirect, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ChoiceChips, TextField, Toggle, ToggleRow } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, DashedBox, DemoTag, Screen, SectionLabel } from '@/components/layout';
import { OfficialPriceFinder, type FoundPrice } from '@/components/official-price';
import { ratioBand } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { demoHouseFromApi, demoHouses, type DemoHouse } from '@/data/demo';
import { ApiError, apiEnabled, getDemoHouses, parseRegistry, postCheck, type ApiRegistryParseResult } from '@/lib/api';
import {
  checkViewFromApi,
  estimateFromOfficial,
  housingTypes,
  isNotApplicable,
  runCheckLocal,
  setLatestCheck,
  type CheckInput,
  type CheckView,
  type GuarantorConsult,
  type HousingType,
  type RegistryLease,
  type TrustConsent,
} from '@/lib/check';
import { dottedDate, todayDate } from '@/lib/clock';
import { hasConsent, useConsent } from '@/lib/consent';
import { formatWon, parseManwon, parseNumber } from '@/lib/format';

const steps = ['집 정보', '집값·보증금', '등기부', '확인·수정'];

type Violation = 'unknown' | 'no' | 'yes';
// filled = 시연 등기부, parsed = 서버가 PDF에서 읽은 값, manual = 직접 입력
type RegistryMode = 'none' | 'loading' | 'filled' | 'parsed' | 'manual';
/** 등기부에서 읽은 임차권·전세권 한 건. included = 선순위 채권에 넣음 (기본), amountText = 보증금을 못 읽었을 때 직접 입력 */
type LeaseRow = RegistryLease & { included: boolean; amountText: string };

/** 등기부 올리기 안내 (인터넷등기소 "부동산정보요약"을 PDF로 저장) */
const uploadSteps = [
  '인터넷등기소(iros.go.kr)에서 이 집 등기부를 열람해요 (700원)',
  '열람 화면에서 "부동산정보요약"을 눌러요',
  '인쇄 → "PDF로 저장"으로 저장해요',
  '아래에서 저장한 PDF를 골라요',
];

/** 조회일 (가상 날짜면 그날) */
const todayText = () => dottedDate(todayDate());

const toManwonText = (won: number) => (won ? String(Math.round(won / 10_000)) : '');

/**
 * 계약 전 확인 입력 (UI-01 입력 부분, FR-001~006). 집 정보 → 집값·보증금 → 등기부 → 추출 결과 확인·수정 → 결과.
 * 다가구·단독은 점검 대상이 아니라 1단계에서 보증금까지 받고 바로 결과로 간다
 */
/** 서비스 안내·개인정보 동의를 받은 뒤에만 계약 전 확인을 시작한다 (처음 한 번, 안내 버전이 바뀌면 다시) */
export default function PrecheckScreen() {
  const consent = useConsent();
  if (consent === undefined) return null; // 휴대폰에서 불러오는 중
  if (!hasConsent(consent)) return <Redirect href={{ pathname: '/consent', params: { next: 'precheck' } }} />;
  return <PrecheckForm />;
}

function PrecheckForm() {
  const [step, setStep] = useState(0);
  const [preset, setPreset] = useState<DemoHouse | null>(null);
  const [houses, setHouses] = useState<DemoHouse[]>(demoHouses);

  // 시연 집은 서버 값(GET /api/demo-houses, 경보 계산 정답표)으로. 못 받으면 앱에 든 같은 값을 쓴다
  useEffect(() => {
    if (!apiEnabled) return;
    let alive = true;
    getDemoHouses()
      .then((r) => {
        // 계약 당일 장면이 있는 집(빌라)을 앞에
        const list = r.houses.map(demoHouseFromApi).sort((a, b) => Number(!!b.contractDay) - Number(!!a.contractDay));
        if (alive && list.length) setHouses(list);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // ① 집 정보
  const [address, setAddress] = useState('');
  const [housingType, setHousingType] = useState<HousingType | null>(null);
  const [depositText, setDepositText] = useState('');
  const [areaText, setAreaText] = useState('');
  // 전용면적을 주소로 찾은 공시가격에서 채웠는지 (그러면 다른 호를 고를 때 다시 채운다)
  const [areaAuto, setAreaAuto] = useState(false);

  // ② 공시가격 (시연 집은 미리 매칭, 그 밖의 주소는 주소로 찾거나 직접 입력)
  const [officialText, setOfficialText] = useState('');
  const [found, setFound] = useState<FoundPrice | null>(null);

  // ③④ 등기부
  const [registryMode, setRegistryMode] = useState<RegistryMode>('none');
  const [fileName, setFileName] = useState<string | null>(null);
  const [owner, setOwner] = useState('');
  const [seizure, setSeizure] = useState(false);
  const [mortgage, setMortgage] = useState(false);
  const [mortgageText, setMortgageText] = useState('');
  const [trust, setTrust] = useState(false);
  const [leases, setLeases] = useState<LeaseRow[]>([]);
  const [leaseOn, setLeaseOn] = useState(false); // 직접 입력: 임차권·전세권 등기 있음
  const [leaseText, setLeaseText] = useState('');
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [registryWarnings, setRegistryWarnings] = useState<string[]>([]);
  const [sourceLines, setSourceLines] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [trustConsent, setTrustConsent] = useState<TrustConsent>('unknown');
  const [violation, setViolation] = useState<Violation>('unknown');
  const [guarantorConsult, setGuarantorConsult] = useState<GuarantorConsult>('not_yet');

  const deposit = parseManwon(depositText);
  // 주소로 찾은 값은 원 단위 그대로 (입력 칸은 만 원 단위라 반올림됨)
  const official = preset ? preset.official_price : found ? found.price : parseManwon(officialText);
  const mortgageAmount = parseManwon(mortgageText);
  // 임차권·전세권 보증금은 선순위 채권. 등기부에서 읽은 목록이 있으면 넣은 항목만, 없으면 직접 입력한 합계
  const leaseRowAmount = (l: LeaseRow) => l.amount ?? parseManwon(l.amountText);
  const manualLeaseAmount = parseManwon(leaseText);
  const leaseAmount = leases.length
    ? leases.reduce((sum, l) => sum + (l.included ? (leaseRowAmount(l) ?? 0) : 0), 0)
    : leaseOn
      ? (manualLeaseAmount ?? 0)
      : 0;
  const leasesReady = leases.length ? leases.every((l) => !l.included || !!leaseRowAmount(l)) : !leaseOn || !!manualLeaseAmount;
  const updateLease = (i: number, patch: Partial<LeaseRow>) =>
    setLeases((rows) => rows.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const na = housingType !== null && isNotApplicable(housingType);

  const fillPreset = (h: DemoHouse) => {
    setPreset(h);
    setAddress(h.address);
    setHousingType(h.housing_type);
    setDepositText(h.depositManwon);
    setAreaText(h.area);
    setAreaAuto(false);
    setOfficialText(toManwonText(h.official_price));
    setFound(null);
    setViolation(h.building_violation === null ? 'unknown' : h.building_violation ? 'yes' : 'no');
    setRegistryMode('none');
    setFileName(null);
  };

  // 주소를 직접 고치면 시연 집 매칭을 푼다
  const editAddress = (v: string) => {
    setAddress(v);
    if (preset && v !== preset.address) setPreset(null);
    setFound(null); // 주소를 바꾸면 찾은 공시가격의 출처 표시를 남기지 않는다 (입력 칸 값은 그대로)
  };

  const editHousingType = (t: HousingType) => {
    setHousingType(t);
    if (t !== housingType) setFound(null); // 유형이 바뀌면 찾은 공시가격(공동주택가격) 표시를 풀고 칸 값만 남긴다
  };

  const editArea = (v: string) => {
    setAreaText(v);
    setAreaAuto(false);
  };

  const fillFound = (p: FoundPrice) => {
    setFound(p);
    setOfficialText(toManwonText(p.price));
    // 비어 있거나 앞서 찾은 값으로 채운 면적만 바꾼다 (직접 넣은 면적은 그대로)
    if (p.area && (!areaText.trim() || areaAuto)) {
      setAreaText(String(p.area));
      setAreaAuto(true);
    }
  };

  const editOfficial = (v: string) => {
    setOfficialText(v);
    setFound(null);
  };

  const fillRegistry = (h: DemoHouse | null) => {
    if (h) {
      setOwner(h.registry.owner);
      setSeizure(h.registry.seizure);
      setMortgage(h.registry.mortgage);
      setMortgageText(toManwonText(h.registry.mortgage_amount));
      setTrust(h.registry.trust);
      setLeases(h.registry.leases.map((l) => ({ ...l, included: l.same_deposit_as == null, amountText: '' })));
      setRegistryWarnings(h.registry.warnings);
      setRegistryMode('filled');
    } else {
      setLeases([]);
      setRegistryWarnings([]);
      setRegistryMode('manual');
    }
    setLeaseOn(false);
    setLeaseText('');
    setSourceLines([]);
    setStep(3);
  };

  /** 서버가 PDF에서 읽은 값으로 확인 화면을 채운다 (FR-005~006) */
  const fillFromParse = (r: ApiRegistryParseResult) => {
    setOwner(r.owners.join(', '));
    setSeizure(r.fields.seizure);
    setMortgage(r.fields.mortgage);
    setMortgageText(toManwonText(r.fields.mortgage_amount));
    setTrust(r.fields.trust);
    setLeases((r.leases ?? []).map((l) => ({ ...l, included: l.same_deposit_as == null, amountText: '' })));
    setLeaseOn(false);
    setLeaseText('');
    setSourceLines([...r.seizures, ...r.trusts, ...r.mortgages, ...(r.leases ?? []), ...r.others].map((e) => e.text));
    setRegistryWarnings(r.warnings);
    setRegistryMode('parsed');
    setStep(3);
  };

  const pickPdf = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
    if (res.canceled) return;
    const asset = res.assets[0];
    setFileName(asset.name);
    setRegistryError(null);
    setRegistryMode('loading');
    if (!apiEnabled) {
      // 서버 주소가 없으면: 시연 집이면 시연 등기부 값으로, 아니면 직접 입력으로 넘긴다
      setTimeout(() => fillRegistry(preset), 600);
      return;
    }
    try {
      fillFromParse(await parseRegistry(asset));
    } catch (e) {
      setRegistryMode('none');
      setRegistryError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '등기부를 읽지 못했어요');
    }
  };

  const submit = async (withRegistry: boolean) => {
    if (!housingType || !deposit || submitting) return;
    // 시연 집은 서버가 단지로 실거래를 찾는다 (주택 유형을 바꿨으면 단지 매칭은 쓰지 않음)
    const complex = preset?.complex && preset.housing_type === housingType ? preset.complex : null;
    const input: CheckInput = {
      housing_type: housingType,
      deposit,
      official_price: official,
      trade_price: apiEnabled && complex ? null : (preset?.trade_price ?? null),
      complex,
      exclusive_area: parseNumber(areaText),
      registry: withRegistry
        ? { seizure, mortgage, mortgage_amount: mortgage ? (mortgageAmount ?? 0) : 0, lease_amount: leaseAmount, trust }
        : null,
      trust_consent: trust ? trustConsent : 'unknown',
      building_violation: violation === 'unknown' ? null : violation === 'yes',
      guarantor_consult: violation === 'yes' ? guarantorConsult : 'not_yet',
    };
    const typeLabel = housingTypes.find((t) => t.value === housingType)?.label ?? '';
    const label = `${preset ? preset.label : address.trim()} · ${typeLabel}`;
    const ownerName = withRegistry && owner.trim() ? owner.trim() : null;
    const virtualMortgage = withRegistry && registryMode === 'filled' && mortgage && !!preset?.registry.virtualMortgage;

    let view: CheckView;
    if (apiEnabled) {
      setSubmitting(true);
      setSubmitError(null);
      try {
        view = checkViewFromApi(await postCheck(input), input, label, todayText(), ownerName);
      } catch (e) {
        if (!(e instanceof ApiError) || e.code !== 'NETWORK_ERROR') {
          // 입력 오류 등 서버가 답한 오류는 앱 계산으로 덮지 않고 보여 준다
          setSubmitError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '판정을 받지 못했어요');
          return;
        }
        const localInput = { ...input, trade_price: preset?.trade_price ?? null };
        view = { ...runCheckLocal(localInput, label, todayText(), ownerName), notice: '서버에 연결하지 못해 앱에서 임시로 계산했어요' };
      } finally {
        setSubmitting(false);
      }
    } else {
      view = runCheckLocal(input, label, todayText(), ownerName);
    }
    const viewSource = !withRegistry ? [] : registryMode === 'filled' && preset ? preset.registry.source : sourceLines;
    setLatestCheck({ ...view, virtualMortgage, sourceLines: viewSource, demoDates: preset?.contractDay ?? undefined });
    router.push('/check');
  };

  // 공동주택가격으로 공시가격을 찾을 수 있는 유형
  const findable = housingType === 'apartment' || housingType === 'row_house';

  const depositField = (
    <TextField
      label="보증금"
      value={depositText}
      onChange={setDepositText}
      suffix="만 원"
      keyboardType="number-pad"
      placeholder="14000"
      helper={deposit ? `= ${formatWon(deposit)} 원` : '계약서의 전세 보증금'}
    />
  );

  // 단계별로 다음으로 넘어갈 수 있는지
  const canNext = [
    address.trim().length > 0 && housingType !== null && (!na || !!deposit),
    !!official && !!deposit,
    false, // 등기부 단계는 아래 버튼들로 넘어간다
    (!mortgage || !!mortgageAmount) && leasesReady,
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
          label={submitting ? '판정 받는 중…' : step === 3 || (step === 0 && na) ? '결과 보기' : '다음'}
          onPress={canNext && !submitting ? next : undefined}
          style={{ flex: 1, opacity: canNext && !submitting ? 1 : 0.4 }}
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
        {submitError ? (
          <AppText size={13} color={Colors.danger} leading={1.6} style={{ marginTop: 8 }}>
            {submitError}
          </AppText>
        ) : null}
      </View>

      {step === 0 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            어떤 집을 보고 있나요?
          </AppText>

          <SectionLabel style={{ marginTop: 14 }}>시연 집으로 채우기</SectionLabel>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {houses.map((h) => {
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
            <ChoiceChips label="주택 유형" choices={housingTypes} value={housingType} onChange={editHousingType} />
            {/* 다가구·단독은 집값 단계가 없어 여기서 보증금을 받는다 (신고 대상 판별·할 일 관리) */}
            {na ? depositField : null}
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
            집값과 보증금을 확인해요
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
              {areaText ? <Row label="전용면적" value={`${areaText}㎡`} /> : null}
              {apiEnabled && preset.complex ? (
                <Row label="실거래가 · 전용 ±10%" note="최근 12개월 신고" value="판정 때 단지에서 찾아요" />
              ) : (
                <Row
                  label="실거래가 · 전용 ±10%"
                  note={preset.trade_price ? '최근 12개월 신고' : undefined}
                  value={preset.trade_price ? `${formatWon(preset.trade_price)} 원` : '표본 부족'}
                />
              )}
            </Card>
          ) : (
            <>
              {/* 주소로 찾기는 공동주택가격이 있는 아파트·연립다세대만 (오피스텔은 공동주택가격 대상이 아님) */}
              {apiEnabled && findable ? <OfficialPriceFinder address={address} onFound={fillFound} /> : null}
              <Card style={{ marginTop: 14, gap: 12 }}>
                <TextField
                  label="공시가격"
                  value={officialText}
                  onChange={editOfficial}
                  suffix="만 원"
                  keyboardType="number-pad"
                  placeholder="15000"
                  helper={
                    official
                      ? `= ${formatWon(official)} 원 · 추정 집값 ${formatWon(estimateFromOfficial(official))} 원`
                      : findable
                        ? '위에서 찾거나 부동산 공시가격 알리미에서 찾아 넣어요'
                        : '오피스텔은 주소로 찾을 수 없어요. 직접 넣어 주세요'
                  }
                />
                {found ? (
                  <AppText size={11} color={Colors.textHint} leading={1.5}>
                    {found.label} · {found.source}
                  </AppText>
                ) : null}
                {found?.area ? (
                  <Row label="전용면적" note="공동주택가격" value={`${found.area}㎡`} />
                ) : (
                  <TextField
                    label="전용면적 (선택)"
                    value={areaText}
                    onChange={editArea}
                    suffix="㎡"
                    keyboardType="decimal-pad"
                    placeholder="49.5"
                    helper="같은 단지 실거래·주변 전세 시세를 찾을 때 써요"
                  />
                )}
              </Card>
            </>
          )}

          <Card style={{ marginTop: 12 }}>{depositField}</Card>

          {deposit && official ? <MinimumPreview deposit={deposit} official={official} trade={preset?.trade_price ?? null} /> : null}
        </>
      ) : null}

      {step === 2 ? (
        <>
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            등기부를 올려 주세요
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            인터넷등기소 &quot;부동산정보요약&quot;만 읽어요. 근저당·압류·신탁·임차권을 찾아 판정에 써요.
          </AppText>

          <Card style={{ marginTop: 14, gap: 10 }}>
            <AppText size={13} weight="semibold">
              등기부 올리는 방법
            </AppText>
            {uploadSteps.map((text, i) => (
              <View key={text} style={{ flexDirection: 'row', gap: 10 }}>
                <View style={styles.stepNo}>
                  <AppText size={11} weight="bold" color={Colors.primary}>
                    {i + 1}
                  </AppText>
                </View>
                <AppText size={13} color={Colors.textSub} leading={1.6} style={{ flex: 1 }}>
                  {text}
                </AppText>
              </View>
            ))}
          </Card>

          <Pressable accessibilityRole="button" onPress={pickPdf} disabled={registryMode === 'loading'}>
            <DashedBox style={styles.upload}>
              <Icon name="doc" size={28} color={Colors.primary} />
              <AppText size={15} weight="semibold" color={Colors.primary} style={{ marginTop: 8 }}>
                {registryMode === 'loading' ? '읽는 중이에요…' : '등기부 PDF 고르기'}
              </AppText>
              <AppText size={12} color={Colors.textHint} style={{ marginTop: 4 }}>
                {fileName ?? '부동산정보요약 PDF (요약이 붙은 등기사항증명서도 돼요)'}
              </AppText>
            </DashedBox>
          </Pressable>
          {registryError ? (
            <AppText size={13} color={Colors.danger} leading={1.6} style={{ marginTop: 8 }}>
              {registryError}
            </AppText>
          ) : null}

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
            {registryMode === 'filled' || registryMode === 'parsed' ? '읽은 내용이 맞는지 확인해 주세요' : '등기부 내용을 입력해 주세요'}
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            판정은 여기서 확인한 값으로 해요. 원문과 다르면 고쳐 주세요.
          </AppText>

          {registryMode === 'filled' && preset ? (
            <Card style={{ marginTop: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <AppText size={11} color={Colors.textHint}>
                  등기부 요약 · 원문
                </AppText>
                {preset.registry.virtualMortgage ? <DemoTag label="시연용 가상 근저당" /> : null}
              </View>
              <View style={styles.source}>
                {preset.registry.source.map((line) => (
                  <AppText key={line} size={12} color={Colors.textCode} leading={1.7}>
                    {line}
                  </AppText>
                ))}
              </View>
            </Card>
          ) : null}

          {registryMode === 'parsed' ? (
            <Card style={{ marginTop: 14 }}>
              <AppText size={11} color={Colors.textHint}>
                등기부 요약 · 읽은 원문
              </AppText>
              <View style={styles.source}>
                {(sourceLines.length ? sourceLines : ['갑구·을구 기록사항 없음']).map((line, i) => (
                  <AppText key={`${i}-${line}`} size={12} color={Colors.textCode} leading={1.7}>
                    {line}
                  </AppText>
                ))}
              </View>
              {registryWarnings.map((w) => (
                <AppText key={w} size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
                  · {w}
                </AppText>
              ))}
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
            {leases.length ? (
              <View style={[styles.leases, styles.dividerBottom]}>
                <AppText size={14} weight="semibold">
                  임차권·전세권 {leases.length}건
                </AppText>
                <AppText size={12} color={Colors.textHint} leading={1.6}>
                  앞 세입자 보증금이라 내 보증금보다 먼저 돌려받아요. 선순위 채권에 넣었어요. 이미 돌려받았거나 내 계약이면 빼 주세요.
                </AppText>
                {leases.map((l, i) => {
                  const amount = leaseRowAmount(l);
                  return (
                    <View key={l.rank} style={styles.leaseItem}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: Touch.min }}>
                        <View style={{ flex: 1 }}>
                          <AppText size={13} weight="semibold" color={l.included ? Colors.text : Colors.textHint}>
                            을구 {l.rank} · {l.purpose}
                          </AppText>
                          <AppText size={12} color={Colors.textHint} style={{ marginTop: 2 }}>
                            {l.included ? '선순위 채권에 넣음' : '뺐어요 · 비율에 넣지 않아요'}
                            {l.amount ? ` · 보증금 ${formatWon(l.amount)} 원` : ''}
                            {l.holder ? ` · ${l.holder}` : ''}
                          </AppText>
                        </View>
                        <Toggle
                          value={l.included}
                          onChange={(v) => updateLease(i, { included: v })}
                          label={`을구 ${l.rank} ${l.purpose} 보증금을 선순위 채권에 넣기`}
                        />
                      </View>
                      {l.included && l.amount === null ? (
                        <TextField
                          label="보증금 (읽지 못했어요)"
                          value={l.amountText}
                          onChange={(v) => updateLease(i, { amountText: v })}
                          suffix="만 원"
                          keyboardType="number-pad"
                          error={amount ? undefined : '보증금을 입력하거나 빼 주세요'}
                          helper={amount ? `= ${formatWon(amount)} 원` : undefined}
                        />
                      ) : null}
                    </View>
                  );
                })}
                <AppText size={12} color={Colors.textSub}>
                  선순위 채권에 넣은 보증금 합계 {formatWon(leaseAmount)} 원
                </AppText>
              </View>
            ) : (
              <ToggleRow
                label="임차권·전세권"
                sub="을구에 임차권설정·주택임차권·전세권설정이 있나요?"
                value={leaseOn}
                onChange={setLeaseOn}>
                <TextField
                  label="보증금 (여러 건이면 합계)"
                  value={leaseText}
                  onChange={setLeaseText}
                  suffix="만 원"
                  keyboardType="number-pad"
                  error={leaseOn && !manualLeaseAmount ? '보증금을 입력해 주세요' : undefined}
                  helper={
                    manualLeaseAmount
                      ? `= ${formatWon(manualLeaseAmount)} 원 · 이미 돌려받았거나 내 계약이면 넣지 마세요`
                      : undefined
                  }
                />
              </ToggleRow>
            )}
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
            {preset && preset.building_violation !== null ? (
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
        근저당을 0원으로 둔 값이에요. 등기부를 올리면 근저당·임차권·전세권 보증금까지 더해 다시 계산해요.
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
  dividerBottom: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  leases: { paddingVertical: 12, gap: 8 },
  leaseItem: { gap: 8, paddingTop: 4 },
  stepNo: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: Colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
});
