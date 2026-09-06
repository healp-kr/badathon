/* 종목 상세 행 — 결과 화면의 목록 한 줄.
 *
 * 레퍼런스의 "선택 행" 패턴을 따른다: 좌측 썸네일 · 제목 굵게 · 메타 회색 · 속성 칩 · 우측 셰브론.
 * 속성 칩은 두 종류다 — 연녹 채움은 권장·오늘(의미 있는 강조), 연회색 아웃라인은 강도·실내외(사실).
 * 강도·종목에 색을 배정하지 않는다.
 *
 * `강도주의` 는 권장 상한을 넘을 때만 붙는 안전 문구이므로 접거나 생략하지 말 것.
 */
import { coverOf } from '../lib/cover';
import { plain, shortName } from '../lib/format';
import type { 갈래, 추천종목 } from '../api/types';
import styles from './SportRow.module.css';

interface Props {
  item: 추천종목;
  bucket: 갈래;
  selected?: boolean;
  done?: boolean;
  onOpen(bucket: 갈래, item: 추천종목): void;
  onFind(sport: string): void;
  onDid(bucket: 갈래, item: 추천종목): void;
}

export default function SportRow({
  item,
  bucket,
  selected = false,
  done = false,
  onOpen,
  onFind,
  onDid,
}: Props) {
  const intensity =
    item.강도 && item.강도 !== '미확인'
      ? item.강도 === '고'
        ? '세게 하면 고강도'
        : `강도 ${item.강도}`
      : null;

  const meta = [item.맞춤이유?.map(plain).join(' · '), plain(item.이유), item.처방]
    .filter(Boolean)
    .join(' · ');

  return (
    <div
      className={`${styles.sport} ${selected ? styles.selected : ''}`}
      data-rank={item.display_rank ?? 0}
    >
      <button
        className={styles.head}
        type="button"
        onClick={() => onOpen(bucket, item)}
        aria-label={`${item.종목} 상세`}
      >
        <span className={styles.thumb} style={{ background: coverOf(item.종목) }}>
          {shortName(item.종목).slice(0, 1)}
        </span>

        <span className={styles.body}>
          <span className={styles.name}>{item.종목}</span>

          {meta && <span className={`${styles.meta} clamp2`}>{meta}</span>}

          <span className={styles.chips}>
            {done && <span className="badge">오늘 완료</span>}
            {item.환경배지 && <span className="badge env">오늘 {item.환경배지}</span>}
            {intensity && <span className="badge">{intensity}</span>}
            {item.실내외 && <span className="badge">{item.실내외}</span>}
          </span>
        </span>

        <svg
          className="chevron"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m9 6 6 6-6 6" />
        </svg>
      </button>

      {item.강도주의 && (
        <p className="note warn">
          <span className="badge warn">주의</span>
          {item.강도주의}
        </p>
      )}

      <div className={styles.actions}>
        <button className={`opt ${styles.act} ${styles.go}`} type="button" onClick={() => onFind(item.종목)}>
          주변에서 찾기
        </button>
        <button className={`opt ${styles.act}`} type="button" onClick={() => onDid(bucket, item)}>
          했어요
        </button>
      </div>
    </div>
  );
}
