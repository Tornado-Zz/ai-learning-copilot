"""Sprint 2 lessons and study plan

Revision ID: 0003_sprint2_lessons_and_plan
Revises: 0002_sprint1a_identity_diagnostics
Create Date: 2026-03-01 00:00:00+00:00

Creates exactly three tables - lessons, learning_progress, study_plan_items -
and seeds the five Sprint 2 lessons (Python basics). No other table is touched,
0002 is not modified, and only CREATE / INSERT statements are issued: the
project rule forbids DROP, DELETE, TRUNCATE and every downgrade path.

Deliberate choices, each explained in the Sprint 2 report:
* lessons.code carries the UNIQUE identity that DATABASE.md 4.5 calls slug;
  lessons.content jsonb + content_version replace content_md so the five
  content blocks (goal / explanation / example / mistakes / self check) stay
  structured, and the JSONB carries schema_version as 1.4 requires.
* learning_progress.self_assessment replaces DATABASE.md 4.9 mastery_level and
  is capped at L2 by a CHECK: the Sprint 2 contract never lets a lesson
  self-assessment grant L3/L4 nor write user_skill_levels.
* study_plan_items.target_id gets no foreign key (DATABASE.md 4.14: a
  polymorphic reference must survive lesson removal), so the "target_id is a
  real lessons.id" rule is enforced by a trigger plus the service layer.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0003_sprint2_lessons_and_plan"
down_revision: str | None = "0002_sprint1a_identity_diagnostics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LESSONS = """
CREATE TABLE lessons (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code varchar(64) NOT NULL CONSTRAINT uq_lessons_code UNIQUE,
  skill_id bigint NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
  route_code varchar(32) NOT NULL DEFAULT 'route_a',
  stage smallint NOT NULL CONSTRAINT ck_lessons_stage CHECK (stage BETWEEN 1 AND 6),
  title varchar(200) NOT NULL,
  summary text NULL,
  content jsonb NOT NULL,
  content_version smallint NOT NULL DEFAULT 1
    CONSTRAINT ck_lessons_content_version CHECK (content_version >= 1),
  estimated_minutes smallint NOT NULL DEFAULT 15
    CONSTRAINT ck_lessons_estimated_minutes CHECK (estimated_minutes BETWEEN 1 AND 240),
  order_index smallint NOT NULL,
  difficulty smallint NOT NULL DEFAULT 1
    CONSTRAINT ck_lessons_difficulty CHECK (difficulty BETWEEN 1 AND 5),
  status varchar(16) NOT NULL DEFAULT 'draft'
    CONSTRAINT ck_lessons_status CHECK (status IN ('draft', 'published', 'archived')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL
)
"""

LEARNING_PROGRESS = """
CREATE TABLE learning_progress (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_id bigint NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
  status varchar(16) NOT NULL DEFAULT 'not_started'
    CONSTRAINT ck_learning_progress_status
    CHECK (status IN ('not_started', 'in_progress', 'completed')),
  self_assessment smallint NOT NULL DEFAULT 0
    CONSTRAINT ck_learning_progress_self_assessment CHECK (self_assessment BETWEEN 0 AND 2),
  progress_pct smallint NOT NULL DEFAULT 0
    CONSTRAINT ck_learning_progress_progress_pct CHECK (progress_pct BETWEEN 0 AND 100),
  time_spent_seconds integer NOT NULL DEFAULT 0
    CONSTRAINT ck_learning_progress_time_spent CHECK (time_spent_seconds >= 0),
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_learning_progress_user_lesson UNIQUE (user_id, lesson_id),
  CONSTRAINT ck_learning_progress_started_present
    CHECK (status = 'not_started' OR started_at IS NOT NULL),
  CONSTRAINT ck_learning_progress_completed_present
    CHECK (status <> 'completed' OR completed_at IS NOT NULL)
)
"""

STUDY_PLAN_ITEMS = """
CREATE TABLE study_plan_items (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start date NOT NULL,
  plan_date date NOT NULL,
  kind varchar(16) NOT NULL DEFAULT 'lesson'
    CONSTRAINT ck_spi_kind CHECK (kind IN ('lesson', 'exercise', 'review')),
  target_id bigint NOT NULL,
  planned_minutes smallint NOT NULL
    CONSTRAINT ck_spi_planned_minutes CHECK (planned_minutes BETWEEN 15 AND 480),
  status varchar(16) NOT NULL DEFAULT 'scheduled'
    CONSTRAINT ck_spi_status CHECK (status IN ('scheduled', 'done', 'skipped', 'expired')),
  rationale varchar(200) NOT NULL,
  dedupe_key varchar(120) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_study_plan_items_dedupe UNIQUE (user_id, dedupe_key),
  CONSTRAINT ck_spi_plan_date_in_week
    CHECK (plan_date >= week_start AND plan_date < week_start + 7)
)
"""

# DATABASE.md 4.14 refuses a foreign key on target_id (a lesson that is removed
# later must not delete the history that R1-R6 are audited against). The trigger
# keeps the "real lessons.id" guarantee without any cascade.
TARGET_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_spi_lesson_target_exists() RETURNS trigger AS $fn$
BEGIN
  IF NEW.kind = 'lesson' AND NOT EXISTS (SELECT 1 FROM lessons WHERE id = NEW.target_id) THEN
    RAISE EXCEPTION 'study_plan_items.target_id 必须是真实存在的 lessons.id: %', NEW.target_id
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END $fn$ LANGUAGE plpgsql
"""

TARGET_TRIGGER = """
CREATE TRIGGER trg_spi_lesson_target_exists BEFORE INSERT OR UPDATE ON study_plan_items
  FOR EACH ROW EXECUTE FUNCTION fn_spi_lesson_target_exists()
"""

INDEXES = (
    "CREATE INDEX ix_lessons_stage_order ON lessons (stage, order_index)",
    "CREATE INDEX ix_lessons_status ON lessons (status)",
    "CREATE INDEX ix_learning_progress_user_status ON learning_progress (user_id, status)",
    "CREATE INDEX ix_study_plan_items_user_week "
    "ON study_plan_items (user_id, week_start, plan_date)",
)

# Seeds the five Sprint 2 lessons. Contents live here, not in a runtime module:
# the request path only ever reads the row, so no request can rewrite a lesson.
SEED_LESSON = text(
    """
    INSERT INTO lessons (
        code, skill_id, route_code, stage, title, summary, content,
        content_version, estimated_minutes, order_index, difficulty, status
    )
    SELECT :code, s.id, 'route_a', :stage, :title, :summary, :content,
           :content_version, :estimated_minutes, :order_index, 1, 'published'
    FROM skills s WHERE s.code = 'route_a.a1'
    ON CONFLICT (code) DO NOTHING
    """
).bindparams(bindparam("content", type_=JSONB))

LESSONS_V1: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.py.variables",
        "stage": 1,
        "title": "变量与数据类型",
        "summary": "用名字记住数据，分清整数、小数、文本与真假值",
        "content_version": 1,
        "estimated_minutes": 20,
        "order_index": 1,
        "content": {
            "schema_version": 1,
            "goal": "能说出 int / float / str / bool 四种基本类型的区别，会给变量起有意义的名字，会用 type() 与类型转换，并能读懂 TypeError。",
            "explanation": [
                "变量就是给数据贴一个名字。age = 18 让 Python 记住 18，并把名字 age 指向它；之后写 age 就等于写 18。名字要说明含义，score 比 a 好得多。",
                "最常用的四种类型：int 是整数（18、-3），float 是小数（3.14、2.0），str 是文本（\"你好\"，必须用引号包起来），bool 只有 True 和 False 两个值（首字母大写）。",
                "type(x) 能查看一个值的类型；int(\"18\")、str(18)、float(\"3.14\") 可以在类型之间转换。转换失败会报 ValueError，例如 int(\"十八\")。",
                "不同类型不能随便混用：1 + \"1\" 会报 TypeError。Python 不会替你猜，先把字符串转成数字再算。",
                "命名规则：以字母或下划线开头，只能包含字母、数字、下划线；不能用 if、for 这类关键字；区分大小写，Age 与 age 是两个名字。",
            ],
            "example": {
                "title": "四种类型、查看类型与转换",
                "code": "name = \"小明\"\nage = 18\nheight = 1.75\nis_student = True\n\nprint(type(age))              # <class 'int'>\nprint(type(height))           # <class 'float'>\nprint(type(name))             # <class 'str'>\nprint(type(is_student))       # <class 'bool'>\n\nage_text = str(age)           # 把数字转成文本 \"18\"\nprint(name + \" 今年 \" + age_text + \" 岁\")\nprint(age + 1)                # 19",
                "output": "<class 'int'>\n<class 'float'>\n<class 'str'>\n<class 'bool'>\n小明 今年 18 岁\n19",
                "notes": [
                    "代码从上往下执行，前面定义的名字后面都能用。",
                    "print 只负责显示，不会改变数据本身。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "写 1 + \"1\"",
                    "why": "int 与 str 是不同类型，Python 不会自动把文本转成数字。",
                    "fix": "改成 1 + int(\"1\")，先转换再计算。",
                },
                {
                    "mistake": "变量名写成 my-name 或 2name",
                    "why": "my-name 会被当成 my 减 name；名字不能以数字开头。",
                    "fix": "用下划线：my_name、name2。",
                },
                {
                    "mistake": "把布尔值写成 true / false",
                    "why": "Python 的布尔值首字母必须大写，小写的 true 是一个未定义的名字。",
                    "fix": "写 True / False。",
                },
            ],
            "self_check": [
                {
                    "question": "a = \"3\" 与 b = 3 有什么区别？a + b 会怎样？",
                    "answer": "a 是字符串 str，b 是整数 int；a + b 报 TypeError，需要写 int(a) + b。",
                },
                {
                    "question": "x = 5、y = 2.0，print(x / y) 输出什么？",
                    "answer": "2.5。Python 的 / 除法结果总是 float，想要整数除法用 //（结果是 2）。",
                },
                {
                    "question": "为什么 print(\"年龄：\" + 18) 会报错？怎么改？",
                    "answer": "str 与 int 不能相加。改成 print(\"年龄：\" + str(18))，或用 f 字符串 print(f\"年龄：{18}\")。",
                },
            ],
        },
    },
    {
        "code": "route_a.py.control_flow",
        "stage": 1,
        "title": "条件判断与循环",
        "summary": "用 if 表达分支、用 for 与 while 重复执行，并避开死循环",
        "content_version": 1,
        "estimated_minutes": 25,
        "order_index": 2,
        "content": {
            "schema_version": 1,
            "goal": "能用 if / elif / else 写出多分支判断，能用 for 遍历一串数据、用 while 反复执行到条件不成立，并能识别死循环。",
            "explanation": [
                "分支结构：if 条件: 做某事，elif 条件: 做另一件事，else: 做剩下的。三个关键字后面都要有英文冒号，下一行必须缩进（统一 4 个空格）。",
                "比较运算有 >、<、>=、<=、==、!=；判断相等用两个等号。多个条件用 and（都要成立）、or（任一成立）、not（取反）连接。",
                "for 用来“把一串东西逐个处理”：for n in range(1, 6) 依次拿到 1、2、3、4、5；for ch in \"abc\" 依次拿到每个字符。",
                "while 用来“条件成立就一直做”：while count < 3。循环体里必须有让条件最终变成 False 的语句，否则程序永远停不下来（死循环）。",
                "break 立刻结束整个循环，continue 跳过本次剩余代码直接进入下一次。它们只在循环内部有效。",
            ],
            "example": {
                "title": "多分支判断、for 累加、while 计数",
                "code": "score = 72\nif score >= 85:\n    level = \"优秀\"\nelif score >= 60:\n    level = \"及格\"\nelse:\n    level = \"需要补基础\"\nprint(level)               # 及格\n\ntotal = 0\nfor n in range(1, 6):       # 1 到 5\n    total += n\nprint(total)                # 15\n\ncount = 0\nwhile count < 3:\n    print(\"第\", count + 1, \"次\")\n    count += 1              # 必须有这一行，否则死循环",
                "output": "及格\n15\n第 1 次\n第 2 次\n第 3 次",
                "notes": [
                    "缩进不是排版，是语法：同一分支的语句必须缩进一致。",
                    "range(1, 6) 含头不含尾，只有 1 到 5。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "if score > 60 后面漏了冒号",
                    "why": "Python 用冒号标记块的开始，缺冒号直接 SyntaxError。",
                    "fix": "写成 if score > 60:，下一行再缩进。",
                },
                {
                    "mistake": "while 循环体里忘了改计数器",
                    "why": "条件一直成立，循环永不结束，程序卡死。",
                    "fix": "在循环体里加 count += 1，并确保某次会让条件变假。",
                },
                {
                    "mistake": "用 = 判断相等，写成 if score = 60:",
                    "why": "一个等号是赋值，不是比较，条件位置会报 SyntaxError。",
                    "fix": "判断相等写 ==。",
                },
                {
                    "mistake": "缩进混用空格与 Tab",
                    "why": "Python 对缩进敏感，混用会报 IndentationError 或让代码落进别的分支。",
                    "fix": "统一用 4 个空格。",
                },
            ],
            "self_check": [
                {
                    "question": "range(3) 会产生哪些数字？for n in range(3) 的循环体执行几次？",
                    "answer": "0、1、2；执行 3 次。range 从 0 开始，含头不含尾。",
                },
                {
                    "question": "什么时候用 for，什么时候用 while？",
                    "answer": "已经知道要遍历哪些数据（列表、range、字符串）时用 for；只知道“重复到某个条件不成立”时用 while。",
                },
                {
                    "question": "这段代码为什么停不下来：i = 0 / while i < 5: / print(i)？",
                    "answer": "循环体里没有改变 i，条件永远成立。补上 i += 1。",
                },
            ],
        },
    },
    {
        "code": "route_a.py.list_dict",
        "stage": 1,
        "title": "列表与字典",
        "summary": "用列表存一串数据、用字典存有名字的字段，并安全地取值",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 3,
        "content": {
            "schema_version": 1,
            "goal": "会用列表按下标取值、切片与增删，会用字典按键取值并安全地 get，能判断该用列表还是字典，并避免 IndexError 与 KeyError。",
            "explanation": [
                "列表 list 是有顺序的一串数据，可以重复：nums = [3, 1, 4]。用下标访问，下标从 0 开始，nums[0] 是第一个，nums[-1] 是最后一个。",
                "切片 nums[1:3] 取下标 1 和 2（含头不含尾），结果是新列表。常用操作：append 追加、remove 删除、len 长度、in 判断是否存在、sort 排序。",
                "字典 dict 是键值对集合：{\"name\": \"小明\", \"age\": 18}。按 key 取值最快；d[\"score\"] 在键不存在时抛 KeyError，用 d.get(\"score\", 0) 更安全。",
                "遍历方式：for x in nums 逐个拿元素；for i, x in enumerate(nums) 同时拿下标；for k, v in d.items() 同时拿键和值。",
                "怎么选：一串同类数据用列表（学生姓名、分数）；一组有名字的字段用字典（一个人的姓名、年龄、城市）。列表和字典可以互相嵌套。",
            ],
            "example": {
                "title": "列表的增删取值、切片与字典的按键读取",
                "code": "nums = [3, 1, 4, 1, 5]\nnums.append(9)\nprint(nums[0], nums[-1])        # 3 9\nprint(nums[1:3])                # [1, 4]\nprint(len(nums), 5 in nums)     # 6 True\n\nstudent = {\"name\": \"小明\", \"age\": 18}\nstudent[\"age\"] = 19\nprint(student[\"name\"], student.get(\"score\", \"暂无成绩\"))\n\nfor key, value in student.items():\n    print(key, \"=\", value)",
                "output": "3 9\n[1, 4]\n6 True\n小明 暂无成绩\nname = 小明\nage = 19",
                "notes": [
                    "下标越界会抛 IndexError：长度为 n 的列表最大下标是 n-1。",
                    "遍历字典时不要增加或删除键，可以先复制一份 keys 列表。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "长度为 3 的列表去取 nums[3]",
                    "why": "下标从 0 开始，合法下标是 0、1、2，取 3 就越界了。",
                    "fix": "取最后一个用 nums[-1]，或先判断 len(nums) > 3。",
                },
                {
                    "mistake": "用 d[\"score\"] 读一个可能不存在的键",
                    "why": "键不存在时字典直接抛 KeyError，程序中断。",
                    "fix": "用 d.get(\"score\", 0)，或先判断 \"score\" in d。",
                },
                {
                    "mistake": "以为 nums.sort() 返回新列表",
                    "why": "sort() 就地排序、返回 None；把结果赋给变量会得到 None。",
                    "fix": "要么直接 nums.sort()，要么用 new = sorted(nums) 拿新列表。",
                },
            ],
            "self_check": [
                {
                    "question": "nums = [1, 2, 3, 4] 时，nums[1:3] 是什么？",
                    "answer": "[2, 3]。切片含头不含尾：从下标 1 取到下标 2。",
                },
                {
                    "question": "列表和字典最大的区别是什么？什么时候该用字典？",
                    "answer": "列表按位置存取、有顺序；字典按键存取、适合带名字的字段（姓名、年龄、城市）。取“某个字段”用字典，存“一串同类东西”用列表。",
                },
                {
                    "question": "报错 KeyError: 'score' 说明什么？怎么改？",
                    "answer": "字典里没有 score 这个键。改用 d.get(\"score\", 默认值)，或先确认 \"score\" in d 再取。",
                },
            ],
        },
    },
    {
        "code": "route_a.py.functions",
        "stage": 1,
        "title": "函数与参数",
        "summary": "把重复逻辑封装成函数，用参数传值、用 return 交回结果",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 4,
        "content": {
            "schema_version": 1,
            "goal": "会用 def 定义函数、用 return 返回结果，能区分位置参数与默认参数，理解函数内部的变量在外面看不到。",
            "explanation": [
                "def 定义函数，函数体缩进；return 把结果交回调用处。没有 return 的函数返回 None，这是最常见的“为什么我拿到 None”的原因。",
                "参数是函数的输入：位置参数按顺序传；默认参数给常用值，例如 def greet(name, greeting=\"你好\")，调用时不传就用默认值。",
                "带默认值的参数必须放在参数列表最后：def f(a, b=1) 合法，def f(a=1, b) 不合法。",
                "调用时可以用关键字更清楚：greet(greeting=\"嗨\", name=\"小明\")，顺序就不重要了。",
                "作用域：函数内部定义的变量外面看不到；函数要用的数据通过参数传进去，不要依赖全局变量。函数名用小写加下划线，动词开头，如 calc_total。",
            ],
            "example": {
                "title": "带默认参数的函数与返回值",
                "code": "def calc_total(prices, discount=0.0):\n    \"\"\"返回打折后的总价。\"\"\"\n    total = sum(prices)\n    return total * (1 - discount)\n\nprint(calc_total([10, 20, 30]))        # 60.0\nprint(calc_total([10, 20, 30], 0.1))   # 54.0\n\ndef is_adult(age):\n    return age >= 18\n\nprint(is_adult(20), is_adult(16))      # True False\n\ndef greet(name, greeting=\"你好\"):\n    return greeting + \"，\" + name\n\nprint(greet(\"小明\"))\nprint(greet(\"小明\", \"嗨\"))",
                "output": "60.0\n54.0\nTrue False\n你好，小明\n嗨，小明",
                "notes": [
                    "sum(prices) 把列表里的数加起来。",
                    "print 与 return 是两件事：print 只显示，return 才把值交给调用处。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "函数里只写了计算，忘了 return",
                    "why": "没有 return 的函数返回 None，调用处拿不到结果。",
                    "fix": "把最后一行改成 return 结果。",
                },
                {
                    "mistake": "把带默认值的参数写在前面：def f(a=1, b)",
                    "why": "Python 无法判断 b 该取哪个实参，直接 SyntaxError。",
                    "fix": "把带默认值的参数放到参数列表最后。",
                },
                {
                    "mistake": "用 print 代替 return",
                    "why": "print 只往屏幕输出，函数返回值仍是 None，后续无法继续计算。",
                    "fix": "函数内用 return，需要显示时在调用处 print。",
                },
                {
                    "mistake": "在函数里修改传入的列表，外面也变了",
                    "why": "列表是可变对象，函数拿到的是同一个对象的引用。",
                    "fix": "需要保持原数据时先复制：items = list(items)。",
                },
            ],
            "self_check": [
                {
                    "question": "函数里没有 return 语句时，调用它会得到什么？",
                    "answer": "None。想拿到结果必须在函数里写 return。",
                },
                {
                    "question": "def f(a, b=1) 与 def f(a=1, b) 哪个合法？为什么？",
                    "answer": "第一个合法。带默认值的参数必须放在没有默认值的参数后面。",
                },
                {
                    "question": "为什么下面打印 None：def double(x): x * 2 然后 print(double(3))？",
                    "answer": "函数里少了 return，x * 2 算完就丢了。改成 return x * 2。",
                },
            ],
        },
    },
    {
        "code": "route_a.py.debugging",
        "stage": 1,
        "title": "综合小练习与错误排查",
        "summary": "把输入-处理-输出写成小脚本，按报错信息定位五类高频错误",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 5,
        "content": {
            "schema_version": 1,
            "goal": "能把一个小需求拆成函数写成完整脚本，能读出 NameError / TypeError / IndexError / KeyError / IndentationError 的含义，并按 traceback 的行号定位问题。",
            "explanation": [
                "排查四步：先读 traceback 的最后一行（错误类型与说明），再看它指出的文件名与行号，然后打印相关变量确认值，最后把无关代码删掉做最小复现。",
                "五类高频错误：NameError 名字没定义（多半是拼错或用之前没赋值）；TypeError 类型不匹配（str 与 int 相加）；IndexError 下标越界；KeyError 字典键不存在；IndentationError 缩进不对。",
                "小脚本的结构：先定义函数（每个函数只做一件事），再准备数据，然后循环处理，最后打印结果。",
                "写完一段就运行一次，先让最短路径跑通，再加下一个功能。一次性写完再运行，报错时你不知道是哪一步引入的。",
                "遇到看不懂的值就 print(type(x), x)，不要凭感觉猜；确认类型和内容后再改代码。",
            ],
            "example": {
                "title": "统计字母出现次数并取前三名",
                "code": "def count_letters(text):\n    \"\"\"统计每个字母出现的次数，空格跳过。\"\"\"\n    result = {}\n    for ch in text.lower():\n        if ch == \" \":\n            continue\n        result[ch] = result.get(ch, 0) + 1\n    return result\n\ndef top_n(counter, n=3):\n    \"\"\"按次数从大到小取前 n 个。\"\"\"\n    pairs = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)\n    return pairs[:n]\n\ntext = \"hello world\"\ncounts = count_letters(text)\nprint(counts)\nprint(top_n(counts))",
                "output": "{'h': 1, 'e': 1, 'l': 3, 'o': 2, 'w': 1, 'r': 1, 'd': 1}\n[('l', 3), ('o', 2), ('h', 1)]",
                "notes": [
                    "lambda kv: kv[1] 是一个临时的小函数，等价于“按键值对的第二项排序”。",
                    "result.get(ch, 0) + 1 是“第一次出现记 1，之后累加”的标准写法。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "看到报错就直接改代码，不看 traceback",
                    "why": "报错最后一行已经写明错误类型，行号指向真正出问题的地方，跳过它就等于猜。",
                    "fix": "先读最后一行和行号，再定位到那一行。",
                },
                {
                    "mistake": "把变量名取成 list、dict、str 等内置名字",
                    "why": "会覆盖内置类型，后面再调用 list(...) 就报 TypeError。",
                    "fix": "换个名字，如 items、mapping、text。",
                },
                {
                    "mistake": "一个函数里做完所有事",
                    "why": "出错时无法判断是哪一步错，也无法单独测试。",
                    "fix": "拆成几个小函数，每个函数单独调用验证。",
                },
            ],
            "self_check": [
                {
                    "question": "看到 TypeError: can only concatenate str (not \"int\") to str，先检查什么？",
                    "answer": "找出哪一处把字符串和整数相加了，然后用 str() 或 int() 统一类型。",
                },
                {
                    "question": "IndexError: list index out of range 的常见原因有哪些？",
                    "answer": "下标大于等于 len（越界），或列表是空的却直接取 [0]。先 print(len(nums)) 确认长度。",
                },
                {
                    "question": "排查一个报错的前两步是什么？",
                    "answer": "第一步读 traceback 最后一行的错误类型与行号；第二步在那一行附近打印相关变量的 type 与值。",
                },
            ],
        },
    },
)


def upgrade() -> None:
    """Create the three Sprint 2 tables and seed the five Python lessons."""
    for statement in (
        LESSONS,
        *INDEXES[:2],
        LEARNING_PROGRESS,
        INDEXES[2],
        STUDY_PLAN_ITEMS,
        INDEXES[3],
        TARGET_TRIGGER_FUNCTION,
        TARGET_TRIGGER,
    ):
        op.execute(statement)

    op.get_bind().execute(
        SEED_LESSON,
        [
            {
                "code": lesson["code"],
                "stage": lesson["stage"],
                "title": lesson["title"],
                "summary": lesson["summary"],
                # The JSONB bind type serialises the dict; passing a JSON string
                # here would store a JSON string instead of a JSON object.
                "content": lesson["content"],
                "content_version": lesson["content_version"],
                "estimated_minutes": lesson["estimated_minutes"],
                "order_index": lesson["order_index"],
            }
            for lesson in LESSONS_V1
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0003_sprint2_lessons_and_plan 不支持降级：Sprint 2 契约禁止 DROP/DELETE 类语句"
    )
