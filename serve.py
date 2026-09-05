"""단일 진입점.

설문 응답 하나를 넣으면 배정·추천·시설 검색 조건까지 한 번에 돌려준다.
앱과 GIS 레이어는 이 함수만 알면 되고, 내부 구조(assignment/, recommendation/)는
몰라도 된다.

    from serve import serve
    result = serve({
        "나이": 34, "성별": "남", "키": 175, "몸무게": 72,
        "규칙적참여": True,
        "운동빈도": "일주일에 3번", "운동요일": "평일",
        "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
        "운동강도": "중", "체력인지": "보통이다",
        "자주해온운동": ["보디빌딩(헬스)"], "관심운동": ["배드민턴"],
        "체력자가평가": {"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
        "불편부위": ["무릎"],
    })

입출력 계약은 `인터페이스_명세.md` 가 정본이다.
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "assignment"))
sys.path.insert(0, str(ROOT / "recommendation"))

from assign import AssignmentError, assign_fitness, assign_preference, route  # noqa: E402
from recommend import recommend  # noqa: E402

API_VERSION = "1.1.0"

# 설문 문항 → 내부 필드
PREFERENCE_ITEMS = ["운동빈도", "운동요일", "운동시간대", "운동목적", "운동강도", "체력인지"]
REQUIRED = ["나이", "성별"]


class RequestError(ValueError):
    """입력이 계약을 벗어남. 4xx 로 응답할 성질의 오류."""


def serve(payload, request_id=None, top_n=None):
    """설문 응답 → 배정·추천.

    top_n : 갈래별 후보 개수. 기본은 규칙 파일의 값(3)이다.
            **표현 계층이 날씨로 재정렬할 계획이면 넉넉히(예: 6) 받아야 한다** —
            3개만 받으면 끌어올릴 실내 종목이 애초에 목록에 없다.
    """
    _validate(payload)

    age = payload["나이"]
    sex = payload["성별"]
    regular = bool(payload.get("규칙적참여", True))

    routing = route(age, sex, regular)

    preference = None
    if routing["preference_segment"]:
        answers = {k: payload.get(k) for k in PREFERENCE_ITEMS if payload.get(k) is not None}
        if answers:
            preference = assign_preference(answers, routing["preference_segment"])

    fitness = None
    if routing["fitness_group"]:
        levels = payload.get("체력자가평가") or {}
        height, weight = payload.get("키"), payload.get("몸무게")
        if levels or (height and weight):
            from assign import age_to_band
            fitness = assign_fitness(levels, routing["fitness_group"],
                                     height_cm=height, weight_kg=weight,
                                     age_band=age_to_band(age))

    result = recommend(
        preference_result=preference,
        fitness_result=fitness,
        age=age,
        discomfort_areas=payload.get("불편부위"),
        played_sports=payload.get("자주해온운동"),
        interested_sports=payload.get("관심운동"),
        survey={k: payload.get(k) for k in ("운동목적", "운동시간대", "운동강도")},
        top_n=top_n,
    )

    return {
        "request_id": request_id or str(uuid.uuid4()),
        "생성시각": datetime.now(timezone.utc).isoformat(),
        "api_version": API_VERSION,
        "model_version": model_fingerprint(),
        "라우팅": routing,
        "선호유형": result["선호유형"],
        "체력유형": result["체력유형"],
        "기반활동": result["기반활동"],
        "익숙한운동": result["익숙한운동"],
        "새로운운동": result["새로운운동"],
        "제외종목": result["제외종목"],
        "처방": result["처방"],
        "보완운동": result["보완운동"],
        "시설검색조건": _facility_requests(result),
        "안내": result["안내"],
        "면책": result["면책"],
    }


def _validate(payload):
    if not isinstance(payload, dict):
        raise RequestError("payload 는 dict 여야 한다")

    missing = [k for k in REQUIRED if payload.get(k) is None]
    if missing:
        raise RequestError(f"필수 항목 누락: {', '.join(missing)}")

    try:
        route(payload["나이"], payload["성별"], bool(payload.get("규칙적참여", True)))
    except AssignmentError as exc:
        raise RequestError(str(exc)) from exc

    for key in ("키", "몸무게"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            raise RequestError(f"{key}는 양수여야 한다: {value!r}")

    levels = payload.get("체력자가평가")
    if levels is not None:
        if not isinstance(levels, dict):
            raise RequestError("체력자가평가는 dict 여야 한다")
        for item, value in levels.items():
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise RequestError(f"체력자가평가 '{item}' 는 1~5 정수여야 한다: {value!r}")

    for key in ("관심운동", "자주해온운동", "불편부위"):
        value = payload.get(key)
        if value is not None and not isinstance(value, list):
            raise RequestError(f"{key}는 리스트여야 한다")


def _facility_requests(result):
    """GIS 레이어가 그대로 받아 쓸 검색 조건.

    여기서 주변 시설을 찾지 않는다 — 무엇을 찾아야 하는지만 정한다.
    """
    requests = []
    seen = set()
    for bucket, items in (("기반활동", result["기반활동"]),
                          ("익숙한운동", result["익숙한운동"]),
                          ("새로운운동", result["새로운운동"])):
        for item in items or []:
            sport = item["종목"]
            if sport in seen:
                continue
            seen.add(sport)
            facility = item.get("시설") or {}
            requests.append({
                "종목": sport,
                "갈래": bucket,
                "시설유형": [t["이름"] for t in facility.get("시설유형", [])],
                "시설대분류": [g["이름"] for g in facility.get("시설대분류", [])],
                "시설불필요_비율": facility.get("시설불필요_비율"),
                "신뢰도": facility.get("신뢰도"),
            })
    return requests


def model_fingerprint():
    """파라미터 파일의 해시. 어떤 모델이 이 결과를 냈는지 로그로 추적하기 위한 것."""
    import hashlib

    files = [
        ROOT / "assignment" / "params" / "preference_model.json",
        ROOT / "assignment" / "params" / "fitness_model.json",
        ROOT / "recommendation" / "data" / "rules.json",
        ROOT / "recommendation" / "data" / "preference_sport_matrix.csv",
        ROOT / "recommendation" / "data" / "sport_master.csv",
        ROOT / "recommendation" / "data" / "sport_facility_map.csv",
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()[:12]


if __name__ == "__main__":
    import json

    sys.stdout.reconfigure(encoding="utf-8")
    out = serve({
        "나이": 34, "성별": "남", "키": 175, "몸무게": 82,
        "규칙적참여": True,
        "운동빈도": "일주일에 3번", "운동요일": "평일",
        "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
        "운동강도": "중", "체력인지": "보통이다",
        "자주해온운동": ["보디빌딩(헬스)"], "관심운동": ["배드민턴", "등산"],
        "체력자가평가": {"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
        "불편부위": ["무릎"],
    })
    print(json.dumps(out, ensure_ascii=False, indent=1)[:1500])
