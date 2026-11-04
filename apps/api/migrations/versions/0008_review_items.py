"""v0.1.2 错题本与间隔复习：只建 review_items 一张表

Revision ID: 0008_review_items
Revises: 0007_sprint6_plan_exercise_targets
Create Date: 2026-11-04 00:00:00+00:00

本迁移只做一件事：CREATE TABLE review_items 加它的一个索引。不建第二张表，不改
列，不改 0003 的 study_plan_items.kind CHECK（它从 0003 起就允许 'review'），也
不 CREATE OR REPLACE 0003/0007 的 fn_spi_lesson_target_exists（review 行的
target_id 由 app.services.study_plan 在写入前校验，数据库侧保持原样）。既有 14
张表的行数在升级前后逐表相等，由 tests/test_migrations.py 在一次性探针库里验证。

三个参照口径：

* user_id 级联删除：错题本是用户私有数据，用户没了它没有独立价值。
* exercise_id 是 RESTRICT：题在错题本里就代表学习证据，不允许因为删题而静默丢失。
* source_submission_id 可空且为 SET NULL：它只回答"是哪一次提交触发/推进了这条
  记录"，提交行被清掉时这条复习计划本身仍然有效，因此不级联、也不删除。

调度规则写在 app/services/review.py 里并逐条可测：
streak / interval_days / next_review_on / status / last_result 五个字段就是"间隔复习"
的全部状态，行永不删除，done 只是一种状态。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_review_items"
down_revision: str | None = "0007_sprint6_plan_exercise_targets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVIEW_ITEMS = """
CREATE TABLE review_items (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id bigint NOT NULL REFERENCES exercises(id) ON DELETE RESTRICT,
  source_submission_id bigint NULL REFERENCES submissions(id) ON DELETE SET NULL,
  streak integer NOT NULL DEFAULT 0
    CONSTRAINT ck_review_items_streak CHECK (streak >= 0),
  interval_days integer NOT NULL DEFAULT 1
    CONSTRAINT ck_review_items_interval_days CHECK (interval_days >= 1),
  next_review_on date NOT NULL,
  last_result varchar(16) NULL
    CONSTRAINT ck_review_items_last_result CHECK (last_result IN ('passed', 'failed')),
  last_reviewed_at timestamptz NULL,
  status varchar(16) NOT NULL DEFAULT 'pending'
    CONSTRAINT ck_review_items_status CHECK (status IN ('pending', 'done')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  -- 一道题在一个用户的错题本里只有一行：答错是 upsert，答对是在这一行上推进。
  CONSTRAINT uq_review_items_user_exercise UNIQUE (user_id, exercise_id)
)
"""

# 到期列表与 summary 的唯一访问路径：按 (user_id, next_review_on) 取今天及逾期的行。
REVIEW_INDEX = (
    "CREATE INDEX ix_review_items_user_next_review ON review_items (user_id, next_review_on)"
)


def upgrade() -> None:
    """Create exactly one table and its one index; no row, no other object changes."""
    op.execute(REVIEW_ITEMS)
    op.execute(REVIEW_INDEX)


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0008_review_items 不支持降级：v0.1.2 契约禁止 DROP/DELETE 类语句"
    )
