/* 히어로 — "당신의 유형". 바닐라의 `heroBlock()` 을 옮겼다.
 *
 * 이 앱의 주인공은 활동량이 아니라 **분류 결과**다. 6,602명 데이터로 만든 두 축이
 * 무엇을 했는지가 첫 화면에서 읽혀야 한다. 순서를 뒤집으면 흔한 만보기 앱이 된다.
 *
 * 확신도가 낮으면(`ambiguous`) 대안 유형을 병기한다 — 자가평가 기반 추정이라
 * 단정하지 않는 것이 PRD 의 리스크 대응이다. 이 줄을 지우지 말 것.
 */
import type { 선호유형, 체력유형 } from '../api/types';
import styles from './Hero.module.css';

interface Props {
  pref: 선호유형 | null;
  fit: 체력유형 | null;
  /** 운동 탭에서는 홈에서 이미 본 카드라 설명 줄을 접는다 */
  compact?: boolean;
}

export default function Hero({ pref, fit, compact = false }: Props) {
  return (
    <div className={`${styles.hero} ${compact ? styles.compact : ''}`}>
      <div className={styles.eyebrow}>설문 13문항으로 찾은 당신의 유형</div>
      <div className={styles.title}>{pref ? pref.name : '관심 운동 중심'}</div>
      {fit && <div className={styles.sub}>{fit.segment}</div>}

      {!compact && (
        <div className={styles.desc}>
          {pref ? (
            <>운동 습관이 이 유형에 <b>가까워요</b>.</>
          ) : (
            <>아직 규칙적으로 운동하지 않으신다고 하셨어요.</>
          )}
          {fit && <> 또래와 비교한 체력은 <b>{fit.segment}</b> 쪽일 수 있어요.</>}
          {fit?.ambiguous && fit.alternative && (
            <><br /><b>{fit.alternative}</b>일 가능성도 비슷합니다.</>
          )}
        </div>
      )}
    </div>
  );
}
