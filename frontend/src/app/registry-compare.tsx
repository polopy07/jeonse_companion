import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField, ToggleRow } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card, DashedBox, Disclaimer, Screen, SectionLabel } from '@/components/layout';
import { Colors, Radius, Touch } from '@/constants/theme';
import {
  ApiError,
  apiEnabled,
  getRegistryCompares,
  parseRegistry,
  postRegistryCompare,
  type ApiContract,
  type ApiRegistryCompare,
  type ApiRegistryCompareItem,
  type ApiRegistryFields,
} from '@/lib/api';
import { useLatestCheck } from '@/lib/check';
import { contractToken, refreshContract, useLatestContract } from '@/lib/contract';
import { formatWon, parseManwon } from '@/lib/format';

const STAGE_LABEL = { contract_day: '계약 당일', balance_day: '잔금일' } as const;

/** verdict.yaml levels (응답에는 다시 판정한 단계 이름만 와서 앞 단계 이름은 여기서) */
const LEVEL_LABEL: Record<string, string> = {
  problem: '문제 항목',
  check_needed: '확인 필요',
  no_problem: '문제 없음',
  not_applicable: '대상 아님',
};

const CHANGE = {
  same: { label: '그대로', color: Colors.textSub, bg: Colors.bg },
  risk: { label: '위험해짐', color: Colors.danger, bg: Colors.dangerBg },
  eased: { label: '줄어듦', color: Colors.ok, bg: Colors.bg },
} as const;

/** 원 → 입력칸의 만 원 */
const manwon = (won: number) => (won ? String(Math.round(won / 10_000)) : '');

/** "2026-11-25" → "2026.11.25" */
const dotDate = (s: string) => s.replaceAll('-', '.');

function valueText(v: ApiRegistryCompareItem['before']): string {
  if (v === null) return '안 올림';
  if (typeof v === 'boolean') return v ? '있음' : '없음';
  return v ? `${formatWon(v)} 원` : '없음';
}

const percent = (r: number | null) => (r === null ? '-' : `${Math.round(r * 100)}%`);

/**
 * 계약 당일·잔금일 등기부 재비교 (FR-023·048, UC-006, POST /api/contracts/{id}/registry-compare).
 * 등기부 요약 PDF를 다시 읽어(또는 직접 입력) 확인한 값을 계약 전 확인과 항목별로 비교하고, 위험해졌으면 보류를 안내한다
 */
export default function RegistryCompareScreen() {
  const latest = useLatestContract();
  const contract = apiEnabled ? latest : null;
  const check = useLatestCheck();
  // 계약 전 확인 때 등기부 (시연에서 "같은 값으로 채우기" → 한 항목만 바꿔 보류 장면)
  const baseline = contract && check?.id === contract.check_id ? (check.input.registry ?? null) : null;
  if (!contract) {
    return (
      <Screen title="등기부 다시 비교">
        <AppText size={14} color={Colors.textSub} leading={1.6} style={{ marginTop: 20 }}>
          비교할 계약이 없어요. 계약 당일 체크에서 할 일을 먼저 만들어 주세요.
        </AppText>
      </Screen>
    );
  }
  return <CompareForm key={contract.id} contract={contract} baseline={baseline} />;
}

function CompareForm({ contract, baseline }: { contract: ApiContract; baseline: ApiRegistryFields | null }) {
  const token = contractToken(contract.id);
  const active = contract.status !== 'cancelled';
  const [filled, setFilled] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [seizure, setSeizure] = useState(false);
  const [mortgage, setMortgage] = useState(false);
  const [mortgageText, setMortgageText] = useState('');
  const [leaseText, setLeaseText] = useState('');
  const [trust, setTrust] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiRegistryCompare | null>(null);
  const [history, setHistory] = useState<ApiRegistryCompare[]>([]);

  useEffect(() => {
    let alive = true;
    getRegistryCompares(contract.id, token)
      .then((list) => alive && setHistory(list))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [contract.id, token]);

  const fill = (f: ApiRegistryFields) => {
    setSeizure(f.seizure);
    setMortgage(f.mortgage);
    setMortgageText(manwon(f.mortgage_amount));
    setLeaseText(manwon(f.lease_amount));
    setTrust(f.trust);
    setFilled(true);
    setError(null);
  };

  const pickPdf = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
    if (res.canceled) return;
    const asset = res.assets[0];
    setFileName(asset.name);
    setParsing(true);
    setError(null);
    try {
      const r = await parseRegistry(asset);
      // 같은 보증금을 가리키는 임차권·전세권(전세권과 그 임차권등기)은 한 번만 (계약 전 확인과 같음)
      const leases = (r.leases ?? []).filter((l) => l.same_deposit_as == null).reduce((s, l) => s + (l.amount ?? 0), 0);
      fill({ ...r.fields, lease_amount: r.fields.lease_amount ?? leases });
      setWarnings(r.warnings);
    } catch (e) {
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '등기부를 읽지 못했어요');
    } finally {
      setParsing(false);
    }
  };

  const mortgageAmount = parseManwon(mortgageText);
  const leaseAmount = parseManwon(leaseText) ?? 0;
  const canSubmit = active && filled && (!mortgage || !!mortgageAmount) && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const r = await postRegistryCompare(contract.id, token, {
        seizure,
        mortgage,
        mortgage_amount: mortgage ? (mortgageAmount ?? 0) : 0,
        lease_amount: leaseAmount,
        trust,
      });
      setResult(r);
      setHistory((h) => [...h, r]);
      // 새로 걸린 연동 규칙은 할 일에 더해지고 경보도 다시 계산된다
      refreshContract().catch(() => {});
    } catch (e) {
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '비교하지 못했어요');
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return <CompareResult result={result} onAgain={() => setResult(null)} />;
  }

  return (
    <Screen
      title="등기부 다시 비교"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            {error ??
              (active
                ? '계약 전 확인 때 등기부와 항목별로 비교해요. 위험해졌으면 보류를 안내해요.'
                : '무산된 계약이라 새로 비교할 수 없어요. 지난 비교는 아래에서 볼 수 있어요.')}
          </Disclaimer>
          <Button
            label={submitting ? '비교하는 중…' : '계약 전 확인과 비교하기'}
            onPress={canSubmit ? submit : undefined}
            style={{ opacity: canSubmit ? 1 : 0.4 }}
          />
        </>
      }>
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
        계약 당일(점검한 날과 계약일이 다를 때)과 잔금일 아침에 등기부 요약을 다시 떼어 올려 주세요. 그사이 근저당·압류가
        새로 생겼는지 봐요.
      </AppText>

      {active ? (
        <>
          <Pressable accessibilityRole="button" onPress={pickPdf} disabled={parsing}>
            <DashedBox style={styles.upload}>
              <Icon name="doc" size={28} color={Colors.primary} />
              <AppText size={15} weight="semibold" color={Colors.primary} style={{ marginTop: 8 }}>
                {parsing ? '읽는 중이에요…' : '오늘 뗀 등기부 PDF 고르기'}
              </AppText>
              <AppText size={12} color={Colors.textHint} style={{ marginTop: 4 }}>
                {fileName ?? '부동산정보요약 PDF (요약이 붙은 등기사항증명서도 돼요)'}
              </AppText>
            </DashedBox>
          </Pressable>
          <View style={{ gap: 8, marginTop: 12 }}>
            {baseline ? (
              <Button
                variant="outline"
                height={Touch.min}
                label="계약 전 확인 때 값으로 채우기 (시연)"
                onPress={() => fill(baseline)}
              />
            ) : null}
            <Button
              variant="outline"
              height={Touch.min}
              label="등기부 내용 직접 입력"
              onPress={() => fill({ seizure: false, mortgage: false, mortgage_amount: 0, lease_amount: 0, trust: false })}
            />
          </View>
        </>
      ) : null}

      {filled ? (
        <>
          <SectionLabel>읽은 내용이 맞는지 확인해 주세요</SectionLabel>
          {warnings.map((w) => (
            <AppText key={w} size={12} color={Colors.textSub} leading={1.6} style={{ marginBottom: 6 }}>
              · {w}
            </AppText>
          ))}
          <Card style={{ paddingVertical: 6 }}>
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
            <View style={styles.leaseRow}>
              <TextField
                label="임차권·전세권 보증금 합계 (없으면 비워 두기)"
                value={leaseText}
                onChange={setLeaseText}
                suffix="만 원"
                keyboardType="number-pad"
                helper={leaseAmount ? `= ${formatWon(leaseAmount)} 원 · 내 계약이면 넣지 마세요` : undefined}
              />
            </View>
            <ToggleRow label="압류·가압류·가처분·경매" sub="갑구에 이런 등기가 있나요?" value={seizure} onChange={setSeizure} />
            <ToggleRow label="신탁등기" sub="소유자가 신탁회사인가요?" value={trust} onChange={setTrust} last />
          </Card>
        </>
      ) : null}

      {history.length ? (
        <>
          <SectionLabel>지난 비교</SectionLabel>
          <Card style={{ paddingVertical: 4 }}>
            {[...history].reverse().map((h, i) => (
              <Pressable
                key={h.id}
                accessibilityRole="button"
                onPress={() => setResult(h)}
                style={[styles.historyRow, i < history.length - 1 && styles.divider]}>
                <AppText size={13} style={{ flex: 1 }}>
                  {dotDate(h.compared_on)} · {STAGE_LABEL[h.stage]}
                </AppText>
                <AppText size={12} weight="semibold" color={h.hold ? Colors.danger : h.changed ? Colors.caution : Colors.ok}>
                  {h.hold ? '보류 안내' : h.changed ? '변동 있음' : '그대로'}
                </AppText>
              </Pressable>
            ))}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}

/** 비교 결과: 보류 안내 → 항목별 변동 → 근저당 금액 필수 확인 → 다시 판정한 단계 */
function CompareResult({ result: r, onAgain }: { result: ApiRegistryCompare; onAgain: () => void }) {
  const stage = STAGE_LABEL[r.stage];
  return (
    <Screen
      title="등기부 다시 비교"
      footer={
        <View style={{ gap: 8 }}>
          <Button label="할 일로 돌아가기" onPress={() => router.back()} />
          <Button variant="outline" label="다시 비교하기" onPress={onAgain} />
        </View>
      }>
      <AppText size={13} color={Colors.textSub} style={{ marginTop: 6 }}>
        {dotDate(r.compared_on)} · {stage} 등기부
      </AppText>

      {r.hold ? (
        <View style={[styles.banner, { backgroundColor: Colors.dangerBg }]}>
          <AppText size={18} weight="bold" color={Colors.dangerDeep}>
            {r.advice}
          </AppText>
          <AppText size={13} color={Colors.dangerText} leading={1.6} style={{ marginTop: 6 }}>
            {r.hint}
          </AppText>
        </View>
      ) : (
        <View style={[styles.banner, { backgroundColor: Colors.bg }]}>
          <AppText size={16} weight="bold" color={Colors.ok}>
            {r.changed ? '바뀐 항목이 있지만 위험해지지는 않았어요' : '계약 전 확인 때와 같아요'}
          </AppText>
          <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
            {r.stage === 'balance_day'
              ? '잔금을 치르고 오늘 전입신고까지 마쳐 주세요. 3번 할 일은 등기부 화면 사진으로 끝내요.'
              : '계약을 진행해도 돼요. 잔금일 아침에 한 번 더 비교해요.'}
          </AppText>
        </View>
      )}

      {r.baseline_missing ? (
        <AppText size={12} color={Colors.caution} leading={1.6} style={{ marginTop: 10 }}>
          계약 전 확인에서 등기부를 올리지 않아, 오늘 등기부에 있는 것은 모두 새로 생긴 것으로 봤어요.
        </AppText>
      ) : null}

      <SectionLabel>항목별 비교</SectionLabel>
      <Card style={{ paddingVertical: 4 }}>
        <View style={[styles.itemRow, styles.divider]}>
          <AppText size={11} color={Colors.textHint} style={{ flex: 1 }}>
            항목
          </AppText>
          <AppText size={11} color={Colors.textHint}>
            계약 전 → 오늘
          </AppText>
        </View>
        {r.items.map((item, i) => (
          <View key={item.field} style={[styles.itemRow, i < r.items.length - 1 && styles.divider]}>
            <AppText size={13} style={{ flex: 1 }}>
              {item.label}
            </AppText>
            <View style={{ alignItems: 'flex-end', gap: 4 }}>
              <AppText size={13} weight={item.change === 'same' ? 'regular' : 'semibold'}>
                {valueText(item.before)} → {valueText(item.after)}
              </AppText>
              <View style={[styles.badge, { backgroundColor: CHANGE[item.change].bg }]}>
                <AppText size={11} weight="semibold" color={CHANGE[item.change].color}>
                  {CHANGE[item.change].label}
                </AppText>
              </View>
            </View>
          </View>
        ))}
      </Card>

      {r.mortgage_check ? (
        <Card style={{ marginTop: 12, borderColor: Colors.cautionStrong, borderWidth: 1.5 }}>
          <AppText size={13} weight="bold" color={Colors.caution}>
            근저당 금액 비교 (필수 확인)
          </AppText>
          <AppText size={13} leading={1.6} style={{ marginTop: 4 }}>
            계약 전 {valueText(r.mortgage_check.before)} → 오늘 {valueText(r.mortgage_check.after)}
          </AppText>
          <AppText size={12} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
            계약 전에 근저당이 있던 집이라 채권최고액이 늘지 않았는지 꼭 봐요.
          </AppText>
        </Card>
      ) : null}

      <SectionLabel>오늘 등기부로 다시 판정</SectionLabel>
      <Card style={{ gap: 6 }}>
        <View style={styles.rowBetween}>
          <AppText size={13} color={Colors.textSub}>
            판정
          </AppText>
          <AppText size={13} weight="semibold">
            {LEVEL_LABEL[r.level_before] ?? r.level_before} → {r.level_after_label}
          </AppText>
        </View>
        <View style={styles.rowBetween}>
          <AppText size={13} color={Colors.textSub}>
            내 보증금 비율
          </AppText>
          <AppText size={13} weight="semibold">
            {percent(r.deposit_ratio_before)} → {percent(r.deposit_ratio_after)}
          </AppText>
        </View>
        <AppText size={12} color={Colors.textHint} leading={1.6}>
          계약 전 확인 때 보증금·공시가격에 등기부만 바꿔 계산했어요. 새로 걸린 항목은 할 일에 더하고 경보도 다시 계산해요.
        </AppText>
      </Card>

      <View style={{ flex: 1 }} />
      <Disclaimer>정보 제공이며 보증하지 않습니다.</Disclaimer>
    </Screen>
  );
}

const styles = StyleSheet.create({
  upload: { marginTop: 14, alignItems: 'center', paddingVertical: 22 },
  leaseRow: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: Colors.divider },
  historyRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  banner: { marginTop: 12, padding: 16, borderRadius: Radius.card },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10 },
  badge: { paddingVertical: 2, paddingHorizontal: 8, borderRadius: 999 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
});
