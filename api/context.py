# -*- coding: utf-8 -*-
"""환경 컨텍스트 — 지금·여기의 조건을 하나로 합친다.

    from api.context import get_context, apply_context
    ctx = get_context("관악구")            # 날씨 + 대기 + 자외선
    view = apply_context(serve_result, ctx, 운동시간대="저녁(18-22시)")

**serve() 는 건드리지 않는다.** 같은 입력이면 항상 같은 출력을 낸다는 성질이 로그 분석과
model_version 추적의 근거이기 때문이다. 날씨는 그 밖에서, 표현 계층의 후처리로만 적용한다.
추천 목록(무엇을 추천하는가)은 그대로 두고 **표시 순서와 배지**만 바꾼다.

원칙 셋:
  1. 종목을 지우지 않는다. 순서만 바꾸고 이유를 배지로 말한다
  2. 갈래(기반/익숙한/새로운) 경계를 넘어 섞지 않는다 — 두 갈래의 클릭률 비교가
     가중치 보정(D4)의 근거이므로 갈래를 흐리면 그 측정이 깨진다
  3. 모르면 아무것도 하지 않는다. 조회 실패는 "정상"이 아니라 "모름"이다
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import weather_api_v17 as weather          # noqa: E402
from locate import DISTRICTS                # noqa: E402

CACHE_TTL_SEC = 600          # 10분. 초단기예보가 매시 30분 발표이므로 충분하다
_CACHE = {}

# 판정 강도. 큰 쪽이 이긴다
_RANK = {"모름": 0, "정상": 1, "주의": 2, "비권장": 3}

CAI_RULE = {"4": ("비권장", "미세먼지 매우나쁨"), "3": ("주의", "미세먼지 나쁨")}
UV_THRESHOLD = 6             # 생활기상지수 '높음' 구간 시작
DAYTIME_SLOTS = ("아침/새벽(6-8시)", "오전(8-12시)", "점심(12-14시)", "오후(14-18시)")


def get_context(district, now=None):
    """자치구 하나의 현재 조건. 10분 캐시.

    반환 키: district · 판정 · 배지 · 요약 · 기온 · 강수 · 대기 · 자외선 · 조회
    """
    if district not in DISTRICTS:
        return {"district": district, "판정": "모름", "배지": [],
                "요약": None, "사유": "지원하지 않는 지역"}

    cached = _CACHE.get(district)
    if cached and time.time() - cached[0] < CACHE_TTL_SEC:
        return cached[1]

    ctx = _build(district, now or datetime.now())
    _CACHE[district] = (time.time(), ctx)
    return ctx


def _build(district, now):
    station = DISTRICTS[district].get("cai_station", district)
    w = weather.get_outdoor_status(district)
    cai = weather.fetch_cai(station)
    uv = _uv_now(district)

    badges, verdict = [], w.get("판정", "모름")

    if verdict == "비권장":
        badges.append({"종류": "강수", "문구": f"{w['이유']} — 오늘은 실내가 편해요",
                       "시간대조건": None})
    elif verdict == "주의":
        badges.append({"종류": "기온", "문구": w["이유"], "시간대조건": None})

    grade = str(cai.get("khaiGrade") or "") if cai.get("ok") else ""
    if grade in CAI_RULE:
        level, label = CAI_RULE[grade]
        verdict = _max(verdict, level)
        badges.append({"종류": "대기질", "문구": f"{label} — 실내 종목을 먼저 보여드려요"
                       if level == "비권장" else f"{label} — 무리하지 마세요",
                       "시간대조건": None})

    if uv.get("지수") is not None and uv["지수"] >= UV_THRESHOLD:
        verdict = _max(verdict, "주의")
        # 저녁에 운동하는 사람에게 자외선 배지는 의미가 없다. 표시 조건을 함께 넘긴다
        badges.append({"종류": "자외선", "문구": f"자외선 지수 {uv['지수']} — 낮 시간대는 그늘로",
                       "시간대조건": "낮"})

    if not w.get("ok", True) and verdict == "모름":
        verdict = "모름"

    return {
        "district": district,
        "생성시각": now.isoformat(timespec="seconds"),
        "판정": verdict,
        "실외권장": None if verdict == "모름" else verdict != "비권장",
        "배지": badges,
        "요약": _summary(district, w, cai),
        "기온": w.get("기온"),
        "강수": w.get("강수형태"),
        "하늘": w.get("하늘"),
        "대기": cai.get("등급") if cai.get("ok") else None,
        "자외선": uv.get("지수"),
        "조회": {"날씨": w.get("판정") != "모름", "대기": bool(cai.get("ok")),
                 "자외선": uv.get("지수") is not None},
    }


def _uv_now(district):
    """생활기상지수 자외선 — h0 이 발표시각의 지수다."""
    raw = weather.fetch_uv_index(district)
    if not raw.get("ok") or not raw.get("items"):
        return {"지수": None}
    try:
        return {"지수": int(raw["items"][0].get("h0"))}
    except (TypeError, ValueError):
        return {"지수": None}


def _summary(district, w, cai):
    parts = [district]
    if w.get("기온") is not None:
        parts.append(f"{w['기온']:.0f}도")
    if w.get("강수형태") and w["강수형태"] != "없음":
        parts.append(w["강수형태"])
    elif w.get("하늘"):
        parts.append(w["하늘"])
    if cai.get("ok") and cai.get("등급"):
        parts.append(f"미세먼지 {cai['등급']}")
    return " · ".join(parts) if len(parts) > 1 else None


def _max(a, b):
    return a if _RANK[a] >= _RANK[b] else b


# ------------------------------------------------------------------
# 표현 계층 후처리 — 순서와 배지만 바꾼다
# ------------------------------------------------------------------
BUCKETS = ("기반활동", "익숙한운동", "새로운운동")


def apply_context(result, ctx, 운동시간대=None, display_n=3):
    """serve() 결과에 환경 컨텍스트를 얹은 **표시용 사본**을 만든다.

    원본은 건드리지 않는다. 로그에는 serve() 원본 순위와 여기 매긴 display_rank 를
    둘 다 남겨야 재정렬의 효과를 나중에 측정할 수 있다.

    display_n : 갈래별 최종 표시 개수. **자르는 일은 재정렬 뒤에 한다.**
                serve() 에서 미리 3개로 잘라 오면 끌어올릴 실내 종목이 목록에 없다
                — serve(payload, top_n=6) 처럼 넉넉히 받아 여기서 자를 것.
    """
    view = dict(result)
    view["환경"] = _visible_context(ctx, 운동시간대)

    reorder = bool(ctx) and ctx.get("실외권장") is False
    for bucket in BUCKETS:
        items = [dict(x) for x in result.get(bucket) or []]
        for rank, item in enumerate(items):
            item["원본순위"] = rank
            if reorder and item.get("실내외") == "실외":
                item["환경배지"] = _outdoor_badge(ctx)
        if reorder:
            # 갈래 안에서만 재정렬한다. 실내를 앞으로, 나머지는 원래 순서 유지
            items.sort(key=lambda i: (i.get("실내외") == "실외", i["원본순위"]))
        if display_n:
            items = items[:display_n]
        for rank, item in enumerate(items):
            item["display_rank"] = rank
        view[bucket] = items

    view["재정렬"] = reorder
    return view


def _visible_context(ctx, 운동시간대):
    """사용자의 운동 시간대에 해당하는 배지만 남긴다."""
    if not ctx:
        return None
    visible = []
    for badge in ctx.get("배지", []):
        if badge.get("시간대조건") == "낮" and 운동시간대 not in DAYTIME_SLOTS:
            continue
        visible.append(badge)
    return {**ctx, "배지": visible}


def _outdoor_badge(ctx):
    reasons = [b["문구"] for b in ctx.get("배지", []) if b["종류"] in ("강수", "대기질")]
    return reasons[0] if reasons else "오늘은 실외 활동이 어려울 수 있어요"


if __name__ == "__main__":
    import json
    for gu in DISTRICTS:
        print(json.dumps(get_context(gu), ensure_ascii=False, indent=1))
