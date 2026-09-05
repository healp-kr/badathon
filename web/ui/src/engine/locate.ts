/* 좌표 → 자치구 판정 — `api/locate.py` 의 포팅.
 *
 * 경계 폴리곤(WGS84)에 대한 point-in-polygon 만으로 판정한다. 외부 API 도 라이브러리도
 * 쓰지 않으므로 시연 중 네트워크 장애의 영향을 받지 않는다 — 정적화하면서 이 성질이
 * 더 중요해졌다. 이제 이 판정이 **브라우저 안에서** 끝난다.
 *
 * **경계 밖이면 '지원 밖'이다. 최근접 보정을 하지 않는다.**
 * 전국에 '중구'는 여럿이므로, 부산에서 접속했는데 "중구입니다"가 뜨면 안 된다.
 *
 * GeoJSON 좌표는 (경도, 위도) 순이다. 공개 함수는 전부 (lat, lon) 을 받고
 * 내부에서만 뒤집는다 — 순서 혼동은 이 프로젝트에서 반복적으로 나오는 함정이다.
 */
import CONF from './data/districts.json' with { type: 'json' };
import BOUNDARY from './data/boundary.json' with { type: 'json' };

type Json = any;

export interface District {
  district: string;
  sigungu_nm: string;
  center: [number, number];
  nx: number;
  ny: number;
  areaNo: string;
  cai_station: string;
}

const conf = CONF as Json;
export const DISTRICTS = new Map<string, District>(
  (conf.districts as District[]).map((d) => [d.district, d]),
);
const KEY = conf.boundary_key as string;

/** Polygon / MultiPolygon 을 외곽 링 목록으로 편다. */
function ringsOf(geometry: Json): number[][][] {
  const kind = geometry.type;
  const coords = geometry.coordinates;
  if (kind === 'Polygon') return [coords[0]];
  if (kind === 'MultiPolygon') return coords.map((poly: Json) => poly[0]);
  return [];
}

const POLYGONS = (() => {
  const out = new Map<string, number[][][]>();
  for (const feature of (BOUNDARY as Json).features as Json[]) {
    const name = feature.properties?.[KEY];
    if (!name) continue;
    if (!out.has(name)) out.set(name, []);
    out.get(name)!.push(...ringsOf(feature.geometry));
  }
  return out;
})();

/** Ray casting. ring 은 [[경도, 위도], ...]. */
function inRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  const n = ring.length;
  let j = n - 1;
  for (let i = 0; i < n; i++) {
    const p = ring[i]!;
    const q = ring[j]!;
    const xi = p[0]!;
    const yi = p[1]!;
    const xj = q[0]!;
    const yj = q[1]!;
    if (yi > lat !== yj > lat) {
      const xCross = ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (lon < xCross) inside = !inside;
    }
    j = i;
  }
  return inside;
}

/** 파이썬 `float(x)` 와 같은 성질. 변환할 수 없으면 null 을 돌려준다.
 *
 * JS `Number(null)` 은 0 이고 `Number("")` 도 0 이다 — 파이썬 `float()` 은 둘 다
 * 예외다. 그대로 두면 좌표를 안 준 사용자가 적도(0, 0)로 판정된다.
 */
function toFloat(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const text = value.trim();
    if (text === '') return null;
    const parsed = Number(text);
    return Number.isNaN(parsed) && !/^[+-]?nan$/i.test(text) ? null : parsed;
  }
  return null;
}

export interface LocateResult {
  district: string | null;
  사유: string;
  source: string;
}

/** 위도·경도 → 지원 자치구. */
export function resolveDistrict(lat: unknown, lon: unknown): LocateResult {
  const latitude = toFloat(lat);
  const longitude = toFloat(lon);
  if (latitude === null || longitude === null) {
    return { district: null, 사유: '좌표 형식 오류', source: 'auto' };
  }

  for (const [name, rings] of POLYGONS) {
    if (!DISTRICTS.has(name)) continue; // 경계 파일에는 있으나 서비스 대상이 아닌 구
    if (rings.some((ring) => inRing(longitude, latitude, ring))) {
      return { district: name, 사유: '경계 내부', source: 'auto' };
    }
  }
  return { district: null, 사유: '지원 지역 밖', source: 'auto' };
}

/** 지역 선택 시트가 쓸 목록. */
export function listDistricts(): Array<{ district: string; center: [number, number] }> {
  return (conf.districts as District[]).map((d) => ({ district: d.district, center: d.center }));
}

/** 지도 배경으로 그릴 경계 GeoJSON (FeatureCollection).
 *
 * 타일이 안 떠도 이 폴리곤은 그려진다 — Leaflet 을 고른 이유가 이것이다(PRD §9-2).
 */
export function boundaryFeatures(district?: string | null): Json {
  const features: Json[] = [];
  for (const feature of (BOUNDARY as Json).features as Json[]) {
    const name = feature.properties?.[KEY];
    if (!DISTRICTS.has(name)) continue; // 서비스 대상이 아닌 구는 내보내지 않는다
    if (district && name !== district) continue;
    features.push({
      type: 'Feature',
      properties: { district: name, center: DISTRICTS.get(name)!.center },
      geometry: feature.geometry,
    });
  }
  return { type: 'FeatureCollection', features };
}

/** 위치를 못 받았을 때 쓰는 대체 중심점 (lat, lon). */
export function districtCenter(district: string | null | undefined): [number, number] | null {
  if (!district) return null;
  const entry = DISTRICTS.get(district);
  return entry ? (entry.center.slice() as [number, number]) : null;
}

export function isSupported(district: string | null | undefined): boolean {
  return !!district && DISTRICTS.has(district);
}
