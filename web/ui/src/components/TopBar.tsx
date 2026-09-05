/* 앱바 — 브랜드와 현재 지역. */
import { useApp } from '../state/AppContext';
import styles from './TopBar.module.css';

export default function TopBar({ onPickDistrict }: { onPickDistrict(): void }) {
  const { district } = useApp();

  return (
    <header className={styles.topbar}>
      <div className={styles.bar}>
        <span className={styles.brand}>
          <span className={styles.dot}>S</span>Sportstify
        </span>
        <button className={styles.chip} type="button" onClick={onPickDistrict}>
          {district ?? '지역 선택하기'}
        </button>
      </div>
    </header>
  );
}
