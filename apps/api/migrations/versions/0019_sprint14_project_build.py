"""Sprint 14 内容：给 a6「简单 AI 项目」补一节「跟着做一遍」的实战课，以及两道练习

Revision ID: 0019_sprint14_project_build
Revises: 0018_sprint13_a5_a6_second_lessons
Create Date: 2026-11-13 00:00:00+00:00

0018 之后 a5 / a6 各有两节课（「项目范围与验收」「AI 项目的方法论」），但两节都在讲
方法与取舍，**没有一节把已有零件真正拼起来跑一遍**——初学者读完仍不知道「一个能跑的
小工具长什么样」。本迁移补上 route_a.project.build（40 分钟）：把前五个域学过的零件串成
一条主路径，读本地材料 -> 用关键词打分挑出最相关的一段 -> 把「材料 + 问题」拼成提示 ->
解析结构化回答 -> 打印带出处的结论，外加两道练习（共 14 条规则），课程到 16 节、
练习到 32 道。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 15 节课、30 道练习、199 条判题规则与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：正文与两道练习只用「本地字典里的材料」「本地字符串」当教材，模型回答由一段
固定示例文本代替（不联网、不需要密钥）；两道练习的 forbidden_patterns 都把「导入网络库」
与「真实地址字面量」写成正则禁止项，静态判题会直接拒掉联网写法。

order_index 取 16：lessons.order_index 上已有 1-15（0003 的 5 节 + 0011/0012 的 4 节 +
0013 的 a2 两节 + 0017 的 a3/a4 两节 + 0018 的 a5/a6 两节），本迁移只发 INSERT、不改写
既有行，因此新课只能接在后面；stage 仍是 a6 的 6，列表接口按 (stage, order_index) 排序时
它紧跟 route_a.project.scope，是 a6 的第三节。

requirement_labels 与 required_patterns **逐条一一对应、顺序相同、条数相等**（0014 建立
的契约）：第 N 条标签就是第 N 条规则，判题失败时学习者看到的是那句中文要求。两道题题面
点到「打印」「返回」「for」「sorted」「split」「get」的地方，各有一条规则与一条标签与之
对应（0015 / 0016 的口径）。

注意：示例代码与两道练习的起始代码里都有 \n 字面量（拼提示、拼结构化回答），因此这里的
三引号字符串一律加 r 前缀原样存放，避免 0017 那次「普通三引号把 \n 变成真换行」造出的
SyntaxError。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0019_sprint14_project_build"
down_revision: str | None = "0018_sprint13_a5_a6_second_lessons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库生成
# （lessons / exercises 用 identity，真实 id 早已过了 1109 / 30），硬编码会在另一个库上
# 指向错误的行。这条口径与 0003 / 0004 / 0011 / 0012 / 0013 / 0017 / 0018 完全一致。
SEED_LESSON = text(
    """
    INSERT INTO lessons (
        code, skill_id, route_code, stage, title, summary, content,
        content_version, estimated_minutes, order_index, difficulty, status
    )
    SELECT :code, s.id, 'route_a', :stage, :title, :summary, :content,
           :content_version, :estimated_minutes, :order_index, :difficulty, 'published'
    FROM skills s
    WHERE s.code = :skill_code
    ON CONFLICT (code) DO NOTHING
    """
).bindparams(bindparam("content", type_=JSONB))

SEED_EXERCISE = text(
    """
    INSERT INTO exercises (
        lesson_id, code, title, prompt, starter_code, visible_tests,
        required_patterns, forbidden_patterns, requirement_labels, expected_output,
        estimated_minutes, difficulty, status, order_index, content_version
    )
    SELECT l.id, :code, :title, :prompt, :starter_code, :visible_tests,
           :required_patterns, :forbidden_patterns, :requirement_labels, :expected_output,
           :estimated_minutes, :difficulty, 'published', :order_index, :content_version
    FROM lessons l
    WHERE l.code = :lesson_code AND l.status = 'published' AND l.deleted_at IS NULL
    ON CONFLICT (code) DO NOTHING
    """
).bindparams(
    bindparam("visible_tests", type_=JSONB),
    bindparam("required_patterns", type_=JSONB),
    bindparam("forbidden_patterns", type_=JSONB),
    bindparam("requirement_labels", type_=JSONB),
)

# ---------------------------------------------------------------------------
# 课程 16：跟着做：把零件拼成一个小问答（a6）
# ---------------------------------------------------------------------------

BUILD_EXAMPLE_CODE = r"""# 一条主路径的五个零件：读本地材料 -> 打分挑最相关的一段 -> 拼提示 -> 解析回答 -> 打印带出处的结论

MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}
QUESTION = "检索增强的步骤是什么"
KEYWORDS = ["检索", "片段", "引用"]


def score(text, keywords):
    # 打分就是数命中几个关键词：简单、可解释，而且能脱离模型单独测
    return sum(1 for word in keywords if word in text)


def pick(materials, keywords):
    # sorted 按分数从高到低排，取第一个：挑哪一段由代码决定，不由模型决定
    ranked = sorted(materials.items(), key=lambda item: score(item[1], keywords), reverse=True)
    return ranked[0][0]


def build_prompt(question, material_id, materials):
    # 提示是拼出来的字符串：材料 + 问题 + 输出格式，三块都要能单独打印出来看
    return "\n".join(
        [
            "材料：" + material_id + " " + materials[material_id],
            "问题：" + question,
            "要求：只依据材料回答，输出 ANSWER 与 SOURCE 两行。",
        ]
    )


def ask_model(prompt):
    # 模型回答由固定示例文本代替：不联网、不需要密钥。换真模型时只改这一个函数
    if "检索" in prompt:
        return "ANSWER: 先取回原文片段，再基于片段回答\nSOURCE: M2"
    return "ANSWER: 材料里没有提到\nSOURCE: 无"


def parse(reply):
    # 解析要求回答有固定格式：每行「字段: 值」。没有格式就没有可靠的解析
    fields = {}
    for line in reply.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


material_id = pick(MATERIALS, KEYWORDS)
prompt = build_prompt(QUESTION, material_id, MATERIALS)
print("=== 拼好的提示 ===")
print(prompt)
reply = ask_model(prompt)
print("=== 模型回答（示例文本）===")
print(reply)
fields = parse(reply)
print("=== 带出处的结论 ===")
source = fields.get("SOURCE", "无")
print("结论：" + fields.get("ANSWER", "解析失败"))
print("出处：" + source + " -> " + MATERIALS.get(source, "材料里没有这条编号"))
"""

BUILD_EXAMPLE_OUTPUT = (
    "=== 拼好的提示 ===\n"
    "材料：M2 检索增强要先取回原文片段，再让模型基于片段回答。\n"
    "问题：检索增强的步骤是什么\n"
    "要求：只依据材料回答，输出 ANSWER 与 SOURCE 两行。\n"
    "=== 模型回答（示例文本）===\n"
    "ANSWER: 先取回原文片段，再基于片段回答\n"
    "SOURCE: M2\n"
    "=== 带出处的结论 ===\n"
    "结论：先取回原文片段，再基于片段回答\n"
    "出处：M2 -> 检索增强要先取回原文片段，再让模型基于片段回答。"
)

# ---------------------------------------------------------------------------
# 2 道练习的起始代码（只给骨架与说明，判题时注释与 docstring 会被剥离）
# ---------------------------------------------------------------------------

BUILD_EX1_STARTER = r"""# 三份离线材料：编号 -> 原文（教学材料，不联网）
MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}
QUESTION = "检索增强的步骤是什么"
KEYWORDS = ["检索", "片段", "引用"]


def score(text, keywords):
    # 1) 返回这段材料命中了几个关键词
    pass


def pick(materials, keywords):
    # 2) 用 sorted 按分数从高到低排，返回分数最高那一段的编号
    pass


def build_prompt(question, material_id, materials):
    # 3) 返回三行提示：材料 / 问题 / 要求，行与行之间用换行符连起来
    pass


# 4) 用 for 逐条打印每份材料的编号与分数
# 5) 打印挑中的材料编号，再打印拼好的提示
"""

BUILD_EX2_STARTER = r"""# 三份离线材料：编号 -> 原文（教学材料，不联网）
MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}

# 两份模型回答（示例文本代替模型输出，不联网、不需要密钥）：第二份缺 SOURCE 那一行
REPLIES = [
    "ANSWER: 先取回原文片段，再基于片段回答\nSOURCE: M2",
    "ANSWER: 先取回原文片段，再基于片段回答",
]


def parse_reply(reply):
    # 1) 用 split 逐行按「字段: 值」切开，返回 {字段: 值} 的字典
    pass


def source_of(fields, materials):
    # 2) 用 get 取 SOURCE；它在 materials 里就返回该编号，否则返回「无」
    pass


# 3) 用 for 逐份处理 REPLIES，每份打印两行：第 N 份 结论：… 与 第 N 份 出处：…
# 4) 出处是编号时打印「编号 原文」，是「无」时只打印「无」
"""

LESSONS_V7: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.project.build",
        "skill_code": "route_a.a6",
        "stage": 6,
        "title": "跟着做：把零件拼成一个小问答",
        "summary": (
            "把前五个域学过的零件串成一条主路径：读本地材料 → 关键词打分挑出最相关的一段 → "
            "把「材料 + 问题」拼成提示 → 解析结构化回答 → 打印带出处的结论；先跑通一条最短"
            "路径再扩展；模型回答由固定示例文本代替，不联网、不需要密钥；最后对照验收标准自查"
        ),
        "content_version": 1,
        "estimated_minutes": 40,
        "order_index": 16,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能在离线环境里把已有零件串成一条跑得通的主路径：读本地材料、用关键词打分挑出"
                "最相关的一段、把材料与问题拼成提示、把固定示例回答解析成字段、打印一条带出处的"
                "结论；能说清为什么先跑通最短路径再扩展；并且能拿验收标准逐条自查这条路径是不是"
                "真的跑通了。"
            ),
            "explanation": [
                (
                    "「拼」是独立的一课，因为零件之间靠的是数据形状，而不是各自的正确性。单独看，"
                    "读材料、打分、拼提示、解析、打印每一步都对；接起来才发现读材料返回的是"
                    "「编号 -> 原文」的字典，打分函数却以为收到的是一个字符串，或者解析出来的字段名"
                    "与打印时写的键差一个空格。初学者真正卡住的地方几乎都不是某一步算错了，而是"
                    "接缝处的数据格式对不上——这类问题只有把整条路径跑一遍才会浮出来，读代码看不"
                    "出来。"
                ),
                (
                    "为什么用关键词打分挑材料，而不是「把全部材料丢过去让模型自己找」？因为挑选"
                    "一旦发生在模型内部，你就失去了三样东西：可解释（为什么是这一段，说不清）、"
                    "可测试（同一个问题两次挑中不同段落，没法断言）、可复现（离线、无密钥就跑不起"
                    "来）。打分写成一行 sum + sorted，挑哪一段就完全由代码决定，于是你可以对同一个"
                    "问题断言「必须挑中 M2」。这就是检索增强最简形态：先用最笨的办法把「挑」做出"
                    "来，再谈用向量或模型去挑。"
                ),
                (
                    "提示要拼成一个能打印出来的字符串。提示是程序写给模型的唯一输入，看不见它就"
                    "调不动它：回答不对时，你无法判断是材料没挑对、提示没拼全，还是模型没按格式回"
                    "答。把拼提示写成一个函数并打印出来，等于给这条链路开了一个观察孔——三行字，"
                    "材料、问题、格式要求各一行，缺哪一行一眼看得出。拼提示是代码，不是咒语，因此"
                    "它值得被写成一个有名字、能单独调用的函数。"
                ),
                (
                    "回答要有固定格式，因为解析需要契约。散文化的回答读起来舒服，但你的程序只能"
                    "靠猜去取「结论是哪一句」「出处在哪里」；固定成 ANSWER / SOURCE 两行之后，解析"
                    "变成一个 for 循环加一次 split，字段名对得上就有值，对不上就是没有。格式要写在"
                    "提示里（「输出 ANSWER 与 SOURCE 两行」），因为模型只会照着你说过的格式输出；"
                    "解析不出来时必须显式说出「解析失败」，而不是悄悄返回一个空字符串——静默降级"
                    "会让错误在几十行之后才以另一种样子出现。"
                ),
                (
                    "每条结论都要带出处，而且出处必须指到具体编号。源文本里写着 [M2]，读者能在几"
                    "秒内翻回那段原文核对；出处写成「根据相关材料」，读起来像有依据，实际指不到任"
                    "何一段字，核对只能靠通读全文。所以打印那一步不是装饰：把编号一起打出来，"
                    "「指不回去」这件事在屏幕上立刻可见——这也是自查一条结论是否可信最便宜的手段。"
                ),
                (
                    "为什么模型那一段用固定示例文本代替？因为整条链路里只有它是不可控的。把不可控"
                    "的那一段固定住，剩下的四段就是完全属于你的代码：材料、打分、拼提示、解析、打印"
                    "每一步都能单独断言，整条路径也就能在离线、无密钥的环境里反复跑通。等接真模型"
                    "时，只改 ask_model 这一个函数，其它行一行都不用动——这就是「先跑通一条最短路径，"
                    "再扩展」的实际含义：先让整条管线通水，再换掉其中一段的水源。"
                ),
            ],
            "example": {
                "title": "一条主路径：材料 -> 打分挑段 -> 拼提示 -> 解析回答 -> 带出处的结论",
                "code": BUILD_EXAMPLE_CODE,
                "output": BUILD_EXAMPLE_OUTPUT,
                "notes": [
                    "score 只数关键词命中几个：可解释、可断言，而且完全不依赖模型。",
                    "pick 用 sorted 按分数取第一名：挑哪一段由代码决定，不由模型决定。",
                    "build_prompt 返回一个能打印的字符串——提示看得见，链路才调得动。",
                    "ask_model 是唯一被替换掉的一段：固定示例文本，不联网、不需要密钥。",
                    "最后一行把编号与原文一起打出来：出处指不回具体编号，就等于没有出处。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "一上来就把整条链路接上真模型，再回头调每一段",
                    "why": (
                        "不可控的一段在上面，出了错你分不清是材料没挑对、提示没拼全，还是模型没"
                        "按格式回答，只能整体重试。"
                    ),
                    "fix": "先把模型那一段换成固定示例文本，让整条路径跑通，再换回真模型。",
                },
                {
                    "mistake": "把挑材料交给模型，让它在提示里自己找",
                    "why": "挑选过程看不见、不可复现，也没法对「必须挑中哪一段」写断言。",
                    "fix": "打分与挑选写成代码（sum + sorted），挑中的编号打印出来；模型只负责措辞。",
                },
                {
                    "mistake": "不约定输出格式，直接拿整段回答当结论",
                    "why": (
                        "没有契约就只能靠猜去取字段，取错了还不知道；解析失败时往往静默变成一个"
                        "空值。"
                    ),
                    "fix": "提示里写死两行格式，解析后取不到字段就显式打印「解析失败」。",
                },
                {
                    "mistake": "结论里不带出处，或把出处写成「根据相关材料」",
                    "why": "指不回具体编号的出处等于没有出处，读者只能通读全文去猜依据在哪。",
                    "fix": "每条结论挂一个能在材料里查到的编号，打印时把编号与原文一起打出来。",
                },
            ],
            "self_check": [
                {
                    "question": "这条主路径的五个零件分别是什么？",
                    "answer": (
                        "读本地材料、用关键词打分挑出最相关的一段、把材料与问题拼成提示、把回答"
                        "解析成字段、打印带出处的结论。"
                    ),
                },
                {
                    "question": "为什么挑材料要写成能单独测试的函数？",
                    "answer": (
                        "挑选一旦交给模型就不可解释、不可复现；写成 sum + sorted 之后，"
                        "「同一个问题必须挑中 M2」才能被断言。"
                    ),
                },
                {
                    "question": "回答为什么必须有固定格式？",
                    "answer": (
                        "解析需要契约：格式写在提示里，解析才能变成 split 加取值；解析不出来要"
                        "显式说「解析失败」，不能静默返回空值。"
                    ),
                },
                {
                    "question": "换成真模型时，代码里要改哪一处？",
                    "answer": (
                        "只改 ask_model 这一个函数：它是整条链路里唯一不可控的一段，其余四段都是"
                        "你自己的代码。"
                    ),
                },
            ],
        },
    },
)

EXERCISES_V7: tuple[dict[str, object], ...] = (
    # --- 课程 16：跟着做：把零件拼成一个小问答 --------------------------------
    {
        "lesson_code": "route_a.project.build",
        "code": "route_a.project.build.ex1",
        "title": "挑出最相关的一段，拼成一条提示",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 20,
        "content_version": 1,
        "prompt": (
            "目标：把「挑材料」与「拼提示」写成两个能单独测的函数，最后打印一条能看的提示。\n"
            "要做的事：\n"
            "1) score(text, keywords)：返回这段材料命中了几个关键词；\n"
            "2) pick(materials, keywords)：用 sorted 按分数从高到低排，返回分数最高那一段的"
            "编号；\n"
            "3) build_prompt(question, material_id, materials)：返回三行提示——材料：<编号> "
            "<原文>，问题：<问题>，要求：只依据材料回答，三行之间用换行符连起来；\n"
            "4) 用 for 逐条打印每份材料的编号与分数；\n"
            "5) 打印挑中的材料编号，再打印拼好的提示；\n"
            "6) 期望输出八行：\n"
            "M1 分数：0\n"
            "M2 分数：2\n"
            "M3 分数：1\n"
            "挑中的材料：M2\n"
            "=== 拼好的提示 ===\n"
            "材料：M2 检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "问题：检索增强的步骤是什么\n"
            "要求：只依据材料回答\n"
            "注意：挑哪一段由分数决定，不许在代码里写死 M2——把 KEYWORDS 换成只含「引用」"
            "一个关键词的列表，挑中的必须变成 M3。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 20 分钟，难度 2。"
        ),
        "starter_code": BUILD_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "前三行 M1 分数：0 / M2 分数：2 / M3 分数：1：打分只是数命中的关键词个数",
            },
            {
                "name": "自检 2",
                "expect": "第四行 挑中的材料：M2：分数最高的那一段被挑选函数选中",
            },
            {
                "name": "自检 3",
                "expect": (
                    "第五到七行是拼好的提示：材料那行带编号与原文，问题那行带原问题，最后一行"
                    "是格式要求"
                ),
            },
            {
                "name": "自检 4",
                "expect": "把 KEYWORDS 换成只含「引用」的列表再跑，第四行必须变成 挑中的材料：M3",
            },
        ],
        "required_patterns": [
            r"def\s+score\s*\(",
            r"def\s+pick\s*\(",
            r"def\s+build_prompt\s*\(",
            r"return\s+",
            r"sorted\s*\(",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 score 给一段材料打分",
            "定义函数 pick 挑出分数最高的一段",
            "定义函数 build_prompt 拼出提示",
            "用 return 把结论交回调用方",
            "用 sorted 按分数从高到低排序",
            "用 for 逐条查看每份材料的分数",
            "用 print 打印分数、挑中的材料与提示",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "M1 分数：0\n"
            "M2 分数：2\n"
            "M3 分数：1\n"
            "挑中的材料：M2\n"
            "=== 拼好的提示 ===\n"
            "材料：M2 检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "问题：检索增强的步骤是什么\n"
            "要求：只依据材料回答"
        ),
    },
    {
        "lesson_code": "route_a.project.build",
        "code": "route_a.project.build.ex2",
        "title": "解析结构化回答，打印带出处的结论",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 20,
        "content_version": 1,
        "prompt": (
            "目标：把固定示例回答解析成字段，只在出处能指回材料时打印编号，指不回去就直说"
            "「无」。\n"
            "要做的事：\n"
            "1) parse_reply(reply)：用 split 逐行按「字段: 值」切开，返回一个字典，键与值都"
            "去掉两端空白；\n"
            "2) source_of(fields, materials)：用 get 取 SOURCE；它在 materials 里就返回该"
            "编号，否则返回「无」；\n"
            "3) 用 for 逐份处理 REPLIES 里的两份回答，每份打印两行：第 N 份 结论：… 与 "
            "第 N 份 出处：…；\n"
            "4) 出处是编号时打印「编号 原文」，是「无」时只打印「无」；\n"
            "5) 期望输出四行：\n"
            "第 1 份 结论：先取回原文片段，再基于片段回答\n"
            "第 1 份 出处：M2 检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "第 2 份 结论：先取回原文片段，再基于片段回答\n"
            "第 2 份 出处：无\n"
            "注意：第二份回答缺了 SOURCE 那一行，解析出来就没有出处——这时必须打印「无」，"
            "不许猜一个编号补上。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 20 分钟，难度 3。"
        ),
        "starter_code": BUILD_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 第 1 份 结论：先取回原文片段，再基于片段回答：ANSWER 那一行被解析出来",
            },
            {
                "name": "自检 2",
                "expect": "第二行 第 1 份 出处：M2 加原文：出处编号能在材料里查到，就把编号与原文一起打印",
            },
            {
                "name": "自检 3",
                "expect": "第四行 第 2 份 出处：无：缺 SOURCE 的那份回答不许猜编号，只能直说没有",
            },
            {
                "name": "自检 4",
                "expect": "把第二份回答的 SOURCE 改成 M9（材料里没有），第四行仍然必须是 出处：无",
            },
        ],
        "required_patterns": [
            r"def\s+parse_reply\s*\(",
            r"def\s+source_of\s*\(",
            r"return\s+",
            r"\.split\s*\(",
            r"\.get\s*\(",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 parse_reply 解析结构化回答",
            "定义函数 source_of 核对出处编号",
            "用 return 把结论交回调用方",
            "用 split 把每一行切成字段与值",
            "用 get 取字段并给出缺省值",
            "用 for 逐份处理回答清单",
            "用 print 打印结论与出处",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "第 1 份 结论：先取回原文片段，再基于片段回答\n"
            "第 1 份 出处：M2 检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "第 2 份 结论：先取回原文片段，再基于片段回答\n"
            "第 2 份 出处：无"
        ),
    },
)


def upgrade() -> None:
    """Seed the Sprint 14 hands-on lesson and its two exercises (idempotent)."""
    connection = op.get_bind()
    connection.execute(
        SEED_LESSON,
        [
            {
                "code": lesson["code"],
                "skill_code": lesson["skill_code"],
                "stage": lesson["stage"],
                "title": lesson["title"],
                "summary": lesson["summary"],
                # JSONB 绑定类型负责序列化；传 JSON 字符串会存成 JSON 字符串而不是对象。
                "content": lesson["content"],
                "content_version": lesson["content_version"],
                "estimated_minutes": lesson["estimated_minutes"],
                "order_index": lesson["order_index"],
                "difficulty": lesson["difficulty"],
            }
            for lesson in LESSONS_V7
        ],
    )
    connection.execute(
        SEED_EXERCISE,
        [
            {
                "lesson_code": exercise["lesson_code"],
                "code": exercise["code"],
                "title": exercise["title"],
                "prompt": exercise["prompt"],
                "starter_code": exercise["starter_code"],
                "visible_tests": exercise["visible_tests"],
                "required_patterns": exercise["required_patterns"],
                "forbidden_patterns": exercise["forbidden_patterns"],
                # 条数与顺序与 required_patterns 严格一致：第 N 条标签说的就是第 N 条规则。
                "requirement_labels": exercise["requirement_labels"],
                "expected_output": exercise["expected_output"],
                "estimated_minutes": exercise["estimated_minutes"],
                "difficulty": exercise["difficulty"],
                "order_index": exercise["order_index"],
                "content_version": exercise["content_version"],
            }
            for exercise in EXERCISES_V7
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0019_sprint14_project_build 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
