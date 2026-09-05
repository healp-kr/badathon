# -*- coding: utf-8 -*-
"""
기상청 단기예보(초단기예보) API 연동 모듈
- 중구·관악구 시연용
- 사용 전: 터미널에서 pip install requests   (python-dotenv는 이제 필요 없음)

[사용법]
1. 이 파일과 같은 폴더에 ".env" 파일을 만들고 인증키 적기:
   KMA_SERVICE_KEY_ENCODED=인코딩버전키
   KMA_SERVICE_KEY_DECODED=디코딩버전키
   (둘 중 하나만 있어도 되고, 실행 시 자동으로 순서대로 시도합니다)

2. 앱 코드에서:
   from weather_api import get_outdoor_status
   status = get_outdoor_status("중구")
   print(status)  # {"가능": True/False, "이유": "...", ...}
"""

import os
import requests
from datetime import datetime, timedelta
from urllib.parse import unquote

def _load_env_file():
    """
    python-dotenv에 의존하지 않고 .env 파일을 직접 읽어서 환경변수로 등록.
    (미설치·BOM·인코딩 문제 등으로 python-dotenv가 조용히 실패하는 경우를 피하기 위함)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, ".env")
    if not os.path.exists(env_path):
        return
    # PowerShell Out-File 등에서 붙는 UTF-8 BOM까지 안전하게 처리
    with open(env_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:  # 이미 설정된 시스템 환경변수는 덮어쓰지 않음
                os.environ[key] = value

_load_env_file()

SERVICE_KEY = os.environ.get("KMA_SERVICE_KEY", "")
# 디코딩 키가 CAI 등에서 더 안정적으로 성공하는 것으로 확인되어 먼저 시도하도록 순서 조정
SERVICE_KEY_CANDIDATES = [k for k in [
    os.environ.get("KMA_SERVICE_KEY_DECODED", ""),
    os.environ.get("KMA_SERVICE_KEY_ENCODED", ""),
    SERVICE_KEY,
] if k]

# 시연 지역 격자좌표 (기상청 격자변환 공식으로 산출)
DISTRICT_GRID = {
    "중구": {"nx": 60, "ny": 127},
    "관악구": {"nx": 59, "ny": 125},
}

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"


def _get_base_datetime():
    """초단기예보 규칙: 매시 30분 발표, 45분 이후 호출 가능 -> 조회 기준시각 계산"""
    now = datetime.now()
    if now.minute < 45:
        now -= timedelta(hours=1)
    return now.strftime("%Y%m%d"), now.strftime("%H") + "30"


def fetch_weather(district: str) -> dict:
    """
    지정 자치구의 초단기예보 원본 응답을 반환.
    .env에 등록된 인증키 후보(인코딩/디코딩)를 순서대로 시도한다.
    실패 시 {"ok": False, "error": "..."} 형태로 반환 (앱이 죽지 않도록).
    """
    if district not in DISTRICT_GRID:
        return {"ok": False, "error": f"지원하지 않는 지역: {district}"}
    if not SERVICE_KEY_CANDIDATES:
        return {"ok": False, "error": "KMA_SERVICE_KEY가 설정되지 않았습니다(.env 확인)"}

    base_date, base_time = _get_base_datetime()
    grid = DISTRICT_GRID[district]
    last_error = None

    for key in SERVICE_KEY_CANDIDATES:
        params = {
            "serviceKey": key,
            "numOfRows": 60,
            "pageNo": 1,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": grid["nx"],
            "ny": grid["ny"],
        }
        try:
            res = requests.get(BASE_URL, params=params, timeout=5)
        except requests.exceptions.RequestException as e:
            last_error = f"네트워크 오류: {e}"
            continue

        if res.status_code != 200:
            last_error = f"HTTP {res.status_code}"
            continue

        try:
            data = res.json()
            result_code = data["response"]["header"]["resultCode"]
        except (ValueError, KeyError):
            last_error = f"응답 파싱 실패. 원문: {res.text[:200]}"
            continue

        if result_code != "00":
            last_error = f"API 오류({result_code}): {data['response']['header'].get('resultMsg','')}"
            continue  # 이 키가 안 맞으면 다음 후보 키로 자동 재시도

        return {"ok": True, "items": data["response"]["body"]["items"]["item"]}

    return {"ok": False, "error": f"모든 인증키 후보 실패. 마지막 오류: {last_error}"}


PTY_LABEL = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기",
             "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}
SKY_LABEL = {"1": "맑음", "3": "구름많음", "4": "흐림"}


def get_outdoor_status(district: str) -> dict:
    """지금 실외활동에 지장이 있는지 판정한다.

    판정: "정상" | "주의" | "비권장" | "모름"

    **조회 실패는 "모름"이다.** 예전 구현은 실패 시 "가능"을 돌려줬는데, 그러면 화면이
    사실이 아닌 것을 단정하게 된다. 모를 때는 배지를 띄우지 않는 편이 낫다.

    **흐림(SKY=4)은 정상이다.** 예전에는 실외 불가로 봤으나 대부분의 날에 배지가 붙어
    신호가 죽는다. 실외를 막는 것은 강수·폭염·한파이지 구름이 아니다.
    """
    result = fetch_weather(district)
    if not result["ok"]:
        return {"판정": "모름", "이유": f"날씨 조회 실패 ({result['error']})"}

    pty = sky = temp = None
    for item in result["items"]:
        category, value = item["category"], item["fcstValue"]
        if category == "PTY" and pty is None:
            pty = value
        elif category == "SKY" and sky is None:
            sky = value
        elif category == "T1H" and temp is None:
            temp = value

    try:
        temp_c = float(temp) if temp is not None else None
    except ValueError:
        temp_c = None

    out = {"판정": "정상", "이유": "강수 없음",
           "PTY": pty, "SKY": sky, "기온": temp_c,
           "강수형태": PTY_LABEL.get(pty, "없음"), "하늘": SKY_LABEL.get(sky)}

    if pty not in (None, "0"):
        out.update(판정="비권장", 이유=f"{PTY_LABEL.get(pty, '강수')} 예보")
    elif temp_c is not None and temp_c >= 33:
        out.update(판정="주의", 이유=f"기온 {temp_c:.0f}도 — 더운 시간대")
    elif temp_c is not None and temp_c <= -12:
        out.update(판정="주의", 이유=f"기온 {temp_c:.0f}도 — 추운 시간대")
    return out


# 생활기상지수 4.0 지점코드 (dfs-zone-tree 공식 코드표로 확인)
DISTRICT_AREANO = {
    "중구": "1114000000",
    "관악구": "1162000000",
}
UV_URL = "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV5/getUVIdxV5"


def fetch_uv_index(district: str) -> dict:
    """생활기상지수 4.0 - 자외선지수 조회 (지점코드 areaNo 기반)."""
    if district not in DISTRICT_AREANO:
        return {"ok": False, "error": f"지원하지 않는 지역: {district}"}
    if not SERVICE_KEY_CANDIDATES:
        return {"ok": False, "error": "인증키가 설정되지 않았습니다(.env 확인)"}

    now = datetime.now()
    # 발표시각은 3시간 단위(0,3,6,9,...) 기준 - 가장 최근 발표시각으로 내림
    time_str = now.strftime("%Y%m%d") + f"{(now.hour // 3) * 3:02d}"
    last_error = None

    for key in SERVICE_KEY_CANDIDATES:
        params = {
            "serviceKey": key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "areaNo": DISTRICT_AREANO[district],
            "time": time_str,
        }
        try:
            res = requests.get(UV_URL, params=params, timeout=5)
        except requests.exceptions.RequestException as e:
            last_error = f"네트워크 오류: {e}"
            continue
        if res.status_code != 200:
            last_error = f"HTTP {res.status_code}"
            continue
        try:
            data = res.json()
            result_code = data["response"]["header"]["resultCode"]
        except (ValueError, KeyError):
            last_error = f"응답 파싱 실패. 원문: {res.text[:200]}"
            continue
        if result_code != "00":
            last_error = f"API 오류({result_code}): {data['response']['header'].get('resultMsg','')}"
            continue
        return {"ok": True, "items": data["response"]["body"]["items"]["item"]}

    return {"ok": False, "error": f"모든 인증키 후보 실패. 마지막 오류: {last_error}"}


CAI_URL = "http://apis.data.go.kr/B552584/RltmKhaiInfoSvc/getMsrstnKhaiRltmDnsty"
CAI_GRADE_LABEL = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def fetch_cai(district: str) -> dict:
    """통합대기환경지수(CAI) 조회 - 측정소명에 자치구명을 그대로 사용.
    공공데이터포털은 계정당 인증키가 하나라 SERVICE_KEY_CANDIDATES를 그대로 재사용."""
    if not SERVICE_KEY_CANDIDATES:
        return {"ok": False, "error": "인증키가 설정되지 않았습니다(.env 확인)"}

    last_error = None
    for key in SERVICE_KEY_CANDIDATES:
        for attempt in range(2):  # 일시적 서버 오류(5xx) 대비 최대 2회 시도
            params = {
                "serviceKey": key,
                "returnType": "json",  # 이 API는 dataType이 아니라 returnType
                "numOfRows": 10,
                "pageNo": 1,
                "stationName": district,
            }
            try:
                res = requests.get(CAI_URL, params=params, timeout=10)
            except requests.exceptions.RequestException as e:
                last_error = f"네트워크 오류: {e}"
                continue
            if res.status_code >= 500:
                last_error = f"HTTP {res.status_code} (서버 일시 오류)"
                continue  # 같은 키로 한 번 더 시도
            if res.status_code != 200:
                last_error = f"HTTP {res.status_code}"
                break  # 5xx가 아니면 재시도 의미 없음, 다음 키로
            break
        else:
            continue  # 2회 다 실패 -> 다음 키 후보로
        if res.status_code >= 500 or res.status_code != 200:
            continue

        try:
            data = res.json()
            result_code = str(data["response"]["header"]["resultCode"])
            result_msg = data["response"]["header"].get("resultMsg", "")
        except (ValueError, KeyError):
            last_error = f"응답 파싱 실패. 원문: {res.text[:200]}"
            continue
        # 문서상 성공코드는 "00"이지만 실제 서버는 "200"/NORMAL_CODE로도 응답함 - 둘 다 성공 처리
        if result_code not in ("00", "200") and "NORMAL" not in result_msg.upper():
            last_error = f"API 오류({result_code}): {result_msg}"
            continue

        items_raw = data["response"]["body"].get("items", [])
        # data.go.kr 계열 API는 결과가 1건일 때 리스트가 아니라 단일 dict로 오는 경우가 흔함 - 형태 무관하게 처리
        if isinstance(items_raw, dict):
            items_raw = items_raw.get("item", items_raw)
        if isinstance(items_raw, dict):
            items_raw = [items_raw]
        if not items_raw:
            return {"ok": False, "error": f"'{district}' 측정소 데이터 없음"}
        item = items_raw[0]
        # 공식 문서는 khaiValue/khaiGrade로 되어있으나 실제 서버 응답은 caiValue/caiGrade로 확인됨 - 둘 다 대응
        grade = item.get("caiGrade") or item.get("khaiGrade")
        value = item.get("caiValue") or item.get("khaiValue")
        pollutant = item.get("caiItem") or item.get("khaiItem")
        if not grade or grade in ("", "-"):
            return {
                "ok": True,
                "khaiValue": value,
                "khaiGrade": grade,
                "등급": "측정값 일시 결측(측정소 점검 중일 수 있음)",
                "주오염물질": pollutant,
                "측정일시": item.get("dataTime"),
            }
        return {
            "ok": True,
            "khaiValue": value,
            "khaiGrade": grade,
            "등급": CAI_GRADE_LABEL.get(grade, "알수없음"),
            "주오염물질": pollutant,
            "측정일시": item.get("dataTime"),
        }

    return {"ok": False, "error": f"모든 인증키 후보 실패. 마지막 오류: {last_error}"}


if __name__ == "__main__":
    # 직접 실행 시 테스트
    for gu in ["중구", "관악구"]:
        print(gu, "->", get_outdoor_status(gu))
        print(gu, "(자외선지수) ->", fetch_uv_index(gu))
        print(gu, "(대기환경지수) ->", fetch_cai(gu))
