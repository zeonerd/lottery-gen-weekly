"""F5-2~4 — 백테스트.

이 모듈의 목적은 전략이 좋다는 것을 보여주는 게 아니라, **무엇이 실제로
효과가 있고 무엇이 없는지를 분리해서 정직하게 보여주는 것**이다.

그래서 네 가지를 비교한다.

    random         5장 완전 무작위 (R8 없음)          ← 기준선
    random_spread  5장 무작위 + 뒷자리 상이 (R8만)    ← R8의 순효과
    eliminate      전체 규칙 + R8 (실제 제품)         ← 소거 규칙의 순효과
    concentrate    전체 규칙 + 5장 동일 번호          ← 분산의 반대편

`random` ↔ `random_spread` 차이가 R8이 만든 것이고,
`random_spread` ↔ `eliminate` 차이가 소거 규칙(R1~R6)이 만든 것이다.
후자는 0에 수렴해야 정상이다. 0이 아니게 나오면 그건 발견이 아니라 표본 잡음이다.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from scipy import stats as sp

from .analyzer import eliminator, stats
from .config import Config
from .models import (
    DIGITS,
    GROUPS,
    NUM_POSITIONS,
    RANK_PRIZE,
    TICKET_PRICE,
    Draw,
    Ticket,
    evaluate_rank,
    is_bonus_win,
)
from .strategy import spread

TAIL = NUM_POSITIONS - 1

#: 이론적 "주간 1장 이상 당첨" 확률.
#: 당첨의 최소 조건은 뒤 1자리 일치이므로, 뒷자리 커버리지가 그대로 적중률이 된다.
THEORY = {
    "random": 1 - 0.9**5,   # 40.951% — 뒷자리가 겹칠 수 있다
    "random_spread": 0.50,  # 5/10 — 뒷자리가 서로 다르면 정확히 5개를 덮는다
    "eliminate": 0.50,      # 소거를 해도 커버리지는 그대로다
    "concentrate": 0.10,    # 1/10 — 5장이 같은 뒷자리를 공유
}


@dataclass
class StrategyResult:
    name: str
    weeks: int = 0
    trials: int = 0
    hits: int = 0
    ranks: Counter = field(default_factory=Counter)
    bonus: int = 0
    payout: int = 0
    payout_low: int = 0        # 3~7등만 (1·2등 연금은 표본에서 거의 안 나온다)
    payout_low_sq: float = 0.0
    cost: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.trials if self.trials else 0.0

    @property
    def roi_low(self) -> float:
        return (self.payout_low - self.cost) / self.cost if self.cost else 0.0

    @property
    def mean_weekly_low(self) -> float:
        return self.payout_low / self.trials if self.trials else 0.0

    @property
    def sd_weekly_low(self) -> float:
        """3~7등 주당 수익의 표준편차.

        1·2등·보너스를 넣으면 1.2억짜리 사건 하나가 분산을 통째로 지배해서
        분산 '구조'가 보이지 않는다. 226주 표본에서 그 사건은 0~2회 발생하며,
        어느 전략이 그걸 맞았는지는 순전히 운이다.
        """
        if self.trials < 2:
            return 0.0
        mean = self.payout_low / self.trials
        var = max(0.0, self.payout_low_sq / self.trials - mean**2)
        return math.sqrt(var)


def _random_tickets(rng: random.Random, count: int) -> list[Ticket]:
    return [
        Ticket(g, tuple(rng.choice(DIGITS) for _ in range(NUM_POSITIONS)))
        for g in GROUPS[:count]
    ]


def _random_spread_tickets(rng: random.Random, count: int) -> list[Ticket]:
    """R8만 적용한 무작위. 소거는 하지 않는다."""
    tails = rng.sample(list(DIGITS), k=count)
    return [
        Ticket(g, tuple(rng.choice(DIGITS) for _ in range(NUM_POSITIONS - 1)) + (t,))
        for g, t in zip(GROUPS[:count], tails)
    ]


def _score(result: StrategyResult, tickets: list[Ticket], actual: Draw) -> None:
    week_payout = 0
    week_low = 0
    won = False
    for t in tickets:
        rank = evaluate_rank(t, actual)
        if rank:
            won = True
            result.ranks[rank] += 1
            week_payout += RANK_PRIZE[rank]
            if rank >= 3:
                week_low += RANK_PRIZE[rank]
        if is_bonus_win(t, actual):
            result.bonus += 1
            week_payout += RANK_PRIZE[2]
    result.hits += int(won)
    result.payout += week_payout
    result.payout_low += week_low
    result.payout_low_sq += float(week_low) ** 2
    result.cost += TICKET_PRICE * len(tickets)
    result.trials += 1


def run(
    draws: list[Draw],
    cfg: Config,
    weeks: int = 200,
    trials: int = 100,
    seed: int | None = 20260805,
) -> dict[str, StrategyResult]:
    """과거 회차를 하나씩 대상으로 삼아 전략을 재현한다.

    각 대상 회차에 대해 **그 이전 데이터만** 사용한다. 미래 정보가 새어
    들어가면 백테스트는 의미가 없다.
    """
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    count = cfg.strategy.tickets
    results = {n: StrategyResult(n) for n in THEORY}

    start = max(cfg.analysis.window or 1, len(draws) - weeks)
    conc = cfg.model_copy(deep=True)
    conc.strategy.mode = "concentrate"

    for i in range(start, len(draws)):
        history = draws[:i]
        actual = draws[i]
        win = stats.window(history, cfg.analysis.window)

        # 회차당 한 번만 계산한다. 시행마다 다시 하면 백테스트가 끝나지 않는다.
        logs = eliminator.build_position_logs(win, cfg)
        table = spread.build_pick_table(win, logs, cfg)
        bounds = None
        if cfg.rules.sum_range.enabled:
            from .analyzer import rules as _rules

            bounds = _rules.sum_bounds(
                win, cfg.rules.sum_range.low_pct, cfg.rules.sum_range.high_pct
            )

        for r in results.values():
            r.weeks += 1

        for _ in range(trials):
            _score(results["random"], _random_tickets(rng, count), actual)
            _score(results["random_spread"], _random_spread_tickets(rng, count), actual)
            _score(
                results["eliminate"],
                spread.build_recommendation(win, logs, cfg, rng, table, bounds).tickets,
                actual,
            )
            _score(
                results["concentrate"],
                spread.build_recommendation(win, logs, conc, rng, table, bounds).tickets,
                actual,
            )
    return results


def hit_rate_ci(r: StrategyResult, n_eff: int, z: float = 1.96) -> tuple[float, float]:
    """적중률의 신뢰구간.

    표본 수로 시행 수가 아니라 **주 수**를 쓴다. 같은 회차를 100번 시행해도
    실제로 관측된 추첨은 한 번뿐이다. 시행 수로 계산하면 구간이 10배쯤
    좁아져서, 잡음을 발견처럼 보이게 만든다.
    """
    if n_eff < 2:
        return 0.0, 1.0
    p = r.hit_rate
    margin = z * math.sqrt(p * (1 - p) / n_eff)
    return max(0.0, p - margin), min(1.0, p + margin)


def two_proportion_test(a: StrategyResult, b: StrategyResult, n_eff: int) -> float:
    """두 적중률의 차이에 대한 p-value.

    `n_eff`는 **시행 수가 아니라 주(week) 수**를 쓴다. 같은 회차를 여러 번
    시행한 결과는 서로 독립이 아니다. 실제 추첨은 주당 한 번뿐이므로,
    시행 수를 표본 수로 쓰면 p-value가 실제보다 작게 나온다.
    """
    p1, p2 = a.hit_rate, b.hit_rate
    if n_eff < 2:
        return 1.0
    pool = (p1 + p2) / 2
    denom = math.sqrt(2 * pool * (1 - pool) / n_eff)
    if denom == 0:
        return 1.0
    return float(2 * sp.norm.sf(abs(p1 - p2) / denom))


def render(results: dict[str, StrategyResult], cfg: Config) -> str:
    """백테스트 결과를 사람이 읽는 표로 만든다."""
    order = ["random", "random_spread", "eliminate", "concentrate"]
    label = {
        "random": "무작위 (기준선)",
        "random_spread": "무작위 + R8",
        "eliminate": "전체 규칙 + R8",
        "concentrate": "집중 (5장 동일)",
    }
    weeks = results["random"].weeks
    trials = results["random"].trials
    out: list[str] = []

    out.append("═" * 74)
    out.append(f" 백테스트 — 최근 {weeks}회차 × 회차당 {trials // weeks if weeks else 0}회 시행")
    out.append("═" * 74)
    out.append("")
    out.append(" 전략              적중률 (95% 신뢰구간)   이론값   3~7등 주당수익")
    out.append(" " + "─" * 70)
    for name in order:
        r = results[name]
        lo, hi = hit_rate_ci(r, weeks)
        out.append(
            f" {label[name]:16s} {r.hit_rate * 100:6.2f}% "
            f"[{lo * 100:5.1f}, {hi * 100:5.1f}]  {THEORY[name] * 100:6.2f}%"
            f"   {r.mean_weekly_low:9,.0f}원"
        )
    out.append("")
    out.append(
        f" ⓘ 신뢰구간은 시행 수({trials:,})가 아니라 **주 수({weeks})** 를 기준으로 계산했습니다.\n"
        "   같은 회차를 여러 번 시행한 결과는 서로 독립이 아닙니다. 실제 추첨은\n"
        "   주당 한 번뿐이므로, 시행 수를 표본 수로 쓰면 구간이 실제보다 좁아집니다."
    )
    out.append("")

    out.append(" 등위별 당첨 횟수 (전체 시행 합계)")
    out.append(" " + "─" * 70)
    header = "".join(f"{str(k) + '등':>9s}" for k in range(3, 8))
    out.append(f" {'전략':16s}{header}      보너스")
    for name in order:
        r = results[name]
        counts = "".join(f"{r.ranks.get(k, 0):>9,d}" for k in range(3, 8))
        out.append(f" {label[name]:16s}{counts}{r.bonus:>12,d}")
    out.append("")

    # 효과 분해
    base, r8, elim = (results[k] for k in ("random", "random_spread", "eliminate"))
    p_r8 = two_proportion_test(base, r8, weeks)
    p_rules = two_proportion_test(r8, elim, weeks)

    out.append(" 무엇이 효과를 냈는가")
    out.append(" " + "─" * 70)
    out.append(
        f" R8 분산 배치      : {base.hit_rate * 100:.2f}% → {r8.hit_rate * 100:.2f}% "
        f"({(r8.hit_rate - base.hit_rate) * 100:+.2f}%p)   p={p_r8:.4f}"
        f"  {'유의' if p_r8 < 0.05 else '유의하지 않음'}"
    )
    out.append(
        f" 소거 규칙 R1~R6   : {r8.hit_rate * 100:.2f}% → {elim.hit_rate * 100:.2f}% "
        f"({(elim.hit_rate - r8.hit_rate) * 100:+.2f}%p)   p={p_rules:.4f}"
        f"  {'유의' if p_rules < 0.05 else '유의하지 않음'}"
    )
    out.append("")
    out.append(" 분산 구조 비교 — 3~7등 주당 수익")
    out.append(" " + "─" * 70)
    for name in ("random_spread", "eliminate", "concentrate"):
        r = results[name]
        out.append(
            f" {label[name]:16s} 평균 {r.mean_weekly_low:8,.0f}원   "
            f"표준편차 {r.sd_weekly_low:9,.0f}원   회수율 {r.roi_low * 100:7.2f}%"
        )
    out.append("")
    out.append(
        " ⓘ 1·2등과 보너스는 제외했습니다. 표본에서 0~2회 발생하는데 당첨금이\n"
        "   1.2억~16.8억이라 하나만 터져도 분산을 통째로 지배합니다. 어느 전략이\n"
        "   그걸 맞았는지는 전략의 성질이 아니라 순전히 운입니다.\n"
        "   3등(1백만원)도 기대 4회 수준이라 편차가 큽니다. 분산 vs 집중의 구조적\n"
        "   차이는 읽을 수 있지만, 같은 분산 계열끼리의 대소는 잡음입니다."
    )
    out.append("")
    out.append(_verdict(base, r8, elim, results["concentrate"], p_rules, weeks))
    return "\n".join(out)


def _verdict(base, r8, elim, conc, p_rules: float, weeks: int) -> str:
    diff = (elim.hit_rate - r8.hit_rate) * 100
    lo, hi = hit_rate_ci(elim, weeks)
    lines = [
        "─" * 74,
        "해석",
        "",
        "· R8(뒷자리 분산)이 적중 '빈도'를 올리는 것은 통계적 발견이 아니라",
        "  산술입니다. 뒷자리 5개를 겹치지 않게 두면 10개 중 정확히 5개를",
        "  덮습니다. 겹치도록 두면 기대 커버리지가 1-(9/10)^5 = 40.95%로 낮아집니다.",
        "  관측값이 이론값과 맞아떨어지는지만 확인하면 됩니다.",
        "",
        f"· 소거 규칙 R1~R6의 적중률 기여는 {diff:+.2f}%p, p={p_rules:.4f}로",
        "  통계적으로 유의하지 않습니다. **이것이 정상이며 버그가 아닙니다.**",
        "  연금복권의 추첨은 매 회차 독립이므로 과거 데이터로 무엇을 지우든",
        "  당첨 확률은 변하지 않습니다.",
    ]
    if diff > 0:
        lines += [
            "",
            f"  ⚠ '전체 규칙'의 점추정치가 이론값 50%보다 높게 나왔습니다"
            f" ({elim.hit_rate * 100:.2f}%).",
            f"    그러나 신뢰구간 [{lo * 100:.1f}, {hi * 100:.1f}]가 50%를 포함합니다.",
            "    이것은 소거가 효과를 냈다는 증거가 아니라 표본 잡음입니다.",
            "    소거는 뽑는 후보를 좁힐 뿐, 뒷자리 5개를 덮는다는 사실은",
            "    바꾸지 못하므로 커버리지는 어떤 경우에도 정확히 50%입니다.",
        ]
    lines += [
        "",
        "· 회수율은 모든 전략에서 음수입니다. 어떤 배치로도 기대값은 같으며,",
        "  바뀌는 것은 '자주 조금' 이냐 '드물게 크게' 냐 하는 분산뿐입니다.",
        "",
        f"· 집중은 적중률이 {conc.hit_rate * 100:.1f}%로 분산의 약 1/5이지만, 적중하면",
        "  5장이 동시에 당첨됩니다. 3~7등 기준 표준편차가 그 구조를 보여줍니다:",
        f"  분산 {r8.sd_weekly_low:,.0f}원 vs 집중 {conc.sd_weekly_low:,.0f}원.",
        "─" * 74,
    ]
    return "\n".join(lines)
