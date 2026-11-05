"""Sprint 15 内容：给 a1「Python 基础」补两节「处理数据」的日常课，以及每课两道练习

Revision ID: 0020_sprint15_py_strings_files
Revises: 0019_sprint14_project_build
Create Date: 2026-11-07 00:00:00+00:00

a1 到 0019 为止只有 5 节（variables / control_flow / list_dict / functions / debugging），
缺的恰好是「处理 AI 数据」最常用的两块：字符串与文件。模型给的东西永远是文本，
程序要「记住」东西就得落到文件——这两块不补，学习者读完 5 节仍然拼不出「读一条
模型回答、洗干净、存进文件、明天再读回来」这条主路径。

本迁移补上 route_a.py.strings（30 分钟，字符串是几乎所有 AI 数据的形状）与
route_a.py.files（30 分钟，用 with open 让程序记住东西）两节课，以及每课两道练习
（共 4 道）。两节课都接在 a1 既有五节之后，六域课程分布不变、a1 从 5 节变 7 节。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 16 节课、32 道练习、213 条判题规则与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习只用「内存里的字符串」与「练习自己创建的临时目录」
当教材，学习与判题都不需要联网、不需要密钥、不读系统文件；4 道练习的 forbidden_patterns
都把「导入网络库」与「真实地址字面量」写成正则禁止项，静态判题会直接拒掉联网写法。

order_index 取 17 / 18：lessons.order_index 上已有 1-16（0003 的 5 节 + 0011/0012 的
4 节 + 0013 的 a2 两节 + 0017 的 a3/a4 两节 + 0018 的 a5/a6 两节 + 0019 的 a6 一节），
本迁移只发 INSERT、不改写既有行，因此新课只能接在后面；stage 仍是 a1 的 1，列表接口按
(stage, order_index) 排序时它们紧跟在 debugging 之后（a1: debugging -> strings -> files）。

requirement_labels 与 required_patterns **逐条一一对应、顺序相同、条数相等**（0014 建立
的契约）：第 N 条标签就是第 N 条规则，判题失败时学习者看到的是那句中文要求。本迁移的
4 道题按这个口径新写：题面点到「打印」「返回」「定义函数」，各有一条规则与一条标签与之
对应（0015 / 0016 的口径）；题面点名的构造（strip / split / join / replace / 切片 /
with open / encoding / json.dump / json.load / json.dumps / w / a）也各有一条规则与标签。

示例代码里没有 \n 字面量（多行写入用 print(..., file=handle)，避开 0017 踩过的坑），
但两个示例与四段起始代码仍然一律写成带 r 前缀的原始字符串：原始字符串是这条口径的
护栏，不是这一次的补丁。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0020_sprint15_py_strings_files"
down_revision: str | None = "0019_sprint14_project_build"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库生成
# （lessons / exercises 用 identity，真实 id 早已过了 1109 / 32），硬编码会在另一个库上
# 指向错误的行。这条口径与 0003 / 0004 / 0011 / 0012 / 0013 / 0017 / 0018 / 0019 完全一致。
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
# 课程 17：字符串是几乎所有 AI 数据的形状（a1）
# ---------------------------------------------------------------------------

STRINGS_EXAMPLE_CODE = r"""# 一条模型返回的原始文本：前后带空白，字段之间用竖线分隔（离线字符串，不联网）
RAW = "  问题: 什么是 RAG? | 答案是: 先检索再生成  "

# 1) strip 去掉首尾空白：字符串不可变，它返回的是新串，RAW 本身一个字都没动
cleaned = RAW.strip()
print(f"strip 之后：{cleaned!r}")
print(f"RAW 还是原来的样子：{RAW!r}")

# 2) 下标从 0 开始；切片拿到的同样是新串
print(f"下标 0 取到的字符：{cleaned[0]}")
print(f"切片 [-6:] 取到的：{cleaned[-6:]}")

# 3) split 切开、join 拼回：两次操作各产生一个新对象
fields = cleaned.split("|")
print(f"切开以后有 {len(fields)} 段")

pairs = []
for field in fields:
    # 只切一次：值里再出现冒号时，剩下的部分整体留在值里
    key, value = field.strip().split(":", 1)
    pairs.append(f"{key.strip()}={value.strip()}")
print("；".join(pairs))

# 4) f 字符串与 format 的取舍：一处拼接用 f 字符串更短，模板要复用时才用 format
template = "{name} 一共 {count} 段"
print(template.format(name="字段", count=len(pairs)))
print(f"字段 一共 {len(pairs)} 段")
"""

STRINGS_EXAMPLE_OUTPUT = (
    "strip 之后：'问题: 什么是 RAG? | 答案是: 先检索再生成'\n"
    "RAW 还是原来的样子：'  问题: 什么是 RAG? | 答案是: 先检索再生成  '\n"
    "下标 0 取到的字符：问\n"
    "切片 [-6:] 取到的：先检索再生成\n"
    "切开以后有 2 段\n"
    "问题=什么是 RAG?；答案是=先检索再生成\n"
    "字段 一共 2 段\n"
    "字段 一共 2 段"
)

# ---------------------------------------------------------------------------
# 课程 18：读写文件，让程序记住东西（a1）
# ---------------------------------------------------------------------------

FILES_EXAMPLE_CODE = r"""import json
import tempfile
from pathlib import Path

# 只在自己创建的临时目录里读写：位置在当前目录下，整段结束后自动删掉；
# 不联网，也不碰仓库里的其他文件
with tempfile.TemporaryDirectory(dir=".") as workdir:
    notes = Path(workdir) / "notes.txt"
    progress = Path(workdir) / "progress.json"

    # 1) w 模式：文件不存在就新建，已存在就清空重写
    with open(notes, "w", encoding="utf-8") as handle:
        print("第一行：strip 去掉两端空白", file=handle)
        print("第二行：encoding 不能省", file=handle)

    # 2) a 模式：接着末尾写，不覆盖已有内容
    with open(notes, "a", encoding="utf-8") as handle:
        print("第三行：with 会自动关闭文件", file=handle)

    # 3) read() 一次拿到整段文本，适合小文件
    with open(notes, encoding="utf-8") as handle:
        whole = handle.read()
    print(f"read() 拿到 {len(whole.splitlines())} 行")

    # 4) 逐行遍历：大文件也不必一次全读进内存；每行末尾的换行由 strip 去掉
    with open(notes, encoding="utf-8") as handle:
        for line in handle:
            print(f"逐行读：{line.strip()}")

    # 5) readlines() 一次读成列表，适合小文件里要反复按行取的时候
    with open(notes, encoding="utf-8") as handle:
        lines = handle.readlines()
    print(f"readlines() 拿到 {len(lines)} 条")

    # 6) json.dump / json.load 直接对着文件转；只在内存里转字符串用 dumps / loads
    data = {"lesson": "files", "lines": len(lines)}
    with open(progress, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    with open(progress, encoding="utf-8") as handle:
        loaded = json.load(handle)
    print(f"存进去再读回来：{loaded}")

    # 7) 同一个文件名再用 w 打开一次：前面三行就没了，这就是 w 与 a 的差别
    with open(notes, "w", encoding="utf-8") as handle:
        print("重新写过", file=handle)
    with open(notes, encoding="utf-8") as handle:
        print(f"重写以后只剩：{handle.read().strip()}")
"""

FILES_EXAMPLE_OUTPUT = (
    "read() 拿到 3 行\n"
    "逐行读：第一行：strip 去掉两端空白\n"
    "逐行读：第二行：encoding 不能省\n"
    "逐行读：第三行：with 会自动关闭文件\n"
    "readlines() 拿到 3 条\n"
    "存进去再读回来：{'lesson': 'files', 'lines': 3}\n"
    "重写以后只剩：重新写过"
)

# ---------------------------------------------------------------------------
# 4 道练习的起始代码（只给骨架与说明，判题时注释与 docstring 会被剥离）
# ---------------------------------------------------------------------------

STRINGS_EX1_STARTER = r"""# 一条模型返回的原始文本：前后带空白，字段之间用竖线分隔（离线字符串，不联网）
RAW = "  问题: 什么是 RAG? | 答案是: 先检索再生成  "


def clean(text):
    # 1) 去掉首尾空白，返回去掉之后的新字符串
    pass


def fields(text):
    # 2) 按竖线切成若干段，每段再去掉两端空白，返回这些段组成的列表
    pass


def pairs(text):
    # 3) 每段按冒号只切一次，键和值都去掉空白，返回键=值形式的新字符串列表
    pass


# 4) 用 for 逐段打印「第 N 段：键=值」；再用 join 把各段拼成一行打印「拼回去：…」
# 5) 最后打印「clean 返回的是新串：True」——用 is not 比较，证明它是新对象
# 6) 期望输出四行：
# 第 1 段：问题=什么是 RAG?
# 第 2 段：答案是=先检索再生成
# 拼回去：问题=什么是 RAG?；答案是=先检索再生成
# clean 返回的是新串：True
"""

STRINGS_EX2_STARTER = r"""# 一条带标记的模型输出：开头有三个井号，结尾有重复的句号（离线字符串，不联网）
RAW = "### 答案：检索增强 先取回原文片段，再让模型基于片段回答。。"


def strip_marks(text):
    # 1) 去掉开头的三个井号加一个空格，返回去掉之后的新字符串
    pass


def drop_duplicate(text):
    # 2) 把结尾重复的两个句号换成一个句号，返回换好之后的新字符串
    pass


def headline(text, limit):
    # 3) 用切片只取开头 limit 个字符，返回这一段
    pass


# 4) 依次打印「第 1 步：…」「第 2 步：…」「前 10 个字符：…」三行
# 5) 最后打印「原串还是原来的样子：True」——每次操作都产生新串，RAW 一个字都没变
"""

FILES_EX1_STARTER = r"""import tempfile
from pathlib import Path

# 练习只在自己创建的临时目录里读写（整段结束后自动删掉），不联网、不碰系统文件
with tempfile.TemporaryDirectory(dir=".") as workdir:
    notes = Path(workdir) / "notes.txt"

    def write_lines(path, lines):
        # 1) 用 with open(path, "w", encoding="utf-8") 把 lines 逐行写进去
        pass

    def append_line(path, line):
        # 2) 用 with open(path, "a", encoding="utf-8") 在末尾追加一行
        pass

    def read_lines(path):
        # 3) 用 with open(path, encoding="utf-8") 逐行读，去掉每行结尾空白，返回列表
        pass

    write_lines(notes, ["第一行", "第二行"])
    append_line(notes, "第三行")

    # 4) 用 for 逐行打印「第 N 行：…」，前面先打印一行「读回 3 行」
    # 5) 期望输出四行：
    # 读回 3 行
    # 第 1 行：第一行
    # 第 2 行：第二行
    # 第 3 行：第三行
"""

FILES_EX2_STARTER = r"""import json
import tempfile
from pathlib import Path

# 要存的数据：三个字段（离线数据，不联网）
PROGRESS = {"lesson": "files", "done": 2, "total": 3}

with tempfile.TemporaryDirectory(dir=".") as workdir:
    path = Path(workdir) / "progress.json"

    def save(path, data):
        # 1) 用 with open(path, "w", encoding="utf-8") 加 json.dump 把 data 写进文件
        pass

    def load(path):
        # 2) 用 with open(path, encoding="utf-8") 加 json.load 读回来，返回这个字典
        pass

    def text_of(data):
        # 3) 返回 json.dumps(data, ensure_ascii=False) 的结果（只在内存里转，不落盘）
        pass

    # 4) 存进去再读回来，打印「读回来是字典：True」「字段对得上：True」两行
    # 5) 最后打印 text_of(back) 的结果
    # 6) 期望输出三行：
    # 读回来是字典：True
    # 字段对得上：True
    # {"lesson": "files", "done": 2, "total": 3}
"""

LESSONS_V7: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.py.strings",
        "skill_code": "route_a.a1",
        "stage": 1,
        "title": "字符串：几乎所有 AI 数据的形状",
        "summary": (
            "下标与切片各取到什么；strip / split / join / replace 是三件套怎么连着用；"
            "f 字符串与 format 的取舍；字符串不可变意味着每次操作都产生新串；"
            "为什么模型的输入输出要永远先当字符串处理"
        ),
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 17,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "能把一段模型返回的文本按「先清理、再拆分、再拼接」三步处理；知道下标与切片"
                "各自取到什么；分得清 strip / split / join / replace 各自返回什么；会按场景在"
                "f 字符串与 format 之间选一个；并且能说清「字符串不可变」意味着每次操作都产生"
                "新串、原串始终不变。"
            ),
            "explanation": [
                (
                    "模型给你的东西永远是文本：请求体是 JSON，JSON 里的人话是字符串；提示是"
                    "字符串，回答是字符串，日志也是字符串。从文件里读出来的是字符串，网页表单"
                    "提交上来的是字符串，接口失败时的报错还是字符串。所以「处理 AI 数据」的日常"
                    "主干，其实是把一串字符洗干净、切成结构、再拼成能看的样子——这节课练的就是"
                    "这三步。"
                ),
                (
                    "下标是「第几个字符」，从 0 开始数：text[0] 是第一个字符，text[-1] 是最后"
                    "一个。切片 text[a:b] 取的是「从 a 到 b 之前」的一段，不含 b，所以 text[:3]"
                    " 是前三个字符、text[-6:] 是最后六个。切片越界不报错，超出范围的部分直接被"
                    "截掉，这让它很适合做「最多显示 N 个字」这类显示逻辑。注意它按码点算，不是"
                    "按「看起来像一个字」算，中英混排时要自己数清楚。"
                ),
                (
                    "strip / split / join 是清理文本的三件套，而且通常连在一起用：先 strip 去掉"
                    "首尾空白（空格、换行、制表符都算），再 split 按分隔符切段，每段再 strip 一次，"
                    "最后 join 拼回去。split 不带参数时按任意长度的空白切，连续空格只算一个分隔"
                    "符；带参数时按那个分隔符切。要格外留意只切一次：值本身带分隔符时，"
                    'split(":", 1) 只切一刀，剩下的整体留在值里；不加这个 1，值会被切成好几段。'
                ),
                (
                    "字符串不可变：strip、replace、split 都不改动原字符串，它们返回新对象。想改就"
                    "得接住返回值——rc = text.strip() 之后 text 还是老样子，只写 text.strip() 不管"
                    "返回值，等于什么都没做。不可变还有一面好处：同一个字符串可以放心传给很多地方，"
                    "谁都不会偷偷改掉它。判等用 ==，别用 is：is 比的是「是不是同一个对象」，两段"
                    "内容相同的文字完全可能不是同一个对象。"
                ),
                (
                    "f 字符串与 format 是两种拼字符串的写法，取舍只有一条：拼接点少、变量就在旁边，"
                    "用 f 字符串最直白；字符串本身是一份要反复填的模板（放在配置里、要用不同数据填"
                    "很多次），用 format 更合适。两种都别和加号及 str() 混着用：一长串加法可读性差，"
                    "还特别容易漏空格、漏 str()，在数字处直接抛 TypeError。"
                ),
                (
                    "为什么模型的输入输出要「先当字符串处理」？因为你无法保证它按你想要的格式回来："
                    "多一个前导空格、少一个换行、结尾多一句客套话，都足以让后续解析失败。稳妥的顺序"
                    "是：先 strip 掉噪声，再按明确的分隔符切段，然后逐段校验「是不是我期待的形状」，"
                    "最后才当数据用。真遇上 JSON 就交给 json.loads，别用 split 手工切——嵌套、转义、"
                    "引号里的逗号，手工切一定会漏。"
                ),
            ],
            "example": {
                "title": "把一条模型返回的文本洗干净、切开、再拼回去",
                "code": STRINGS_EXAMPLE_CODE,
                "output": STRINGS_EXAMPLE_OUTPUT,
                "notes": [
                    "RAW 前后的空白被 strip 去掉；第二行还能看到 RAW 原样没动——字符串不可变。",
                    "cleaned[0] 取第一个字符，cleaned[-6:] 用负下标从尾部切，两个都是新串。",
                    "split 切开后逐段 strip，再拼成「键=值」；split 只切一次，值里的冒号不会被切走。",
                    "同一句话先用 format 再用 f 字符串：内容一致，取舍只在「模板复用」还是「就近拼接」。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "用加号和一串 str() 拼长文本",
                    "why": "可读性差，而且只要漏掉一处 str()，数字或列表就会让整行抛 TypeError。",
                    "fix": "拼接点用 f 字符串；模板复用改用 format，让变量待在它出现的位置。",
                },
                {
                    "mistake": "不 strip 就直接 split",
                    "why": "首尾空白会跟着第一段与最后一段进字段，后面按值比较时怎么都对不上。",
                    "fix": "先 strip 整段，切完再逐段 strip 一次；两步都做，别只做一步。",
                },
                {
                    "mistake": "写了 text.strip() 却以为 text 变了",
                    "why": "字符串不可变，strip 返回新串，不接住返回值就什么也没发生。",
                    "fix": "写成 text = text.strip() 或 rc = text.strip()，把返回值接住。",
                },
                {
                    "mistake": '值里带分隔符时仍然用 split(":") 切到底',
                    "why": "值被切成好几段，解包成两个变量时会直接抛 ValueError。",
                    "fix": '只切一次：split(":", 1)，第一刀之后剩下的整体留在值里。',
                },
                {
                    "mistake": "把 JSON 当普通字符串手工切",
                    "why": "嵌套结构、转义引号、引号里的逗号，手工切一定漏，而且错得很安静。",
                    "fix": "交给 json.loads：格式不对它会直接报错，比切出一堆错字段好排查。",
                },
            ],
            "self_check": [
                {
                    "question": "text[:3] 与 text[0] 分别取到什么？",
                    "answer": (
                        "text[:3] 取前三个字符（下标 0、1、2），text[0] 只取第一个字符；"
                        "两者都不会改动 text 本身。"
                    ),
                },
                {
                    "question": "strip、split、join 各自返回什么？",
                    "answer": (
                        "strip 返回去掉首尾空白的新字符串，split 返回列表，join 返回把列表"
                        "拼起来的新字符串。"
                    ),
                },
                {
                    "question": "什么时候用 f 字符串、什么时候用 format？",
                    "answer": (
                        "拼接点少、变量就在旁边用 f 字符串；字符串本身是要反复填的模板、"
                        "或者要放在配置文件里，用 format。"
                    ),
                },
                {
                    "question": "为什么模型输出要先当字符串处理？",
                    "answer": (
                        "你控制不了它回来的样子：多一个空格、少一个换行都会让解析失败。"
                        "先 strip、再按明确分隔符切、再逐段校验，最后才当数据用。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.py.files",
        "skill_code": "route_a.a1",
        "stage": 1,
        "title": "读写文件：让程序记住东西",
        "summary": (
            "open 与 with 的关系，以及为什么 with 不能省；encoding 为什么必须显式写；"
            "read / readlines / 逐行遍历各自适合什么；json.dump 与 json.load 的最小用法；"
            "写文件时 w 与 a 的区别"
        ),
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 18,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "能说清 open 与 with 的关系、为什么 with 不能省；知道 encoding 为什么必须显式"
                "写成 utf-8；分得清 read() / readlines() / 逐行遍历各自适合什么场景；会用"
                "json.dump 与 json.load 完成一次最小持久化；并且清楚写文件时 w 会清空、a 才追加。"
            ),
            "explanation": [
                (
                    "程序一结束，内存里的变量就没了。要让程序「记住」东西，就得把它写进文件："
                    "关掉再打开、明天再跑，内容还在。文件是最小的持久化单位，也是所有大工程的"
                    "起点——日志、配置、缓存、模型返回的原始结果，最终都落在文件里。"
                ),
                (
                    "open 打开文件后会占着一个句柄，必须关。忘了关的后果不是「浪费一点内存」："
                    "写出去的内容可能还停在缓冲区里没落盘，Windows 上文件还可能一直锁着删不掉，"
                    "程序跑久了会把句柄耗尽。with open(...) as handle 的意义就是——不管代码块是"
                    "正常结束、中途 return，还是抛了异常，关文件这件事一定会执行。所以「必须用"
                    " with」不是风格问题，是正确性问题。"
                ),
                (
                    "encoding 不能省。不写编码，Python 会用操作系统的默认编码：Windows 上多半是"
                    " GBK 一类的本地编码，读到 UTF-8 的中文就变成乱码、甚至直接抛"
                    " UnicodeDecodeError。写文件更隐蔽——本地编码写出去，别人用 UTF-8 读回来还是"
                    "乱码。把 encoding 显式写成 utf-8 是最便宜的跨平台保险，每一处 open 都写。"
                ),
                (
                    "三种读法按场景选：read() 一次拿到整段文本，最简单，但文件多大就占多大内存；"
                    "readlines() 一次读成列表，适合小文件里要按行号反复取；for line in handle"
                    " 逐行处理，任何时候只有一行在内存里，是处理大文件的标准写法。要注意逐行读"
                    "出来的每一行都带着结尾的换行符，比较之前先 strip，否则带换行的那一行永远"
                    "不等于你写的那几个字。"
                ),
                (
                    "json.dump 与 json.load 是 JSON 的「对文件」版本：dump 把字典写成文件，load"
                    " 从文件读回字典；只在内存里转字符串用 dumps / loads 这一对多一个 s 的写法。"
                    "ensure_ascii=False 让中文按原样写进文件，而不是写成一串转义序列——写给自己"
                    "看的文件，可读性值这个参数。反过来，读别人的 JSON 要当心：格式不对会抛"
                    " JSONDecodeError，所以读之前先确认文件不是空的，写的时候用 with 确保内容"
                    "真的落了盘。"
                ),
                (
                    "w 与 a 决定了「写」的语义：w 模式打开就清空，文件不存在才新建——所以拿 w"
                    " 写日志，每次都只剩最后一条；a 模式把写入点挪到末尾，追加而不覆盖。判断方法"
                    "很朴素：这次写入要保留旧内容就用 a，要整体重写就用 w。写完立刻用 with 读回"
                    "来一次，是验证「真的写进去了」最便宜的检查，也正是本课示例最后两步在做的事。"
                ),
            ],
            "example": {
                "title": "用 with 写进去、读回来，再把 w 与 a 的差别摆出来",
                "code": FILES_EXAMPLE_CODE,
                "output": FILES_EXAMPLE_OUTPUT,
                "notes": [
                    "整段示例只在自己创建的临时目录里读写，结束时自动删掉：不联网、不碰仓库里的其他文件。",
                    "四处写文件都用 with：块结束时自动 close，内容一定落盘，抛异常也一样。",
                    "read() 拿到整段、逐行遍历每行一条、readlines() 拿到列表：三种读法按场景选。",
                    "最后一步用 w 再打开同一个文件，前面三行就没了——这就是 w 与 a 的区别。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "直接 open 打开、写完忘了 close",
                    "why": "缓冲区里的内容可能没落盘，Windows 上文件还会被锁住，下一次读到的可能是空的。",
                    "fix": "一律写成 with open(...) as handle：正常结束、提前 return、抛异常都会关。",
                },
                {
                    "mistake": "open 时不写 encoding",
                    "why": "用系统默认编码读写，中文在 Windows 上会乱码，或者直接抛 UnicodeDecodeError。",
                    "fix": "每一处 open 都补上 encoding 并写死 utf-8，读和写都补。",
                },
                {
                    "mistake": "往日志里用 w 模式继续写",
                    "why": "w 一打开就清空，日志里每次只剩最后一条，历史全丢。",
                    "fix": "追加用 a 模式；只有确实要整体重写时才用 w。",
                },
                {
                    "mistake": "读到的行不 strip 就和目标字符串比较",
                    "why": "每行结尾带着换行符，带换行的字符串永远不等于你写的那几个字。",
                    "fix": "比较、拼接之前先 strip；写出去时也别自己再补一个换行。",
                },
                {
                    "mistake": "读一个可能为空的 JSON 文件",
                    "why": "空文件不是合法 JSON，json.load 会抛 JSONDecodeError，整个程序停在这里。",
                    "fix": "读之前看一眼内容是否为空，或者用 try 接住解析错误，把「文件坏了」当成正常分支。",
                },
            ],
            "self_check": [
                {
                    "question": "为什么 with open 不能省？",
                    "answer": (
                        "它保证不管代码块怎么结束都会关文件：内容真的落盘，句柄不泄漏，"
                        "异常路径上也不会留一个开着半截的文件。"
                    ),
                },
                {
                    "question": "encoding 为什么不写就会出问题？",
                    "answer": (
                        "不写就用操作系统的默认编码；Windows 上读写 UTF-8 的中文会乱码，"
                        "甚至直接抛 UnicodeDecodeError。"
                    ),
                },
                {
                    "question": "read()、readlines()、逐行遍历怎么选？",
                    "answer": (
                        "小文件求简单用 read()；要按行号反复取用 readlines()；文件可能很大、"
                        "只需顺序处理，用 for line in handle。"
                    ),
                },
                {
                    "question": "w 与 a 的差别是什么？",
                    "answer": "w 打开就清空、整体重写；a 把写入点挪到末尾、保留旧内容。",
                },
            ],
        },
    },
)

EXERCISES_V7: tuple[dict[str, object], ...] = (
    # --- 课程 17：字符串是几乎所有 AI 数据的形状 ---------------------------------
    {
        "lesson_code": "route_a.py.strings",
        "code": "route_a.py.strings.ex1",
        "title": "拆一条模型输出：先清理，再切段，再拼回去",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一条模型返回的原始文本洗干净、拆成字段，再拼回一行能看的结果。\n"
            "要做的事：\n"
            "1) clean(text)：用 strip 去掉首尾空白，返回去掉之后的新字符串；\n"
            "2) fields(text)：按竖线把 text 切成若干段，每段再去掉两端空白，返回这些段组成的"
            "列表；\n"
            "3) pairs(text)：把每段按冒号只切一次，键和值都去掉空白，返回「键=值」形式的新字符"
            "串列表；\n"
            "4) 用 for 逐段打印「第 N 段：键=值」；\n"
            "5) 用 join 把各段拼成一行，打印「拼回去：…」；\n"
            "6) 打印「clean 返回的是新串：True」——用 is not 比较，证明它返回的是新对象；\n"
            "7) 期望输出四行：\n"
            "第 1 段：问题=什么是 RAG?\n"
            "第 2 段：答案是=先检索再生成\n"
            "拼回去：问题=什么是 RAG?；答案是=先检索再生成\n"
            "clean 返回的是新串：True\n"
            "注意：RAW 前后有空白、字段之间有竖线，先 strip 再 split 的顺序不能反；冒号只切一次，"
            "否则值里的冒号会把一段切成两段。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": STRINGS_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 第 1 段：问题=什么是 RAG?：前导空白已被 strip 掉，键里不带空格",
            },
            {
                "name": "自检 2",
                "expect": "第二行 第 2 段：答案是=先检索再生成：第二段同样切、同样去掉两端空白",
            },
            {
                "name": "自检 3",
                "expect": "第三行 拼回去：…：两段用中文分号连成一行，顺序与原文一致",
            },
            {
                "name": "自检 4",
                "expect": "第四行 clean 返回的是新串：True：不可变意味着每次操作都返回新对象",
            },
        ],
        "required_patterns": [
            r"def\s+clean\s*\(",
            r"def\s+fields\s*\(",
            r"def\s+pairs\s*\(",
            r"\.strip\s*\(",
            r"\.split\s*\(",
            r"\.join\s*\(",
            r"return\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 clean 去掉首尾空白",
            "定义函数 fields 按竖线把文本切段",
            "定义函数 pairs 拼出键值对",
            "用 strip 去掉每段两端的空白",
            "用 split 把一段文字切成若干段",
            "用 join 把各段拼回一行",
            "用 return 把结果交回调用方",
            "用 print 打印每一段与拼回去的结果",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "第 1 段：问题=什么是 RAG?\n"
            "第 2 段：答案是=先检索再生成\n"
            "拼回去：问题=什么是 RAG?；答案是=先检索再生成\n"
            "clean 返回的是新串：True"
        ),
    },
    {
        "lesson_code": "route_a.py.strings",
        "code": "route_a.py.strings.ex2",
        "title": "收拾一条带标记的输出，并亲手验证不可变",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：用 replace 与切片把一条带标记的模型输出收拾干净，并亲手验证字符串不可变。\n"
            "要做的事：\n"
            "1) strip_marks(text)：用 replace 去掉开头的三个井号加一个空格，返回新字符串；\n"
            "2) drop_duplicate(text)：用 replace 把结尾重复的两个句号换成一个句号，返回新字符串；\n"
            "3) headline(text, limit)：用切片只取开头 limit 个字符，返回这一段；\n"
            "4) 依次打印「第 1 步：…」「第 2 步：…」「前 10 个字符：…」三行；\n"
            "5) 最后打印「原串还是原来的样子：True」，证明每一步都产生新串、RAW 一个字都没变；\n"
            "6) 期望输出四行：\n"
            "第 1 步：答案：检索增强 先取回原文片段，再让模型基于片段回答。。\n"
            "第 2 步：答案：检索增强 先取回原文片段，再让模型基于片段回答。\n"
            "前 10 个字符：答案：检索增强 先取\n"
            "原串还是原来的样子：True\n"
            "注意：第 1 步只是在去掉开头标记，结尾的两个句号还在；第 2 步才把它们合成一个。"
            "这两行不一样，正是「每一步返回一条新串」的证据。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": STRINGS_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行以 答案： 开头且结尾仍是两个句号：只去掉了开头的井号标记",
            },
            {
                "name": "自检 2",
                "expect": "第二行结尾只有一个句号：重复的两个句号已合成一个",
            },
            {
                "name": "自检 3",
                "expect": "第三行 前 10 个字符：答案：检索增强 先取：切片用开头 limit 个字符",
            },
            {
                "name": "自检 4",
                "expect": "第四行 原串还是原来的样子：True：RAW 没被任何一步改过",
            },
        ],
        "required_patterns": [
            r"def\s+strip_marks\s*\(",
            r"def\s+drop_duplicate\s*\(",
            r"def\s+headline\s*\(",
            r"\.replace\s*\(",
            r"\[:\s*\w+\s*\]",
            r"return\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 strip_marks 去掉开头标记",
            "定义函数 drop_duplicate 合并重复标点",
            "定义函数 headline 只取开头几个字",
            "用 replace 换掉标记与重复标点",
            "用切片取开头若干个字符",
            "用 return 把新串交回调用方",
            "用 print 打印每一步的结果",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "第 1 步：答案：检索增强 先取回原文片段，再让模型基于片段回答。。\n"
            "第 2 步：答案：检索增强 先取回原文片段，再让模型基于片段回答。\n"
            "前 10 个字符：答案：检索增强 先取\n"
            "原串还是原来的样子：True"
        ),
    },
    # --- 课程 18：读写文件，让程序记住东西 ---------------------------------------
    {
        "lesson_code": "route_a.py.files",
        "code": "route_a.py.files.ex1",
        "title": "写进去再读回来：with open 与 w、a 的配合",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：用 with open 把一个列表写进文件，再用 a 追加一行，最后逐行读回来。\n"
            "要做的事：\n"
            '1) write_lines(path, lines)：用 with open(path, "w", encoding="utf-8") 把 lines'
            " 逐行写进去（w 会清空重写）；\n"
            '2) append_line(path, line)：用 with open(path, "a", encoding="utf-8") 在末尾追加'
            "一行（a 不覆盖已有内容）；\n"
            '3) read_lines(path)：用 with open(path, encoding="utf-8") 逐行读，去掉每行结尾的'
            "空白，返回这些行组成的列表；\n"
            "4) 先写两行、再追加一行、再读回来：先打印「读回 3 行」；\n"
            "5) 用 for 逐行打印「第 N 行：…」；\n"
            "6) 期望输出四行：\n"
            "读回 3 行\n"
            "第 1 行：第一行\n"
            "第 2 行：第二行\n"
            "第 3 行：第三行\n"
            "注意：三个 with 一个都不能省；不写 encoding，Windows 上会按本地编码读写，中文会乱码。"
            "读回来的每行带换行符，比较与打印之前都要 strip。\n"
            "禁止：不许访问网络；只在练习自己创建的临时目录里读写，不读系统文件。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": FILES_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 读回 3 行：两行 write 加一行 append，读回来正好三条",
            },
            {
                "name": "自检 2",
                "expect": "第二行与第三行是第一、第二行的内容：write_lines 用了 w 模式写入",
            },
            {
                "name": "自检 3",
                "expect": "第四行 第 3 行：第三行：append_line 用了 a 模式，没有把前两行清掉",
            },
            {
                "name": "自检 4",
                "expect": "把 append_line 的模式换成 w 再跑，读回来只剩一行——这就是 w 与 a 的差别",
            },
        ],
        "required_patterns": [
            r"with\s+open\s*\(",
            r"encoding\s*=\s*[\"']utf-8[\"']",
            r"[\"']w[\"']",
            r"[\"']a[\"']",
            r"\.strip\s*\(",
            r"def\s+read_lines\s*\(",
            r"return\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "用 with 打开文件并自动关闭",
            "打开文件时写明 utf-8 编码",
            "用 w 模式清空重写文件",
            "用 a 模式在末尾追加内容",
            "用 strip 去掉每行结尾的空白",
            "定义函数 read_lines 把行读回来",
            "用 return 把读到的行交回调用方",
            "用 print 打印读回来的每一行",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": ("读回 3 行\n第 1 行：第一行\n第 2 行：第二行\n第 3 行：第三行"),
    },
    {
        "lesson_code": "route_a.py.files",
        "code": "route_a.py.files.ex2",
        "title": "把字典存成 JSON：dump 落盘、load 读回",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把字典存成 JSON 文件再读回来，并分清淡「对着文件」与「对着字符串」的两组写法。\n"
            "要做的事：\n"
            '1) save(path, data)：用 with open(path, "w", encoding="utf-8") 加 json.dump 把'
            " data 写进文件，转中文时带上 ensure_ascii=False；\n"
            '2) load(path)：用 with open(path, encoding="utf-8") 加 json.load 读回来，返回这个'
            "字典；\n"
            "3) text_of(data)：返回 json.dumps(data, ensure_ascii=False) 的结果（只在内存里转，"
            "不落盘）；\n"
            "4) 存进去再读回来，打印「读回来是字典：True」与「字段对得上：True」两行；\n"
            "5) 最后打印 text_of(back) 的结果；\n"
            "6) 期望输出三行：\n"
            "读回来是字典：True\n"
            "字段对得上：True\n"
            '{"lesson": "files", "done": 2, "total": 3}\n'
            "注意：json.dump 与 json.dumps 的差别只在「写进文件」还是「得到一段字符串」；"
            "ensure_ascii=False 让中文按原样写，否则会变成一串转义序列。\n"
            "禁止：不许访问网络；只在练习自己创建的临时目录里读写，不读系统文件。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": FILES_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 读回来是字典：True：json.load 返回的是字典而不是字符串",
            },
            {
                "name": "自检 2",
                "expect": "第二行 字段对得上：True：读回来的字典与存进去的一模一样",
            },
            {
                "name": "自检 3",
                "expect": '第三行 {"lesson": "files", "done": 2, "total": 3}：dumps 的结果',
            },
            {
                "name": "自检 4",
                "expect": "把 ensure_ascii 改成 True 再跑，第三行里的中文会变成转义序列",
            },
        ],
        "required_patterns": [
            r"with\s+open\s*\(",
            r"encoding\s*=\s*[\"']utf-8[\"']",
            r"json\.dump\s*\(",
            r"json\.load\s*\(",
            r"json\.dumps\s*\(",
            r"def\s+load\s*\(",
            r"return\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "用 with 打开文件并自动关闭",
            "打开文件时写明 utf-8 编码",
            "用 json.dump 把字典写进文件",
            "用 json.load 从文件读回字典",
            "用 json.dumps 在内存里转成字符串",
            "定义函数 load 读回字典",
            "用 return 把字典交回调用方",
            "用 print 打印核对结果",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            '读回来是字典：True\n字段对得上：True\n{"lesson": "files", "done": 2, "total": 3}'
        ),
    },
)


def upgrade() -> None:
    """Seed the two Sprint 15 lessons and their four exercises (idempotent)."""
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
        "0020_sprint15_py_strings_files 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
