/* 아직 추천이 없는 탭 — 빈 화면 대신 무엇이 필요한지 말하고 길을 준다. */
import { useApp } from '../state/AppContext';

export default function Locked({ where }: { where: '운동' | '지도' }) {
  const { openSurvey } = useApp();

  return (
    <>
      <h1>{where === '운동' ? '운동' : '주변에서 찾기'}</h1>
      <div className="card">
        <h3>먼저 몇 가지만 여쭤볼게요</h3>
        <p className="note">
          13개 문항에 답하시면{' '}
          {where === '운동' ? '유형에 맞는 종목과 강도를' : '추천 종목의 주변 시설을'}{' '}
          보여드릴 수 있어요.
        </p>
        <button className="primary" type="button" onClick={openSurvey}>
          내게 맞는 운동 찾기
        </button>
      </div>
    </>
  );
}
