import { Tabs } from 'expo-router/js-tabs';

import { Icon, type IconName } from '@/components/Icon';
import { Colors, Font } from '@/constants/theme';

const tabs: { name: string; title: string; icon: IconName }[] = [
  { name: 'index', title: '홈', icon: 'home' },
  { name: 'todos', title: '할 일', icon: 'todos' },
  { name: 'records', title: '기록함', icon: 'folder' },
  { name: 'alert', title: '경보', icon: 'trend' },
];

/** 하단 탭 4개: 홈 / 할 일 / 기록함 / 경보. 계약 전 확인(무료)은 탭 밖 흐름이다. */
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textHint,
        tabBarStyle: {
          backgroundColor: Colors.card,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          minHeight: 72,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontFamily: Font.medium, fontSize: 11 },
        sceneStyle: { backgroundColor: Colors.bg },
      }}>
      {tabs.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.title,
            tabBarIcon: ({ color }) => <Icon name={t.icon} color={String(color)} />,
          }}
        />
      ))}
    </Tabs>
  );
}
