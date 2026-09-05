/* 운동 기록 입력 — "했어요" 한 번으로 끝나야 한다.
 *
 * 강도는 종목 마스터(`sport_master.csv`)가 정한 값을 기본으로 채운다. 화면이 강도를
 * 임의로 정하면 달성률 공식(Σ중 + Σ고×2)이 화면마다 달라진다 — 출처는 하나여야 한다.
 */
import { useState } from 'react';
import Sheet from '../../components/Sheet';
import { useApp } from '../../state/AppContext';
import { useRecords } from '../../state/useRecords';
import type { 강도 } from '../../api/types';

const 시간후보 = [20, 30, 45, 60] as const;
const 강도후보: 강도[] = ['저', '중', '고'];

export default function RecordSheet({
  sport,
  onClose,
}: {
  sport: string;
  onClose(): void;
}) {
  const { sports } = useApp();
  const { add, intensityOf } = useRecords(sports);

  const [minutes, setMinutes] = useState<number>(30);
  const [intensity, setIntensity] = useState<강도>(intensityOf(sport) ?? '중');

  function save() {
    add({ 종목: sport, 시간분: minutes, 강도: intensity });
    onClose();
  }

  return (
    <Sheet onClose={onClose} label={`${sport} 기록`}>
      <h2>{sport}</h2>
      <p className="muted">얼마나 하셨어요?</p>

      <fieldset>
        <legend>시간</legend>
        <div className="chips">
          {시간후보.map((m) => (
            <button
              key={m}
              className="opt"
              type="button"
              aria-pressed={minutes === m}
              onClick={() => setMinutes(m)}
            >
              {m}분
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>강도</legend>
        <div className="chips">
          {강도후보.map((g) => (
            <button
              key={g}
              className="opt"
              type="button"
              aria-pressed={intensity === g}
              onClick={() => setIntensity(g)}
            >
              {g}
            </button>
          ))}
        </div>
        <p className="note fine">
          기본값은 종목 대표 강도예요. 실제로 어떻게 하셨는지에 맞춰 바꿔 주세요.
        </p>
      </fieldset>

      <button className="primary" type="button" onClick={save}>
        기록하기
      </button>
    </Sheet>
  );
}
