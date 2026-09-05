/* 단일 진입점 — `serve.py` 의 포팅.
 *
 * 설문 응답 하나를 넣으면 배정·추천·시설 검색 조건까지 한 번에 돌려준다.
 * 화면은 이 함수만 알면 되고, 내부 구조(assign · recommend)는 몰라도 된다.
 *
 * 백엔드가 있던 시절에는 `POST /api/serve` 가 이 자리였다. 정적화하면서 같은 계약을
 * 브라우저 안으로 옮겼다 — **입출력은 한 글자도 바꾸지 않았다**. 그래야 파이썬 엔진으로
 * 만든 골든 파일이 그대로 정답지가 된다.
 *
 * 오류 메시지도 계약의 일부다. 파이썬 `RequestError` 의 문구를 그대로 재현한다 —
 * 화면이 그 문구를 사용자에게 보여주기 때문이다.
 */
import VERSION from './data/version.json' with { type: 'json' };
import {
  AssignmentError,
  ageToBand,
  assignFitness,
  assignPreference,
  pyRepr,
  route,
  type FitnessResult,
  type PreferenceResult,
} from './assign.ts';
import { recommend } from './recommend.ts';

type Json = any;

export const API_VERSION = '1.1.0';

/** 설문 문항 → 내부 필드. 순서가 `used_items` 에 남는다. */
const PREFERENCE_ITEMS = ['운동빈도', '운동요일', '운동시간대', '운동목적', '운동강도', '체력인지'];
const REQUIRED = ['나이', '성별'];

/** 입력이 계약을 벗어남. 백엔드 시절 4xx 로 나가던 성질의 오류. */
export class RequestError extends Error {}

export interface ServeOptions {
  requestId?: string | null;
  /** 갈래별 후보 개수. 기본은 규칙 파일의 값(3)이다.
   *  표현 계층이 날씨로 재정렬할 계획이면 넉넉히(예: 6) 받아야 한다. */
  topN?: number | null;
}

export function serve(payload: Json, options: ServeOptions = {}): Json {
  validate(payload);

  const age = payload['나이'];
  const sex = payload['성별'];
  const regular = Boolean(payload['규칙적참여'] ?? true);

  const routing = route(age, sex, regular);

  let preference: PreferenceResult | null = null;
  if (routing.preference_segment) {
    const answers: Record<string, unknown> = {};
    for (const key of PREFERENCE_ITEMS) {
      const value = payload[key];
      if (value !== null && value !== undefined) answers[key] = value;
    }
    if (Object.keys(answers).length > 0) {
      preference = assignPreference(answers, routing.preference_segment);
    }
  }

  let fitness: FitnessResult | null = null;
  if (routing.fitness_group) {
    const levels = (payload['체력자가평가'] ?? {}) as Record<string, unknown>;
    const height = payload['키'];
    const weight = payload['몸무게'];
    // 파이썬 `if levels or (height and weight)` — 빈 dict 와 0 은 거짓이다
    if (Object.keys(levels).length > 0 || (truthy(height) && truthy(weight))) {
      fitness = assignFitness(levels, routing.fitness_group, {
        heightCm: height ?? null,
        weightKg: weight ?? null,
        ageBand: ageToBand(age),
      });
    }
  }

  const survey: Record<string, unknown> = {};
  for (const key of ['운동목적', '운동시간대', '운동강도']) {
    survey[key] = payload[key] ?? null;
  }

  const result = recommend({
    preferenceResult: preference,
    fitnessResult: fitness,
    age,
    discomfortAreas: payload['불편부위'] ?? null,
    playedSports: payload['자주해온운동'] ?? null,
    interestedSports: payload['관심운동'] ?? null,
    survey,
    topN: options.topN ?? null,
  });

  return {
    request_id: options.requestId ?? randomId(),
    생성시각: new Date().toISOString(),
    api_version: API_VERSION,
    model_version: (VERSION as Json).model_version,
    라우팅: routing,
    선호유형: result['선호유형'],
    체력유형: result['체력유형'],
    기반활동: result['기반활동'],
    익숙한운동: result['익숙한운동'],
    새로운운동: result['새로운운동'],
    제외종목: result['제외종목'],
    처방: result['처방'],
    보완운동: result['보완운동'],
    시설검색조건: facilityRequests(result),
    안내: result['안내'],
    면책: result['면책'],
  };
}

function truthy(value: unknown): boolean {
  return !(value === null || value === undefined || value === 0 || value === false || value === '');
}

function validate(payload: Json): void {
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new RequestError('payload 는 dict 여야 한다');
  }

  const missing = REQUIRED.filter((k) => payload[k] === null || payload[k] === undefined);
  if (missing.length > 0) {
    throw new RequestError(`필수 항목 누락: ${missing.join(', ')}`);
  }

  try {
    route(payload['나이'], payload['성별'], Boolean(payload['규칙적참여'] ?? true));
  } catch (error) {
    if (error instanceof AssignmentError) throw new RequestError(error.message);
    throw error;
  }

  for (const key of ['키', '몸무게']) {
    const value = payload[key];
    if (value !== null && value !== undefined) {
      if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) {
        throw new RequestError(`${key}는 양수여야 한다: ${pyRepr(value)}`);
      }
    }
  }

  const levels = payload['체력자가평가'];
  if (levels !== null && levels !== undefined) {
    if (typeof levels !== 'object' || Array.isArray(levels)) {
      throw new RequestError('체력자가평가는 dict 여야 한다');
    }
    for (const [item, value] of Object.entries(levels)) {
      if (!Number.isInteger(value) || !((value as number) >= 1 && (value as number) <= 5)) {
        throw new RequestError(`체력자가평가 '${item}' 는 1~5 정수여야 한다: ${pyRepr(value)}`);
      }
    }
  }

  for (const key of ['관심운동', '자주해온운동', '불편부위']) {
    const value = payload[key];
    if (value !== null && value !== undefined && !Array.isArray(value)) {
      throw new RequestError(`${key}는 리스트여야 한다`);
    }
  }
}

/** GIS 레이어가 그대로 받아 쓸 검색 조건.
 *
 * 여기서 주변 시설을 찾지 않는다 — 무엇을 찾아야 하는지만 정한다.
 */
function facilityRequests(result: Json): Json[] {
  const requests: Json[] = [];
  const seen = new Set<string>();
  const buckets: Array<[string, Json[]]> = [
    ['기반활동', result['기반활동']],
    ['익숙한운동', result['익숙한운동']],
    ['새로운운동', result['새로운운동']],
  ];

  for (const [bucket, items] of buckets) {
    for (const item of items ?? []) {
      const sport = item['종목'];
      if (seen.has(sport)) continue;
      seen.add(sport);
      const facility = item['시설'] ?? {};
      requests.push({
        종목: sport,
        갈래: bucket,
        시설유형: (facility['시설유형'] ?? []).map((t: Json) => t['이름']),
        시설대분류: (facility['시설대분류'] ?? []).map((g: Json) => g['이름']),
        시설불필요_비율: facility['시설불필요_비율'] ?? null,
        신뢰도: facility['신뢰도'] ?? null,
      });
    }
  }
  return requests;
}

function randomId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
