# -*- coding: utf-8 -*-
"""지도·시설·혼잡도 층의 골든 파일.

`make_golden.py` 가 배정·추천을 얼린다면 이쪽은 그 다음 층을 얼린다.
`make_golden.py` 를 돌리면 이 모듈도 함께 실행된다.

여기서 노리는 함정은 배정 층과 다르다.

  · **좌표 순서** — GeoJSON 은 (경도, 위도)이고 공개 함수는 (위도, 경도)를 받는다.
    프로젝트 안에서 반복해서 나온 실수라 경계 안팎을 촘촘히 깐다.
  · **거리 반올림** — `round(distance)` 도 은행가 반올림이다.
  · **정렬 안정성** — 거리로만 정렬하므로 같은 거리의 시설 순서가 파이썬의
    안정 정렬을 그대로 따라야 한다. 실제로 좌표가 같은 시설이 있다.
  · **결측** — 예약 시설의 좌표가 49% 비어 있다. 빈 문자열이지 NaN 이 아니다.
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.locate import (boundary_features, district_center, is_supported,  # noqa: E402
                        list_districts, resolve_district)
from geo.crowding import get_crowding, slot_to_hour                        # noqa: E402
from geo.facility import JOIN, access, find_facilities                     # noqa: E402
from geo.mapdata import pins                                               # noqa: E402

OUT_DIR = os.path.join(ROOT, "web", "ui", "tests", "golden")

# 판정이 갈리는 지점을 노린다 — 경계 안, 경계 밖, 그리고 동명이구(부산 중구)
COORDS = [
    ("서울시청 (중구)", 37.5663, 126.9779),
    ("명동 (중구)", 37.5636, 126.9850),
    ("서울역 (중구 경계 근처)", 37.5547, 126.9707),
    ("서울대입구역 (관악구)", 37.4813, 126.9527),
    ("관악구청", 37.4784, 126.9516),
    ("낙성대 (관악구)", 37.4771, 126.9634),
    ("강남역 (지원 밖)", 37.4979, 127.0276),
    ("여의도 (지원 밖)", 37.5219, 126.9245),
    ("부산 중구 (동명이구 함정)", 35.1065, 129.0323),
    ("제주 (지원 밖)", 33.4996, 126.5312),
    ("적도 (말도 안 되는 좌표)", 0.0, 0.0),
    ("북극 (범위 밖)", 89.9, 179.9),
]


def locate_cases():
    out = []
    for label, lat, lon in COORDS:
        out.append({"이름": label, "lat": lat, "lon": lon,
                    "결과": resolve_district(lat, lon)})
    # 형식 오류 경로 — 파이썬은 float() 실패를 잡아 '좌표 형식 오류' 를 돌려준다
    for label, lat, lon in [("문자열", "abc", "def"), ("None", None, None)]:
        out.append({"이름": f"형식오류 {label}", "lat": lat, "lon": lon,
                    "결과": resolve_district(lat, lon)})
    return out


def crowding_cases():
    out = []
    for district in ("중구", "관악구", "없는구"):
        for daytype in ("평일", "주말", "없는요일"):
            for hour in (None, 3, 5, 7, 10, 13, 16, 19, 22, 23):
                out.append({
                    "이름": f"{district}/{daytype}/{hour}",
                    "district": district, "daytype": daytype, "hour": hour,
                    "결과": get_crowding(district, daytype, hour),
                })
    return out


def facility_cases():
    """매핑된 전 종목 × 좌표 유무 × 자치구."""
    out = []
    spots = [
        ("관악구청", "관악구", 37.4784, 126.9516),
        ("서울시청", "중구", 37.5663, 126.9779),
        ("좌표없음(관악)", "관악구", None, None),
        ("자치구없음", None, 37.4784, 126.9516),
    ]
    for sport in sorted(JOIN.keys()):
        for label, district, lat, lon in spots:
            out.append({
                "이름": f"{sport} @ {label}",
                "sport": sport, "district": district, "lat": lat, "lon": lon,
                "결과": find_facilities(sport, lat=lat, lon=lon, district=district),
            })
    # 매핑에 없는 종목
    out.append({
        "이름": "매핑없는종목 @ 관악구",
        "sport": "없는종목", "district": "관악구", "lat": 37.4784, "lon": 126.9516,
        "결과": find_facilities("없는종목", lat=37.4784, lon=126.9516, district="관악구"),
    })
    return out


def pin_cases():
    out = []
    for sport in sorted(JOIN.keys()):
        for reservable_only in (False, True):
            out.append({
                "이름": f"{sport} 예약만={reservable_only}",
                "sport": sport, "district": "관악구",
                "lat": 37.4784, "lon": 126.9516,
                "limit": 20, "reservable_only": reservable_only,
                "결과": pins(sport, district="관악구", lat=37.4784, lon=126.9516,
                            limit=20, reservable_only=reservable_only),
            })
    # 중구에서도 한 번 — 시설 분포가 다르다
    for sport in ("보디빌딩(헬스)", "테니스+정구", "걷기(속보 포함)"):
        out.append({
            "이름": f"{sport} @중구",
            "sport": sport, "district": "중구", "lat": 37.5663, "lon": 126.9779,
            "limit": 20, "reservable_only": False,
            "결과": pins(sport, district="중구", lat=37.5663, lon=126.9779,
                        limit=20, reservable_only=False),
        })
    return out


def access_cases():
    out = []
    for label, lat, lon in COORDS[:8]:
        out.append({"이름": label, "lat": lat, "lon": lon, "결과": access(lat, lon)})
    out.append({"이름": "좌표없음", "lat": None, "lon": None, "결과": access(None, None)})
    return out


def slot_cases():
    slots = ["아침/새벽(6-8시)", "오전(8-12시)", "점심(12-14시)", "오후(14-18시)",
             "저녁(18-22시)", "일정하지 않음", "없는시간대"]
    return [{"slot": s, "결과": slot_to_hour(s)} for s in slots]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "note": "지도·시설·혼잡도 층의 정답지. tools/make_golden_geo.py 가 만든다.",
        "locate": locate_cases(),
        "districts": list_districts(),
        "boundary_전체": boundary_features(),
        "boundary_중구": boundary_features("중구"),
        "center": {d: district_center(d) for d in ("중구", "관악구", "없는구")},
        "supported": {d: is_supported(d) for d in ("중구", "관악구", "없는구")},
        "crowding": crowding_cases(),
        "slot": slot_cases(),
        "facilities": facility_cases(),
        "pins": pin_cases(),
        "access": access_cases(),
    }
    path = os.path.join(OUT_DIR, "geo.json")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    counts = " · ".join(
        f"{k} {len(payload[k])}" for k in
        ("locate", "crowding", "facilities", "pins", "access"))
    print(f"geo 케이스 — {counts}")
    print(f"→ {os.path.relpath(path, ROOT)}  ({os.path.getsize(path)/1024:.0f}KB)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
