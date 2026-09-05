/* 지도(S4)가 그릴 것 — `geo/mapdata.py` 의 포팅.
 *
 * `findFacilities` 가 "어디에 있는지"를 답한다면, 이 모듈은 그것을
 * **지도가 바로 그릴 수 있는 형태**로 옮긴다. 새로 찾지 않는다.
 *
 * 지도이므로 목록 화면과 다른 점이 셋 있다.
 *   1. 개수가 많다 (거리순 상위 20). 목록은 5건이면 충분하지만 핀은 성기면 허전하다
 *   2. 예약 시설도 핀이 된다 — 단 좌표가 49% 결측이라 **없는 것은 목록에만** 남긴다
 *   3. 시설마다 '가는 방법'을 미리 붙인다. 핀을 누를 때마다 왕복하지 않으려는 것이다
 */
import { JOIN, access, findFacilities } from './facility.ts';

type Json = any;

export const MAP_LIMIT = 20;

export interface PinOptions {
  district?: string | null;
  lat?: number | null;
  lon?: number | null;
  limit?: number;
  reservableOnly?: boolean;
}

/** 종목 하나의 지도 데이터.
 *
 * 반환 키: 종목 · 핀 · 좌표없는예약 · 확장 · 매칭없음 · 대체처리 · 확인필요 · 매핑없음
 */
export function pins(sport: string, options: PinOptions = {}): Json {
  const {
    district = null,
    lat = null,
    lon = null,
    limit = MAP_LIMIT,
    reservableOnly = false,
  } = options;

  const found = findFacilities(sport, { lat, lon, district, limit });

  const marks: Json[] = [];
  for (const item of found['예약']) marks.push(pinOf(item, true));
  if (!reservableOnly) {
    for (const item of found['주변']) marks.push(pinOf(item, false));
  }

  const located = marks.filter((m) => m['위도'] !== null);
  const unlocated = marks.filter((m) => m['위도'] === null);

  // 예약 가능한 곳이 위로. 전환 지점이기 때문이다(PRD §2 — 예약 링크가 전환 지점)
  located.sort((a, b) => {
    const ar = a['예약'] ? 0 : 1;
    const br = b['예약'] ? 0 : 1;
    if (ar !== br) return ar - br;
    const an = a['거리m'] === null ? 1 : 0;
    const bn = b['거리m'] === null ? 1 : 0;
    if (an !== bn) return an - bn;
    return (a['거리m'] ?? 0) - (b['거리m'] ?? 0);
  });

  for (const mark of located) {
    if (mark['위도'] !== null) mark['접근성'] = access(mark['위도'], mark['경도']);
  }

  return {
    종목: sport,
    핀: located.slice(0, limit),
    좌표없는예약: unlocated,
    확장: found['확장'],
    매칭없음: found['매칭없음'] && located.length === 0 && unlocated.length === 0,
    대체처리: found['대체처리'] || '',
    사유: found['사유'] ?? null,
    확인필요: found['확인필요'] ?? false,
    매핑없음: !JOIN.has(sport),
  };
}

/** 예약 행과 시설 행은 컬럼이 다르다. 지도는 한 가지 모양만 안다. */
function pinOf(item: Json, 예약: boolean): Json {
  if (예약) {
    return {
      시설명: item['장소명'],
      예약: true,
      업종: item['서비스명'],
      세부유형: item['세부종목'],
      자치구: item['자치구'],
      주소: null,
      전화번호: null,
      위도: item['위도'],
      경도: item['경도'],
      거리m: item['거리m'],
      예약URL: item['예약URL'],
      유무료: item['유무료'],
      예약건수: item['예약건수'] ?? 1,
      지도: `https://map.naver.com/p/search/${item['장소명']}`,
    };
  }
  return {
    시설명: item['시설명'],
    예약: false,
    업종: item['업종'],
    세부유형: item['세부유형'],
    자치구: item['자치구'],
    주소: item['주소'],
    전화번호: item['전화번호'],
    위도: item['위도'],
    경도: item['경도'],
    거리m: item['거리m'],
    예약URL: null,
    유무료: null,
    예약건수: 0,
    지도: item['지도'],
  };
}
