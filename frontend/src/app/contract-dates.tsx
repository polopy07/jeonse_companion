import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ChoiceChips, TextField, ToggleRow } from '@/components/form';
import { Button, Card, Disclaimer, Screen, StepProgress } from '@/components/layout';
import { Colors } from '@/constants/theme';
import { checkResult, house } from '@/data/demo';
import { ApiError, apiEnabled, getCheck, getContract, postContract, type Guarantor } from '@/lib/api';
import { useLatestCheck } from '@/lib/check';
import { dateOrderError, isDateText as isDate, parseManwon } from '@/lib/format';
import { contractToken, setCreatedContract, setLatestContract } from '@/lib/contract';
import { paymentIdFor, releasedFor, setLatestPayment, setReleasedPayment } from '@/lib/payment';
import { useSpecialTermResults } from '@/lib/special-terms';

/** 시연 데이터의 "2026.10.20" → 입력칸 "2026-10-20" */
const demoDate = (s: string) => s.replaceAll('.', '-');

/** UI-03 계약 당일 체크 5/5: 계약 날짜·조건 입력 → 계약 생성과 할 일 9종 (FR-014, POST /api/contracts) */
export default function ContractDatesScreen() {
  const check = useLatestCheck() ?? checkResult;
  const termResults = useSpecialTermResults();

  // 시연 집이면 계약 당일 시연 장면 날짜(demo_houses.yaml), 아니면 시연 데이터 날짜로 채워 둔다
  const [contractDate, setContractDate] = useState(check.demoDates?.contract_date ?? demoDate(house.contractDate));
  const [balanceDate, setBalanceDate] = useState(check.demoDates?.balance_date ?? demoDate(house.balanceDate));
  const [endDate, setEndDate] = useState(check.demoDates?.end_date ?? demoDate(house.endDate));
  const [loan, setLoan] = useState(false);
  const [loanDate, setLoanDate] = useState('');
  const [guarantor, setGuarantor] = useState<Guarantor>('HUG');
  const [brokered, setBrokered] = useState(true);
  const [rentText, setRentText] = useState('');
  const [renewalUsed, setRenewalUsed] = useState(false);
  const [coTenant, setCoTenant] = useState(false);
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const datesValid = isDate(contractDate) && isDate(balanceDate) && isDate(endDate) && (!loanDate || isDate(loanDate));
  const orderError = datesValid ? dateOrderError(contractDate, balanceDate, endDate) : null;
  // 월세는 만 원 단위 (비우면 전세 0원)
  const monthlyRent = rentText.trim() ? parseManwon(rentText) : 0;
  const canSubmit = datesValid && !orderError && monthlyRent !== null && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    if (!apiEnabled || check.id === null) {
      // 서버 판정이 없으면(앱 안 계산·시연) 계약을 만들지 않고 시연 할 일 목록으로 간다
      setLatestContract(null);
      router.push('/todos');
      return;
    }
    setSubmitting(true);
    setError(null);
    // 이 판정에 한 결제가 없으면 무산된 계약에서 풀린 결제(그 계약의 토큰과 함께)를 쓴다 (FR-016)
    const ownPayment = paymentIdFor(check.id);
    const released = ownPayment === null ? releasedFor(check.level === 'na' ? 'todo_only' : 'package') : null;
    try {
      const contract = await postContract({
        check_id: check.id,
        contract_date: contractDate,
        balance_date: balanceDate,
        end_date: endDate,
        monthly_rent: monthlyRent ?? 0,
        loan,
        loan_execution_date: loan && loanDate ? loanDate : null,
        guarantor,
        brokered,
        renewal_right_used: renewalUsed,
        co_tenant: coTenant,
        email: email.trim() || null,
        special_term_result: Object.fromEntries(
          Object.entries(termResults).filter((e): e is [string, 'inserted' | 'rejected'] => !!e[1]),
        ),
        payment_id: ownPayment ?? released?.payment_id ?? null,
        released_contract_token: released?.token ?? null,
      });
      // 접근 토큰은 이 응답에서 한 번만 온다. 휴대폰에 저장해 계약 아래 API에 붙인다.
      // 보던 계약이 갈아타기를 저장한 지금 집이면 이 계약을 다음 집으로 연결하고 두 집을 오가며 본다 (FR-027)
      await setCreatedContract(contract);
      setLatestPayment(null); // 계약에 쓴 결제 (무산되면 서버가 풀어 준다)
      if (released) setReleasedPayment(null);
      router.push('/todos');
    } catch (e) {
      // 이미 이 판정으로 계약을 만들었으면 그 계약의 할 일로 간다
      if (e instanceof ApiError && e.code === 'CHECK_ALREADY_USED') {
        const contractId = await getCheck(check.id)
          .then((c) => c.contract_id)
          .catch(() => null);
        const existing =
          contractId === null ? null : await getContract(contractId, contractToken(contractId)).catch(() => null);
        if (existing) {
          setLatestContract(existing);
          router.push('/todos');
          return;
        }
      }
      // 풀린 결제를 쓸 수 없으면(이미 다른 계약에 씀 등) 지워서 결과 화면에서 새로 결제하게 한다
      if (released && e instanceof ApiError && e.status === 402) setReleasedPayment(null);
      // 402 PAYMENT_REQUIRED: 결과 화면의 결제 확인 창으로 돌아가라는 안내(hint)를 그대로 보여 준다
      setError(e instanceof ApiError ? [e.message, e.hint].filter(Boolean).join('. ') : '계약을 만들지 못했어요');
    } finally {
      setSubmitting(false);
    }
  };

  const dateField = (label: string, value: string, onChange: (v: string) => void, helper?: string) => (
    <TextField
      label={label}
      value={value}
      onChange={onChange}
      placeholder="2026-10-20"
      keyboardType="numbers-and-punctuation"
      error={value && !isDate(value) ? 'YYYY-MM-DD 형식으로 입력해 주세요' : undefined}
      helper={helper}
    />
  );

  return (
    <Screen
      title="계약 당일 체크"
      footer={
        <>
          <Disclaimer style={{ paddingTop: 0, marginBottom: 12 }}>
            {error ?? orderError ?? '날짜를 넣으면 2년 동안 할 일과 기한을 만들어 드려요.'}
          </Disclaimer>
          <Button
            label={submitting ? '할 일 만드는 중…' : '할 일 만들기'}
            onPress={canSubmit ? submit : undefined}
            style={{ opacity: canSubmit ? 1 : 0.4 }}
          />
        </>
      }>
      <StepProgress current={4} total={5} label="계약 날짜 입력" />

      <AppText size={18} weight="bold" style={{ marginTop: 18 }}>
        계약서의 날짜를 넣어 주세요
      </AppText>
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 4 }}>
        신고·전입·보증 가입 기한은 이 날짜로 계산해요. 나중에 날짜가 바뀌면 고칠 수 있어요.
      </AppText>

      <Card style={{ marginTop: 14, gap: 14 }}>
        {dateField('계약일', contractDate, setContractDate)}
        {dateField('잔금일', balanceDate, setBalanceDate, '잔금을 치르고 이사하는 날')}
        {dateField('만기일', endDate, setEndDate)}
      </Card>

      <Card style={{ marginTop: 12, paddingVertical: 6 }}>
        <ToggleRow label="전세대출" sub="전세자금대출을 받나요?" value={loan} onChange={setLoan}>
          {dateField('대출 실행일 (모르면 비워 두세요)', loanDate, setLoanDate)}
        </ToggleRow>
        <ToggleRow label="중개 거래" sub="공인중개사를 통해 계약했나요?" value={brokered} onChange={setBrokered} />
        <ToggleRow
          label="갱신 계약"
          sub="계약갱신요구권을 써서 같은 집에 다시 계약했나요?"
          value={renewalUsed}
          onChange={setRenewalUsed}
        />
        <ToggleRow label="공동 계약자" sub="부부 등 두 사람이 함께 계약했나요?" value={coTenant} onChange={setCoTenant} last />
      </Card>

      <Card style={{ marginTop: 12 }}>
        <TextField
          label="월세 (전세면 비워 두세요)"
          value={rentText}
          onChange={setRentText}
          placeholder="0"
          suffix="만 원"
          keyboardType="number-pad"
          error={monthlyRent === null ? '숫자로 입력해 주세요' : undefined}
          helper="보증금 6천만 원 이하·월세 30만 원 이하면 임대차 신고 대신 확정일자를 챙겨 드려요"
        />
      </Card>

      <Card style={{ marginTop: 12, gap: 14 }}>
        <ChoiceChips
          label="반환보증 보증기관"
          choices={[
            { value: 'HUG', label: 'HUG' },
            { value: 'HF', label: 'HF' },
            { value: 'SGI', label: 'SGI' },
            { value: 'none', label: '가입 안 함' },
          ]}
          value={guarantor}
          onChange={setGuarantor}
        />
        <TextField
          label="알림 받을 이메일 (선택)"
          value={email}
          onChange={setEmail}
          placeholder="name@example.com"
          keyboardType="email-address"
        />
      </Card>

      {!apiEnabled || check.id === null ? (
        <View style={{ marginTop: 12 }}>
          <AppText size={12} color={Colors.textHint} leading={1.6}>
            서버에 저장된 판정이 없어 시연 할 일 목록으로 이어져요.
          </AppText>
        </View>
      ) : null}
    </Screen>
  );
}
