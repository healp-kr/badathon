# -*- coding: utf-8 -*-
"""환경 컨텍스트를 정적 파일로 굽는다 — GitHub Actions 가 1시간마다 돌린다.

정적 배포에는 서버가 없다. 그런데 기상청·대기·자외선 조회에는 인증키가 필요하고,
그 키를 브라우저 번들에 넣으면 공개된다. 그래서 **조회만 Actions 가 대신한다.**

    python tools/fetch_context.py          # → web/ui/public/context/<자치구>.json

키는 `api/.env` 또는 환경변수 `KMA_SERVICE_KEY_DECODED` · `KMA_SERVICE_KEY_ENCODED`
에서 읽는다. Actions 에서는 Secrets 로 주입한다 — 저장소에는 들어가지 않는다.

**실패해도 0 으로 끝난다.** 날씨를 못 받은 것은 배포를 멈출 이유가 아니다. 앱은 배지를
안 띄울 뿐 추천·지도·기록이 그대로 동작한다. 대신 기존 파일을 덮어쓰지 않는다 —
낡은 값이라도 남겨 두는 편이, 빈 파일로 갈아엎는 것보다 낫다(화면이 낡음을 판정한다).
"""
import io
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(ROOT, "web", "ui", "public", "context")


def main():
    # import 시점에 .env 를 읽으므로 키 확인보다 먼저 부르지 않는다
    from api.context import get_context
    from api.locate import DISTRICTS

    has_key = any(os.environ.get(name) for name in
                  ("KMA_SERVICE_KEY_DECODED", "KMA_SERVICE_KEY_ENCODED"))
    if not has_key:
        print("인증키가 없다 — 조회를 건너뛴다. 앱은 배지 없이 정상 동작한다.")

    os.makedirs(OUT_DIR, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    written, skipped = 0, 0
    for district in DISTRICTS:
        path = os.path.join(OUT_DIR, f"{district}.json")
        try:
            ctx = get_context(district)
        except Exception as exc:                     # noqa: BLE001 — 어떤 실패든 배포를 막지 않는다
            print(f"  {district:6} 조회 실패 ({type(exc).__name__}: {exc}) — 기존 파일 유지")
            skipped += 1
            continue

        # 판정이 '모름'이면 배지가 없다. 그래도 파일은 쓴다 —
        # 화면이 '조회했으나 모름'과 '아직 조회 못함'을 구분할 필요는 없지만,
        # 낡음 판정을 하려면 최신 타임스탬프가 필요하다.
        # 타임존 없는 `생성시각` 과 별개로 UTC 시각을 따로 적는다 (화면이 이것만 본다)
        ctx = {**ctx, "fetched_at": fetched_at}

        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(ctx, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")

        badges = " · ".join(b["문구"] for b in ctx.get("배지", [])) or "배지 없음"
        print(f"  {district:6} {ctx.get('판정', '모름'):4}  {badges}")
        written += 1

    print(f"\n{written}곳 기록 · {skipped}곳 건너뜀 → {os.path.relpath(OUT_DIR, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:                          # noqa: BLE001
        # 여기까지 온 것은 조회가 아니라 코드·환경 문제다. 그래도 배포는 막지 않는다
        print(f"환경 컨텍스트 갱신을 건너뛴다: {type(exc).__name__}: {exc}")
        raise SystemExit(0)
