# -*- coding: utf-8 -*-
"""좌표 → 자치구 판정.

경계 폴리곤(WGS84)에 대한 point-in-polygon 만으로 판정한다. 외부 API도 라이브러리도
쓰지 않으므로 시연 중 네트워크 장애의 영향을 받지 않는다.

    from api.locate import resolve_district, list_districts
    resolve_district(37.4784, 126.9516)   # {'district': '관악구', ...}

**경계 밖이면 '지원 밖'이다. 최근접 보정을 하지 않는다.**
전국에 '중구'는 여럿이므로, 부산에서 접속했는데 "중구입니다"가 뜨면 안 된다.

GeoJSON 좌표는 (경도, 위도) 순이다. 이 모듈의 공개 함수는 전부 (lat, lon) 을 받고
내부에서만 뒤집는다 — 순서 혼동은 이 프로젝트에서 반복적으로 나오는 함정이다.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

with open(os.path.join(_HERE, "districts.json"), encoding="utf-8") as f:
    _CONF = json.load(f)

DISTRICTS = {d["district"]: d for d in _CONF["districts"]}

with open(os.path.join(_ROOT, _CONF["boundary_geojson"]), encoding="utf-8") as f:
    _BOUNDARY = json.load(f)

_KEY = _CONF["boundary_key"]


def _rings(geometry):
    """Polygon / MultiPolygon 을 외곽 링 목록으로 편다."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Polygon":
        return [coords[0]]
    if kind == "MultiPolygon":
        return [poly[0] for poly in coords]
    return []


def _load_polygons():
    out = {}
    for feature in _BOUNDARY["features"]:
        name = feature["properties"].get(_KEY)
        if name:
            out.setdefault(name, []).extend(_rings(feature["geometry"]))
    return out


_POLYGONS = _load_polygons()


def _in_ring(lon, lat, ring):
    """Ray casting. ring 은 [[경도, 위도], ...]."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def resolve_district(lat, lon):
    """위도·경도 → 지원 자치구.

    반환: {'district': '관악구' | None, '사유': str, 'source': 'auto'}
    """
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return {"district": None, "사유": "좌표 형식 오류", "source": "auto"}

    for name, rings in _POLYGONS.items():
        if name not in DISTRICTS:
            continue  # 경계 파일에는 있으나 서비스 대상이 아닌 구
        if any(_in_ring(lon, lat, ring) for ring in rings):
            return {"district": name, "사유": "경계 내부", "source": "auto"}

    return {"district": None, "사유": "지원 지역 밖", "source": "auto"}


def list_districts():
    """지역 선택 시트가 쓸 목록."""
    return [{"district": d["district"], "center": d["center"]}
            for d in _CONF["districts"]]


def boundary_features(district=None):
    """지도 배경으로 그릴 경계 GeoJSON (FeatureCollection).

    타일이 안 떠도 이 폴리곤은 그려진다 — Leaflet 을 고른 이유가 이것이다(PRD §9-2).
    좌표는 GeoJSON 규약대로 (경도, 위도) 순서 그대로 내보낸다.
    """
    features = []
    for feature in _BOUNDARY["features"]:
        name = feature["properties"].get(_KEY)
        if name not in DISTRICTS:
            continue                       # 서비스 대상이 아닌 구는 내보내지 않는다
        if district and name != district:
            continue
        features.append({
            "type": "Feature",
            "properties": {"district": name, "center": DISTRICTS[name]["center"]},
            "geometry": feature["geometry"],
        })
    return {"type": "FeatureCollection", "features": features}


def district_center(district):
    """위치를 못 받았을 때 쓰는 대체 중심점 (lat, lon)."""
    entry = DISTRICTS.get(district)
    return tuple(entry["center"]) if entry else None


def is_supported(district):
    return district in DISTRICTS


if __name__ == "__main__":
    samples = [
        ("서울시청 (중구)", 37.5663, 126.9779),
        ("서울대입구역 (관악구)", 37.4813, 126.9527),
        ("강남역 (지원 밖)", 37.4979, 127.0276),
        ("부산 중구 (동명이구 함정)", 35.1065, 129.0323),
        ("제주", 33.4996, 126.5312),
    ]
    for label, lat, lon in samples:
        print(f"{label:28} → {resolve_district(lat, lon)}")
