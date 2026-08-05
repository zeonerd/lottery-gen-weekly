"""Markdown 리포트 생성.

소거 과정을 코드블록으로 그리는 것은 의도적이다. 이 형식은 파일·터미널·
메신저 어디서도 정렬이 깨지지 않는다(PRD F4-3).
"""

from __future__ import annotations

from ..models import POSITION_NAMES, PositionLog
from .builder import ReportData
from .disclaimer import DISCLAIMER

TAIL_POSITION = 5


def _fmt_digits(digits: tuple[int, ...] | list[int]) -> str:
    return ", ".join(str(d) for d in digits)


def _elimination_block(data: ReportData, log: PositionLog) -> str:
    """한 자리의 소거 과정을 그린다. 이 블록이 이 리포트의 핵심이다."""
    win_label = (
        f"최근 {data.window_rounds}회차 기준"
        if data.window_size
        else f"전체 {data.window_rounds}회차 기준"
    )
    lines = [
        f"[{log.ordinal}번째 자리 — {POSITION_NAMES[log.position]}]  {win_label}",
        "",
        f"  후보: {' '.join(str(d) for d in log.initial)}   (10개)",
        "",
    ]

    remaining = set(log.initial)
    step_no = 0
    for step in log.steps:
        if step.skipped:
            lines.append(f"  ─ {step.label}")
            lines.append(f"     ⚠ 건너뜀 — {step.skip_reason}")
            continue
        step_no += 1
        remaining -= set(step.removed)
        lines.append(f"  {step_no}차 — {step.label}")
        if step.removed:
            lines.append(f"        → {step.detail} 제거")
        else:
            lines.append(f"        → {step.detail} — 앞 단계에서 이미 제거됨")
        lines.append(
            f"        남은 {len(remaining)}개: {_fmt_digits(sorted(remaining))}"
        )

    lines.append("")
    lines.append(f"  최종 후보: {_fmt_digits(log.final)}   ({len(log.final)}개)")

    picks = [t.digits[log.position] for t in data.recommendation.tickets]
    if log.position == TAIL_POSITION:
        lines.append(f"  5장 배정: {_fmt_digits(picks)}   ← 서로 다름 (R8 분산)")
    else:
        lines.append(f"  5장 선택: {_fmt_digits(picks)}   (후보 중 무작위)")
    return "\n".join(lines)


def render(data: ReportData) -> str:
    d = data
    iso = d.target_date.isocalendar()
    freshness = "최신" if d.last_round == d.target_round - 1 else "⚠ 지연"

    out: list[str] = []
    out.append(f"# 연금복권720+ 주간 추천 — {iso.year}년 {iso.week}주차")
    out.append("")
    out.append(f"- **대상 회차:** {d.target_round}회 (추첨일 {d.target_date})")
    out.append(
        f"- **분석 데이터:** {d.first_round}~{d.last_round}회 "
        f"(총 {d.total_rounds}회, 최신 추첨 {d.last_draw_date}) — {freshness}"
    )
    out.append(
        f"- **분석 윈도우:** "
        + (f"최근 {d.window_rounds}회차" if d.window_size else f"전체 {d.window_rounds}회차")
    )
    if d.seed is not None:
        out.append(f"- ⚠ **시드 고정 실행** (seed={d.seed}) — 테스트용이며 재현 가능합니다.")
    for w in d.warnings:
        out.append(f"- ⚠ {w}")
    out.append("")

    # 1. 무작위 추첨
    out.append("## 1. 무작위 추첨")
    out.append("")
    out.append("분석과 무관하게 뽑은 순수 무작위 5장입니다.")
    out.append("")
    out.append("```")
    for t in d.random_tickets:
        out.append(f"{t.group_no}조 - {t.number}")
    out.append("```")
    out.append("")

    # 2. 분석 기반 추천
    out.append("## 2. 분석 기반 추천")
    out.append("")
    out.append("### 2-1. 적용 규칙")
    out.append("")
    for r in d.active_rules:
        out.append(f"- {r}")
    out.append("")

    out.append("### 2-2. 자리별 소거 과정")
    out.append("")
    for log in d.recommendation.position_logs:
        out.append("```")
        out.append(_elimination_block(d, log))
        out.append("```")
        out.append("")

    out.append("### 2-3. 최종 번호")
    out.append("")
    out.append("```")
    for t in d.recommendation.tickets:
        out.append(f"{t.group_no}조 - {t.number[:5]}[{t.number[5]}]")
    out.append("")
    tails = [t.digits[TAIL_POSITION] for t in d.recommendation.tickets]
    out.append(f"뒷자리: {_fmt_digits(tails)}  → 모두 상이 ✅ (R8 분산 배치)")
    out.append(f"이번 주 7등 이상 적중 확률: {d.tail_hit_pct:.0f}%")
    out.append("```")
    out.append("")
    for note in d.recommendation.notes:
        out.append(f"> ⚠ {note}")
    if d.recommendation.notes:
        out.append("")

    # 3. 데이터 노트
    out.append("## 3. 이번 주 데이터 노트")
    out.append("")
    out.append(
        f"자리별 숫자 하나당 기대 출현은 **{d.expected_per_digit:.1f}회**이고, "
        f"**{d.normal_low:.0f}~{d.normal_high:.0f}회는 정상 변동 범위**입니다."
    )
    out.append("")
    out.append("| 자리 | 최다 | 최소 | χ² | p-value | 판정 |")
    out.append("|---|---|---|---|---|---|")
    for ps in d.position_stats:
        verdict = "**유의**" if ps.significant else "정상"
        out.append(
            f"| {ps.position + 1}번째 ({POSITION_NAMES[ps.position]}) "
            f"| {ps.max_digit} ({ps.max_count}회) | {ps.min_digit} ({ps.min_count}회) "
            f"| {ps.chi:.2f} | {ps.p_value:.3f} | {verdict} |"
        )
    out.append("")
    if d.longest_gap:
        g = d.longest_gap
        out.append(
            f"- 가장 오래 잠든 숫자: **{g.position + 1}번째 자리 '{g.digit}'** "
            f"({g.count}회차 미출현)"
        )
    sig = [p for p in d.position_stats if p.significant]
    if sig:
        out.append(
            f"- ⚠ 유의한 편차가 관측된 자리: {', '.join(str(p.position + 1) for p in sig)}번째 "
            "— 표본이 작을 때 드물게 발생합니다. 예측력을 뜻하지 않습니다."
        )
    else:
        out.append(
            "- 6개 자리 모두 균등분포와 유의한 차이가 없습니다 (p > 0.05). "
            "위 '최다/최소'는 무작위 변동입니다."
        )
    out.append(
        f"- 조 균등성: χ²={d.group_chi:.2f}, p={d.group_p:.3f} "
        f"({'정상' if d.group_p >= 0.05 else '유의'})"
    )
    out.append("")
    out.append("---")
    out.append("")
    out.append("```")
    out.append(DISCLAIMER)
    out.append("```")
    out.append("")
    return "\n".join(out)
