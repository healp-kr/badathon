/* 홈 — 유형 · 오늘 할 것 · 이번 주.
 *
 * 이 앱의 주인공은 활동량이 아니라 **분류 결과**다. 그래서 히어로가 유형 카드고,
 * 주간 달성률은 아래로 내려간다 — 순서가 뒤집히면 흔한 만보기 앱이 된다.
 */
import { useState } from 'react';
import EnvBar from '../components/EnvBar';
import Hero from '../components/Hero';
import LimeBand from '../components/LimeBand';
import Rail from '../components/Rail';
import Ring from '../components/Ring';
import SportTile from '../components/SportTile';
import DistrictSheet from '../components/DistrictSheet';
import SportDetail from './sport/SportDetail';
import { todayLabel } from '../lib/format';
import { useApp } from '../state/AppContext';
import { useRecords } from '../state/useRecords';
import type { 갈래, 추천종목 } from '../api/types';

export default function Home() {
  const { result, sports, setTab } = useApp();
  const { stats } = useRecords(sports);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [detail, setDetail] = useState<{ bucket: 갈래; item: 추천종목 } | null>(null);

  if (!result) return null;

  const today = result.익숙한운동 ?? [];
  const fresh = result.새로운운동 ?? [];

  function select(bucket: 갈래, item: 추천종목) {
    setDetail({ bucket, item });
  }

  return (
    <>
      {/* 라임 밴드 — 날짜·인사말·오늘의 조건을 한 덩어리로 묶는다.
          밴드 위 글자는 --ink 로 둔다(라임 위 흰 글자는 대비가 나오지 않는다). */}
      <LimeBand>
        <p className="muted">{todayLabel()}</p>
        <h1>오늘도 움직여 볼까요</h1>
        <EnvBar env={result.환경} onChangeDistrict={() => setSheetOpen(true)} />
      </LimeBand>

      <Hero pref={result.선호유형} fit={result.체력유형} />

      {today.length > 0 && (
        <>
          <div className="sec">
            <h2>오늘 이건 어때요</h2>
            <button className="link" type="button" onClick={() => setTab('운동')}>
              전체 보기
            </button>
          </div>
          <Rail>
            {today.map((item) => (
              <SportTile
                key={item.종목}
                item={item}
                bucket="익숙한운동"
                onSelect={select}
              />
            ))}
          </Rail>
        </>
      )}

      {fresh.length > 0 && (
        <>
          <div className="sec">
            <h2>비슷한 분들의 선택</h2>
          </div>
          <p className="muted" style={{ margin: '-6px 2px 10px' }}>
            같은 유형에서 유독 많이 하는 운동이에요
          </p>
          <Rail>
            {fresh.map((item) => (
              <SportTile
                key={item.종목}
                item={item}
                bucket="새로운운동"
                onSelect={select}
              />
            ))}
          </Rail>
        </>
      )}

      <div className="sec">
        <h2>이번 주</h2>
        <button className="link" type="button" onClick={() => setTab('기록')}>
          기록 보기
        </button>
      </div>
      <div className="card ringcard">
        <Ring
          percent={Math.min(100, stats.달성률)}
          main={stats.점수}
          unit="분"
          caption={`지침 권장 ${stats.목표}분 기준`}
        />
        <p className="note">
          {stats.이번주
            ? `근력 운동 ${stats.근력일수}일 · 기록 ${stats.이번주}건`
            : '아직 이번 주 기록이 없어요. 운동하고 [했어요]만 누르면 여기에 쌓입니다'}
        </p>
      </div>

      {sheetOpen && <DistrictSheet onClose={() => setSheetOpen(false)} />}
      {detail && (
        <SportDetail
          item={detail.item}
          bucket={detail.bucket}
          onClose={() => setDetail(null)}
        />
      )}
    </>
  );
}
