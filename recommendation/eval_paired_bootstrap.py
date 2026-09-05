"""평가 방법 1-c — 유형기반 vs 전체인기도 격차의 대응표본 부트스트랩.

지표값만으로는 "격차가 표본 노이즈와 구분되는가"를 답할 수 없다. 같은 홀드아웃 응답자를
두 순위표로 각각 채점하므로 차이는 **대응표본**이고, 응답자 단위 부트스트랩으로 CI를 낸다.

두 화면 모델을 나란히 본다.
  raw    — 걷기 포함. 걷기는 어느 유형에서든 1위라 양쪽 순위표 앞자리를 똑같이 채운다.
  nowalk — 걷기를 순위 경쟁에서 뺀 세계. 유형이 비걷기 종목을 실제로 갈라놓는지가 드러난다.

한계: 폴드 재적합 변동은 이 CI에 안 들어간다(폴드는 5개로 고정). 한 세그먼트 안의 응답자들은
같은 순위표 몇 개를 공유하므로 완전한 독립 표본은 아니다 — CI는 다소 낙관적으로 읽어야 한다.

산출: docs/평가_격차_유의성.md, recommendation/data/paired_bootstrap.json

실행: python recommendation/eval_paired_bootstrap.py
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from eval_ranking_metrics import (
    CACHE, DATA, DOCS, hr_at_n, ndcg_at_n, population, recall_at_n, reciprocal_rank,
    screen_lists, truth,
)

sys.stdout.reconfigure(encoding="utf-8")

B = 10000
SEED = 0
METRICS = ["MRR", "HR@3", "NDCG@3", "Recall@3", "HR@8", "Recall@8"]
VARIANTS = ["raw", "nowalk"]


def score(lst, off, rec, rel, act, metric):
    if metric == "MRR":
        return reciprocal_rank(lst, rec["primary"])
    kind, n = metric.split("@")
    n = int(n) + off
    if kind == "HR":
        return hr_at_n(lst, n, {rec["primary"]})
    if kind == "Recall":
        return recall_at_n(lst, n, act)
    return ndcg_at_n(lst, n, rel)


def run():
    with open(CACHE, "rb") as f:
        records = pickle.load(f)[0]
    rng = np.random.default_rng(SEED)
    segments = sorted({r["세그먼트"] for r in records})
    out = []

    for variant in VARIANTS:
        for scope in segments + ["전체"]:
            sub = population([r for r in records
                              if scope == "전체" or r["세그먼트"] == scope], variant)
            truths = [truth(r, variant) for r in sub]
            tb = [screen_lists(r, variant, "type") for r in sub]
            pb = [screen_lists(r, variant, "pop") for r in sub]
            for m in METRICS:
                t = np.array([score(l, o, r, tr[0], tr[1], m)
                              for (l, o), r, tr in zip(tb, sub, truths)], dtype=float)
                p = np.array([score(l, o, r, tr[0], tr[1], m)
                              for (l, o), r, tr in zip(pb, sub, truths)], dtype=float)
                d = t - p
                d = d[~np.isnan(d)]
                boot = d[rng.integers(0, len(d), size=(B, len(d)))].mean(axis=1)
                lo, hi = np.percentile(boot, [2.5, 97.5])
                out.append({
                    "화면": variant, "세그먼트": scope, "N": len(sub), "지표": m,
                    "유형기반": float(np.nanmean(t)), "전체인기도": float(np.nanmean(p)),
                    "격차": float(d.mean()), "lo": float(lo), "hi": float(hi),
                    "판정": "유의" if lo > 0 else "인기도 우위" if hi < 0 else "구분 안 됨",
                })
    return out


def report(rows):
    (DATA / "paired_bootstrap.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    pct = {"HR@3", "HR@8", "Recall@3", "Recall@8"}

    def f(v, m):
        return f"{v:+.1%}" if m in pct else f"{v:+.3f}"

    def a(v, m):
        return f"{v:.1%}" if m in pct else f"{v:.3f}"

    lines = [
        "# 평가 방법 1-c — 격차의 유의성 (대응표본 부트스트랩)", "",
        "유형기반과 전체인기도의 격차가 표본 노이즈와 구분되는지를 잰다. 같은 홀드아웃 응답자를 "
        "두 순위표로 각각 채점하므로 차이는 대응표본이고, 응답자 단위로 "
        f"{B:,}회 재표본해 95% CI를 냈다.", "",
        "**읽는 법**: CI가 0을 걸치면 그 격차는 이 표본으로는 방향을 말할 수 없다. "
        "n이 크면 작은 차이도 유의하게 나오므로, **유의성과 크기를 따로 읽어야 한다.**", "",
    ]
    for variant, title in (("raw", "걷기 포함 (raw)"),
                           ("nowalk", "걷기를 순위 경쟁에서 뺀 경우 (nowalk)")):
        lines += [f"## {title}", "",
                  "| 세그먼트 | N | 지표 | 유형기반 | 전체인기도 | 격차 | 95% CI | 판정 |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in [x for x in rows if x["화면"] == variant]:
            m = r["지표"]
            lines.append(
                f"| {r['세그먼트']} | {r['N']} | {m} | {a(r['유형기반'], m)} | "
                f"{a(r['전체인기도'], m)} | **{f(r['격차'], m)}** | "
                f"[{f(r['lo'], m)}, {f(r['hi'], m)}] | {r['판정']} |")
        lines.append("")

    lines += [
        "## 한계", "",
        "- 폴드 재적합 변동은 이 CI에 포함되지 않는다 (폴드는 5개로 고정).",
        "- 한 세그먼트 안의 응답자들은 같은 순위표 몇 개(클래스 수만큼)를 공유하므로 완전한 "
        "독립 표본이 아니다. CI는 실제보다 다소 좁게(낙관적으로) 나온다.",
        f"- 재표본 {B:,}회 / 시드 {SEED}.",
    ]
    out = DOCS / "평가_격차_유의성.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {out}")
    print(f"저장: {DATA / 'paired_bootstrap.json'}")


if __name__ == "__main__":
    rows = run()
    report(rows)
    for r in rows:
        if r["세그먼트"] == "전체":
            print(f"{r['화면']:<7} {r['지표']:<9} {r['격차']:+.4f} "
                  f"[{r['lo']:+.4f}, {r['hi']:+.4f}]  {r['판정']}")
