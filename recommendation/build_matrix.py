"""B2. 선호 적합도 행렬 (12 클래스 × 36 종목).

lca_final_combined.csv 에는 TOP3 만 있어서 추천에 쓸 수 없다.
원 파이프라인을 다시 돌려 전체 class × sport 점수를 뽑는다.

산출: data/preference_sport_matrix.csv
  선호점수비율 — 그 클래스가 실제로 많이 하는 종목 (1·2·3순위 3·2·1점 × 사후확률)
  클래스참여율 — 그 클래스에서 해당 종목을 하는 사람 비율
  Lift        — 세그먼트 평균 대비 그 클래스에서 유독 튀는 정도
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "analysis" / "최종 클러스터링 결과"
OUT = Path(__file__).resolve().parent / "data"

FINAL_K = {"성인_남성": 4, "성인_여성": 3, "노인_남성": 2, "노인_여성": 3}


def main():
    src = (RESULT / "lca_refit_local.py").read_text(encoding="utf-8")
    ns = {"__file__": str(RESULT / "lca_refit_local.py")}  # 원본이 상대경로를 __file__ 로 잡는다
    exec(compile(src.split("# ===== CELL 4")[0], "prep", "exec"), ns)
    analysis_df, indicators, fit_lca = ns["analysis_df"], ns["INDICATORS"], ns["fit_lca"]

    keep = ["응답자ID", "세그먼트", "운동종목_1", "운동종목_2", "운동종목_3"]
    weight_parts = []
    for segment, part in analysis_df.groupby("세그먼트"):
        model = fit_lca(part, indicators, n_classes=FINAL_K[segment], n_init=20)
        for c in range(model["n_classes"]):
            temp = part[keep].copy()
            temp["class_id"] = f"{segment}_LC{c + 1}"
            temp["weight"] = model["posterior"][:, c]
            weight_parts.append(temp)
    weights_long = pd.concat(weight_parts, ignore_index=True)

    # 종목 롱포맷 (1·2·3순위 → 3·2·1점, 같은 종목 중복 시 최상위 순위만)
    parts = []
    for rank, rank_weight in {1: 3, 2: 2, 3: 1}.items():
        temp = analysis_df[["응답자ID", "세그먼트", f"운동종목_{rank}"]].rename(
            columns={f"운동종목_{rank}": "운동종목"})
        temp["응답순위"] = rank
        temp["rank_weight"] = rank_weight
        parts.append(temp)
    sport_long = pd.concat(parts, ignore_index=True)
    sport_long = sport_long[sport_long["운동종목"].notna()
                            & sport_long["운동종목"].ne("없음")].copy()
    sport_long = (sport_long.sort_values(["응답자ID", "운동종목", "응답순위"])
                  .drop_duplicates(["응답자ID", "운동종목"]))

    sw = sport_long.merge(weights_long[["응답자ID", "class_id", "weight"]],
                          on="응답자ID", how="inner")
    sw["score"] = sw["rank_weight"] * sw["weight"]

    totals = weights_long.groupby("class_id")["weight"].sum().rename("클래스가중인원")
    summary = (sw.groupby(["class_id", "운동종목"], as_index=False)
               .agg(선호점수=("score", "sum"), 참여가중인원=("weight", "sum"))
               .merge(totals, on="class_id"))
    summary["선호점수비율"] = (summary["선호점수"]
                          / summary.groupby("class_id")["선호점수"].transform("sum") * 100)
    summary["클래스참여율"] = summary["참여가중인원"] / summary["클래스가중인원"] * 100
    summary["세그먼트"] = summary["class_id"].str.rsplit("_LC", n=1).str[0]

    seg_size = analysis_df.groupby("세그먼트")["응답자ID"].nunique().rename("세그먼트인원")
    seg_sport = (sport_long.groupby(["세그먼트", "운동종목"])["응답자ID"].nunique()
                 .rename("세그먼트참여인원").reset_index().merge(seg_size, on="세그먼트"))
    seg_sport["세그먼트참여율"] = (seg_sport["세그먼트참여인원"]
                             / seg_sport["세그먼트인원"] * 100)

    matrix = summary.merge(seg_sport[["세그먼트", "운동종목", "세그먼트참여율"]],
                           on=["세그먼트", "운동종목"], how="left")
    matrix["Lift"] = matrix["클래스참여율"] / matrix["세그먼트참여율"]

    cols = ["세그먼트", "class_id", "운동종목", "선호점수비율", "클래스참여율",
            "세그먼트참여율", "Lift", "참여가중인원"]
    matrix = matrix[cols].sort_values(["class_id", "선호점수비율"],
                                      ascending=[True, False]).round(4)
    matrix.to_csv(OUT / "preference_sport_matrix.csv", index=False, encoding="utf-8-sig")

    print(f"저장: {OUT / 'preference_sport_matrix.csv'}")
    print(f"  {matrix['class_id'].nunique()}개 클래스 × {matrix['운동종목'].nunique()}개 종목 "
          f"= {len(matrix)}행")

    master = pd.read_csv(OUT / "sport_master.csv")
    missing = set(matrix["운동종목"]) - set(master["종목"])
    extra = set(master["종목"]) - set(matrix["운동종목"])
    print(f"  마스터에 없는 종목: {sorted(missing) if missing else '없음'}")
    print(f"  데이터에 없는 종목: {sorted(extra) if extra else '없음'}")

    print("\n클래스별 상위 3종목 (선호점수비율):")
    for cid, g in matrix.groupby("class_id"):
        top = g.head(3)
        print(f"  {cid}: " + ", ".join(
            f"{r.운동종목}({r.선호점수비율:.1f}%)" for r in top.itertuples()))


if __name__ == "__main__":
    main()
