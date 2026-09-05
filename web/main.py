# -*- coding: utf-8 -*-
"""백엔드 — 프론트는 HTTP 만 안다.

    pip install fastapi uvicorn
    python -m uvicorn web.main:app --reload --port 8000

폰에서 위치 기능을 쓰려면 HTTPS 가 필요하다(localhost 는 예외).
    python -m uvicorn web.main:app --host 0.0.0.0 --port 8443 \
        --ssl-keyfile key.pem --ssl-certfile cert.pem

`serve()` 를 직접 임포트하는 곳은 여기 한 곳뿐이다. 프론트는 내부 구조를 모른다.
"""
import os
import sys
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import serve as serve_module                                  # noqa: E402
from serve import serve, RequestError                          # noqa: E402
from logging_schema import events_for_request, interaction_event  # noqa: E402
from api.locate import (resolve_district, list_districts, is_supported,  # noqa: E402
                        boundary_features, district_center)
from api.context import get_context, apply_context             # noqa: E402
from geo.facility import find_facilities, fallback_of          # noqa: E402
from geo.mapdata import pins as map_pins                       # noqa: E402
from geo.crowding import get_crowding, slot_to_hour            # noqa: E402
from web.schema import build_schema, sport_catalog             # noqa: E402
from web import sink                                           # noqa: E402

CANDIDATE_N = 10     # serve() 에서 받는 후보 수. 재정렬 뒤 display_n 으로 자른다
DISPLAY_N = 3

app = FastAPI(title="바다톤 운동 추천", version=serve_module.API_VERSION)


@app.get("/api/survey-schema")
def survey_schema():
    """문항·선택지. **value 를 그대로 /api/serve 에 보낼 것.**

    선택지 문자열을 프론트에 하드코딩하면 안 된다 — 모델 범주와 한 글자만 달라도
    그 문항이 조용히 무시된다. 이 응답이 유일한 출처다.
    """
    return build_schema()


@app.get("/api/districts")
def districts():
    return {"districts": list_districts(),
            "note": "지원 지역 밖에서는 주변 정보를 제공하지 않는다"}


@app.get("/api/locate")
def locate(lat: float = Query(...), lon: float = Query(...)):
    """좌표 → 자치구. **좌표는 여기서만 받고 저장하지 않는다.**"""
    return resolve_district(lat, lon)


@app.get("/api/context")
def context(district: str = Query(...)):
    return get_context(district)


class ServeRequest(BaseModel):
    payload: dict
    district: str | None = None
    session_id: str | None = None
    user_id: str | None = None


@app.post("/api/serve")
def api_serve(body: ServeRequest):
    try:
        result = serve(body.payload, top_n=CANDIDATE_N)
    except RequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ctx = get_context(body.district) if body.district and is_supported(body.district) else None
    view = apply_context(result, ctx,
                         운동시간대=body.payload.get("운동시간대"),
                         display_n=DISPLAY_N)

    session_id = body.session_id or str(uuid.uuid4())
    for event in events_for_request(body.payload, result, session_id, body.user_id):
        sink.write(event)

    view["session_id"] = session_id
    return view


@app.get("/api/facilities")
def facilities(sport: str = Query(...), district: str | None = None,
               lat: float | None = None, lon: float | None = None):
    result = find_facilities(sport, lat=lat, lon=lon, district=district)
    return result


@app.get("/api/sports")
def sports():
    """종목 목록 + 기본 강도. 기록 화면이 강도를 하드코딩하지 않게 한다.

    달성률 공식(Σ중 + Σ고×2)이 이 강도 값을 그대로 신뢰하므로,
    `sport_master.csv` 와 어긋나면 안 된다 — 출처는 여기 하나다.
    """
    catalog = sport_catalog()
    for row in catalog:
        # 시설을 쓰지 않는 종목('시설불필요'·'집')인지 — 지도가 기본 종목을 고를 때 본다
        row["대체처리"] = fallback_of(row["종목"])
    return {"sports": catalog,
            "note": "강도는 sport_master.csv 대표값이다. 사용자가 세게 했는지 여부는 모른다"}


@app.get("/api/map/boundary")
def map_boundary(district: str | None = None):
    """자치구 경계 GeoJSON. 타일이 안 떠도 이것만은 그려진다."""
    return boundary_features(district)


@app.get("/api/map/facilities")
def map_facilities(sport: str = Query(...), district: str | None = None,
                   lat: float | None = None, lon: float | None = None,
                   limit: int = 20, reservable_only: bool = False):
    """지도용 핀 묶음. 좌표가 없는 예약 시설은 `좌표없는예약` 으로 따로 나간다."""
    if lat is None and district and is_supported(district):
        center = district_center(district)      # 위치를 못 받아도 지도는 열려야 한다
        if center:
            lat, lon = center
    result = map_pins(sport, district=district, lat=lat, lon=lon,
                      limit=max(1, min(limit, 100)), reservable_only=reservable_only)
    result["중심"] = list(district_center(district) or ()) or None
    return result


@app.get("/api/crowding")
def crowding(district: str = Query(...), daytype: str = "평일",
             hour: int | None = None, slot: str | None = None):
    if hour is None and slot:
        hour = slot_to_hour(slot)
    result = get_crowding(district, daytype, hour)
    if result is None:
        raise HTTPException(status_code=404, detail="혼잡도 데이터가 없는 지역입니다")
    return result


class EventRequest(BaseModel):
    event_type: str
    session_id: str
    request_id: str
    model_version: str
    sport: str | None = None
    bucket: str | None = None
    rank: int | None = None
    user_id: str | None = None
    extra: dict = Field(default_factory=dict)


@app.post("/api/events")
def api_events(body: EventRequest):
    """노출·클릭·해제·시작·완료. request_id 로 추천과 조인한다.

    **sport_dismissed 를 빠뜨리지 말 것.** 음성 신호가 없으면 클릭률만으로 편향된다.
    """
    try:
        event = interaction_event(
            body.event_type, body.session_id, body.request_id, body.model_version,
            sport=body.sport, bucket=body.bucket, rank=body.rank,
            user_id=body.user_id, extra=body.extra)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sink.write(event)
    return {"ok": True, "event_id": event["event_id"]}


@app.exception_handler(RequestError)
def request_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# 화면은 `web/ui` 의 빌드 결과다. 개발 중에는 Vite(5173)가 직접 내고 /api 만 이리로
# 넘어오므로, 이 마운트는 **빌드본으로 띄울 때만** 쓰인다.
#   빌드   cd web/ui && npm run build   → web/ui/dist
# dist 가 없으면 마운트하지 않는다 — API 는 그대로 살아 있어야 한다.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "dist")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
