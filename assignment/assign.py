"""배정 층 (A2 · A4 · A5).

설문 응답 → (선호 유형, 체력 유형).

학습이 없다. params/*.json 의 파라미터로 계산만 한다.
의존성은 numpy 하나뿐이고, 모든 함수는 부작용이 없다.

    from assign import assign_all
    result = assign_all(
        age=34, sex="남", regular_exercise=True,
        preference={"운동빈도": "일주일에 3번", "운동요일": "평일",
                    "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
                    "운동강도": "중", "체력인지": "보통이다"},
        fitness={"근력": 4, "근지구력": 3, "순발력": 2, "유연성": 3},
        height_cm=175, weight_kg=72,
    )
"""
import json
import math
from pathlib import Path

import numpy as np

PARAMS = Path(__file__).resolve().parent / "params"

with open(PARAMS / "preference_model.json", encoding="utf-8") as f:
    PREFERENCE = json.load(f)
with open(PARAMS / "fitness_model.json", encoding="utf-8") as f:
    FITNESS = json.load(f)

# 설문 문항명 → 모델 변수명
ITEM_TO_VAR = {
    "운동빈도": "운동빈도_1",
    "운동요일": "운동요일_1",
    "운동시간대": "운동시간대_1",
    "운동목적": "운동목적_1",
    "운동강도": "운동강도_1",
    "체력인지": "체력인지",
}

ELDERLY_PREFERENCE_AGE = 60   # 선호 모델의 노인 경계
ELDERLY_FITNESS_AGE = 65      # 체력 모델의 노인 경계 (측정 프로토콜)
ELDERLY_DISPLAY_AGE = 60      # 서비스 표시 라벨의 노인 경계
MIN_FITNESS_AGE = 19          # 19세 미만은 체력 축 미부여


class AssignmentError(ValueError):
    pass


# ------------------------------------------------------------------
# A5. 라우팅
# ------------------------------------------------------------------
def route(age, sex, regular_exercise=True):
    """나이·성별·참여여부로 어느 모델을 태울지 결정한다.

    세 경계가 서로 다르다 (의도된 설계):
      선호 모델 60세 / 체력 모델 65세 / 표시 라벨 60세
    """
    if sex not in ("남", "여"):
        raise AssignmentError(f"성별은 '남' 또는 '여': {sex!r}")
    if not isinstance(age, (int, float)) or not (0 < age < 120):
        raise AssignmentError(f"나이 범위 오류: {age!r}")

    sex_full = "남성" if sex == "남" else "여성"

    if regular_exercise:
        stage = "노인" if age >= ELDERLY_PREFERENCE_AGE else "성인"
        preference_segment = f"{stage}_{sex_full}"
    else:
        preference_segment = None  # 비참여자 — 선호 모델 대상 아님

    if age < MIN_FITNESS_AGE:
        fitness_group = None       # 측정 원자료에 없는 연령
    else:
        stage = "노인" if age >= ELDERLY_FITNESS_AGE else "성인"
        fitness_group = f"{stage} {sex}"

    return {
        "preference_segment": preference_segment,
        "fitness_group": fitness_group,
        "display_age_group": "노인" if age >= ELDERLY_DISPLAY_AGE else "성인",
        "skip_reason": {
            "preference": None if regular_exercise else "규칙적 체육활동 비참여자",
            "fitness": None if fitness_group else "19세 미만은 체력 축 미부여",
        },
    }


# ------------------------------------------------------------------
# A2. 선호 유형 배정
# ------------------------------------------------------------------
def assign_preference(answers, segment):
    """LCA posterior 를 직접 계산한다. 학습된 분류기가 아니다.

    answers 에 없거나 levels 에 없는 문항은 해당 항을 건너뛴다(주변화).
    → 문항을 줄여도 그대로 동작한다.
    """
    if segment not in PREFERENCE["segments"]:
        raise AssignmentError(f"알 수 없는 세그먼트: {segment!r}")
    spec = PREFERENCE["segments"][segment]

    log_prob = np.log(np.asarray(spec["class_prob"]) + 1e-300)
    used, skipped = [], []

    for item, var in ITEM_TO_VAR.items():
        value = answers.get(item)
        levels = spec["indicators"][var]["levels"]
        if value is None:
            skipped.append(item)
            continue
        if value not in levels:
            # 무응답 범주가 학습돼 있으면 그쪽으로, 없으면 건너뜀
            if "무응답" in levels:
                value = "무응답"
            else:
                skipped.append(item)
                continue
        idx = levels.index(value)
        rp = np.asarray(spec["indicators"][var]["response_prob"])  # [클래스][범주]
        log_prob = log_prob + np.log(rp[:, idx] + 1e-300)
        used.append(item)

    posterior = np.exp(log_prob - log_prob.max())
    posterior = posterior / posterior.sum()

    order = np.argsort(-posterior)
    classes = spec["classes"]
    ranked = [
        {"class_id": classes[i]["class_id"],
         "name": classes[i]["name"],
         "probability": round(float(posterior[i]), 4)}
        for i in order
    ]
    margin = float(posterior[order[0]] - posterior[order[1]]) if len(order) > 1 else 1.0

    return {
        "segment": segment,
        "class_id": ranked[0]["class_id"],
        "name": ranked[0]["name"],
        "probability": ranked[0]["probability"],
        "runner_up": ranked[1] if len(ranked) > 1 else None,
        "margin": round(margin, 4),
        "ranked": ranked,
        "used_items": used,
        "skipped_items": skipped,
    }


# ------------------------------------------------------------------
# A4. 체력 유형 배정
# ------------------------------------------------------------------
def assign_fitness(levels, group, height_cm=None, weight_kg=None,
                   age_band=None, z_override=None):
    """자가평가 5단계 → 분위 매핑 → 최근접 중심.

    levels     : {"근력": 1..5, ...} 1=매우 낮은 편 … 5=매우 높은 편
    z_override : 실측 z 를 직접 넣을 때 사용 (검증·간이측정 경로)
    """
    if group not in FITNESS["groups"]:
        raise AssignmentError(f"알 수 없는 체력 하위집단: {group!r}")
    spec = FITNESS["groups"][group]
    axes = spec["axes"]
    n_levels = FITNESS["n_levels"]

    z = np.zeros(len(axes))
    missing = []

    for j, axis in enumerate(axes):
        if z_override and axis in z_override:
            z[j] = float(z_override[axis])
            continue

        item = spec["axis_item"][axis]
        if item is None:  # 신체조성 — 자가평가가 아니라 키·몸무게로 추정
            if height_cm is None or weight_kg is None:
                missing.append(axis)
                continue  # 0 = 또래 평균
            z[j] = _estimate_body_comp(spec, height_cm, weight_kg, age_band)
            continue

        level = levels.get(item)
        if level is None:
            missing.append(axis)
            continue  # 0 = 평균으로 둠
        level = int(level)
        if not 1 <= level <= n_levels:
            raise AssignmentError(f"{item} 응답은 1~{n_levels}: {level!r}")
        z[j] = spec["level_to_z"][item][level - 1]

    names = list(spec["centroids"].keys())
    centroids = np.asarray([spec["centroids"][n] for n in names])
    distances = np.linalg.norm(centroids - z, axis=1)
    order = np.argsort(distances)

    nearest, second = order[0], order[1]
    confidence = float(distances[second] / distances[nearest]) if distances[nearest] > 0 else float("inf")
    gate = FITNESS["confidence_gate"]

    return {
        "group": group,
        "segment": names[nearest],
        "confidence": round(confidence, 3),
        "ambiguous": bool(confidence < gate),
        "alternative": names[second],
        "z": {axis: round(float(v), 3) for axis, v in zip(axes, z)},
        "종합체력z": round(float(z.mean()), 3),
        "missing_axes": missing,
        "distances": {names[i]: round(float(distances[i]), 3) for i in order},
    }


def _estimate_body_comp(spec, height_cm, weight_kg, age_band):
    reg = spec["body_comp_regression"]
    if height_cm <= 0 or weight_kg <= 0:
        raise AssignmentError("키·몸무게는 양수여야 한다")
    bmi = weight_kg / (height_cm / 100) ** 2
    model = None
    if age_band is not None:
        model = reg["by_age_band"].get(str(int(age_band)))
    if model is None:
        model = reg["pooled"]
    if model is None:
        return 0.0
    x = np.asarray([height_cm, weight_kg, bmi])
    return float(model["intercept"] + np.dot(model["coef"], x))


# ------------------------------------------------------------------
# 통합 진입점
# ------------------------------------------------------------------
def assign_all(age, sex, regular_exercise=True, preference=None,
               fitness=None, height_cm=None, weight_kg=None):
    routing = route(age, sex, regular_exercise)
    out = {"routing": routing, "preference": None, "fitness": None}

    if routing["preference_segment"] and preference:
        out["preference"] = assign_preference(preference, routing["preference_segment"])

    if routing["fitness_group"] and (fitness or (height_cm and weight_kg)):
        out["fitness"] = assign_fitness(
            fitness or {}, routing["fitness_group"],
            height_cm=height_cm, weight_kg=weight_kg,
            age_band=age_to_band(age),
        )
    return out


def age_to_band(age):
    """원자료 측정연령수 코드.

    1=19-24, 2=25-29, 3=30-34, 4=35-39, 5=40-44, 6=45-49,
    7=50-54, 8=55-59, 9=60-64, 10=65-69, 11=70-74, 12=75-79, 13=80+
    """
    age = int(age)
    if age < 19:
        return None
    if age < 25:
        return 1
    if age < 65:
        return 2 + (age - 25) // 5
    return min(13, 10 + (age - 65) // 5)
