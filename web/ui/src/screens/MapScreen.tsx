/* S4 지도 — 추천 종목의 주변 시설.
 *
 * 지도는 추천의 연장이지 검색창이 아니다. 그래서 종목 목록은 추천 결과 안에서만 나온다.
 */
import { useEffect, useMemo, useState } from 'react';
import { fetchBoundary, fetchMapFacilities } from '../api/endpoints';
import { optional } from '../api/client';
import { useLeafletMap } from '../features/map/useLeafletMap';
import { distance } from '../lib/format';
import { useApp } from '../state/AppContext';
import Locked from './Locked';
import Sheet from '../components/Sheet';
import DistrictSheet from '../components/DistrictSheet';
import type { MapFacilitiesResponse, 지도핀 } from '../api/types';
import styles from './MapScreen.module.css';

export default function MapScreen() {
  const { result, sports, district, districts, coords } = useApp();

  /* 추천 밖 종목은 넣지 않는다. */
  const recommended = useMemo(() => {
    if (!result) return [];
    const out: string[] = [];
    for (const bucket of ['익숙한운동', '새로운운동'] as const) {
      for (const item of result[bucket] ?? []) {
        if (!out.includes(item.종목)) out.push(item.종목);
      }
    }
    return out;
  }, [result]);

  /* 시설을 쓰지 않는 종목(`대체처리`)이 첫 칸에 오면 지도의 첫인상이
   * "매칭 없음" 안내문이 된다. 그래서 시설이 있는 종목을 기본값으로 고른다. */
  const initialSport = useMemo(() => {
    const usesFacility = (sport: string) => {
      const found = sports.find((s) => s.종목 === sport);
      return !found || !found.대체처리;
    };
    return recommended.find(usesFacility) ?? recommended[0] ?? null;
  }, [recommended, sports]);

  const [sport, setSport] = useState<string | null>(initialSport);
  const [data, setData] = useState<MapFacilitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<지도핀 | null>(null);
  const [districtOpen, setDistrictOpen] = useState(false);

  const center = useMemo<[number, number]>(() => {
    const found = districts.find((d) => d.district === district);
    return found?.center ?? [37.5636, 126.9976];
  }, [districts, district]);

  const { containerRef, drawBoundary, drawPins, tileFailed } = useLeafletMap({
    center,
    coords,
  });

  /* 경계는 한 번만 그린다 */
  useEffect(() => {
    if (!district) return;
    let alive = true;
    optional(fetchBoundary(district)).then((geo) => {
      if (alive && geo) drawBoundary(geo);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [district]);

  /* 종목이 바뀌면 핀과 목록을 다시 받는다 */
  useEffect(() => {
    if (!sport) return;
    let alive = true;
    setLoading(true);

    fetchMapFacilities(sport, {
      district,
      ...(coords ? { lat: coords.lat, lon: coords.lon } : {}),
    })
      .then((res) => {
        if (!alive) return;
        setData(res);
        drawPins(res.핀, (index) => setPicked(res.핀[index] ?? null));
      })
      .catch(() => {
        if (alive) setData(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sport, district, coords]);

  if (!result) return <Locked where="지도" />;

  return (
    <>
      {/* 지도는 화면 끝까지 채우고, 종목 칩은 그 위에 띄운다 */}
      <div className={styles.stage}>
        <div ref={containerRef} className={styles.canvas} />

        {recommended.length > 0 && (
          <div className={styles.floatChips}>
            {recommended.map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={sport === s}
                onClick={() => setSport(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {tileFailed && (
          <p className={`${styles.tileNote} note warn`}>
            지도 배경을 불러오지 못했어요. 위치와 시설은 그대로 보입니다
          </p>
        )}
      </div>

      <div className={styles.sheet}>
        <div className={styles.handle} aria-hidden="true" />
        <h1>주변에서 찾기</h1>

        {loading ? (
          <p className="loading">주변을 찾는 중…</p>
        ) : !data ? (
          <div className="card info">
            <p>주변 정보를 불러오지 못했어요.</p>
            <p className="note">
              잠시 뒤 다시 시도해 주세요. 추천과 기록은 그대로 쓰실 수 있어요.
            </p>
          </div>
        ) : data.매칭없음 || data.매핑없음 ? (
          <div className="card info">
            <h3>이 종목은 주변 정보를 제공하지 않아요</h3>
            <p className="note">
              {data.사유 || data.대체처리 || '시설을 쓰지 않는 종목이에요'}
            </p>
          </div>
        ) : data.핀.length === 0 ? (
          <div className="card info">
            <p className="note">가까운 곳을 찾지 못했어요.</p>
          </div>
        ) : (
          <>
            {data.핀.slice(0, 10).map((pin, i) => (
              <button
                key={`${pin.시설명}-${i}`}
                className={styles.row}
                type="button"
                onClick={() => setPicked(pin)}
              >
                <span className={styles.rowIcon} aria-hidden="true">
                  <PinIcon />
                </span>
                <span className={styles.rowBody}>
                  <span className={styles.rowName}>{pin.시설명}</span>
                  <span className={`${styles.rowMeta} clamp2`}>
                    {pin.거리m != null && `${distance(pin.거리m)} · `}
                    {pin.세부유형 ?? pin.업종}
                  </span>
                </span>
                {pin.예약 && <span className="badge env">예약 가능</span>}
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
            ))}
          </>
        )}

        {data?.확인필요 && (
          <p className="note fine">
            시설 정보가 일부 누락되어 있어요. 방문 전에 확인해 주세요.
          </p>
        )}

        {/* 주 버튼 + 위성 버튼 — 시트 하단에 붙는다 */}
        {data && data.핀.length > 0 && (
          <div className={styles.sticky}>
            <button
              className={styles.satellite}
              type="button"
              aria-label="지역 선택"
              onClick={() => setDistrictOpen(true)}
            >
              <PinIcon />
            </button>
            <button
              className={`primary ${styles.cta}`}
              type="button"
              onClick={() => setPicked(data.핀[0] ?? null)}
            >
              가장 가까운 곳 보기
            </button>
          </div>
        )}
      </div>

      {picked && <FacilitySheet pin={picked} onClose={() => setPicked(null)} />}
      {districtOpen && <DistrictSheet onClose={() => setDistrictOpen(false)} />}
    </>
  );
}

/* 시설 행·위성 버튼이 쓰는 핀 아이콘. 새 이미지 파일을 만들지 않는다. */
function PinIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.6" />
    </svg>
  );
}

function FacilitySheet({ pin, onClose }: { pin: 지도핀; onClose(): void }) {
  const access = pin.접근성;

  return (
    <Sheet onClose={onClose} label={`${pin.시설명} 상세`}>
      <h2>{pin.시설명}</h2>
      <p className="note">
        {pin.세부유형 ?? pin.업종}
        {pin.거리m != null && ` · ${distance(pin.거리m)}`}
      </p>
      {pin.주소 && <p className="note">{pin.주소}</p>}

      {pin.전화번호 && (
        <p>
          <a className="opt" href={`tel:${pin.전화번호}`}>
            {pin.전화번호}
          </a>
        </p>
      )}

      {access && (
        <>
          <h3>가는 길</h3>
          {access.지하철 && (
            <p className="note">
              지하철 {access.지하철.이름}
              {access.지하철.노선 && ` (${access.지하철.노선})`} ·{' '}
              {distance(access.지하철.거리m)}
            </p>
          )}
          {access.버스 && (
            <p className="note">
              버스 {access.버스.이름} · {distance(access.버스.거리m)}
            </p>
          )}
          {access.주차장 && (
            <p className="note">
              주차 {access.주차장.이름} · {distance(access.주차장.거리m)}
              {access.주차장.요금 && ` · ${access.주차장.요금}`}
            </p>
          )}
        </>
      )}

      {/* 예약은 외부 링크로 연결한다 — 서비스 내부에서 처리하지 않는다 */}
      {pin.예약URL && (
        <p>
          <a
            className="primary link-btn"
            href={pin.예약URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            예약하기
          </a>
        </p>
      )}
      {pin.지도 && (
        <p>
          <a className="opt" href={pin.지도} target="_blank" rel="noopener noreferrer">
            지도에서 보기
          </a>
        </p>
      )}
    </Sheet>
  );
}
