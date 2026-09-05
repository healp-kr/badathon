"""평가 방법 1-b — 랭킹 품질 지표 (HR / Recall / MRR / NDCG).

eval_offline_recall.py 는 "top-N 안에 들었는가"(HR)만 잰다. K가 커지면 유형기반과
전체인기도가 붙어버려서(노인_남성 @8: 85.9 vs 89.3) 순위 품질 차이가 안 보인다.
이 스크립트는 같은 5-fold 홀드아웃 위에서 순위를 반영하는 지표를 추가로 잰다.

  - HR@K      : top-K 안에 1순위 종목이 있는가 (기존 지표, 이름만 정확히)
  - Recall@K  : 신고한 1~3순위 중 top-K가 건진 비율 (진짜 recall, 분모가 정답 수)
  - MRR       : 1순위 종목의 역순위 평균. 전체 리스트 대상(잘리지 않음)
  - NDCG@K    : 등급형 관련도. 신고 1·2·3순위 → rel 3·2·1
                (build_train_matrix 가 학습에 쓰는 rank_weight 와 같은 스킴)

두 개의 화면 모델을 각각 잰다.
  raw  : 적합도 행렬 순위 그대로 (걷기 포함). 순위 지표의 기준선.
  live : recommend() 운영 로직. 기반활동(걷기)이 항상 1번 슬롯, 그 뒤에 새로운운동 top-N.

산출: docs/평가_랭킹지표.md, recommendation/data/ranking_metrics.json
      (+ 폴드 재적합 캐시 scratch/records.pkl — 시각화 스크립트가 재사용)

실행: python recommendation/eval_ranking_metrics.py
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from eval_offline_recall import (
    BASELINE_SPORTS, DATA, DOCS, FINAL_K, K_FOLDS, N_INIT, SEED,
    assign_batch, build_train_matrix, load_analysis, make_folds, pooled_popularity,
)

sys.stdout.reconfigure(encoding="utf-8")

# eval_offline_recall 의 N_LIST([3,5,8])를 그대로 쓰지 않고 여기서 넓힌다.
# K=1·2 에서 유형 정보의 이득이 가장 크고(HR@1 상대 +18%), K=8 에서 사라지는 것이
# 이 평가의 핵심 관찰이라 양 끝이 다 보여야 한다. 원본 스크립트의 산출 문서는
# 발표 자료가 참조하므로 그쪽 N_LIST 는 건드리지 않는다.
N_LIST = [1, 2, 3, 5, 8]

CACHE = Path(__file__).resolve().parent / "data" / "ranking_records.pkl"
REL = {1: 3, 2: 2, 3: 1}  # 신고 순위 → 관련도 등급


# ---------------------------------------------------------------- 지표

def hr_at_n(ranked, n, actual):
    return float(bool(set(ranked[:n]) & actual))


def recall_at_n(ranked, n, actual):
    """진짜 recall — 분모가 그 사람의 정답 개수."""
    if not actual:
        return np.nan
    return len(set(ranked[:n]) & actual) / len(actual)


def reciprocal_rank(ranked, target):
    """1순위 종목의 역순위. 전체 리스트에 없으면 0."""
    try:
        return 1.0 / (ranked.index(target) + 1)
    except ValueError:
        return 0.0


def ndcg_at_n(ranked, n, rel_map):
    """rel_map: {종목: 등급}. IDCG 는 그 사람이 가진 등급을 이상적으로 정렬한 값."""
    if not rel_map:
        return np.nan
    dcg = sum(rel_map.get(s, 0) / np.log2(i + 2) for i, s in enumerate(ranked[:n]))
    ideal = sorted(rel_map.values(), reverse=True)[:n]
    idcg = sum(g / np.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else np.nan


def random_mrr(catalog_size):
    """무작위 순열에서 특정 1개 정답의 기대 역순위 = H_C / C."""
    return sum(1.0 / i for i in range(1, catalog_size + 1)) / catalog_size


# ---------------------------------------------------------------- 수집

def collect():
    analysis_df, indicators, fit_lca = load_analysis()
    master = pd.read_csv(DATA / "sport_master.csv")
    recommendable = set(master.loc[master["추천가능"] == "Y", "종목"])

    records, catalog_sizes = [], {}
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
            pooled_nowalk = pooled_popularity(sport_long, seg_n, recommendable,
                                              exclude=BASELINE_SPORTS)
            catalog_sizes[segment] = len(set(sport_long["운동종목"]) & recommendable)

            for row, ci in zip(test_part.itertuples(), assign_batch(model, indicators, test_part)):
                cid = class_ids[ci]
                primary = getattr(row, "운동종목_1")
                # 등급형 관련도: 같은 종목이 여러 순위에 오면 높은 등급을 남긴다
                rel_map = {}
                for r in (1, 2, 3):
                    s = getattr(row, f"운동종목_{r}")
                    if isinstance(s, str) and s != "없음":
                        rel_map[s] = max(rel_map.get(s, 0), REL[r])
                records.append({
                    "세그먼트": segment, "fold": fi, "class_id": cid,
                    "primary": primary,
                    "primary_recommendable": primary in recommendable,
                    "rel_map": rel_map,
                    "actual_all": set(rel_map),
                    "class_ranked": ranked_raw.get(cid, []),
                    "class_ranked_new": ranked_new.get(cid, []),
                    "pooled_ranked": pooled,
                    "pooled_ranked_nowalk": pooled_nowalk,
                })
            print(f"  fold {fi + 1}/{K_FOLDS}: train={len(train_part)} test={len(test_part)} "
                  f"entropy={model.get('Entropy', float('nan')):.3f}")

    return records, catalog_sizes


def load_or_collect(refresh=False):
    if CACHE.exists() and not refresh:
        print(f"캐시 사용: {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    payload = collect()
    with open(CACHE, "wb") as f:
        pickle.dump(payload, f)
    print(f"캐시 저장: {CACHE}")
    return payload


# ---------------------------------------------------------------- 집계

VARIANTS = ("raw", "nowalk", "live")


def screen_lists(rec, variant, ranker):
    """그 응답자가 실제로 보는 순서대로의 리스트와, top-K 창을 넓힐 칸 수를 돌려준다.

    raw    : 적합도 행렬 순위 그대로. offset 0.
    nowalk : 기반활동(걷기)을 순위 경쟁에서 아예 뺀 세계. 걷기는 어느 유형에서든 1위라
             양쪽 순위표의 앞자리를 똑같이 채워 격차를 가린다. 걷기를 빼고 나머지 종목만으로
             재면 "유형이 비걷기 종목을 실제로 갈라놓는가"가 드러난다.
             정답 집합과 모집단에서도 걷기를 빼야 공정하다(§aggregate 참조).
    live   : 기반활동이 1번 슬롯, 그 뒤 새로운운동 목록. recommend() 화면 구조.
             **기반활동은 새로운운동 N칸을 소비하지 않는다** — 화면은 걷기 + 새로운운동 N개다.
             eval_offline_recall.py 의 live 절이 걷기를 무조건 hit 처리하는 것과 같은 규약이고,
             그래서 offset 만큼 창을 넓혀야 발표에 실린 수치(HR@3 73.4% / 69.7%)가 재현된다.
    """
    if variant == "raw":
        return (rec["class_ranked"] if ranker == "type" else rec["pooled_ranked"]), 0
    if variant == "nowalk":
        lst = rec["class_ranked"] if ranker == "type" else rec["pooled_ranked"]
        return [s for s in lst if s not in BASELINE_SPORTS], 0
    tail = rec["class_ranked_new"] if ranker == "type" else rec["pooled_ranked_nowalk"]
    base = [s for s in BASELINE_SPORTS if s not in tail]
    return base + tail, len(base)


def truth(rec, variant):
    """그 화면 모델에서 정답으로 칠 수 있는 것 (등급맵, 정답집합)."""
    if variant == "nowalk":
        rel = {k: v for k, v in rec["rel_map"].items() if k not in BASELINE_SPORTS}
        return rel, set(rel)
    return rec["rel_map"], rec["actual_all"]


def population(records, variant):
    """모집단. nowalk 는 걷기를 1순위로 신고한 사람을 뺀다 — 맞힐 수 없는 정답이므로."""
    base = [r for r in records if r["primary_recommendable"]]
    if variant == "nowalk":
        base = [r for r in base if r["primary"] not in BASELINE_SPORTS]
    return base


def aggregate(records, catalog_sizes):
    rows = []
    segments = sorted({r["세그먼트"] for r in records})

    for segment in segments:
        seg_all = [r for r in records if r["세그먼트"] == segment]
        for variant in VARIANTS:
            seg = population(seg_all, variant)
            truths = [truth(r, variant) for r in seg]
            rels = [t[0] for t in truths]
            actuals = [t[1] for t in truths]
            primaries = [r["primary"] for r in seg]

            for ranker, label in (("type", "유형기반"), ("pop", "전체인기도")):
                built = [screen_lists(r, variant, ranker) for r in seg]
                lists = [b[0] for b in built]
                offs = [b[1] for b in built]

                row = {"세그먼트": segment, "N": len(seg), "화면": variant, "지표군": label,
                       "MRR": float(np.mean([reciprocal_rank(l, p)
                                             for l, p in zip(lists, primaries)]))}
                for n in N_LIST:
                    row[f"HR@{n}"] = float(np.mean([hr_at_n(l, n + o, {p})
                                                    for l, o, p in zip(lists, offs, primaries)]))
                    row[f"Recall@{n}"] = float(np.nanmean([recall_at_n(l, n + o, a)
                                                           for l, o, a in zip(lists, offs, actuals)]))
                    row[f"NDCG@{n}"] = float(np.nanmean([ndcg_at_n(l, n + o, m)
                                                         for l, o, m in zip(lists, offs, rels)]))
                rows.append(row)

            # 무작위 기준선 — nowalk 는 카탈로그도 걷기만큼 줄어든다
            csize = catalog_sizes[segment] - (len(BASELINE_SPORTS) if variant == "nowalk" else 0)
            if variant != "live":
                rows.append({"세그먼트": segment, "N": len(seg), "화면": variant,
                             "지표군": "무작위(이론)", "MRR": random_mrr(csize),
                             **{f"HR@{n}": min(1.0, n / csize) for n in N_LIST},
                             **{f"Recall@{n}": min(1.0, n / csize) for n in N_LIST},
                             **{f"NDCG@{n}": np.nan for n in N_LIST}})
    return pd.DataFrame(rows)


def weighted_overall(agg):
    """세그먼트 표본 수 가중평균."""
    out = []
    metric_cols = [c for c in agg.columns if c not in ("세그먼트", "N", "화면", "지표군")]
    for (variant, label), g in agg.groupby(["화면", "지표군"], sort=False):
        row = {"세그먼트": "가중평균", "N": int(g["N"].sum()), "화면": variant, "지표군": label}
        for c in metric_cols:
            w, v = g["N"].values, g[c].values
            mask = ~np.isnan(v)
            row[c] = float(np.average(v[mask], weights=w[mask])) if mask.any() else np.nan
        out.append(row)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 리포트

def fmt(v, metric):
    if np.isnan(v):
        return "—"
    return f"{v:.3f}" if metric == "MRR" or metric.startswith("NDCG") else f"{v:.1%}"


def table(sub, metrics):
    lines = ["| 세그먼트 | N | 지표 | " + " | ".join(metrics) + " |",
             "|---|---|---|" + "---|" * len(metrics)]
    for _, r in sub.iterrows():
        lines.append(f"| {r['세그먼트']} | {r['N']} | {r['지표군']} | "
                     + " | ".join(fmt(r[m], m) for m in metrics) + " |")
    return lines


def report(agg, overall, catalog_sizes):
    full = pd.concat([agg, overall], ignore_index=True)
    lines = [
        "# 평가 방법 1-b — 랭킹 품질 지표 (HR / Recall / MRR / NDCG)", "",
        f"`평가_오프라인재현율.md`와 **완전히 같은 {K_FOLDS}-fold 홀드아웃** 위에서, "
        "순위를 반영하는 지표를 추가로 계산했다. 폴드·시드·적합 절차가 같으므로 "
        "HR 열은 기존 문서와 일치한다.", "",
        "## 지표 정의", "",
        "| 지표 | 정의 | 왜 필요한가 |",
        "|---|---|---|",
        "| HR@K | top-K 안에 1순위 신고 종목이 있으면 1 | 기존 문서가 '재현율'로 부르던 그 값. "
        "정답이 1개라 Recall과 수치가 같지만 이름은 HR이 맞다 |",
        "| Recall@K | (top-K ∩ 신고 1~3순위) / 신고 개수 | '세 개 중 몇 개를 건지나'. "
        "기존 문서의 '1~3순위 중 하나' 행은 분자만 이진이라 Recall이 아니었다 |",
        "| MRR | 1순위 종목이 나온 자리의 역수, 전체 리스트 대상 | K에 안 잘려서 "
        "**HR@8에서 사라지는 순위 품질 차이가 남는다** |",
        "| NDCG@K | 신고 1·2·3순위를 rel 3·2·1 로 두고 DCG/IDCG | 등급형 관련도가 "
        "우리 데이터에 실제로 있다. 학습에 쓰는 rank_weight와 같은 스킴 |", "",
        "## 화면 모델 세 가지", "",
        "- **raw** — 적합도 행렬 순위 그대로(걷기 포함). 순위 지표의 기준선.",
        "- **nowalk** — 걷기를 순위 경쟁에서 아예 뺀 세계. 걷기는 어느 유형에서든 1위라 "
        "양쪽 순위표의 앞자리를 똑같이 채워 격차를 가린다. 걷기를 빼면 유형이 "
        "**비걷기 종목을 실제로 갈라놓는지**가 드러난다. 순위표·정답집합·모집단 세 곳 모두에서 "
        "걷기를 빼야 공정하므로, 걷기를 1순위로 신고한 응답자는 N에서 제외된다.",
        "- **live** — `recommend()` 운영 로직. 기반활동(걷기)이 항상 1번 슬롯, "
        "그 뒤에 Lift 0.5로 재점수화한 새로운운동. 사용자가 실제로 보는 순서다.", "",
        "**MRR·NDCG는 raw 기준으로 읽는 것을 권한다.** live는 걷기가 1번 슬롯에 고정돼서 "
        "걷기를 1순위로 신고한 사람 전원이 RR=1.0을 받는다 — 화면 재현으로는 정확하지만 "
        "순위 알고리즘의 변별력을 재는 데는 걷기 비중이 그대로 점수가 된다.", "",
    ]

    for variant, title in (("raw", "적합도 행렬 순위 그대로 (raw)"),
                           ("nowalk", "걷기를 순위 경쟁에서 뺀 경우 (nowalk)"),
                           ("live", "운영 화면 순서 (live — 기반활동 + 새로운운동)")):
        sub = full[full["화면"] == variant]
        lines.append(f"## {title}")
        lines.append("")
        lines += table(sub, ["MRR"] + [f"NDCG@{n}" for n in N_LIST])
        lines.append("")
        lines += table(sub, [f"HR@{n}" for n in N_LIST] + [f"Recall@{n}" for n in N_LIST])
        lines.append("")

    lines += [
        "## 참고", "",
        f"- 폴드 {K_FOLDS} / EM 시작 {N_INIT} / 시드 {SEED} — `eval_offline_recall.py`와 동일",
        "- 카탈로그 크기: " + ", ".join(f"{k} {v}개" for k, v in catalog_sizes.items()),
        "- 무작위(이론) MRR = H_C / C (C=카탈로그 크기). NDCG 무작위 기준선은 "
        "응답자별 등급 분포에 의존해 닫힌 식이 없어 생략했다.",
        "- 대상은 '추천가능 카탈로그 안의 종목을 1순위로 신고한 응답자'다 "
        "(`평가_결과_요약.md`의 핵심 표와 같은 모집단).",
        "- 이 평가가 재는 것은 **선호 적합도 행렬의 종목 순위**다. 체력축·안전필터·"
        "설문 보정(recommend.py ③④)은 포함하지 않는다.",
        "- '신고한 종목'은 설문의 '주로 참여하는 체육활동'이지 앱에서의 클릭·수락이 아니다.",
    ]

    out = DOCS / "평가_랭킹지표.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n저장: {out}")

    payload = {"segments": agg.to_dict("records"), "overall": overall.to_dict("records"),
               "catalog_sizes": catalog_sizes, "n_list": N_LIST}
    (DATA / "ranking_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"저장: {DATA / 'ranking_metrics.json'}")
    return full


if __name__ == "__main__":
    recs, sizes = load_or_collect(refresh="--refresh" in sys.argv)
    agg_df = aggregate(recs, sizes)
    full_df = report(agg_df, weighted_overall(agg_df), sizes)
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(full_df.to_string(index=False))
