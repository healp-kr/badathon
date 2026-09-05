"""단일 진입점 검증.

실행: python test_serve.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from logging_schema import EVENT_TYPES, events_for_request, interaction_event  # noqa: E402
from serve import RequestError, serve  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


FULL = {
    "나이": 34, "성별": "남", "키": 175, "몸무게": 82, "규칙적참여": True,
    "운동빈도": "일주일에 3번", "운동요일": "평일", "운동시간대": "저녁(18-22시)",
    "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다",
    "자주해온운동": ["보디빌딩(헬스)"], "관심운동": ["배드민턴", "등산"],
    "체력자가평가": {"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
    "불편부위": ["무릎"],
}

REQUIRED_KEYS = ["request_id", "생성시각", "api_version", "model_version", "라우팅",
                 "선호유형", "체력유형", "기반활동", "익숙한운동", "새로운운동",
                 "제외종목", "처방", "보완운동", "시설검색조건", "안내", "면책"]


def test_contract():
    print("\n1. 출력 계약")
    out = serve(FULL)
    check("모든 키가 존재", all(k in out for k in REQUIRED_KEYS),
          f"{len(out)}개 키")
    check("선호·체력 모두 배정", out["선호유형"] and out["체력유형"],
          f"{out['선호유형']['name']} × {out['체력유형']['segment']}")
    check("기반활동은 걷기", out["기반활동"][0]["종목"] == "걷기(속보 포함)")
    check("걷기는 추천 칸에 없음",
          all(i["종목"] != "걷기(속보 포함)"
              for i in out["익숙한운동"] + out["새로운운동"]))
    check("시설 검색 조건이 종목마다 붙음",
          all(r["시설유형"] or r["신뢰도"] == "없음" for r in out["시설검색조건"]),
          f"{len(out['시설검색조건'])}종목")
    check("불편 부위가 반영됨",
          any("무릎" in e["사유"] for e in out["제외종목"]))
    check("model_version 이 12자리 해시", len(out["model_version"]) == 12,
          out["model_version"])


def test_edge_cases():
    print("\n2. 경계·부분 응답")
    kid = serve({**FULL, "나이": 16})
    check("19세 미만은 체력 미배정",
          kid["체력유형"] is None and kid["선호유형"] is not None,
          kid["라우팅"]["skip_reason"]["fitness"])

    elder = serve({**FULL, "나이": 70,
                   "체력자가평가": {"근력": 2, "하지근기능": 2, "협응력평형": 3, "유연성": 3}})
    check("70세는 노인 트랙",
          elder["라우팅"]["fitness_group"] == "노인 남",
          f"{elder['선호유형']['name']} × {elder['체력유형']['segment']}")

    boundary = serve({**FULL, "나이": 62})
    check("62세는 선호=노인 / 체력=성인 / 표시=노인",
          boundary["라우팅"]["preference_segment"] == "노인_남성"
          and boundary["라우팅"]["fitness_group"] == "성인 남"
          and boundary["라우팅"]["display_age_group"] == "노인")

    non = serve({k: v for k, v in FULL.items()
                 if k not in ("운동빈도", "운동요일", "운동시간대", "운동목적",
                              "운동강도", "체력인지")} | {"규칙적참여": False})
    check("비참여자는 관심 종목만으로 추천",
          non["선호유형"] is None and non["익숙한운동"],
          f"{[i['종목'] for i in non['익숙한운동']]}")

    partial = serve({**FULL, "운동목적": None, "운동강도": None, "체력인지": None})
    check("일부 문항 결측도 배정됨", partial["선호유형"] is not None,
          f"{partial['선호유형']['name']} p={partial['선호유형']['probability']}")

    minimal = serve({"나이": 40, "성별": "여"})
    check("나이·성별만으로도 죽지 않음", minimal["라우팅"] is not None,
          f"선호={minimal['선호유형'] is not None}, 체력={minimal['체력유형'] is not None}")


def test_validation():
    print("\n3. 잘못된 입력")
    bad_cases = [
        ("필수 누락", {"성별": "남"}),
        ("성별 오류", {"나이": 30, "성별": "M"}),
        ("나이 범위", {"나이": -5, "성별": "남"}),
        ("몸무게 음수", {"나이": 30, "성별": "남", "몸무게": -1}),
        ("자가평가 범위", {"나이": 30, "성별": "남", "체력자가평가": {"근력": 9}}),
        ("리스트 아님", {"나이": 30, "성별": "남", "관심운동": "등산"}),
        ("dict 아님", ["나이"]),
    ]
    for name, payload in bad_cases:
        try:
            serve(payload)
            check(f"{name} → 거부", False)
        except RequestError as exc:
            check(f"{name} → RequestError", True, str(exc)[:44])
        except Exception as exc:  # noqa: BLE001
            check(f"{name} → RequestError 여야 함", False, f"{type(exc).__name__}: {exc}")


def test_logging():
    print("\n4. 로그 스키마")
    out = serve(FULL)
    events = events_for_request(FULL, out, session_id="s1", user_id="u1")
    check("serve 1회 → 이벤트 3건", len(events) == 3,
          ", ".join(e["event_type"] for e in events))
    check("모든 이벤트가 정의된 타입",
          all(e["event_type"] in EVENT_TYPES for e in events))
    check("request_id 로 조인 가능",
          all(e["request_id"] == out["request_id"] for e in events))
    check("model_version 이 이벤트에 박힘",
          all(e["model_version"] == out["model_version"] for e in events))

    served = next(e for e in events if e["event_type"] == "recommendation_served")
    check("추천 로그에 순위·점수·이유가 남음",
          all("순위" in i and "점수" in i and "이유" in i for i in served["새로운운동"]))

    made = next(e for e in events if e["event_type"] == "assignment_made")
    check("배정 로그에 확률·확신도가 남음",
          made["선호_확률"] is not None and made["체력_확신도"] is not None,
          f"p={made['선호_확률']} conf={made['체력_확신도']}")

    onboard = next(e for e in events if e["event_type"] == "onboarding_submitted")
    check("응답 원본이 가공 없이 남음", onboard["payload"] == FULL)

    click = interaction_event("sport_click", "s1", out["request_id"],
                              out["model_version"], sport="등산", bucket="새로운운동", rank=2)
    check("상호작용 이벤트 생성", click["종목"] == "등산" and click["순위"] == 2)

    try:
        interaction_event("sport_hovered", "s1", "r", "v", sport="등산")
        check("미정의 이벤트 거부", False)
    except ValueError:
        check("미정의 이벤트는 거부", True)


def test_determinism():
    print("\n5. 재현성")
    a, b = serve(FULL), serve(FULL)
    same = ([i["종목"] for i in a["새로운운동"]] == [i["종목"] for i in b["새로운운동"]]
            and a["선호유형"]["class_id"] == b["선호유형"]["class_id"])
    check("같은 입력 → 같은 결과", same)
    check("request_id 는 매번 다름", a["request_id"] != b["request_id"])
    check("model_version 은 동일", a["model_version"] == b["model_version"])


if __name__ == "__main__":
    test_contract()
    test_edge_cases()
    test_validation()
    test_logging()
    test_determinism()
    print(f"\n{'=' * 60}\n통과 {len(PASS)} / 실패 {len(FAIL)}")
    if FAIL:
        print("실패:", *FAIL, sep="\n  - ")
        sys.exit(1)
