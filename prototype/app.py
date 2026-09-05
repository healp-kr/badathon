"""팀 공유용 프로토타입 — 설문에 답하면 추천 운동이 나온다.

디자인 없음. 지리정보(시설 검색) 제외. 알고리즘이 실제로 도는 것만 보여주는 용도다.

    python prototype/app.py
    → http://localhost:8000

파이썬 표준 라이브러리만 쓴다(설치할 것 없음). 내부는 serve.serve() 하나만 호출한다.

**선택지 문자열을 여기에 하드코딩하지 않았다.** 문항 선택지는 실행 시점에
`assignment/params/preference_model.json` 의 levels 에서 그대로 읽어 온다.
설문 선택지와 모델 범주가 어긋나는 사고(인터페이스_명세 §1)를 구조적으로 막기 위한 것이고,
동시에 "매핑 표를 데이터 파일로 둔다"가 무슨 뜻인지 보여주는 예시이기도 하다.
"""
import csv
import html
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from serve import RequestError, serve  # noqa: E402

PARAMS = ROOT / "assignment" / "params"
PREFERENCE = json.loads((PARAMS / "preference_model.json").read_text(encoding="utf-8"))
FITNESS = json.loads((PARAMS / "fitness_model.json").read_text(encoding="utf-8"))

PORT = 8000
BODY_PARTS = ["무릎", "허리", "어깨", "발목", "손목"]

# 화면에 보여줄 순서. 여기 없는 값은 뒤에 그대로 붙는다.
# 문자열은 모델 levels 와 대조해 검증한다(_options 참조).
DISPLAY_ORDER = {
    "운동빈도_1": ["한 달에 3번 이하", "일주일에 1번", "일주일에 2번", "일주일에 3번",
                   "일주일에 4번", "일주일에 5번", "일주일에 6번", "일주일에 7번(매일)"],
    "운동요일_1": ["평일", "휴일", "평일/휴일"],
    "운동시간대_1": ["아침/새벽(6-8시)", "오전(8-12시)", "점심(12-14시)",
                     "오후(14-18시)", "저녁(18-22시)", "일정하지 않음"],
    "운동강도_1": ["저", "중", "고"],
    "체력인지": ["전혀 체력이 좋지 않은 편이다", "별로 체력이 좋지 않은 편이다", "보통이다",
                 "체력이 좋은 편이다", "매우 체력이 좋은 편이다"],
}

SELF_RATING = ["매우 낮은 편", "낮은 편", "보통", "높은 편", "매우 높은 편"]

# 체력 자가평가 문항 문구 (설문문항_v1.md §4). 축 이름 자체는 파라미터 파일에서 읽는다.
AXIS_QUESTION = {
    "근력": "무거운 물건을 들거나 힘을 쓸 때, 또래와 비교해 힘이 센 편인가요?",
    "유연성": "앉아서 상체를 앞으로 굽힐 때, 또래보다 유연한 편인가요?",
    "근지구력": "윗몸일으키기처럼 같은 동작을 반복할 때, 또래보다 오래 지속할 수 있나요?",
    "순발력": "제자리에서 멀리 뛰거나 순간적으로 튀어나갈 때, 또래보다 잘하는 편인가요?",
    "하지근기능": "의자에 앉았다 일어서기를 반복할 때, 또래보다 수월한 편인가요?",
    "협응력평형": "걷다가 방향을 바꾸거나 한 발로 설 때, 또래보다 균형을 잘 잡나요?",
}

STRUCTURED_LABEL = {
    "운동빈도_1": ("운동빈도", "얼마나 자주 하시나요?"),
    "운동요일_1": ("운동요일", "주로 언제 운동하시나요? (요일)"),
    "운동시간대_1": ("운동시간대", "주로 몇 시에 하시나요?"),
    "운동목적_1": ("운동목적", "운동하는 주된 이유는 무엇인가요?"),
    "운동강도_1": ("운동강도", "운동 강도는 어느 정도인가요?"),
    "체력인지": ("체력인지", "본인의 체력 상태를 어떻게 생각하시나요?"),
}


def _options(var):
    """모든 세그먼트의 levels 합집합을 표시 순서대로 돌려준다.

    세그먼트마다 levels 가 조금씩 다르다(예: '시간소비'는 노인 여성에만 있다).
    그 세그먼트에 없는 값이 들어오면 assign_preference 가 해당 문항을 주변화하므로
    합집합을 써도 안전하다.
    """
    levels = set()
    for spec in PREFERENCE["segments"].values():
        levels.update(spec["indicators"][var]["levels"])

    ordered = [v for v in DISPLAY_ORDER.get(var, []) if v in levels]
    unknown = [v for v in DISPLAY_ORDER.get(var, []) if v not in levels]
    if unknown:  # 모델에 없는 문자열을 표시 순서에 적어 둔 경우 — 조용히 넘기지 않는다
        print(f"  [경고] {var}: 모델 levels 에 없는 선택지 {unknown}", file=sys.stderr)
    ordered += sorted(levels - set(ordered))
    return ordered


def _sports():
    path = ROOT / "recommendation" / "data" / "sport_master.csv"
    with open(path, encoding="utf-8-sig") as f:
        return [r["종목"] for r in csv.DictReader(f) if r["추천가능"] == "Y"]


def _fitness_axes(group):
    """하위집단의 자가평가 문항 목록. 신체조성(axis_item=None)은 키·몸무게로 대체된다."""
    spec = FITNESS["groups"][group]
    return [item for item in (spec["axis_item"][a] for a in spec["axes"]) if item]


SPORTS = _sports()
ADULT_AXES = _fitness_axes("성인 남")
ELDER_AXES = _fitness_axes("노인 남")


# ------------------------------------------------------------------
# 폼
# ------------------------------------------------------------------
def _radio(name, options, checked=None):
    out = []
    for i, opt in enumerate(options):
        mark = " checked" if opt == checked or (checked is None and i == 0) else ""
        out.append(f'<label><input type="radio" name="{name}" value="{html.escape(opt)}"'
                   f'{mark}> {html.escape(opt)}</label>')
    return f'<div class="opts">{"".join(out)}</div>'


def _scale(name):
    out = []
    for i, label in enumerate(SELF_RATING, start=1):
        mark = " checked" if i == 3 else ""
        out.append(f'<label><input type="radio" name="{name}" value="{i}"{mark}> {label}</label>')
    return f'<div class="opts">{"".join(out)}</div>'


def _checkboxes(name, options):
    out = [f'<label><input type="checkbox" name="{name}" value="{html.escape(o)}"> '
           f'{html.escape(o)}</label>' for o in options]
    return f'<div class="opts wrap">{"".join(out)}</div>'


def _axis_block(axes, css_class):
    out = []
    for axis in axes:
        out.append(f'<div class="q {css_class}"><b>{html.escape(axis)}</b> — '
                   f'{html.escape(AXIS_QUESTION.get(axis, axis))}{_scale("자가_" + axis)}</div>')
    return "".join(out)


def form_page(message=""):
    prefs = []
    for var, (field, question) in STRUCTURED_LABEL.items():
        prefs.append(f'<div class="q"><b>{html.escape(question)}</b>{_radio(field, _options(var))}</div>')

    return f"""<h1>운동 추천 프로토타입</h1>
<p class="note">알고리즘 확인용입니다. 디자인·시설 검색은 들어 있지 않습니다.
선택지는 모델 파라미터 파일에서 그대로 읽어 옵니다.</p>
{f'<p class="err">{html.escape(message)}</p>' if message else ''}
<form method="post" action="/">

<h2>기본 정보</h2>
<div class="q"><b>나이 (만)</b>
  <input type="number" name="나이" value="34" min="1" max="119" required id="age"></div>
<div class="q"><b>성별</b>{_radio("성별", ["남", "여"])}</div>
<div class="q"><b>키 (cm)</b> <input type="number" name="키" value="170" step="0.1">
  &nbsp; <b>몸무게 (kg)</b> <input type="number" name="몸무게" value="65" step="0.1">
  <span class="note">신체조성 축 추정에 씁니다. 비워도 됩니다</span></div>
<div class="q"><b>최근 1년간 규칙적으로 운동하고 계신가요?</b>
  {_radio("규칙적참여", ["예", "아니오"])}
  <span class="note">'아니오'면 선호 유형을 배정하지 않고 관심 종목 기반으로 추천합니다</span></div>

<h2>운동 패턴 <span class="note">— 선호 유형 12개 배정</span></h2>
{''.join(prefs)}

<h2>선호 운동</h2>
<div class="q"><b>그동안 자주 해온 운동</b> <span class="note">(복수 선택)</span>
  {_checkboxes("자주해온운동", SPORTS)}</div>
<div class="q"><b>관심 있는 운동</b> <span class="note">(복수 선택)</span>
  {_checkboxes("관심운동", SPORTS)}</div>

<h2>체력 자가평가 <span class="note">— 모두 "같은 나이·성별의 또래와 비교해서"</span></h2>
<p class="note" id="track-note"></p>
{_axis_block(ADULT_AXES, "adult")}
{_axis_block(ELDER_AXES, "elder")}

<h2>불편한 부위</h2>
<div class="q"><span class="note">고른 부위에 부담이 가는 종목을 추천에서 뺍니다</span>
  {_checkboxes("불편부위", BODY_PARTS)}</div>

<p><button type="submit">추천 받기</button></p>
</form>

<script>
// 체력 문항은 65세 기준으로 갈린다 (선호 60세 / 체력 65세 — 의도된 설계)
function syncTrack() {{
  var age = parseInt(document.getElementById('age').value || '0', 10);
  var elder = age >= 65;
  document.querySelectorAll('.adult').forEach(function (e) {{ e.style.display = elder ? 'none' : ''; }});
  document.querySelectorAll('.elder').forEach(function (e) {{ e.style.display = elder ? '' : 'none'; }});
  document.getElementById('track-note').textContent =
    elder ? '65세 이상 — 노인 문항 (하지근기능·협응력)' : '19~64세 — 성인 문항 (근지구력·순발력)';
}}
document.getElementById('age').addEventListener('input', syncTrack);
syncTrack();
</script>"""


# ------------------------------------------------------------------
# 결과
# ------------------------------------------------------------------
def _sport_list(items, title, note=""):
    if not items:
        return ""
    rows = []
    for item in items:
        bits = []
        if item.get("강도"):
            bits.append(f'강도 {item["강도"]}')
        if item.get("이유"):
            bits.append(item["이유"])
        for extra in item.get("맞춤이유") or []:
            bits.append(extra)
        detail = " · ".join(html.escape(b) for b in bits)
        rows.append(f'<li><b>{html.escape(item["종목"])}</b>'
                    f'{f" <span class=note>{detail}</span>" if detail else ""}</li>')
    return (f'<h3>{html.escape(title)}'
            f'{f" <span class=note>{html.escape(note)}</span>" if note else ""}</h3>'
            f'<ul>{"".join(rows)}</ul>')


def result_page(result, payload):
    pref = result["선호유형"]
    fit = result["체력유형"]
    routing = result["라우팅"]

    if pref:
        runner = pref.get("runner_up")
        pref_html = (f'<b>{html.escape(pref["name"])}</b> '
                     f'<span class="note">확률 {pref["probability"]:.1%} · {pref["class_id"]}</span>')
        if runner:
            pref_html += (f'<br><span class="note">2순위 {html.escape(runner["name"])} '
                          f'{runner["probability"]:.1%}</span>')
    else:
        pref_html = f'<span class="note">배정 안 함 — {routing["skip_reason"]["preference"]}</span>'

    if fit:
        fit_html = f'<b>{html.escape(fit["segment"])}</b> <span class="note">확신도 {fit["confidence"]:.2f}</span>'
        if fit.get("ambiguous"):
            fit_html += ('<br><span class="warn">확신도가 낮습니다. '
                         f'대안: {html.escape(fit.get("alternative") or "-")}</span>')
    else:
        fit_html = f'<span class="note">배정 안 함 — {routing["skip_reason"]["fitness"]}</span>'

    excluded = "".join(
        f'<li>{html.escape(e["종목"])} <span class="note">{html.escape(e["사유"])}</span></li>'
        for e in result["제외종목"])

    support = "".join(
        f'<li><b>{html.escape(s["축"])}</b> — {html.escape(", ".join(s["운동"]))}'
        f'<br><span class="note">{html.escape(s["처방"])} · 근거: {html.escape(s["근거"])}'
        f'{" (제안)" if s["표현"] == "제안" else ""}</span></li>'
        for s in result["보완운동"])

    notices = "".join(f'<li>{html.escape(n)}</li>' for n in result["안내"])
    prescription = result["처방"]
    adjust = (prescription.get("조정") or {}).get("메시지")

    return f"""<h1>추천 결과</h1>
<p><a href="/">← 다시 하기</a></p>

<div class="box">
<h2>배정</h2>
<p><b>선호 유형</b><br>{pref_html}</p>
<p><b>체력 유형</b><br>{fit_html}</p>
<p class="note">라우팅 — 선호 {routing["preference_segment"] or "-"} /
  체력 {routing["fitness_group"] or "-"} / 표시 {routing["display_age_group"]}</p>
</div>

<div class="box">
<h2>추천</h2>
{_sport_list(result["익숙한운동"], "익숙한 운동", "고르신 것 중 지금 하실 수 있는 것")}
{_sport_list(result["새로운운동"], "새로운 운동", "비슷한 분들이 많이 하시는 것")}
{f'<h3>제외</h3><ul>{excluded}</ul>' if excluded else ''}
</div>

<div class="box">
<h2>강도·빈도</h2>
<p>권장 강도 상한 <b>{html.escape(prescription.get("권장강도상한") or "-")}</b></p>
<p class="note">유산소 {html.escape(prescription["기준"]["유산소"])}<br>
  근력 {html.escape(prescription["기준"]["근력"])}<br>
  근거: {html.escape(prescription["기준"]["근거"])}</p>
{f'<p>{html.escape(adjust)}</p>' if adjust else ''}
{f'<h3>보완 운동</h3><ul>{support}</ul>' if support else ''}
{f'<h3>안내</h3><ul>{notices}</ul>' if notices else ''}
<p class="note">{html.escape(result["면책"])}</p>
</div>

<details><summary>개발용 — 원본 응답 / 출력 JSON</summary>
<pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre>
<pre>{html.escape(json.dumps(result, ensure_ascii=False, indent=2))}</pre>
</details>
<p class="note">model_version {result["model_version"]} · api {result["api_version"]}</p>"""


# ------------------------------------------------------------------
# 요청 처리
# ------------------------------------------------------------------
def build_payload(fields):
    def one(name):
        value = fields.get(name, [""])[0].strip()
        return value or None

    def many(name):
        return [v for v in fields.get(name, []) if v]

    def number(name):
        value = one(name)
        return float(value) if value else None

    age = number("나이")
    payload = {
        "나이": int(age) if age is not None else None,
        "성별": one("성별"),
        "키": number("키"),
        "몸무게": number("몸무게"),
        "규칙적참여": one("규칙적참여") != "아니오",
        "자주해온운동": many("자주해온운동"),
        "관심운동": many("관심운동"),
        "불편부위": many("불편부위"),
    }
    for field, _ in STRUCTURED_LABEL.values():
        payload[field] = one(field)

    # 나이에 맞는 축만 넣는다. 반대쪽 트랙 문항이 함께 와도 여기서 걸러진다.
    axes = ELDER_AXES if (age or 0) >= 65 else ADULT_AXES
    ratings = {}
    for axis in axes:
        value = one("자가_" + axis)
        if value:
            ratings[axis] = int(value)
    payload["체력자가평가"] = ratings

    return {k: v for k, v in payload.items() if v is not None}


PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>운동 추천 프로토타입</title>
<style>
 body {{ font-family: system-ui, sans-serif; line-height: 1.6; max-width: 760px;
        margin: 24px auto; padding: 0 16px; }}
 h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 28px; }}
 h3 {{ font-size: 1rem; margin-bottom: 4px; }}
 .q {{ margin: 10px 0; }}
 .opts label {{ display: block; font-weight: normal; }}
 .opts.wrap {{ display: flex; flex-wrap: wrap; gap: 2px 14px; }}
 .opts.wrap label {{ display: inline-block; }}
 .note {{ color: #666; font-size: 0.85rem; font-weight: normal; }}
 .warn {{ color: #a40; font-size: 0.85rem; }}
 .err {{ color: #a00; }}
 .box {{ border: 1px solid #ddd; padding: 4px 16px 16px; margin: 16px 0; }}
 pre {{ background: #f6f6f6; padding: 12px; overflow-x: auto; font-size: 0.8rem; }}
 button {{ padding: 8px 20px; font-size: 1rem; }}
 ul {{ margin-top: 4px; }}
</style>
{body}
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body):
        encoded = PAGE.format(body=body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(form_page())
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        payload = build_payload(fields)
        try:
            result = serve(payload)
        except RequestError as exc:
            self._send(form_page(f"입력 오류: {exc}"))
            return
        self._send(result_page(result, payload))

    def log_message(self, fmt, *args):  # 한글 경로 로그로 콘솔이 깨지는 것을 막는다
        sys.stderr.write(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")


if __name__ == "__main__":
    print(f"종목 {len(SPORTS)}개 · 성인 축 {ADULT_AXES} · 노인 축 {ELDER_AXES}")
    for var in STRUCTURED_LABEL:
        _options(var)  # 표시 순서와 모델 levels 대조 (어긋나면 경고 출력)
    url = f"http://localhost:{PORT}"
    print(f"열기: {url}   (끄기: Ctrl+C)")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
