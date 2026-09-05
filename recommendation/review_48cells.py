"""B7. 48셀 스모크 테스트.

선호 12유형 × 체력 4유형의 모든 유효 조합에 대해 추천을 생성해
사람이 훑어보며 이상한 결과를 잡을 수 있는 마크다운을 만든다.

유효 셀 = 하위집단이 겹치는 조합만
  성인남 4×4 + 성인여 3×4 + 노인남 2×4 + 노인여 3×4 = 48

산출: ../docs/48셀_검수.md
"""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "assignment"))
sys.stdout.reconfigure(encoding="utf-8")

from assign import FITNESS, PREFERENCE          # noqa: E402
from recommend import RULES, recommend          # noqa: E402

# 세그먼트 → (체력 하위집단, 대표 나이)
SEGMENT_CONTEXT = {
    "성인_남성": ("성인 남", 40),
    "성인_여성": ("성인 여", 40),
    "노인_남성": ("노인 남", 70),
    "노인_여성": ("노인 여", 70),
}

# 세그먼트 중심을 그대로 넣어 "그 유형의 전형적인 사람"을 만든다
def fitness_stub(group, segment):
    spec = FITNESS["groups"][group]
    z = dict(zip(spec["axes"], spec["centroids"][segment]))
    names = list(spec["centroids"])
    import numpy as np
    centroids = np.asarray([spec["centroids"][n] for n in names])
    vec = np.asarray([z[a] for a in spec["axes"]])
    dist = np.linalg.norm(centroids - vec, axis=1)
    order = dist.argsort()
    conf = float(dist[order[1]] / dist[order[0]]) if dist[order[0]] > 0 else float("inf")
    return {
        "group": group,
        "segment": names[order[0]],
        "confidence": round(conf, 3),
        "ambiguous": conf < FITNESS["confidence_gate"],
        "alternative": names[order[1]],
        "z": {k: round(v, 3) for k, v in z.items()},
    }


def modal_survey(segment, class_index):
    """그 클래스의 전형적인 설문 응답 = 조건부 응답확률이 가장 높은 범주.

    48셀 검수를 실제와 가깝게 만들기 위해 클래스마다 자기 프로파일을 입력으로 쓴다.
    """
    spec = PREFERENCE["segments"][segment]["indicators"]
    out = {}
    for item, var in (("운동목적", "운동목적_1"), ("운동시간대", "운동시간대_1"),
                      ("운동강도", "운동강도_1")):
        levels = spec[var]["levels"]
        probs = spec[var]["response_prob"][class_index]
        out[item] = levels[max(range(len(levels)), key=lambda i: probs[i])]
    return out


def main():
    lines = ["# 48셀 추천 검수",
             "",
             "선호 12유형 × 체력 4유형의 모든 유효 조합. **각 체력 유형의 중심값**(그 유형의",
             "전형적인 사람)을 넣어 생성했다. 불편 부위는 없다고 가정.",
             "",
             "표에 실린 것은 **'새로운 운동'** 갈래다. 추천은 기반 활동 + 두 갈래로 나가는데,",
             "**걷기는 '기반 활동'으로 빠져 추천 칸에 오르지 않는다**(어느 유형에서든 1위라",
             "다른 종목을 밀어내기 때문). '익숙한 운동'은 사용자가 고른 종목에 따라 달라져 비어 있다.",
             "점수에는 각 유형의 **전형적 설문 응답**(강도·시간대·목적)에 따른 보정이 반영돼 있다.",
             "'새로운 운동'은 사용자가 고르지 않은 종목 중에서 뽑으므로 Lift 가중이 더 높다",
             f"(선호점수비율 {1 - RULES['buckets']['새로운_Lift_가중']:.1f} / "
             f"Lift {RULES['buckets']['새로운_Lift_가중']:.1f}).",
             "",
             "명백히 이상한 추천이 있는지 훑어보는 용도다. 예: 70대에게 고강도 구기 종목,",
             "체력이 낮은데 강도가 높게 나오는 경우, 유형 성격과 동떨어진 종목.",
             "",
             f"- 점수 = 선호점수비율 {RULES['scoring']['선호점수비율_가중']} + "
             f"Lift {RULES['scoring']['Lift_가중']} (정규화 후 가중합)",
             f"- 최소 표본: 참여가중인원 {RULES['scoring']['최소_참여가중인원']}명, "
             f"클래스참여율 {RULES['scoring']['최소_클래스참여율']}% 이상",
             "- 체력축은 종목 선택에 관여하지 않는다. 강도 조절과 보완 운동에만 쓴다.",
             "", "---", ""]

    rows = []
    for segment, spec in PREFERENCE["segments"].items():
        group, age = SEGMENT_CONTEXT[segment]
        fitness_segments = list(FITNESS["groups"][group]["centroids"])

        for ci, klass in enumerate(spec["classes"]):
            survey = modal_survey(segment, ci)
            lines.append(f"## {klass['name']}  ·  {klass['class_id']}")
            lines.append("")
            lines.append(f"{segment} / 대표 나이 {age}세 / 유형 비중 {klass['prob']:.1%}")
            lines.append(f"전형적 응답 — 강도 {survey['운동강도']} · "
                         f"{survey['운동시간대']} · 목적 {survey['운동목적']}")
            lines.append("")
            lines.append("| 체력 유형 | 추천 종목 (점수) | 권장 강도 상한 | 보완 운동 | 제외 |")
            lines.append("|---|---|---|---|---|")

            for fseg in fitness_segments:
                fit = fitness_stub(group, fseg)
                out = recommend({"class_id": klass["class_id"], "name": klass["name"],
                                 "probability": None},
                                fit, age=age, survey=survey, top_n=4)

                sports = " · ".join(
                    f"{s['종목'].split(',')[0].split('(')[0].strip()}({s['점수']:.0f})"
                    for s in out["새로운운동"])
                support = " / ".join(
                    f"{s['축']}→{s['운동'][0]}" for s in out["보완운동"]) or "—"
                excluded = f"{len(out['제외종목'])}건" if out["제외종목"] else "—"
                cap = out["처방"].get("권장강도상한", "—")
                flag = " ⚠" if fit["ambiguous"] else ""

                lines.append(f"| {fseg}{flag} | {sports} | {cap} | {support} | {excluded} |")
                rows.append({"선호유형": klass["name"], "체력유형": fseg,
                             "상위종목": out["새로운운동"][0]["종목"] if out["새로운운동"] else None,
                             "강도상한": cap, "보완수": len(out["보완운동"]),
                             "제외수": len(out["제외종목"])})
            lines.append("")

    lines += ["---", "", "## 점검 포인트", "",
              f"- 총 {len(rows)}개 셀 생성",
              "- ⚠ 표시는 체력 유형 중심값끼리도 확신도가 낮은 경우 (경계가 가까운 유형)",
              "- 체력축은 종목의 **순위**에 관여하지 않는다. 순위는 선호축만으로 정해지고, "
              "체력축은 강도 상한을 넘는 종목을 **잘라내는** 역할만 한다. "
              "그래서 같은 선호유형이면 종목 목록은 같고, 체력이 낮은 쪽만 뒤가 잘려 나간다.",
              "- 65세 이상에게는 고령적합 '비권장' 종목을 체력 유형과 무관하게 제외한다. "
              "이건 데이터가 아니라 보수적 판단이다(근거 없음).",
              "", "## 근거", ""]
    lines += [f"- {s}" for s in RULES["sources"]]
    lines += ["", f"> {RULES['safety']['면책']}"]

    out_path = HERE.parent / "docs" / "48셀_검수.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    df = pd.DataFrame(rows)
    print(f"저장: {out_path}  ({len(rows)}셀)")
    print("\n강도 상한 분포:")
    print(df["강도상한"].value_counts().to_string())
    print("\n체력 유형별 보완 운동 개수:")
    print(df.groupby("체력유형")["보완수"].mean().round(2).to_string())
    print("\n선호유형별 1순위 종목:")
    print(df.groupby("선호유형")["상위종목"].agg(lambda s: s.mode()[0]).to_string())


if __name__ == "__main__":
    main()
