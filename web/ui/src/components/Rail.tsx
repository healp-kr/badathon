/* 가로 캐러셀 — 타일들을 담는 껍데기.
 *
 * 화면 가장자리까지 흐르도록 음수 마진을 쓴다(잘린 타일이 보여야 더 있다는 신호가 된다).
 * 다만 잘림만으로 스크롤을 알리지는 않는다 — 아래 인디케이터를 반드시 함께 둔다.
 * 활성은 긴 바, 비활성은 점이며, 레퍼런스보다 크게(6px) 잡았다.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import styles from './Rail.module.css';

export default function Rail({ children }: { children: ReactNode }) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [index, setIndex] = useState(0);
  const [pages, setPages] = useState(0);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    function measure() {
      if (!track) return;
      const child = track.firstElementChild as HTMLElement | null;
      const step = child ? child.offsetWidth + 12 : 0; // 타일 폭 + gap
      if (!step) {
        setPages(0);
        return;
      }
      setPages(Math.max(0, Math.ceil((track.scrollWidth - track.clientWidth) / step) + 1));
      setIndex(Math.round(track.scrollLeft / step));
    }

    measure();
    track.addEventListener('scroll', measure, { passive: true });
    window.addEventListener('resize', measure);
    return () => {
      track.removeEventListener('scroll', measure);
      window.removeEventListener('resize', measure);
    };
  }, [children]);

  return (
    <>
      <div className={styles.rail} ref={trackRef}>
        {children}
      </div>
      {pages > 1 && (
        <div className={styles.dots} aria-hidden="true">
          {Array.from({ length: pages }, (_, i) => (
            <span key={i} className={i === index ? styles.active : styles.dot} />
          ))}
        </div>
      )}
    </>
  );
}
