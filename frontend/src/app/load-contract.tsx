import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField } from '@/components/form';
import { Button, Card, Screen, SectionLabel } from '@/components/layout';
import { Colors, Touch } from '@/constants/theme';
import { ApiError, apiEnabled, getContract, postAccessLink, type ApiContract } from '@/lib/api';
import { setLatestContract } from '@/lib/contract';
import { setDemoMode } from '@/lib/demo-mode';

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * 내 계약 불러오기 (휴대폰을 바꿨거나 처음부터 다시했을 때, POST /api/contracts/access-link).
 * ① 계약 때 넣은 알림 이메일로 접근 코드 받기 → ② 메일의 계약 번호·접근 코드로 불러오기.
 * 메일의 링크(APP_LINK_BASE?contract=&token=)로 열면 ②를 바로 채운다
 */
export default function LoadContractScreen() {
  const params = useLocalSearchParams<{ contract?: string; token?: string }>();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [idText, setIdText] = useState(params.contract ?? '');
  const [token, setToken] = useState(params.token ?? '');
  // 메일 링크(contract·token)로 열었으면 처음부터 불러오는 중
  const auto = !!(params.contract && params.token);
  const [loading, setLoading] = useState(auto);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (!EMAIL.test(email.trim()) || sending) return;
    setSending(true);
    setError(null);
    try {
      setSent((await postAccessLink(email.trim())).message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '메일을 보내지 못했어요');
    } finally {
      setSending(false);
    }
  };

  const contractId = Number(idText.trim());
  const ready = Number.isInteger(contractId) && contractId > 0 && token.trim().length > 0;

  const opened = (contract: ApiContract, code: string) => {
    setLatestContract(contract, code);
    setDemoMode(false);
    router.replace('/');
  };

  const failed = (e: unknown) =>
    setError(
      e instanceof ApiError && e.status === 404
        ? '계약 번호나 접근 코드가 맞지 않아요. 메일에 적힌 그대로 넣어 주세요'
        : e instanceof ApiError
          ? e.message
          : '계약을 불러오지 못했어요',
    );

  const open = (id: number, code: string) =>
    getContract(id, code)
      .then((c) => opened(c, code), failed)
      .finally(() => setLoading(false));

  const load = () => {
    if (!ready || loading) return;
    setLoading(true);
    setError(null);
    open(contractId, token.trim());
  };

  // 메일 링크로 열었으면 바로 불러온다
  useEffect(() => {
    if (auto) open(Number(params.contract), String(params.token));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!apiEnabled) {
    return (
      <Screen title="내 계약 불러오기">
        <AppText size={14} color={Colors.textSub} leading={1.6} style={{ marginTop: 16 }}>
          서버 주소가 설정되지 않아 불러올 수 없어요.
        </AppText>
      </Screen>
    );
  }

  return (
    <Screen title="내 계약 불러오기">
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 8 }}>
        계약은 서버에 남아 있어요. 계약할 때 넣은 알림 이메일로 접근 코드를 받아 이 휴대폰에서 다시 볼 수 있어요.
      </AppText>

      <SectionLabel>① 접근 코드 받기</SectionLabel>
      <Card style={{ gap: 10 }}>
        <TextField
          label="알림 이메일 (공동 계약자 이메일도 돼요)"
          value={email}
          onChange={setEmail}
          placeholder="me@example.com"
          keyboardType="email-address"
        />
        <Button
          variant="outline"
          height={Touch.min}
          label={sending ? '보내는 중…' : '접근 코드 메일 받기'}
          onPress={EMAIL.test(email.trim()) && !sending ? send : undefined}
          style={{ opacity: EMAIL.test(email.trim()) ? 1 : 0.4 }}
        />
        {sent ? (
          <AppText size={12} color={Colors.textSub} leading={1.6}>
            {sent}
          </AppText>
        ) : null}
      </Card>

      <SectionLabel>② 메일의 계약 번호·접근 코드 넣기</SectionLabel>
      <Card style={{ gap: 10 }}>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextField label="계약 번호" value={idText} onChange={setIdText} placeholder="12" keyboardType="number-pad" style={{ flex: 0.4 }} />
          <TextField label="접근 코드" value={token} onChange={setToken} placeholder="메일의 접근 코드" />
        </View>
        <Button
          label={loading ? '불러오는 중…' : '불러오기'}
          onPress={ready && !loading ? load : undefined}
          style={{ opacity: ready ? 1 : 0.4 }}
        />
      </Card>

      {error ? (
        <AppText size={13} color={Colors.danger} leading={1.6} style={{ marginTop: 10 }}>
          {error}
        </AppText>
      ) : null}
      <AppText size={11} color={Colors.textHint} leading={1.5} style={{ marginTop: 12 }}>
        접근 코드를 가진 사람은 계약을 볼 수 있으니 다른 사람에게 보내지 마세요. 한 계약에 한 시간 세 번까지 받을 수 있어요.
      </AppText>
    </Screen>
  );
}
