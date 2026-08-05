"""메신저용 포매터 (PRD F4-3).

텔레그램·디스코드·슬랙 셋 다 표(table)를 렌더링하지 못한다. 그래서
마크다운용 포매터를 그대로 재사용하면 표가 깨진다. 여기서는 표를
고정폭 코드블록으로 바꿔 내보낸다.

Telegram은 `parse_mode=HTML`을 쓴다. MarkdownV2는 `.`, `-`, `(` 등을 전부
이스케이프해야 하고 하나만 빠져도 HTTP 400으로 죽는데, 이 리포트는
숫자·괄호·하이픈 범벅이라 사고가 잦다. HTML은 `&`, `<`, `>` 셋만 처리하면 된다.
"""

from __future__ import annotations

from html import escape

from ..models import POSITION_NAMES
from .builder import ReportData
from .disclaimer import DISCLAIMER
from .markdown import _elimination_block

TAIL_POSITION = 5

#: Telegram sendMessage 본문 한도
TELEGRAM_LIMIT = 4096


def _pre(text: str) -> str:
    return f"<pre>{escape(text)}</pre>"


def render_html(data: ReportData, full: bool = True) -> str:
    """텔레그램 HTML 본문.

    `full=False`면 소거 과정을 빼고 결론만 싣는다. 본문이 한도를 넘을 때
    전문은 파일로 첨부하고 본문은 요약으로 대체하기 위한 것이다.
    """
    d = data
    iso = d.target_date.isocalendar()
    parts: list[str] = []

    parts.append(f"<b>연금복권720+ {d.target_round}회 추천</b>")
    parts.append(f"{iso.year}년 {iso.week}주차 · 추첨 {d.target_date}")
    parts.append("")

    if d.seed is not None:
        parts.append(f"⚠ 시드 고정 실행 (seed={d.seed}) — 테스트용")
    for w in d.warnings:
        parts.append(f"⚠ {escape(w)}")
    if d.seed is not None or d.warnings:
        parts.append("")

    parts.append("<b>■ 분석 기반 추천</b>")
    final = [f"{t.group_no}조 - {t.number[:5]}[{t.number[5]}]" for t in d.recommendation.tickets]
    tails = ", ".join(str(t.digits[TAIL_POSITION]) for t in d.recommendation.tickets)
    final.append("")
    final.append(f"뒷자리 {tails} → 모두 상이 (R8 분산)")
    final.append(f"7등 이상 적중 확률 {d.tail_hit_pct:.0f}%")
    parts.append(_pre("\n".join(final)))

    for note in d.recommendation.notes:
        parts.append(f"⚠ {escape(note)}")

    parts.append("")
    parts.append("<b>■ 무작위 추첨</b>")
    parts.append(_pre("\n".join(f"{t.group_no}조 - {t.number}" for t in d.random_tickets)))

    if full:
        parts.append("")
        parts.append("<b>■ 자리별 소거 과정</b>")
        for log in d.recommendation.position_logs:
            parts.append(_pre(_elimination_block(d, log)))

    parts.append("")
    parts.append("<b>■ 데이터 노트</b>")
    stat_lines = [
        f"분석 {d.first_round}~{d.last_round}회 / 윈도우 {d.window_rounds}회차",
        f"자리별 기대 {d.expected_per_digit:.1f}회 · 정상 변동 "
        f"{d.normal_low:.0f}~{d.normal_high:.0f}회",
        "",
    ]
    for ps in d.position_stats:
        stat_lines.append(
            f"{ps.position + 1}번째({POSITION_NAMES[ps.position]}): "
            f"최다 {ps.max_digit}={ps.max_count}회 최소 {ps.min_digit}={ps.min_count}회 "
            f"p={ps.p_value:.3f} {'유의' if ps.significant else '정상'}"
        )
    if d.longest_gap:
        g = d.longest_gap
        stat_lines.append("")
        stat_lines.append(
            f"가장 오래 잠든 숫자: {g.position + 1}번째 '{g.digit}' ({g.count}회차 미출현)"
        )
    parts.append(_pre("\n".join(stat_lines)))

    parts.append("")
    parts.append(_pre(DISCLAIMER))
    return "\n".join(parts)


def render_within_limit(data: ReportData) -> tuple[str, bool]:
    """한도에 맞는 본문을 만든다.

    반환값은 (본문, 전문을 파일로 첨부해야 하는가).
    """
    full = render_html(data, full=True)
    if len(full) <= TELEGRAM_LIMIT:
        return full, False
    summary = render_html(data, full=False)
    if len(summary) <= TELEGRAM_LIMIT:
        return summary, True
    return summary[: TELEGRAM_LIMIT - 20] + "\n…(생략)", True
