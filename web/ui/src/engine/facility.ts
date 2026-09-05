/* 종목 → 주변 실제 시설 — `geo/facility.py` 의 포팅.
 *
 * `serve()` 의 `시설검색조건` 이 "무엇을 찾을지"를 말한다면, 이 모듈은 "어디에 있는지"를
 * 답한다. 사이의 분류 체계 차이는 `sport_facility_join` 이 메운다.
 *
 * 반경 2km 로 먼저 찾고, 3건 미만이면 자치구 전체로 넓힌다(`확장=true`).
 * 결과가 없으면 지우지 않고 `대체처리` 를 돌려준다 — 화면은 빈 목록 대신 그것을 보여준다.
 *
 * 원본은 `csv.DictReader` 로 읽어 **모든 값이 문자열**이었고, 위경도만 `_floatify` 가
 * 따로 숫자로 바꾸면서 실패한 행을 버렸다. 데이터를 JSON 으로 옮길 때도 문자열 그대로
 * 두었으므로 그 동작을 여기서 똑같이 재현한다.
 */
import FACILITIES_RAW from './data/facilities.json' with { type: 'json' };
import RESERVATIONS_RAW from './data/reservations.json' with { type: 'json' };
import SUBWAY_RAW from './data/subway.json' with { type: 'json' };
import BUS_RAW from './data/bus.json' with { type: 'json' };
import PARKING_RAW from './data/parking.json' with { type: 'json' };
import JOIN_RAW from './data/sport_facility_join.json' with { type: 'json' };
import { pyRound } from './pyround.ts';

type Json = any;
type Raw = Record<string, string>;
/** 위경도가 숫자로 바뀐 행. 나머지 열은 문자열 그대로다. */
type Geo = Record<string, any>;

export const DEFAULT_RADIUS_M = 2000;
const MIN_RESULTS = 3;

/** 파이썬 `_floatify` — 지정한 열을 float 으로 바꾸고, 실패한 **행 전체를 버린다**. */
function floatify(rows: Raw[], keys: string[]): Geo[] {
  const out: Geo[] = [];
  for (const row of rows) {
    const copy: Geo = { ...row };
    let ok = true;
    for (const key of keys) {
      const text = row[key];
      // 파이썬 float("") · float(None) 은 예외다
      if (text === undefined || text === null || String(text).trim() === '') {
        ok = false;
        break;
      }
      const value = Number(String(text).trim());
      if (Number.isNaN(value)) {
        ok = false;
        break;
      }
      copy[key] = value;
    }
    if (ok) out.push(copy);
  }
  return out;
}

const FACILITIES = floatify(FACILITIES_RAW as Raw[], ['위도', '경도']);
const RESERVATIONS = RESERVATIONS_RAW as Raw[];
const SUBWAY = floatify(SUBWAY_RAW as Raw[], ['위도', '경도']);
const BUS = floatify(BUS_RAW as Raw[], ['위도', '경도']);
const PARKING = floatify(PARKING_RAW as Raw[], ['위도', '경도']);

export interface JoinSpec {
  세부유형: Set<string>;
  업종: Set<string>;
  예약: Set<string>;
  대체처리: string;
  확인필요: boolean;
}

const splitSet = (text: string | undefined): Set<string> =>
  new Set((text ?? '').split('|').filter(Boolean));

/** `csv.DictReader` 는 헤더에 있는 열을 늘 채워 준다. 타입만 좁혀 준다. */
const col = (row: Raw, key: string): string => row[key] ?? '';

export const JOIN = new Map<string, JoinSpec>(
  (JOIN_RAW as Raw[]).map((row): [string, JoinSpec] => [
    col(row, '종목'),
    {
      세부유형: splitSet(row['시설_세부유형']),
      업종: splitSet(row['시설_업종']),
      예약: splitSet(row['예약_세부종목']),
      대체처리: col(row, '대체처리'),
      확인필요: row['확인필요'] === 'Y',
    },
  ]),
);

export function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371000.0;
  const rad = Math.PI / 180;
  const p1 = lat1 * rad;
  const p2 = lat2 * rad;
  const dp = (lat2 - lat1) * rad;
  const dl = (lon2 - lon1) * rad;
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

export interface FindOptions {
  lat?: number | null;
  lon?: number | null;
  district?: string | null;
  radiusM?: number;
  limit?: number;
}

export function findFacilities(sport: string, options: FindOptions = {}): Json {
  const { lat = null, lon = null, district = null, radiusM = DEFAULT_RADIUS_M, limit = 5 } = options;

  const spec = JOIN.get(sport);
  if (!spec) return emptyResult(sport, '', '매핑에 없는 종목');
  if (district === null || district === undefined) {
    // 지원 지역 밖에서 굳이 먼 시설을 끌어오지 않는다.
    // "두 곳에서만 주변 정보를 제공한다"는 약속과 어긋난다
    return emptyResult(sport, spec.대체처리, '지원 지역 밖');
  }

  const reservations = reservationsOf(spec, district, lat, lon);
  const [nearby, expanded] = nearbyOf(spec, district, lat, lon, radiusM, limit);

  if (reservations.length === 0 && nearby.length === 0) {
    return emptyResult(sport, spec.대체처리, '주변에 등록된 시설이 없음', accessOf(lat, lon));
  }

  const anchor = nearby.length > 0 ? nearby[0] : null;
  const accessLat = anchor ? anchor['위도'] : lat;
  const accessLon = anchor ? anchor['경도'] : lon;

  return {
    종목: sport,
    예약: reservations,
    주변: nearby,
    접근성: accessOf(accessLat, accessLon),
    확장: expanded,
    매칭없음: false,
    // 시설이 있어도 함께 안내한다 — 걷기는 간이운동장이 잡혀도 '시설이 필요 없는 운동'이다
    대체처리: spec.대체처리,
    확인필요: spec.확인필요,
  };
}

function emptyResult(sport: string, fallback: string, reason: string, access?: Json): Json {
  return {
    종목: sport,
    예약: [],
    주변: [],
    접근성: access && Object.keys(access).length > 0 ? access : {},
    확장: false,
    매칭없음: true,
    대체처리: fallback,
    사유: reason,
    확인필요: Boolean(JOIN.get(sport)?.확인필요),
  };
}

function reservationsOf(
  spec: JoinSpec,
  district: string | null,
  lat: number | null,
  lon: number | null,
): Json[] {
  if (spec.예약.size === 0) return [];
  const out: Json[] = [];

  for (const row of RESERVATIONS) {
    if (!spec.예약.has(col(row, '세부종목'))) continue;
    if (district && row['자치구'] !== district) continue;
    if (row['접수상태'] !== '접수중') continue; // 마감·종료된 것을 보여줄 이유가 없다

    const item: Json = {
      장소명: row['장소명'],
      서비스명: row['서비스명'],
      세부종목: row['세부종목'],
      유무료: row['유무료'],
      예약URL: row['예약URL'],
      자치구: row['자치구'],
      위도: null,
      경도: null,
      거리m: null,
    };
    // 좌표 결측 49% — 없는 것은 핀 없이 목록에만 (PRD §9-3)
    if (row['위도']) {
      const la = Number(row['위도']);
      const lo = Number(row['경도']);
      if (!Number.isNaN(la) && !Number.isNaN(lo)) {
        item['위도'] = la;
        item['경도'] = lo;
      }
    }
    if (lat !== null && lat !== undefined && item['위도'] !== null) {
      item['거리m'] = pyRound(haversineM(lat, lon as number, item['위도'], item['경도']));
    }
    out.push(item);
  }

  // 파이썬 key=(거리m is None, 거리m or 0) — False(0) 가 True(1) 보다 앞
  out.sort((a, b) => {
    const an = a['거리m'] === null ? 1 : 0;
    const bn = b['거리m'] === null ? 1 : 0;
    if (an !== bn) return an - bn;
    return (a['거리m'] ?? 0) - (b['거리m'] ?? 0);
  });
  return dedupeByPlace(out);
}

/** 같은 장소의 코트·시간대가 여러 건으로 들어온다(장충테니스장 등).
 *  장소 단위로 접어 보여주고 예약 가능 건수만 알린다. */
function dedupeByPlace(rows: Json[]): Json[] {
  const merged = new Map<string, Json>();
  for (const row of rows) {
    const key = row['장소명'];
    const found = merged.get(key);
    if (found) {
      found['예약건수'] += 1;
      continue;
    }
    merged.set(key, { ...row, 예약건수: 1 });
  }
  return Array.from(merged.values());
}

function matches(row: Geo, spec: JoinSpec): boolean {
  return spec.세부유형.has(row['세부유형']) || spec.업종.has(row['업종']);
}

function nearbyOf(
  spec: JoinSpec,
  district: string | null,
  lat: number | null,
  lon: number | null,
  radiusM: number,
  limit: number,
): [Json[], boolean] {
  let pool = FACILITIES.filter((r) => matches(r, spec));
  if (district) pool = pool.filter((r) => r['자치구'] === district);
  if (pool.length === 0) return [[], false];

  if (lat === null || lat === undefined || lon === null || lon === undefined) {
    return [pool.slice(0, limit).map((r) => itemOf(r, null)), false];
  }

  // 파이썬 sorted(key=거리) — 안정 정렬이라 같은 거리면 원래 순서를 지킨다
  const scored = pool
    .map((r) => ({ d: haversineM(lat, lon, r['위도'], r['경도']), r }))
    .sort((a, b) => a.d - b.d);

  let within = scored.filter((t) => t.d <= radiusM);
  let expanded = false;
  if (within.length < MIN_RESULTS) {
    within = scored; // 자치구 전체로 확장
    expanded = true;
  }
  return [within.slice(0, limit).map(({ r, d }) => itemOf(r, d)), expanded];
}

function itemOf(row: Geo, distance: number | null): Json {
  return {
    시설명: row['시설명'],
    업종: row['업종'],
    세부유형: row['세부유형'],
    자치구: row['자치구'],
    주소: row['주소'],
    전화번호: row['전화번호'],
    위도: row['위도'],
    경도: row['경도'],
    거리m: distance === null ? null : pyRound(distance),
    지도: mapLink(row),
  };
}

/** 지도 타일을 그리지 않는다. 외부 지도 앱으로 넘긴다. */
function mapLink(row: Geo): string {
  return `https://map.naver.com/p/search/${row['시설명']}`;
}

/** 가는 방법 — 가장 가까운 역·정류장·주차장. */
function accessOf(lat: number | null, lon: number | null): Json {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return {};
  const out: Json = {};
  const sources: Array<[string, Geo[]]> = [
    ['지하철', SUBWAY],
    ['버스', BUS],
    ['주차장', PARKING],
  ];

  for (const [key, rows] of sources) {
    if (rows.length === 0) continue;
    // 파이썬 min() 은 동점이면 먼저 나온 것을 고른다
    let best = rows[0]!;
    let bestDistance = haversineM(lat, lon, best['위도'], best['경도']);
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i]!;
      const d = haversineM(lat, lon, row['위도'], row['경도']);
      if (d < bestDistance) {
        best = row;
        bestDistance = d;
      }
    }
    const entry: Json = { 이름: best['이름'], 거리m: pyRound(bestDistance) };
    if (key === '지하철') entry['노선'] = best['노선'] ?? null;
    if (key === '주차장') {
      entry['장애인구역'] = best['장애인주차구역'] === 'Y';
      entry['요금'] = best['요금정보'] ?? null;
    }
    out[key] = entry;
  }
  return out;
}

/** '시설불필요' · '집' · ''. 시설을 쓰지 않는 종목인지 화면이 미리 알아야 한다. */
export function fallbackOf(sport: string): string {
  return JOIN.get(sport)?.대체처리 ?? '';
}

/** 가는 방법 — 시설 한 곳 기준. 지도의 시설 상세 카드(M4)가 쓴다. */
export function access(lat: number | null, lon: number | null): Json {
  return accessOf(lat, lon);
}
