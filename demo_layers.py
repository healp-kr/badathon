# -*- coding: utf-8 -*-
"""화면 없이 전체 흐름을 확인하는 콘솔 데모.

    python demo_layers.py

위치 판정 → 환경 컨텍스트 → 배정·추천 → 날씨 재정렬 → 실제 시설 → 혼잡도.
앱 프론트가 붙기 전에 백엔드가 실제로 이어지는지 보는 용도다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serve import serve                                   # noqa: E402
from api.locate import resolve_district                   # noqa: E402
from api.context import get_context, apply_context        # noqa: E402
from geo.facility import find_facilities                  # noqa: E402
from geo.crowding import get_crowding, slot_to_hour       # noqa: E402

LINE = "=" * 74

RAIN = {"district": None, "판정": "비권장", "실외권장": False,
        "요약": "비 · 22도 · 미세먼지 보통",
        "배지": [{"종류": "강수", "문구": "비 예보 — 오늘은 실내가 편해요", "시간대조건": None}]}


def run(label, payload, lat, lon, force_rain=False):
    print("\n" + LINE)
    print(label)
    print(LINE)

    located = resolve_district(lat, lon)
    district = located["district"]
    print(f"위치      ({lat}, {lon}) → {district or '지원 밖'} · {located['사유']}")
    if district is None:
        print("          → 지역 선택 시트로. 추천은 그대로 진행된다")

    ctx = get_context(district) if district else None
    if force_rain and district:
        ctx = {**RAIN, "district": district}
    if ctx:
        print(f"오늘      {ctx['요약']} · 판정 {ctx['판정']}")

    result = serve(payload, top_n=10)              # 후보를 넉넉히 받아
    view = apply_context(result, ctx, 운동시간대=payload.get("운동시간대"),
                         display_n=3)              # 표현 계층에서 자른다

    pref = view["선호유형"]["name"] if view["선호유형"] else "없음(비참여자)"
    fit = view["체력유형"]
    print(f"선호유형  {pref}")
    if fit:
        amb = " · 확신도 낮음" if fit["ambiguous"] else ""
        print(f"체력유형  {fit['segment']} (확신도 {fit['confidence']}{amb})")
    print(f"권장강도  상한 {view['처방']['권장강도상한']} · 컷 {view['처방']['강도컷']}")

    if view["재정렬"]:
        print("재정렬    실외 → 실내 (종목은 지우지 않았다)")

    for bucket in ("기반활동", "익숙한운동", "새로운운동"):
        items = view.get(bucket) or []
        if not items:
            continue
        print(f"\n[{bucket}]")
        for item in items:
            moved = ""
            if item["원본순위"] != item["display_rank"]:
                moved = f"  (원본 {item['원본순위'] + 1}위)"
            badge = item.get("환경배지") or item.get("강도주의") or ""
            print(f"  · {item['종목']}  [{item.get('실내외')}·{item.get('강도')}]{moved}")
            if badge:
                print(f"      ↳ {badge}")

    if view["제외종목"]:
        print("\n[제외]")
        for item in view["제외종목"]:
            print(f"  · {item['종목']} — {item['사유']}")

    # 시설 — 첫 종목으로
    target = (view["새로운운동"] or view["익숙한운동"] or view["기반활동"])[0]["종목"]
    fac = find_facilities(target, lat=lat, lon=lon, district=district)
    print(f"\n[시설] {target}")
    if fac["매칭없음"]:
        if fac.get("사유") == "지원 지역 밖":
            print("  지원 지역(중구·관악구) 밖이라 주변 정보를 제공하지 않습니다")
        else:
            fallback = {"시설불필요": "시설이 필요 없는 운동이에요",
                        "집": "집에서도 할 수 있어요"}.get(fac["대체처리"])
            print(f"  {fallback or '주변 시설 정보를 제공하지 않는 종목입니다'} (S4-b)")
    else:
        for res in fac["예약"][:2]:
            count = f" · 예약 {res['예약건수']}건" if res["예약건수"] > 1 else ""
            print(f"  예약  {res['장소명']} ({res['유무료']}){count}")
        for near in fac["주변"][:3]:
            dist = f"{near['거리m']}m" if near["거리m"] is not None else "-"
            print(f"  시설  {dist:>7}  {near['시설명']} [{near['세부유형']}]")
        if fac["확장"]:
            print("        (2km 안에 3곳이 안 되어 구 전체에서 찾았습니다)")
        access = fac["접근성"]
        if access.get("지하철"):
            sub = access["지하철"]
            print(f"  교통  {sub['이름']} {sub['거리m']}m · 버스 {access['버스']['이름']} "
                  f"{access['버스']['거리m']}m")
        if fac["대체처리"] == "시설불필요":
            print("        ↳ 시설이 꼭 필요한 운동은 아니에요")

    # 혼잡도
    hour = slot_to_hour(payload.get("운동시간대"))
    if district and hour is not None:
        crowd = get_crowding(district, "평일", hour)
        if crowd:
            print(f"\n[혼잡도] {crowd['문구']}")


if __name__ == "__main__":
    run("D1 · 34세 남 · 저녁 헬스 · 무릎 불편 · 서울시청(중구)",
        {"나이": 34, "성별": "남", "키": 175, "몸무게": 75, "규칙적참여": True,
         "운동빈도": "일주일에 3번", "운동요일": "평일", "운동시간대": "저녁(18-22시)",
         "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다",
         "체력자가평가": {"근력": 3, "근지구력": 2, "순발력": 3, "유연성": 2},
         "자주해온운동": ["보디빌딩(헬스)"], "불편부위": ["무릎"]},
        37.5663, 126.9779)

    run("D2 · 72세 여 · 매일 오전 걷기 · 체력 낮음 · 서울대입구(관악구)",
        {"나이": 72, "성별": "여", "키": 155, "몸무게": 52, "규칙적참여": True,
         "운동빈도": "일주일에 7번(매일)", "운동요일": "평일/휴일",
         "운동시간대": "오전(8-12시)", "운동목적": "건강 유지 및 체력증진",
         "운동강도": "저", "체력인지": "전혀 체력이 좋지 않은 편이다",
         "체력자가평가": {"근력": 1, "하지근기능": 1, "협응력평형": 1, "유연성": 2}},
        37.4813, 126.9527)

    run("D3 · 40세 남 · 휴일 야외 구기 · 비 오는 날 · 관악구",
        {"나이": 40, "성별": "남", "키": 175, "몸무게": 75, "규칙적참여": True,
         "운동빈도": "일주일에 1번", "운동요일": "휴일", "운동시간대": "오전(8-12시)",
         "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다",
         "체력자가평가": {"근력": 3, "근지구력": 3, "순발력": 3, "유연성": 3}},
        37.4784, 126.9516, force_rain=True)

    run("예비 · 시연 장소가 지원 밖일 때 (강남역)",
        {"나이": 34, "성별": "남", "키": 175, "몸무게": 75, "규칙적참여": True,
         "운동빈도": "일주일에 3번", "운동요일": "평일", "운동시간대": "저녁(18-22시)",
         "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다",
         "체력자가평가": {"근력": 3, "근지구력": 3, "순발력": 3, "유연성": 3}},
        37.4979, 127.0276)
