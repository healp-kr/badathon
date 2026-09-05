/* 종목 타일 — 캐러셀 한 칸. 바닐라의 `tile()` 을 옮겼다.
 *
 * 커버는 사진이 아니라 종목명에서 뽑은 그라데이션이다(`coverOf`).
 * 캡션에는 강도와 실내외만 넣는다 — 점수·확률은 화면에 노출하지 않는다(§11).
 *
 * 바닐라에서는 타일을 그릴 때 `state.items[bucket::종목] = item` 으로 전역에 등록해두고
 * 상세 화면이 그 키로 되짚었다. 여기서는 아이템을 그대로 넘기므로 그 사전이 필요 없다.
 */
import { coverOf } from '../lib/cover';
import { shortName } from '../lib/format';
import type { 갈래, 추천종목 } from '../api/types';
import styles from './SportTile.module.css';

interface Props {
  item: 추천종목;
  bucket: 갈래;
  onSelect(bucket: 갈래, item: 추천종목): void;
}

export default function SportTile({ item, bucket, onSelect }: Props) {
  const badge = item.강도 && item.강도 !== '미확인' ? `강도 ${item.강도}` : '';
  const caption = [badge, item.실내외].filter(Boolean).join(' · ');

  return (
    <button
      className={styles.tile}
      type="button"
      data-rank={item.display_rank ?? 0}
      onClick={() => onSelect(bucket, item)}
    >
      <span className={styles.cover} style={{ background: coverOf(item.종목) }}>
        {shortName(item.종목)}
      </span>
      <span className={styles.cap}>
        {item.환경배지 ? '오늘 추천 · ' : ''}
        {caption}
      </span>
    </button>
  );
}
