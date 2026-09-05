# -*- coding: utf-8 -*-
"""지도(S4)가 그릴 것 — 경계 폴리곤과 시설 핀.

    from geo.mapdata import pins
    pins("보디빌딩(헬스)", district="관악구", lat=37.4784, lon=126.9516)

`facility.find_facilities` 가 "어디에 있는지"를 답한다면, 이 모듈은 그것을
**지도가 바로 그릴 수 있는 형태**로 옮긴다. 새로 찾지 않는다.

지도이므로 목록 화면과 다른 점이 셋 있다.
  1. 개수가 많다 (거리순 상위 20). 목록은 5건이면 충분하지만 핀은 성기면 허전하다
  2. 예약 시설도 핀이 된다 — 단 좌표가 49% 결측이라 **없는 것은 목록에만** 남긴다
  3. 시설마다 '가는 방법'을 미리 붙인다. 핀을 누를 때마다 왕복하지 않으려는 것이다
"""
from geo.facility import JOIN, access, find_facilities

MAP_LIMIT = 20


def pins(sport, district=None, lat=None, lon=None, limit=MAP_LIMIT,
         reservable_only=False):
    """종목 하나의 지도 데이터.

    반환 키: 종목 · 핀 · 좌표없는예약 · 확장 · 매칭없음 · 대체처리 · 신뢰없음
    """
    found = find_facilities(sport, lat=lat, lon=lon, district=district, limit=limit)

    marks = []
    for item in found["예약"]:
        marks.append(_pin(item, 예약=True))
    if not reservable_only:
        for item in found["주변"]:
            marks.append(_pin(item, 예약=False))

    located = [m for m in marks if m["위도"] is not None]
    unlocated = [m for m in marks if m["위도"] is None]

    # 예약 가능한 곳이 위로. 전환 지점이기 때문이다(PRD §2 — 예약 링크가 전환 지점)
    located.sort(key=lambda m: (not m["예약"], m["거리m"] is None, m["거리m"] or 0))

    for mark in located:
        if mark["위도"] is not None:
            mark["접근성"] = access(mark["위도"], mark["경도"])

    return {
        "종목": sport,
        "핀": located[:limit],
        "좌표없는예약": unlocated,
        "확장": found["확장"],
        "매칭없음": found["매칭없음"] and not located and not unlocated,
        "대체처리": found.get("대체처리") or "",
        "사유": found.get("사유"),
        "확인필요": found.get("확인필요", False),
        "매핑없음": sport not in JOIN,
    }


def _pin(item, 예약):
    """예약 행과 시설 행은 컬럼이 다르다. 지도는 한 가지 모양만 안다."""
    if 예약:
        return {
            "시설명": item["장소명"], "예약": True,
            "업종": item["서비스명"], "세부유형": item["세부종목"],
            "자치구": item["자치구"], "주소": None, "전화번호": None,
            "위도": item["위도"], "경도": item["경도"], "거리m": item["거리m"],
            "예약URL": item["예약URL"], "유무료": item["유무료"],
            "예약건수": item.get("예약건수", 1),
            "지도": f"https://map.naver.com/p/search/{item['장소명']}",
        }
    return {
        "시설명": item["시설명"], "예약": False,
        "업종": item["업종"], "세부유형": item["세부유형"],
        "자치구": item["자치구"], "주소": item["주소"], "전화번호": item["전화번호"],
        "위도": item["위도"], "경도": item["경도"], "거리m": item["거리m"],
        "예약URL": None, "유무료": None, "예약건수": 0,
        "지도": item["지도"],
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    for sport in ("보디빌딩(헬스)", "테니스+정구", "걷기(속보 포함)"):
        out = pins(sport, district="관악구", lat=37.4784, lon=126.9516)
        head = out["핀"][0]["시설명"] if out["핀"] else "—"
        print(f"{sport:20} 핀 {len(out['핀']):>3}  좌표없는예약 {len(out['좌표없는예약']):>2}  "
              f"대체처리 {out['대체처리'] or '—':6} 최근접 {head}")
