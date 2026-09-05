/* Python 호환 반올림.
 *
 * 파이썬 `round()` 는 **은행가 반올림**(round-half-to-even)이고, JS 의 `Math.round` 는
 * 0.5 를 항상 위로 올린다. 골든 파일 9,549개 실수 중 6개가 실제로 이 차이에 걸린다 —
 * 화면으로는 절대 안 보이고 골든 비교에서만 드러나는 종류의 어긋남이다.
 *
 * 정확히 두 가지만 하면 파이썬과 같아진다.
 *
 * 1. **타이가 아닐 때** — `toFixed(n)` 이 곧 정답이다. ECMA-262 의 `toFixed` 는
 *    파이썬처럼 double 의 *정확한* 값을 기준으로 가장 가까운 값을 고른다.
 *    `x * 10**n` 을 직접 계산하면 그 곱셈에서 오차가 새로 생겨 어긋난다
 *    (0.95 * 10 이 정확히 9.5 가 되어 버리는 식).
 *
 * 2. **정확한 타이일 때만** 짝수 쪽으로 보낸다. double 은 이진 유리수라
 *    n 자리에서 정확한 타이가 되려면 `x` 가 `1/2^(n+1)` 의 홀수 배여야 한다
 *    (x = j/2^(n+1), j 홀수). 그 판정은 2 의 거듭제곱 곱셈이라 오차가 없다.
 */

/** 파이썬 `round(x, digits)` 와 같은 값을 낸다. */
export function pyRound(x: number, digits = 0): number {
  if (!Number.isFinite(x)) return x;

  // 정확한 타이인가 — x 가 1/2^(digits+1) 의 홀수 배인가
  const half = x * Math.pow(2, digits + 1);
  if (Number.isSafeInteger(half) && !Number.isInteger(half / 2)) {
    const scale = Math.pow(10, digits);
    const scaled = x * scale; // 타이일 때 이 값은 정확히 k + 0.5 다
    const lower = Math.floor(scaled);
    const even = lower % 2 === 0 ? lower : lower + 1;
    const rounded = even / scale;
    // 파이썬 round(-0.5) 는 -0.0 이다. 부호 있는 0 을 잃지 않는다
    return rounded === 0 && (x < 0 || Object.is(x, -0)) ? -0 : rounded;
  }

  return Number(x.toFixed(digits));
}

/** 파이썬 `round(float(x), digits)` 자리에 그대로 대응한다. null 은 통과시킨다. */
export function pyRoundOrNull(x: number | null | undefined, digits = 0): number | null {
  if (x === null || x === undefined || !Number.isFinite(x)) return null;
  return pyRound(x, digits);
}
