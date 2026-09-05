/* 아이콘 — 외부 아이콘 패키지를 쓰지 않는다. 네 개뿐이고 의존성을 들일 이유가 없다.
 *
 * 탭바가 활성 상태를 "아이콘 채움"으로 말하므로 유형마다 채운 변형을 함께 둔다.
 * 선 아이콘(운동·기록)은 fill 로는 채워지지 않아 도형 자체를 다르게 그린다.
 */
import type { ReactNode } from 'react';

export type IconName = '홈' | '운동' | '지도' | '기록';

const OUTLINE: Record<IconName, ReactNode> = {
  홈: <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  운동: <path d="M6.5 8v8M17.5 8v8M4 10v4M20 10v4M6.5 12h11" />,
  지도: (
    <>
      <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.6" />
    </>
  ),
  기록: <path d="M5 20V10M12 20V4M19 20v-7" />,
};

const FILLED: Record<IconName, ReactNode> = {
  홈: <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" fill="currentColor" stroke="none" />,
  운동: (
    <g fill="currentColor" stroke="none">
      <rect x="5" y="7" width="3" height="10" rx="1.5" />
      <rect x="16" y="7" width="3" height="10" rx="1.5" />
      <rect x="2.5" y="9.5" width="2" height="5" rx="1" />
      <rect x="19.5" y="9.5" width="2" height="5" rx="1" />
      <rect x="7.5" y="10.75" width="9" height="2.5" rx="1.25" />
    </g>
  ),
  지도: (
    <path
      d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11zm0-8.4a2.6 2.6 0 1 1 0-5.2 2.6 2.6 0 0 1 0 5.2z"
      fill="currentColor"
      stroke="none"
      fillRule="evenodd"
    />
  ),
  기록: (
    <g fill="currentColor" stroke="none">
      <rect x="3.5" y="10" width="3" height="10" rx="1.5" />
      <rect x="10.5" y="4" width="3" height="16" rx="1.5" />
      <rect x="17.5" y="13" width="3" height="7" rx="1.5" />
    </g>
  ),
};

export default function Icon({
  name,
  filled = false,
}: {
  name: IconName;
  filled?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {filled ? FILLED[name] : OUTLINE[name]}
    </svg>
  );
}
