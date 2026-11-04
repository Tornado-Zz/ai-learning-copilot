"""Sprint 3 exercise catalogue and submissions

Revision ID: 0004_sprint3_exercises
Revises: 0003_sprint2_lessons_and_plan
Create Date: 2026-03-08 00:00:00+00:00

Creates exactly two tables - exercises, submissions - and seeds the ten
Sprint 3 practice exercises (two per Sprint 2 lesson). Nothing else is touched:
0001-0003 are not modified, the seven existing tables keep their structure and
every row they already hold, and only CREATE / INSERT statements are issued
(the project contract forbids DROP, DELETE, TRUNCATE and every downgrade path).

B1 evidence grading (frozen for stage B, the only allowed wording):

* judging_mode = 'static_rule' -> verification_method = 'static_rule'
  -> verification_strength = 'assessed' -> UI label 已验证（静态规则）
* judging_mode = 'self_check'  -> verification_method = 'self_report'
  -> verification_strength = 'self_reported' -> UI label 未验证（自检）

verification_strength is a STORED generated column, so 'verified' cannot be
written by any INSERT or UPDATE; ck_submissions_strength_never_verified states
that in the schema itself. Neither branch writes user_skill_levels, and the MVP
level ceiling stays at L2 (B1).

B2 red line: nothing in this schema invites execution of user code. code_text
is compared textually against required_patterns / forbidden_patterns, and
claimed_output is compared with expected_output as a normalised string.
**静态规则通过 ≠ 代码可运行** - a passing static rule only proves the text
contains the expected shapes, never that the program runs. Every judgement
created by this feature carries that disclaimer.

Deliberate choices:
* exercises.lesson_id is ON DELETE RESTRICT: an exercise without its lesson has
  no place in the curriculum, so the migration refuses to orphan it.
* submissions.exercise_id is also RESTRICT (submission history is audit
  evidence), while submissions.user_id cascades like every other user-owned row.
* uq_submissions_user_exercise_attempt makes attempt_no monotonic by database
  rule, not only by service code.
* ck_submissions_evidence_paired refuses a row whose mode and method disagree,
  so a static-rule submission can never be labelled as a self report (and the
  other way round). 'none' stays legal in the column CHECK to mirror
  user_skill_levels.verification_method, but no API path produces it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0004_sprint3_exercises"
down_revision: str | None = "0003_sprint2_lessons_and_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXERCISES = """
CREATE TABLE exercises (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  lesson_id bigint NOT NULL REFERENCES lessons(id) ON DELETE RESTRICT,
  code varchar(64) NOT NULL CONSTRAINT uq_exercises_code UNIQUE,
  title varchar(200) NOT NULL,
  prompt text NOT NULL,
  starter_code text NOT NULL,
  visible_tests jsonb NOT NULL,
  required_patterns jsonb NOT NULL DEFAULT '[]'::jsonb,
  forbidden_patterns jsonb NOT NULL DEFAULT '[]'::jsonb,
  expected_output text NULL,
  estimated_minutes smallint NOT NULL DEFAULT 10
    CONSTRAINT ck_exercises_estimated_minutes CHECK (estimated_minutes BETWEEN 1 AND 120),
  difficulty smallint NOT NULL DEFAULT 1
    CONSTRAINT ck_exercises_difficulty CHECK (difficulty BETWEEN 1 AND 5),
  status varchar(16) NOT NULL DEFAULT 'draft'
    CONSTRAINT ck_exercises_status CHECK (status IN ('draft', 'published', 'archived')),
  order_index smallint NOT NULL
    CONSTRAINT ck_exercises_order_index CHECK (order_index >= 1),
  content_version smallint NOT NULL DEFAULT 1
    CONSTRAINT ck_exercises_content_version CHECK (content_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  -- B3: every exercise ships at least two visible self-check cases.
  CONSTRAINT ck_exercises_visible_tests CHECK (
    jsonb_typeof(visible_tests) = 'array' AND jsonb_array_length(visible_tests) >= 2
  ),
  CONSTRAINT ck_exercises_required_patterns CHECK (jsonb_typeof(required_patterns) = 'array'),
  CONSTRAINT ck_exercises_forbidden_patterns CHECK (jsonb_typeof(forbidden_patterns) = 'array')
)
"""

SUBMISSIONS = """
CREATE TABLE submissions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id bigint NOT NULL REFERENCES exercises(id) ON DELETE RESTRICT,
  attempt_no integer NOT NULL
    CONSTRAINT ck_submissions_attempt_no CHECK (attempt_no >= 1),
  code_text text NOT NULL
    CONSTRAINT ck_submissions_code_text CHECK (length(btrim(code_text)) > 0),
  claimed_output text NULL,
  judging_mode varchar(16) NOT NULL
    CONSTRAINT ck_submissions_judging_mode
    CHECK (judging_mode IN ('static_rule', 'self_check')),
  verification_method varchar(16) NOT NULL
    CONSTRAINT ck_submissions_verification_method
    CHECK (verification_method IN ('static_rule', 'self_report', 'none')),
  -- B1: the only mapping from method to evidence strength. 'verified' is not
  -- reachable from here, which is why a submission can never claim it.
  verification_strength varchar(16) GENERATED ALWAYS AS (CASE
    WHEN verification_method = 'static_rule' THEN 'assessed'
    WHEN verification_method = 'self_report' THEN 'self_reported'
    ELSE 'none' END) STORED,
  is_passed boolean NULL,
  ai_assistance_level varchar(16) NOT NULL DEFAULT 'none'
    CONSTRAINT ck_submissions_ai_assistance_level
    CHECK (ai_assistance_level IN ('none', 'light', 'heavy')),
  used_ai boolean GENERATED ALWAYS AS (ai_assistance_level <> 'none') STORED,
  passed_with_ai boolean GENERATED ALWAYS AS (
    COALESCE(is_passed, false) AND ai_assistance_level <> 'none'
  ) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_submissions_user_exercise_attempt UNIQUE (user_id, exercise_id, attempt_no),
  CONSTRAINT ck_submissions_evidence_paired CHECK (
    verification_method = 'none'
    OR (judging_mode = 'static_rule' AND verification_method = 'static_rule')
    OR (judging_mode = 'self_check' AND verification_method = 'self_report')
  ),
  CONSTRAINT ck_submissions_strength_never_verified
    CHECK (verification_strength <> 'verified')
)
"""

INDEXES = (
    "CREATE INDEX ix_exercises_lesson_order ON exercises (lesson_id, order_index)",
    "CREATE INDEX ix_exercises_status ON exercises (status)",
    "CREATE INDEX ix_submissions_user_created "
    "ON submissions (user_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_submissions_user_exercise_created "
    "ON submissions (user_id, exercise_id, created_at DESC, id DESC)",
)

# Seed content lives in the migration, not in a runtime module: the request path
# only ever reads a row, so no request can rewrite an exercise. Patterns are raw
# strings because they are regular expressions (\b is not a backspace here).
SEED_EXERCISE = text(
    """
    INSERT INTO exercises (
        lesson_id, code, title, prompt, starter_code, visible_tests,
        required_patterns, forbidden_patterns, expected_output,
        estimated_minutes, difficulty, status, order_index, content_version
    )
    SELECT l.id, :code, :title, :prompt, :starter_code, :visible_tests,
           :required_patterns, :forbidden_patterns, :expected_output,
           :estimated_minutes, :difficulty, 'published', :order_index, :content_version
    FROM lessons l
    WHERE l.code = :lesson_code AND l.status = 'published' AND l.deleted_at IS NULL
    ON CONFLICT (code) DO NOTHING
    """
).bindparams(
    bindparam("visible_tests", type_=JSONB),
    bindparam("required_patterns", type_=JSONB),
    bindparam("forbidden_patterns", type_=JSONB),
)

EXERCISES_V1: tuple[dict[str, object], ...] = (
    # --- lesson 1: 变量与数据类型 -------------------------------------------
    {
        "lesson_code": "route_a.py.variables",
        "code": "route_a.py.variables.ex1",
        "title": "用变量记住四种类型并打印",
        "order_index": 1,
        "difficulty": 1,
        "estimated_minutes": 10,
        "prompt": (
            "目标：把 name / age / height / is_student 四个变量写完整，打印每个变量的类型，"
            "最后用 str() 拼出一句自我介绍。\n"
            "要做的事：\n"
            "1) name 用双引号写「小明」；\n"
            "2) age 是整数 18；\n"
            "3) height 是小数 1.75；\n"
            "4) is_student 是 True（首字母大写）；\n"
            "5) 用 type(变量名) 打印类型；\n"
            "6) 用 str(age) 把数字变成文本，拼出：小明 今年 18 岁。\n"
            "禁止：不许用 eval()、exec()、import；不许把整数和字符串直接相加"
            "（age + \"岁\" 会报 TypeError）。\n"
            "预计 10 分钟，难度 1。"
        ),
        "starter_code": (
            "# 1) 把四个变量的值填成题目要求的值\n"
            "name = \"\"\n"
            "age = 0\n"
            "height = 0.0\n"
            "is_student = False\n"
            "\n"
            "# 2) 打印每个变量的类型，例如 print(type(name))\n"
            "#    期望四行：<class 'str'> / <class 'int'> / <class 'float'> / <class 'bool'>\n"
            "\n"
            "# 3) 用 str(age) 拼出：小明 今年 18 岁\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "print(type(name)) 输出 <class 'str'>"},
            {
                "name": "自检 2",
                "expect": "print(type(age)) 输出 <class 'int'>，print(type(height)) 输出 <class 'float'>",
            },
            {"name": "自检 3", "expect": "最后一行输出是：小明 今年 18 岁"},
        ],
        "required_patterns": [
            r'name\s*=\s*"小明"',
            r"age\s*=\s*18\b",
            r"height\s*=\s*1\.75",
            r"is_student\s*=\s*True",
            r"type\s*\(\s*name\s*\)",
            r"type\s*\(\s*is_student\s*\)",
            r"str\s*\(\s*age\s*\)",
        ],
        "forbidden_patterns": [
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\bimport\s+\w+",
            r'age\s*\+\s*"',
            r"age\s*\+\s*'",
        ],
        "expected_output": (
            "<class 'str'>\n<class 'int'>\n<class 'float'>\n<class 'bool'>\n小明 今年 18 岁"
        ),
    },
    {
        "lesson_code": "route_a.py.variables",
        "code": "route_a.py.variables.ex2",
        "title": "把文本转成数字再计算",
        "order_index": 2,
        "difficulty": 1,
        "estimated_minutes": 8,
        "prompt": (
            "目标：age_text 里存的是文本 \"18\"，把它转成整数 18 存进 age，再打印 age + 1。\n"
            "要做的事：\n"
            "1) 用 int() 把 age_text 转成整数，赋给 age；\n"
            "2) 打印 age + 1，期望输出 19。\n"
            "禁止：不许用 eval()、exec()、import；不要直接把 \"18\" 和 1 相加。\n"
            "预计 8 分钟，难度 1。"
        ),
        "starter_code": (
            "age_text = \"18\"\n"
            "\n"
            "# 1) 用 int() 把文本转成整数，存进 age\n"
            "age = \n"
            "\n"
            "# 2) 打印 age + 1，期望输出 19\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "print(type(age)) 输出 <class 'int'>"},
            {"name": "自检 2", "expect": "最后一行的输出是 19"},
        ],
        "required_patterns": [
            r"int\s*\(\s*age_text\s*\)",
            r"print\s*\(\s*age\s*\+\s*1\s*\)",
        ],
        "forbidden_patterns": [r"\beval\s*\(", r"\bexec\s*\(", r"\bimport\s+\w+"],
        "expected_output": "19",
    },
    # --- lesson 2: 条件与循环 -----------------------------------------------
    {
        "lesson_code": "route_a.py.control_flow",
        "code": "route_a.py.control_flow.ex1",
        "title": "用 if / elif / else 判成绩等级",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 10,
        "prompt": (
            "目标：把 score = 85 换成成绩等级并打印出来。\n"
            "要做的事：\n"
            "1) 90 分及以上是 \"A\"；\n"
            "2) 80 分及以上是 \"B\"；\n"
            "3) 其余是 \"C\"；\n"
            "4) 必须用到 if、elif、else 三个分支，最后只打印一行等级，不要打印多余提示。\n"
            "禁止：不许用 while 循环，不许用 eval()。\n"
            "预计 10 分钟，难度 2。"
        ),
        "starter_code": (
            "score = 85\n"
            "\n"
            "# 用 if / elif / else 给 level 赋值，再打印它\n"
            "# 90 分及以上 -> \"A\"，80 分及以上 -> \"B\"，其余 -> \"C\"\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "score = 85 时输出 B"},
            {"name": "自检 2", "expect": "把 score 改成 95，输出变成 A；改成 60，输出变成 C"},
            {"name": "自检 3", "expect": "只打印一行，不要打印「你的等级是：」之类的前缀"},
        ],
        "required_patterns": [
            r"if\s+score\s*>=\s*90",
            r"elif\s+score\s*>=\s*80",
            r"else\s*:",
            r"print\s*\(",
        ],
        "forbidden_patterns": [r"\bwhile\b", r"\beval\s*\("],
        "expected_output": "B",
    },
    {
        "lesson_code": "route_a.py.control_flow",
        "code": "route_a.py.control_flow.ex2",
        "title": "用 for 循环把 1 到 10 加起来",
        "order_index": 2,
        "difficulty": 2,
        "estimated_minutes": 10,
        "prompt": (
            "目标：用 for 循环把 1 到 10 累加进 total，最后打印 total（期望 55）。\n"
            "要做的事：\n"
            "1) 用 for 循环搭配 range()，注意上界要写 11 才不会漏掉 10；\n"
            "2) 循环里用 total += i 累加；\n"
            "3) 循环结束后打印 total。\n"
            "禁止：不许用 sum() 一步算完（练习目的就是自己写循环）。\n"
            "预计 10 分钟，难度 2。"
        ),
        "starter_code": (
            "total = 0\n"
            "\n"
            "# 用 for 循环把 1 到 10 加起来（提示：range(1, 11) 是 1 到 10）\n"
            "\n"
            "# 循环结束后打印 total，期望 55\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "range 的上界写 11，否则会漏掉 10，结果是 45"},
            {"name": "自检 2", "expect": "最后输出 55"},
        ],
        "required_patterns": [
            r"for\s+\w+\s+in\s+range\s*\(",
            r"total\s*\+=\s*\w+",
            r"print\s*\(\s*total\s*\)",
        ],
        "forbidden_patterns": [r"\bsum\s*\(", r"\beval\s*\("],
        "expected_output": "55",
    },
    # --- lesson 3: 列表与字典 -----------------------------------------------
    {
        "lesson_code": "route_a.py.list_dict",
        "code": "route_a.py.list_dict.ex1",
        "title": "列表的取值与长度",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 10,
        "prompt": (
            "目标：建立列表 fruits = [\"苹果\", \"香蕉\"]，然后分别打印第一个元素、最后一个元素和列表长度。\n"
            "要做的事：\n"
            "1) 用 fruits[0] 取第一个元素，输出「苹果」；\n"
            "2) 用 fruits[-1] 取最后一个元素，输出「香蕉」（-1 表示倒数第一个）；\n"
            "3) 用 len(fruits) 打印列表长度，输出 2。\n"
            "禁止：不许用 eval()、import；不要用 fruits[1] 冒充「最后一个」（列表一变就错）。\n"
            "预计 10 分钟，难度 2。"
        ),
        "starter_code": (
            "# 1) 建立列表 fruits，放进「苹果」和「香蕉」两个元素\n"
            "fruits = []\n"
            "\n"
            "# 2) 打印第一个元素\n"
            "\n"
            "# 3) 用 -1 打印最后一个元素\n"
            "\n"
            "# 4) 打印列表长度\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "三行输出依次是：苹果 / 香蕉 / 2"},
            {"name": "自检 2", "expect": "取最后一个元素要用 fruits[-1]，不是 fruits[1]"},
        ],
        "required_patterns": [
            r"fruits\s*=\s*\[",
            r"fruits\s*\[\s*0\s*\]",
            r"fruits\s*\[\s*-1\s*\]",
            r"len\s*\(\s*fruits\s*\)",
        ],
        "forbidden_patterns": [r"\beval\s*\(", r"\bimport\s+\w+"],
        "expected_output": "苹果\n香蕉\n2",
    },
    {
        "lesson_code": "route_a.py.list_dict",
        "code": "route_a.py.list_dict.ex2",
        "title": "字典的取值与更新",
        "order_index": 2,
        "difficulty": 2,
        "estimated_minutes": 10,
        "prompt": (
            "目标：建立字典 person = {\"name\": \"小明\", \"age\": 18}，把 age 改成 19，再打印姓名和年龄。\n"
            "要做的事：\n"
            "1) 用双引号写键：\"name\" 和 \"age\"；\n"
            "2) 用 person[\"age\"] = 19 更新年龄；\n"
            "3) 打印一行：小明 19（用 person[\"name\"] 与 person[\"age\"]）。\n"
            "禁止：不许用 eval()；不许用 del 删键。\n"
            "预计 10 分钟，难度 2。"
        ),
        "starter_code": (
            "# 1) 建立字典 person，包含 name 和 age 两个键\n"
            "person = {}\n"
            "\n"
            "# 2) 把 age 改成 19\n"
            "\n"
            "# 3) 打印：小明 19\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "输出是：小明 19（同一行，中间一个空格）"},
            {"name": "自检 2", "expect": "字典的键必须用引号包起来，person[age] 会报 NameError"},
        ],
        "required_patterns": [
            r'person\s*=\s*\{',
            r'person\s*\[\s*"age"\s*\]\s*=\s*19',
            r'person\s*\[\s*"name"\s*\]',
        ],
        "forbidden_patterns": [r"\beval\s*\(", r"\bdel\s+"],
        "expected_output": "小明 19",
    },
    # --- lesson 4: 函数 -----------------------------------------------------
    {
        "lesson_code": "route_a.py.functions",
        "code": "route_a.py.functions.ex1",
        "title": "定义函数求两数之和",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 12,
        "prompt": (
            "目标：定义一个函数 add(a, b)，返回两个参数的和，然后打印 add(2, 3)。\n"
            "要做的事：\n"
            "1) 用 def add(a, b): 定义函数；\n"
            "2) 用 return 把结果交回给调用者（不要在里面直接 print）；\n"
            "3) 打印 add(2, 3)，期望输出 5。\n"
            "禁止：不许用 lambda，不许用 eval()。\n"
            "预计 12 分钟，难度 3。"
        ),
        "starter_code": (
            "# 1) 定义函数 add(a, b)，返回两个数的和\n"
            "\n"
            "\n"
            "# 2) 打印 add(2, 3)，期望输出 5\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "print(add(2, 3)) 输出 5"},
            {"name": "自检 2", "expect": "add 里用 return 而不是 print，否则 add(2, 3) 的值是 None"},
        ],
        "required_patterns": [
            r"def\s+add\s*\(\s*\w+\s*,\s*\w+\s*\)",
            r"return\s+",
            r"add\s*\(\s*2\s*,\s*3\s*\)",
        ],
        "forbidden_patterns": [r"\blambda\b", r"\beval\s*\("],
        "expected_output": "5",
    },
    {
        "lesson_code": "route_a.py.functions",
        "code": "route_a.py.functions.ex2",
        "title": "带默认参数的函数",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 12,
        "prompt": (
            "目标：定义函数 greet(name=\"同学\")，返回「你好，」加上 name；不传参数时用默认值。\n"
            "要做的事：\n"
            "1) 参数写成 name=\"同学\"（默认值，注意双引号和等号两边不留空格也可以）；\n"
            "2) 用 return 返回拼好的字符串；\n"
            "3) 打印 greet(\"小明\")，输出：你好，小明；\n"
            "4) 再打印 greet()，输出：你好，同学。\n"
            "禁止：不许用 eval()，不许把 print 写在函数里代替 return。\n"
            "预计 12 分钟，难度 3。"
        ),
        "starter_code": (
            "# 1) 定义函数 greet(name=\"同学\")，返回「你好，」+ name\n"
            "\n"
            "\n"
            "# 2) 打印 greet(\"小明\")，再打印 greet()\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "greet(\"小明\") 返回「你好，小明」"},
            {"name": "自检 2", "expect": "greet() 返回「你好，同学」（没有默认值就会报 TypeError）"},
        ],
        "required_patterns": [
            r'def\s+greet\s*\(\s*name\s*=\s*"同学"\s*\)',
            r"return\s+",
            r'greet\s*\(\s*"小明"\s*\)',
            r"greet\s*\(\s*\)",
        ],
        "forbidden_patterns": [r"\beval\s*\("],
        "expected_output": "你好，小明\n你好，同学",
    },
    # --- lesson 5: 调试 -----------------------------------------------------
    {
        "lesson_code": "route_a.py.debugging",
        "code": "route_a.py.debugging.ex1",
        "title": "修掉 TypeError：文本不能直接加数字",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 12,
        "prompt": (
            "目标：下面的代码会报 TypeError，读懂报错并修好它，让程序输出 7。\n"
            "要做的事：\n"
            "1) 看报错最后一行：can only concatenate str (not \"int\") to str；\n"
            "2) 分辨哪一个是文本、哪一个是数字；\n"
            "3) 用 int(a) 把文本转成数字，再相加。\n"
            "禁止：不许用 str(b) 绕过——那样得到的是 \"34\" 而不是 7；不许用 eval()、exec()。\n"
            "预计 12 分钟，难度 3。"
        ),
        "starter_code": (
            "a = \"3\"\n"
            "b = 4\n"
            "\n"
            "# 下面这行会报 TypeError: can only concatenate str (not \"int\") to str\n"
            "# 用 int() 把文本转成数字，修好这一行\n"
            "print(a + b)\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "修好后输出 7"},
            {"name": "自检 2", "expect": "如果用 str(b) 凑，输出是 34，说明类型搞反了"},
        ],
        "required_patterns": [r"int\s*\(\s*a\s*\)"],
        "forbidden_patterns": [r"\beval\s*\(", r"\bexec\s*\(", r"str\s*\(\s*b\s*\)"],
        "expected_output": "7",
    },
    {
        "lesson_code": "route_a.py.debugging",
        "code": "route_a.py.debugging.ex2",
        "title": "修好循环边界并累加求和",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 12,
        "prompt": (
            "目标：下面的循环少算了一个数，而且从没累加过。请修好它，让它先打印 1 到 5，再打印总和 15。\n"
            "要做的事：\n"
            "1) 把 range 的上界改成 6，让循环跑到 5；\n"
            "2) 在循环里用 total += i 累加；\n"
            "3) 循环结束后打印 total。\n"
            "禁止：不许用 sum() 一步算完。\n"
            "预计 12 分钟，难度 3。"
        ),
        "starter_code": (
            "total = 0\n"
            "\n"
            "for i in range(1, 5):\n"
            "    print(i)\n"
            "\n"
            "print(total)   # 期望 15\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "输出依次是 1 / 2 / 3 / 4 / 5 / 15"},
            {"name": "自检 2", "expect": "最后一行是 15，不是 0（0 说明没有累加）"},
        ],
        "required_patterns": [r"range\s*\(\s*1\s*,\s*6\s*\)", r"total\s*\+=\s*i"],
        "forbidden_patterns": [r"\bsum\s*\("],
        "expected_output": "1\n2\n3\n4\n5\n15",
    },
)


def upgrade() -> None:
    """Create the two Sprint 3 tables and seed the ten practice exercises."""
    for statement in (EXERCISES, *INDEXES[:2], SUBMISSIONS, *INDEXES[2:]):
        op.execute(statement)

    op.get_bind().execute(
        SEED_EXERCISE,
        [
            {
                "lesson_code": exercise["lesson_code"],
                "code": exercise["code"],
                "title": exercise["title"],
                "prompt": exercise["prompt"],
                "starter_code": exercise["starter_code"],
                # The JSONB bind type serialises the list; passing a JSON string
                # would store a JSON string instead of a JSON array.
                "visible_tests": exercise["visible_tests"],
                "required_patterns": exercise["required_patterns"],
                "forbidden_patterns": exercise["forbidden_patterns"],
                "expected_output": exercise["expected_output"],
                "estimated_minutes": exercise["estimated_minutes"],
                "difficulty": exercise["difficulty"],
                "order_index": exercise["order_index"],
                "content_version": 1,
            }
            for exercise in EXERCISES_V1
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0004_sprint3_exercises 不支持降级：Sprint 3 契约禁止 DROP/DELETE 类语句"
    )
