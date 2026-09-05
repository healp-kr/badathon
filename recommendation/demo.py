"""추천 결과를 사람이 읽는 형태로 출력하는 데모."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "assignment"))
sys.stdout.reconfigure(encoding="utf-8")

from assign import assign_all      # noqa: E402
from recommend import recommend    # noqa: E402


def _places(item):
    """GIS 레이어에 넘길 검색 대상 시설. 여기서 실제 검색은 하지 않는다."""
    fac = item.get("시설") or {}
    types = fac.get("시설유형") or []
    if not types:
        return f"— ({fac.get('비고', '정보 없음')})"
    text = ", ".join(f"{t['이름']} {t['비율']:.0f}%" for t in types[:2])
    if fac.get("신뢰도") == "낮음":
        text += "  ※시설 응답률 낮음"
    return text


def show(title, profile, picks, discomfort=()):
    print("=" * 72)
    print(title)
    print("=" * 72)
    r = assign_all(**profile)
    out = recommend(r["preference"], r["fitness"], age=profile["age"],
                    played_sports=picks.get("자주해온"),
                    interested_sports=picks.get("관심"),
                    survey=profile.get("preference"),
                    discomfort_areas=list(discomfort))

    if out["선호유형"]:
        print(f"선호 유형  {out['선호유형']['name']} (p={out['선호유형']['probability']})")
    else:
        print("선호 유형  없음 — 규칙적 체육활동 비참여자")
    if out["체력유형"]:
        f = out["체력유형"]
        flag = " ⚠모호" if f["ambiguous"] else ""
        print(f"체력 유형  {f['segment']} (확신도 {f['confidence']}{flag})")
    print(f"권장 강도  {out['처방'].get('권장강도상한')}")
    print()

    for b in out["기반활동"] or []:
        mark = " (이미 하고 계심)" if b["이미하는중"] else ""
        print(f"■ 기반활동 — 순위에서만 분리하고 화면에는 싣지 않는다{mark}")
        print(f"    · {b['종목']} — {b['처방']}")
        print(f"      찾을 곳: {_places(b)}")

    print("■ 익숙한 운동 — 고르신 것 중 지금 하실 수 있는 것")
    for s in out["익숙한운동"] or []:
        print(f"    · {s['종목']}  — {s['이유']}")
        print(f"      찾을 곳: {_places(s)}")
    if not out["익숙한운동"]:
        print("    (없음)")

    print("■ 새로운 운동 — 비슷한 분들이 많이 하시는 것")
    for s in out["새로운운동"] or []:
        fit = f"  [{' · '.join(s['맞춤이유'])}]" if s.get("맞춤이유") else ""
        print(f"    · {s['종목']} ({s['점수']:.0f}점)  — {s['이유']}{fit}")
        print(f"      찾을 곳: {_places(s)}")
    if not out["새로운운동"]:
        print("    (없음)")

    if out["제외종목"]:
        print("■ 제외")
        for e in out["제외종목"][:4]:
            print(f"    · {e['종목']}: {e['사유']}")

    if out["보완운동"]:
        print("■ 보완 운동")
        for b in out["보완운동"]:
            mark = "(제안)" if b["표현"] == "제안" else ""
            print(f"    · {b['축']} 보완 {mark}: {', '.join(b['운동'])}")
            print(f"      {b['처방']}")

    print("■ 안내")
    for note in out["안내"]:
        print(f"    - {note}")
    print()


if __name__ == "__main__":
    show("34세 남 · 저녁 헬스 · 무릎 불편",
         dict(age=34, sex="남", regular_exercise=True,
              preference={"운동빈도": "일주일에 3번", "운동요일": "평일",
                          "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
                          "운동강도": "중", "체력인지": "보통이다"},
              fitness={"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
              height_cm=175, weight_kg=82),
         picks={"자주해온": ["보디빌딩(헬스)"], "관심": ["배드민턴", "등산"]},
         discomfort=["무릎"])

    show("72세 여 · 매일 오전 걷기 · 체력 낮음",
         dict(age=72, sex="여", regular_exercise=True,
              preference={"운동빈도": "일주일에 7번(매일)", "운동요일": "평일/휴일",
                          "운동시간대": "오전(8-12시)", "운동목적": "건강 유지 및 체력증진",
                          "운동강도": "저", "체력인지": "별로 체력이 좋지 않은 편이다"},
              fitness={"근력": 1, "하지근기능": 1, "협응력평형": 2, "유연성": 2},
              height_cm=155, weight_kg=62),
         picks={"자주해온": ["걷기(속보 포함)"], "관심": ["수영+아쿠아로빅, 수중발레+수구"]})

    show("45세 여 · 비참여자 (선호 유형 없음)",
         dict(age=45, sex="여", regular_exercise=False,
              fitness={"근력": 3, "근지구력": 2, "순발력": 2, "유연성": 4},
              height_cm=162, weight_kg=60),
         picks={"관심": ["요가, 필라테스, 태보", "걷기(속보 포함)"]})

    show("40세 남 · 청년 고강도 구기형인데 아무것도 안 고름",
         dict(age=40, sex="남", regular_exercise=True,
              preference={"운동빈도": "일주일에 3번", "운동요일": "휴일",
                          "운동시간대": "저녁(18-22시)", "운동목적": "개인의 즐거움",
                          "운동강도": "고", "체력인지": "체력이 좋은 편이다"},
              fitness={"근력": 4, "근지구력": 4, "순발력": 4, "유연성": 3},
              height_cm=178, weight_kg=74),
         picks={})
