/* S2 결과 — 갈래별 추천 전체.
 *
 * 홈이 "오늘 뭐 할까"라면 여기는 "왜 이걸 골랐나"다. 그래서 제외 종목과 처방 기준,
 * 보완 운동까지 전부 편다. 히어로는 compact — 홈에서 이미 본 카드다.
 */
import { useState } from 'react';
import EnvBar from '../components/EnvBar';
import Hero from '../components/Hero';
import SportRow from '../components/SportRow';
import DistrictSheet from '../components/DistrictSheet';
import SportDetail from './sport/SportDetail';
import RecordSheet from './records/RecordSheet';
import Locked from './Locked';
import { useApp } from '../state/AppContext';
import { useRecords } from '../state/useRecords';
import type { 갈래, 추천종목 } from '../api/types';

export default function Result() {
  const { result, sports, setTab } = useApp();
  const { doneToday } = useRecords(sports);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detail, setDetail] = useState<{ bucket: 갈래; item: 추천종목 } | null>(null);
  const [logging, setLogging] = useState<추천종목 | null>(null);
  /* 마지막으로 연 종목을 초록 테두리로 표시해 둔다 — 상세를 닫고 돌아왔을 때
     어디를 보고 있었는지 잃지 않게 한다. */
  const [selected, setSelected] = useState<string | null>(null);

  if (!result) return <Locked where="운동" />;

  function open(bucket: 갈래, item: 추천종목) {
    setSelected(item.종목);
    setDetail({ bucket, item });
  }

  const pref = result.선호유형;

  function find(_sport: string) {
    // 지도 탭이 추천 종목을 스스로 고르므로 여기서는 이동만 시킨다
    setTab('지도');
  }

  return (
    <>
      <h1>이런 운동은 어떠세요</h1>

      <EnvBar env={result.환경} onChangeDistrict={() => setSheetOpen(true)} />
      <Hero pref={result.선호유형} fit={result.체력유형} compact />

      <Bucket
        title={pref ? '이미 하고 계신 운동' : '관심 있다고 하신 운동'}
        items={result.익숙한운동}
        bucket="익숙한운동"
        selected={selected}
        doneToday={doneToday}
        onOpen={open}
        onFind={find}
        onDid={(_b, i) => setLogging(i)}
      />
      <Bucket
        title="비슷한 분들의 선택"
        items={result.새로운운동}
        bucket="새로운운동"
        selected={selected}
        doneToday={doneToday}
        onOpen={open}
        onFind={find}
        onDid={(_b, i) => setLogging(i)}
      />

      {result.제외종목.length > 0 && (
        <div className="card">
          <h3>오늘은 빼 두었어요</h3>
          <ul className="excluded">
            {result.제외종목.map((x) => (
              <li key={x.종목}>
                {x.종목} — {x.사유}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <h3>얼마나, 어느 정도로</h3>
        <p className="note">
          {Object.entries(result.처방.기준)
            .filter(([k]) => k !== '근거') /* 출처 문구는 본문에 섞지 않는다 */
            .map(([k, v]) => (
              <span key={k}>
                · {k} — {v}
                <br />
              </span>
            ))}
        </p>
        {result.처방.조정 && <p className="note warn">{result.처방.조정.메시지}</p>}
      </div>

      {result.보완운동.length > 0 && (
        <div className="card">
          <h3>이런 것도 곁들이면 좋아요</h3>
          {result.보완운동.map((s) => (
            <div key={s.축} style={{ marginBottom: 12 }}>
              <div>
                <span style={{ fontWeight: 800 }}>{s.축}</span>{' '}
                {s.표현 === '제안' && <span className="badge">근거가 약한 제안</span>}
              </div>
              <p className="note">
                {s.운동.join(' · ')}
                {s.처방 && (
                  <>
                    <br />
                    {s.처방}
                  </>
                )}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* 안내는 파스텔 정보 카드로 — 파스텔은 안내·프로모에만 쓴다 */}
      {result.안내.length > 0 && (
        <div className="card info tight">
          <p className="note">
            {result.안내.map((t) => (
              <span key={t}>
                · {t}
                <br />
              </span>
            ))}
          </p>
        </div>
      )}

      <p className="note fine">{result.면책}</p>

      {sheetOpen && <DistrictSheet onClose={() => setSheetOpen(false)} />}
      {detail && (
        <SportDetail item={detail.item} bucket={detail.bucket} onClose={() => setDetail(null)} />
      )}
      {logging && <RecordSheet sport={logging.종목} onClose={() => setLogging(null)} />}
    </>
  );
}

interface BucketProps {
  title: string;
  items: 추천종목[];
  bucket: 갈래;
  selected: string | null;
  doneToday(sport: string): boolean;
  onOpen(bucket: 갈래, item: 추천종목): void;
  onFind(sport: string): void;
  onDid(bucket: 갈래, item: 추천종목): void;
}

function Bucket({ title, items, bucket, selected, doneToday, onOpen, onFind, onDid }: BucketProps) {
  if (!items?.length) return null;
  return (
    <div className="card">
      <h3>{title}</h3>
      {items.map((item) => (
        <SportRow
          key={item.종목}
          item={item}
          bucket={bucket}
          selected={selected === item.종목}
          done={doneToday(item.종목)}
          onOpen={onOpen}
          onFind={onFind}
          onDid={onDid}
        />
      ))}
    </div>
  );
}
