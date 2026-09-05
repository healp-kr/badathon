/* 위치 판정 — 바닐라의 `askLocation()`.
 *
 * 권한 거부는 오류가 아니라 정상 경로다. PRD 가 "위치 권한 거부 시 지역 직접 선택"을
 * 명시하므로, 실패를 던지지 않고 사유를 담아 돌려준다.
 */
import { locate } from '../api/endpoints';

export type LocateOutcome =
  | { ok: true; district: string }
  | { ok: false; reason: 'denied' | 'unsupported' | 'unsupported-area'; message?: string };

export async function askLocation(): Promise<LocateOutcome> {
  if (!navigator.geolocation) return { ok: false, reason: 'unsupported' };

  const position = await new Promise<GeolocationPosition | null>((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(pos),
      () => resolve(null),
      { timeout: 5000, maximumAge: 300000 },
    );
  });

  if (!position) return { ok: false, reason: 'denied' };

  try {
    const res = await locate(position.coords.latitude, position.coords.longitude);
    if (res.district) return { ok: true, district: res.district };
    return { ok: false, reason: 'unsupported-area', message: res.reason };
  } catch {
    return { ok: false, reason: 'unsupported-area' };
  }
}

/** 위치 확인 결과를 사람이 읽는 한 줄로 */
export function locateMessage(outcome: LocateOutcome): string {
  if (outcome.ok) return outcome.district;
  return outcome.reason === 'denied'
    ? '위치 권한이 거부되었어요'
    : '지원 지역 밖이에요';
}
