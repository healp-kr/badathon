/* S0 진입 — 설정 전의 홈.
 *
 * 랜딩 페이지가 아니라 **아직 비어 있는 앱 화면**으로 보여야 한다. 그래서 이번 주
 * 활동을 먼저 보여준다 — 열자마자 자기 상태를 말하는 것이 앱이고, 설문부터
 * 들이미는 것은 검사지다.
 */
import { useState } from 'react';
import Ring from '../components/Ring';
import Icon, { type IconName } from '../components/icons';
import DistrictSheet from '../components/DistrictSheet';
import { askLocation } from '../lib/geolocate';
import { todayLabel } from '../lib/format';
import { useApp } from '../state/AppContext';
import { useRecords } from '../state/useRecords';
import styles from './Intro.module.css';

export default function Intro() {
  const { district, sports, setDistrict, openSurvey } = useApp();
  const { stats } = useRecords(sports);
  const [locating, setLocating] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  /* 지역이 없으면 위치부터 확인하고, 실패하면 시트를 연다.
   * 시트에서 고르면 그쪽이 설문을 이어서 연다. */
  async function start() {
    if (district) {
      openSurvey();
      return;
    }
    setLocating(true);
    const located = await askLocation();
    setLocating(false);

    if (located.ok) {
      setDistrict(located.district, 'auto');
      openSurvey();
    } else {
      setSheetOpen(true);
    }
  }

  return (
    <>
      <p className="muted">{todayLabel()}</p>
      <h1>안녕하세요</h1>

      <div className="card ringcard">
        <h3>이번 주 신체활동</h3>
        <Ring
          percent={stats.달성률}
          main={stats.점수}
          unit="분"
          caption={`지침 권장 ${stats.목표}분 기준`}
        />
      </div>

      <button className={styles.cta} type="button" onClick={start} disabled={locating}>
        <span className={styles.eyebrow}>아직 내 유형을 몰라요</span>
        <span className={styles.title}>내게 맞는 운동 찾기</span>
        <span className={styles.sub}>
          {locating ? '위치를 확인하고 있어요…' : '13개 문항 · 2~3분이면 끝나요'}
        </span>
      </button>

      <div className="sec">
        <h2>무엇을 할 수 있나요</h2>
      </div>
      <div className="card">
        <Feature
          icon="운동"
          title="내 유형 찾기"
          body="국민생활체육조사·국민체력측정통계로 만든 선호 12유형 × 체력 16세그먼트"
        />
        <Feature
          icon="지도"
          title="주변에서 찾기"
          body="중구·관악구 체육시설 776곳과 예약 가능한 곳"
        />
        <Feature
          icon="기록"
          title="주간 활동 기록"
          body="한 번 누르면 기록되고, 지침 대비 달성률로 보여드려요"
        />
      </div>

      <p className="note fine">
        체력 유형은 자가평가를 바탕으로 한 추정이라 정확하지 않을 수 있어요.{' '}
        <strong>답변과 기록은 이 기기를 벗어나지 않습니다</strong> — 추천 계산이 브라우저
        안에서 끝나므로 나이·키·몸무게·불편한 곳을 보내는 서버가 없습니다.
      </p>

      {sheetOpen && <DistrictSheet onClose={() => setSheetOpen(false)} />}
    </>
  );
}

function Feature({ icon, title, body }: { icon: IconName; title: string; body: string }) {
  return (
    <div className={styles.feat}>
      <span className={styles.featIcon} aria-hidden="true">
        <Icon name={icon} />
      </span>
      <div>
        <h3>{title}</h3>
        <p className="note">{body}</p>
      </div>
    </div>
  );
}
