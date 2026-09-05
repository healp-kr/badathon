/* 스플래시 — 브랜드 그린 전면에 중앙 워드마크.
 *
 * 스피너를 넣지 않는다. 부트는 설문 문항·지역·종목 마스터를 한 번 받는 정도라
 * 짧게 지나가는데, 스피너를 두면 그 짧은 순간이 오히려 "기다림"으로 읽힌다.
 */
import styles from './Splash.module.css';

export default function Splash() {
  return (
    <div className={styles.splash}>
      <span className={styles.mark}>
        <span className={styles.dot}>S</span>
        Sportstify
      </span>
    </div>
  );
}
