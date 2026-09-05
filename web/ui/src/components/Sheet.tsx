/* 바텀시트 껍데기 — 종목 상세 · 시설 상세 · 기록 입력이 함께 쓴다.
 * 바닐라의 `BD.sheet` 에 해당하지만, 여닫는 상태는 부르는 쪽이 들고 있다.
 */
import { useEffect, type ReactNode } from 'react';
import styles from './Sheet.module.css';

interface Props {
  children: ReactNode;
  onClose(): void;
  label?: string;
}

export default function Sheet({ children, onClose, label }: Props) {
  /* Esc 로 닫기. 바닐라에는 없던 동작이지만 모달의 기본이다. */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className={styles.sheet}>
      <div className={styles.backdrop} onClick={onClose} />
      <div className={styles.body} role="dialog" aria-modal="true" aria-label={label}>
        {children}
        <button className="ghost" type="button" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
