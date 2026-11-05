"""Sprint 2 Patch 的课程侧语义（S3 / S4）：完成同步计划项、计划完成 ≠ 课程完成、进度只前进。

九条验收里 ⑤⑥⑦ 在本文件，①②③④⑧⑨ 在 test_sprint2_patch_study_plan.py。

隔离策略沿用既有集成用例：读基线 → 事务内改档案 → 生成/断言 → 复原。写入路径用本测试
自建的一节课，因此不依赖真实用户已有的进度行；所有断言按 user_id 限定，外层事务回滚，
全程不执行 DELETE。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import ARRAY, SmallInteger, bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import calendar_today, future_weekdays

pytestmark = pytest.mark.integration

SET_USER_TIMEZONE = text(
    "UPDATE users SET timezone = :timezone, timezone_source = :source WHERE id = :user_id"
)
SET_PROFILE = text(
    "UPDATE user_profiles SET study_days = :days, daily_minutes = :daily_minutes "
    "WHERE user_id = :user_id"
).bindparams(bindparam("days", type_=ARRAY(SmallInteger)))
SELECT_WEEK_START = text("SELECT (date_trunc('week', now() AT TIME ZONE :timezone))::date")
SELECT_WEEK_ROWS = text(
    """
    SELECT id, plan_date, target_id, planned_minutes, status, dedupe_key, updated_at
    FROM study_plan_items
    WHERE user_id = :user_id AND week_start = :week_start
    ORDER BY plan_date, id
    """
)
SELECT_PROGRESS = text(
    """
    SELECT status, progress_pct, started_at, completed_at, updated_at
    FROM learning_progress
    WHERE user_id = :user_id AND lesson_id = :lesson_id
    """
)
COUNT_COMPLETED_PROGRESS = text(
    "SELECT count(*) FROM learning_progress "
    "WHERE user_id = :user_id AND lesson_id = :lesson_id AND status = 'completed'"
)
SELECT_COMPLETED_LESSON = text(
    "SELECT lesson_id FROM learning_progress "
    "WHERE user_id = :user_id AND status = 'completed' ORDER BY lesson_id LIMIT 1"
)
INSERT_TEST_LESSON = text(
    """
    INSERT INTO lessons (code, skill_id, stage, title, summary, content, estimated_minutes,
                         order_index, status)
    VALUES (:code, (SELECT id FROM skills WHERE code = 'route_a.a1'), 1, :title, :summary,
            :content, 20, 99, 'published')
    RETURNING id
    """
).bindparams(bindparam("content", type_=JSONB))

TEST_CONTENT = {
    "schema_version": 1,
    "goal": "验证进度只前进用的一节课",
    "explanation": ["只用于测试，迁移种子之外不会出现"],
    "example": {"title": "示例", "code": "print(1)", "notes": []},
    "common_mistakes": [{"mistake": "无", "why": "无", "fix": "无"}],
    "self_check": [
        {"question": "问题一？", "answer": "答案一"},
        {"question": "问题二？", "answer": "答案二"},
    ],
}


async def _baseline(api) -> dict[str, object]:
    me = (await api.get("/api/v1/users/me")).json()
    return {
        "user_id": int(me["user"]["id"]),
        "timezone": me["user"]["timezone"],
        "timezone_source": me["user"]["timezone_source"],
        "study_days": me["profile"]["study_days"],
        "daily_minutes": me["profile"]["daily_minutes"],
    }


async def _restore(db_session: AsyncSession, baseline: dict[str, object]) -> None:
    await db_session.execute(
        SET_USER_TIMEZONE,
        {
            "user_id": baseline["user_id"],
            "timezone": baseline["timezone"],
            "source": baseline["timezone_source"],
        },
    )
    await db_session.execute(
        SET_PROFILE,
        {
            "user_id": baseline["user_id"],
            "days": baseline["study_days"],
            "daily_minutes": baseline["daily_minutes"],
        },
    )


async def _confirmed(
    db_session: AsyncSession, user_id: int, *, study_days: list[int], daily_minutes: int
) -> tuple[object, object]:
    await db_session.execute(
        SET_USER_TIMEZONE,
        {"user_id": user_id, "timezone": "Asia/Shanghai", "source": "user_confirmed"},
    )
    await db_session.execute(
        SET_PROFILE,
        {"user_id": user_id, "days": study_days, "daily_minutes": daily_minutes},
    )
    monday = (
        await db_session.execute(SELECT_WEEK_START, {"timezone": "Asia/Shanghai"})
    ).scalar_one()
    return monday


async def _rows(
    db_session: AsyncSession, user_id: int, monday
) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in (
            await db_session.execute(
                SELECT_WEEK_ROWS, {"user_id": user_id, "week_start": monday}
            )
        ).mappings()
    ]


def _terminal(rows: list[dict[str, object]]) -> dict[int, tuple[str, object]]:
    return {
        int(row["id"]): (str(row["status"]), row["updated_at"])
        for row in rows
        if row["status"] in ("done", "skipped")
    }


async def _make_lesson(session: AsyncSession) -> int:
    suffix = uuid.uuid4().hex[:8]
    return int(
        (
            await session.execute(
                INSERT_TEST_LESSON,
                {
                    "code": f"pytest.patch.{suffix}",
                    "title": f"测试课程 {suffix}",
                    "summary": "仅测试用",
                    "content": TEST_CONTENT,
                },
            )
        ).scalar_one()
    )


async def _progress(session: AsyncSession, user_id: int, lesson_id: int) -> dict[str, object] | None:
    row = (
        (
            await session.execute(
                SELECT_PROGRESS, {"user_id": user_id, "lesson_id": lesson_id}
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def test_patch_05_completing_a_lesson_marks_its_scheduled_plan_item_done(
    api, db_session: AsyncSession
) -> None:
    """⑤ 完成课程后，同一事务内把该 lesson 的 scheduled 计划项置 done（其它行不动）。"""
    baseline = await _baseline(api)
    user_id = int(baseline["user_id"])
    try:
        # 不写死「周几」：走 HTTP 生成用的是真实时钟，写死周五会在周六日整片变红。
        monday, today = await calendar_today(db_session)
        days = future_weekdays(today, 1)
        if not days:
            pytest.skip("本周已无「今天及以后」的学习日")
        monday = await _confirmed(db_session, user_id, study_days=[days[0]], daily_minutes=480)
        generated = await api.post("/api/v1/study-plan/generate")
        assert generated.status_code == 200, generated.text
        rows = await _rows(db_session, user_id, monday)
        terminal_before = _terminal(rows)
        scheduled = [row for row in rows if row["status"] == "scheduled"]
        assert len(scheduled) >= 2, "需要至少两行才能证明只同步了本课程那一行"
        item = scheduled[0]
        lesson_id = int(item["target_id"])
        others = [int(row["id"]) for row in scheduled[1:]]
        assert await _progress(db_session, user_id, lesson_id) is None, "该课程此前从未打开"

        completed = await api.put(
            f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
        )
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["progress_pct"] == 100
        assert body["plan_items_completed"] == 1, "本次完成只应同步这一条计划项"

        after = await _rows(db_session, user_id, monday)
        by_id_after = {int(row["id"]): row for row in after}
        # 状态翻转即写入证据；时间戳在测试外层事务里是常量（PostgreSQL now() = 事务时间），
        # 所以这里只断言状态，updated_at 的稳定性由 ⑧ 用「快照相等」证明。
        assert by_id_after[int(item["id"])]["status"] == "done", "关联计划项必须同事务变 done"
        assert by_id_after[int(item["id"])]["dedupe_key"] == item["dedupe_key"]
        for other_id in others:
            assert by_id_after[other_id]["status"] == "scheduled", "其它课程的计划项不动"
        assert len(after) == len(rows), "同步只改状态，不加行"

        # 重复提交 completed 幂等：已没有可同步的 scheduled 行
        again = await api.put(
            f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
        )
        assert again.status_code == 200, again.text
        assert again.json()["plan_items_completed"] == 0

        # 计划项在响应里已经是 done
        plan = await api.get("/api/v1/study-plan")
        assert plan.status_code == 200, plan.text
        statuses = {
            int(entry["id"]): entry["status"]
            for day in plan.json()["days"]
            for entry in day["items"]
        }
        assert statuses[int(item["id"])] == "done"
        # 真实数据里的 done/skipped 历史行（其它课程）没有被顺手改写
        terminal_after = _terminal(after)
        for item_id, snapshot in terminal_before.items():
            if item_id == int(item["id"]):
                continue
            assert terminal_after[item_id] == snapshot

        print(
            f"课程完成同步: lesson={lesson_id} plan_item={item['id']} scheduled->done "
            f"plan_items_completed=1 再提交=0 others_scheduled={len(others)}"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_06_marking_a_plan_item_done_never_completes_the_lesson(
    api, db_session: AsyncSession
) -> None:
    """⑥ 计划项 done 只是执行完成，不等于课程完成：learning_progress 一行都不写。"""
    baseline = await _baseline(api)
    user_id = int(baseline["user_id"])
    try:
        # 不写死「周几」：走 HTTP 生成用的是真实时钟，写死周五会在周六日整片变红。
        monday, today = await calendar_today(db_session)
        days = future_weekdays(today, 1)
        if not days:
            pytest.skip("本周已无「今天及以后」的学习日")
        monday = await _confirmed(db_session, user_id, study_days=[days[0]], daily_minutes=480)
        assert (await api.post("/api/v1/study-plan/generate")).status_code == 200
        rows = await _rows(db_session, user_id, monday)
        item = next(row for row in rows if row["status"] == "scheduled")
        lesson_id = int(item["target_id"])
        progress_before = await _progress(db_session, user_id, lesson_id)

        patched = await api.patch(
            f"/api/v1/study-plan/items/{item['id']}", json={"status": "done"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "done"

        assert (
            await _progress(db_session, user_id, lesson_id)
        ) == progress_before, "计划项 done 不得写 learning_progress"
        assert int(
            (
                await db_session.execute(
                    COUNT_COMPLETED_PROGRESS,
                    {"user_id": user_id, "lesson_id": lesson_id},
                )
            ).scalar_one()
        ) == 0, "计划完成不得把课程标成 completed"

        detail = await api.get(f"/api/v1/lessons/{lesson_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["progress"] is None, "课程仍是未开始，UI 需要同时展示这两件事"

        print(
            f"计划项 done 不等于课程完成: plan_item={item['id']} status=done "
            f"lesson={lesson_id} progress={detail.json()['progress']} completed_rows=0"
        )
    finally:
        await _restore(db_session, baseline)


async def test_patch_07_progress_regression_is_422_with_zero_writes(
    api, db_session: AsyncSession
) -> None:
    """⑦ completed→in_progress 返回 422 COURSE_PROGRESS_REGRESSION，且库不变（含真实数据）。"""
    baseline = await _baseline(api)
    user_id = int(baseline["user_id"])
    try:
        seeded_completed = (
            await db_session.execute(SELECT_COMPLETED_LESSON, {"user_id": user_id})
        ).scalar_one_or_none()
        lesson_id = await _make_lesson(db_session)

        # 合法前进：not_started -> in_progress -> completed
        assert (
            await api.put(
                f"/api/v1/lessons/{lesson_id}/progress", json={"status": "in_progress"}
            )
        ).status_code == 200
        completed = await api.put(
            f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
        )
        assert completed.status_code == 200, completed.text
        snapshot = await _progress(db_session, user_id, lesson_id)
        assert snapshot is not None and snapshot["status"] == "completed"

        for requested in ("in_progress", "not_started"):
            rejected = await api.put(
                f"/api/v1/lessons/{lesson_id}/progress", json={"status": requested}
            )
            assert rejected.status_code == 422, rejected.text
            error = rejected.json()["error"]
            assert error["code"] == "COURSE_PROGRESS_REGRESSION"
            assert error["details"]["field"] == "status"
            assert error["details"]["reason"] == "course_progress_regression"
            assert error["details"]["current_status"] == "completed"
            assert error["details"]["requested_status"] == requested
            assert await _progress(db_session, user_id, lesson_id) == snapshot, (
                f"completed->{requested} 必须零写入（updated_at 都不能变）"
            )

        # in_progress -> not_started 同样是回退
        other_lesson = await _make_lesson(db_session)
        assert (
            await api.put(
                f"/api/v1/lessons/{other_lesson}/progress", json={"status": "in_progress"}
            )
        ).status_code == 200
        started_snapshot = await _progress(db_session, user_id, other_lesson)
        backwards = await api.put(
            f"/api/v1/lessons/{other_lesson}/progress", json={"status": "not_started"}
        )
        assert backwards.status_code == 422, backwards.text
        assert backwards.json()["error"]["code"] == "COURSE_PROGRESS_REGRESSION"
        assert await _progress(db_session, user_id, other_lesson) == started_snapshot

        # 相同状态重复提交是幂等 200，不是回退
        repeated = await api.put(
            f"/api/v1/lessons/{lesson_id}/progress", json={"status": "completed"}
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["completed_at"] == completed.json()["completed_at"]

        # 真实数据：种子里已完成的课程回退同样 422 且零写入
        if seeded_completed is not None:
            real_snapshot = await _progress(db_session, user_id, int(seeded_completed))
            assert real_snapshot is not None
            real = await api.put(
                f"/api/v1/lessons/{int(seeded_completed)}/progress",
                json={"status": "in_progress"},
            )
            assert real.status_code == 422, real.text
            assert real.json()["error"]["code"] == "COURSE_PROGRESS_REGRESSION"
            assert (
                await _progress(db_session, user_id, int(seeded_completed))
            ) == real_snapshot, "真实已完成课程的进度行必须原样"

        print(
            f"进度回退: completed->in_progress 422 {rejected.json()['error']['code']} "
            f"completed->not_started 422 in_progress->not_started 422 "
            f"同类重复提交 200 幂等 | 真实课程={seeded_completed} 行不变"
        )
    finally:
        await _restore(db_session, baseline)
