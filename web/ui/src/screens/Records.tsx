/* S5 기록 — 이번 주 달성률과 기록 목록.
 *
 * 미달성을 질책하지 않는다. "이번 주는 60분 하셨어요"까지만 말한다.
 * 기록이 이 기기에만 있다는 사실은 화면에 밝힌다(§4) — 감추면 나중에 배신이 된다.
 */
import Ring from '../components/Ring';
import { kstLabel, useRecords } from '../state/useRecords';
import { useApp } from '../state/AppContext';
import styles from './Records.module.css';

const WEEKDAY = ['월', '화', '수', '목', '금', '토', '일'];

export default function Records() {
  const { sports } = useApp();
  const { stats, remove } = useRecords(sports);

  return (
    <>
      <h1>이번 주 기록</h1>

      {/* 이번 주 성과는 연녹 채움으로 시각적으로 떼어 놓는다 */}
      <div className={`card ringcard ${styles.summary}`}>
        <Ring
          percent={Math.min(100, stats.달성률)}
          main={stats.점수}
          unit="분"
          caption={`지침 권장 ${stats.목표}분 기준`}
        />
        <p className="note">
          근력 운동 {stats.근력일수}일 / 권장 {stats.근력목표}일
          {stats.저강도횟수 > 0 && ` · 저강도 ${stats.저강도횟수}회`}
        </p>
        {stats.연속주차 > 0 && (
          <p className="note">
            <span className="badge env">연속</span>
            {stats.연속주차}주째 지침을 채우고 계세요
          </p>
        )}
      </div>

      <div className="card">
        <h3>요일별</h3>
        <div className={styles.week}>
          {stats.요일분.map((minutes, i) => (
            <div key={WEEKDAY[i]} className={styles.day}>
              <div className={styles.bar}>
                <div style={{ height: `${Math.min(100, (minutes / 60) * 100)}%` }} />
              </div>
              <span className="note fine">{WEEKDAY[i]}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="sec">
        <h2>전체 기록</h2>
      </div>

      {stats.전체.length === 0 ? (
        <div className="card">
          <p className="note">
            아직 기록이 없어요. 운동하고 [했어요]만 누르면 여기에 쌓입니다.
          </p>
        </div>
      ) : (
        <div className="card">
          {stats.전체.map((r) => (
            <div key={r.id} className={styles.row}>
              <span className={styles.thumb} aria-hidden="true">
                {r.종목.slice(0, 1)}
              </span>
              <div className={styles.body}>
                <span className={styles.name}>{r.종목}</span>
                <span className={`${styles.meta} clamp2`}>
                  {kstLabel(r.일시)} · {r.시간분}분
                </span>
                <span className={styles.chips}>
                  <span className="badge">강도 {r.강도}</span>
                  {r.샘플 && <span className="badge sample">샘플</span>}
                </span>
              </div>
              <button className="link" type="button" onClick={() => remove(r.id)}>
                삭제
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 로컬 저장 고지는 파스텔 안내 카드로 승격한다 — 문구는 그대로 */}
      <div className="card info">
        <p className="note">
          기록은 이 기기에만 저장됩니다. 브라우저 데이터를 지우면 함께 사라져요.
          설문 답변도 서버로 보내지 않습니다.
        </p>
      </div>
    </>
  );
}
