/* 환경 컨텍스트 — `api/context.py` 의 포팅 (표현 계층 부분).
 *
 * 원본은 두 가지 일을 했다. 정적화하면서 그 둘이 갈렸다.
 *
 *   1. **조회** — 기상청·대기·자외선 API 호출. 인증키가 필요하다.
 *      브라우저에 키를 넣을 수 없으므로 GitHub Actions 가 1시간마다 대신 조회해
 *      `public/context/<자치구>.json` 으로 커밋한다. 여기서는 그 파일을 읽기만 한다.
 *   2. **후처리** — `applyContext`. 순서와 배지만 바꾼다. 그대로 옮겼다.
 *
 * 원칙 셋은 그대로다.
 *   1. 종목을 지우지 않는다. 순서만 바꾸고 이유를 배지로 말한다
 *   2. 갈래 경계를 넘어 섞지 않는다
 *   3. **모르면 아무것도 하지 않는다.** 조회 실패는 "정상"이 아니라 "모름"이다
 *      — 파일이 없거나 오래됐으면 배지를 아예 띄우지 않는다
 */

type Json = any;

const BUCKETS = ['기반활동', '익숙한운동', '새로운운동'] as const;

const DAYTIME_SLOTS = new Set([
  '아침/새벽(6-8시)',
  '오전(8-12시)',
  '점심(12-14시)',
  '오후(14-18시)',
]);

/** 이보다 오래된 파일은 안 쓴다. Actions 는 1시간마다 도는데, 두 번까지는 놓쳐도 봐준다.
 *  그 이상이면 낡은 날씨로 실외 종목을 내리는 편보다 아무 말 안 하는 편이 낫다. */
const MAX_AGE_MS = 3 * 60 * 60 * 1000;

/** 사용자의 운동 시간대에 해당하는 배지만 남긴다. */
function visibleContext(ctx: Json, 운동시간대: string | null | undefined): Json {
  if (!ctx) return null;
  const visible = (ctx['배지'] ?? []).filter(
    (badge: Json) =>
      !(badge['시간대조건'] === '낮' && !DAYTIME_SLOTS.has(운동시간대 ?? '')),
  );
  return { ...ctx, 배지: visible };
}

function outdoorBadge(ctx: Json): string {
  const reasons = (ctx['배지'] ?? [])
    .filter((b: Json) => b['종류'] === '강수' || b['종류'] === '대기질')
    .map((b: Json) => b['문구']);
  return reasons.length > 0 ? reasons[0] : '오늘은 실외 활동이 어려울 수 있어요';
}

/** `serve()` 결과에 환경 컨텍스트를 얹은 **표시용 사본**을 만든다.
 *
 * 원본은 건드리지 않는다. `serve()` 가 같은 입력이면 같은 출력을 낸다는 성질이
 * model_version 추적의 근거이기 때문이다.
 *
 * displayN : 갈래별 최종 표시 개수. **자르는 일은 재정렬 뒤에 한다** —
 *            미리 3개로 잘라 오면 끌어올릴 실내 종목이 목록에 없다.
 */
export function applyContext(
  result: Json,
  ctx: Json,
  운동시간대: string | null = null,
  displayN = 3,
): Json {
  const view: Json = { ...result };
  view['환경'] = visibleContext(ctx, 운동시간대);

  const reorder = Boolean(ctx) && ctx['실외권장'] === false;

  for (const bucket of BUCKETS) {
    const items: Json[] = (result[bucket] ?? []).map((x: Json) => ({ ...x }));
    items.forEach((item, rank) => {
      item['원본순위'] = rank;
      if (reorder && item['실내외'] === '실외') item['환경배지'] = outdoorBadge(ctx);
    });

    let shown = items;
    if (reorder) {
      // 갈래 안에서만 재정렬한다. 실내를 앞으로, 나머지는 원래 순서 유지
      shown = items.slice().sort((a, b) => {
        const ao = a['실내외'] === '실외' ? 1 : 0;
        const bo = b['실내외'] === '실외' ? 1 : 0;
        if (ao !== bo) return ao - bo;
        return a['원본순위'] - b['원본순위'];
      });
    }
    if (displayN) shown = shown.slice(0, displayN);
    shown.forEach((item, rank) => {
      item['display_rank'] = rank;
    });
    view[bucket] = shown;
  }

  view['재정렬'] = reorder;
  return view;
}

/** GitHub Actions 가 구워 둔 자치구별 조건을 읽는다.
 *
 * 실패는 정상 경로다 — 파일이 아직 없거나(첫 배포), 워크플로가 멈췄거나,
 * 인증키가 만료됐을 수 있다. 어느 경우든 배지 없이 추천은 그대로 동작한다.
 */
export async function loadContext(district: string): Promise<Json> {
  const base = import.meta.env.BASE_URL ?? '/';
  const url = `${base}context/${encodeURIComponent(district)}.json`;

  let ctx: Json;
  try {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) return null;
    ctx = await res.json();
  } catch {
    return null;
  }
  if (!ctx || typeof ctx !== 'object') return null;

  /* 낡은 날씨로 실외 종목을 내리지 않는다.
   *
   * `생성시각` 은 타임존이 없는 로컬 시각이다(파이썬 `datetime.now()`). Actions 러너는
   * UTC 이므로 한국 브라우저가 그 문자열을 KST 로 읽으면 9시간 미래가 되어 **영원히
   * 낡지 않는다**. 그래서 갱신 스크립트가 `fetched_at` 을 UTC(Z) 로 따로 적고,
   * 판정은 그 값으로만 한다. 없으면 판정을 포기한다 — 틀린 판정보다 낫다. */
  const stamped = Date.parse(ctx['fetched_at'] ?? '');
  if (!Number.isNaN(stamped) && Date.now() - stamped > MAX_AGE_MS) return null;

  return ctx;
}
