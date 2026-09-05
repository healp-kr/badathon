/* 종목 커버 — 바닐라 버전의 `BD.cover`.
 *
 * 종목 이미지가 없다. Spotify 플레이리스트 커버처럼 **그라데이션 타일**로 대신한다.
 * 종목명에서 결정적으로 색을 뽑으므로 같은 종목은 화면이 바뀌어도 같은 색이다.
 * 사진을 구해 붙이는 것보다 정직하고(출처 문제가 없다) 훨씬 싸다.
 *
 * 팔레트를 바꾸려면 COVERS 만 고치면 된다. 개수가 바뀌어도 동작한다.
 */

const COVERS = [
  'linear-gradient(135deg,#12b04f,#0f9d84)',
  'linear-gradient(135deg,#0b7ea8,#1462c9)',
  'linear-gradient(135deg,#6c4bd8,#a03fd0)',
  'linear-gradient(135deg,#e0603a,#d43f6a)',
  'linear-gradient(135deg,#d9962a,#c56a1f)',
  'linear-gradient(135deg,#1a9a8f,#2b7fd4)',
  'linear-gradient(135deg,#3f7a5a,#2f6f8f)',
  'linear-gradient(135deg,#2f9e44,#7cb305)',
] as const;

/** 종목명 → CSS 그라데이션. 같은 이름이면 항상 같은 값을 돌려준다. */
export function coverOf(sport: string | null | undefined): string {
  let hash = 0;
  for (const ch of String(sport ?? '')) {
    hash = (hash + (ch.codePointAt(0) ?? 0)) % 997;
  }
  return COVERS[hash % COVERS.length] ?? COVERS[0];
}
