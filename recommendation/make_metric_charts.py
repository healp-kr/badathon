"""평가_랭킹지표.md 용 차트 렌더.

입력: recommendation/data/ranking_metrics.json (eval_ranking_metrics.py 가 생성)
출력: docs/img/fig1_mrr.png … fig4_recall.png

팀 공유는 Notion 붙여넣기용 .md 이고 이미지는 data URI 로 안 붙으므로 PNG 를 따로 낸다.
PNG 는 다크모드 전환이 불가능하므로 라이트 서피스(#fcfcfb) 단일 모드로 확정해 렌더한다.

색: dataviz 기본 팔레트 슬롯 1·2 (blue/orange) — 2계열 all-pairs 전 검사 통과
    (CVD ΔE 24.7 / normal ΔE 33.6 / 대비 모두 ≥3:1).
    무작위 기준선은 계열이 아니라 컨텍스트라 muted 잉크 그레이를 쓰고 항상 직접 라벨을 단다.
꺾은선의 값 라벨은 양 끝점에만 단다(선택적 직접 라벨). 교차 구간에서 위/아래 배치는
그 지점에서 실제로 높은 쪽이 위로 가도록 값으로 결정한다 — 고정 오프셋은 교차점에서 뒤집힌다.

실행: python recommendation/make_metric_charts.py
"""
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
TYPE_C = "#2a78d6"   # 슬롯 1 — 유형기반
POP_C = "#eb6834"    # 슬롯 2 — 전체인기도

SEG_ORDER = ["성인_남성", "성인_여성", "노인_남성", "노인_여성", "가중평균"]
K_LIST = [3, 5, 8]

plt.rcParams.update({
    "font.family": "Malgun Gothic",
    "axes.unicode_minus": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "font.size": 11,
})


def load():
    raw = json.loads((HERE / "data" / "ranking_metrics.json").read_text(encoding="utf-8"))
    return {(r["세그먼트"], r["화면"], r["지표군"]): r for r in raw["segments"] + raw["overall"]}


def titles(fig, title, subtitle, top=0.85):
    """제목·부제를 figure 좌표에 고정하고 축 영역을 그 아래로 밀어낸다."""
    fig.tight_layout(rect=(0, 0, 1, top))
    fig.text(0.012, 0.975, title, fontsize=13.5, color=INK, fontweight="bold",
             va="top", ha="left")
    fig.text(0.012, 0.905, subtitle, fontsize=9.5, color=MUTED, va="top", ha="left")


def style(ax, ylabel=None, pct=False):
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.xaxis.grid(False)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(length=0)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    if pct:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))


def bar_labels(ax, bars, vals, fmt="{:.3f}", pad=0.012, size=9):
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + pad, fmt.format(v),
                ha="center", va="bottom", fontsize=size, color=INK2)


def endpoint_labels(ax, ks, series, fmt="{:.1%}", gap=0.011, size=9.5):
    """양 끝점에만 값 라벨. 그 지점에서 높은 계열이 위, 낮은 계열이 아래."""
    for i in (0, len(ks) - 1):
        ranked = sorted(series, key=lambda s: -s["vals"][i])
        for pos, s in enumerate(ranked):
            v = s["vals"][i]
            above = pos == 0
            ax.text(ks[i], v + (gap if above else -gap), fmt.format(v),
                    ha="center", va="bottom" if above else "top",
                    fontsize=size, color=INK2)


# ── fig 1 — MRR 세그먼트별 -------------------------------------------------------
# 막대그래프. 무작위 기준선은 뺐다 — 0.14~0.19가 축 아래를 잡아먹어 정작 비교할 두 막대가
# 붙어 보였다. **세로축은 0에서 시작한다**: 막대는 길이로 값을 말하므로 축을 자르면
# +0.003(노인 남성)까지 유의미한 차이처럼 보이게 만든다. 차이 강조는 축을 자르는 대신
# 막대 쌍 위에 격차 브래킷을 직접 달아서 한다.
def wave_break(ax, y_upper, y_lower, cycles=13):
    """교과서식 물결선 — 막대 중간을 끊어 그 구간이 생략됐음을 표시한다.

    막대는 0에서 나와 짧게 올라가다 물결에서 끊기고, 물결 위에서 다시 이어져 실제 값까지
    간다. 0 눈금이 축에 그대로 남으므로 "0부터 시작하지 않는 그래프"가 아니라
    "중간을 생략한 그래프"가 된다 — 국내 교과서·통계 자료의 표준 표기다.
    """
    x0, x1 = ax.get_xlim()
    xw = np.linspace(x0, x1, 900)
    amp = (y_upper - y_lower) * 0.30
    phase = np.linspace(0, cycles * 2 * np.pi, 900)
    for y in (y_upper, y_lower):
        ax.plot(xw, y + amp * np.sin(phase), color=AXIS, linewidth=1.3,
                zorder=7, clip_on=False, solid_capstyle="round")
    ax.set_xlim(x0, x1)


def fig1(idx):
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    xs = list(range(len(SEG_ORDER)))
    w = 0.32
    # 물결 위는 실제 눈금(wave_hi = 0.30부터), 물결 아래는 0에서 나온 짧은 밑동.
    lo_cut, hi_lim = 0.30, 0.88
    span = hi_lim - lo_cut
    wave_hi = lo_cut
    wave_lo = lo_cut - 0.034 * span
    zero_y = lo_cut - 0.082 * span       # 0 눈금 자리 (밑동이 여기서 나온다)

    tv = [idx[(s, "raw", "유형기반")]["MRR"] for s in SEG_ORDER]
    pv = [idx[(s, "raw", "전체인기도")]["MRR"] for s in SEG_ORDER]

    for vals, color, key, off in ((tv, TYPE_C, "유형기반", -w / 2),
                                  (pv, POP_C, "전체인기도", w / 2)):
        px = [x + off for x in xs]
        # 밑동 — 0에서 물결 아래까지
        ax.bar(px, wave_lo - zero_y, w * 0.9, bottom=zero_y, color=color,
               edgecolor=SURFACE, linewidth=2, zorder=3)
        # 본체 — 물결 위에서 실제 값까지
        bars = ax.bar(px, [v - wave_hi for v in vals], w * 0.9, bottom=wave_hi,
                      label=key, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
        bar_labels(ax, bars, vals, pad=0.013 * span, size=9.5)

    # 격차 브래킷 — 축을 잘라 커 보이는 차이 대신 실제 숫자를 읽게 한다
    for x, t, p in zip(xs, tv, pv):
        top = max(t, p) + 0.089 * span
        ax.plot([x - w / 2, x - w / 2, x + w / 2, x + w / 2],
                [t + 0.064 * span, top, top, p + 0.064 * span],
                color=MUTED, linewidth=1, zorder=2)
        ax.text(x, top + 0.009 * span, f"{t - p:+.3f}", ha="center", va="bottom",
                fontsize=10, color=INK, fontweight="bold")

    data_ticks = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
    ax.set_xticks(xs)
    ax.set_xticklabels([s.replace("_", " ") for s in SEG_ORDER], color=INK2, fontsize=10.5)
    style(ax, ylabel="MRR (1순위 종목의 역순위 평균)")
    ax.set_ylim(zero_y - 0.020 * span, hi_lim)
    # 눈금은 데이터 구간 + 맨 아래 0. 격자는 데이터 구간에만 긋는다 — 0 자리에 격자가 가면
    # 물결 아래가 또 하나의 눈금 칸처럼 보인다.
    ax.set_yticks(data_ticks + [zero_y])
    ax.set_yticklabels([f"{t:.2f}" for t in data_ticks] + ["0"])
    ax.yaxis.grid(False)
    for t in data_ticks:
        ax.axhline(t, color=GRID, linewidth=1, zorder=1)
    ax.axhline(zero_y, color=AXIS, linewidth=1.3, zorder=5)
    ax.spines["bottom"].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=10, ncol=2)
    wave_break(ax, wave_hi, wave_lo)

    titles(fig, "MRR — 유형 기반이 정답을 얼마나 더 위에 올리는가",
           "걷기 포함(raw) · 물결선 아래(0 ~ 0.30)를 생략했다 — 막대 길이의 비율은 실제 "
           "비율이 아니므로 숫자로 읽을 것 · 무작위 기준선(0.144~0.194)은 제외", top=0.86)
    fig.savefig(IMG / "fig1_mrr.png", dpi=200)
    plt.close(fig)


# ── fig 2 — HR 는 K 가 커지면 신호를 잃고, MRR 은 남는다 --------------------------
def fig2(idx):
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11.5, 4.8),
                                   gridspec_kw={"width_ratios": [1.6, 1]})

    series = []
    for key, color in (("유형기반", TYPE_C), ("전체인기도", POP_C)):
        vals = [idx[("가중평균", "raw", key)][f"HR@{k}"] for k in K_LIST]
        axl.plot(K_LIST, vals, marker="o", markersize=9, linewidth=2, color=color,
                 label=key, zorder=3, markeredgecolor=SURFACE, markeredgewidth=2)
        series.append({"vals": vals, "color": color})
    endpoint_labels(axl, K_LIST, series)

    axl.set_xticks(K_LIST)
    axl.set_xticklabels([f"K={k}" for k in K_LIST], color=INK2, fontsize=10.5)
    axl.set_xlim(2.6, 8.6)
    style(axl, ylabel="HR@K", pct=True)
    axl.set_ylim(0.575, 0.93)
    axl.set_title("HR@K — K가 커질수록 붙고, @8에서 역전된다", fontsize=12,
                  color=INK, pad=10, loc="left")
    axl.legend(frameon=False, loc="upper left", fontsize=10)
    axl.text(8.45, 0.755, "여기서 유형 정보의 이득이\n숫자상 사라진다",
             fontsize=9.5, color=INK2, ha="right", va="top", linespacing=1.5)

    vals = [idx[("가중평균", "raw", k)]["MRR"] for k in ("유형기반", "전체인기도")]
    bars = axr.bar([0, 1], vals, 0.5, color=[TYPE_C, POP_C], edgecolor=SURFACE,
                   linewidth=2, zorder=3)
    bar_labels(axr, bars, vals, pad=0.01, size=11)
    axr.axhline(vals[1], xmin=0.08, xmax=0.92, color=INK2, linewidth=1,
                linestyle=(0, (4, 3)), zorder=4)
    axr.text(0.5, (vals[0] + vals[1]) / 2 + 0.004, f"+{vals[0] - vals[1]:.3f}",
             ha="center", va="bottom", fontsize=11, color=INK, fontweight="bold")
    axr.set_xticks([0, 1])
    axr.set_xticklabels(["유형기반", "전체인기도"], color=INK2, fontsize=10.5)
    style(axr, ylabel="MRR")
    axr.set_ylim(0, 0.72)
    axr.set_title("MRR — 같은 데이터에서 격차가 남는다", fontsize=12, color=INK,
                  pad=10, loc="left")

    titles(fig, "지표를 바꾸면 결론이 바뀐다 — 같은 폴드, 같은 응답자 (가중평균 n=6,273)",
           "걷기 포함(raw) · 왼쪽은 top-K 안에 들었는지만 보는 HR, 오른쪽은 몇 번째에 들었는지를 보는 MRR",
           top=0.85)
    fig.savefig(IMG / "fig2_hr_vs_mrr.png", dpi=200)
    plt.close(fig)


# ── fig 3 — NDCG@K 세그먼트별 ----------------------------------------------------
def fig3(idx):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    xs = list(range(len(SEG_ORDER)))
    w = 0.34
    for ax, k in zip(axes, (3, 8)):
        for i, (key, color) in enumerate((("유형기반", TYPE_C), ("전체인기도", POP_C))):
            vals = [idx[(s, "raw", key)][f"NDCG@{k}"] for s in SEG_ORDER]
            bars = ax.bar([x + (-w / 2 if i == 0 else w / 2) for x in xs], vals, w * 0.9,
                          label=key, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
            bar_labels(ax, bars, vals, pad=0.014, size=8.5)
        ax.set_xticks(xs)
        ax.set_xticklabels([s.replace("_", " ") for s in SEG_ORDER], color=INK2,
                           fontsize=9.5, rotation=18, ha="right")
        style(ax, ylabel="NDCG" if k == 3 else None)
        ax.set_ylim(0, 0.98)
        ax.set_title(f"NDCG@{k}", fontsize=12, color=INK, pad=10, loc="left")
    axes[0].legend(frameon=False, loc="upper left", fontsize=10, ncol=2)
    titles(fig, "NDCG — 신고 1·2·3순위를 rel 3·2·1로 둔 등급형 평가",
           "걷기 포함(raw) · K=3에서 벌린 격차(+0.035)가 K=8에서는 +0.012로 줄어든다 · 높을수록 좋음",
           top=0.85)
    fig.savefig(IMG / "fig3_ndcg.png", dpi=200)
    plt.close(fig)


# ── fig 4 — Recall@K: 정직하게 밝혀야 하는 반대 방향 ------------------------------
def fig4(idx):
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    series = []
    for key, color in (("유형기반", TYPE_C), ("전체인기도", POP_C)):
        vals = [idx[("가중평균", "raw", key)][f"Recall@{k}"] for k in K_LIST]
        ax.plot(K_LIST, vals, marker="o", markersize=9, linewidth=2, color=color,
                label=key, zorder=3, markeredgecolor=SURFACE, markeredgewidth=2)
        series.append({"vals": vals, "color": color})
    endpoint_labels(ax, K_LIST, series)

    ax.axvline(5, color=AXIS, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.text(5.12, 0.565, "K=5부터 역전", fontsize=9.5, color=INK2, ha="left")

    ax.set_xticks(K_LIST)
    ax.set_xticklabels([f"K={k}" for k in K_LIST], color=INK2, fontsize=10.5)
    ax.set_xlim(2.6, 8.6)
    style(ax, ylabel="Recall@K (신고 1~3순위 중 건진 비율)", pct=True)
    ax.set_ylim(0.545, 0.885)
    ax.legend(frameon=False, loc="lower right", fontsize=10)
    titles(fig, "Recall@K — 다양성 커버리지는 인기도 나열이 앞선다",
           "걷기 포함(raw) · 가중평균 n=6,273 · 유형 기반의 우위가 모든 지표에서 성립하지는 않는다", top=0.86)
    fig.savefig(IMG / "fig4_recall.png", dpi=200)
    plt.close(fig)


# ── fig 5 — 걷기를 순위 경쟁에서 빼면 격차가 어떻게 변하는가 ----------------------
# raw → nowalk 는 항목별 before→after 이므로 계열 색이 아니라 한 색 두 단계를 쓴다.
# (figs 1~4 의 blue/orange 는 유형기반/전체인기도를 뜻하므로 여기서 재사용하면 안 된다.)
RAW_C, NOWALK_C = "#6da7ec", "#184f95"   # 2단계 파랑 — ordinal 검증 통과, 밝은 쪽은 직접 라벨로 해소
GAP_ROWS = ["성인_남성", "성인_여성", "노인_남성", "노인_여성", "전체"]


def fig5():
    rows = json.loads((HERE / "data" / "paired_bootstrap.json").read_text(encoding="utf-8"))
    idx = {(r["화면"], r["세그먼트"], r["지표"]): r for r in rows}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.0), sharey=True)
    ys = list(range(len(GAP_ROWS)))[::-1]
    h = 0.34

    for ax, metric, unit in ((axes[0], "HR@3", "pct"), (axes[1], "MRR", "idx")):
        for i, (variant, color, name) in enumerate(((("raw"), RAW_C, "걷기 포함 (raw)"),
                                                    ("nowalk", NOWALK_C, "걷기 제외 (nowalk)"))):
            vals = [idx[(variant, s, metric)]["격차"] for s in GAP_ROWS]
            los = [idx[(variant, s, metric)]["lo"] for s in GAP_ROWS]
            his = [idx[(variant, s, metric)]["hi"] for s in GAP_ROWS]
            off = h / 2 if i == 0 else -h / 2
            pos = [y + off for y in ys]
            ax.barh(pos, vals, h * 0.88, color=color, label=name, zorder=3,
                    edgecolor=SURFACE, linewidth=2)
            ax.errorbar(vals, pos, xerr=[[v - l for v, l in zip(vals, los)],
                                         [hi - v for v, hi in zip(vals, his)]],
                        fmt="none", ecolor=INK2, elinewidth=1.2, capsize=3, zorder=4)
            for y, v, hi, lo in zip(pos, vals, his, los):
                txt = f"{v * 100:+.1f}%p" if unit == "pct" else f"{v:+.3f}"
                at = hi if v >= 0 else lo
                ax.text(at + (0.004 if unit == "pct" else 0.004) * (1 if v >= 0 else -1),
                        y, txt, va="center", ha="left" if v >= 0 else "right",
                        fontsize=8.5, color=INK2)

        ax.axvline(0, color=INK2, linewidth=1.2, zorder=5)
        ax.set_yticks(ys)
        ax.set_yticklabels([s.replace("_", " ") for s in GAP_ROWS], color=INK2, fontsize=10.5)
        ax.set_axisbelow(True)
        ax.xaxis.grid(True, color=GRID, linewidth=1)
        ax.yaxis.grid(False)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
        if unit == "pct":
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0%}"))
            ax.set_xlim(-0.135, 0.185)
            ax.set_xlabel("HR@3 격차 (유형기반 - 전체인기도, %p)", color=INK2, fontsize=10)
        else:
            ax.set_xlim(-0.10, 0.155)
            ax.set_xlabel("MRR 격차 (유형기반 - 전체인기도)", color=INK2, fontsize=10)
        ax.set_title({"HR@3": "HR@3", "MRR": "MRR"}[metric], fontsize=12, color=INK,
                     pad=10, loc="left")

    axes[0].legend(frameon=False, loc="lower left", fontsize=10)
    titles(fig, "걷기를 순위 경쟁에서 빼면 — 세그먼트별 격차와 95% 신뢰구간",
           "막대가 0선 오른쪽이고 오차막대가 0을 안 걸쳐야 유형 정보가 실제로 이득이다 · "
           "대응표본 부트스트랩 10,000회", top=0.85)
    fig.savefig(IMG / "fig5_nowalk_gap.png", dpi=200)
    plt.close(fig)


# ── 걷기 제외(nowalk) 단일 지표 막대 ---------------------------------------------
# fig1 과 같은 형태지만 nowalk 수치이고 물결선이 없다. 물결선을 빼면 절단 표시가 사라지므로
# 세로축은 0에서 시작한다 — 표시 없이 자르면 그냥 왜곡이다.
# 걷기 제외는 걷기를 1순위로 신고한 응답자가 빠진 부분집합이라 세그먼트별 N을 같이 적는다.
# 제목·부제 없이 슬라이드에 바로 얹는 용도라, 어느 지표인지는 y축 라벨이 혼자 짊어진다.
def nowalk_bar(idx, metric, ylabel, hi_lim, fname):
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    xs = list(range(len(SEG_ORDER)))
    w = 0.32

    tv = [idx[(s, "nowalk", "유형기반")][metric] for s in SEG_ORDER]
    pv = [idx[(s, "nowalk", "전체인기도")][metric] for s in SEG_ORDER]
    ns = [idx[(s, "nowalk", "유형기반")]["N"] for s in SEG_ORDER]

    for vals, color, key, off in ((tv, TYPE_C, "유형기반", -w / 2),
                                  (pv, POP_C, "전체인기도", w / 2)):
        bars = ax.bar([x + off for x in xs], vals, w * 0.9, label=key, color=color,
                      edgecolor=SURFACE, linewidth=2, zorder=3)
        bar_labels(ax, bars, vals, fmt="{:.1%}", pad=0.013 * hi_lim, size=9.5)

    ax.set_xticks(xs)
    ax.set_xticklabels([f"{s.replace('_', ' ')}\n(n={n:,})" for s, n in zip(SEG_ORDER, ns)],
                       color=INK2, fontsize=10)
    style(ax, ylabel=ylabel, pct=True)
    ax.set_ylim(0, hi_lim)
    ax.legend(frameon=False, loc="upper left", fontsize=10, ncol=2)

    fig.tight_layout()
    fig.savefig(IMG / fname, dpi=200)
    plt.close(fig)


# ── 걷기 포함(raw) 단일 지표 막대 -----------------------------------------------
# nowalk_bar 의 걷기 포함 짝. 적합도 행렬 순위 그대로(raw)이고, 모집단은 걷기를
# 1순위로 신고한 응답자까지 포함한 전체다(세그먼트별 N 병기). 물결선 없이 0에서 시작한다.
def raw_bar(idx, metric, ylabel, hi_lim, fname):
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    xs = list(range(len(SEG_ORDER)))
    w = 0.32

    tv = [idx[(s, "raw", "유형기반")][metric] for s in SEG_ORDER]
    pv = [idx[(s, "raw", "전체인기도")][metric] for s in SEG_ORDER]
    ns = [idx[(s, "raw", "유형기반")]["N"] for s in SEG_ORDER]

    for vals, color, key, off in ((tv, TYPE_C, "유형기반", -w / 2),
                                  (pv, POP_C, "전체인기도", w / 2)):
        bars = ax.bar([x + off for x in xs], vals, w * 0.9, label=key, color=color,
                      edgecolor=SURFACE, linewidth=2, zorder=3)
        bar_labels(ax, bars, vals, fmt="{:.1%}", pad=0.013 * hi_lim, size=9.5)

    ax.set_xticks(xs)
    ax.set_xticklabels([f"{s.replace('_', ' ')}\n(n={n:,})" for s, n in zip(SEG_ORDER, ns)],
                       color=INK2, fontsize=10)
    style(ax, ylabel=ylabel, pct=True)
    ax.set_ylim(0, hi_lim)
    ax.legend(frameon=False, loc="upper left", fontsize=10, ncol=2)

    fig.tight_layout()
    fig.savefig(IMG / fname, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    data = load()
    fig1(data)
    nowalk_bar(data, "MRR", "MRR", 0.70, "fig6_mrr_nowalk.png")
    nowalk_bar(data, "HR@1", "HR@1 (1순위 신고 종목을 맨 위에서 맞힌 비율)",
               0.46, "fig7_hr1_nowalk.png")
    nowalk_bar(data, "HR@2", "HR@2 (1순위 신고 종목이 상위 2칸 안에 든 비율)",
               0.64, "fig8_hr2_nowalk.png")
    raw_bar(data, "HR@2", "HR@2 (1순위 신고 종목이 상위 2칸 안에 든 비율, 걷기 포함)",
            0.85, "fig9_hr2_raw.png")
    fig2(data)
    fig3(data)
    fig4(data)
    fig5()
    for p in sorted(IMG.glob("fig*.png")):
        print(f"저장: {p}  ({p.stat().st_size // 1024} KB)")
