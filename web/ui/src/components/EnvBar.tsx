/* 오늘의 조건 — 바닐라의 `envBlock()`.
 *
 * 기상·대기·자외선 조회가 실패해도 이 줄만 흐려질 뿐 추천과 기록은 그대로 동작한다.
 * 그것이 이 앱의 원칙이므로, 여기서 예외를 던지거나 화면을 막으면 안 된다.
 */
import type { 환경 } from '../api/types';
import styles from './EnvBar.module.css';

interface Props {
  env: 환경 | null | undefined;
  onChangeDistrict(): void;
}

export default function EnvBar({ env, onChangeDistrict }: Props) {
  const badge = env?.배지?.[0]?.문구;

  return (
    <div className={styles.envbar}>
      {env?.요약 ? (
        <span className={`${styles.text} clamp2`}>
          <b>{env.요약}</b>
          {badge && <span className="note">{badge}</span>}
        </span>
      ) : (
        <span className={`${styles.text} muted`}>오늘의 조건을 불러오지 못했어요</span>
      )}

      <button className="chip-action" type="button" onClick={onChangeDistrict}>
        {env?.요약 ? '지역 변경' : '지역 선택'}
      </button>
    </div>
  );
}
