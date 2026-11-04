"""app.services.progress 的纯聚合助手（不需要数据库，默认档即可运行）。

端到端验收在 test_progress_overview.py（集成档）；这里只钉住三条与数据库无关的
规则：平均等级保留 1 位小数、活跃窗口固定 7 天且缺失补 0、达标判定在恰好达到时为真。
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services import progress


def test_average_level_keeps_one_decimal_and_handles_no_rows() -> None:
    assert progress.average_level(48, 30) == 1.6
    assert progress.average_level(2, 3) == 0.7
    assert progress.average_level(7, 1) == 7.0
    assert progress.average_level(0, 0) == 0.0


def test_activity_window_is_seven_days_ascending_with_zero_fill() -> None:
    today = date(2026, 11, 4)
    window = progress.activity_window(today, {date(2026, 11, 2): 45})

    assert len(window) == 7
    assert [item["date"] for item in window] == [
        today - timedelta(days=offset) for offset in range(6, -1, -1)
    ]
    assert window[-1] == {"date": today, "minutes": 0}
    assert window[4] == {"date": date(2026, 11, 2), "minutes": 45}
    assert sum(int(item["minutes"]) for item in window) == 45


def test_activity_window_ignores_dates_outside_the_window() -> None:
    today = date(2026, 11, 4)
    window = progress.activity_window(today, {date(2026, 10, 20): 99})

    assert [int(item["minutes"]) for item in window] == [0] * 7


def test_requirement_is_met_at_exactly_the_required_value() -> None:
    assert progress.requirement("k", "l", 5, 4)["met"] is False
    assert progress.requirement("k", "l", 5, 5)["met"] is True
    assert progress.requirement("k", "l", 5, 9)["met"] is True
    assert progress.requirement("k", "l", 0, 0)["met"] is True


def test_requirement_carries_the_frozen_five_fields() -> None:
    assert progress.requirement("exercises_passed", "通过至少 6 道练习", 6, 2) == {
        "key": "exercises_passed",
        "label": "通过至少 6 道练习",
        "required": 6,
        "actual": 2,
        "met": False,
    }
