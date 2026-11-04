"""Sprint 10 判题可读性：给每道题的每条必须写法配一句中文要求

Revision ID: 0014_sprint10_requirement_labels
Revises: 0013_sprint9_practice_content
Create Date: 2026-03-26 00:00:00+00:00

问题：判题失败时学习者只看到「第 4 项必须出现的写法没有出现」。题面没有编号，
规则本身是正则又是答案键（绝不能回给前端），于是「第 4 项」对学习者没有任何信息量。

做法：exercises 增加 requirement_labels jsonb，与 required_patterns **逐条一一对应、
顺序相同、条数相等**。这个顺序就是判题顺序，所以第 N 条标签说的正是第 N 条规则。

* 本迁移只为既有 22 道题的 124 条规则补标签，不改任何一行题面、不动用户数据；
* 只有 ADD COLUMN / 一条 CHECK 约束 / UPDATE 三类语句；没有 DROP / DELETE / TRUNCATE，
  也没有 downgrade 路径（项目契约禁止破坏性语句）；
* 回填是幂等的：每条 UPDATE 的赋值都是常量，重复执行结果相同；列与约束本身用
  IF NOT EXISTS / DO 块守着，重复执行不报错。

标签口径：≤ 40 字、动词开头、说「要做什么」而不写正则。判题是纯文本匹配，标签
只是把规则翻译成人话，既不是额外校验也不是答案键——真正的模式仍只留在库里。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0014_sprint10_requirement_labels"
down_revision: str | None = "0013_sprint9_practice_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADD_COLUMN = """
ALTER TABLE exercises
  ADD COLUMN IF NOT EXISTS requirement_labels jsonb NOT NULL DEFAULT '[]'::jsonb
"""

# 与 0004 的 ck_exercises_required_patterns / ck_exercises_forbidden_patterns 同口径：
# 只允许数组。DO 块让约束的创建可以重复执行，且不需要先 DROP 再加。
ADD_CHECK = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'exercises'
      AND c.conname = 'ck_exercises_requirement_labels'
  ) THEN
    ALTER TABLE exercises
      ADD CONSTRAINT ck_exercises_requirement_labels
      CHECK (jsonb_typeof(requirement_labels) = 'array');
  END IF;
END
$$;
"""

# 常量赋值 => 幂等：同一个库执行第 N 次与第 1 次结果完全一致。
# JSONB 绑定类型负责序列化，传 Python list 即落成 JSON 数组（不传 JSON 字符串）。
SET_REQUIREMENT_LABELS = text(
    """
    UPDATE exercises
    SET requirement_labels = :labels
    WHERE code = :code
    """
).bindparams(bindparam("labels", type_=JSONB))

# 22 道题 124 条规则，顺序与 required_patterns 严格一致；第 N 条标签说的就是第 N 条规则。
# 标签里刻意不出现括号/方括号/竖线/反斜杠：它们是正则记号，写给学习者的句子不需要它们。
REQUIREMENT_LABELS: dict[str, tuple[str, ...]] = {
    "route_a.py.variables.ex1": (
        "定义变量 name，赋值为小明",
        "定义变量 age，赋值为整数 18",
        "定义变量 height，赋值为小数 1.75",
        "定义变量 is_student，赋值为 True",
        "用 type 查看 name 的类型",
        "用 type 查看 is_student 的类型",
        "用 str 把 age 变成文本再拼接",
    ),
    "route_a.py.variables.ex2": (
        "用 int 把 age_text 转成整数",
        "打印 age 加 1 的结果",
    ),
    "route_a.py.control_flow.ex1": (
        "用 if 判断 score 大于等于 90",
        "用 elif 判断 score 大于等于 80",
        "补上 else 分支兜住其余情况",
        "用 print 打印出成绩等级",
    ),
    "route_a.py.control_flow.ex2": (
        "用 for 循环搭配 range 从 1 数到 10",
        "用累加把每个数字加进 total",
        "打印 total 的累加结果",
    ),
    "route_a.py.list_dict.ex1": (
        "定义列表 fruits 并放入两种水果",
        "用下标 0 取列表第一个元素",
        "用下标负一取列表最后一个元素",
        "用 len 打印列表的长度",
    ),
    "route_a.py.list_dict.ex2": (
        "定义字典 person 并放入姓名和年龄",
        "更新字典里 age 的值为 19",
        "取出字典里 name 键对应的姓名",
    ),
    "route_a.py.functions.ex1": (
        "定义一个名为 add、接受两个参数的函数",
        "用 return 把结果返回",
        "调用 add 并传入 2 和 3 验证结果",
    ),
    "route_a.py.functions.ex2": (
        "定义 greet 函数，参数 name 默认是同学",
        "用 return 返回拼好的问候语",
        "调用 greet 并传入小明",
        "调用 greet 且不传参数验证默认值",
    ),
    "route_a.py.debugging.ex1": (
        "用 int 把文本 a 转成数字再相加",
    ),
    "route_a.py.debugging.ex2": (
        "改 range 的上界为 6，让循环跑到 5",
        "用累加把 i 加进 total",
    ),
    "route_a.api.json.ex1": (
        "导入 json 模块",
        "用 json.loads 把 raw 解析成字典",
        "取出 response 里 status 的值",
        "取出 data 键对应的值",
        "取出 lesson 键对应的值",
        "取出 title 键里的课程标题",
        "取出 exercises 键里的练习列表",
        "用 sum 累加所有练习的分钟数",
        "取出每一项的 minutes 分钟数",
    ),
    "route_a.api.json.ex2": (
        "导入 json 模块",
        "定义函数 describe 接收一段响应文本",
        "用 json.loads 把文本解析成字典",
        "用 get 方法安全读出 status",
        "用 get 方法安全读出 error",
        "用 status 小于 400 判断调用成功",
        "用 print 打印出判断结果",
    ),
    "route_a.llm.messages.ex1": (
        "导入 json 模块",
        "写下 messages 消息数组",
        "设第一条消息的 role 为 system",
        "设第二条消息的 role 为 user",
        "设 temperature 为 0 到 1 之间的小数",
        "设 max_tokens 为正整数",
        "用 json.dumps 把请求体转成文本",
    ),
    "route_a.llm.messages.ex2": (
        "导入 json 模块",
        "用 json.loads 解析 response_text",
        "取出 choices 里的第一项",
        "取出 message 这一段",
        "用 content 键取出回答正文",
        "用 usage 键取出这次的用量",
        "用 total_tokens 取出总 token 数",
        "用 round 把花费四舍五入",
    ),
    "route_a.rag.retrieval.ex1": (
        "定义函数 score 计算关键词重合度",
        "定义函数 best_chunk 挑出最相关的一块",
        "用 split 把问题拆成关键词",
        "用 for 遍历每一块文档",
        "用 max 按分数取最高的那一块",
        "用 text 键取出块的原文",
        "用 id 键取出块的编号",
        "打印以 best 开头的胜出结果",
    ),
    "route_a.rag.retrieval.ex2": (
        "定义函数 build_prompt 拼出三行提示词",
        "定义函数 cite 给答案补上出处",
        "用 text 键把块的原文塞进提示词",
        "用 id 键取出块的编号当出处",
        "用换行符把三行提示词拼起来",
        "写出处标记，标明这段回答来自哪一块",
        "打印 cite 返回的带出处答案",
    ),
    "route_a.agent.tool.ex1": (
        "导入 json 模块",
        "设最外层的 type 为 function",
        "设工具名 name 为 get_weather",
        "用 description 写清楚什么时候该用",
        "用 parameters 描述工具的参数",
        "用 properties 声明 city 参数",
        "用 required 声明 city 是必填参数",
        "用 sorted 打印排好序的参数名",
        "用 json.dumps 把工具声明转成文本",
    ),
    "route_a.agent.tool.ex2": (
        "导入 json 模块",
        "用 json.loads 解析 response_text",
        "取出 choices 里的第一项",
        "用 tool_calls 取出这次要调用的工具",
        "用 arguments 取出参数文本",
        "用 finish_reason 看这次为什么停下",
        "用 json.loads 再解析 arguments 文本",
        "用工具名在 HANDLERS 里查到函数",
    ),
    "route_a.practice.decompose.ex1": (
        "定义函数 read_scores 读入每行成绩",
        "定义函数 average 只负责算平均分",
        "定义函数 report 只负责打印结果",
        "用逗号 split 拆开课名和分数",
        "用 int 把分数文本转成数字",
        "用 round 把平均分保留一位小数",
        "用 return 把分数字典交回调用者",
        "用 f 字符串按课名打印平均分",
    ),
    "route_a.practice.decompose.ex2": (
        "定义函数 total 接收列表算总分",
        "定义函数 average 接收列表算平均分",
        "用 return 加 sum 直接交出总分",
        "调用 total 拿到总分再算平均",
        "用 round 把平均分保留一位小数",
        "打印 average 返回的平均分",
        "用第二组数据 70、60、85 再算一次",
    ),
    "route_a.practice.debug.ex1": (
        "定义函数 error_kind 读出异常类型",
        "定义函数 error_line 读出出错行号",
        "用负一索引取报错的最后一行",
        "用 line 这个词定位行号那一行",
        "用 int 把行号文本转成整数",
        "用 strip 去掉行尾空白",
        "打印 error_kind 返回的异常类型",
    ),
    "route_a.practice.debug.ex2": (
        "用 get 取值，缺键时按 0 算",
        "用 for 遍历 names 逐个打印分数",
        "打印 score_of 返回的分数",
        "定义函数 score_of 查一个人的分数",
        "打印带 KeyError 和缺键名的定位结论",
        "用 return 加 get 安全返回分数",
    ),
}


def upgrade() -> None:
    """Add requirement_labels and backfill 124 Chinese labels for 22 exercises."""
    op.execute(ADD_COLUMN)
    op.execute(ADD_CHECK)
    op.get_bind().execute(
        SET_REQUIREMENT_LABELS,
        [{"code": code, "labels": list(labels)} for code, labels in REQUIREMENT_LABELS.items()],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0014_sprint10_requirement_labels 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
