"""v0.1.3 结业作品提交：只建 capstone_submissions 一张表

Revision ID: 0009_capstone_submissions
Revises: 0008_review_items
Create Date: 2026-11-11 00:00:00+00:00

本迁移只做一件事：CREATE TABLE capstone_submissions 加它的一个索引。不建第二张
表，不改任何既有列，不 CREATE OR REPLACE 任何函数。既有 14 张产品表（外加
alembic_version）的行数在升级前后逐表相等，由 tests/test_migrations.py 在一次性
探针库里验证。

三条被冻结的诚实性约束都由数据库自己守住，应用层只是提前给它一个可读的错误码：

* status 只有 draft / submitted / reviewed 三态，没有"别人评审中"这类状态。
* reviewer 只有 'self' 一个合法值。本版本是单用户本地应用，不存在第三方评审者；
  数据库层面就无法写入第二个评审者，接口也就无法暗示存在人工评审。
* status = 'reviewed' 的行必须同时具备 verdict、reviewer = 'self' 与 reviewed_at：
  一次"已评审"不允许缺结论、缺评审者或缺时间戳。verify 与 reviewer 是同一件事。

readiness_snapshot 可空，因为"提交"与"达标"是两件独立的事：作品可以先交，
四条要求的快照由 POST /submit 在同一事务里写下，达标与否由它记录、由界面提示。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_capstone_submissions"
down_revision: str | None = "0008_review_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAPSTONE_SUBMISSIONS = """
CREATE TABLE capstone_submissions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title varchar(120) NOT NULL,
  summary text NOT NULL,
  repo_url varchar(300) NULL,
  run_instructions text NOT NULL,
  self_checks jsonb NOT NULL DEFAULT '[]'::jsonb,
  readiness_snapshot jsonb NULL,
  status varchar(16) NOT NULL DEFAULT 'draft'
    CONSTRAINT ck_capstone_submissions_status
    CHECK (status IN ('draft', 'submitted', 'reviewed')),
  verdict varchar(16) NULL
    CONSTRAINT ck_capstone_submissions_verdict
    CHECK (verdict IN ('pass', 'needs_work')),
  reviewer varchar(16) NULL
    CONSTRAINT ck_capstone_submissions_reviewer CHECK (reviewer IN ('self')),
  reviewer_note text NULL,
  submitted_at timestamptz NULL,
  reviewed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  -- 一次"已评审"不允许缺结论、缺评审者或缺时间戳；评审者只能是本人。
  CONSTRAINT ck_capstone_submissions_reviewed_complete CHECK (
    status <> 'reviewed'
    OR (verdict IS NOT NULL AND reviewer = 'self' AND reviewed_at IS NOT NULL)
  )
)
"""

# 列表与详情只有两条访问路径：按用户取最近的作品。
CAPSTONE_INDEX = (
    "CREATE INDEX ix_capstone_submissions_user_created "
    "ON capstone_submissions (user_id, created_at DESC)"
)


def upgrade() -> None:
    """Create exactly one table and its one index; no row, no other object changes."""
    op.execute(CAPSTONE_SUBMISSIONS)
    op.execute(CAPSTONE_INDEX)


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0009_capstone_submissions 不支持降级：v0.1.3 契约禁止 DROP/DELETE 类语句"
    )
