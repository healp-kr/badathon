/* 앱 셸 — 어느 화면을 보여줄지만 정한다.
 *
 * 바닐라의 `showTab()` + 각 `renderX()` 호출을 대체한다. 그쪽에서는 화면 전환이
 * `app.innerHTML = ...` 이라 이전 화면의 이벤트 핸들러를 직접 떼어내야 했고
 * (`BD.map.teardown()`), 빠뜨리면 지도가 유령처럼 남았다. 여기서는 언마운트가
 * 정리를 맡으므로 그 종류의 버그가 구조적으로 사라진다.
 */
import TopBar from './components/TopBar';
import TabBar from './components/TabBar';
import DistrictSheet from './components/DistrictSheet';
import Splash from './components/Splash';
import Intro from './screens/Intro';
import Survey from './screens/Survey';
import Home from './screens/Home';
import Result from './screens/Result';
import MapScreen from './screens/MapScreen';
import Records from './screens/Records';
import Locked from './screens/Locked';
import { useApp } from './state/AppContext';
import { useState } from 'react';

export default function App() {
  const { booted, bootError, surveyOpen, submitting } = useApp();
  const [sheetOpen, setSheetOpen] = useState(false);

  if (!booted) return <Splash />;

  if (bootError) {
    return (
      <main>
        <h1>시작하지 못했어요</h1>
        <p className="note">{bootError}</p>
        <button className="primary" type="button" onClick={() => location.reload()}>
          다시 시도
        </button>
      </main>
    );
  }

  // 온보딩이 끝나기 전에는 앱바와 탭바를 감춘다
  const chromeVisible = !surveyOpen;

  return (
    <>
      {chromeVisible && <TopBar onPickDistrict={() => setSheetOpen(true)} />}

      <main>
        {submitting ? (
          <p className="loading">결과를 만들고 있어요…</p>
        ) : (
          <Screen />
        )}
      </main>

      {sheetOpen && <DistrictSheet onClose={() => setSheetOpen(false)} />}
      {/* 설정 전에도 탭은 그대로 둔다 — 랜딩이 아니라 "아직 비어 있는 앱"으로 보여야 한다.
          추천이 없는 탭은 Locked 이 받아 설문으로 안내한다. */}
      {chromeVisible && <TabBar />}
    </>
  );
}

/* 추천이 없어도 갈 수 있는 탭이 있다 — 기록은 설문과 무관하게 쓰이고,
 * 운동·지도는 Locked 이 받아 설문으로 안내한다. 홈만 Intro 로 떨어진다. */
function Screen() {
  const { surveyOpen, result, tab } = useApp();

  if (surveyOpen) return <Survey />;

  switch (tab) {
    case '운동':
      return result ? <Result /> : <Locked where="운동" />;
    case '지도':
      return result ? <MapScreen /> : <Locked where="지도" />;
    case '기록':
      return <Records />;
    case '홈':
    default:
      return result ? <Home /> : <Intro />;
  }
}
