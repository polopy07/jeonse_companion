/** 140000000 → "1억 4,000만", 36000000 → "3,600만", 0 → "0원" */
export function formatWon(won: number): string {
  if (won <= 0) return '0원';
  const man = Math.round(won / 10_000);
  const eok = Math.floor(man / 10_000);
  const rest = man % 10_000;
  const parts: string[] = [];
  if (eok) parts.push(`${eok}억`);
  if (rest) parts.push(`${rest.toLocaleString('en-US')}만`);
  return parts.join(' ') || '0원';
}

/** 입력칸의 "14000"(만 원) → 140000000(원). 숫자가 아니면 null */
export function parseManwon(text: string): number | null {
  const digits = text.replace(/[^0-9]/g, '');
  if (!digits) return null;
  return Number(digits) * 10_000;
}

/** 입력칸 숫자 → 소수 (전용면적 등). 숫자가 아니면 null */
export function parseNumber(text: string): number | null {
  const n = Number(text.replace(/[^0-9.]/g, ''));
  return text.trim() && Number.isFinite(n) && n > 0 ? n : null;
}
