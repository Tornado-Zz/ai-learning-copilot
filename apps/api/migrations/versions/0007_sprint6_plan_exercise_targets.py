"""Sprint 6 - a plan item's target_id is checked by kind (lessons / exercises)

Revision ID: 0007_sprint6_plan_exercise_targets
Revises: 0006_sprint5_knowledge
Create Date: 2026-11-04 00:00:00+00:00

Sprint 6 把练习纳入周计划，kind='exercise' 的计划行开始真正落库。0003 的触发器
函数只校验 kind='lesson'，exercise 行当时恒为 0 行所以足够；现在同一个函数必须
按 kind 分派到 lessons / exercises 两张表。

本迁移只做一件事：CREATE OR REPLACE 同一个函数 fn_spi_lesson_target_exists，
函数名与触发器 trg_spi_lesson_target_exists 都保持不变（因此触发器的创建语句、
绑定关系与执行时机都不动）。不建表、不加列、不加约束、不重建触发器、不写一行
数据，也不执行任何 DROP/DELETE/TRUNCATE。

为什么保留函数名而不是改名：触发器按 OID 绑定函数，改名或重建触发器都会在本已
承载产品数据的表上做无谓的加锁与重建；CREATE OR REPLACE 只替换函数体。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_sprint6_plan_exercise_targets"
down_revision: str | None = "0006_sprint5_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 0003 相同的函数名、相同的 ERRCODE（23503 = foreign_key_violation），
# 只把校验从「只有 lesson」扩展为「lesson 查 lessons、exercise 查 exercises」。
TARGET_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_spi_lesson_target_exists() RETURNS trigger AS $fn$
BEGIN
  IF NEW.kind = 'lesson' AND NOT EXISTS (SELECT 1 FROM lessons WHERE id = NEW.target_id) THEN
    RAISE EXCEPTION 'study_plan_items.target_id 必须是真实存在的 lessons.id: %', NEW.target_id
      USING ERRCODE = '23503';
  END IF;
  IF NEW.kind = 'exercise'
     AND NOT EXISTS (SELECT 1 FROM exercises WHERE id = NEW.target_id) THEN
    RAISE EXCEPTION 'study_plan_items.target_id 必须是真实存在的 exercises.id: %', NEW.target_id
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END $fn$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Extend the target check to exercises without touching the table or any row."""
    op.execute(TARGET_TRIGGER_FUNCTION)


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0007_sprint6_plan_exercise_targets 不支持降级：Sprint 6 契约禁止 DROP/DELETE 类语句"
    )
