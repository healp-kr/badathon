# -*- coding: utf-8 -*-
"""엔진 데이터 변환기 — CSV·JSON → 브라우저가 읽을 JSON 번들.

정적화하면 `pd.read_csv` 가 없다. 그런데 파이썬 쪽 동작은 pandas 의 타입 추론에
은근히 기대고 있다 — 빈 칸이 `NaN` 이 되고, `isinstance(value, str)` 검사가 그
`NaN` 을 걸러내는 식이다. 그래서 이 변환기는 **pandas 가 읽은 그대로**를 JSON 으로
옮긴다. 직접 CSV 를 파싱하면 그 타입 추론을 TS 쪽에서 다시 흉내 내야 하고,
거기서 어긋나면 조용한 불일치가 된다.

`NaN` 은 JSON 에 실을 수 없으므로 `null` 로 바꾼다. TS 쪽은 `null` 을 파이썬의
`NaN` 과 같게 다룬다 — 문자열이 아니고, 숫자도 아니다.

    python tools/make_engine_data.py    # → web/ui/src/engine/data/*.json
"""
import csv
import io
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

OUT_DIR = os.path.join(ROOT, "web", "ui", "src", "engine", "data")
REC = os.path.join(ROOT, "recommendation", "data")
PARAMS = os.path.join(ROOT, "assignment", "params")
GEO = os.path.join(ROOT, "geo", "data")


def clean(value):
    """pandas 값 → JSON 안전 값. NaN·NaT → None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, str, bool)):
        return value
    if hasattr(value, "item"):        # numpy 스칼라
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    return value


def rows_of(path):
    frame = pd.read_csv(path)
    return [{k: clean(v) for k, v in row.items()}
            for row in frame.to_dict("records")]


def copy_json(src, name):
    with io.open(src, encoding="utf-8") as f:
        data = json.load(f)
    write(name, data)
    return data


def write(name, data):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    return os.path.getsize(path)


def report_nan(name, rows):
    """어느 열에 결측이 있는지 밝혀 둔다 — TS 포팅이 그 열을 조심해야 한다."""
    if not rows:
        return
    cols = {}
    for row in rows:
        for key, value in row.items():
            if value is None:
                cols[key] = cols.get(key, 0) + 1
    if cols:
        detail = ", ".join(f"{k}({v})" for k, v in sorted(cols.items()))
        print(f"    결측 있는 열 — {detail}")


def main():
    total = 0
    print("recommendation/")
    for csv_name, out_name in (
        ("preference_sport_matrix.csv", "preference_sport_matrix.json"),
        ("sport_master.csv", "sport_master.json"),
        ("sport_facility_map.csv", "sport_facility_map.json"),
    ):
        rows = rows_of(os.path.join(REC, csv_name))
        size = write(out_name, rows)
        total += size
        print(f"  {out_name:34} {len(rows):4}행  {size/1024:6.1f}KB")
        report_nan(out_name, rows)

    size = os.path.getsize(os.path.join(REC, "rules.json"))
    copy_json(os.path.join(REC, "rules.json"), "rules.json")
    total += size
    print(f"  {'rules.json':34}       {size/1024:6.1f}KB")

    print("assignment/params/")
    for name in ("preference_model.json", "fitness_model.json"):
        copy_json(os.path.join(PARAMS, name), name)
        size = os.path.getsize(os.path.join(PARAMS, name))
        total += size
        print(f"  {name:34}       {size/1024:6.1f}KB")

    print(f"\n합계 약 {total/1024:.0f}KB (번들에 그대로 들어간다)")
    # ---- geo 층 --------------------------------------------------
    # 주의: 이쪽 파이썬은 pandas 가 아니라 `csv.DictReader` 를 쓴다. 즉 **모든 값이
    # 문자열**이고, 숫자 변환은 `_floatify` 가 따로 한다. 빈 칸도 NaN 이 아니라 "" 다.
    # 그래서 여기서는 타입 추론을 하지 않고 읽은 그대로 옮긴다 —
    # 추론을 넣으면 `row["위도"]` 의 참/거짓 판정이 어긋난다.
    print("geo/data/ (문자열 그대로 — csv.DictReader 와 같게)")
    for name in ("facilities.csv", "reservations.csv", "subway.csv", "bus.csv",
                 "parking.csv", "sport_facility_join.csv", "crowding.csv"):
        with io.open(os.path.join(GEO, name), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        out_name = name.replace(".csv", ".json")
        size = write(out_name, rows)
        total += size
        print(f"  {out_name:34} {len(rows):4}행  {size/1024:6.1f}KB")

    # 경계 폴리곤 — api/locate.py 가 import 시점에 읽던 것
    with io.open(os.path.join(ROOT, "api", "districts.json"), encoding="utf-8") as f:
        conf = json.load(f)
    write("districts.json", conf)
    total += os.path.getsize(os.path.join(ROOT, "api", "districts.json"))
    with io.open(os.path.join(ROOT, conf["boundary_geojson"]), encoding="utf-8") as f:
        boundary = json.load(f)
    size = write("boundary.json", boundary)
    total += size
    print(f"  {'boundary.json':34}       {size/1024:6.1f}KB")

    # ---- 설문 스키마·종목 마스터 -----------------------------------
    # 백엔드 시절 /api/survey-schema · /api/sports 가 내주던 것.
    # 모델 범주 대조(web/schema.py 의 validate)는 여기서 한 번 돌고 끝난다 —
    # 어긋난 채로 배포되지 않도록 import 자체가 예외를 던진다.
    from web.schema import build_schema, sport_catalog
    size = write("survey_schema.json", build_schema())
    total += size
    print(f"  {'survey_schema.json':34}       {size/1024:6.1f}KB")
    size = write("sports.json", {"sports": sport_catalog()})
    total += size
    print(f"  {'sports.json':34}       {size/1024:6.1f}KB")

    # 파라미터 해시 — 파이썬 serve.model_fingerprint() 와 같은 값이어야 한다.
    # TS 는 파일을 읽어 해시할 수 없으므로 빌드 시점에 구워 넣는다.
    from serve import model_fingerprint
    fingerprint = model_fingerprint()
    write("version.json", {"model_version": fingerprint})
    print(f"model_version {fingerprint} -> version.json")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
