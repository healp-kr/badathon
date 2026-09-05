"""배정 층 파라미터 추출 (A1 + A3).

원본 데이터에서 앱이 쓸 파라미터만 뽑아 JSON으로 저장한다.
이 스크립트는 배포 대상이 아니다 — 산출된 params/*.json 만 앱이 참조한다.

실행: python build_params.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "analysis" / "최종 클러스터링 결과"
OUT = Path(__file__).resolve().parent / "params"
OUT.mkdir(exist_ok=True)

FINAL_K = {"성인_남성": 4, "성인_여성": 3, "노인_남성": 2, "노인_여성": 3}

CLASS_NAMES = {
    "성인_남성_LC1": "저빈도 야외·구기형",
    "성인_남성_LC2": "저녁 고빈도 헬스형",
    "성인_남성_LC3": "일정 유동적 복합운동형",
    "성인_남성_LC4": "청년 고강도 구기형",
    "성인_여성_LC1": "저녁 체형관리 운동형",
    "성인_여성_LC2": "저빈도 유동적 생활운동형",
    "성인_여성_LC3": "중고빈도 건강관리형",
    "노인_남성_LC1": "상시 고빈도 저강도 걷기형",
    "노인_남성_LC2": "휴일 오전 야외 등산·낚시형",
    "노인_여성_LC1": "고빈도 저강도 걷기형",
    "노인_여성_LC2": "오전 중강도 복합운동형",
    "노인_여성_LC3": "저빈도 오전 걷기·등산형",
}

# 체력 5축 — 성인과 노인의 구성이 다르다
AXES = {
    "성인": ["z_근력", "z_근지구력", "z_순발력", "z_유연성", "z_신체조성"],
    "노인": ["z_근력", "z_하지근기능", "z_협응력/동적평형", "z_유연성", "z_신체조성"],
}
# 자가평가 문항 ↔ 축 (신체조성은 문항이 없고 키·몸무게로 추정)
AXIS_ITEM = {
    "z_근력": "근력",
    "z_근지구력": "근지구력",
    "z_순발력": "순발력",
    "z_하지근기능": "하지근기능",
    "z_협응력/동적평형": "협응력평형",
    "z_유연성": "유연성",
    "z_신체조성": None,
}
N_LEVELS = 5  # 자가평가 5단계


# ------------------------------------------------------------------
# A1. 선호축 LCA 파라미터
# ------------------------------------------------------------------
def build_preference():
    src = (RESULT / "lca_refit_local.py").read_text(encoding="utf-8")
    ns = {"__file__": str(RESULT / "lca_refit_local.py")}  # 원본이 상대경로를 __file__ 로 잡는다
    exec(compile(src.split("# ===== CELL 4")[0], "prep", "exec"), ns)

    analysis_df = ns["analysis_df"]
    indicators = ns["INDICATORS"]
    fit_lca = ns["fit_lca"]

    segments = {}
    for segment, part in analysis_df.groupby("세그먼트"):
        model = fit_lca(part, indicators, n_classes=FINAL_K[segment], n_init=20)

        classes = []
        for c in range(model["n_classes"]):
            class_id = f"{segment}_LC{c + 1}"
            classes.append({
                "class_id": class_id,
                "name": CLASS_NAMES[class_id],
                "prob": float(model["class_prob"][c]),
            })

        segments[segment] = {
            "n_classes": model["n_classes"],
            "class_prob": [float(p) for p in model["class_prob"]],
            "classes": classes,
            "indicators": {
                var: {
                    "levels": list(model["levels"][var]),
                    # response_prob[클래스][범주]
                    "response_prob": model["response_prob"][j].tolist(),
                }
                for j, var in enumerate(indicators)
            },
            "n_train": int(len(part)),
            "entropy": float(model["Entropy"]),
        }
        print(f"  {segment}: k={model['n_classes']}, n={len(part)}, entropy={model['Entropy']:.3f}")

    payload = {
        "indicator_order": indicators,
        "segments": segments,
        "note": "log P(c|x) ∝ log class_prob[c] + Σ_j log response_prob[j][c][x_j]. "
                "응답이 없거나 levels에 없는 항목은 해당 항을 건너뛴다(주변화).",
    }
    (OUT / "preference_model.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return payload


# ------------------------------------------------------------------
# A3. 체력축 중심 · 신체조성 회귀 · 분위 대표값
# ------------------------------------------------------------------
def build_fitness():
    d = pd.read_csv(RESULT / "fit2023_segments_final_v2.csv")
    groups = {}

    for label, s in d.groupby("하위집단_라벨"):
        key = "성인" if label.startswith("성인") else "노인"
        axes = AXES[key]
        Z = s[axes].values

        # 중심 = 세그먼트별 축 평균 (K-means 중심과 동일)
        centroid_df = s.groupby("체력세그먼트")[axes].mean()
        centroids = {
            name: [float(v) for v in row]
            for name, row in zip(centroid_df.index, centroid_df.values)
        }
        share = (s["체력세그먼트"].value_counts(normalize=True) * 100).round(1).to_dict()

        # 신체조성 축: 키·몸무게·BMI 회귀 (연령대 셀별, 표본 부족 시 하위집단 통합)
        jbc = axes.index("z_신체조성")
        feats = ["신장(cm)", "체중(kg)", "BMI(kg/㎡)"]
        pooled, r2_pooled = _fit_linear(s, feats, Z[:, jbc])
        by_age = {}
        for band, part in s.groupby("측정연령수"):
            if len(part) < 300:
                continue
            zb = part[axes].values[:, jbc]
            beta, _ = _fit_linear(part, feats, zb)
            if beta is not None:
                by_age[str(int(band))] = beta

        # 자가평가 단계 → z 대표값: 실제 분포의 분위 평균 (정규 가정보다 정확)
        reps = {}
        for j, axis in enumerate(axes):
            item = AXIS_ITEM[axis]
            if item is None:
                continue
            col = Z[:, j]
            cuts = np.nanquantile(col, np.arange(1, N_LEVELS) / N_LEVELS)
            level = np.digitize(col, cuts)
            reps[item] = [float(np.nanmean(col[level == k])) for k in range(N_LEVELS)]

        groups[label] = {
            "axes": axes,
            "axis_item": {a: AXIS_ITEM[a] for a in axes},
            "centroids": centroids,
            "share_pct": {k: float(v) for k, v in share.items()},
            "body_comp_regression": {
                "features": feats,
                "pooled": pooled,
                "by_age_band": by_age,
                "r2_pooled": float(r2_pooled),
            },
            "level_to_z": reps,
            "n_train": int(len(s)),
        }
        print(f"  {label}: n={len(s)}, 신체조성 R2={r2_pooled:.3f}, 연령대별 회귀 {len(by_age)}개")

    payload = {
        "n_levels": N_LEVELS,
        "confidence_gate": 1.2,
        "groups": groups,
        "note": "5축 벡터를 중심에 최근접 배정. 확신도 = 2번째 거리 / 1번째 거리, "
                "1.2 미만이면 모호로 보고 대안 세그먼트를 함께 제시한다. "
                "종합체력z = 5축 평균 (원본과 일치 확인).",
    }
    (OUT / "fitness_model.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return payload


def _fit_linear(frame, features, y):
    X = frame[features].copy()
    ok = X.notna().all(axis=1).values & np.isfinite(y)
    if ok.sum() < 50:
        return None, float("nan")
    Xv = np.c_[np.ones(ok.sum()), X.values[ok]]
    yv = y[ok]
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    r2 = 1 - ((yv - Xv @ beta) ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
    return {"intercept": float(beta[0]),
            "coef": [float(b) for b in beta[1:]]}, r2


if __name__ == "__main__":
    print("A1. 선호축 LCA 파라미터")
    build_preference()
    print("\nA3. 체력축 중심·회귀·분위 대표값")
    build_fitness()
    print(f"\n저장 위치: {OUT}")
