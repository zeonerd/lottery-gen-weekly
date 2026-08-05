"""SQLite 저장소."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from ..models import Draw, Ticket

DEFAULT_DB_PATH = Path("data/draws.db")
_SCHEMA = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA.read_text(encoding="utf-8"))

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- draws -------------------------------------------------------
    def upsert_draws(self, draws: list[Draw]) -> int:
        """신규 회차만 저장하고 저장된 건수를 반환한다."""
        rows = [
            (d.round, d.draw_date.isoformat(), d.group_no, *d.digits, d.bonus, _now())
            for d in draws
        ]
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO draws"
            " (round, draw_date, group_no, d1, d2, d3, d4, d5, d6, bonus, collected_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()
        return cur.rowcount

    def all_draws(self) -> list[Draw]:
        """회차 오름차순으로 전량 반환한다."""
        rows = self.conn.execute("SELECT * FROM draws ORDER BY round").fetchall()
        return [
            Draw(
                round=r["round"],
                draw_date=date.fromisoformat(r["draw_date"]),
                group_no=r["group_no"],
                digits=tuple(r[f"d{i}"] for i in range(1, 7)),
                bonus=r["bonus"],
            )
            for r in rows
        ]

    def latest_round(self) -> int | None:
        row = self.conn.execute("SELECT MAX(round) AS m FROM draws").fetchone()
        return row["m"]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM draws").fetchone()["c"]

    # --- recommendations ---------------------------------------------
    def save_recommendations(
        self,
        target_round: int,
        strategy: str,
        mode: str,
        tickets: list[Ticket],
        rules_hash: str | None = None,
    ) -> None:
        """같은 회차·전략의 기존 추천을 대체한다.

        추가가 아니라 대체인 이유: 한 회차에 사는 것은 한 세트뿐이다.
        재실행할 때마다 누적되면 백테스트에서 같은 주가 여러 번 계상된다.
        """
        self.conn.execute(
            "DELETE FROM outcomes WHERE recommendation_id IN"
            " (SELECT id FROM recommendations WHERE target_round = ? AND strategy = ?)",
            (target_round, strategy),
        )
        self.conn.execute(
            "DELETE FROM recommendations WHERE target_round = ? AND strategy = ?",
            (target_round, strategy),
        )
        self.conn.executemany(
            "INSERT INTO recommendations"
            " (target_round, strategy, mode, group_no, numbers, rules_hash, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (target_round, strategy, mode, t.group_no, t.number, rules_hash, _now())
                for t in tickets
            ],
        )
        self.conn.commit()

    # --- deliveries --------------------------------------------------
    def was_delivered(self, target_round: int, channel: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM deliveries WHERE target_round = ? AND channel = ?",
            (target_round, channel),
        ).fetchone()
        return row is not None

    def mark_delivered(self, target_round: int, channel: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO deliveries (target_round, channel, sent_at)"
            " VALUES (?,?,?)",
            (target_round, channel, _now()),
        )
        self.conn.commit()

    def recommendations_for(self, target_round: int) -> list[tuple[int, str, Ticket]]:
        rows = self.conn.execute(
            "SELECT id, strategy, group_no, numbers FROM recommendations"
            " WHERE target_round = ? ORDER BY strategy, group_no",
            (target_round,),
        ).fetchall()
        return [
            (r["id"], r["strategy"],
             Ticket(r["group_no"], tuple(int(c) for c in r["numbers"])))
            for r in rows
        ]
