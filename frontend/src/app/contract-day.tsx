import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Card, Disclaimer, Screen, StepProgress } from '@/components/layout';
import { useCopy } from '@/components/verdict';
import { Colors, Radius, Touch } from '@/constants/theme';
import { checkResult, siteCheckDemo } from '@/data/demo';
import { ApiError, apiEnabled, getSpecialTerms } from '@/lib/api';
import { useLatestCheck } from '@/lib/check';
import { siteCheckItems, useSiteCheck } from '@/lib/site-check';
import {
  setSpecialTermResults,
  termsFor,
  termsFromApi,
  useSpecialTermResults,
  type ShownTerm,
  type SpecialTermResult,
} from '@/lib/special-terms';

type Picks = Partial<Record<string, SpecialTermResult>>;
type RemoteGuide = { terms: ShownTerm[]; warnings: string[]; checks: string[] };

/** UI-03 계약 당일 체크: 현장 확인 → 특약 예시 → "넣음/거절당함" 기록 (특약 반영 분기) */
export default function ContractDayScreen() {
  const check = useLatestCheck() ?? checkResult;
  // 서버 판정이면 GET /api/checks/{id}/special-terms, 앱에서 계산한 결과면 앱 안 규칙으로 고른다 (기준은 같음)
  const [remote, setRemote] = useState<RemoteGuide | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    if (!apiEnabled || check.id === null || check.block_payment) return;
    let alive = true;
    getSpecialTerms(check.id)
      .then((r) => alive && setRemote({ terms: termsFromApi(r), warnings: r.warnings, checks: r.checks }))
      .catch((e) => alive && setLoadError(e instanceof ApiError ? e.message : '특약 예시를 받지 못했어요'));
    return () => {
      alive = false;
    };
  }, [check.id, check.block_payment]);
  const terms = check.block_payment ? [] : (remote?.terms ?? termsFor(check.matched));
  // 처음에는 아무것도 고르지 않은 상태. 전에 골랐던 값이 있으면 이어서 보여 준다
  const [picks, setPicks] = useState<Picks>(useSpecialTermResults());
  // 현장 확인을 거치지 않고 열면(시연) 모두 확인한 시연 값을 보여 준다
  const items = siteCheckItems(useSiteCheck() ?? siteCheckDemo);

  const allPicked = !check.block_payment && terms.every((t) => picks[t.id]);
  const next = () => {
    setSpecialTermResults(Object.fromEntries(terms.map((t) => [t.id, picks[t.id]])) as Picks);
    router.push('/contract-dates');
  };

  return (
    <Screen
      title="계약 당일 체크"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            {check.block_payment
              ? '"문제 항목" 판정이라 패키지를 시작할 수 없어요.'
              : terms.length && !allPicked
                ? '특약마다 "넣음" 또는 "거절당함"을 골라 주세요.'
                : '특약 예시는 공공 자료를 바탕으로 한 참고 문구이며 법률 자문이 아닙니다.'}
          </Disclaimer>
          <Button
            label="다음 · 계약 날짜 입력"
            onPress={allPicked ? next : undefined}
            style={{ opacity: allPicked ? 1 : 0.4 }}
          />
        </>
      }>
      <StepProgress current={3} total={5} label="특약 반영 기록" />

      <Pressable accessibilityRole="button" accessibilityLabel="현장 확인 다시 보기" onPress={() => router.navigate('/site-check')}>
        <Card style={{ marginTop: 14, paddingVertical: 14, gap: 8, borderRadius: Radius.sm }}>
          {items.map((c) => (
            <View key={c.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Icon name={c.checked ? 'check' : 'info'} size={18} color={c.checked ? Colors.ok : Colors.caution} strokeWidth={2.2} />
              <AppText size={14} color={c.checked ? Colors.text : Colors.caution} style={{ flex: 1 }}>
                {c.checked ? c.label : `확인 안 함 · ${c.label}`}
              </AppText>
            </View>
          ))}
        </Card>
      </Pressable>

      {check.block_payment ? (
        <View style={[styles.result, { backgroundColor: Colors.dangerBg }]}>
          <AppText size={14} weight="bold" color={Colors.dangerDeep}>
            결제 전에 멈추세요
          </AppText>
          <AppText size={13} color={Colors.dangerText} leading={1.6} style={{ marginTop: 6 }}>
            &quot;문제 항목&quot; 판정은 특약으로 해결되지 않아요. 계약을 다시 검토하고 공공 상담 창구에 물어보세요.
          </AppText>
        </View>
      ) : terms.length ? (
        <>
          {loadError ? (
            <AppText size={12} color={Colors.textHint} style={{ marginTop: 12 }}>
              {loadError} · 앱에 저장된 특약 예시를 보여 드려요
            </AppText>
          ) : null}
          {remote && (remote.checks.length || remote.warnings.length) ? (
            <Card style={{ marginTop: 14, gap: 6 }}>
              <AppText size={13} weight="semibold">
                계약 전에 한 번 더 확인하세요
              </AppText>
              {[...remote.checks, ...remote.warnings].map((w) => (
                <AppText key={w} size={13} color={Colors.textSub} leading={1.6}>
                  · {w}
                </AppText>
              ))}
            </Card>
          ) : null}
          <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
            {terms.length > 1 ? `이 특약 ${terms.length}개, 계약서에 넣었나요?` : '이 특약, 계약서에 넣었나요?'}
          </AppText>
          <AppText size={13} color={Colors.textSub} style={{ marginTop: 4 }}>
            넣었는지에 따라 앞으로 할 일이 달라져요.
          </AppText>
          {terms.map((t) => (
            <TermCard key={t.id} term={t} pick={picks[t.id]} onPick={(v) => setPicks((p) => ({ ...p, [t.id]: v }))} />
          ))}
        </>
      ) : (
        <View style={[styles.result, { backgroundColor: Colors.primarySoft, marginTop: 18 }]}>
          <AppText size={14} weight="bold" color={Colors.primary}>
            이 판정에 맞는 특약 예시가 없어요
          </AppText>
          <AppText size={13} color={Colors.primarySoftText} leading={1.6} style={{ marginTop: 6 }}>
            걸린 항목이 없어 기본 할 일로 진행해요. 확인 못 한 항목은 따로 챙겨 주세요.
          </AppText>
        </View>
      )}
    </Screen>
  );
}

function TermCard({ term, pick, onPick }: { term: ShownTerm; pick?: SpecialTermResult; onPick: (v: SpecialTermResult) => void }) {
  const { copied, copy } = useCopy(term.text);
  return (
    <>
      <Card padding={18} style={{ marginTop: 12, borderRadius: Radius.lg }}>
        <AppText size={15} weight="bold">
          {term.title}
        </AppText>
        <AppText size={12} color={Colors.textSub} style={{ marginTop: 2 }}>
          {term.link}
        </AppText>
        <View style={styles.termText}>
          <AppText size={13} leading={1.7}>
            {term.text}
          </AppText>
        </View>
        <Button
          variant="outline"
          height={Touch.min}
          label={copied ? '복사했어요' : '특약 문구 복사'}
          icon={<Icon name={copied ? 'check' : 'copy'} size={16} color={Colors.primary} strokeWidth={2} />}
          onPress={copy}
          style={{ marginTop: 10 }}
        />
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }} accessibilityRole="radiogroup">
          <PickButton label="넣음" selected={pick === 'inserted'} color={Colors.primary} onPress={() => onPick('inserted')} />
          <PickButton
            label="거절당함"
            selected={pick === 'rejected'}
            color={Colors.cautionStrong}
            onPress={() => onPick('rejected')}
          />
        </View>
      </Card>
      {pick ? <Outcome term={term} pick={pick} /> : null}
    </>
  );
}

/** 고른 결과에 따라 바뀌는 것 (special_terms.yaml on_inserted / on_rejected) */
function Outcome({ term, pick }: { term: ShownTerm; pick: SpecialTermResult }) {
  const o = pick === 'rejected' ? term.ifRejected : term.ifInserted;
  const rejected = pick === 'rejected';
  return (
    <View style={[styles.result, { backgroundColor: rejected ? Colors.cautionBg : Colors.primarySoft }]}>
      <AppText size={14} weight="bold" color={rejected ? Colors.caution : Colors.primary}>
        {rejected ? '할 일이 이렇게 바뀌어요' : '계약 기록에 남겼어요'}
      </AppText>
      {o.warnings.map((w) => (
        <AppText key={w} size={13} color={rejected ? Colors.cautionText : Colors.primarySoftText} leading={1.6} style={{ marginTop: 6 }}>
          {w}
        </AppText>
      ))}
      {o.movesToTop.length || o.addsTodos?.length || o.documents.length || o.linkCounsel ? (
        <View style={{ gap: 6, marginTop: 12 }}>
          {o.movesToTop.map((t) => (
            <Change key={t} tag="맨 위로" text={t} />
          ))}
          {(o.addsTodos ?? []).map((t) => (
            <Change key={t} tag="새 할 일" text={t} />
          ))}
          {o.documents.map((d) => (
            <Change key={d} tag="기록함" text={`${d} 올리기`} color={Colors.primary} />
          ))}
          {o.linkCounsel ? <Change tag="상담" text="공공 상담 창구 안내를 함께 보여 드려요" /> : null}
        </View>
      ) : null}
    </View>
  );
}

function PickButton({ label, selected, color, onPress }: { label: string; selected: boolean; color: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.pick,
        selected ? { backgroundColor: color, borderColor: color } : { backgroundColor: Colors.card, borderColor: Colors.inputBorder },
      ]}>
      <AppText size={15} weight="bold" color={selected ? '#FFFFFF' : Colors.text}>
        {label}
      </AppText>
    </Pressable>
  );
}

function Change({ tag, text, color = Colors.cautionStrong }: { tag: string; text: string; color?: string }) {
  return (
    <View style={styles.change}>
      <View style={[styles.tag, { backgroundColor: color }]}>
        <AppText size={11} weight="bold" color="#FFFFFF">
          {tag}
        </AppText>
      </View>
      <AppText size={13} style={{ flex: 1 }}>
        {text}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  termText: { marginTop: 12, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: Colors.bg, borderRadius: Radius.input },
  pick: { flex: 1, height: Touch.primary, borderRadius: Radius.button, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  result: { marginTop: 12, padding: 16, borderRadius: Radius.card },
  change: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: Colors.card,
    borderRadius: Radius.input,
  },
  tag: { paddingVertical: 2, paddingHorizontal: 6, borderRadius: 4 },
});
