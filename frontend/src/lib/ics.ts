/**
 * 할 일 기한 → 캘린더 파일 (ICS, FR-042, NFR-008, AC-011). 구글·애플 캘린더에서 가져올 수 있다.
 *
 * 끝나지 않은 할 일마다 하루 종일 일정 1개: 기한이 있으면 기한일, 재알림(T6·T8)은 알림일.
 * 알림은 todos.yaml notifications와 같게 7일 전·1일 전 오전 9시. 캘린더 알림은 보조 수단임을 설명에 적는다.
 * 휴대폰은 파일을 만들어 공유(캘린더 앱으로 열기), 웹은 내려받기.
 */
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import type { ApiContract, ApiTodo } from '@/lib/api';
import { addDays } from '@/lib/clock';

const FILE_NAME = 'jeonse-todos.ics';
const NOTICE = '알림은 보조 수단이에요. 기한은 앱의 할 일 목록과 보증기관 안내를 함께 확인하세요.';
/** 기한 7일 전·1일 전 오전 9시 (하루 종일 일정은 그날 0시 기준) */
const ALARMS = ['-P6DT15H', '-PT15H'];

/** 텍스트 값 이스케이프 (RFC 5545 3.3.11) */
const escapeText = (s: string) => s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');

const utf8Bytes = (ch: string) => {
  const cp = ch.codePointAt(0) ?? 0;
  return cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
};

/** 한 줄이 75바이트를 넘으면 접는다 (RFC 5545 3.1). 한글이 바이트 중간에서 잘리지 않게 글자 단위로 센다 */
function fold(line: string): string {
  const out: string[] = [];
  let cur = '';
  let bytes = 0;
  for (const ch of line) {
    const n = utf8Bytes(ch);
    if (bytes + n > (out.length ? 74 : 75)) {
      out.push(cur);
      cur = '';
      bytes = 0;
    }
    cur += ch;
    bytes += n;
  }
  out.push(cur);
  return out.join('\r\n ');
}

const compactDate = (s: string) => s.replaceAll('-', '');

function utcStamp(d: Date) {
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

/** 할 일 하나의 일정 날짜. 기한이 있으면 기한, 재알림이면 알림일, 둘 다 없으면 null (일정을 만들지 않음) */
const eventDay = (t: ApiTodo) => t.due_date ?? t.remind_date;

function event(contract: ApiContract, t: ApiTodo, day: string, stamp: string, houseLabel: string | null): string[] {
  const detail = [
    t.start_date && t.start_date !== day ? `${t.start_date}부터 할 수 있어요.` : null,
    t.detail,
    houseLabel ? `집: ${houseLabel}` : null,
    NOTICE,
  ].filter(Boolean);
  return [
    'BEGIN:VEVENT',
    // 같은 계약·할 일은 같은 UID: 다시 내보내 가져오면 캘린더가 새로 만들지 않고 바꾼다
    `UID:jeonse-${contract.id}-${t.rule_id}@jeonse-companion`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${compactDate(day)}`,
    `DTEND;VALUE=DATE:${compactDate(addDays(day, 1))}`,
    `SUMMARY:${escapeText(`[전동기] ${t.title}`)}`,
    `DESCRIPTION:${escapeText(detail.join('\n'))}`,
    'TRANSP:TRANSPARENT',
    ...ALARMS.flatMap((trigger) => [
      'BEGIN:VALARM',
      'ACTION:DISPLAY',
      `DESCRIPTION:${escapeText(t.title)}`,
      `TRIGGER:${trigger}`,
      'END:VALARM',
    ]),
    'END:VEVENT',
  ];
}

/** 계약의 끝나지 않은 할 일 → ICS 본문 (줄바꿈 CRLF) */
export function buildIcs(contract: ApiContract, houseLabel: string | null = null, now: Date = new Date()): string {
  const stamp = utcStamp(now);
  const events = contract.todos
    .filter((t) => t.status === 'todo' && eventDay(t))
    .flatMap((t) => event(contract, t, eventDay(t)!, stamp, houseLabel));
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//jeonse-companion//todos//KO',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeText('전동기 할 일')}`,
    ...events,
    'END:VCALENDAR',
  ];
  return lines.map(fold).join('\r\n') + '\r\n';
}

/** 캘린더에 넣을 할 일 수 (0이면 내보낼 것이 없음) */
export const icsEventCount = (contract: ApiContract) => contract.todos.filter((t) => t.status === 'todo' && eventDay(t)).length;

/**
 * ICS 파일을 내보낸다. 휴대폰은 공유 창(캘린더 앱·파일·메일)으로, 웹은 파일 내려받기.
 * 공유를 쓸 수 없는 기기면 오류를 던진다
 */
export async function exportIcs(contract: ApiContract, houseLabel: string | null = null): Promise<void> {
  const text = buildIcs(contract, houseLabel);
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/calendar;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = FILE_NAME;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1_000);
    return;
  }
  if (!(await Sharing.isAvailableAsync())) throw new Error('이 기기에서는 파일을 공유할 수 없어요');
  const file = new File(Paths.cache, FILE_NAME);
  if (file.exists) file.delete();
  file.create();
  file.write(text);
  await Sharing.shareAsync(file.uri, { mimeType: 'text/calendar', UTI: 'public.calendar-event', dialogTitle: '캘린더에 추가' });
}
