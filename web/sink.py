# -*- coding: utf-8 -*-
"""로그 싱크 — JSONL 파일.

**v1부터 남겨야 한다. 소급 수집이 안 된다.** 이게 없으면 두 가지를 영원히 모른다:
체력 자가평가의 신뢰도(r), 그리고 근거 없이 정한 가중치들이 맞는지.

데모에서는 파일 한 줄씩이면 충분하다. 나중에 DB로 바꿔도 이 함수 시그니처만 지키면 된다.
"""
import io
import json
import os
import threading
from datetime import datetime

LOG_DIR = os.environ.get("BADATHON_LOG_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

_LOCK = threading.Lock()


def _path():
    return os.path.join(LOG_DIR, f"events-{datetime.now():%Y%m%d}.jsonl")


def write(event):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, default=str)
    with _LOCK:
        with io.open(_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return event


def read_all(day=None):
    """시연 후 분석용."""
    name = f"events-{day or datetime.now():%Y%m%d}.jsonl" if not isinstance(day, str) \
        else f"events-{day}.jsonl"
    path = os.path.join(LOG_DIR, name)
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
