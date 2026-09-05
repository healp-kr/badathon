# -*- coding: utf-8 -*-
"""종목 → 주변 실제 시설.

    from geo.facility import find_facilities
    find_facilities("보디빌딩(헬스)", lat=37.4784, lon=126.9516, district="관악구")

`serve()` 의 `시설검색조건` 이 "무엇을 찾을지"를 말한다면, 이 모듈은 "어디에 있는지"를 답한다.
사이의 분류 체계 차이는 `geo/data/sport_facility_join.csv` 가 메운다.

반경 2km 로 먼저 찾고, 3건 미만이면 자치구 전체로 넓힌다(`확장=True`).
결과가 없으면 지우지 않고 `대체처리` 를 돌려준다 — 화면은 빈 목록 대신 그것을 보여준다.
"""
import csv
import io
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

DEFAULT_RADIUS_M = 2000
MIN_RESULTS = 3


def _load(name):
    with io.open(os.path.join(DATA, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _floatify(rows, *keys):
    out = []
    for row in rows:
        try:
            for key in keys:
                row[key] = float(row[key])
        except (TypeError, ValueError):
            continue
        out.append(row)
    return out


FACILITIES = _floatify(_load("facilities.csv"), "위도", "경도")
RESERVATIONS = _load("reservations.csv")
SUBWAY = _floatify(_load("subway.csv"), "위도", "경도")
BUS = _floatify(_load("bus.csv"), "위도", "경도")
PARKING = _floatify(_load("parking.csv"), "위도", "경도")

JOIN = {}
for row in _load("sport_facility_join.csv"):
    JOIN[row["종목"]] = {
        "세부유형": set(filter(None, row["시설_세부유형"].split("|"))),
        "업종": set(filter(None, row["시설_업종"].split("|"))),
        "예약": set(filter(None, row["예약_세부종목"].split("|"))),
        "대체처리": row["대체처리"],
        "확인필요": row["확인필요"] == "Y",
    }


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_facilities(sport, lat=None, lon=None, district=None,
                    radius_m=DEFAULT_RADIUS_M, limit=5):
    spec = JOIN.get(sport)
    if spec is None:
        return _empty(sport, "", "매핑에 없는 종목")
    if district is None:
        # 지원 지역 밖에서 굳이 먼 시설을 끌어오지 않는다.
        # "두 곳에서만 주변 정보를 제공한다"는 약속과 어긋난다
        return _empty(sport, spec["대체처리"], "지원 지역 밖")

    reservations = _reservations(spec, district, lat, lon)
    nearby, expanded = _nearby(spec, district, lat, lon, radius_m, limit)

    if not reservations and not nearby:
        return _empty(sport, spec["대체처리"], "주변에 등록된 시설이 없음",
                      access=_access(lat, lon))

    anchor = nearby[0] if nearby else None
    access_lat = anchor["위도"] if anchor else lat
    access_lon = anchor["경도"] if anchor else lon

    return {
        "종목": sport,
        "예약": reservations,
        "주변": nearby,
        "접근성": _access(access_lat, access_lon),
        "확장": expanded,
        "매칭없음": False,
        # 시설이 있어도 함께 안내한다 — 걷기는 간이운동장이 잡혀도 '시설이 필요 없는 운동'이다
        "대체처리": spec["대체처리"],
        "확인필요": spec["확인필요"],
    }


def _empty(sport, fallback, reason, access=None):
    return {"종목": sport, "예약": [], "주변": [], "접근성": access or {},
            "확장": False, "매칭없음": True, "대체처리": fallback, "사유": reason,
            "확인필요": bool(JOIN.get(sport, {}).get("확인필요"))}


def _reservations(spec, district, lat, lon):
    if not spec["예약"]:
        return []
    out = []
    for row in RESERVATIONS:
        if row["세부종목"] not in spec["예약"]:
            continue
        if district and row["자치구"] != district:
            continue
        if row["접수상태"] != "접수중":
            continue          # 마감·종료된 것을 보여줄 이유가 없다
        item = {"장소명": row["장소명"], "서비스명": row["서비스명"],
                "세부종목": row["세부종목"], "유무료": row["유무료"],
                "예약URL": row["예약URL"], "자치구": row["자치구"],
                "위도": None, "경도": None, "거리m": None}
        # 좌표 결측 49% — 없는 것은 핀 없이 목록에만 (PRD §9-3)
        if row["위도"]:
            try:
                item["위도"], item["경도"] = float(row["위도"]), float(row["경도"])
            except ValueError:
                pass
        if lat is not None and item["위도"] is not None:
            item["거리m"] = round(haversine_m(lat, lon, item["위도"], item["경도"]))
        out.append(item)
    out.sort(key=lambda i: (i["거리m"] is None, i["거리m"] or 0))
    return _dedupe_by_place(out)


def _dedupe_by_place(rows):
    """같은 장소의 코트·시간대가 여러 건으로 들어온다(장충테니스장 등).
    장소 단위로 접어 보여주고 예약 가능 건수만 알린다."""
    merged = {}
    for row in rows:
        key = row["장소명"]
        if key in merged:
            merged[key]["예약건수"] += 1
            continue
        merged[key] = {**row, "예약건수": 1}
    return list(merged.values())


def _match(row, spec):
    return row["세부유형"] in spec["세부유형"] or row["업종"] in spec["업종"]


def _nearby(spec, district, lat, lon, radius_m, limit):
    pool = [r for r in FACILITIES if _match(r, spec)]
    if district:
        pool = [r for r in pool if r["자치구"] == district]
    if not pool:
        return [], False

    if lat is None or lon is None:
        return [_item(r, None) for r in pool[:limit]], False

    scored = sorted(((haversine_m(lat, lon, r["위도"], r["경도"]), r) for r in pool),
                    key=lambda t: t[0])
    within = [(d, r) for d, r in scored if d <= radius_m]
    expanded = False
    if len(within) < MIN_RESULTS:
        within, expanded = scored, True      # 자치구 전체로 확장
    return [_item(r, d) for d, r in within[:limit]], expanded


def _item(row, distance):
    return {"시설명": row["시설명"], "업종": row["업종"], "세부유형": row["세부유형"],
            "자치구": row["자치구"], "주소": row["주소"], "전화번호": row["전화번호"],
            "위도": row["위도"], "경도": row["경도"],
            "거리m": None if distance is None else round(distance),
            "지도": _map_link(row)}


def _map_link(row):
    """지도 타일을 그리지 않는다. 외부 지도 앱으로 넘긴다."""
    return f"https://map.naver.com/p/search/{row['시설명']}"


def _access(lat, lon):
    """가는 방법 — 가장 가까운 역·정류장·주차장."""
    if lat is None or lon is None:
        return {}
    out = {}
    for key, rows, label in (("지하철", SUBWAY, "이름"), ("버스", BUS, "이름"),
                             ("주차장", PARKING, "이름")):
        if not rows:
            continue
        distance, row = min(((haversine_m(lat, lon, r["위도"], r["경도"]), r) for r in rows),
                            key=lambda t: t[0])
        entry = {"이름": row[label], "거리m": round(distance)}
        if key == "지하철":
            entry["노선"] = row.get("노선")
        if key == "주차장":
            entry["장애인구역"] = row.get("장애인주차구역") == "Y"
            entry["요금"] = row.get("요금정보")
        out[key] = entry
    return out


def fallback_of(sport):
    """'시설불필요' · '집' · ''. 시설을 쓰지 않는 종목인지 화면이 미리 알아야 한다."""
    return (JOIN.get(sport) or {}).get("대체처리", "")


def access(lat, lon):
    """가는 방법 — 시설 한 곳 기준. 지도의 시설 상세 카드(M4)가 쓴다."""
    return _access(lat, lon)


def coverage_report():
    """어느 종목이 실제로 시설과 이어지는지 — S4-b 설계의 근거."""
    rows = []
    for sport, spec in JOIN.items():
        n_fac = sum(1 for r in FACILITIES if _match(r, spec))
        n_res = sum(1 for r in RESERVATIONS
                    if r["세부종목"] in spec["예약"] and r["접수상태"] == "접수중")
        rows.append((sport, n_fac, n_res, spec["대체처리"]))
    return sorted(rows, key=lambda t: -(t[1] + t[2]))


if __name__ == "__main__":
    print(f"{'종목':34} {'시설':>5} {'예약':>5}  대체처리")
    print("-" * 62)
    for sport, n_fac, n_res, fallback in coverage_report():
        print(f"{sport:34} {n_fac:>5} {n_res:>5}  {fallback}")
