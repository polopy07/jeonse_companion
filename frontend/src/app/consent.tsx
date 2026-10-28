import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Icon } from '@/components/Icon';
import { Button, Card, Screen, SectionLabel } from '@/components/layout';
import { Colors, Touch } from '@/constants/theme';
import { agreeConsent, hasConsent, useConsent, withdrawConsent } from '@/lib/consent';

/** 서비스 안내 (NFR-014, FR-010): 결과 화면마다 붙는 "정보 제공이며 보증하지 않습니다"를 처음에 풀어서 */
const SERVICE_NOTICE = [
  '전동기는 공공 자료와 올려 주신 등기부 요약으로 위험 신호를 알려 드리는 정보 제공 서비스예요. 집이 안전하다고 보증하지 않아요.',
  '개별 법률 판단이 아니에요. 계약을 멈출지 정하기 어렵거나 보증금을 돌려받지 못했으면 공공 상담 창구에 문의하세요.',
  '대출·보증 상품을 추천하지 않아요. 보증기관 이름은 제도 안내로만 쓰고, 기관의 공식 서비스가 아니에요.',
  '판정에는 조회 시점이 있어요. 공시가격·실거래가는 늦게 반영될 수 있고 그 뒤 생긴 등기는 들어가지 않아요.',
  '알림(이메일·앱 기한표·캘린더)은 보조 수단이에요. 기한은 할 일 화면에서 직접 확인해 주세요.',
];

/** 개인정보 수집·이용 (NFR-010·011) */
const PRIVACY = [
  { label: '수집 항목', text: '계약 조건(날짜·보증금·월세·보증기관 등), 등기부 요약에서 확인한 값(근저당·압류·신탁 등), 알림 이메일(넣은 경우), 할 일 증빙 사진' },
  { label: '이용 목적', text: '위험 판정, 내 계약 맞춤 할 일·기한 알림, 역전세 경보 계산, 전세 기록함 보관' },
  { label: '보관 기간', text: '보증금 반환을 확인한 날(반환 대응 중이면 대응이 끝난 날)로부터 3개월. 기록함 사진은 언제든 직접 지울 수 있어요' },
  { label: '수집하지 않는 것', text: '주민등록번호. 주민번호가 보이는 서류는 가린 뒤 올려 주세요. 등기부 PDF는 읽기만 하고 저장하지 않아요' },
];

/**
 * 서비스 안내(면책)·개인정보 수집·이용 동의. 계약 전 확인을 처음 시작할 때 이 화면이 먼저 열리고(next=precheck),
 * 동의하면 계약 전 확인으로 간다. 홈에서 다시 보기·동의 철회
 */
export default function ConsentScreen() {
  const { next } = useLocalSearchParams<{ next?: string }>();
  const current = useConsent();
  const agreed = hasConsent(current);
  const [notice, setNotice] = useState(agreed);
  const [privacy, setPrivacy] = useState(agreed);
  const canAgree = notice && privacy;

  const agree = () => {
    if (!canAgree) return;
    agreeConsent();
    if (next === 'precheck') router.replace('/precheck');
    else if (router.canGoBack()) router.back();
    else router.replace('/');
  };

  const withdraw = () => {
    withdrawConsent();
    router.replace('/');
  };

  return (
    <Screen
      title="시작하기 전에"
      footer={
        agreed ? (
          <View style={{ gap: 4 }}>
            <Button label="확인했어요" onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} />
            <Pressable accessibilityRole="button" onPress={withdraw} style={styles.textButton}>
              <AppText size={13} weight="semibold" color={Colors.textSub}>
                동의 철회 (다음에 계약 전 확인을 시작할 때 다시 물어요)
              </AppText>
            </Pressable>
          </View>
        ) : (
          <Button
            label="동의하고 시작하기"
            onPress={canAgree ? agree : undefined}
            style={{ opacity: canAgree ? 1 : 0.4 }}
          />
        )
      }>
      <AppText size={13} color={Colors.textSub} leading={1.6} style={{ marginTop: 6 }}>
        {agreed
          ? `${current.agreedOn.replaceAll('-', '.')}에 동의했어요.`
          : '계약 전 확인과 할 일 관리를 쓰려면 아래 두 가지를 확인해 주세요.'}
      </AppText>

      <SectionLabel>서비스 안내</SectionLabel>
      <Card style={{ gap: 8 }}>
        {SERVICE_NOTICE.map((t) => (
          <AppText key={t} size={13} leading={1.6}>
            · {t}
          </AppText>
        ))}
      </Card>

      <SectionLabel>개인정보 수집·이용</SectionLabel>
      <Card style={{ gap: 10 }}>
        {PRIVACY.map((p) => (
          <View key={p.label}>
            <AppText size={12} weight="semibold" color={Colors.textSub}>
              {p.label}
            </AppText>
            <AppText size={13} leading={1.6} style={{ marginTop: 2 }}>
              {p.text}
            </AppText>
          </View>
        ))}
        <AppText size={12} color={Colors.textHint} leading={1.6}>
          동의하지 않으면 계약 전 확인과 할 일 관리를 쓸 수 없어요. 회원 가입·로그인은 없고, 이 동의는 이 휴대폰에만 저장해요.
        </AppText>
      </Card>

      {agreed ? null : (
        <Card style={{ marginTop: 12, paddingVertical: 6 }}>
          <CheckItem label="[필수] 서비스 안내를 읽었어요" checked={notice} onChange={setNotice} />
          <View style={styles.divider} />
          <CheckItem label="[필수] 개인정보 수집·이용에 동의해요" checked={privacy} onChange={setPrivacy} />
        </Card>
      )}
    </Screen>
  );
}

function CheckItem({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      style={styles.checkItem}>
      <View style={[styles.box, checked && { backgroundColor: Colors.ok, borderColor: Colors.ok }]}>
        {checked ? <Icon name="check" size={16} color="#FFFFFF" strokeWidth={2.6} /> : null}
      </View>
      <AppText size={14} weight={checked ? 'semibold' : 'regular'} style={{ flex: 1 }}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  checkItem: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: Touch.min, paddingVertical: 6 },
  box: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  divider: { height: 1, backgroundColor: Colors.divider },
  textButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
});
