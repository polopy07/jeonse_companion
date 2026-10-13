import {
  IBMPlexSansKR_400Regular,
  IBMPlexSansKR_500Medium,
  IBMPlexSansKR_600SemiBold,
  IBMPlexSansKR_700Bold,
  useFonts,
} from '@expo-google-fonts/ibm-plex-sans-kr';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { Colors, MaxAppWidth } from '@/constants/theme';
import { restoreContract } from '@/lib/contract';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useFonts({
    IBMPlexSansKR_400Regular,
    IBMPlexSansKR_500Medium,
    IBMPlexSansKR_600SemiBold,
    IBMPlexSansKR_700Bold,
  });

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  // 전에 만든 계약이 있으면 서버에서 다시 불러온다 (할 일 탭이 이어서 보여 줌)
  useEffect(() => {
    restoreContract();
  }, []);

  if (!loaded && !error) return null;

  return (
    <View style={styles.outer}>
      <View style={styles.app}>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.bg } }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // 웹에서 넓은 화면으로 열어도 모바일 폭으로 보이게 가운데 둔다
  outer: { flex: 1, backgroundColor: '#D9D6CF', alignItems: 'center' },
  app: { flex: 1, width: '100%', maxWidth: MaxAppWidth, backgroundColor: Colors.bg },
});
