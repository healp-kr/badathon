/* S3 종목 상세 — 왜 이 종목인지, 어디서 할 수 있는지.
 *
 * 바닐라에서는 전역 `state.items['갈래::종목']` 에서 아이템을 되짚었다.
 * 여기서는 부모가 아이템을 그대로 넘기므로 그 사전이 필요 없다.
 */
import { useEffect, useState } from 'react';
import Sheet from '../../components/Sheet';
import { fetchFacilities } from '../../api/endpoints';
import { optional } from '../../api/client';
import { distance, plain } from '../../lib/format';
import { useApp } from '../../state/AppContext';
import type { FacilitiesResponse, 갈래, 추천종목 } from '../../api/types';

interface Props {
  item: 추천종목;
  bucket: 갈래;
  onClose(): void;
}

export default function SportDetail({ item, onClose }: Props) {
  const { district } = useApp();
  const [facilities, setFacilities] = useState<FacilitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    optional(fetchFacilities(item.종목, { district })).then((res) => {
      if (!alive) return;
      setFacilities(res);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [item.종목, district]);

  const nearby = facilities?.주변 ?? [];
  const booking = facilities?.예약 ?? [];

  return (
    <Sheet onClose={onClose} label={`${item.종목} 상세`}>
      <h2>{item.종목}</h2>

      <p>
        {item.강도 && item.강도 !== '미확인' && <span className="badge">강도 {item.강도}</span>}
        {item.실내외 && <span className="badge">{item.실내외}</span>}
        {item.고령적합 && <span className="badge">고령 {item.고령적합}</span>}
      </p>

      {item.강도주의 && (
        <p className="note warn">
          <span className="badge warn">주의</span>
          {item.강도주의}
        </p>
      )}

      {item.이유 && <p className="note">{plain(item.이유)}</p>}
      {item.처방 && <p className="note">{item.처방}</p>}
      {item.근거 && <p className="note fine">{item.근거}</p>}

      {item.부담부위?.length ? (
        <p className="note">부담이 갈 수 있는 곳 — {item.부담부위.join(' · ')}</p>
      ) : null}

      <h3>어디서 하나요</h3>
      {loading ? (
        <p className="loading">주변을 찾고 있어요…</p>
      ) : facilities?.매칭없음 ? (
        <p className="note">
          {facilities.사유 || '이 종목은 시설 매핑에 없어요'}
        </p>
      ) : nearby.length === 0 && booking.length === 0 ? (
        <p className="note">가까운 곳을 찾지 못했어요</p>
      ) : (
        <>
          {booking.length > 0 && (
            <>
              <p className="note">예약 가능</p>
              {booking.slice(0, 3).map((f, i) => (
                <FacilityLine key={`${f.시설명}-${i}`} name={f.시설명} meters={f.거리m} link={f.지도} />
              ))}
            </>
          )}
          {nearby.slice(0, 5).map((f, i) => (
            <FacilityLine key={`${f.시설명}-${i}`} name={f.시설명} meters={f.거리m} link={f.지도} />
          ))}
        </>
      )}

      {facilities?.확인필요 && (
        <p className="note fine">시설 정보가 일부 누락되어 있어요. 방문 전에 확인해 주세요.</p>
      )}
    </Sheet>
  );
}

function FacilityLine({
  name,
  meters,
  link,
}: {
  name: string;
  meters: number | null | undefined;
  link?: string;
}) {
  return (
    <p className="note">
      {meters != null && <b>{distance(meters)} </b>}
      {name}
      {/* 지도·예약은 외부 링크로 연결한다 — 서비스 내부에서 처리하지 않는다 */}
      {link && (
        <>
          {' '}
          <a href={link} target="_blank" rel="noopener noreferrer">
            지도
          </a>
        </>
      )}
    </p>
  );
}
