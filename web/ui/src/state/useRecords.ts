/* 운동 기록 — 저장소와 주간 달성률. 바닐라 `records.js` 의 계산부를 옮겼다.
 *
 * 지켜야 할 것 넷 (원본 주석 그대로 옮긴다. 하나라도 어기면 화면마다 숫자가 달라진다):
 *  1. 달성률은 처방과 같은 근거를 쓴다 — Σ(중강도 분) + Σ(고강도 분)×2, 목표 150분.
 *     rules.json 의 baseline 문장("중강도 주 150분 또는 고강도 75분")이 2:1 환산을 이미 담고 있다
 *  2. 저강도는 분 점수에 넣지 않는다(O10). 횟수로만 따로 보여준다
 *  3. 주 경계는 KST 월요일 00:00 이다. 브라우저 타임존이 무엇이든 결과가 같아야 한다
 *  4. 미달성을 질책하지 않는다. "이번 주는 60분 하셨어요"까지만
 *
 * 기록은 이 기기에만 있다. 서버 DB 를 만들지 않기로 한 것은 타협이 아니라 선택이고,
 * 그 사실을 화면에 밝힌다(§4).
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { 강도, 종목마스터 } from '../api/types';

export const RECORDS_KEY = 'badathon.records';

const KST_MS = 9 * 60 * 60 * 1000;
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** 중강도 주 150분 */
export const GOAL_MIN = 150;
/** 근력 운동 주 2일 — 지침의 별도 권고 */
export const STRENGTH_GOAL_DAYS = 2;

/* '미확인' 은 serve() 가 상한과 비교할 때 '중' 으로 간주한다. 여기서도 같은 가정을
 * 쓰지 않으면 같은 종목이 화면마다 다르게 계산된다. 가정이라는 점은 화면에 밝힌다. */
const SCORE_WEIGHT: Record<string, number> = { 고: 2, 중: 1, 미확인: 1, 저: 0 };

export interface 기록 {
  id: string;
  종목: string;
  시간분: number;
  강도: 강도;
  /** KST 오프셋이 붙은 ISO 문자열 */
  일시: string;
  메모: string;
  /** 시연용 더미인지 (O12) */
  샘플: boolean;
}

/* ---------------- 주 경계 (KST) ---------------- */

/** 해당 시각이 속한 주의 KST 월요일 00:00 을 실제 epoch 으로 돌려준다. */
export function weekStart(ms: number): number {
  const shifted = new Date(ms + KST_MS); // UTC 필드를 KST 로 읽는다
  const monday = (shifted.getUTCDay() + 6) % 7; // 월=0
  const midnight =
    Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate()) -
    monday * DAY_MS;
  return midnight - KST_MS; // 다시 실제 epoch 으로
}

export function kstIso(ms: number): string {
  const d = new Date(ms + KST_MS);
  const p = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}` +
    `T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}+09:00`
  );
}

export function kstLabel(iso: string): string {
  const d = new Date(new Date(iso).getTime() + KST_MS);
  const day = '일월화수목금토'[d.getUTCDay()];
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${day}) ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/* ---------------- 저장소 ---------------- */

function readAll(): 기록[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(RECORDS_KEY) ?? '[]');
    return Array.isArray(raw) ? (raw as 기록[]) : [];
  } catch {
    return []; // 깨진 값이 화면을 막지 않는다
  }
}

function writeAll(list: 기록[]): void {
  try {
    localStorage.setItem(RECORDS_KEY, JSON.stringify(list));
  } catch {
    /* 저장 실패해도 화면은 계속 동작한다 */
  }
}

/* ---------------- 공유 저장소 ---------------- */
/* 화면 여러 곳이 같은 기록을 본다 — 홈의 링, 기록 탭, 기록 입력 시트.
 * 훅마다 useState 를 두면 한 곳에서 기록해도 다른 곳이 모르므로,
 * 모듈 수준에 스냅숏 하나를 두고 useSyncExternalStore 로 구독한다.
 * 바닐라의 전역 `store` 가 하던 역할이 이것이다. */

let snapshot: 기록[] = readAll();
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): 기록[] {
  return snapshot;
}

function setRecords(next: 기록[]): void {
  snapshot = next;
  writeAll(next);
  emit();
}

/* 다른 탭에서 기록이 바뀌면 따라간다. 모듈 수준에 한 번만 붙인다. */
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== RECORDS_KEY) return;
    snapshot = readAll();
    emit();
  });
}

/* ---------------- 달성률 ---------------- */

function weightOf(강도: string | undefined): number {
  const w = SCORE_WEIGHT[강도 ?? ''];
  return w === undefined ? 1 : w;
}

function scoreOf(list: 기록[]): number {
  return list.reduce((sum, r) => sum + (Number(r.시간분) || 0) * weightOf(r.강도), 0);
}

function inWeek(list: 기록[], start: number): 기록[] {
  return list.filter((r) => {
    const t = new Date(r.일시).getTime();
    return t >= start && t < start + WEEK_MS;
  });
}

export interface 주간통계 {
  주시작: number;
  점수: number;
  목표: number;
  달성률: number;
  저강도횟수: number;
  근력일수: number;
  근력목표: number;
  이번주: number;
  /** 인덱스 0 이 월요일 */
  요일분: number[];
  연속주차: number;
  전체: 기록[];
}

export function computeStats(
  list: 기록[],
  isStrength: (sport: string) => boolean,
  now: number = Date.now(),
): 주간통계 {
  const start = weekStart(now);
  const week = inWeek(list, start);

  const scored = week.filter((r) => weightOf(r.강도) > 0);
  const low = week.filter((r) => weightOf(r.강도) === 0);
  const 점수 = scoreOf(scored);

  // 근력은 '일수'로 센다 — 같은 날 두 번 해도 하루다
  const strengthDays = new Set(
    week.filter((r) => isStrength(r.종목)).map((r) => r.일시.slice(0, 10)),
  );

  // 요일 스트립용 — 주시작이 KST 월요일이므로 인덱스 0 이 월요일이다
  const byDay = [0, 0, 0, 0, 0, 0, 0];
  week.forEach((r) => {
    const index = Math.floor((new Date(r.일시).getTime() - start) / DAY_MS);
    if (index >= 0 && index < 7) byDay[index] = (byDay[index] ?? 0) + (Number(r.시간분) || 0);
  });

  let streak = 0;
  for (let s = start; ; s -= WEEK_MS) {
    if (scoreOf(inWeek(list, s)) < GOAL_MIN) break;
    streak += 1;
    if (streak > 52) break;
  }

  return {
    주시작: start,
    점수: Math.round(점수),
    목표: GOAL_MIN,
    달성률: Math.round((점수 / GOAL_MIN) * 100),
    저강도횟수: low.length,
    근력일수: strengthDays.size,
    근력목표: STRENGTH_GOAL_DAYS,
    이번주: week.length,
    요일분: byDay,
    연속주차: streak,
    전체: [...list].sort(
      (a, b) => new Date(b.일시).getTime() - new Date(a.일시).getTime(),
    ),
  };
}

/* ---------------- 훅 ---------------- */

export interface RecordsApi {
  records: 기록[];
  stats: 주간통계;
  add(record: Pick<기록, '종목' | '시간분' | '강도'> & Partial<기록>): 기록;
  remove(id: string): void;
  /** 종목 마스터가 정하는 기본 강도. 화면이 강도를 하드코딩하지 않게 한다. */
  intensityOf(sport: string): 강도 | null;
  isStrength(sport: string): boolean;
}

/** 종목 마스터를 넘겨야 강도·근력 여부를 알 수 있다 — 출처는 `sport_master.csv` 하나다. */
export function useRecords(sports: 종목마스터[]): RecordsApi {
  const records = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const intensityOf = useCallback(
    (sport: string) => sports.find((s) => s.종목 === sport)?.강도 ?? null,
    [sports],
  );

  const isStrength = useCallback(
    (sport: string) => Boolean(sports.find((s) => s.종목 === sport)?.근력),
    [sports],
  );

  const add = useCallback<RecordsApi['add']>((record) => {
    const full: 기록 = {
      id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()),
      일시: kstIso(Date.now()),
      메모: '',
      샘플: false,
      ...record,
    };
    setRecords([...getSnapshot(), full]);
    return full;
  }, []);

  const remove = useCallback((id: string) => {
    setRecords(getSnapshot().filter((r) => r.id !== id));
  }, []);

  const stats = useMemo(
    () => computeStats(records, isStrength),
    [records, isStrength],
  );

  return { records, stats, add, remove, intensityOf, isStrength };
}
