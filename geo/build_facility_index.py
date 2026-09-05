# -*- coding: utf-8 -*-
"""geo/ 원본 CSV → 런타임 인덱스 (geo/data/).

원본은 손대지 않는다. 런타임이 매번 정제할 필요가 없도록 한 번만 정리해 둔다.

    python geo/build_facility_index.py

하는 일:
  - 좌표가 없거나 범위를 벗어난 행 제거 (예약 시설은 좌표 없이도 남긴다 — §예약)
  - 위도/경도를 float 로 캐스팅. **원본에서 경도·위도 순서가 파일마다 다르다**
  - 예약 URL 의 &amp; 언이스케이프 (그대로 두면 링크가 깨진다)
  - 생활인구 시간대 요약을 혼잡도 조회용으로 정리
"""
import csv
import io
import os
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")

# 서울 대략 경계. 좌표가 뒤집힌 행을 걸러내는 용도
LAT_RANGE = (37.0, 37.8)
LON_RANGE = (126.6, 127.3)


def _read(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(name, rows, fields):
    os.makedirs(OUT, exist_ok=True)
    with io.open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
    print(f"  {name:24} {len(rows):>5}행")


def _coords(row, lat_key="위도", lon_key="경도"):
    """(lat, lon) 또는 None. 범위를 벗어나면 버린다."""
    try:
        lat, lon = float(row[lat_key]), float(row[lon_key])
    except (TypeError, ValueError, KeyError):
        return None
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        return None
    return lat, lon


def build_facilities():
    rows, dropped = [], 0
    for row in _read("중구관악구_체육시설.csv"):
        pos = _coords(row)
        if pos is None:
            dropped += 1
            continue
        rows.append({"시설명": row["시설명"], "업종": row["업종"], "세부유형": row["세부유형"],
                     "자치구": row["자치구"], "주소": row["주소"], "전화번호": row["전화번호"],
                     "위도": pos[0], "경도": pos[1]})
    if dropped:
        print(f"  (체육시설 좌표 불량 {dropped}행 제외)")
    _write("facilities.csv", rows,
           ["시설명", "업종", "세부유형", "자치구", "주소", "전화번호", "위도", "경도"])
    return rows


def build_reservations():
    """예약 시설은 **좌표가 없어도 남긴다.**

    57건 중 28건에 좌표가 없는데, 이들을 버리면 예약 기능 자체가 반토막 난다.
    좌표 없는 항목은 거리 표기를 생략하고 '예약 가능' 목록에만 넣는다.
    """
    rows = []
    for row in _read("중구관악구_예약가능시설.csv"):
        pos = _coords(row)
        rows.append({"서비스명": row["서비스명"], "세부종목": row["세부종목"],
                     "접수상태": row["접수상태"], "유무료": row["유무료"],
                     "장소명": row["장소명"], "자치구": row["자치구"],
                     "예약URL": unescape(row["예약URL"] or ""),
                     "위도": pos[0] if pos else "", "경도": pos[1] if pos else ""})
    no_pos = sum(1 for r in rows if r["위도"] == "")
    print(f"  (예약시설 좌표 없음 {no_pos}행 — 버리지 않고 거리 없이 노출)")
    _write("reservations.csv", rows,
           ["서비스명", "세부종목", "접수상태", "유무료", "장소명", "자치구",
            "예약URL", "위도", "경도"])
    return rows


def build_transit():
    subway = []
    for row in _read("중구관악구_지하철역.csv"):
        pos = _coords(row)
        if pos:
            subway.append({"이름": row["역사명"], "노선": row["노선명"],
                           "위도": pos[0], "경도": pos[1]})
    _write("subway.csv", subway, ["이름", "노선", "위도", "경도"])

    bus = []
    for row in _read("중구관악구_버스정류소.csv"):
        pos = _coords(row)
        if pos:
            bus.append({"이름": row["정류소명"], "자치구": row["자치구"],
                        "위도": pos[0], "경도": pos[1]})
    _write("bus.csv", bus, ["이름", "자치구", "위도", "경도"])

    parking = []
    for row in _read("03_주차장_중구관악구.csv"):
        pos = _coords(row)
        if pos:
            parking.append({"이름": row["주차장명"], "구분": row["구분"],
                            "자치구": row["자치구"], "요금정보": row["요금정보"],
                            "장애인주차구역": row["장애인주차구역"],
                            "위도": pos[0], "경도": pos[1]})
    _write("parking.csv", parking,
           ["이름", "구분", "자치구", "요금정보", "장애인주차구역", "위도", "경도"])


def build_crowding():
    rows = []
    for row in _read("중구관악구_생활인구_시간대요약.csv"):
        rows.append({"자치구": row["자치구"], "요일유형": row["요일유형"],
                     "시간대": int(row["시간대"]),
                     "평균생활인구수": round(float(row["평균생활인구수"]))})
    rows.sort(key=lambda r: (r["자치구"], r["요일유형"], r["시간대"]))
    _write("crowding.csv", rows, ["자치구", "요일유형", "시간대", "평균생활인구수"])


if __name__ == "__main__":
    print("geo/data/ 생성")
    build_facilities()
    build_reservations()
    build_transit()
    build_crowding()
    print("완료 — 런타임은 geo/data/ 만 읽는다")
