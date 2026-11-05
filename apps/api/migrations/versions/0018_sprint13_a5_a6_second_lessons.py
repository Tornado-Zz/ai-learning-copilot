"""Sprint 13 内容：给 a5「RAG 与 Agent 基础」与 a6「简单 AI 项目」各补一节第二课，以及每课两道练习

Revision ID: 0018_sprint13_a5_a6_second_lessons
Revises: 0017_sprint12_ai_core_content
Create Date: 2026-11-06 00:00:00+00:00

六域覆盖现状：0017 之后 a5（RAG 与 Agent 基础）与 a6（简单 AI 项目）仍各只有 1 节，
其余四域都到 2 节以上——六域里最后两个「只有一课」的域。本迁移补上
route_a.rag.grounding（30 分钟，让回答只说材料里有的事）与 route_a.project.scope
（30 分钟，把一个小项目做完）两节课，以及每课两道练习（共 4 道），六域齐到 2 节。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 13 节课、26 道练习、172 条判题规则与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习都只用「本地字典里的材料」「本地字符串」当教材，
学习与判题都不需要联网、不需要密钥；4 道练习的 forbidden_patterns 都把「导入网络库」
与「真实地址字面量」写成正则禁止项，静态判题会直接拒掉联网写法。

order_index 取 14 / 15：lessons.order_index 上已有 1-13（0003 的 5 节 + 0011/0012 的
4 节 + 0013 的 a2 两节 + 0017 的 a3/a4 两节），本迁移只发 INSERT、不改写既有行，因此新
课只能接在后面；stage 仍是 a5 / a6 的 5 / 6，列表接口按 (stage, order_index) 排序时它们
紧跟在同域的既有课之后（a5: rag.retrieval -> rag.grounding，a6: agent.tool -> project.scope）。

requirement_labels 与 required_patterns **逐条一一对应、顺序相同、条数相等**（0014 建立
的契约）：第 N 条标签就是第 N 条规则，判题失败时学习者看到的是那句中文要求。本迁移的
4 道题是按这个口径新写的，不是事后补标签；题面点到「打印」「返回」「for」「join」的地方，
各有一条规则与一条标签与之对应（0015 / 0016 的口径）。

注意：示例代码里没有 \n 字面量（用 f 字符串与 join 拼行），因此这里的三引号字符串不需要
额外转义——0017 因为普通三引号吃掉了 \n 造出过 SyntaxError，本文件从写法上避开它。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0018_sprint13_a5_a6_second_lessons"
down_revision: str | None = "0017_sprint12_ai_core_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库生成
# （lessons / exercises 用 identity，真实 id 早已过了 1109 / 26），硬编码会在另一个库上
# 指向错误的行。这条口径与 0003 / 0004 / 0011 / 0012 / 0013 / 0017 完全一致。
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
# 课程 14：让回答只说材料里有的事（a5）
# ---------------------------------------------------------------------------

GROUNDING_EXAMPLE_CODE = r"""import re

# 三份离线材料：编号 -> 原文。教学用的「知识库」就是这三行字，不联网。
MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}

QUESTIONS = [
    ("检索增强的步骤是什么", ["检索", "片段"]),
    ("今天天气怎么样", ["天气"]),
]


def retrieve(keywords, materials):
    # 先查：材料原文里命中了几个关键词，命中越多越靠前
    hits = []
    for mid, text in materials.items():
        score = sum(1 for word in keywords if word in text)
        if score:
            hits.append((score, mid))
    hits.sort(reverse=True)
    return [mid for _score, mid in hits]


def answer(question, keywords):
    found = retrieve(keywords, MATERIALS)
    if not found:
        # 材料里没有就直说没有：不猜、不补、不换个说法蒙一个
        return question, "材料里没有提到，无法回答"
    best = found[0]
    return question, f"根据 [{best}]：{MATERIALS[best]}"


results = [answer(question, keywords) for question, keywords in QUESTIONS]
for question, text in results:
    print(f"{question} -> {text}")


def cite_ids(text):
    # 引用写成 [M1] 这样的编号，正则把它捞出来才能逐条核对
    return re.findall(r"\[(M\d+)\]", text)


cites = [mid for _question, text in results for mid in cite_ids(text)]
print(f"引用核对：{cites} 全部指回材料 -> {all(mid in MATERIALS for mid in cites)}")
"""

GROUNDING_EXAMPLE_OUTPUT = (
    "检索增强的步骤是什么 -> 根据 [M2]：检索增强要先取回原文片段，再让模型基于片段回答。\n"
    "今天天气怎么样 -> 材料里没有提到，无法回答\n"
    "引用核对：['M2'] 全部指回材料 -> True"
)

# ---------------------------------------------------------------------------
# 课程 15：把一个小项目做完（a6）
# ---------------------------------------------------------------------------

SCOPE_EXAMPLE_CODE = """# 先写验收标准，再写代码：每条一行，编号 + 一句能对照的话
ACCEPTANCE = {
    "A1": "能读入一条练习提交",
    "A2": "能判出通过与不通过",
    "A3": "能把结论写进一条记录",
}
# 每条的「证据」：真跑过一次才填 True；没填 True 的就是还没对上
EVIDENCE = {"A1": True, "A2": True, "A3": False}


def judge(submission):
    # 最小可用版本只跑通一条主路径：代码里有 return 就算通过
    return "return" in submission


def iterate(step, did, checked, next_step):
    # 迭代记录就三格：做了什么 / 验证了什么 / 下一步
    return f"{step} 做了什么：{did}；验证了什么：{checked}；下一步：{next_step}"


submissions = ["def add(a, b): return a + b", "print(1)"]
verdicts = [judge(text) for text in submissions]
print(f"主路径判定：{verdicts[0]} 与 {verdicts[1]}")
missing = [code for code in ACCEPTANCE if not EVIDENCE[code]]
print(f"验收 {len(ACCEPTANCE)} 条，还没对上的：{missing}")
print(iterate("第 1 轮", "跑通一条主路径", "两条提交都判出结论", "补 A3 的记录写入"))
print(f"做完了吗：{not missing}")
"""

SCOPE_EXAMPLE_OUTPUT = (
    "主路径判定：True 与 False\n"
    "验收 3 条，还没对上的：['A3']\n"
    "第 1 轮 做了什么：跑通一条主路径；验证了什么：两条提交都判出结论；下一步：补 A3 的记录写入\n"
    "做完了吗：False"
)

# ---------------------------------------------------------------------------
# 4 道练习的起始代码（只给骨架与说明，判题时注释与 docstring 会被剥离）
# ---------------------------------------------------------------------------

GROUNDING_EX1_STARTER = """# 三份离线材料：编号 -> 原文（教学材料，不联网）
MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}

QUESTIONS = [
    ("检索增强的步骤是什么", ["检索", "片段"]),
    ("今天天气怎么样", ["天气"]),
]


def retrieve(keywords, materials):
    # 1) 返回材料里命中任意一个关键词的那些编号，按材料里的顺序排成列表
    pass


def answer(question, keywords):
    # 2) 查到材料：返回「问题, 根据 [编号]：原文」；查不到：返回「问题, 材料里没有提到，无法回答」
    pass


# 3) 用 for 逐条处理 QUESTIONS 里的两个问题，按「问题 -> 回答」的格式打印两行
# 4) 再把回答里的 [M1] 这类引用编号捞出来，打印一行「引用核对：…」的结果
"""

GROUNDING_EX2_STARTER = """# 三份离线材料：编号 -> 原文（教学材料，不联网）
MATERIALS = {
    "M1": "静态规则判题只做正则匹配，无法判断语义对错。",
    "M2": "检索增强要先取回原文片段，再让模型基于片段回答。",
    "M3": "每条引用都要能指回具体的一条材料编号。",
}

# 两份待核对的回答：第二份里的 [M9] 在材料里根本不存在
answers = [
    "检索增强要先取回原文片段 [M2]，每条引用都要能指回材料 [M3]。",
    "静态规则判题只做正则匹配 [M9]，这条编号材料里根本没有。",
]


def cite(material_ids):
    # 1) 用「；」把编号连起来，返回「（引用：M1；M3）」；编号列表为空时返回「（没有引用）」
    pass


def bad_citations(text, materials):
    # 2) 用 re.findall 把 text 里的 [M1] 这类编号全部取出来，返回其中不在 materials 里的那些
    pass


# 3) 用 for 逐条核对 answers 里的两份回答，按「回答 -> 编造的引用：[…]」打印两行
# 4) 最后打印 cite(["M1", "M3"]) 的结果
"""

SCOPE_EX1_STARTER = """# 先写验收标准：编号 -> 一句能对照的话
ACCEPTANCE = {
    "A1": "能读入一条练习提交",
    "A2": "能判出通过与不通过",
    "A3": "能把结论写进一条记录",
}
# 证据：真跑过一次才填 True
EVIDENCE = {"A1": True, "A2": True, "A3": False}


def covered(evidence):
    # 1) 返回证据为 True 的验收编号列表（顺序按 ACCEPTANCE）
    pass


def unfinished(evidence):
    # 2) 返回证据不是 True 的验收编号列表
    pass


def is_done(evidence):
    # 3) 用 all 判断每条验收是否都对上了：全部对上返回 True，否则返回 False
    pass


# 4) 用 for 逐条打印验收标准的编号、正文与状态（已对上 / 还没对上）
# 5) 再打印「还没对上：…」与「做完了吗：…」两行
"""

SCOPE_EX2_STARTER = """# 计划里的功能清单，最小可用版本只保留前两件事
MVP = ["读入提交", "判出结论"]
PLANNED = ["读入提交", "判出结论", "导出报告", "历史统计"]
ROUNDS = [
    (1, "跑通一条主路径", "两条提交都判出结论", "补引用核对"),
    (2, "补上引用核对", "编造的编号被抓住", "写进验收记录"),
]


def log_line(index, did, checked, next_step):
    # 1) 用 join 把三格用「；」连成一行，最前面加「第 N 轮 」，返回这一行
    pass


def creep(items, mvp):
    # 2) 返回 items 里不在 mvp 中的那些条目——不在最小可用版本里的计划就是范围蔓延
    pass


# 3) 用 for 逐轮打印 ROUNDS 里的每条迭代记录
# 4) 最后打印「范围蔓延：…」一行
"""

LESSONS_V6: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.rag.grounding",
        "skill_code": "route_a.a5",
        "stage": 5,
        "title": "让回答只说材料里有的事",
        "summary": "先查再答：把检索到的原文拼进提示，回答只能落在材料上；材料里没有就直说没有；引用要能指回具体片段；「听起来很对」比明显错误更危险，因为模型不会主动告诉你它在编",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 14,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能说清「先查再答」到底改变了什么：原文先取回、拼进提示、回答只能落在材料"
                "上；能在提示里写死「材料里没有就直说没有」这条出口；知道一条合格的引用必须"
                "指回具体片段；能解释为什么「听起来很对」比明显错误更危险，以及为什么不能"
                "指望模型自己告诉你它在编。"
            ),
            "explanation": [
                (
                    "不检索时，模型只能靠参数里记住的东西回答：它答得出，是因为「这段话在训练"
                    "语料里出现过类似形状」，而不是因为它此刻手里有一份材料。把检索到的原文拼"
                    "进提示，改变的正是这一点——回答的依据从「它记得的整个语料」缩到「你给的"
                    "这几段字」。范围一缩小，回答就可核对了：每一句都能拿回原文去对。"
                ),
                (
                    "「材料里没有就直说没有」是提示里必须写死的一句，因为它是唯一能让「不知道」"
                    "浮出水面的出口。没有这个出口，模型只有一个方向可走——补一个说得通的答案。"
                    "它不是在骗你：在你给的上下文里，「接着往下写」本来就是它唯一被训练过的动作。"
                    "出口要写进提示，也要写成判据：回答里没有依据时，期望的答案就是那句「材料里"
                    "没有提到」。"
                ),
                (
                    "引用不是装饰，是验收手段。回答里每条结论后面挂一个编号（M1、M2 这样），你"
                    "就能在几秒内核对它是不是真的出自那段原文——编号在不在材料里、原文是不是逐字"
                    "对得上。反过来，「根据相关资料」「如上所述」这类引用等于没有引用：它读起来"
                    "像有出处，却指不到任何一段字，核对只能靠人肉通读全文。引用写不出具体编号，"
                    "通常说明这条结论本来就没有出处。"
                ),
                (
                    "为什么「听起来很对」比明显错误更危险？明显错误（语法错、数字离谱、逻辑自相"
                    "矛盾）会触发你的审查；流畅、术语正确、结构完整的回答不触发——它长得像你已经"
                    "验证过的东西，于是你把「读起来对」当成了「核对过」。错误的真正成本不在于错，"
                    "而在于错得让人不去查。这也解释了为什么带编号的引用比「写得更严谨」的要求更"
                    "管用：它把审查从「读一遍判断像不像」变成「数一数编号在不在材料里」。"
                ),
                (
                    "模型不会主动告诉你它在编。它按「最可能的下一段文字」生成，如实陈述与编造在"
                    "它那里是同一种动作，没有内部信号区分这两者——所以「你觉得这段有依据吗」这类"
                    "自问自答拿不到可靠答案。能用的只有外部核对：引用的编号在不在材料里、数字在"
                    "不在原文里、这句话能不能逐句指回具体片段。核对必须发生在你的程序或你的眼睛"
                    "里，不在模型的自我报告里。"
                ),
                (
                    "这一整套在离线环境里完全练得出来：把材料写成字典、把「查」写成一个函数、把"
                    "「答」写成另一个函数，两个函数都只依赖参数、都返回结果。于是你可以对同一批"
                    "问题逐个断言：有材料时回答带编号且原文对得上，没材料时回答就是「材料里没有"
                    "提到」。真接上模型时，你只是把这两个函数的输出拼进提示，判断逻辑一行都不"
                    "用改——先把结构立起来，再谈模型好不好用。"
                ),
            ],
            "example": {
                "title": "先查再答：有材料才回答，没材料就说没有",
                "code": GROUNDING_EXAMPLE_CODE,
                "output": GROUNDING_EXAMPLE_OUTPUT,
                "notes": [
                    "retrieve 只做一件事：按关键词去材料原文里找，返回命中的编号。",
                    "answer 在找不到材料时返回「材料里没有提到，无法回答」，这是唯一的出口。",
                    "回答里带 [M2] 这样的编号，是为了让每条结论都能指回一段具体原文。",
                    "cite_ids 把编号捞出来逐个核对：引用写不出具体编号，就等于没有出处。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把整段检索结果一股脑塞进提示，让模型自己挑",
                    "why": (
                        "挑选发生在模型的内部，你看不见；回答到底用了哪一段、能不能指回原文，"
                        "事后无从核对。"
                    ),
                    "fix": "只放少量最相关的片段，并要求回答里带编号；挑哪一段由你的代码决定。",
                },
                {
                    "mistake": "只写「请基于以下材料回答」，没写「材料里没有就说没有」",
                    "why": "缺了唯一的出口，模型只能补一个说得通的答案，而这正是编造最常见的起点。",
                    "fix": "把兜底句写死，并把它当成判据：没有依据时，期望的答案就是那句「没有提到」。",
                },
                {
                    "mistake": "引用写成「根据相关资料」「如上所述」",
                    "why": "看起来有出处，实际指不到任何一段字，核对只能靠人肉通读全文。",
                    "fix": "每条结论挂一个编号，编号对应一条可查的原文；写不出编号就说明没有出处。",
                },
                {
                    "mistake": "用回答的流畅程度当正确性证据",
                    "why": "流畅正是生成模型最擅长的事，它和「有依据」是两件独立的事。",
                    "fix": "只认可核对的信号：编号在材料里、原文逐字对得上、数字能在原文找到。",
                },
            ],
            "self_check": [
                {
                    "question": "先查再答，和直接把问题丢给模型，差别在哪？",
                    "answer": (
                        "依据从「模型记得的整个语料」缩到「你给的几段原文」：回答的范围变小了，"
                        "每一句也都能拿回原文去对。"
                    ),
                },
                {
                    "question": "为什么提示里一定要写「材料里没有就说没有」？",
                    "answer": (
                        "它是唯一能让「不知道」浮出水面的出口；没有它，模型只能补一个说得通的"
                        "答案，而这就是编造。"
                    ),
                },
                {
                    "question": "一条合格的引用长什么样？",
                    "answer": (
                        "指回具体片段：回答里带 [M2] 这样的编号，编号能在材料里找到，原文逐字"
                        "对得上。"
                    ),
                },
                {
                    "question": "「听起来很对」为什么比明显错误更危险？",
                    "answer": (
                        "明显错误会触发审查，流畅完整的内容不会——它让人停在「读起来对」这一层，"
                        "于是错的东西一路通过。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.project.scope",
        "skill_code": "route_a.a6",
        "stage": 6,
        "title": "把一个小项目做完",
        "summary": "先写验收标准再写代码；最小可用版本先跑通一条主路径；范围蔓延的典型征兆；迭代记录只写三格（做了什么 / 验证了什么 / 下一步）；每条验收都有证据才叫「做完了」",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 15,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "能在动手前写出可对照的验收标准；知道最小可用版本的第一件事是跑通一条主路径；"
                "能认出范围蔓延的四个征兆；能把每一轮迭代写成三格记录；并且用「每条验收都有"
                "证据」代替「代码差不多写完了」来判断什么叫做完。"
            ),
            "explanation": [
                (
                    "验收标准是「怎样算通过」的句子，必须写在动手之前。它的作用不是给老板看，"
                    "而是把「感觉差不多了」换成一张能逐条对照的清单：哪些是这一轮必须成立的、"
                    "哪些是可以下一轮的。写不出来的那一条，通常说明你还没想清楚要做什么——这是"
                    "整个项目里最早、也最便宜的发现时机，晚一周发现就要重写一周的代码。"
                ),
                (
                    "最小可用版本的第一件事是跑通一条主路径：一个真实输入从进到出，哪怕实现很笨。"
                    "在它跑通之前，任何新功能都只是把「不知道行不行」的面积扩大——三块半成品放在"
                    "一起，出了问题时你连是输入、判断还是输出坏了都分不清。先把一条路径跑通，"
                    "再谈第二条：这时候每加一块，你都知道刚才那一步是好用的。"
                ),
                (
                    "范围蔓延有很典型的征兆：清单外的功能开始出现在代码里；「顺便再加一个……」"
                    "开头的句子变多；验收标准一直没被勾上，新功能却一个接一个；每加一个小功能都"
                    "要改三处已有代码。出现任意一条，就该停下来把范围写回清单，而不是继续加——"
                    "蔓延不是「做得更多」，是把一件快做完的事重新变成一件做不完的事。"
                ),
                (
                    "迭代记录只写三格：做了什么（一句话，能对照代码或演示）、验证了什么（跑过"
                    "什么、结论是什么）、下一步（下一轮第一件事）。三格的价值在第二格：写不出"
                    "「验证了什么」，说明这一轮只是写了代码，没有跑过、也没有结论。「今天改了"
                    "半天」不是记录，因为它既不能证明前进了，也不能告诉下一个人从哪继续。"
                ),
                (
                    "什么叫「做完了」？不是代码写完了，是每条验收标准都有证据：跑过一次，结果"
                    "与期望一致。没有证据的验收项就是没做完，哪怕代码看起来很完整。「基本完成」"
                    "「差不多能跑」这类说法，本质上是在承认有一条验收还没对上——把它写清楚，比"
                    "用形容词盖过去有用得多。演示时集中暴露的问题，几乎都是这类没被对照过的"
                    "验收项。"
                ),
                (
                    "这套东西离线也能练，而且练的是结构而不是记性：验收标准是一个字典（编号 ->"
                    "一句话），证据是一组布尔值，迭代记录是三格拼出来的一行字，「做完了」就是"
                    "每条都为 True。写成函数之后，一个项目有没有做完就变成一句可以打印出来的"
                    "结论，而不是一种感觉——这也是它与「写了很多代码」最本质的区别。"
                ),
            ],
            "example": {
                "title": "验收标准 + 一条主路径 + 迭代记录：三样东西一起看",
                "code": SCOPE_EXAMPLE_CODE,
                "output": SCOPE_EXAMPLE_OUTPUT,
                "notes": [
                    "ACCEPTANCE 写在 judge 之前：先定义怎样算通过，再写通过它的代码。",
                    "judge 只跑通一条主路径（有 return 就算通过）：最笨的实现也比没有路径强。",
                    "EVIDENCE 里 A3 还是 False，所以「做完了吗」是 False——没证据就不算做完。",
                    "iterate 固定三格：做了什么 / 验证了什么 / 下一步，缺第二格就说明这轮没验证。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "先写代码，验收标准等做完再补",
                    "why": ("补出来的标准是照着代码写的，它只能证明你已经做的，不能证明你该做的。"),
                    "fix": "动手前先写三条能对照的验收句子；写不出来就先别写代码。",
                },
                {
                    "mistake": "一上来就把功能铺满，主路径却一次都没跑通",
                    "why": "每块都是半成品，出问题时分不清是输入、判断还是输出坏了。",
                    "fix": "先让一条主路径从输入跑到输出，再逐条加；每加一条都回到同一条路径上验证。",
                },
                {
                    "mistake": "迭代记录只写「今天做了什么」",
                    "why": "没有验证那一格，你无法判断这一轮是前进还是原地打转。",
                    "fix": "三格都写；验证那格必须是一次真实的运行与一个明确结论。",
                },
                {
                    "mistake": "代码写完就宣布完成",
                    "why": "验收标准没有被对照过，「完成」只是自我感觉，问题会在演示时集中出现。",
                    "fix": "逐条对照验收并留下证据；没对上的就写「还没对上」，别用形容词盖过去。",
                },
            ],
            "self_check": [
                {
                    "question": "为什么验收标准要写在代码之前？",
                    "answer": (
                        "写在前面才是「怎样算通过」的目标；写在后面就只能照代码抄，变成对既有"
                        "实现的描述。"
                    ),
                },
                {
                    "question": "最小可用版本的第一件事是什么？",
                    "answer": (
                        "让一条主路径从真实输入跑到真实输出，哪怕实现很笨；跑通之后再谈第二条。"
                    ),
                },
                {
                    "question": "范围蔓延有哪些征兆？",
                    "answer": (
                        "清单外功能进代码、「顺便再加」变多、验收没勾上却一直加新东西、加一个"
                        "小功能要改三处已有代码。"
                    ),
                },
                {
                    "question": "「做完了」的判据是什么？",
                    "answer": (
                        "每条验收标准都有证据：跑过一次、结果与期望一致。没有证据的验收项就是"
                        "没做完。"
                    ),
                },
            ],
        },
    },
)

EXERCISES_V6: tuple[dict[str, object], ...] = (
    # --- 课程 14：让回答只说材料里有的事 ---------------------------------------
    {
        "lesson_code": "route_a.rag.grounding",
        "code": "route_a.rag.grounding.ex1",
        "title": "先查再答：查到才回答，查不到就说没有",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「先查再答」写成两个纯函数——先去材料里查，查到才回答，查不到就直说没有。\n"
            "要做的事：\n"
            "1) retrieve(keywords, materials)：返回材料里命中任意一个关键词的那些编号，按材料"
            "里的顺序排成列表；\n"
            "2) answer(question, keywords)：查到材料时返回「问题, 根据 [编号]：原文」两个值，"
            "查不到时返回「问题, 材料里没有提到，无法回答」；\n"
            "3) 用 for 逐条处理 QUESTIONS 里的两个问题，按「问题 -> 回答」的格式打印两行；\n"
            "4) 再把回答里的 [M1] 这类引用编号捞出来，打印一行「引用核对：['M2']」；\n"
            "5) 期望输出三行：\n"
            "检索增强的步骤是什么 -> 根据 [M2]：检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "今天天气怎么样 -> 材料里没有提到，无法回答\n"
            "引用核对：['M2']\n"
            "注意：第二个问题在材料里没有答案，所以回答必须直说没有——不许编一条看起来对的内容。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": GROUNDING_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 检索增强的步骤是什么 -> 根据 [M2]：…：回答落在材料原文上，还带着编号",
            },
            {
                "name": "自检 2",
                "expect": "第二行 今天天气怎么样 -> 材料里没有提到，无法回答：查不到就直说没有",
            },
            {
                "name": "自检 3",
                "expect": "第三行 引用核对：['M2']：回答里的引用编号能被正则捞出来逐个核对",
            },
            {
                "name": "自检 4",
                "expect": "把 QUESTIONS 里的第二个问题换成命中 M3 的关键词，第二行应变成带 [M3] 的回答",
            },
        ],
        "required_patterns": [
            r"def\s+retrieve\s*\(",
            r"def\s+answer\s*\(",
            r"return\s+",
            r"材料里没有提到",
            r"any\s*\(",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 retrieve 先去材料里查",
            "定义函数 answer 再按材料回答",
            "用 return 把结论交回调用方",
            "查不到材料就直说没有",
            "用 any 判断任意一个关键词是否命中",
            "用 for 逐条处理问题清单",
            "用 print 打印每一条问答结论",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "检索增强的步骤是什么 -> 根据 [M2]：检索增强要先取回原文片段，再让模型基于片段回答。\n"
            "今天天气怎么样 -> 材料里没有提到，无法回答\n"
            "引用核对：['M2']"
        ),
    },
    {
        "lesson_code": "route_a.rag.grounding",
        "code": "route_a.rag.grounding.ex2",
        "title": "核对引用：编造的编号必须被抓住",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：给回答配上能核对的引用，并抓住「材料里根本没有」的编造编号。\n"
            "要做的事：\n"
            "1) cite(material_ids)：用「；」把编号连起来，返回「（引用：M1；M3）」这样一段；"
            "编号列表为空时返回「（没有引用）」；\n"
            "2) bad_citations(text, materials)：用 re.findall 把 text 里的 [M1] 这类编号全部"
            "取出来，返回其中不在 materials 里的那些；\n"
            "3) 用 for 逐条核对 answers 里的两份回答，按「回答 -> 编造的引用：[…]」的格式打印"
            "两行；\n"
            '4) 最后打印 cite(["M1", "M3"]) 的结果；\n'
            "5) 期望输出三行：\n"
            "检索增强要先取回原文片段 [M2]，每条引用都要能指回材料 [M3]。 -> 编造的引用：[]\n"
            "静态规则判题只做正则匹配 [M9]，这条编号材料里根本没有。 -> 编造的引用：['M9']\n"
            "（引用：M1；M3）\n"
            "注意：第二份回答里的 [M9] 在材料里不存在，必须被挑出来——这就是「引用能指回片段」"
            "的可执行版本。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": GROUNDING_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 编造的引用：[]：两条编号都能在材料里找到，核对通过",
            },
            {
                "name": "自检 2",
                "expect": "第二行 编造的引用：['M9']：材料里没有 M9，编造的引用被抓出来",
            },
            {
                "name": "自检 3",
                "expect": "第三行 （引用：M1；M3）：多个编号用「；」连成一段，顺序与传入一致",
            },
            {
                "name": "自检 4",
                "expect": "把 cite 传空列表，结果必须是「（没有引用）」，而不是「（引用：）」",
            },
        ],
        "required_patterns": [
            r"def\s+cite\s*\(",
            r"def\s+bad_citations\s*\(",
            r"return\s+",
            r"\.join\s*\(",
            r"re\.findall",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 cite 拼出引用那一段",
            "定义函数 bad_citations 核对引用",
            "用 return 把结论交回调用方",
            "用 join 把多个编号连成一段引用",
            "用 re.findall 把引用编号全部捞出来",
            "用 for 逐份核对回答",
            "用 print 打印每份回答的核对结论",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "检索增强要先取回原文片段 [M2]，每条引用都要能指回材料 [M3]。 -> 编造的引用：[]\n"
            "静态规则判题只做正则匹配 [M9]，这条编号材料里根本没有。 -> 编造的引用：['M9']\n"
            "（引用：M1；M3）"
        ),
    },
    # --- 课程 15：把一个小项目做完 ---------------------------------------------
    {
        "lesson_code": "route_a.project.scope",
        "code": "route_a.project.scope.ex1",
        "title": "先写验收标准，再判哪些还没对上",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：先写验收标准，再用三个纯函数回答「哪些已经对上」「哪些还没对上」「做完了"
            "没有」。\n"
            "要做的事：\n"
            "1) covered(evidence)：返回证据为 True 的验收编号列表，顺序按 ACCEPTANCE；\n"
            "2) unfinished(evidence)：返回证据不是 True 的验收编号列表，顺序同上；\n"
            "3) is_done(evidence)：用 all 判断每条验收是否都对上了，全部对上返回 True，否则"
            "返回 False；\n"
            "4) 用 for 逐条打印验收标准的编号、正文与状态（已对上 / 还没对上）；\n"
            "5) 再打印「还没对上：…」与「做完了吗：…」两行；\n"
            "6) 期望输出五行：\n"
            "A1 能读入一条练习提交 -> 已对上\n"
            "A2 能判出通过与不通过 -> 已对上\n"
            "A3 能把结论写进一条记录 -> 还没对上\n"
            "还没对上：['A3']\n"
            "做完了吗：False\n"
            "注意：「做完了吗」是 False 不是 bug：A3 还没有证据，就不算做完。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": SCOPE_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "前两行以 已对上 结尾：A1 与 A2 都有 True 的证据",
            },
            {
                "name": "自检 2",
                "expect": "第三行 A3 能把结论写进一条记录 -> 还没对上：证据是 False",
            },
            {
                "name": "自检 3",
                "expect": "第四行 还没对上：['A3']：顺序与 ACCEPTANCE 一致，不是靠写死的字符串",
            },
            {
                "name": "自检 4",
                "expect": "把 EVIDENCE 里 A3 改成 True 再跑，最后一行必须变成 做完了吗：True",
            },
        ],
        "required_patterns": [
            r"def\s+covered\s*\(",
            r"def\s+unfinished\s*\(",
            r"def\s+is_done\s*\(",
            r"return\s+",
            r"all\s*\(",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 covered 列出已经对上的验收",
            "定义函数 unfinished 列出还没对上的验收",
            "定义函数 is_done 判断做完了没有",
            "用 return 把结论交回调用方",
            "用 all 判断每条验收都对上了",
            "用 for 逐条打印验收标准",
            "用 print 打印验收标准与结论",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "A1 能读入一条练习提交 -> 已对上\n"
            "A2 能判出通过与不通过 -> 已对上\n"
            "A3 能把结论写进一条记录 -> 还没对上\n"
            "还没对上：['A3']\n"
            "做完了吗：False"
        ),
    },
    {
        "lesson_code": "route_a.project.scope",
        "code": "route_a.project.scope.ex2",
        "title": "一轮迭代一行记录，并认出范围蔓延",
        "order_index": 2,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一轮迭代写成一行三格记录（做了什么 / 验证了什么 / 下一步），并认出计划里"
            "的范围蔓延。\n"
            "要做的事：\n"
            "1) log_line(index, did, checked, next_step)：用 join 把「做了什么：…」「验证了"
            "什么：…」「下一步：…」三格用「；」连成一行，最前面加上「第 N 轮 」，返回这一行；\n"
            "2) creep(items, mvp)：返回 items 里不在 mvp 中的那些条目——不在最小可用版本里的"
            "计划就是范围蔓延；\n"
            "3) 用 for 逐轮打印 ROUNDS 里的每条迭代记录；\n"
            "4) 最后打印「范围蔓延：…」一行；\n"
            "5) 期望输出三行：\n"
            "第 1 轮 做了什么：跑通一条主路径；验证了什么：两条提交都判出结论；下一步：补引用核对\n"
            "第 2 轮 做了什么：补上引用核对；验证了什么：编造的编号被抓住；下一步：写进验收记录\n"
            "范围蔓延：['导出报告', '历史统计']\n"
            "注意：第三行在告诉你「计划里有两件事不在最小可用版本内」——先停下来问它们该不该"
            "进这一轮。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": SCOPE_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 第 1 轮 做了什么：…；验证了什么：…；下一步：…：三格齐全且顺序固定",
            },
            {
                "name": "自检 2",
                "expect": "第二行 第 2 轮 做了什么：补上引用核对…：换一轮数据，三格内容跟着变",
            },
            {
                "name": "自检 3",
                "expect": "第三行 范围蔓延：['导出报告', '历史统计']：只列出不在 MVP 里的两项",
            },
            {
                "name": "自检 4",
                "expect": "把 PLANNED 里多出来的两项删掉，第三行必须是 范围蔓延：[]",
            },
        ],
        "required_patterns": [
            r"def\s+log_line\s*\(",
            r"def\s+creep\s*\(",
            r"return\s+",
            r"\.join\s*\(",
            r"for\s+\w+\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 log_line 拼出一行三格记录",
            "定义函数 creep 找出范围蔓延的条目",
            "用 return 把结论交回调用方",
            "用 join 把三格连成一行",
            "用 for 逐轮处理迭代清单",
            "用 print 打印每轮的迭代记录",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "第 1 轮 做了什么：跑通一条主路径；验证了什么：两条提交都判出结论；下一步：补引用核对\n"
            "第 2 轮 做了什么：补上引用核对；验证了什么：编造的编号被抓住；下一步：写进验收记录\n"
            "范围蔓延：['导出报告', '历史统计']"
        ),
    },
)


def upgrade() -> None:
    """Seed the two Sprint 13 lessons and their four exercises (idempotent)."""
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
            for lesson in LESSONS_V6
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
            for exercise in EXERCISES_V6
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0018_sprint13_a5_a6_second_lessons 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
