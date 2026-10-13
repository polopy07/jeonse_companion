/**
 * 디자인 토큰. docs/design/README.md "디자인 규칙"을 그대로 옮겼다.
 * 판정·경보 색(danger / caution / ok)은 판정 표시에만 강하게 쓴다.
 */
export const Colors = {
  bg: '#F4F2EC',
  card: '#FFFFFF',
  border: '#E3DFD6',
  divider: '#EEEAE1',
  track: '#EEEAE1',
  muted: '#E7E3DA',
  inputBorder: '#C9C3B6',
  dashed: '#B9B3A6',
  inactiveDot: '#D5D0C4',
  timelineLine: '#DAD5CA',
  photo: '#E8E4DA',

  text: '#17202A',
  textSub: '#55606B',
  textHint: '#6B7580',
  textCode: '#3A444E',

  primary: '#1D3B5C',
  primarySoft: '#E4ECF4',
  primarySoftText: '#2E4660',

  danger: '#A61B1B',
  dangerDeep: '#7E1717',
  dangerText: '#5E1A1A',
  dangerBg: '#F6E3E3',
  dangerSlot: '#FBEDED',

  caution: '#8A4307',
  cautionStrong: '#B85A0B',
  cautionText: '#5C3A12',
  cautionBg: '#FBEEDF',
  cautionRow: '#FDF6EE',

  ok: '#2B5C8A',
} as const;

export const Font = {
  regular: 'IBMPlexSansKR_400Regular',
  medium: 'IBMPlexSansKR_500Medium',
  semibold: 'IBMPlexSansKR_600SemiBold',
  bold: 'IBMPlexSansKR_700Bold',
} as const;

export type FontWeight = keyof typeof Font;

export const Radius = {
  lg: 18,
  card: 16,
  sm: 14,
  item: 12,
  button: 12,
  input: 10,
} as const;

/** 버튼·링크 최소 높이 44, 주 버튼 52 */
export const Touch = {
  min: 44,
  primary: 52,
} as const;

/** 화면 좌우 여백 */
export const Gutter = 20;

/** 웹에서 열 때 모바일 폭으로 가운데 정렬 */
export const MaxAppWidth = 480;
