/* fetch 얇은 래퍼 — 바닐라 버전의 `BD.json` 을 대신한다.
 *
 * 화면은 URL 을 조립하지 않는다. `endpoints.ts` 만 URL 을 안다.
 * 한글 쿼리 파라미터가 많아서(종목·지역) 인코딩을 여기서 한 번에 처리한다
 * — 직접 문자열을 이어붙이면 서버가 요청 자체를 거부한다.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly url: string,
    /** 서버가 준 detail. FastAPI 는 검증 실패를 여기에 담는다. */
    readonly detail?: unknown,
  ) {
    super(`${status} ${url}`);
    this.name = 'ApiError';
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, params?: Params): string {
  if (!params) return path;
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    q.set(key, String(value));
  }
  const query = q.toString();
  return query ? `${path}?${query}` : path;
}

async function parse(res: Response, url: string): Promise<unknown> {
  if (!res.ok) {
    const detail = await res.json().then(
      (body) => (body as { detail?: unknown })?.detail ?? body,
      () => undefined,
    );
    throw new ApiError(res.status, url, detail);
  }
  return res.json();
}

export async function get<T>(path: string, params?: Params): Promise<T> {
  const url = withQuery(path, params);
  return (await parse(await fetch(url), url)) as T;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return (await parse(res, path)) as T;
}

/** 실패해도 화면을 멈추면 안 되는 호출용 — 환경 배지처럼 "없으면 숨기면 그만"인 것들.
 *  이 앱의 원칙이다: 외부 데이터가 죽어도 추천과 기록은 계속 동작한다. */
export async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    return null;
  }
}
