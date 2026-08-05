"""파일 알림 — 항상 동작한다.

다른 채널이 실패해도 리포트 자체는 남아야 한다(PRD F4-4). 이 알림기는
네트워크를 쓰지 않으며, 다른 채널과 항상 병행 실행된다.
"""

from __future__ import annotations

from pathlib import Path

from ..reporter.builder import ReportData
from ..reporter.markdown import render
from .base import DeliveryResult


class FileNotifier:
    name = "file"

    def __init__(self, directory: Path = Path("reports")) -> None:
        self.directory = Path(directory)

    def path_for(self, data: ReportData) -> Path:
        iso = data.target_date.isocalendar()
        return self.directory / f"{iso.year}-W{iso.week:02d}-{data.target_round}회.md"

    def send(self, data: ReportData) -> DeliveryResult:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.path_for(data)
            path.write_text(render(data), encoding="utf-8")
        except OSError as exc:
            return DeliveryResult(self.name, False, f"파일 저장 실패: {exc}")
        return DeliveryResult(self.name, True, str(path))
