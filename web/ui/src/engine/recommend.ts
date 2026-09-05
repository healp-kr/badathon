/* B6. 추천 층 — `recommendation/recommend.py` 의 포팅.
 *
 * 두 축을 한 점수 안에서 저울질하지 않고 순서대로 적용한다.
 *
 *     ① 종목 선택      ← 선호축만 (데이터 기반)
 *     ② 안전 필터       ← 부상·연령은 하드 컷, 강도는 순위 강등
 *     ③ 강도·빈도 조절  ← 체력축
 *     ④ 보완 운동       ← 체력축 약한 부위
 *
 * 체력 배정 정확도가 50% 내외이므로 체력축은 종목 선택에 관여하지 않는다.
 * 배정이 틀려도 "엉뚱한 종목"이 아니라 "강도가 한 단계 어긋남"으로 실패하게 만드는 구조다.
 *
 * 포팅에서 조심한 것 — 원본이 pandas 에 기대던 동작들이다.
 *   · 빈 칸은 `NaN` 이었고 여기서는 `null` 이다. `isinstance(x, str)` 검사가
 *     그것을 걸러내던 자리는 `typeof x === 'string'` 으로 옮겼다
 *   · `_normalize` 의 폭이 0 이면 전부 0.5 다. 0 으로 나누지 않는다
 *   · `f"{x:.1f}"` 도 은행가 반올림이다 — `pyFormat` 을 쓴다
 *   · `chosen` 의 순회 순서가 결과 순서에 남는다 → `Map` 으로 삽입 순서를 지킨다
 */
import MATRIX from './data/preference_sport_matrix.json' with { type: 'json' };
import MASTER from './data/sport_master.json' with { type: 'json' };
import FACILITY from './data/sport_facility_map.json' with { type: 'json' };
import RULES from './data/rules.json' with { type: 'json' };
import { pyRound } from './pyround.ts';
import type { FitnessResult, PreferenceResult } from './assign.ts';

type Json = any;
type Row = Record<string, any>;

const MASTER_BY_SPORT = new Map<string, Row>(
  (MASTER as Row[]).map((row) => [row['종목'] as string, row]),
);
const FACILITY_BY_SPORT = new Map<string, Row>(
  (FACILITY as Row[]).map((row) => [row['종목'] as string, row]),
);
const RECOMMENDABLE = new Set(
  (MASTER as Row[]).filter((row) => row['추천가능'] === 'Y').map((row) => row['종목'] as string),
);

const INTENSITY_ORDER = ['저', '중', '고'];
const R = RULES as Json;
const OVER_CAP_PENALTY = R.scoring['강도상한초과_감산비율'] as number;

/** 파이썬 `f"{x:.Nf}"`. 포맷도 반올림이므로 은행가 규칙을 탄다. */
function pyFormat(x: number, digits: number): string {
  return pyRound(x, digits).toFixed(digits);
}

/** pandas 의 `NaN` 자리. 값이 없거나 숫자가 아니면 참. */
function isNa(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value));
}

/** `_normalize` — 폭이 0 에 가까우면 전부 0.5 로 둔다. */
function normalize(values: number[]): number[] {
  if (values.length === 0) return [];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (hi - lo < 1e-9) return values.map(() => 0.5);
  return values.map((v) => (v - lo) / (hi - lo));
}

export interface RecommendOptions {
  preferenceResult?: PreferenceResult | null;
  fitnessResult?: FitnessResult | null;
  age?: number | null;
  discomfortAreas?: string[] | null;
  playedSports?: string[] | null;
  interestedSports?: string[] | null;
  survey?: Record<string, unknown> | null;
  topN?: number | null;
}

export function recommend(options: RecommendOptions = {}): Json {
  const {
    preferenceResult = null,
    fitnessResult = null,
    age = null,
    discomfortAreas = null,
    playedSports = null,
    interestedSports = null,
    survey = null,
    topN = null,
  } = options;

  const discomfort = new Set(discomfortAreas ?? []);
  const chosen = userChoiceWeights(playedSports, interestedSports);
  const classId = preferenceResult ? preferenceResult.class_id : null;
  const baselineSports = new Set(R['기반활동']['종목'] as string[]);

  let ranked: Json[] = classId ? scoreSports(classId) : [];
  const prescription = prescribe(fitnessResult, age); // ③ 먼저 강도 상한을 정하고

  // 기반 활동은 두 갈래 어디에도 넣지 않고 따로 뺀다
  const baseline = ranked.filter((s) => baselineSports.has(s['종목']));
  ranked = ranked.filter((s) => !baselineSports.has(s['종목']));

  let familiarPool = familiarPoolOf(chosen, ranked, baselineSports);
  const newPool = ranked.filter((s) => !chosen.has(s['종목']));

  familiarPool = familiarPool.map((s) => applySurvey(s, survey));
  sortByWeightThenScore(familiarPool);

  const [familiar, exFamiliar] = applySafety(familiarPool, age, discomfort, prescription);
  const [newItems, exNew] = applySafety(rescoreNew(newPool, survey), age, discomfort, prescription);

  // 강도 상한 초과 종목은 점수가 깎인 채로 돌아온다. 여기서 다시 정렬해 반영한다
  sortByWeightThenScore(familiar);
  newItems.sort((a, b) => (b['점수'] ?? 0) - (a['점수'] ?? 0));

  const nFamiliar = topN ?? (R.buckets['익숙한_개수'] as number);
  const nNew = topN ?? (R.buckets['새로운_개수'] as number);

  return {
    선호유형: !preferenceResult
      ? null
      : {
          class_id: classId,
          name: preferenceResult.name ?? null,
          probability: preferenceResult.probability ?? null,
        },
    체력유형: !fitnessResult
      ? null
      : {
          segment: fitnessResult.segment,
          confidence: fitnessResult.confidence,
          ambiguous: fitnessResult.ambiguous,
          alternative: fitnessResult.alternative,
        },
    기반활동: baselineBlock(baseline, chosen),
    익숙한운동: familiar.slice(0, nFamiliar),
    새로운운동: newItems.slice(0, nNew),
    제외종목: exFamiliar.concat(exNew),
    처방: prescription,
    보완운동: supportExercises(fitnessResult),
    안내: guidance(fitnessResult, prescription, familiar, exFamiliar, chosen),
    면책: R.safety['면책'],
  };
}

/** `(사용자가중, 점수)` 내림차순. 파이썬 `sort(key=..., reverse=True)` 와 같은 안정 정렬. */
function sortByWeightThenScore(items: Json[]): void {
  items.sort((a, b) => {
    const w = (b['사용자가중'] ?? 0) - (a['사용자가중'] ?? 0);
    if (w !== 0) return w;
    return (b['점수'] ?? 0) - (a['점수'] ?? 0);
  });
}

/** 자주 해온 운동에 더 큰 가중. 둘 다 고르면 큰 쪽. */
function userChoiceWeights(
  playedSports: string[] | null,
  interestedSports: string[] | null,
): Map<string, number> {
  const wPlayed = R.buckets['자주해온_가중'] as number;
  const wInterest = R.buckets['관심_가중'] as number;
  const weights = new Map<string, number>();
  for (const sport of interestedSports ?? []) {
    weights.set(sport, Math.max(weights.get(sport) ?? 0, wInterest));
  }
  for (const sport of playedSports ?? []) {
    weights.set(sport, Math.max(weights.get(sport) ?? 0, wPlayed));
  }
  return weights;
}

/** 기반 활동 — 걷기는 어느 유형에서든 1위라 추천 갈래를 밀어낸다. 그래서 여기로 빼둔다.
 *
 * 계약상 계속 내보내지만 화면에는 싣지 않는다(2026-09-05).
 */
function baselineBlock(baseline: Json[], chosen: Map<string, number>): Json[] {
  const spec = R['기반활동'];
  const out: Json[] = [];
  for (const sport of spec['종목'] as string[]) {
    const found = baseline.find((s) => s['종목'] === sport);
    let item: Json;
    if (found) {
      item = { ...found };
    } else {
      const meta = MASTER_BY_SPORT.get(sport);
      if (!meta) continue;
      item = {
        종목: sport,
        강도: meta['강도'] ?? null,
        부담부위: areasOf(meta),
        고령적합: meta['고령적합'] ?? null,
        실내외: meta['실내외'] ?? null,
      };
    }
    item['처방'] = spec['처방'];
    item['근거'] = spec['근거'];
    item['이미하는중'] = chosen.has(sport);
    item['시설'] = facilityQuery(sport);
    out.push(item);
  }
  return out;
}

/** 설문 응답과 종목 속성을 맞춰 점수를 보정한다. 선호축 점수가 주이고 이것은 보정이다. */
function applySurvey(item: Json, survey: Record<string, unknown> | null): Json {
  if (!survey || item['점수'] === null || item['점수'] === undefined) return item;

  const cfg = R['설문반영'];
  const meta = MASTER_BY_SPORT.get(item['종목']) ?? {};
  let delta = 0;
  const reasons: string[] = [];

  const want = survey['운동강도'] as string | undefined;
  const have = item['강도'] as string | undefined;
  if (want !== undefined && have !== undefined &&
      INTENSITY_ORDER.includes(want) && INTENSITY_ORDER.includes(have)) {
    const gap = Math.abs(INTENSITY_ORDER.indexOf(want) - INTENSITY_ORDER.indexOf(have));
    if (gap === 0) {
      delta += cfg['강도일치_가산'];
      reasons.push(`원하시는 강도(${want})와 맞음`);
    } else if (gap >= 2) {
      delta -= cfg['강도2단계차이_감산'];
      reasons.push(`원하시는 강도(${want})와 차이가 큼`);
    }
  }

  if (survey['운동목적'] === '대인관계 및 사교') {
    const group = meta['그룹성'];
    if (group === '그룹') {
      delta += cfg['사교목적_그룹가산'];
      reasons.push('여럿이 함께하는 종목');
    } else if (group === '혼합') {
      delta += cfg['사교목적_혼합가산'];
    }
  }

  if (survey['운동시간대'] === '저녁(18-22시)' && meta['실내외'] === '실내') {
    delta += cfg['저녁시간대_실내가산'];
    reasons.push('저녁에 하기 좋은 실내 종목');
  }

  if (delta) {
    // 파이썬은 delta 가 0 이 아닐 때만 새 dict 를 만들고 맞춤이유를 붙인다.
    // 사교목적 '혼합' 만 걸리면 reasons 가 빈 배열인 채로 붙는다 — 그대로 맞춘다
    return { ...item, 점수: pyRound(item['점수'] + delta, 1), 맞춤이유: reasons };
  }
  return item;
}

/** 사용자가 고른 종목. 유형 적합도가 있으면 순위 보조로 쓴다.
 *
 * 그 유형에서 표본이 적어 행렬에 없는 종목도 사용자가 골랐으면 포함한다 —
 * 본인이 하겠다는 운동을 데이터가 없다고 빼면 안 된다.
 */
function familiarPoolOf(
  chosen: Map<string, number>,
  ranked: Json[],
  baselineSports: Set<string>,
): Json[] {
  const bySport = new Map<string, Json>(ranked.map((s) => [s['종목'] as string, s]));
  const pool: Json[] = [];

  for (const [sport, weight] of chosen) {
    if (baselineSports.has(sport)) continue; // 기반 활동은 따로 표시한다
    const meta = MASTER_BY_SPORT.get(sport);
    if (!meta) continue; // 마스터에 없는 종목명은 무시

    const found = bySport.get(sport);
    const item: Json = found
      ? { ...found }
      : {
          종목: sport,
          점수: null,
          선호점수비율: null,
          Lift: null,
          강도: meta['강도'] !== undefined ? meta['강도'] : '미확인',
          부담부위: areasOf(meta),
          고령적합: meta['고령적합'] ?? null,
          실내외: meta['실내외'] ?? null,
        };
    item['사용자가중'] = weight;
    item['이유'] =
      weight >= (R.buckets['자주해온_가중'] as number)
        ? '자주 해오신 운동입니다'
        : '관심 있다고 고르신 운동입니다';
    pool.push(item);
  }

  sortByWeightThenScore(pool);
  return pool;
}

/** '새로운 운동' 은 Lift 가중을 올려 그 유형을 차별화하는 종목이 드러나게 한다. */
function rescoreNew(pool: Json[], survey: Record<string, unknown> | null): Json[] {
  if (pool.length === 0) return pool;

  const wLift = R.buckets['새로운_Lift_가중'] as number;
  const cap = R.scoring['Lift_상한'] as number;

  const shares = pool.map((i) => (i['선호점수비율'] ? i['선호점수비율'] : 0));
  const lifts = pool.map((i) => Math.min(i['Lift'] ? i['Lift'] : 1.0, cap));
  const normShares = normalize(shares);
  const normLifts = normalize(lifts);

  const out: Json[] = pool.map((item, i) => {
    const score = ((1 - wLift) * normShares[i]! + wLift * normLifts[i]!) * 100;
    return applySurvey({ ...item, 점수: pyRound(score, 1) }, survey);
  });

  // 파이썬 sorted(..., reverse=True) 는 안정 정렬이다
  out.sort((a, b) => b['점수'] - a['점수']);
  return out;
}

// ------------------------------------------------------------------
// ① 종목 선택 — 선호축만
// ------------------------------------------------------------------
function scoreSports(classId: string): Json[] {
  let part = (MATRIX as Row[]).filter((row) => row['class_id'] === classId);
  if (part.length === 0) throw new Error(`행렬에 없는 클래스: ${classId}`);

  // 표본이 극소수인 종목은 Lift 가 과장되므로 먼저 잘라낸다
  part = part.filter(
    (row) =>
      row['참여가중인원'] >= (R.scoring['최소_참여가중인원'] as number) &&
      row['클래스참여율'] >= (R.scoring['최소_클래스참여율'] as number),
  );
  // "그 외 종목" 묶음은 사용자에게 제시할 수 없다
  part = part.filter((row) => RECOMMENDABLE.has(row['운동종목'] as string));
  if (part.length === 0) throw new Error(`추천 가능한 종목이 없다: ${classId}`);

  const wShare = R.scoring['선호점수비율_가중'] as number;
  const wLift = R.scoring['Lift_가중'] as number;
  const liftCap = R.scoring['Lift_상한'] as number;

  const share = part.map((row) => row['선호점수비율'] as number);
  const lift = part.map((row) => Math.min(isNa(row['Lift']) ? 1.0 : (row['Lift'] as number), liftCap));
  const normShare = normalize(share);
  const normLift = normalize(lift);

  const scored = part.map((row, i) => ({
    row,
    점수: (wShare * normShare[i]! + wLift * normLift[i]!) * 100,
  }));
  scored.sort((a, b) => b.점수 - a.점수);

  return scored.map(({ row, 점수 }) => {
    const meta = MASTER_BY_SPORT.get(row['운동종목'] as string) ?? {};
    return {
      종목: row['운동종목'],
      점수: pyRound(점수, 1),
      선호점수비율: pyRound(row['선호점수비율'] as number, 1),
      Lift: isNa(row['Lift']) ? null : pyRound(row['Lift'] as number, 2),
      강도: meta['강도'] !== undefined ? meta['강도'] : '미확인',
      부담부위: areasOf(meta),
      고령적합: meta['고령적합'] ?? null,
      // 날씨 재정렬은 표현 계층에서 한다. 종목명으로 실내외를 추측하게 두지 않는다
      실내외: meta['실내외'] ?? null,
      이유: reasonOf(row),
    };
  });
}

function reasonOf(row: Row): string {
  const lift = row['Lift'];
  if (!isNa(lift) && (lift as number) >= 1.5 && (row['클래스참여율'] as number) >= 3) {
    return `같은 유형에서 유독 많이 하는 종목 (평균 대비 ${pyFormat(lift as number, 1)}배)`;
  }
  if ((row['선호점수비율'] as number) >= 10) {
    return `같은 유형이 가장 많이 하는 종목 (선호도 ${pyFormat(row['선호점수비율'] as number, 0)}%)`;
  }
  return '같은 유형에서 자주 선택되는 종목';
}

// ------------------------------------------------------------------
// ② 안전 필터 — 부위·연령은 하드 컷, 강도는 원칙적으로 소프트
// ------------------------------------------------------------------
function applySafety(
  ranked: Json[],
  age: number | null,
  discomfortAreas: Set<string>,
  prescription: Json,
): [Json[], Json[]] {
  const kept: Json[] = [];
  const demoted: Json[] = [];
  const excluded: Json[] = [];

  const elderly = age !== null && age !== undefined && age >= 65;
  const cap = prescription['권장강도상한'];
  const capIdx = INTENSITY_ORDER.includes(cap)
    ? INTENSITY_ORDER.indexOf(cap)
    : INTENSITY_ORDER.length - 1;
  const hardGate = prescription['강도컷'] === '하드';

  for (let item of ranked) {
    let reason: string | null = null;
    const overlap = (item['부담부위'] as string[]).filter((a) => discomfortAreas.has(a));
    const intensity = item['강도'];
    const overCap = INTENSITY_ORDER.indexOf(effectiveIntensity(intensity)) > capIdx;

    if (overlap.length > 0) {
      // 파이썬 sorted(set) 과 같은 순서 — 한글은 코드포인트 순
      const unique = Array.from(new Set(overlap)).sort();
      reason = `불편 부위(${unique.join(', ')})와 겹쳐 제외`;
    } else if (elderly && item['고령적합'] === '비권장') {
      reason = '고령 사용자에게 기본 제외되는 종목';
    } else if (overCap && hardGate) {
      reason = `권장 강도 상한('${cap}')을 넘어 제외`;
    }

    if (reason) {
      excluded.push({ 종목: item['종목'], 사유: reason });
      continue;
    }

    if (intensity === '미확인') item = { ...item, 주의: '강도 미확인 종목' };
    // 장소 연결 레이어가 바로 쓸 수 있게 검색 대상 시설을 붙인다
    item = { ...item, 시설: facilityQuery(item['종목']) };

    if (overCap) {
      // 맨 뒤로 밀어버리면 목록 길이에 잘려 사실상 삭제가 된다.
      // 점수를 깎아 두고 정렬에 맡긴다 — 적합도가 뚜렷이 높으면 배지를 달고 남는다
      item = {
        ...item,
        강도주의: `권장하는 강도('${cap}')보다 강한 편입니다. 낮은 강도로 짧게 시작해 보세요`,
      };
      if (item['점수'] !== null && item['점수'] !== undefined) {
        item = { ...item, 점수: pyRound(item['점수'] * OVER_CAP_PENALTY, 1) };
      }
      demoted.push(item);
    } else {
      kept.push(item);
    }
  }
  return [kept.concat(demoted), excluded];
}

/** 강도 미확인 종목은 '중'으로 간주한다. */
function effectiveIntensity(intensity: unknown): string {
  return typeof intensity === 'string' && INTENSITY_ORDER.includes(intensity) ? intensity : '중';
}

function areasOf(meta: Row): string[] {
  const value = meta['부담부위'];
  if (typeof value !== 'string' || !value) return [];
  return value.split('|').filter(Boolean);
}

// ------------------------------------------------------------------
// 장소 연결 인계 — 실제 주변 시설 검색은 GIS 쪽에서 한다
// ------------------------------------------------------------------
export function facilityQuery(sport: string): Json {
  const row = FACILITY_BY_SPORT.get(sport);
  if (!row) {
    return {
      종목: sport,
      시설유형: [],
      시설대분류: [],
      신뢰도: '없음',
      비고: '표본 부족으로 시설 분포를 산출하지 않은 종목',
    };
  }

  const types: Json[] = [];
  const groups: Json[] = [];
  for (const i of [1, 2, 3]) {
    const name = row[`세부시설_${i}`];
    if (typeof name === 'string') types.push({ 이름: name, 비율: row[`세부시설_${i}_비율`] ?? null });
  }
  for (const i of [1, 2]) {
    const name = row[`시설대분류_${i}`];
    if (typeof name === 'string') groups.push({ 이름: name, 비율: row[`시설대분류_${i}_비율`] ?? null });
  }

  return {
    종목: sport,
    시설유형: types,
    시설대분류: groups,
    시설불필요_비율: row['시설불필요_비율'] ?? null,
    신뢰도: row['세부시설_신뢰도'] ?? null,
    표본: row['n'] ?? null,
  };
}

// ------------------------------------------------------------------
// ③ 강도·빈도 처방
// ------------------------------------------------------------------
function prescribe(fitnessResult: FitnessResult | null, age: number | null): Json {
  const stage = age !== null && age !== undefined && age >= 65 ? '노인' : '성인';
  const baseline = { ...R.baseline[stage] };
  const result: Json = {
    기준: baseline,
    생애주기: stage,
    조정: null,
    강도조정단계: 0,
    강도컷: '소프트',
    권장강도상한: capIntensity(0),
  };

  if (!fitnessResult) return result;

  const adjust = R.segment_adjust[fitnessResult.segment];
  if (!adjust) return result;

  // 배정이 모호한 것은 '체력이 낮다'가 아니라 '우리가 모른다'는 뜻이다.
  // 확신도는 종목을 지우는 데 쓰지 않고 안내 문구로만 알린다.
  const steps = adjust['강도조정'] ?? 0;

  result['조정'] = {
    세그먼트: fitnessResult.segment,
    시작규칙: adjust['시작규칙'] ?? null,
    메시지: adjust['메시지'] ?? null,
    근거: adjust['근거'] ?? null,
  };
  result['강도조정단계'] = steps;
  result['권장강도상한'] = capIntensity(steps);

  // 상한 초과를 '제외'로 처리하는 경우는 실제 위험군 하나뿐이다 —
  // 노인 + 전반적 저조형 + 배정 확정
  if (stage === '노인' && steps < 0 && !fitnessResult.ambiguous) {
    result['강도컷'] = '하드';
  }
  return result;
}

function capIntensity(steps: number): string {
  const idx = Math.max(0, Math.min(INTENSITY_ORDER.length - 1, 2 + steps));
  return INTENSITY_ORDER[idx]!;
}

// ------------------------------------------------------------------
// ④ 보완 운동
// ------------------------------------------------------------------
function supportExercises(fitnessResult: FitnessResult | null, threshold = -0.3): Json[] {
  if (!fitnessResult) return [];
  const z = fitnessResult.z ?? {};

  // 파이썬: sorted((v, k) for ...) — z 오름차순, 같으면 축 이름 순
  const weak = Object.entries(z)
    .filter(([, v]) => v < threshold)
    .sort((a, b) => (a[1] !== b[1] ? a[1] - b[1] : a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));

  const out: Json[] = [];
  for (const [axis, value] of weak) {
    const spec = R.weak_axis_support[axis];
    if (!spec || !spec['운동'] || spec['운동'].length === 0) continue; // 순발력처럼 근거가 없는 축
    const basis = spec['근거'] as string;
    out.push({
      축: axis.replace('z_', ''),
      z: pyRound(value, 2),
      운동: spec['운동'],
      처방: spec['처방'],
      근거: basis,
      표현: basis.includes('없음') || basis.includes('약함') ? '제안' : '지침',
    });
  }
  return out.slice(0, 2);
}

// ------------------------------------------------------------------
// 안내 문구
// ------------------------------------------------------------------
function guidance(
  fitnessResult: FitnessResult | null,
  prescription: Json,
  familiar: Json[],
  excludedFamiliar: Json[],
  chosen: Map<string, number>,
): string[] {
  const notes: string[] = [];
  if (chosen.size > 0 && familiar.length === 0 && excludedFamiliar.length > 0) {
    // 고른 종목이 전부 걸러진 경우 — 이유를 밝히지 않으면 사용자는 무시당했다고 느낀다
    notes.push('고르신 운동은 지금 단계에서 부담이 될 수 있어 대신 비슷한 종목을 담았습니다');
  } else if (chosen.size === 0) {
    notes.push('관심 있는 운동을 골라주시면 더 맞는 추천을 드릴 수 있습니다');
  }
  if (fitnessResult && fitnessResult.ambiguous) {
    notes.push(
      `체력 유형이 '${fitnessResult.segment}'과 ` +
        `'${fitnessResult.alternative}' 사이에 걸쳐 있습니다. ` +
        `강도는 무리하지 않는 선에서 조절해 주세요`,
    );
  }
  if (prescription['강도조정단계'] < 0) {
    notes.push(R.segment_adjust['전반적 저조형']['시작규칙']);
  }
  notes.push(...(R.safety['상담안내'] as string[]).slice(0, 1));
  return notes;
}
