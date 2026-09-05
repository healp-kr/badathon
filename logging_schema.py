"""로그 스키마 (D1).

**v1부터 남겨야 한다. 소급 수집이 안 된다.**

이 로그가 없으면 두 가지를 영원히 모른다.
  - 체력 자가평가 신뢰도 r — 지금 설계에서 가장 불확실한 값 (정확도 50% 내외 추정)
  - 추천 가중치가 맞는지 — w₁ 결합비, Lift 가중, 설문 보정값 전부 근거 없는 조정값이다

모든 이벤트는 공통 필드를 갖는다. `model_version` 을 반드시 남겨야 나중에
"어느 모델이 낸 결과였나"를 되짚을 수 있다.

    from serve import serve
    from logging_schema import events_for_request

    result = serve(payload)
    for event in events_for_request(payload, result, session_id="...", user_id="..."):
        sink.write(event)          # DB / 파일 / 스트림 — 저장소는 이 모듈의 관심사가 아니다
"""
import json
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0.0"

EVENT_TYPES = {
    # 온보딩 — serve() 호출 시점에 한 번씩
    "onboarding_submitted": "설문 응답 원본. 문항이 바뀌어도 원본을 남겨야 재분석이 된다",
    "assignment_made": "배정 결과. 확률·확신도까지 남긴다 — 하드 라벨만 남기면 경계 사례 분석이 불가능하다",
    "recommendation_served": "추천 목록 전체. 순위·점수·이유·제외 사유까지",
    # 노출·상호작용 — 앱에서 발생할 때마다
    "sport_impression": "종목 카드가 화면에 실제로 보인 시점",
    "sport_click": "종목 카드를 눌렀다",
    "facility_click": "그 종목의 주변 시설을 눌렀다 (GIS 레이어 연결 지점)",
    "sport_started": "실제로 하기 시작했다고 표시",
    "sport_completed": "한 회차를 마쳤다고 표시",
    "sport_dismissed": "관심 없다고 치웠다 — 음성 신호. 이게 없으면 클릭률만으로 편향된다",
    # 검증 루프
    "self_measure_submitted": "간이 측정 결과. 자가평가와 짝지어 r 을 추정하는 유일한 경로",
    "feedback_submitted": "난이도·만족도 등 직접 피드백",
}

# 이 필드들은 모든 이벤트에 들어간다
COMMON_FIELDS = ["event_id", "event_type", "occurred_at", "schema_version",
                 "session_id", "user_id", "request_id", "model_version"]


def _base(event_type, session_id, user_id, request_id, model_version):
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "user_id": user_id,
        "request_id": request_id,
        "model_version": model_version,
    }


def events_for_request(payload, result, session_id, user_id=None):
    """serve() 한 번에서 나오는 이벤트 3종. 앱은 이걸 그대로 저장하면 된다."""
    request_id = result["request_id"]
    version = result["model_version"]

    def base(event_type):
        return _base(event_type, session_id, user_id, request_id, version)

    onboarding = base("onboarding_submitted")
    onboarding["payload"] = payload          # 원본 그대로. 가공하지 않는다
    onboarding["api_version"] = result["api_version"]

    assignment = base("assignment_made")
    assignment.update({
        "라우팅": result["라우팅"],
        "선호유형": result["선호유형"],
        "체력유형": result["체력유형"],
        # 경계 사례 분석용 — 확률과 확신도가 없으면 나중에 아무것도 못 한다
        "선호_확률": (result["선호유형"] or {}).get("probability"),
        "체력_확신도": (result["체력유형"] or {}).get("confidence"),
        "체력_모호": (result["체력유형"] or {}).get("ambiguous"),
        "체력_대안": (result["체력유형"] or {}).get("alternative"),
    })

    served = base("recommendation_served")
    served.update({
        "기반활동": [_item(i, "기반활동", n) for n, i in enumerate(result["기반활동"] or [])],
        "익숙한운동": [_item(i, "익숙한운동", n) for n, i in enumerate(result["익숙한운동"] or [])],
        "새로운운동": [_item(i, "새로운운동", n) for n, i in enumerate(result["새로운운동"] or [])],
        "제외종목": result["제외종목"],
        "권장강도상한": result["처방"].get("권장강도상한"),
        "보완운동": [b["축"] for b in result["보완운동"] or []],
    })

    return [onboarding, assignment, served]


def _item(item, bucket, rank):
    """추천 한 칸의 로그 표현. 나중에 클릭과 조인할 수 있게 순위·점수·이유를 남긴다."""
    return {
        "종목": item["종목"],
        "갈래": bucket,
        "순위": rank + 1,
        "점수": item.get("점수"),
        "선호점수비율": item.get("선호점수비율"),
        "Lift": item.get("Lift"),
        "강도": item.get("강도"),
        "이유": item.get("이유"),
        "맞춤이유": item.get("맞춤이유"),
    }


def interaction_event(event_type, session_id, request_id, model_version,
                      sport, bucket=None, rank=None, user_id=None, extra=None):
    """노출·클릭·시작·완료·해제. request_id 로 추천 이벤트와 조인한다."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"알 수 없는 이벤트: {event_type}")
    event = _base(event_type, session_id, user_id, request_id, model_version)
    event.update({"종목": sport, "갈래": bucket, "순위": rank})
    if extra:
        event.update(extra)
    return event


def self_measure_event(session_id, request_id, model_version, measures,
                       self_rating=None, user_id=None):
    """r 검증 루프.

    measures    : 실제 측정값 {"의자에앉았다일어서기": 14, "앉아윗몸앞으로굽히기": 8.5}
    self_rating : 같은 사용자의 자가평가 {"하지근기능": 3, "유연성": 2}

    이 둘을 짝지어야 자가평가 신뢰도를 추정할 수 있다.
    측정만 받고 자가평가를 안 남기면 아무 소용이 없다.
    """
    event = _base("self_measure_submitted", session_id, user_id, request_id, model_version)
    event.update({"측정값": measures, "자가평가": self_rating})
    return event


def describe():
    """스키마 요약. 문서와 코드가 어긋나지 않게 여기서 뽑아 쓴다."""
    lines = [f"로그 스키마 v{SCHEMA_VERSION}", "",
             "공통 필드: " + ", ".join(COMMON_FIELDS), "", "이벤트:"]
    lines += [f"  {name:26s} {desc}" for name, desc in EVENT_TYPES.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    from serve import serve

    print(describe())
    print()

    payload = {
        "나이": 34, "성별": "남", "키": 175, "몸무게": 82, "규칙적참여": True,
        "운동빈도": "일주일에 3번", "운동요일": "평일", "운동시간대": "저녁(18-22시)",
        "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다",
        "자주해온운동": ["보디빌딩(헬스)"], "관심운동": ["배드민턴"],
        "체력자가평가": {"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
        "불편부위": ["무릎"],
    }
    result = serve(payload)
    events = events_for_request(payload, result, session_id="sess-demo", user_id="u-1")

    print(f"serve() 1회 → 이벤트 {len(events)}건")
    for event in events:
        print(f"  {event['event_type']:26s} {len(json.dumps(event, ensure_ascii=False)):>6}B")

    click = interaction_event("sport_click", "sess-demo", result["request_id"],
                              result["model_version"], sport="수영+아쿠아로빅, 수중발레+수구",
                              bucket="새로운운동", rank=1, user_id="u-1")
    print(f"\n클릭 이벤트 예시:\n{json.dumps(click, ensure_ascii=False, indent=1)}")
