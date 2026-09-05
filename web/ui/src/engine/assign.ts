/* 배정 층 (A2 · A4 · A5) — `assignment/assign.py` 의 포팅.
 *
 * 학습이 없다. params/*.json 의 파라미터로 계산만 한다. 그래서 브라우저로 그대로
 * 옮길 수 있었다 — 원본이 numpy 를 쓰지만 실제 연산은 log·exp·정렬·유클리드 거리뿐이다.
 *
 * 파이썬과 **한 글자도 다르면 안 된다**. 어긋나기 쉬운 곳은 세 군데이고 전부 막아 두었다.
 *   · 반올림      → `pyRound` (은행가 반올림). `Math.round` 를 쓰면 조용히 어긋난다
 *   · 정렬 안정성 → 파이썬 `sorted` 와 JS `sort` 는 둘 다 안정 정렬이라 같다.
 *                   numpy `argsort` 는 비안정이지만 클래스가 12개 이하라 삽입정렬로
 *                   떨어져 사실상 안정이다 (골든 194건이 이를 확인한다)
 *   · 결측        → pandas 의 NaN 을 JSON 에서 null 로 옮겼다. 문자열도 숫자도 아니다
 *
 * 검증: `node tests/run.mjs`
 */
import PREFERENCE from './data/preference_model.json' with { type: 'json' };
import FITNESS from './data/fitness_model.json' with { type: 'json' };
import { pyRound } from './pyround.ts';

/* 설문 문항명 → 모델 변수명. **순서가 의미를 가진다** — `used_items`·`skipped_items`
 * 의 나열 순서가 파이썬 dict 의 삽입 순서를 그대로 따라야 한다. */
const ITEM_TO_VAR: ReadonlyArray<readonly [string, string]> = [
  ['운동빈도', '운동빈도_1'],
  ['운동요일', '운동요일_1'],
  ['운동시간대', '운동시간대_1'],
  ['운동목적', '운동목적_1'],
  ['운동강도', '운동강도_1'],
  ['체력인지', '체력인지'],
];

const ELDERLY_PREFERENCE_AGE = 60; // 선호 모델의 노인 경계
const ELDERLY_FITNESS_AGE = 65; // 체력 모델의 노인 경계 (측정 프로토콜)
const ELDERLY_DISPLAY_AGE = 60; // 서비스 표시 라벨의 노인 경계
const MIN_FITNESS_AGE = 19; // 19세 미만은 체력 축 미부여

export class AssignmentError extends Error {}

export interface Routing {
  preference_segment: string | null;
  fitness_group: string | null;
  display_age_group: string;
  skip_reason: { preference: string | null; fitness: string | null };
}

export interface RankedClass {
  class_id: string;
  name: string;
  probability: number;
}

export interface PreferenceResult {
  segment: string;
  class_id: string;
  name: string;
  probability: number;
  runner_up: RankedClass | null;
  margin: number;
  ranked: RankedClass[];
  used_items: string[];
  skipped_items: string[];
}

export interface FitnessResult {
  group: string;
  segment: string;
  confidence: number;
  ambiguous: boolean;
  alternative: string;
  z: Record<string, number>;
  종합체력z: number;
  missing_axes: string[];
  distances: Record<string, number>;
}

/* JSON 은 구조가 넓어 any 로 받고 접근 지점에서 좁힌다.
 * 파라미터 파일은 `build_params.py` 가 만들고 형태가 고정돼 있다. */
type Json = any;

// ------------------------------------------------------------------
// A5. 라우팅
// ------------------------------------------------------------------
/** 나이·성별·참여여부로 어느 모델을 태울지 결정한다.
 *
 * 세 경계가 서로 다르다 (의도된 설계): 선호 60 / 체력 65 / 표시 60
 */
export function route(age: unknown, sex: unknown, regularExercise = true): Routing {
  if (sex !== '남' && sex !== '여') {
    throw new AssignmentError(`성별은 '남' 또는 '여': ${pyRepr(sex)}`);
  }
  if (typeof age !== 'number' || Number.isNaN(age) || !(age > 0 && age < 120)) {
    throw new AssignmentError(`나이 범위 오류: ${pyRepr(age)}`);
  }

  const sexFull = sex === '남' ? '남성' : '여성';

  let preferenceSegment: string | null = null;
  if (regularExercise) {
    const stage = age >= ELDERLY_PREFERENCE_AGE ? '노인' : '성인';
    preferenceSegment = `${stage}_${sexFull}`;
  }

  let fitnessGroup: string | null = null;
  if (age >= MIN_FITNESS_AGE) {
    const stage = age >= ELDERLY_FITNESS_AGE ? '노인' : '성인';
    fitnessGroup = `${stage} ${sex}`;
  }

  return {
    preference_segment: preferenceSegment,
    fitness_group: fitnessGroup,
    display_age_group: age >= ELDERLY_DISPLAY_AGE ? '노인' : '성인',
    skip_reason: {
      preference: regularExercise ? null : '규칙적 체육활동 비참여자',
      fitness: fitnessGroup ? null : '19세 미만은 체력 축 미부여',
    },
  };
}

// ------------------------------------------------------------------
// A2. 선호 유형 배정
// ------------------------------------------------------------------
/** LCA posterior 를 직접 계산한다. 학습된 분류기가 아니다.
 *
 * answers 에 없거나 levels 에 없는 문항은 해당 항을 건너뛴다(주변화).
 * → 문항을 줄여도 그대로 동작한다.
 */
export function assignPreference(
  answers: Record<string, unknown>,
  segment: string,
): PreferenceResult {
  const segments = (PREFERENCE as Json).segments;
  if (!Object.prototype.hasOwnProperty.call(segments, segment)) {
    throw new AssignmentError(`알 수 없는 세그먼트: ${pyRepr(segment)}`);
  }
  const spec = segments[segment];

  // np.log(class_prob + 1e-300)
  let logProb: number[] = (spec.class_prob as number[]).map((p) => Math.log(p + 1e-300));
  const used: string[] = [];
  const skipped: string[] = [];

  for (const [item, variable] of ITEM_TO_VAR) {
    const raw = answers[item];
    const levels = spec.indicators[variable].levels as string[];

    if (raw === undefined || raw === null) {
      skipped.push(item);
      continue;
    }
    let value = raw as string;
    if (!levels.includes(value)) {
      // 무응답 범주가 학습돼 있으면 그쪽으로, 없으면 건너뜀
      if (levels.includes('무응답')) {
        value = '무응답';
      } else {
        skipped.push(item);
        continue;
      }
    }
    const idx = levels.indexOf(value);
    const rp = spec.indicators[variable].response_prob as number[][]; // [클래스][범주]
    logProb = logProb.map((lp, k) => lp + Math.log(rp[k]![idx]! + 1e-300));
    used.push(item);
  }

  const maxLog = Math.max(...logProb);
  const unnormalized = logProb.map((lp) => Math.exp(lp - maxLog));
  const total = unnormalized.reduce((a, b) => a + b, 0);
  const posterior = unnormalized.map((v) => v / total);

  // np.argsort(-posterior) — 내림차순. 동점이면 낮은 인덱스가 앞 (삽입정렬과 같다)
  const order = posterior
    .map((_, i) => i)
    .sort((a, b) => posterior[b]! - posterior[a]!);

  const classes = spec.classes as Array<{ class_id: string; name: string }>;
  const ranked: RankedClass[] = order.map((i) => {
    const klass = classes[i]!;
    return { class_id: klass.class_id, name: klass.name, probability: pyRound(posterior[i]!, 4) };
  });
  const margin =
    order.length > 1 ? posterior[order[0]!]! - posterior[order[1]!]! : 1.0;

  const top = ranked[0]!;
  return {
    segment,
    class_id: top.class_id,
    name: top.name,
    probability: top.probability,
    runner_up: ranked.length > 1 ? ranked[1]! : null,
    margin: pyRound(margin, 4),
    ranked,
    used_items: used,
    skipped_items: skipped,
  };
}

// ------------------------------------------------------------------
// A4. 체력 유형 배정
// ------------------------------------------------------------------
/** 자가평가 5단계 → 분위 매핑 → 최근접 중심.
 *
 * levels : {"근력": 1..5, ...} 1=매우 낮은 편 … 5=매우 높은 편
 */
export function assignFitness(
  levels: Record<string, unknown>,
  group: string,
  options: {
    heightCm?: number | null;
    weightKg?: number | null;
    ageBand?: number | null;
    zOverride?: Record<string, number> | null;
  } = {},
): FitnessResult {
  const groups = (FITNESS as Json).groups;
  if (!Object.prototype.hasOwnProperty.call(groups, group)) {
    throw new AssignmentError(`알 수 없는 체력 하위집단: ${pyRepr(group)}`);
  }
  const spec = groups[group];
  const axes = spec.axes as string[];
  const nLevels = (FITNESS as Json).n_levels as number;

  const { heightCm = null, weightKg = null, ageBand = null, zOverride = null } = options;

  const z = new Array<number>(axes.length).fill(0);
  const missing: string[] = [];

  axes.forEach((axis, j) => {
    if (zOverride && axis in zOverride) {
      z[j] = Number(zOverride[axis]);
      return;
    }

    const item = spec.axis_item[axis] as string | null;
    if (item === null) {
      // 신체조성 — 자가평가가 아니라 키·몸무게로 추정
      if (heightCm === null || heightCm === undefined ||
          weightKg === null || weightKg === undefined) {
        missing.push(axis);
        return; // 0 = 또래 평균
      }
      z[j] = estimateBodyComp(spec, heightCm, weightKg, ageBand);
      return;
    }

    const raw = levels[item];
    if (raw === undefined || raw === null) {
      missing.push(axis);
      return; // 0 = 평균으로 둠
    }
    const level = Math.trunc(Number(raw));
    if (!(level >= 1 && level <= nLevels)) {
      throw new AssignmentError(`${item} 응답은 1~${nLevels}: ${pyRepr(raw)}`);
    }
    z[j] = (spec.level_to_z[item] as number[])[level - 1]!;
  });

  const names = Object.keys(spec.centroids);
  const distances = names.map((name) => {
    const centroid = spec.centroids[name] as number[];
    let sum = 0;
    for (let i = 0; i < centroid.length; i++) {
      const d = centroid[i]! - z[i]!;
      sum += d * d;
    }
    return Math.sqrt(sum);
  });

  // np.argsort(distances) — 오름차순
  const order = distances.map((_, i) => i).sort((a, b) => distances[a]! - distances[b]!);
  const nearest = order[0]!;
  const second = order[1]!;
  const nearestDistance = distances[nearest]!;
  const confidence =
    nearestDistance > 0 ? distances[second]! / nearestDistance : Infinity;
  const gate = (FITNESS as Json).confidence_gate as number;

  const zOut: Record<string, number> = {};
  axes.forEach((axis, i) => {
    zOut[axis] = pyRound(z[i]!, 3);
  });
  const distanceOut: Record<string, number> = {};
  for (const i of order) distanceOut[names[i]!] = pyRound(distances[i]!, 3);

  const mean = z.reduce((a, b) => a + b, 0) / z.length;

  return {
    group,
    segment: names[nearest]!,
    confidence: pyRound(confidence, 3),
    ambiguous: confidence < gate,
    alternative: names[second]!,
    z: zOut,
    종합체력z: pyRound(mean, 3),
    missing_axes: missing,
    distances: distanceOut,
  };
}

function estimateBodyComp(
  spec: Json,
  heightCm: number,
  weightKg: number,
  ageBand: number | null,
): number {
  const reg = spec.body_comp_regression;
  if (heightCm <= 0 || weightKg <= 0) {
    throw new AssignmentError('키·몸무게는 양수여야 한다');
  }
  const bmi = weightKg / Math.pow(heightCm / 100, 2);

  let model: Json = null;
  if (ageBand !== null && ageBand !== undefined) {
    model = reg.by_age_band[String(Math.trunc(ageBand))] ?? null;
  }
  if (model === null) model = reg.pooled ?? null;
  if (model === null) return 0.0;

  const x = [heightCm, weightKg, bmi];
  const coef = model.coef as number[];
  let dot = 0;
  for (let i = 0; i < coef.length; i++) dot += coef[i]! * x[i]!;
  return model.intercept + dot;
}

/** 원자료 측정연령수 코드.
 *
 * 1=19-24, 2=25-29, 3=30-34, 4=35-39, 5=40-44, 6=45-49,
 * 7=50-54, 8=55-59, 9=60-64, 10=65-69, 11=70-74, 12=75-79, 13=80+
 */
export function ageToBand(age: number): number | null {
  const value = Math.trunc(age);
  if (value < 19) return null;
  if (value < 25) return 1;
  if (value < 65) return 2 + Math.floor((value - 25) / 5);
  return Math.min(13, 10 + Math.floor((value - 65) / 5));
}

/** 파이썬 `{!r}` 과 같은 모양으로 찍는다 — 오류 메시지까지 골든과 맞춰야 한다. */
export function pyRepr(value: unknown): string {
  if (typeof value === 'string') return `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
  if (value === null || value === undefined) return 'None';
  if (value === true) return 'True';
  if (value === false) return 'False';
  if (typeof value === 'number') {
    // 파이썬 int 는 소수점을 찍지 않는다
    return Number.isInteger(value) ? String(value) : String(value);
  }
  if (Array.isArray(value)) return `[${value.map(pyRepr).join(', ')}]`;
  return String(value);
}
