"""설정 로딩과 검증.

설정 오류는 런타임 초기에 잡는다. 특히 `tail_diversity`는 분산 전략의
전제이므로 끌 수 없다(PRD F6-5, R8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class AnalysisConfig(BaseModel):
    window: int = Field(default=100, ge=0, description="분석 대상 최근 회차 수 (0=전체)")
    min_candidates: int = Field(default=2, ge=2, description="자리별 최소 후보 수 (Guard)")


class RecentExclusion(BaseModel):
    enabled: bool = True
    n: int = Field(default=3, ge=1)


class HotExclusion(BaseModel):
    enabled: bool = True
    top_k: int = Field(default=2, ge=1)


class ColdPreference(BaseModel):
    enabled: bool = True
    weight: float = Field(default=1.5, ge=1.0)


class AdjacentExclusion(BaseModel):
    enabled: bool = False


class ParityBalance(BaseModel):
    enabled: bool = True
    min_odd: int = Field(default=1, ge=0, le=6)
    max_odd: int = Field(default=5, ge=0, le=6)


class SumRange(BaseModel):
    enabled: bool = True
    low_pct: float = Field(default=10.0, ge=0, lt=50)
    high_pct: float = Field(default=90.0, gt=50, le=100)


class GroupRotation(BaseModel):
    enabled: bool = False
    lookback: int = Field(default=4, ge=1)


class RulesConfig(BaseModel):
    recent_exclusion: RecentExclusion = RecentExclusion()
    hot_exclusion: HotExclusion = HotExclusion()
    cold_preference: ColdPreference = ColdPreference()
    adjacent_exclusion: AdjacentExclusion = AdjacentExclusion()
    parity_balance: ParityBalance = ParityBalance()
    sum_range: SumRange = SumRange()
    group_rotation: GroupRotation = GroupRotation()


class StrategyConfig(BaseModel):
    mode: Literal["spread", "concentrate"] = "spread"
    tickets: int = Field(default=5, ge=1, le=5)
    tail_diversity: bool = True

    @field_validator("tail_diversity")
    @classmethod
    def _must_be_on(cls, v: bool) -> bool:
        # PRD F6-5-3. 분산 전략의 전제이므로 비활성화를 허용하지 않는다.
        if not v:
            raise ValueError(
                "tail_diversity는 끌 수 없습니다. 분산 전략(PRD §2.5, F6)의 전제입니다."
            )
        return v


class NotifyConfig(BaseModel):
    channel: Literal["telegram", "discord", "file"] = "file"
    schedule: str = "WED 20:00"
    parse_mode: Literal["HTML"] = "HTML"
    fallback_to_file: bool = True


class Config(BaseModel):
    locale: str = "ko"
    analysis: AnalysisConfig = AnalysisConfig()
    rules: RulesConfig = RulesConfig()
    strategy: StrategyConfig = StrategyConfig()
    notify: NotifyConfig = NotifyConfig()


DEFAULT_CONFIG_PATH = Path("config/rules.yaml")


def load_config(path: Path | str | None = None) -> Config:
    """YAML 설정을 읽어 검증한다. 파일이 없으면 기본값을 쓴다."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return Config()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)
