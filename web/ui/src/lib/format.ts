/* 표시 형식 — 바닐라 버전의 `BD.plain` · `BD.distance` 를 옮겼다.
 *
 * `BD.esc` 는 여기 없다. React 가 기본으로 이스케이프하기 때문이다.
 * 시설명·주소는 CSV 원본이라 & " ' < 가 그대로 들어 있어서, 바닐라에서는
 * innerHTML 에 넣기 전에 매번 `BD.esc` 를 통과시켜야 했다. 한 번만 빠뜨려도
 * 화면이 깨지는 구조였는데, 이 위험은 마이그레이션으로 사라진다.
 */

/** 추천 이유에 붙는 수치 괄호를 화면에서 뗀다 — "(평균 대비 2.0배)", "(선호도 11%)".
 *
 *  §11: 점수·확률 숫자는 노출하지 않고 배지와 순서로만 말한다. 근거 수치의 설명은
 *  보고서가 맡는다.
 *
 *  **숫자가 든 괄호만** 지우므로 "강도(중)" · "걷기(속보 포함)" 는 남는다.
 *  처방의 "주 150분" 같은 지침 수치에는 적용하지 않는다 — 사용자가 알아야 할 값이다. */
export function plain(text: string | null | undefined): string {
  return String(text ?? '')
    .replace(/\s*[(（][^()（）]*\d[^()（）]*[)）]/g, '')
    .trim();
}

/** 커버 타일에 넣을 짧은 이름 — 괄호와 쉼표 뒤를 자른다.
 *  "수영+아쿠아로빅, 수중발레+수구" → "수영+아쿠아로빅"
 *  "걷기(속보 포함)" → "걷기" */
export function shortName(sport: string | null | undefined): string {
  const text = String(sport ?? '');
  return text.replace(/\s*[(（].*$/, '').replace(/,.*$/, '').trim() || text;
}

/** 1km 미만은 m, 이상은 소수 한 자리 km */
export function distance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return '';
  return meters < 1000 ? `${meters}m` : `${(meters / 1000).toFixed(1)}km`;
}

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'] as const;

export function weekdayOf(date: Date): string {
  return WEEKDAY[date.getDay()] ?? '';
}

/** "9월 4일 목요일" */
export function todayLabel(date: Date = new Date()): string {
  return `${date.getMonth() + 1}월 ${date.getDate()}일 ${weekdayOf(date)}요일`;
}

/** 배열을 사람이 읽는 목록으로. 빈 배열이면 빈 문자열. */
export function joinKo(items: readonly string[], sep = ' · '): string {
  return items.filter(Boolean).join(sep);
}
