import { Text, type TextProps } from 'react-native';

import { Colors, Font, type FontWeight } from '@/constants/theme';

type Props = TextProps & {
  size?: number;
  weight?: FontWeight;
  color?: string;
  /** 줄 높이 배수 (목업의 line-height) */
  leading?: number;
};

/**
 * IBM Plex Sans KR을 굵기별 글꼴 파일로 쓴다.
 * 안드로이드는 fontWeight만으로 굵기가 바뀌지 않아 fontFamily를 직접 고른다.
 */
export function AppText({ size = 14, weight = 'regular', color = Colors.text, leading, style, ...rest }: Props) {
  return (
    <Text
      {...rest}
      style={[
        {
          fontFamily: Font[weight],
          fontSize: size,
          color,
          lineHeight: leading ? Math.round(size * leading) : undefined,
          letterSpacing: size >= 18 ? -0.4 : 0,
        },
        style,
      ]}
    />
  );
}
