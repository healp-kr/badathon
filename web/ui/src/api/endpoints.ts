/* 데이터 진입점 11종 — 화면이 데이터를 얻는 유일한 파일.
 *
 * **2026-09-05 정적화.** 예전에는 이 파일이 `fetch('/api/...')` 를 부르고 FastAPI 가
 * 답했다. 지금은 같은 계산이 브라우저 안에서 끝난다 — `src/engine/` 이 파이썬 엔진의
 * 포팅이고, `tests/golden/` 이 그 결과가 파이썬과 같은지 지킨다.
 *
 * **함수 이름과 반환 모양은 그대로 두었다.** 화면 컴포넌트는 백엔드가 사라진 것을
 * 모른다. 서버로 되돌리고 싶어지면 이 파일만 다시 fetch 로 바꾸면 된다.
 *
 * 비동기 서명도 유지한다. 계산은 즉시 끝나지만 호출부가 전부 `await` 로 쓰고 있고,
 * 동기로 바꾸면 무거운 계산이 렌더를 막는 형태가 된다.
 *
 * 예외 하나: `sendEvent` 는 **아무것도 하지 않는다.** 로그를 받을 서버가 없다.
 * 설문 응답이 기기 밖으로 나가지 않는다는 것이 정적화의 이유 중 하나다.
 */
import { serve } from '../engine/serve';
import { applyContext, loadContext } from '../engine/context';
import {
  boundaryFeatures,
  districtCenter,
  isSupported,
  listDistricts,
  resolveDistrict,
} from '../engine/locate';
import { findFacilities } from '../engine/facility';
import { pins } from '../engine/mapdata';
import { getCrowding, slotToHour } from '../engine/crowding';
import SURVEY_SCHEMA from '../engine/data/survey_schema.json';
import SPORTS from '../engine/data/sports.json';
import { fallbackOf } from '../engine/facility';
import type {
  CrowdingResponse,
  DistrictsResponse,
  EventRequest,
  FacilitiesResponse,
  LocateResponse,
  MapFacilitiesResponse,
  ServeRequest,
  ServeResponse,
  SportsResponse,
  SurveySchema,
  환경,
} from './types';

/** serve() 에서 받는 후보 수. 재정렬 뒤 DISPLAY_N 으로 자른다 */
const CANDIDATE_N = 10;
const DISPLAY_N = 3;

/** 백엔드 시절의 `ApiError` 자리. 화면이 `detail` 을 그대로 사용자에게 보여준다. */
export class DataError extends Error {
  constructor(readonly detail: string) {
    super(detail);
    this.name = 'DataError';
  }
}

/** 설문 문항. 빌드 시점에 `web/schema.py` 가 모델 범주와 대조한 결과다 —
 *  어긋나면 빌드가 실패하므로 어긋난 채로 배포될 수 없다. */
export const fetchSurveySchema = async (): Promise<SurveySchema> =>
  SURVEY_SCHEMA as unknown as SurveySchema;

export const fetchDistricts = async (): Promise<DistrictsResponse> =>
  ({
    districts: listDistricts(),
    note: '지원 지역 밖에서는 주변 정보를 제공하지 않는다',
  }) as unknown as DistrictsResponse;

/** 종목 목록 + 기본 강도. 기록 화면이 강도를 하드코딩하지 않게 한다.
 *
 * 달성률 공식(Σ중 + Σ고×2)이 이 강도 값을 그대로 신뢰하므로,
 * `sport_master.csv` 와 어긋나면 안 된다 — 출처는 여기 하나다.
 */
export const fetchSports = async (): Promise<SportsResponse> => {
  const catalog = (SPORTS as { sports: Array<Record<string, unknown>> }).sports.map((row) => ({
    ...row,
    // 시설을 쓰지 않는 종목('시설불필요'·'집')인지 — 지도가 기본 종목을 고를 때 본다
    대체처리: fallbackOf(row['종목'] as string),
  }));
  return {
    sports: catalog,
    note: '강도는 sport_master.csv 대표값이다. 사용자가 세게 했는지 여부는 모른다',
  } as unknown as SportsResponse;
};

/** 좌표 → 자치구. **좌표는 여기서만 쓰고 어디에도 저장하지 않는다.**
 *  이제는 저장할 서버조차 없다 — 판정이 브라우저 안에서 끝난다. */
export const locate = async (lat: number, lon: number): Promise<LocateResponse> =>
  resolveDistrict(lat, lon) as unknown as LocateResponse;

/** 기상·대기·자외선 합성. 실패할 수 있으므로 `optional()` 과 함께 쓴다. */
export const fetchContext = async (district: string): Promise<환경> => {
  const ctx = await loadContext(district);
  if (!ctx) throw new DataError('환경 정보를 불러오지 못했습니다');
  return ctx as 환경;
};

/** 개인화 처방. 이 앱의 중심 호출이다.
 *
 *  결과를 저장해 재사용하면 안 된다 — 응답에는 그 시점의 날씨로 재정렬된 순서가 들어 있다.
 *  설문 답변(payload)을 저장했다가 다시 호출하는 것이 옳다.
 */
export const requestServe = async (body: ServeRequest): Promise<ServeResponse> => {
  const result = serve(body.payload, { topN: CANDIDATE_N });

  const district = body.district ?? null;
  const ctx = district && isSupported(district) ? await loadContext(district) : null;

  const view = applyContext(
    result,
    ctx,
    (body.payload as Record<string, unknown>)['운동시간대'] as string | null,
    DISPLAY_N,
  );
  view['session_id'] = body.session_id ?? newSessionId();
  return view as ServeResponse;
};

/** 종목 → 주변 시설·예약·접근성 */
export const fetchFacilities = async (
  sport: string,
  opts: { district?: string | null; lat?: number; lon?: number } = {},
): Promise<FacilitiesResponse> =>
  findFacilities(sport, {
    district: opts.district ?? null,
    lat: opts.lat ?? null,
    lon: opts.lon ?? null,
  }) as FacilitiesResponse;

/** 지도용 핀 묶음. 좌표가 없는 예약 시설은 `좌표없는예약` 으로 따로 나간다. */
export const fetchMapFacilities = async (
  sport: string,
  opts: {
    district?: string | null;
    lat?: number;
    lon?: number;
    limit?: number;
    reservableOnly?: boolean;
  } = {},
): Promise<MapFacilitiesResponse> => {
  const district = opts.district ?? null;
  let lat = opts.lat ?? null;
  let lon = opts.lon ?? null;

  if (lat === null && district && isSupported(district)) {
    const center = districtCenter(district); // 위치를 못 받아도 지도는 열려야 한다
    if (center) [lat, lon] = center;
  }

  const limit = Math.max(1, Math.min(opts.limit ?? 20, 100));
  const result = pins(sport, {
    district,
    lat,
    lon,
    limit,
    reservableOnly: opts.reservableOnly ?? false,
  });
  result['중심'] = districtCenter(district) ?? null;
  return result as MapFacilitiesResponse;
};

/** 자치구 경계 폴리곤 (GeoJSON FeatureCollection). 타일이 안 떠도 이것만은 그려진다. */
export const fetchBoundary = async (
  district?: string | null,
): Promise<GeoJSON.FeatureCollection> =>
  boundaryFeatures(district ?? null) as GeoJSON.FeatureCollection;

/** 시간대 혼잡도 */
export const fetchCrowding = async (
  district: string,
  opts: { daytype?: string; hour?: number | null; slot?: string | null } = {},
): Promise<CrowdingResponse> => {
  let hour = opts.hour ?? null;
  if (hour === null && opts.slot) hour = slotToHour(opts.slot) ?? null;
  const result = getCrowding(district, opts.daytype ?? '평일', hour);
  if (result === null) throw new DataError('혼잡도 데이터가 없는 지역입니다');
  return result as unknown as CrowdingResponse;
};

/** 상호작용 로그 — **정적 배포에서는 아무것도 하지 않는다.**
 *
 * 예전에는 서버가 JSONL 로 남겼다. 서버가 사라지면서 남길 곳도 사라졌고,
 * 그 대신 설문 응답(나이·성별·키·몸무게·불편부위)이 기기 밖으로 나가지 않게 됐다.
 * 호출부를 지우지 않고 함수를 남겨 둔 것은, 나중에 동의를 받고 수집을 되살릴 때
 * 이 한 곳만 고치면 되게 하려는 것이다.
 */
export const sendEvent = async (_body: EventRequest): Promise<{ ok: boolean }> => ({ ok: true });

function newSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
