"""Sprint 9 内容：补上 a2「编程实践」两节课，以及每课两道练习

Revision ID: 0013_sprint9_practice_content
Revises: 0012_sprint8_rag_agent
Create Date: 2026-03-26 00:00:00+00:00

六域覆盖现状：a1 五节、a3 / a4 / a5 / a6 各一节，只有 a2「编程实践」
（能把需求拆成函数，能读懂报错并自行定位）一节课都没有——六域里有五域能学，
偏偏「自己动手写、自己动手查」这一域是空的。本迁移补上
route_a.practice.decompose（30 分钟）与 route_a.practice.debug（30 分钟）
两节课，以及每课两道练习（共 4 道）。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 9 节课、18 道练习与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习都只用「本地数据 / 本地报错原文」当教材，
学习与判题都不需要联网、不需要密钥。4 道练习的 forbidden_patterns 都把「导入
网络库」与「真实 URL 字面量」写成正则禁止项，静态判题会直接拒掉联网写法。

order_index 取 10 / 11：lessons.order_index 上已有 1–9（a1 五节 + a3/a4/a5/a6
四节），本迁移只发 INSERT、不改写既有行，因此新课只能接在后面；stage 仍是 a2
的 2，列表接口按 (stage, order_index) 排序时它们会落在 a1 之后、a3 之前。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0013_sprint9_practice_content"
down_revision: str | None = "0012_sprint8_rag_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库
# 生成（lessons 用 identity，0011 / 0012 那四节课的真实 id 是 1058 / 1059 / 1108 / 1109），
# 硬编码会在另一个库上指向错误的行（这正是 0003 / 0004 / 0011 / 0012 的写法）。
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

LESSONS_V4: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.practice.decompose",
        "skill_code": "route_a.a2",
        "stage": 2,
        "title": "把一段需求拆成几个函数",
        "summary": "先写一句「输入 -> 输出」，再按动词拆成读数据 / 算结果 / 打印三个函数，靠参数与返回值串起来",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 10,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "拿到一段需求，能先写出「输入 -> 输出」这一句话再动手；能按动词把它拆成"
                "「读数据 / 算结果 / 打印」三个各做一件事的函数；能让函数之间靠参数与返回值"
                "连接，而不是靠全局变量；拆完能用两组数据自测，确认换一组输入输出跟着变。"
            ),
            "explanation": [
                (
                    "拆函数之前，先写一句话：「输入是什么，输出是什么」。这句话不是为了好看，"
                    "它是拆的标准——只有当你知道进来的东西长什么样、出去的东西长什么样，你才"
                    "知道中间该切成几段。跳过这句直接动手，写出来的函数往往同时干两件不相干的"
                    "事（一边读数据一边算，顺手还打印一句），等你要改其中一半时，只能在两个"
                    "目的缠在一起的代码里翻找。先写句子，是让后面的每一刀都落在正确的位置上。"
                ),
                (
                    "怎么切？按需求里的**动词**切。「把每门课的平均分算出来打印给我」这句话里"
                    "有三个动词：读（把文本行变成数据）、算（把一组分数变成一个平均值）、"
                    "打印（把结果变成屏幕上的一行）。三个动词就是三条边界，对应三个函数。"
                    "一个简单的自检：函数名里要是塞进了「和」「然后」「顺便」，说明它还该再拆。"
                    "函数名应当是一个动作，而不是一段流程。"
                ),
                (
                    "为什么每个函数只做一件事？因为「只做一件事」才换得来两样东西：可替换、可"
                    "单独验证。算平均值的那一段，只要它只依赖参数，明天换成算最高分、算中位数，"
                    "改的就是一个函数体，其他代码一行不动；反过来，一个函数里又读文件又算又打印，"
                    "你想单独验算「平均分算对了没有」都做不到——它一被调用就会去读文件、就会打印。"
                    "一件事一个函数，是把「能不能单独测」这件事提前安排好。"
                ),
                (
                    "函数之间怎么连接？靠参数进来、返回值出去，不要靠全局变量。全局变量的问题是"
                    "它把依赖藏起来了：函数签名上看不出它需要什么，你也看不出谁改了它；第二份"
                    "数据进来（换一个班、换一天）就得先改写全局变量，稍不留神两份数据串在一起，"
                    "报错还报在完全无关的地方。参数与返回值把依赖写在脸上：读数据的函数返回一个"
                    "字典，算结果的函数收这个字典、返回一个数，打印的函数收这个数。这条链子上"
                    "每一步的输入输出都是显式的。"
                ),
                (
                    "打印为什么也要拆出去、并且留在最外层？因为打印是**副作用**：一旦计算函数里"
                    "面写了 print，它就只能对着屏幕用——想写进文件、想返回给接口、想在测试里"
                    "断言结果，全都办不到。把 print 关在最外层，计算函数就变成「给什么算什么」"
                    "的纯加工，这才是能复用的部分。这也是拆分真正带来的收益：不是代码变短了，"
                    "而是每段代码的职责变清楚了。"
                ),
                (
                    "拆完怎么自测？至少两组数据，再补一个边界。第一组正常数据，确认输出对得上"
                    "你手算的结果；第二组换掉数据（换课名、换分数），确认输出跟着变——如果换成"
                    "第二组结果还是老样子，说明某处把值写死了；边界补一个只有一门课、或者分数"
                    "列表只有一个数的情况，确认没有除零、没有空结果。这一步花两分钟，比事后在"
                    "整段脚本里找「为什么打印了两遍」便宜得多。"
                ),
            ],
            "example": {
                "title": "读 -> 算 -> 打：三个函数，一条参数与返回值组成的链子",
                "code": (
                    "# 需求：给一份「课名,分数」的清单，打印每门课的平均分\n"
                    "# 先写一句话：输入是若干行「课名,分数」文本，输出是每门课一行的平均分\n"
                    'raw = ["数学,80", "数学,90", "数学,100", "英语,70", "英语,60"]\n'
                    "\n"
                    "\n"
                    "def read_scores(lines):\n"
                    '    """读：只把文本行变成 {课名: [分数, ...]}，不打印、不算数。"""\n'
                    "    scores = {}\n"
                    "    for line in lines:\n"
                    '        name, text = line.split(",")\n'
                    "        scores.setdefault(name, []).append(int(text))\n"
                    "    return scores\n"
                    "\n"
                    "\n"
                    "def average(values):\n"
                    '    """算：只算一个列表的平均值，保留一位小数。"""\n'
                    "    return round(sum(values) / len(values), 1)\n"
                    "\n"
                    "\n"
                    "def report(scores):\n"
                    '    """打：副作用只留在这里，计算函数一个 print 都没有。"""\n'
                    "    for name, values in scores.items():\n"
                    '        print(f"{name}: {average(values)}")\n'
                    "\n"
                    "\n"
                    "# 连接方式写在最外层：读的返回值喂给打印，全程没有全局变量\n"
                    "report(read_scores(raw))\n"
                ),
                "output": "数学: 90.0\n英语: 65.0",
                "notes": [
                    "read_scores 只读、average 只算、report 只打：三个函数各做一件事，各自能单独验证。",
                    "average 只认一个列表，所以它既能算一门课，也能算一个学生的所有课——复用是从这里来的。",
                    "整条链子只有参数与返回值，没有 global：换一份 raw，输出就跟着变。",
                    "print 只在 report 里出现，所以你随时可以把 report 换成「写文件」而不动计算逻辑。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "不写「输入 -> 输出」那句话，直接从一个空文件开始写",
                    "why": (
                        "不知道边界就没法判断一个函数该到哪儿结束；写到最后函数之间互相调用、"
                        "互相修改，改一处牵动全身。"
                    ),
                    "fix": "先在纸上（或注释里）写一行：输入是什么、输出是什么，再决定切几段。",
                },
                {
                    "mistake": "一个函数里又读数据、又算结果、又 print",
                    "why": (
                        "三件事绑在一起后，算得对不对没法单独验证：一调用它就会去读数据、"
                        "就会打印，你想只测计算那一步都做不到。"
                    ),
                    "fix": "计算函数只 return 结果，print 留在最外层那个负责输出的函数里。",
                },
                {
                    "mistake": "靠 global 把数据传给函数",
                    "why": (
                        "依赖被藏起来了：函数签名看不出它需要什么，谁改了全局变量也追不到；"
                        "第二份数据进来时很容易两份串味。"
                    ),
                    "fix": "参数进来、返回值出去：read_scores(lines) 返回字典，report(scores) 收字典。",
                },
                {
                    "mistake": "拆完只拿一组数据跑一遍就算完",
                    "why": "一组数据过关可能只是碰巧：写死的值、只对某个顺序成立的逻辑都测不出来。",
                    "fix": "换一组数据再跑（输出必须跟着变），再补一个只有单个元素或空列表的边界。",
                },
            ],
            "self_check": [
                {
                    "question": "「输入 -> 输出」这句话在实际拆函数时有什么用？",
                    "answer": (
                        "它定下了这条流水线的两端，你才能判断中间该切成几段、每段接过什么、"
                        "交出什么；没有这句话，切出来的函数边界一定是凭感觉的。"
                    ),
                },
                {
                    "question": "怎样判断一个函数是不是还该再拆？",
                    "answer": (
                        "看函数名里有没有「和 / 然后 / 顺便」；再看它是否同时做了两件可以用不同"
                        "输入单独验证的事。一个函数应当是一个动词。"
                    ),
                },
                {
                    "question": "为什么函数之间要用参数与返回值连接，而不是全局变量？",
                    "answer": (
                        "参数与返回值把依赖写在函数签名上，看得见、追得到；全局变量把依赖藏起来，"
                        "换一份数据就得偷改外部状态，出错点还会漂到别处。"
                    ),
                },
                {
                    "question": "拆分完成后，最小的一套自测是什么？",
                    "answer": (
                        "两组不同的数据各跑一次（确认输出跟着变，说明没有写死），再补一个边界"
                        "（单元素或空列表），确认不会除零、不会崩。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.practice.debug",
        "skill_code": "route_a.a2",
        "stage": 2,
        "title": "读懂报错，自己定位",
        "summary": "从 Traceback 最后一行往前读（异常类型 -> 出错行 -> 调用链），认三类常见异常，用 print 二分缩小范围",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 11,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能读一条 Traceback：从最后一行往前看，先认异常类型，再看出错行，最后看调用链；"
                "能把 TypeError / KeyError / IndexError 对上各自的典型成因；能用 print 与二分法"
                "把出错范围缩到一行；改完能确认别处没有被改坏。"
            ),
            "explanation": [
                (
                    "报错不是判决书，是线索，而且是一条按固定顺序写好的线索。Traceback 的读法"
                    "和读小说相反：**从最后一行往前看**。最后一行是「异常类型: 附加说明」——"
                    "它告诉你死因（KeyError 是键不存在，TypeError 是类型不对，IndexError 是"
                    "下标越界）。倒数第二、三行写着「File 某某, line 12, in 某函数」和出错那一行"
                    "的源码——它告诉你死在哪一行。再往上是调用链：谁调了谁。新手最常做的动作是"
                    "从第一行开始读，结果读了一屏文件路径，真正有用的三行还没看到。"
                ),
                (
                    "三类常见异常，各自有典型成因，认出类型就跳过一半排查。KeyError：字典里没有"
                    "这个键——键名拼错、大小写不一致、数据里根本没这个人；它明明白白告诉你是哪个"
                    "键，别急着怀疑逻辑。TypeError：把一种类型当另一种用——字符串下标当字典用、"
                    "把 None 当数字算、函数少传一个参数。IndexError：下标超出列表长度——最常见的"
                    "是忘了列表从 0 开始、或者空列表直接取 [0]。看见类型先在心里默念一遍「我这段"
                    "代码有没有可能犯这种错」，比乱加 print 快得多。"
                ),
                (
                    "类型和行号给了方向，但「为什么这一行拿到的是这个值」还得自己查。print 调试"
                    "不是到处撒 print，而是**二分定位**：先在中间位置打印一次，看值对不对——"
                    "对，说明问题在后半段；不对，说明前半段就已经错了。每打一次范围减半，十来行"
                    "的脚本两三次就能缩到具体那一行。关键是要打印**能区分两种可能的那个值**："
                    "不确定是不是键名错了，就把字典的 keys() 打出来对照；不确定是不是空列表，"
                    "就把长度打出来。"
                ),
                (
                    "为什么不要用 try/except 把异常吞掉？因为异常是在告诉你「这里的数据和你的"
                    "假设不符」，把它兜住等于把线索扔了：程序继续跑下去，错误的结果会在更远的地方"
                    "以更难懂的方式冒出来（打印出一份少了一行、或者全是 0 的报告）。正确顺序是"
                    "先定位、再决定要不要兜；真要兜，也要兜在明确知道「这里可能缺数据、缺了用什么"
                    "补」的地方，比如用 .get(键, 默认值) 表达「缺了就按 0 算」，这比 except: pass"
                    " 诚实得多。"
                ),
                (
                    "改完还没结束：要确认别处没被改坏。最小做法是三步——第一，用**出错前那份"
                    "数据**再跑一次，看它是否正常通过（没有把正常路径也堵死）；第二，用能触发"
                    "问题的那份数据再跑一次，确认不再报错且结果是你要的默认值；第三，把这次"
                    "改动涉及的所有输出重新对一遍（平均分还是那个平均分吗？行数还是那么多行吗？）。"
                    "改一处、错一处，是修 bug 最常见的二次伤害。"
                ),
                (
                    "最后一个边界：报错指向的行，不一定是该改的行。KeyError 报在取值那一行，"
                    "但真正的错可能是三行之前数据压根没被塞进来；TypeError 报在相加那一行，"
                    "但错在上一行把值赋成了 None。所以顺序是：先用报错定位**现象**，再用 print "
                    "确认**前提**，最后才决定改哪一行。报错是线索，不是结论。"
                ),
            ],
            "example": {
                "title": "从最后一行往前读一条 Traceback，再用 .get() 修好",
                "code": (
                    "# 一份成绩表（离线教材）：键是学生名\n"
                    'scores = {"小明": 90, "小红": 85}\n'
                    "\n"
                    "# 1) 报错原文：把它当线索，从最后一行往前读\n"
                    "traceback_text = (\n"
                    "    'Traceback (most recent call last):\\n'\n"
                    "    '  File \"report.py\", line 9, in <module>\\n'\n"
                    "    '    print(scores[\"小刚\"])\\n'\n"
                    "    \"KeyError: '小刚'\\n\"\n"
                    ")\n"
                    "print(traceback_text.strip())\n"
                    "\n"
                    "# 2) 最后一行 = 异常类型 + 缺的键；File 那一行 = 出错的行号\n"
                    'lines = traceback_text.strip().split("\\n")\n'
                    'print("最后一行:", lines[-1])\n'
                    'print("出错行:", lines[1].strip())\n'
                    "\n"
                    "# 3) 修：缺一个学生不该让整份报告炸掉，改成 .get(键, 默认值)\n"
                    'print(scores.get("小明", 0))\n'
                    'print(scores.get("小刚", 0))\n'
                ),
                "output": (
                    "Traceback (most recent call last):\n"
                    "  File \"report.py\", line 9, in <module>\n"
                    "    print(scores[\"小刚\"])\n"
                    "KeyError: '小刚'\n"
                    "最后一行: KeyError: '小刚'\n"
                    "出错行: File \"report.py\", line 9, in <module>\n"
                    "90\n"
                    "0"
                ),
                "notes": [
                    "最后一行 KeyError: '小刚' 同时给了两件事：死因是键不存在，缺的键是「小刚」。",
                    "File 那一行的 line 9 才是出错位置；再往上的行是调用链，说明是谁调到了这里。",
                    ".get(键, 0) 说的是「缺了就按 0 算」——把假设写出来，而不是用 except 把异常吞掉。",
                    "修完要做回归：小明那行仍然是 90，说明正常路径没有被改坏。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "从 Traceback 第一行开始往下读，读到一堆文件路径就放弃",
                    "why": (
                        "最上面是调用链的起点（往往是框架内部或模块入口），最有用的死因与行号"
                        "在最下面，读反了就是白读。"
                    ),
                    "fix": "先看最后一行（异常类型 + 附加说明），再看它上面那行 File / line，最后才往上看调用链。",
                },
                {
                    "mistake": "看见 KeyError 就去改报错那一行，不看数据到底有没有这个键",
                    "why": (
                        "报错指向的是「取值」这个动作，真正的原因可能是几行之前数据就没被塞进来、"
                        "或者键名拼成了另一个字。"
                    ),
                    "fix": "先把字典的 keys() 打出来，对照你要取的那个键，确认是拼错还是数据缺失。",
                },
                {
                    "mistake": "用 try/except 把异常一把兜住，让程序先跑完",
                    "why": (
                        "异常说明数据与假设不符；兜住它，错误结果会在更远的地方以更难懂的样子出现，"
                        "而且你再也看不到最初那条线索。"
                    ),
                    "fix": "先定位再决定要不要兜；确实可能缺数据时，用 .get(键, 默认值) 把假设写明。",
                },
                {
                    "mistake": "改完只跑「会报错的那份数据」就交付",
                    "why": "修复常常顺手堵死正常路径：默认值把正常值也覆盖了、条件改反了，而你没再跑一次正常数据。",
                    "fix": "三步回归：正常数据仍通过、出错数据不再报错且结果是你想要的、所有输出重新对一遍。",
                },
            ],
            "self_check": [
                {
                    "question": "Traceback 应该按什么顺序读？",
                    "answer": (
                        "从最后一行往前：最后一行是异常类型与说明，上面是 File / line 与出错那一行源码，"
                        "再往上是调用链（谁调了谁）。"
                    ),
                },
                {
                    "question": "KeyError、TypeError、IndexError 各自最常见的成因是什么？",
                    "answer": (
                        "KeyError：字典里没有这个键（拼错、大小写、数据缺失）；TypeError：把一种类型"
                        "当另一种用（字符串当字典、None 参与运算、少传参数）；IndexError：下标越界或空列表取 [0]。"
                    ),
                },
                {
                    "question": "print 调试怎样才高效？",
                    "answer": (
                        "二分：先在中间位置打印能区分两种假设的那个值，对了查后半段、错了查前半段，"
                        "每打一次范围减半，而不是到处撒 print。"
                    ),
                },
                {
                    "question": "改完为什么一定要跑一遍正常数据？",
                    "answer": (
                        "修复很可能顺手改坏了正常路径（默认值盖住正常值、条件写反）；只跑出错那份数据，"
                        "这种二次伤害查不出来。"
                    ),
                },
            ],
        },
    },
)

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

# 判题是纯文本的静态规则：required_patterns 是正则字符串（一律用 raw string，\b 不能被
# 当成退格），能把「写对了」和「没写」区分开；visible_tests 是给人看的自检说明，不参与
# 自动执行。四道题都把联网写法列为 forbidden：静态规则会直接拒掉。
EXERCISES_V4: tuple[dict[str, object], ...] = (
    # --- 课程 10：把一段需求拆成几个函数 -------------------------------------
    {
        "lesson_code": "route_a.practice.decompose",
        "code": "route_a.practice.decompose.ex1",
        "title": "把「读入 + 计算 + 输出」拆成三个函数",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「读入数据 -> 算结果 -> 打印」拆成三个各做一件事的函数，再靠参数与返回值"
            "把它们串起来。\n"
            "要做的事：\n"
            "1) read_scores(lines)：遍历 lines，每行用 split(\",\") 拆成课名和分数文本，"
            "把 int(分数) 追加到该课名对应的列表里（用 setdefault 或先判断都行），最后 return "
            "这个 {课名: [分数, ...]} 字典；\n"
            "2) average(values)：返回 round(总分 / 个数, 1)；这个函数里一个 print 都不许有；\n"
            "3) report(scores)：遍历字典，按「课名: 平均分」打印，一行一门课；平均分必须调用 "
            "average 得到，不许在 report 里把 sum / len 再写一遍；\n"
            "4) 最后用 report(read_scores(raw)) 把两个函数接起来，期望输出两行："
            "数学: 90.0 / 英语: 65.0。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）；不许在计算函数里 print；"
            "不许用 global 传值；不许把平均分直接写死成字面量。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": (
            "# 原始数据：每行是 \"课名,分数\"（离线教材：不读文件、不联网）\n"
            'raw = ["数学,80", "数学,90", "数学,100", "英语,70", "英语,60"]\n'
            "\n"
            "\n"
            "def read_scores(lines):\n"
            "    # 1) 读：把一行行 \"课名,分数\" 变成 {课名: [分数, ...]}，只 return，不打印\n"
            "    pass\n"
            "\n"
            "\n"
            "def average(values):\n"
            "    # 2) 算：只算一个列表的平均值，保留一位小数\n"
            "    pass\n"
            "\n"
            "\n"
            "def report(scores):\n"
            "    # 3) 打：按课名顺序打印「课名: 平均分」，平均分由 average 算\n"
            "    pass\n"
            "\n"
            "\n"
            "# 4) 连接已经写好：读的返回值喂给打印（靠参数与返回值，不要改成全局变量）\n"
            "scores = read_scores(raw)\n"
            "report(scores)\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "输出第一行是 数学: 90.0：80、90、100 的平均分"},
            {"name": "自检 2", "expect": "输出第二行是 英语: 65.0：70、60 的平均分"},
            {
                "name": "自检 3",
                "expect": "average 里没有任何 print：把 average([10, 20]) 单独算一次，只会得到 15.0",
            },
            {
                "name": "自检 4",
                "expect": "把 raw 改成两组别的数据再跑，两行输出跟着变——说明没有写死",
            },
        ],
        "required_patterns": [
            r"def\s+read_scores\s*\(",
            r"def\s+average\s*\(",
            r"def\s+report\s*\(",
            r"\.split\s*\(\s*['\"],['\"]\s*\)",
            r"\bint\s*\(",
            r"\bround\s*\(",
            r"return\s+scores\b",
            r"print\s*\(\s*f['\"]",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\bglobal\b",
        ],
        "expected_output": "数学: 90.0\n英语: 65.0",
    },
    {
        "lesson_code": "route_a.practice.decompose",
        "code": "route_a.practice.decompose.ex2",
        "title": "用参数与返回值连接，不用全局变量",
        "order_index": 2,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一份「靠全局变量传数据」的脚本改成两个函数，让依赖写在函数签名上。\n"
            "要做的事：\n"
            "1) def total(values)：用 sum 把列表加起来并 return，函数不读任何全局变量；\n"
            "2) def average(values)：先调 total(values) 拿到总分，再 return round(总分 / 个数, 1)；"
            "不许在 average 里再写一遍 sum；\n"
            "3) 用两组数据各调一次 average 并打印：第一组 [80, 90, 100]，第二组 [70, 60, 85]；\n"
            "4) 期望输出两行：90.0 / 71.7。\n"
            "starter 是反例：它把数据塞在全局变量里，还用 global 在函数内部改外面——先读懂它为什么"
            "危险，再整体改掉。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）；不许用 global；"
            "不许在函数里直接读写函数外定义的变量；不许把结果写死成字面量。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": (
            "# 反例：数据塞在全局变量里，函数偷偷改外面（这样写，第二份数据进来就会串味）\n"
            "scores = [80, 90, 100]\n"
            "total_value = 0\n"
            "\n"
            "\n"
            "def total():\n"
            "    global total_value          # 这一行就是病根：依赖没有写在参数上\n"
            "    total_value = sum(scores)\n"
            "    return total_value\n"
            "\n"
            "\n"
            "def average():\n"
            "    return round(total() / len(scores), 1)\n"
            "\n"
            "\n"
            "# 1) 改成 total(values) / average(values)：数据从参数进来，结果从返回值出去\n"
            "# 2) 用两组数据各调一次，打印两行平均分：第一组 [80, 90, 100]，第二组 [70, 60, 85]\n"
        ),
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行输出 90.0：average([80, 90, 100]) 靠参数算出来，不读全局变量",
            },
            {
                "name": "自检 2",
                "expect": "第二行输出 71.7：(70 + 60 + 85) / 3 保留一位小数",
            },
            {
                "name": "自检 3",
                "expect": "代码里搜不到 global：依赖只从参数进来、只从返回值出去",
            },
            {
                "name": "自检 4",
                "expect": "average 内部调用 total(values)，没有把 sum 再写一遍——一件事只在一个地方实现",
            },
        ],
        "required_patterns": [
            r"def\s+total\s*\(\s*values\s*\)",
            r"def\s+average\s*\(\s*values\s*\)",
            r"return\s+sum\s*\(",
            r"total\s*\(\s*values\s*\)",
            r"\bround\s*\(",
            r"print\s*\(\s*average\s*\(",
            r"\[\s*70\s*,\s*60\s*,\s*85\s*\]",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\bglobal\b",
        ],
        "expected_output": "90.0\n71.7",
    },
    # --- 课程 11：读懂报错，自己定位 -----------------------------------------
    {
        "lesson_code": "route_a.practice.debug",
        "code": "route_a.practice.debug.ex1",
        "title": "从最后一行往前读一条 Traceback",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「从最后一行往前读报错」这件事写成两个函数，证明你真读懂了那条线索。\n"
            "要做的事：\n"
            "1) error_kind(traceback_text)：取报错的最后一行，返回冒号前面的异常类型名"
            "（先 strip 去掉行尾空白）；\n"
            "2) error_line(traceback_text)：在每一行里找 line 这个词，把它后面那串数字取出来，"
            "用 int 转成整数返回（期望 12）；\n"
            "3) 打印 error_kind(traceback_text)，期望 KeyError；\n"
            "4) 打印 error_line(traceback_text)，期望 12。\n"
            "想清楚两件事再动手：为什么先看最后一行而不是第一行；冒号后面那段文字告诉你的是"
            "「缺了哪个键」，不是「哪一行出错」。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）；不许把 KeyError 或 12 "
            "直接写死成字面量返回，两个值都必须从 traceback_text 里解析出来。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "# 一条真实的报错原文（离线教材）：粘进代码里当线索\n"
            "traceback_text = (\n"
            "    'Traceback (most recent call last):\\n'\n"
            "    '  File \"report.py\", line 12, in <module>\\n'\n"
            "    '    print(scores[\"小刚\"])\\n'\n"
            "    \"KeyError: '小刚'\\n\"\n"
            ")\n"
            "\n"
            "\n"
            "def error_kind(traceback_text):\n"
            "    # 1) 取最后一行，再取冒号前面的类型名（去掉行尾空白）\n"
            "    pass\n"
            "\n"
            "\n"
            "def error_line(traceback_text):\n"
            "    # 2) 从 \"line 12\" 里取出出错行号，返回整数 12\n"
            "    pass\n"
            "\n"
            "\n"
            "# 3) 打印 error_kind(traceback_text)：期望 KeyError\n"
            "# 4) 打印 error_line(traceback_text)：期望 12\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 KeyError：异常类型来自最后一行冒号前那一段"},
            {
                "name": "自检 2",
                "expect": "第二行输出 12：行号来自 File 那一行的 line 12，而不是最后一行",
            },
            {
                "name": "自检 3",
                "expect": "把 traceback_text 换成 IndexError: list index out of range，第一行应变成 IndexError",
            },
            {
                "name": "自检 4",
                "expect": "两个函数都只依赖参数 traceback_text，没有读函数外的任何名字",
            },
        ],
        "required_patterns": [
            r"def\s+error_kind\s*\(",
            r"def\s+error_line\s*\(",
            r"\[-1\]",
            r"['\"]line['\"]",
            r"\bint\s*\(",
            r"\bstrip\s*\(",
            r"print\s*\(\s*error_kind",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
        ],
        "expected_output": "KeyError\n12",
    },
    {
        "lesson_code": "route_a.practice.debug",
        "code": "route_a.practice.debug.ex2",
        "title": "用 .get() 修掉 KeyError，并确认别处没改坏",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：先定位、再修，最后做回归——这是修一个 bug 的完整闭环，缺一步都不算修完。\n"
            "要做的事：\n"
            "1) 先把 starter 原样跑一遍：它会真的抛出一条 KeyError——从最后一行读出异常类型与"
            "缺的键，再往上一行读出出错的行；\n"
            "2) 把 score_of(scores, name) 里出错的那一行改成 scores.get(name, 0)：缺键时按 0 算，"
            "而不是让整份报告炸掉；\n"
            "3) 先打印一行定位结论，里面必须写出异常类型名 KeyError 与缺的键 小强，例如："
            "定位：异常类型 KeyError，缺的键是 小强；\n"
            "4) 遍历 names，逐行打印 score_of(scores, name)，期望在结论那一行之后是 90 / 85 / 0；\n"
            "5) 回归确认：小明和小红仍然是 90 和 85，说明正常路径没有被这次修复改坏。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）；不许用 try/except 把异常"
            "吞掉（那样等于把线索扔了）；不许用 global；不许把 90 / 85 / 0 写死成字面量打印。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "# 成绩表：键是学生名（离线教材）\n"
            'scores = {"小明": 90, "小红": 85}\n'
            "\n"
            "# 要遍历的名单里有一个不在表里\n"
            'names = ["小明", "小红", "小强"]\n'
            "\n"
            "\n"
            "\n"
            "def score_of(scores, name):\n"
            "    # 1) 先定位：原样跑一遍，出错的就是下面这一行（Traceback 最后一行会告诉你类型）\n"
            "    # 2) 再修：改成 scores.get(name, 0)，缺键时按 0 算\n"
            "    return scores[name]\n"
            "\n"
            "\n"
            "# 3) 先打印一行定位结论（必须写出异常类型 KeyError 与缺的键 小强）\n"
            "# 4) 再遍历 names，逐行打印 score_of(scores, name)\n"
            "for name in names:\n"
            "    print(score_of(scores, name))\n"
        ),
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行是定位结论：包含 KeyError 与缺的键 小强，说明先读懂了报错",
            },
            {"name": "自检 2", "expect": "第二行 90：小明的分数，正常路径没有被改坏"},
            {"name": "自检 3", "expect": "第三行 85：小红的分数"},
            {
                "name": "自检 4",
                "expect": "第四行 0：小强不在表里，.get(name, 0) 把「缺了就按 0 算」写成了代码",
            },
        ],
        "required_patterns": [
            r"\.get\s*\(\s*name\s*,\s*0\s*\)",
            r"for\s+name\s+in\s+names\b",
            r"print\s*\(\s*score_of\s*\(",
            r"def\s+score_of\s*\(",
            r"print\s*\(\s*f?['\"][^'\"]*KeyError",
            r"return\s+scores\.get\s*\(",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\bexcept\b",
            r"\bglobal\b",
        ],
        "expected_output": "定位：异常类型 KeyError，缺的键是 小强\n90\n85\n0",
    },
)


def upgrade() -> None:
    """Seed the two Sprint 9 lessons and their four exercises (idempotent)."""
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
            for lesson in LESSONS_V4
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
                "expected_output": exercise["expected_output"],
                "estimated_minutes": exercise["estimated_minutes"],
                "difficulty": exercise["difficulty"],
                "order_index": exercise["order_index"],
                "content_version": exercise["content_version"],
            }
            for exercise in EXERCISES_V4
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0013_sprint9_practice_content 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
