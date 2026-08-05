"""HTML 리포트 (F4-1).

의존성 없이 단독으로 열리는 파일을 만든다. 외부 CSS·폰트·스크립트를
쓰지 않으므로 오프라인에서도 그대로 열린다.
"""

from __future__ import annotations

from html import escape

from ..models import POSITION_NAMES
from .builder import ReportData
from .disclaimer import DISCLAIMER
from .markdown import _elimination_block

TAIL_POSITION = 5

CSS = """
:root { color-scheme: light dark;
  --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e2e2e2;
  --card:#f7f7f8; --accent:#2b6cb0; --warn:#b7791f; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#16181c; --fg:#e8e8ea; --muted:#9aa0a6; --line:#2c2f36;
  --card:#1e2127; --accent:#7cb3ec; --warn:#e0b155; } }
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif; }
main { max-width:52rem; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
h2 { font-size:1.15rem; margin:2.5rem 0 .75rem; padding-bottom:.4rem;
  border-bottom:1px solid var(--line); }
h3 { font-size:1rem; margin:1.75rem 0 .5rem; color:var(--muted); }
.meta { color:var(--muted); font-size:.9rem; margin-bottom:2rem; }
.meta div { margin:.15rem 0; }
pre { background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:.9rem 1rem; overflow-x:auto; font-size:.85rem; line-height:1.55;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
table { border-collapse:collapse; width:100%; font-size:.9rem; display:block;
  overflow-x:auto; }
th,td { text-align:left; padding:.45rem .7rem; border-bottom:1px solid var(--line);
  white-space:nowrap; }
th { color:var(--muted); font-weight:600; }
.warn { color:var(--warn); }
.tickets { font-size:1.1rem; letter-spacing:.02em; }
.notice { background:var(--card); border-left:3px solid var(--accent);
  padding:.75rem 1rem; margin:1rem 0; font-size:.9rem; color:var(--muted); }
footer { margin-top:3rem; }
"""


def render(data: ReportData) -> str:
    d = data
    iso = d.target_date.isocalendar()
    e = escape
    out: list[str] = []
    a = out.append

    a(f"<!doctype html><html lang=ko><head><meta charset=utf-8>")
    a('<meta name="viewport" content="width=device-width,initial-scale=1">')
    a(f"<title>연금복권720+ {d.target_round}회 추천</title>")
    a(f"<style>{CSS}</style></head><body><main>")

    a(f"<h1>연금복권720+ {d.target_round}회 추천</h1>")
    a('<div class="meta">')
    a(f"<div>{iso.year}년 {iso.week}주차 · 추첨 {d.target_date}</div>")
    a(f"<div>분석 {d.first_round}~{d.last_round}회 · 윈도우 {d.window_rounds}회차</div>")
    if d.seed is not None:
        a(f'<div class="warn">⚠ 시드 고정 실행 (seed={d.seed}) — 테스트용</div>')
    for w in d.warnings:
        a(f'<div class="warn">⚠ {e(w)}</div>')
    a("</div>")

    a("<h2>분석 기반 추천</h2>")
    rows = "\n".join(
        f"{t.group_no}조 - {t.number[:5]}[{t.number[5]}]" for t in d.recommendation.tickets
    )
    tails = ", ".join(str(t.digits[TAIL_POSITION]) for t in d.recommendation.tickets)
    a(f'<pre class="tickets">{e(rows)}</pre>')
    a(
        f'<div class="notice">뒷자리 {e(tails)} → 모두 상이 (R8 분산 배치)<br>'
        f"이번 주 7등 이상 적중 확률 {d.tail_hit_pct:.0f}%</div>"
    )
    for note in d.recommendation.notes:
        a(f'<div class="notice warn">⚠ {e(note)}</div>')

    a("<h3>적용 규칙</h3><ul>")
    for r in d.active_rules:
        a(f"<li>{e(r)}</li>")
    a("</ul>")

    a("<h3>자리별 소거 과정</h3>")
    for log in d.recommendation.position_logs:
        a(f"<pre>{e(_elimination_block(d, log))}</pre>")

    a("<h2>무작위 추첨</h2>")
    a(f'<pre class="tickets">{e(chr(10).join(f"{t.group_no}조 - {t.number}" for t in d.random_tickets))}</pre>')

    a("<h2>데이터 노트</h2>")
    a(
        f"<p>자리별 숫자 하나당 기대 출현은 <b>{d.expected_per_digit:.1f}회</b>이고, "
        f"<b>{d.normal_low:.0f}~{d.normal_high:.0f}회는 정상 변동 범위</b>입니다.</p>"
    )
    a("<table><thead><tr><th>자리</th><th>최다</th><th>최소</th>"
      "<th>χ²</th><th>p-value</th><th>판정</th></tr></thead><tbody>")
    for ps in d.position_stats:
        verdict = '<span class="warn">유의</span>' if ps.significant else "정상"
        a(
            f"<tr><td>{ps.position + 1}번째 ({POSITION_NAMES[ps.position]})</td>"
            f"<td>{ps.max_digit} ({ps.max_count}회)</td>"
            f"<td>{ps.min_digit} ({ps.min_count}회)</td>"
            f"<td>{ps.chi:.2f}</td><td>{ps.p_value:.3f}</td><td>{verdict}</td></tr>"
        )
    a("</tbody></table>")
    if d.longest_gap:
        g = d.longest_gap
        a(
            f"<p>가장 오래 잠든 숫자: <b>{g.position + 1}번째 자리 '{g.digit}'</b> "
            f"({g.count}회차 미출현)</p>"
        )

    a(f"<footer><pre>{e(DISCLAIMER)}</pre></footer>")
    a("</main></body></html>")
    return "\n".join(out)
