from __future__ import annotations

import time
from collections import deque
from types import TracebackType

from rich.console import Console, Group
from rich.highlighter import ReprHighlighter
from rich.live import Live
from rich.table import Table
from rich.text import Text

from beehouse_layout.solver.types import Solution, WorkerStatus


LOG_BUFFER_SIZE = 15
REFRESH_PER_SECOND = 2


class Dashboard:
    def __init__(self, num_workers: int) -> None:
        self._console = Console()
        self._recent_logs: deque[str] = deque(maxlen=LOG_BUFFER_SIZE)
        self._worker_statuses: dict[int, WorkerStatus] = {}
        self._worker_updated_at: dict[int, float] = {}
        self._best = Solution()
        self._num_workers = num_workers
        self._highlighter = ReprHighlighter()

    def __enter__(self) -> Dashboard:
        self._live = Live(self._build(), console=self._console, refresh_per_second=REFRESH_PER_SECOND)
        self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._live.__exit__(exc_type, exc_val, exc_tb)

    def log(self, message: str) -> None:
        self._recent_logs.append(message)
        self._refresh()

    def update_worker(self, status: WorkerStatus) -> None:
        self._worker_statuses[status.worker_id] = status
        self._worker_updated_at[status.worker_id] = time.monotonic()
        self._refresh()

    def update_best(self, solution: Solution) -> None:
        self._best = solution
        self._refresh()

    def _refresh(self) -> None:
        self._live.update(self._build())

    def _build(self) -> Group:
        table = Table()
        table.add_column("Worker", style="cyan", width=8)
        table.add_column("Iterations", justify="right")
        table.add_column("Temp", justify="right")
        table.add_column("Current BH", justify="right")
        table.add_column("Improvements", justify="right")
        table.add_column("Last Update", justify="right")

        now = time.monotonic()
        for wid in range(self._num_workers):
            if wid in self._worker_statuses:
                ws = self._worker_statuses[wid]
                age = now - self._worker_updated_at.get(wid, now)
                table.add_row(
                    str(wid),
                    f"{ws.iterations:,}",
                    f"{ws.temperature:.2f}",
                    str(ws.beehouse_count),
                    str(ws.improvements),
                    f"{age:.0f}s ago",
                )
            else:
                table.add_row(str(wid), "...", "...", "...", "...", "...")

        if self._best.beehouse_count > 0:
            best_text = Text(
                f"Best: {self._best.beehouse_count} beehouses, "
                f"{self._best.flower_count} flowers "
                f"({self._best.pot_count} pots), "
                f"{self._best.tour_steps} steps, "
                f"{self._best.route_turns} turns",
                style="bold green",
            )
        else:
            best_text = Text("Best: —", style="bold green")

        log_text = Text("\n".join(self._recent_logs))
        self._highlighter.highlight(log_text)
        return Group(table, best_text, Text(""), log_text)
