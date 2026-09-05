/* 주간 달성률 도넛 — 바닐라 `BD.ring` 을 옮겼다.
 *
 * 값은 stroke-dasharray/offset 으로 그린다. 라이브러리를 쓰지 않는 이유는
 * 이 하나를 위해 차트 의존성을 들이는 것이 과하기 때문이다.
 */
import styles from './Ring.module.css';

interface Props {
  /** 0~100. 범위를 벗어나면 잘라낸다. */
  percent: number;
  /** 가운데 큰 숫자 */
  main: string | number;
  /** 숫자 뒤 단위 — "분" */
  unit?: string;
  /** 링 아래 설명 — "지침 권장 150분 기준" */
  caption?: string;
}

const R = 52;
const CIRCUMFERENCE = 2 * Math.PI * R;

export default function Ring({ percent, main, unit, caption }: Props) {
  const filled = Math.max(0, Math.min(100, percent)) / 100;
  const offset = CIRCUMFERENCE * (1 - filled);

  return (
    <>
      <div className={styles.wrap}>
        <svg className={styles.ring} viewBox="0 0 120 120" aria-hidden="true">
          <circle className={styles.track} cx="60" cy="60" r={R} />
          <circle
            className={styles.bar}
            cx="60"
            cy="60"
            r={R}
            strokeDasharray={CIRCUMFERENCE.toFixed(1)}
            strokeDashoffset={offset.toFixed(1)}
            transform="rotate(-90 60 60)"
          />
        </svg>
        <div className={styles.text}>
          <b>{main}</b>
          {unit && <span>{unit}</span>}
        </div>
      </div>
      {caption && <p className={`note ${styles.caption}`}>{caption}</p>}
    </>
  );
}
