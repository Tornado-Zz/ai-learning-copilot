"""Versioned diagnostic question set v1 and scoring rule r1.

The answer key never leaves the server: answers are scored here, so the same
answers always reproduce the same domain_scores for the same rule version.
Distribution: 20 questions = 12 single choice + 5 code reading + 3 bug fixing,
covering all six route A domains (4 + 4 + 3 + 3 + 3 + 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DOMAIN_CODES: tuple[str, ...] = (
    "route_a.a1",
    "route_a.a2",
    "route_a.a3",
    "route_a.a4",
    "route_a.a5",
    "route_a.a6",
)

QUESTION_SET_VERSION = "v1"
RULE_VERSION = "r1"

CHOICES: tuple[str, ...] = ("A", "B", "C", "D")

# thresholds are applied in integer arithmetic: correct/total >= 85% => L2, >= 60% => L1
L2_MIN_PERCENT = 85
L1_MIN_PERCENT = 60

SINGLE_CHOICE = "single_choice"
CODE_READING = "code_reading"
BUG_FIX = "bug_fix"


@dataclass(frozen=True)
class Question:
    id: str
    skill_code: str
    kind: str
    prompt: str
    options: dict[str, str]
    answer: str
    # 逐题解析：只在批次明细出现，发卷视图（paper_questions）不投影该字段。
    explanation: str


QUESTIONS_V1: tuple[Question, ...] = (
    Question(
        id="q01",
        skill_code="route_a.a1",
        kind=SINGLE_CHOICE,
        prompt="执行 nums = [1, 2, 3, 4] 后，表达式 nums[1:3] 的结果是什么？",
        options={
            "A": "[1, 2]",
            "B": "[2, 3]",
            "C": "[2, 3, 4]",
            "D": "[1, 2, 3]",
        },
        answer="B",
        explanation=(
            "切片是左闭右开：起始索引 1 保留，结束索引 3 不包含，所以结果是 [2, 3]。错选 C 的人把右边界当成包含，这是最常见的切片偏差。"
        ),
    ),
    Question(
        id="q02",
        skill_code="route_a.a1",
        kind=SINGLE_CHOICE,
        prompt="d = {'a': 1}，执行 d.get('b', 0) 的结果是什么？",
        options={"A": "抛出 KeyError", "B": "None", "C": "0", "D": "'b'"},
        answer="C",
        explanation=(
            "get 的第二个参数是默认值，键不存在时直接返回它而不是报错，这正是 get 与下标取值的关键区别。选 A 的人混淆了 d['b'] 会抛 KeyError。"
        ),
    ),
    Question(
        id="q03",
        skill_code="route_a.a1",
        kind=SINGLE_CHOICE,
        prompt="用 open() 写完文件却没有 close()，最可能发生什么？",
        options={
            "A": "缓冲区内容可能没有真正落盘",
            "B": "程序一定会崩溃",
            "C": "文件会被自动删除",
            "D": "Python 会拒绝执行这段代码",
        },
        answer="A",
        explanation=(
            "不 close() 时 Python 的写缓冲可能还没刷到磁盘，进程正常退出只是碰巧兜底，异常退出就会丢数据。选 B 的人高估了后果，泄漏的是数据而非必然崩溃。"
        ),
    ),
    Question(
        id="q04",
        skill_code="route_a.a1",
        kind=SINGLE_CHOICE,
        prompt="with open(path, 'r', encoding='utf-8') as f: 这种写法的主要作用是：",
        options={
            "A": "自动创建不存在的文件",
            "B": "只读模式下不能读取内容",
            "C": "自动压缩文件内容",
            "D": "离开代码块时自动关闭文件",
        },
        answer="D",
        explanation=(
            "with 走上下文管理器协议，离开代码块（含异常）就自动调用 __exit__ 关文件。错选 A 的人误读模式：'r' 不会创建文件。"
        ),
    ),
    Question(
        id="q05",
        skill_code="route_a.a2",
        kind=CODE_READING,
        prompt="阅读代码：\ndef add(a, b=2):\n    return a + b\n\nprint(add(3))\n输出是什么？",
        options={"A": "3", "B": "5", "C": "报错", "D": "None"},
        answer="B",
        explanation=(
            "b 有默认值 2，只传 a=3 时 b 取缺省，返回 3+2=5；缺省参数在调用时才绑定。选 C 的人以为少传参数必然报错，忽略了带默认值的形参可以省略。"
        ),
    ),
    Question(
        id="q06",
        skill_code="route_a.a2",
        kind=CODE_READING,
        prompt="阅读代码：\ntotal = 0\nfor i in range(5):\n    if i == 3:\n        break\n    total += i\nprint(total)\n输出是什么？",
        options={"A": "10", "B": "6", "C": "3", "D": "7"},
        answer="C",
        explanation=(
            "i 取 0、1、2，到 3 时 break 直接跳出，4 不再累加，故 total=3。选 B 的人把 break 当 continue，多算了 3。"
        ),
    ),
    Question(
        id="q07",
        skill_code="route_a.a2",
        kind=CODE_READING,
        prompt="运行时报错 TypeError: 'NoneType' object is not subscriptable，最可能的原因是：",
        options={
            "A": "变量取到了 None，之后又按下标访问",
            "B": "缩进不一致",
            "C": "忘记写 import",
            "D": "文件名写错了",
        },
        answer="A",
        explanation=(
            "报错点名 NoneType，说明按下标的对象本身是 None，常见于函数忘写 return 或查库为空。选 B 的人把缩进问题当成运行时错误的原因。"
        ),
    ),
    Question(
        id="q08",
        skill_code="route_a.a2",
        kind=CODE_READING,
        prompt="阅读代码：\ndef outer():\n    count = 0\n    def inner():\n        count += 1\n        return count\n    return inner()\n\nprint(outer())\n运行结果是：",
        options={"A": "1", "B": "0", "C": "UnboundLocalError", "D": "None"},
        answer="C",
        explanation=(
            "inner 里对 count 有赋值，Python 就视为局部变量，未赋值先 += 只能抛 UnboundLocalError。选 A 的人漏了作用域规则。"
        ),
    ),
    Question(
        id="q09",
        skill_code="route_a.a3",
        kind=SINGLE_CHOICE,
        prompt="调用第三方 HTTP 接口时，为避免程序一直卡住，正确做法是：",
        options={
            "A": "忽略异常，无限重试",
            "B": "只用 http，不用 https",
            "C": "显式设置 timeout 并处理超时异常",
            "D": "把重试次数写成 100 次",
        },
        answer="C",
        explanation=(
            "不设 timeout，连接可能无限等待；正解是显式设 timeout 并捕获超时异常。选 A 的人把重试当超时防护，无上限重试只会更糟。"
        ),
    ),
    Question(
        id="q10",
        skill_code="route_a.a3",
        kind=SINGLE_CHOICE,
        prompt="resp = requests.get(url)，要判断资源不存在，应该检查什么？",
        options={
            "A": "resp.text 是否为空",
            "B": "resp.status_code == 404",
            "C": "resp.encoding 的取值",
            "D": "resp.headers 是否为空",
        },
        answer="B",
        explanation=(
            "状态码才是资源存不存在的标准信号，404 即不存在，应先看 resp.status_code。选 A 的人拿响应体空不空当依据，会误判 204 或错误页。"
        ),
    ),
    Question(
        id="q11",
        skill_code="route_a.a3",
        kind=CODE_READING,
        prompt="阅读代码：\nresp = requests.post(url, json=payload)\ndata = resp.json()\nprint(data['items'][0])\n若接口返回 500 且响应体为空，会发生什么？",
        options={
            "A": "正常打印空列表",
            "B": "requests 自动重试",
            "C": "打印 None",
            "D": "抛出异常，因为响应体不是合法 JSON",
        },
        answer="D",
        explanation=(
            "500 加空响应体时 resp.json() 解析失败，直接抛 JSONDecodeError，后面的取值不会执行。选 C 的人以为它会安静返回 None。"
        ),
    ),
    Question(
        id="q12",
        skill_code="route_a.a4",
        kind=SINGLE_CHOICE,
        prompt="关于大模型的 token，下列说法正确的是：",
        options={
            "A": "1 个 token 恒等于 1 个字符",
            "B": "token 是模型切分文本的最小单位，上下文上限以 token 计",
            "C": "token 只在流式返回时存在",
            "D": "token 由用户在请求里自定义",
        },
        answer="B",
        explanation=(
            "token 是分词器切出的最小单位，一个汉字常占 1 到 2 个 token，上下文上限同样按 token 算。选 A 的人当成字符数，估算会差出好几倍。"
        ),
    ),
    Question(
        id="q13",
        skill_code="route_a.a4",
        kind=SINGLE_CHOICE,
        prompt="流式返回最主要的收益是：",
        options={
            "A": "首个片段更快显示，等待感更短",
            "B": "计费一定更低",
            "C": "模型的回答一定更准确",
            "D": "不再需要处理超时",
        },
        answer="A",
        explanation=(
            "流式让第一个片段到达就开始渲染，首字延迟明显下降，但总时长与费用不变。选 B 的人把等待感更短误当成计费更低，token 数其实没有减少。"
        ),
    ),
    Question(
        id="q14",
        skill_code="route_a.a4",
        kind=BUG_FIX,
        prompt="改错：下面函数想粗估一段中文文本的 token 数，但有 bug：\ndef estimate(text):\n    return len(text.split(' '))\n对中文文本它会低估，最小修正是：",
        options={
            "A": "把 split(' ') 改成 split()",
            "B": "中文没有空格分隔，改用按字符数近似（例如 len(text) / 1.5）",
            "C": "把 len 改成 count",
            "D": "没有 bug，不用改",
        },
        answer="B",
        explanation=(
            "中文几乎没空格，split(' ') 只切出 1 段，应按字符数近似（一个汉字约 1 到 2 个 token）。选 A 的 split() 对中文无效。"
        ),
    ),
    Question(
        id="q15",
        skill_code="route_a.a5",
        kind=SINGLE_CHOICE,
        prompt="把长文档切分成片段（chunk）时，最影响检索效果的是：",
        options={
            "A": "片段数量越多越好",
            "B": "片段过大引入噪声、过小丢失语义，需要合适的粒度与重叠",
            "C": "必须严格按行切分",
            "D": "必须只处理英文文档",
        },
        answer="B",
        explanation=(
            "片段过大稀释相关信号、过小切断语义，需要合适粒度加少量重叠，召回与上下文才都能用。选 A 的人以为越多越好，实际会挤爆上下文并引入噪声。"
        ),
    ),
    Question(
        id="q16",
        skill_code="route_a.a5",
        kind=SINGLE_CHOICE,
        prompt="把检索到的片段拼进提示词时，正确的做法是：",
        options={
            "A": "把所有片段都拼进去，越多越好",
            "B": "不标注片段来源",
            "C": "片段直接放在系统提示之后，不限制总长度",
            "D": "按相关度排序、控制总长度，并标注片段来源",
        },
        answer="D",
        explanation=(
            "拼提示词要按相关度取前几段、控制总长度防止超出上下文，并标注来源便于核对与引用。选 A 的人把所有片段都塞进去，既超长又让模型被无关内容带偏。"
        ),
    ),
    Question(
        id="q17",
        skill_code="route_a.a5",
        kind=BUG_FIX,
        prompt="改错：下面代码检索后没有把文档拼进提示词：\ndocs = retriever.search(query)\nprompt = '请回答：' + query\n应该改哪一行？",
        options={
            "A": "prompt 改为先拼参考资料，再拼问题",
            "B": "删除 docs 变量",
            "C": "把 query 换成英文",
            "D": "把 search 改成 print",
        },
        answer="A",
        explanation=(
            "检索到的 docs 完全没进 prompt，模型只能凭空作答，正确做法是把参考资料拼在问题前面。选 B 的删掉 docs 只是让遗漏更彻底，问题依然存在。"
        ),
    ),
    Question(
        id="q18",
        skill_code="route_a.a6",
        kind=SINGLE_CHOICE,
        prompt="一个可运行、可展示的最小 AI 项目，最重要的交付物是：",
        options={
            "A": "完整的商业计划书",
            "B": "能从命令行或页面跑通、有输入输出与 README 说明的最小闭环",
            "C": "尽量多的功能点",
            "D": "只写设计文档",
        },
        answer="B",
        explanation=(
            "最小可运行闭环能被别人跑起来、看到输入输出，才算交付；功能数量与文档厚度都替代不了能跑。选 C 的人用功能点数量衡量进展，结果一个都没跑通。"
        ),
    ),
    Question(
        id="q19",
        skill_code="route_a.a6",
        kind=SINGLE_CHOICE,
        prompt="把项目交给别人复现时，接口密钥应该放在哪里？",
        options={
            "A": ".env 环境变量里，且不提交到仓库",
            "B": "硬编码在源码里",
            "C": "写在 README 里",
            "D": "写进前端代码",
        },
        answer="A",
        explanation=(
            "密钥放 .env 环境变量并写进 .gitignore，仓库只留 .env.example。选 B 的硬编码会永久留在 git 历史里，事后删也清不干净。"
        ),
    ),
    Question(
        id="q20",
        skill_code="route_a.a6",
        kind=BUG_FIX,
        prompt="改错：下面代码调用外部接口时没有任何异常处理：\ndata = requests.get(url).json()\n最小修正是：",
        options={
            "A": "去掉 .json() 即可",
            "B": "加一行 print 输出",
            "C": "加 try/except 捕获 requests 异常，并设置 timeout",
            "D": "把 get 改成 post",
        },
        answer="C",
        explanation=(
            "网络调用可能超时或返回非 JSON，须 try/except 捕获 requests 异常并设 timeout。选 A 去 .json() 只是挪走解析错误。"
        ),
    ),
)

QUESTION_INDEX: dict[str, Question] = {question.id: question for question in QUESTIONS_V1}
TOTAL_QUESTIONS = len(QUESTIONS_V1)


@dataclass(frozen=True)
class DomainScore:
    skill_code: str
    correct: int
    total: int
    rate: float
    level: int
    state: str

    def as_json(self) -> dict[str, object]:
        return {
            "correct": self.correct,
            "total": self.total,
            "rate": self.rate,
            "level": self.level,
            "state": self.state,
        }

    def as_row(self) -> dict[str, object]:
        return {
            "skill_code": self.skill_code,
            "correct": self.correct,
            "total": self.total,
            "rate": self.rate,
            "level": self.level,
            "state": self.state,
        }


@dataclass(frozen=True)
class ScoreResult:
    total_correct: int
    total_questions: int
    domains: tuple[DomainScore, ...]


def level_for(correct: int, total: int) -> int:
    """Diagnostic grants at most L2: >= 85% -> 2, >= 60% -> 1, otherwise 0."""
    if total <= 0 or correct < 0 or correct > total:
        raise ValueError(f"invalid score {correct}/{total}")
    if correct * 100 >= L2_MIN_PERCENT * total:
        return 2
    if correct * 100 >= L1_MIN_PERCENT * total:
        return 1
    return 0


def state_for(level: int) -> str:
    """A diagnostic row is either established or assessed below the L1 threshold."""
    return "established" if level >= 1 else "assessed_below_threshold"


def question_ids() -> tuple[str, ...]:
    return tuple(question.id for question in QUESTIONS_V1)


def paper_questions() -> tuple[dict[str, object], ...]:
    """Prompt-and-options view of the one question set: no answer, no explanation.

    Projected from QUESTIONS_V1 field by field so no second question definition
    exists; the answer key and the per-question explanation never reach a paper.
    """
    return tuple(
        {
            "id": question.id,
            "order": order,
            "type": question.kind,
            "prompt": question.prompt,
            "options": [{"key": key, "text": text} for key, text in question.options.items()],
            "domain_code": question.skill_code,
        }
        for order, question in enumerate(QUESTIONS_V1, start=1)
    )


def kind_distribution() -> dict[str, int]:
    counts: dict[str, int] = {}
    for question in QUESTIONS_V1:
        counts[question.kind] = counts.get(question.kind, 0) + 1
    return counts


def score_answers(choices: Mapping[str, str]) -> ScoreResult:
    """Deterministic scoring for rule r1: rate = correct / total per domain."""
    correct_by_domain: dict[str, int] = {code: 0 for code in DOMAIN_CODES}
    total_by_domain: dict[str, int] = {code: 0 for code in DOMAIN_CODES}
    total_correct = 0
    for question in QUESTIONS_V1:
        total_by_domain[question.skill_code] += 1
        if choices[question.id] == question.answer:
            correct_by_domain[question.skill_code] += 1
            total_correct += 1

    domains: list[DomainScore] = []
    for code in DOMAIN_CODES:
        correct = correct_by_domain[code]
        total = total_by_domain[code]
        level = level_for(correct, total)
        domains.append(
            DomainScore(
                skill_code=code,
                correct=correct,
                total=total,
                rate=round(correct / total, 2),
                level=level,
                state=state_for(level),
            )
        )
    return ScoreResult(
        total_correct=total_correct,
        total_questions=TOTAL_QUESTIONS,
        domains=tuple(domains),
    )
