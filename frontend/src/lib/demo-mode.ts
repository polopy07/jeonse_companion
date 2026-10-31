import { createStore } from '@/lib/store';

/**
 * "시연 집으로 둘러보기": 계약이 없을 때도 홈·할 일·기록함·경보를 시연 데이터로 보여 준다 (발표·처음 써 보는 사람용).
 * 앱을 다시 켜면 꺼진다. 계약이 있으면 이 값과 상관없이 계약을 보여 준다
 */
const demoMode = createStore(false);
export const useDemoMode = demoMode.use;
export const setDemoMode = demoMode.set;
