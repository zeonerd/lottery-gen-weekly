"""알림 채널 추상화 (PRD F4-5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..reporter.builder import ReportData


@dataclass(slots=True)
class DeliveryResult:
    channel: str
    ok: bool
    detail: str = ""


class Notifier(Protocol):
    name: str

    def send(self, data: ReportData) -> DeliveryResult: ...
