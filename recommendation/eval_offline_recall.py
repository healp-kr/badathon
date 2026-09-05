"""평가 방법 1 — 오프라인 홀드아웃 재현율.

test_assign.py 의 골든 테스트는 "모델을 정확히 구현했는가"를 검증한다(원본 전체로
적합한 LCA의 posterior.argmax 를 그대로 재현하는지). 이 스크립트는 다른 질문에 답한다 —
"그 배정·행렬이 실제로 사람들이 하는 운동을 맞히는가."

방법: 세그먼트별 K-fold 교차검증.
  1. 각 폴드에서 훈련 폴드만으로 LCA를 다시 적합한다 (홀드아웃 응답자는 학습에 안 씀).
  2. 같은 훈련 폴드로 선호 적합도 행렬(build_matrix.py와 동일 로직)을 만든다.
  3. 홀드아웃 응답자를 훈련된 파라미터로 배정하고, 배정된 클래스의 추천 top-N 안에
     그 사람이 실제로 신고한 종목이 있는지를 Recall@N으로 잰다.
  4. 클래스를 무시한 "전체 인기도" top-N과 비교해, 유형 분류가 실제로 정보를 더하는지 본다.

전 응답자가 정확히 한 번씩 홀드아웃되므로(out-of-fold), 80/20 한 번 나누는 것보다
노인_남성처럼 표본이 작은 세그먼트에서도 추정이 안정적이다.

5. 추가로 recommend.py의 "새로운운동" 경로(걷기를 기반활동으로 먼저 빼고, Lift 가중을
   0.5로 올려 재점수화하는 실제 운영 로직)까지 재현해, 걷기 분리 + Lift 강화가
   전체인기도 대비 실질적인 이득을 만드는지도 같이 잰다.

산출: docs/평가_오프라인재현율.md

실행: python eval_offline_recall.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "analysis" / "최종 클러스터링 결과"
DATA = Path(__file__).resolve().parent / "data"
DOCS = ROOT / "docs"

with open(DATA / "rules.json", encoding="utf-8") as f:
    RULES = json.load(f)

FINAL_K = {"성인_남성": 4, "성인_여성": 3, "노인_남성": 2, "노인_여성": 3}
K_FOLDS = 5
SEED = 0
N_INIT = 15
N_LIST = [3, 5, 8]
BASELINE_SPORTS = set(RULES["기반활동"]["종목"])
RULES_NEW_LIFT = RULES["buckets"]["새로운_Lift_가중"]

# recommend.py _score_sports 와 동일한 상수
W_SHARE, W_LIFT, LIFT_CAP = 0.7, 0.3, 3.0
MIN_N, MIN_SHARE = 5, 1.0


def load_analysis():
    src = (RESULT / "lca_refit_local.py").read_text(encoding="utf-8")
    ns = {"__file__": str(RESULT / "lca_refit_local.py")}
    exec(compile(src.split("# ===== CELL 4")[0], "prep", "exec"), ns)
    return ns["analysis_df"], ns["INDICATORS"], ns["fit_lca"]


def make_folds(n, k, seed):
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    return np.array_split(order, k)


def assign_batch(model, columns, frame):
    """train 파라미터로 frame 의 사후확률 argmax 클래스 인덱스를 계산.

    assign_preference와 동일 규칙: 훈련 폴드에 없던 범주는 그 항을 건너뛴다(주변화).
    """
    n = len(frame)
    log_prob = np.tile(np.log(model["class_prob"] + 1e-300), (n, 1))
    for j, col in enumerate(columns):
        idx_map = {lvl: i for i, lvl in enumerate(model["levels"][col])}
        codes = frame[col].map(idx_map)
        known = codes.notna().values
        codes_arr = codes.fillna(0).astype(int).values
        rp = model["response_prob"][j]  # [n_classes, n_categories]
        contrib = np.log(rp[:, codes_arr] + 1e-300).T  # [n, n_classes]
        contrib[~known] = 0.0
        log_prob = log_prob + contrib
    return log_prob.argmax(axis=1)


def build_train_matrix(class_ids, train_part, model, recommendable):
    """build_matrix.py 와 동일한 로직을, 이 폴드의 훈련 응답자만으로 계산."""
    parts = []
    for rank, w in {1: 3, 2: 2, 3: 1}.items():
        col = f"운동종목_{rank}"
        t = train_part[["응답자ID", col]].rename(columns={col: "운동종목"})
        t["응답순위"], t["rank_weight"] = rank, w
        parts.append(t)
    sport_long = pd.concat(parts, ignore_index=True)
    sport_long = sport_long[sport_long["운동종목"].notna() & sport_long["운동종목"].ne("없음")]
    sport_long = (sport_long.sort_values(["응답자ID", "운동종목", "응답순위"])
                  .drop_duplicates(["응답자ID", "운동종목"]))

    weights_long = []
    for c, cid in enumerate(class_ids):
        t = train_part[["응답자ID"]].copy()
        t["class_id"], t["weight"] = cid, model["posterior"][:, c]
        weights_long.append(t)
    weights_long = pd.concat(weights_long, ignore_index=True)

    sw = sport_long.merge(weights_long, on="응답자ID", how="inner")
    sw["score"] = sw["rank_weight"] * sw["weight"]

    totals = weights_long.groupby("class_id")["weight"].sum().rename("클래스가중인원")
    summary = (sw.groupby(["class_id", "운동종목"], as_index=False)
               .agg(선호점수=("score", "sum"), 참여가중인원=("weight", "sum"))
               .merge(totals, on="class_id"))
    summary["선호점수비율"] = (summary["선호점수"]
                          / summary.groupby("class_id")["선호점수"].transform("sum") * 100)
    summary["클래스참여율"] = summary["참여가중인원"] / summary["클래스가중인원"] * 100

    seg_n = train_part["응답자ID"].nunique()
    seg_sport = sport_long.groupby("운동종목")["응답자ID"].nunique().rename("세그먼트참여인원").reset_index()
    seg_sport["세그먼트참여율"] = seg_sport["세그먼트참여인원"] / seg_n * 100
    summary = summary.merge(seg_sport[["운동종목", "세그먼트참여율"]], on="운동종목", how="left")
    summary["Lift"] = summary["클래스참여율"] / summary["세그먼트참여율"]

    # 운영 코드(_score_sports)와 동일한 표본 필터 + 추천가능 필터
    summary = summary[(summary["참여가중인원"] >= MIN_N) & (summary["클래스참여율"] >= MIN_SHARE)]
    summary = summary[summary["운동종목"].isin(recommendable)]

    baseline_sports = {"걷기(속보 포함)"}
    ranked_raw, ranked_new = {}, {}
    for cid, g in summary.groupby("class_id"):
        ranked_raw[cid] = _rank(g, W_SHARE, W_LIFT)  # ① _score_sports 그대로 (걷기 포함)

        g_new = g[~g["운동종목"].isin(baseline_sports)]  # recommend()가 baseline을 먼저 뺀 뒤
        ranked_new[cid] = _rank(g_new, 1 - RULES_NEW_LIFT, RULES_NEW_LIFT)  # _rescore_new 그대로

    return ranked_raw, ranked_new, sport_long, seg_n


def _rank(g, w_share, w_lift):
    if g.empty:
        return []
    share = _normalize(g["선호점수비율"])
    lift = _normalize(g["Lift"].clip(upper=LIFT_CAP))
    score = w_share * share + w_lift * lift
    return g.assign(점수=score).sort_values("점수", ascending=False)["운동종목"].tolist()


def pooled_popularity(sport_long, seg_n, recommendable, exclude=frozenset()):
    """클래스를 무시한 전체 인기도 순위 (같은 rank_weight 스킴, 클래스 가중 없이)."""
    pooled = sport_long.groupby("운동종목")["rank_weight"].sum().rename("점수").reset_index()
    pooled = pooled[pooled["운동종목"].isin(recommendable) & ~pooled["운동종목"].isin(exclude)]
    return pooled.sort_values("점수", ascending=False)["운동종목"].tolist()


def _normalize(s):
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-9:
        return s * 0 + 0.5
    return (s - lo) / (hi - lo)


def hit_at_n(ranked_list, n, actual_set):
    return bool(set(ranked_list[:n]) & actual_set)


def main():
    analysis_df, indicators, fit_lca = load_analysis()
    master = pd.read_csv(DATA / "sport_master.csv")
    recommendable = set(master.loc[master["추천가능"] == "Y", "종목"])

    records = []  # 응답자 단위 결과
    catalog_sizes = {}

    for segment, part in analysis_df.groupby("세그먼트"):
        part = part.reset_index(drop=True)
        class_ids = [f"{segment}_LC{c + 1}" for c in range(FINAL_K[segment])]
        folds = make_folds(len(part), K_FOLDS, SEED)

        print(f"\n{segment} (n={len(part)}, k={FINAL_K[segment]}클래스, {K_FOLDS}-fold)")
        for fi, test_idx in enumerate(folds):
            test_mask = np.zeros(len(part), dtype=bool)
            test_mask[test_idx] = True
            train_part, test_part = part[~test_mask], part[test_mask]

            model = fit_lca(train_part, indicators, n_classes=FINAL_K[segment], n_init=N_INIT)
            ranked_raw, ranked_new, sport_long, seg_n = build_train_matrix(
                class_ids, train_part, model, recommendable)
            pooled = pooled_popularity(sport_long, seg_n, recommendable)
            pooled_nowalk = pooled_popularity(sport_long, seg_n, recommendable, exclude=BASELINE_SPORTS)
            catalog_sizes[segment] = len(set(sport_long["운동종목"]) & recommendable)

            pred_idx = assign_batch(model, indicators, test_part)
            for row, ci in zip(test_part.itertuples(), pred_idx):
                cid = class_ids[ci]
                primary = getattr(row, "운동종목_1")
                actual_all = {getattr(row, f"운동종목_{r}") for r in (1, 2, 3)} - {None, np.nan, "없음"}
                actual_all = {a for a in actual_all if isinstance(a, str)}
                records.append({
                    "세그먼트": segment, "fold": fi, "class_id": cid,
                    "primary": primary,
                    "primary_recommendable": primary in recommendable,
                    "actual_all": actual_all,
                    "class_ranked": ranked_raw.get(cid, []),
                    "class_ranked_new": ranked_new.get(cid, []),
                    "pooled_ranked": pooled,
                    "pooled_ranked_nowalk": pooled_nowalk,
                })
            print(f"  fold {fi + 1}/{K_FOLDS}: train={len(train_part)} test={len(test_part)} "
                  f"entropy={model.get('Entropy', float('nan')):.3f}")

    report(records, catalog_sizes, recommendable)


def report(records, catalog_sizes, recommendable):
    df = pd.DataFrame(records)
    lines = ["# 평가 방법 1 — 오프라인 홀드아웃 재현율", "",
             f"K={K_FOLDS}-fold 교차검증, {len(df)}명 전원이 정확히 한 번씩 홀드아웃됨. "
             "각 폴드에서 LCA·선호 적합도 행렬을 훈련 폴드만으로 다시 만들고, "
             "홀드아웃 응답자가 실제로 신고한 종목이 그 사람이 배정된 클래스의 추천 "
             "top-N 안에 들어가는지를 쟀다.", "",
             "**읽는 법**: `유형기반`이 `전체인기도`보다 높아야 유형 분류가 실제로 정보를 더한다는 뜻. "
             "`무작위(이론)`는 그 세그먼트 카탈로그 크기에서 무작위로 N개를 뽑았을 때의 기대 재현율이다.",
             ""]

    for scope_name, sub in [("전체 (추천가능 종목만 신고한 응답자)", df[df["primary_recommendable"]]),
                             ("전체 (신고 종목이 추천 불가 카탈로그 밖이면 자동 실패 포함)", df)]:
        lines.append(f"## {scope_name}")
        lines.append("")
        lines.append("| 세그먼트 | N | 지표 | " + " | ".join(f"Recall@{n}" for n in N_LIST) + " |")
        lines.append("|---|---|---|" + "---|" * len(N_LIST))

        for segment in sorted(df["세그먼트"].unique()):
            seg_df = sub[sub["세그먼트"] == segment]
            if seg_df.empty:
                continue
            cat_size = catalog_sizes[segment]
            for label, ranked_col in [("유형기반", "class_ranked"), ("전체인기도", "pooled_ranked")]:
                vals = []
                for n in N_LIST:
                    hits = seg_df.apply(
                        lambda r: hit_at_n(r[ranked_col], n, {r["primary"]}), axis=1)
                    vals.append(hits.mean())
                lines.append(f"| {segment} | {len(seg_df)} | {label} (1순위 기준) | "
                             + " | ".join(f"{v:.1%}" for v in vals) + " |")
            vals = [min(1.0, n / cat_size) for n in N_LIST]
            lines.append(f"| {segment} | {len(seg_df)} | 무작위(이론) | "
                         + " | ".join(f"{v:.1%}" for v in vals) + " |")

            # 1~3순위 아무거나 맞아도 되는 관대한 버전 (유형기반만)
            vals = []
            for n in N_LIST:
                hits = seg_df.apply(lambda r: hit_at_n(r["class_ranked"], n, r["actual_all"]), axis=1)
                vals.append(hits.mean())
            lines.append(f"| {segment} | {len(seg_df)} | 유형기반 (1~3순위 중 하나) | "
                         + " | ".join(f"{v:.1%}" for v in vals) + " |")
        lines.append("")

    # 걷기 제외 — 순위표가 걷기 쏠림만으로 점수를 버는 건 아닌지 분해
    lines.append("## 걷기 제외 시 (차별화된 나머지 종목만으로)")
    lines.append("")
    lines.append("| 세그먼트 | N | 지표 | " + " | ".join(f"Recall@{n}" for n in N_LIST) + " |")
    lines.append("|---|---|---|" + "---|" * len(N_LIST))
    walk = "걷기(속보 포함)"
    sub = df[df["primary_recommendable"] & (df["primary"] != walk)]
    for segment in sorted(df["세그먼트"].unique()):
        seg_df = sub[sub["세그먼트"] == segment]
        if seg_df.empty:
            continue
        for label, ranked_col in [("유형기반", "class_ranked"), ("전체인기도", "pooled_ranked")]:
            vals = []
            for n in N_LIST:
                def _hit(r, col=ranked_col, n=n):
                    lst = [s for s in r[col] if s != walk]
                    return hit_at_n(lst, n, {r["primary"]})
                hits = seg_df.apply(_hit, axis=1)
                vals.append(hits.mean())
            lines.append(f"| {segment} | {len(seg_df)} | {label} | "
                         + " | ".join(f"{v:.1%}" for v in vals) + " |")
    lines.append("")

    # 실사용자 체감 — recommend()가 실제로 하는 대로: 걷기는 기반활동으로 항상 보여주고,
    # 나머지는 Lift 가중 0.5로 재점수화한 "새로운운동" 목록을 N개 더 보여준다.
    lines.append("## 실사용자 체감 재현율 (기반활동 분리 + 새로운운동 Lift 0.5 재점수화, 운영 로직 그대로)")
    lines.append("")
    lines.append("사용자가 실제로 보는 화면 = 기반활동(걷기, 항상 노출) + 새로운운동 top-N. "
                 "'전체인기도(걷기분리)'도 같은 구조로, 유형 정보 없이 인기 종목 top-N을 새로운운동 자리에 넣었을 때다.")
    lines.append("")
    lines.append("| 세그먼트 | N | 지표 | " + " | ".join(f"Recall@{n}" for n in N_LIST) + " |")
    lines.append("|---|---|---|" + "---|" * len(N_LIST))
    sub = df[df["primary_recommendable"]]
    for segment in sorted(df["세그먼트"].unique()):
        seg_df = sub[sub["세그먼트"] == segment]
        if seg_df.empty:
            continue
        for label, ranked_col in [("유형기반(새로운운동 로직)", "class_ranked_new"),
                                   ("전체인기도(걷기분리)", "pooled_ranked_nowalk")]:
            vals = []
            for n in N_LIST:
                def _hit(r, col=ranked_col, n=n):
                    if r["primary"] in BASELINE_SPORTS:
                        return True  # 걷기는 항상 기반활동으로 노출됨
                    return hit_at_n(r[col], n, {r["primary"]})
                hits = seg_df.apply(_hit, axis=1)
                vals.append(hits.mean())
            lines.append(f"| {segment} | {len(seg_df)} | {label} | "
                         + " | ".join(f"{v:.1%}" for v in vals) + " |")
    lines.append("")

    lines.append("## 참고")
    lines.append("")
    lines.append(f"- 폴드: {K_FOLDS} / 반복 EM 시작: {N_INIT} / 시드: {SEED}")
    lines.append(f"- 카탈로그 크기(세그먼트별 추천가능 종목 수): "
                 + ", ".join(f"{k} {v}개" for k, v in catalog_sizes.items()))
    lines.append("- 이 평가는 배정 층(assign.py)이 아니라 **선호 적합도 행렬 기반 종목 순위**의 "
                 "일반화 성능을 잰다. 체력축·안전필터·설문 보정은 포함하지 않는다 "
                 "(recommend.py ①·②만 평가, ③④는 제외).")
    lines.append("- '신고한 종목'은 국민생활체육조사의 '주로 참여하는 체육활동'이지, "
                 "앱 사용자가 추천 화면에서 클릭/수락했는지가 아니다. 진짜 만족도·수락률은 "
                 "출시 후 로그(D2)로만 알 수 있다.")

    out_path = DOCS / "평가_오프라인재현율.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n저장: {out_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
