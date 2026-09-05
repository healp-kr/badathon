/* 지역 선택 바텀시트 — 바닐라의 `openSheet()`.
 *
 * 각 지역의 오늘 조건을 함께 띄운다. 지역이 결과를 바꾼다는 걸 고르는 순간에
 * 보여주기 위한 것이므로, 조회가 실패하면 그 줄만 조용히 비운다.
 *
 * 고르고 나면: 이미 결과가 있으면 그 지역으로 다시 돌리고, 없으면 설문으로 간다.
 */
import { useEffect, useState } from 'react';
import { fetchContext } from '../api/endpoints';
import { optional } from '../api/client';
import { askLocation, locateMessage } from '../lib/geolocate';
import { useApp } from '../state/AppContext';
import styles from './DistrictSheet.module.css';

export default function DistrictSheet({ onClose }: { onClose(): void }) {
  const { districts, result, setDistrict, clearDistrict, openSurvey, submit } = useApp();
  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [locateNote, setLocateNote] = useState('위치 권한이 필요해요');
  const [locating, setLocating] = useState(false);

  /* 지역별 오늘 조건. 실패는 조용히 넘긴다 — 없으면 안 보이면 그만이다. */
  useEffect(() => {
    let alive = true;
    districts.forEach(async (d) => {
      const ctx = await optional(fetchContext(d.district));
      if (!alive || !ctx?.요약) return;
      setSummaries((prev) => ({
        ...prev,
        [d.district]: ctx.요약.replace(`${d.district} · `, ''),
      }));
    });
    return () => {
      alive = false;
    };
  }, [districts]);

  /* 지역이 정해진 뒤의 다음 걸음은 하나뿐이다 — 결과가 있으면 갱신, 없으면 설문. */
  function proceed() {
    onClose();
    if (result) void submit();
    else openSurvey();
  }

  function pick(district: string) {
    setDistrict(district, 'manual');
    proceed();
  }

  async function useCurrentLocation() {
    setLocating(true);
    const outcome = await askLocation();
    setLocating(false);

    if (!outcome.ok) {
      setLocateNote(locateMessage(outcome));
      return;
    }
    // 자동 판정은 저장된 수동 선택을 덮어쓴다
    clearDistrict();
    setDistrict(outcome.district, 'auto');
    proceed();
  }

  return (
    <div className={styles.sheet}>
      <div className={styles.backdrop} onClick={onClose} />
      <div className={styles.body} role="dialog" aria-modal="true" aria-labelledby="sheetTitle">
        <h2 id="sheetTitle">어디에서 운동하시나요?</h2>
        <p className="muted">지금은 중구·관악구에서만 주변 정보를 제공해요</p>

        <button
          className={`opt ${styles.locate}`}
          type="button"
          onClick={useCurrentLocation}
          disabled={locating}
        >
          <span className="opt-title">현재 위치로</span>
          <span className="opt-sub">{locating ? '위치를 확인하고 있어요…' : locateNote}</span>
        </button>

        {districts.map((d) => (
          <button className="opt" type="button" key={d.district} onClick={() => pick(d.district)}>
            <span className="opt-title">{d.district}</span>
            <span className="opt-sub">{summaries[d.district] ?? '조건 확인 중…'}</span>
          </button>
        ))}

        <button className="ghost" type="button" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
