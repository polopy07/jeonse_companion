import { useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { TextField } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Button, Card } from '@/components/layout';
import { Colors, Radius, Touch } from '@/constants/theme';
import { ApiError, getOfficialPrice, searchParcels, type ApiOfficialPrice, type ApiParcel, type ApiUnitPrice } from '@/lib/api';
import { formatWon } from '@/lib/format';

/** 찾은 공시가격. 계약 전 확인의 공시가격·전용면적 칸을 채운다 */
export type FoundPrice = { price: number; area: number | null; label: string; source: string };

type Phase = 'idle' | 'searching' | 'parcels' | 'loading' | 'units';

/** 한 번에 보여 줄 호 수. 넘으면 동·호를 넣어 좁힌다 */
const MAX_UNITS = 12;
/** 서버가 이 API를 모르거나(예전 서버) 브이월드 키가 없으면 자동 조회를 쓸 수 없다 */
const UNAVAILABLE = new Set(['VWORLD_KEY_MISSING', 'NOT_FOUND']);

/** "101동"·"101"·" 0101 동" → "101" (서버 unit_key와 같은 규칙. 동·호 표기는 단지마다 다르다) */
const unitKey = (value: string, suffix: string) => {
  let v = value.replace(/\s+/g, '');
  if (v.endsWith(suffix)) v = v.slice(0, -suffix.length);
  return v.replace(/^0+/, '') || v;
};

/** 주소 끝의 "101동 1203호"·"201호"를 떼어 동·호 칸으로 (법정동 "광안동"은 숫자가 없어 남는다) */
export function splitUnit(address: string): { query: string; dong: string; ho: string } {
  const both = address.match(/^(.*?)\s*(\d+)\s*동\s*(\d+)\s*호\s*$/);
  if (both) return { query: both[1].trim(), dong: both[2], ho: both[3] };
  const hoOnly = address.match(/^(.*?)\s*(\d+)\s*호\s*$/);
  if (hoOnly) return { query: hoOnly[1].trim(), dong: '', ho: hoOnly[2] };
  return { query: address.trim(), dong: '', ho: '' };
}

/** 숫자만 온 동·호에 "동"·"호"를 붙인다 (빌라는 동 이름에 건물 이름이 온다: "제이제이") */
const withSuffix = (v: string, suffix: string) => (/^\d+$/.test(v) ? `${v}${suffix}` : v);

/** "101동 1203호". complex를 주면 동 이름이 단지 이름과 같을 때(빌라) 동을 뺀다 */
const unitLabel = (u: ApiUnitPrice, complex?: string) =>
  [u.dong && u.dong !== complex ? withSuffix(u.dong, '동') : '', withSuffix(u.ho, '호')].filter(Boolean).join(' ');

/**
 * 주소로 공동주택 공시가격 찾기 (FR-001 확장, GET /api/official-price). 주소 → 필지 → 동·호 → 공시가격.
 * 못 찾거나 서버가 못 쓰는 상태면 안내만 하고, 화면 아래 직접 입력 칸은 그대로 쓴다
 */
export function OfficialPriceFinder({ address, onFound }: { address: string; onFound: (p: FoundPrice) => void }) {
  const initial = splitUnit(address);
  const [query, setQuery] = useState(initial.query);
  const [dong, setDong] = useState(initial.dong);
  const [ho, setHo] = useState(initial.ho);
  const [phase, setPhase] = useState<Phase>('idle');
  const [parcels, setParcels] = useState<ApiParcel[]>([]);
  const [data, setData] = useState<ApiOfficialPrice | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = phase === 'searching' || phase === 'loading';
  // 마지막 요청 번호. 앞 요청의 응답이 늦게 와도 화면을 덮지 않게
  const seq = useRef(0);

  const fail = (e: unknown) => {
    if (e instanceof ApiError && UNAVAILABLE.has(e.code)) {
      setError('지금은 주소로 찾을 수 없어요. 아래에 공시가격을 직접 입력해 주세요');
    } else {
      setError(`${e instanceof ApiError ? e.message : '공시가격을 찾지 못했어요'}. 아래에 직접 입력할 수 있어요`);
    }
  };

  const pick = (d: ApiOfficialPrice, u: ApiUnitPrice) => {
    setPicked(`${u.dong}|${u.ho}`);
    onFound({
      price: u.official_price,
      area: u.exclusive_area,
      label: [d.complex_name, unitLabel(u, d.complex_name)].filter(Boolean).join(' '),
      source: d.source,
    });
  };

  const matchesOf = (d: ApiOfficialPrice) =>
    d.units.filter(
      (u) => (!dong.trim() || unitKey(u.dong, '동') === unitKey(dong, '동')) && (!ho.trim() || unitKey(u.ho, '호') === unitKey(ho, '호')),
    );

  const fetchUnits = async (p: ApiParcel) => {
    const id = ++seq.current;
    setPhase('loading');
    setError(null);
    setPicked(null);
    try {
      const d = await getOfficialPrice(p.pnu);
      if (id !== seq.current) return;
      setData(d);
      setPhase('units');
      const m = matchesOf(d);
      if (m.length === 1) pick(d, m[0]); // 동·호가 하나로 맞으면 바로 채운다
    } catch (e) {
      if (id !== seq.current) return;
      setPhase('parcels');
      fail(e);
    }
  };

  /** 필지 목록에서 고르기. 받는 중에는 다른 필지를 누르지 못한다 */
  const loadUnits = (p: ApiParcel) => {
    if (!busy) fetchUnits(p);
  };

  const search = async () => {
    if (!query.trim() || busy) return;
    const id = ++seq.current;
    setPhase('searching');
    setError(null);
    setParcels([]);
    setData(null);
    setPicked(null);
    try {
      const r = await searchParcels(query.trim());
      if (id !== seq.current) return;
      setParcels(r.parcels);
      if (r.parcels.length === 1) return fetchUnits(r.parcels[0]);
      setPhase('parcels');
    } catch (e) {
      if (id !== seq.current) return;
      setPhase('idle');
      fail(e);
    }
  };

  const matches = data ? matchesOf(data) : [];

  return (
    <Card style={{ marginTop: 14, gap: 10 }}>
      <AppText size={13} weight="semibold">
        주소로 공시가격 찾기
      </AppText>
      <TextField label="주소 (도로명·지번)" value={query} onChange={setQuery} placeholder="예: 부산 수영구 광안동 212-1" />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TextField label="동" value={dong} onChange={setDong} placeholder="101" suffix="동" />
        <TextField label="호" value={ho} onChange={setHo} placeholder="1203" suffix="호" keyboardType="number-pad" />
      </View>
      <Button
        variant="outline"
        height={Touch.min}
        label={phase === 'searching' ? '찾는 중…' : phase === 'loading' ? '공시가격 받는 중…' : '찾기'}
        onPress={busy ? undefined : search}
      />
      <AppText size={11} color={Colors.textHint} leading={1.5}>
        동이 없는 빌라는 호만 넣어요. 아파트·연립·다세대만 있어요.
      </AppText>

      {error ? (
        <AppText size={13} color={Colors.danger} leading={1.6}>
          {error}
        </AppText>
      ) : null}

      {parcels.length > 1 && (phase === 'parcels' || phase === 'loading') ? (
        <View style={{ gap: 6 }}>
          <AppText size={12} color={Colors.textSub}>
            어느 주소인가요?
          </AppText>
          {parcels.map((p) => (
            <Pressable key={p.pnu} accessibilityRole="button" onPress={() => loadUnits(p)} style={styles.item}>
              <AppText size={13} weight="semibold">
                {p.address}
              </AppText>
              {p.road_address ? (
                <AppText size={11} color={Colors.textHint}>
                  {p.road_address}
                </AppText>
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : null}

      {phase === 'units' && data ? (
        <View style={{ gap: 6 }}>
          <AppText size={12} color={Colors.textSub}>
            {data.complex_name} · {data.stdr_year}년 공시가격 · {matches.length}세대
          </AppText>
          {matches.length === 0 ? (
            <AppText size={13} color={Colors.danger} leading={1.6}>
              그 동·호가 없어요. 동·호를 지우면 전체 목록이 나와요
            </AppText>
          ) : null}
          {matches.slice(0, MAX_UNITS).map((u) => {
            const on = picked === `${u.dong}|${u.ho}`;
            return (
              <Pressable
                key={`${u.dong}|${u.ho}`}
                accessibilityRole="button"
                onPress={() => pick(data, u)}
                style={[styles.item, styles.unit, on && { borderColor: Colors.primary, borderWidth: 2 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  {on ? <Icon name="check" size={14} color={Colors.ok} strokeWidth={2.2} /> : null}
                  <AppText size={13} weight="semibold" color={on ? Colors.primary : Colors.text}>
                    {unitLabel(u, data.complex_name) || '세대'}
                  </AppText>
                  {u.exclusive_area ? (
                    <AppText size={11} color={Colors.textHint}>
                      {u.exclusive_area}㎡
                    </AppText>
                  ) : null}
                </View>
                <AppText size={13} weight="semibold">
                  {formatWon(u.official_price)} 원
                </AppText>
              </Pressable>
            );
          })}
          {matches.length > MAX_UNITS ? (
            <AppText size={12} color={Colors.textSub}>
              {matches.length - MAX_UNITS}세대 더 있어요. 동·호를 넣어 좁혀 주세요
            </AppText>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  item: {
    minHeight: Touch.min,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: Radius.input,
    borderWidth: 1,
    borderColor: Colors.inputBorder,
    backgroundColor: Colors.card,
    justifyContent: 'center',
  },
  unit: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
