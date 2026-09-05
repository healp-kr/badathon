"""배정 층 검증 (A6).

핵심은 골든 테스트다 — 원본 데이터를 그대로 넣어 클러스터링 당시의 배정이
재현되는지 본다. 정답이 있는 테스트라 "됐다/안 됐다"가 명확하다.

실행: python test_assign.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from assign import (AssignmentError, ITEM_TO_VAR, assign_all, assign_fitness,
                    assign_preference, age_to_band, route)

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "analysis" / "최종 클러스터링 결과"

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ------------------------------------------------------------------
# 1. 선호축 골든 테스트 — 원본 6,602명 재현
# ------------------------------------------------------------------
def test_preference_golden():
    print("\n1. 선호축 골든 테스트 (원본 6,602명)")
    src = (RESULT / "lca_refit_local.py").read_text(encoding="utf-8")
    ns = {"__file__": str(RESULT / "lca_refit_local.py")}  # 원본이 상대경로를 __file__ 로 잡는다
    exec(compile(src.split("# ===== CELL 4")[0], "prep", "exec"), ns)
    analysis_df, indicators, fit_lca = ns["analysis_df"], ns["INDICATORS"], ns["fit_lca"]

    FINAL_K = {"성인_남성": 4, "성인_여성": 3, "노인_남성": 2, "노인_여성": 3}
    var_to_item = {v: k for k, v in ITEM_TO_VAR.items()}

    total = agree = 0
    for segment, part in analysis_df.groupby("세그먼트"):
        model = fit_lca(part, indicators, n_classes=FINAL_K[segment], n_init=20)
        reference = model["posterior"].argmax(axis=1) + 1

        got = []
        for _, row in part.iterrows():
            answers = {var_to_item[v]: row[v] for v in indicators}
            got.append(int(assign_preference(answers, segment)["class_id"].split("_LC")[1]))

        same = int((np.asarray(got) == reference).sum())
        check(f"{segment} 재현 {same}/{len(part)}", same == len(part))
        total += len(part)
        agree += same

    check(f"선호축 전체 재현 {agree}/{total} ({agree / total:.4%})", agree == total)


# ------------------------------------------------------------------
# 2. 체력축 골든 테스트 — 실측 z 투입 시 원 라벨 재현
# ------------------------------------------------------------------
def test_fitness_golden():
    print("\n2. 체력축 골든 테스트 (실측 z 투입, 113,234명)")
    d = pd.read_csv(RESULT / "fit2023_segments_final_v2.csv")
    total = agree = 0
    for label, s in d.groupby("하위집단_라벨"):
        sample = s.sample(n=min(4000, len(s)), random_state=0)
        axes = assign_fitness({}, label)["z"].keys()
        got = []
        for _, row in sample.iterrows():
            z = {a: row[a] for a in axes}
            got.append(assign_fitness({}, label, z_override=z)["segment"])
        same = int((np.asarray(got) == sample["체력세그먼트"].values).sum())
        check(f"{label} 재현 {same}/{len(sample)} ({same / len(sample):.2%})",
              same / len(sample) > 0.99)
        total += len(sample)
        agree += same
    check(f"체력축 전체 {agree / total:.2%} (>99% 기대)", agree / total > 0.99)


# ------------------------------------------------------------------
# 3. 라우팅 경계값
# ------------------------------------------------------------------
def test_routing():
    print("\n3. 라우팅 경계값")
    cases = [
        # 나이, 성별, 참여, 기대 선호세그먼트, 기대 체력집단, 표시라벨
        (18, "남", True, "성인_남성", None, "성인"),      # 19세 미만 → 체력 미부여
        (19, "남", True, "성인_남성", "성인 남", "성인"),
        (59, "여", True, "성인_여성", "성인 여", "성인"),
        (60, "여", True, "노인_여성", "성인 여", "노인"),  # 선호는 노인, 체력은 성인
        (64, "남", True, "노인_남성", "성인 남", "노인"),
        (65, "남", True, "노인_남성", "노인 남", "노인"),
        (34, "남", False, None, "성인 남", "성인"),        # 비참여자 → 선호 미부여
    ]
    for age, sex, reg, exp_pref, exp_fit, exp_disp in cases:
        r = route(age, sex, reg)
        ok = (r["preference_segment"] == exp_pref
              and r["fitness_group"] == exp_fit
              and r["display_age_group"] == exp_disp)
        check(f"{age}세 {sex} 참여={reg} → 선호 {r['preference_segment']} / "
              f"체력 {r['fitness_group']} / 표시 {r['display_age_group']}", ok)

    bands = [(19, 1), (24, 1), (25, 2), (60, 9), (64, 9), (65, 10), (79, 12), (95, 13), (18, None)]
    ok = all(age_to_band(a) == b for a, b in bands)
    check("연령대 코드 변환", ok)


# ------------------------------------------------------------------
# 4. 결측·이상 응답
# ------------------------------------------------------------------
def test_robustness():
    print("\n4. 결측·이상 응답")
    full = {"운동빈도": "일주일에 3번", "운동요일": "평일", "운동시간대": "저녁(18-22시)",
            "운동목적": "건강 유지 및 체력증진", "운동강도": "중", "체력인지": "보통이다"}

    base = assign_preference(full, "성인_남성")
    check("6문항 정상 배정", base["class_id"].startswith("성인_남성_LC"),
          f"{base['name']} p={base['probability']}")

    partial = assign_preference({k: full[k] for k in ("운동요일", "운동빈도", "운동시간대")},
                                "성인_남성")
    check("3문항만으로도 동작(주변화)", len(partial["skipped_items"]) == 3,
          f"{partial['name']} p={partial['probability']}")

    unknown = assign_preference({**full, "운동강도": "초고강도"}, "성인_남성")
    check("알 수 없는 선택지를 건너뜀", "운동강도" in unknown["skipped_items"])

    probs = sum(c["probability"] for c in base["ranked"])
    check("확률 합 = 1", abs(probs - 1) < 1e-3, f"{probs:.4f}")

    f = assign_fitness({"근력": 5, "근지구력": 5, "순발력": 5, "유연성": 5},
                       "성인 남", height_cm=175, weight_kg=68)
    check("체력 전항목 최고 → 우수형", f["segment"] == "전반적 우수형",
          f"{f['segment']} 확신도 {f['confidence']}")

    f2 = assign_fitness({"근력": 1, "근지구력": 1, "순발력": 1, "유연성": 1},
                        "성인 남", height_cm=170, weight_kg=95)
    check("체력 전항목 최저 → 저조형", f2["segment"] == "전반적 저조형",
          f"{f2['segment']} 확신도 {f2['confidence']}")

    # 모호 판정은 "중간 응답이면 모호"가 아니라 "확신도 < 게이트면 모호"다.
    # 게이트 동작 자체를 검증하고, 실제로 모호해지는 입력이 존재하는지 확인한다.
    from assign import FITNESS
    gate = FITNESS["confidence_gate"]
    grid, ambiguous_case = [], None
    for a in (1, 2, 3, 4, 5):
        for b in (1, 3, 5):
            for c in (1, 3, 5):
                r = assign_fitness({"근력": a, "근지구력": b, "순발력": c, "유연성": 3},
                                   "성인 남", height_cm=175, weight_kg=72)
                grid.append(r["ambiguous"] == (r["confidence"] < gate))
                if r["ambiguous"] and ambiguous_case is None:
                    ambiguous_case = (a, b, c, r)
    check("모호 플래그 = (확신도 < 1.2)", all(grid), f"{len(grid)}개 조합 검사")
    check("모호해지는 입력이 실제로 존재한다", ambiguous_case is not None,
          "" if ambiguous_case is None else
          f"근력{ambiguous_case[0]}·근지구력{ambiguous_case[1]}·순발력{ambiguous_case[2]} → "
          f"{ambiguous_case[3]['segment']} 확신도 {ambiguous_case[3]['confidence']} "
          f"(대안 {ambiguous_case[3]['alternative']})")

    f3 = assign_fitness({"근력": 3, "근지구력": 3, "순발력": 3, "유연성": 3},
                        "성인 남", height_cm=175, weight_kg=72)
    check("전 항목 '보통' 응답도 배정된다", f3["segment"] in f3["distances"],
          f"{f3['segment']} 확신도 {f3['confidence']} 대안 {f3['alternative']}")

    f4 = assign_fitness({}, "성인 남")
    check("체력 응답 전부 결측이어도 죽지 않음", len(f4["missing_axes"]) == 5)

    for bad in (lambda: route(30, "M"), lambda: route(-1, "남"),
                lambda: assign_preference({}, "없는세그먼트"),
                lambda: assign_fitness({"근력": 9}, "성인 남")):
        try:
            bad()
            check("잘못된 입력에 예외", False)
            break
        except AssignmentError:
            pass
    else:
        check("잘못된 입력에 AssignmentError", True)


# ------------------------------------------------------------------
# 5. 통합 시나리오
# ------------------------------------------------------------------
def test_end_to_end():
    print("\n5. 통합 시나리오")
    r = assign_all(
        age=34, sex="남", regular_exercise=True,
        preference={"운동빈도": "일주일에 3번", "운동요일": "평일",
                    "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
                    "운동강도": "고", "체력인지": "체력이 좋은 편이다"},
        fitness={"근력": 4, "근지구력": 4, "순발력": 3, "유연성": 2},
        height_cm=176, weight_kg=73)
    check("34세 남 통합 배정",
          r["preference"] is not None and r["fitness"] is not None,
          f"{r['preference']['name']} × {r['fitness']['segment']}")

    e = assign_all(age=72, sex="여", regular_exercise=True,
                   preference={"운동빈도": "일주일에 7번(매일)", "운동요일": "평일/휴일",
                               "운동시간대": "오전(8-12시)", "운동목적": "건강 유지 및 체력증진",
                               "운동강도": "저", "체력인지": "보통이다"},
                   fitness={"근력": 2, "하지근기능": 2, "협응력평형": 3, "유연성": 3},
                   height_cm=155, weight_kg=58)
    check("72세 여 통합 배정",
          e["fitness"]["group"] == "노인 여",
          f"{e['preference']['name']} × {e['fitness']['segment']}")

    n = assign_all(age=45, sex="여", regular_exercise=False,
                   fitness={"근력": 3, "근지구력": 2, "순발력": 2, "유연성": 4},
                   height_cm=162, weight_kg=60)
    check("비참여자는 선호 미배정, 체력만",
          n["preference"] is None and n["fitness"] is not None,
          n["routing"]["skip_reason"]["preference"])

    y = assign_all(age=16, sex="남", regular_exercise=True,
                   preference={"운동빈도": "일주일에 2번", "운동요일": "휴일",
                               "운동시간대": "오후(14-18시)", "운동목적": "개인의 즐거움",
                               "운동강도": "중", "체력인지": "보통이다"})
    check("19세 미만은 체력 미배정",
          y["preference"] is not None and y["fitness"] is None,
          y["routing"]["skip_reason"]["fitness"])


if __name__ == "__main__":
    test_preference_golden()
    test_fitness_golden()
    test_routing()
    test_robustness()
    test_end_to_end()
    print(f"\n{'=' * 60}\n통과 {len(PASS)} / 실패 {len(FAIL)}")
    if FAIL:
        print("실패 항목:", *FAIL, sep="\n  - ")
        sys.exit(1)
