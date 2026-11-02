import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { ApiError, apiEnabled, getAlertReport, type ApiAlertReport, type ApiContract } from '@/lib/api';
import { useVirtualToday } from '@/lib/clock';
import { contractToken } from '@/lib/contract';

export type RemoteAlert = { contractId: number; report: ApiAlertReport | null; notApplicable: boolean; error: string | null };

/**
 * 계약의 최근 경보를 서버에서 받는다 (GET /api/contracts/{id}/alerts/latest). 화면을 열 때마다 다시 받아
 * 관리자 재계산(공시가격 발표)·가상 날짜를 바로 반영한다. 서버 주소가 없거나 계약이 없으면 null
 */
export function useAlertReport(contract: ApiContract | null): RemoteAlert | null {
  const [remote, setRemote] = useState<RemoteAlert | null>(null);
  const day = useVirtualToday();
  const id = contract?.id ?? null;
  useFocusEffect(
    useCallback(() => {
      if (!apiEnabled || id === null) return;
      let alive = true;
      getAlertReport(id, contractToken(id))
        .then((report) => alive && setRemote({ contractId: id, report, notApplicable: false, error: null }))
        .catch((e) => {
          if (!alive) return;
          // 404 = 다가구·단독 등 경보를 계산하지 않는 계약 (토큰이 틀린 계약은 할 일 탭에서 먼저 안내)
          const notApplicable = e instanceof ApiError && e.status === 404;
          const error = notApplicable ? null : e instanceof ApiError ? e.message : '경보를 받지 못했어요';
          setRemote({ contractId: id, report: null, notApplicable, error });
        });
      return () => {
        alive = false;
      };
      // contract가 바뀌면(보증금 수정·다시 불러오기) 다시 받는다
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, day, contract]),
  );
  return remote?.contractId === id ? remote : null;
}
