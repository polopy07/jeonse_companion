import { useSyncExternalStore } from 'react';

/**
 * 화면 사이에 값을 넘기는 아주 작은 저장소. 앱을 다시 켜면 사라진다.
 * 백엔드에 저장하게 되면 API 응답으로 바꾼다.
 */
export function createStore<T>(initial: T) {
  let value = initial;
  const listeners = new Set<() => void>();
  const subscribe = (l: () => void) => {
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  };
  return {
    get: () => value,
    set: (next: T) => {
      value = next;
      listeners.forEach((l) => l());
    },
    use: () => useSyncExternalStore(subscribe, () => value, () => value),
  };
}
