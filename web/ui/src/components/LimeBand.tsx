/* 홈 상단 밴드 — 라임 바탕에 하단 웨이브.
 * 새 이미지 파일을 만들지 않기 위해 곡선은 인라인 SVG 로 그린다.
 */
import type { ReactNode } from 'react';
import styles from './LimeBand.module.css';

export default function LimeBand({ children }: { children: ReactNode }) {
  return (
    <div className={`${styles.band} bleed`}>
      <div className={styles.inner}>{children}</div>
      <svg
        className={styles.wave}
        viewBox="0 0 560 26"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path d="M0 26 V14 C120 30 240 0 380 8 C460 12 520 20 560 14 V26 Z" fill="#fff" />
      </svg>
    </div>
  );
}
