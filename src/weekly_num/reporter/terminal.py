"""터미널용 리포트. 마크다운 기호 없이 그대로 읽히는 형태."""

from __future__ import annotations

from ..models import POSITION_NAMES
from .builder import ReportData
from .disclaimer import DISCLAIMER
from .markdown import _elimination_block

TAIL_POSITION = 5
WIDTH = 66


def _rule(char: str = "─") -> str:
    return char * WIDTH


def render(data: ReportData, verbose: bool = True) -> str:
    d = data
    iso = d.target_date.isocalendar()
    out: list[str] = []

    out.append(_rule("═"))
    out.append(f" 연금복권720+ 주간 추천 — {iso.year}년 {iso.week}주차")
    out.append(_rule("═"))
    out.append(f" 대상 회차 : {d.target_round}회 (추첨 {d.target_date})")
    out.append(
        f" 분석 데이터: {d.first_round}~{d.last_round}회 / 윈도우 {d.window_rounds}회차"
    )
    if d.seed is not None:
        out.append(f" ⚠ 시드 고정 실행 (seed={d.seed}) — 테스트용")
    for w in d.warnings:
        out.append(f" ⚠ {w}")
    out.append("")

    out.append("[1] 무작위 추첨")
    for t in d.random_tickets:
        out.append(f"    {t.group_no}조 - {t.number}")
    out.append("")

    out.append("[2] 분석 기반 추천")
    out.append("")
    out.append("  적용 규칙:")
    for r in d.active_rules:
        out.append(f"    · {r}")
    out.append("")

    if verbose:
        out.append("  소거 과정:")
        out.append("")
        for log in d.recommendation.position_logs:
            for line in _elimination_block(d, log).splitlines():
                out.append(f"  {line}" if line else "")
            out.append("")

    out.append("  최종 번호:")
    for t in d.recommendation.tickets:
        out.append(f"    {t.group_no}조 - {t.number[:5]}[{t.number[5]}]")
    tails = ", ".join(str(t.digits[TAIL_POSITION]) for t in d.recommendation.tickets)
    out.append("")
    out.append(f"    뒷자리 {tails} → 모두 상이 (R8 분산)")
    out.append(f"    7등 이상 적중 확률: {d.tail_hit_pct:.0f}%")
    for note in d.recommendation.notes:
        out.append(f"    ⚠ {note}")
    out.append("")

    out.append("[3] 데이터 노트")
    out.append(
        f"    자리별 기대 {d.expected_per_digit:.1f}회 / "
        f"정상 변동 {d.normal_low:.0f}~{d.normal_high:.0f}회"
    )
    for ps in d.position_stats:
        verdict = "유의" if ps.significant else "정상"
        out.append(
            f"    {ps.position + 1}번째({POSITION_NAMES[ps.position]}): "
            f"최다 {ps.max_digit}={ps.max_count}회, 최소 {ps.min_digit}={ps.min_count}회, "
            f"chi2={ps.chi:5.2f} p={ps.p_value:.3f} → {verdict}"
        )
    if d.longest_gap:
        g = d.longest_gap
        out.append(
            f"    가장 오래 잠든 숫자: {g.position + 1}번째 자리 '{g.digit}' "
            f"({g.count}회차 미출현)"
        )
    out.append("")
    out.append(DISCLAIMER)
    out.append("")
    return "\n".join(out)
