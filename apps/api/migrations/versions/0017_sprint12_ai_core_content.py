"""Sprint 12 内容：给 a3「API」与 a4「LLM」各补一节核心课，以及每课两道练习

Revision ID: 0017_sprint12_ai_core_content
Revises: 0016_sprint11_return_rule
Create Date: 2026-11-05 00:00:00+00:00

六域覆盖现状：a1 Python 基础 5 节、a2 编程实践 2 节，而 a3（API）与 a4（LLM）各只有
1 节——「学 AI」最核心的两个域反而最薄。本迁移补上 route_a.api.errors（30 分钟，读懂
状态码）与 route_a.llm.prompt（30 分钟，提示词的四个零件）两节课，以及每课两道练习
（共 4 道）。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 11 节课、22 道练习与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习都只用「本地存下来的响应文本 / 本地字符串」当教材，
学习与判题都不需要联网、不需要密钥；4 道练习的 forbidden_patterns 都把「导入网络库」
与「真实地址字面量」写成正则禁止项，静态判题会直接拒掉联网写法。

order_index 取 12 / 13：lessons.order_index 上已有 1-11（0003 的 5 节 + 0011/0012 的
4 节 + 0013 的 a2 两节），本迁移只发 INSERT、不改写既有行，因此新课只能接在后面；
stage 仍是 a3 / a4 的 3 / 4，列表接口按 (stage, order_index) 排序时它们紧跟在同域的
既有课之后（a3: api.json -> api.errors，a4: llm.messages -> llm.prompt）。

requirement_labels 与 required_patterns **逐条一一对应、顺序相同、条数相等**（0014 建立
的契约）：第 N 条标签就是第 N 条规则，判题失败时学习者看到的是那句中文要求。本迁移的
4 道题是按这个口径新写的，不是事后补标签。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0017_sprint12_ai_core_content"
down_revision: str | None = "0016_sprint11_return_rule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库生成
# （lessons / exercises 用 identity，真实 id 早已过了 1109 / 26），硬编码会在另一个库上
# 指向错误的行。这条口径与 0003 / 0004 / 0011 / 0012 / 0013 完全一致。
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
# 课程 12：接口出错时，怎么读懂状态码（a3）
# ---------------------------------------------------------------------------

STATUS_EXAMPLE_CODE = """import json

# 三份「离线存下来的响应」：状态码 + 响应体原文（真调用接口时收到的就是这两样）
responses = [
    (200, '{"code": "ok", "data": {"lesson": "读懂状态码"}}'),
    (404, '{"code": "lesson_not_found", "message": "这节课不存在"}'),
    (503, '{"code": "upstream_busy", "message": "上游暂时不可用", "details": {"retry_after": "3"}}'),
]


def blame(status):
    # 谁的责任：4xx 是我发来的东西有问题，5xx 是对方自己出了问题
    if 400 <= status < 500:
        return "我的问题"
    if 500 <= status < 600:
        return "对方的问题"
    return "正常"


def retryable(status):
    # 要不要重试：换个时间点再问一遍，结果可能不同才值得重试
    return status in (408, 429, 503)


for status, body in responses:
    payload = json.loads(body)
    print(f"{status} {blame(status)} 重试={retryable(status)} code={payload['code']}")
"""

STATUS_EXAMPLE_OUTPUT = (
    "200 正常 重试=False code=ok\n"
    "404 我的问题 重试=False code=lesson_not_found\n"
    "503 对方的问题 重试=True code=upstream_busy"
)

# ---------------------------------------------------------------------------
# 课程 13：把要求说清楚：提示词的四个零件（a4）
# ---------------------------------------------------------------------------

PROMPT_EXAMPLE_CODE = r"""PARTS = ["角色", "任务", "约束", "输出格式"]


def build_prompt(role, task, rules, fmt):
    # 四个零件各占一行：角色、任务、约束、输出格式
    lines = [
        f"角色：{role}",
        f"任务：{task}",
        "约束：" + "；".join(rules),
        f"输出格式：{fmt}",
    ]
    return "\n".join(lines)


def missing_parts(text):
    # 四件零件里，哪几件在这条提示词里根本没出现
    return [name for name in PARTS if name not in text]


full = build_prompt(
    role="你是一名严格的作业批改员",
    task="判断回答有没有讲清楚「返回」",
    rules=["只回一个词", "不要解释"],
    fmt="通过 / 不通过",
)
print(full)
print(missing_parts("角色：助教。任务：帮我看看这段回答写得怎么样"))
"""

PROMPT_EXAMPLE_OUTPUT = (
    "角色：你是一名严格的作业批改员\n"
    "任务：判断回答有没有讲清楚「返回」\n"
    "约束：只回一个词；不要解释\n"
    "输出格式：通过 / 不通过\n"
    "['约束', '输出格式']"
)

# ---------------------------------------------------------------------------
# 4 道练习的起始代码（只给骨架与说明，判题时注释与 docstring 会被剥离）
# ---------------------------------------------------------------------------

ERRORS_EX1_STARTER = """# 三份离线存下来的响应：状态码 + 响应体原文（不联网，清单直接写在代码里）
responses = [
    (200, '{"code": "ok"}'),
    (404, '{"code": "lesson_not_found"}'),
    (503, '{"code": "upstream_busy"}'),
]


def blame(status):
    # 1) 400 到 499 是请求方的问题，500 到 599 是服务端的问题，其余算正常
    pass


def retryable(status):
    # 2) 只有 408 / 429 / 503 该重试：换个时间点再问，结果可能不同
    pass


# 3) 用 for 遍历 responses，按「状态码 责任 重试=False」的格式打印三行
"""

ERRORS_EX2_STARTER = """import json

# 一份离线保存的「出错响应」原文：真调用接口时会收到这样一段文本（这里不联网）
ERROR_TEXT = '{"code": "rate_limited", "message": "请求太频繁", "details": {"retry_after": "5"}}'


def read_code(text):
    # 1) 用 json.loads 解析 text，然后 return 其中的 code
    pass


def wait_seconds(status, retry_after):
    # 2) status 是 429 或 503 时 return int(retry_after)，其余 return 0
    pass


# 3) 打印三行：错误码、说明、等待秒数（说明用 get 读，缺键时打印「没有说明」）
"""

PROMPT_EX1_STARTER = """PARTS = ["角色", "任务", "约束", "输出格式"]


def build_prompt(role, task, rules, fmt):
    # 1) 拼出四行（角色 / 任务 / 约束 / 输出格式），用换行符连起来，然后 return
    pass


def missing_parts(text):
    # 2) 返回 PARTS 里没有出现在 text 中的那些零件名
    pass


# 3) 拼一条完整提示词并打印
# 4) 再打印 missing_parts 对「角色：助教。任务：帮我看看这段回答写得怎么样」的检查结果
"""

PROMPT_EX2_STARTER = """tasks = ["抽取", "判定", "改写"]


def pick_temperature(kind):
    # 1) 「抽取」「判定」返回 0.0，「改写」返回 0.7，其余返回 0.3
    pass


def few_shot_cost(count, tokens_each):
    # 2) 每个示例每次请求都要重新带上，所以代价是乘法
    pass


# 3) 用 for 遍历 tasks，按「抽取 温度=0.0」的格式打印三行
# 4) 再用 few_shot_cost(3, 80) 算出总花费，打印「三个示例每次多花 240 token」
"""

LESSONS_V5: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.api.errors",
        "skill_code": "route_a.a3",
        "stage": 3,
        "title": "接口出错时，怎么读懂状态码",
        "summary": "状态码的第一位数字在划分责任：4xx 是我的问题、5xx 是对方的问题；响应体分 code / message / details 三段；只有 408 / 429 / 503 值得等一会儿再试",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 12,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "拿到一个出错的状态码，能立刻答出三个问题：这是谁的问题、要不要重试、下一次该等"
                "多久；能把错误响应体读成 code / message / details 三段；知道把错误原样吞掉为什么"
                "是最坏的处理。"
            ),
            "explanation": [
                (
                    "状态码的第一位数字就在划分责任：4xx 是「你发来的东西有问题」，5xx 是「服务端"
                    "自己出了问题」。这条分界线的用处不在分类本身，而在决定下一步动作——4xx 要改"
                    "请求（参数、地址、凭证），你原样再发一百次结果都一样；5xx 与请求内容无关，等"
                    "一会儿或者换个时间点再发，结果可能不同。把两者混成一句「调用失败」，下一步就"
                    "只能靠猜。"
                ),
                (
                    "出错时服务端通常会回一段结构化文本，常见形状是三段：code 给机器读（稳定、可"
                    "枚举，用来写分支）、message 给人读（一句说明，措辞随时会改）、details 给定位"
                    "用（哪个字段错了、还剩多少额度、多久之后可以重试）。这三段要分开用：拿 code "
                    "写 if，拿 message 给人看，拿 details 决定重试的等待时间。混着用就会写出「靠 "
                    "message 里有没有某个词来判断错误类型」这种一改文案就静默失效的代码。"
                ),
                (
                    "判断该不该重试，标准只有一句：重试不改变请求内容，只改变时间点，所以只有"
                    "「外部条件可能变」的错误才值得重试。408（请求超时）、429（请求太频繁）、503"
                    "（服务暂时不可用）属于这一类；400（请求本身不合法）、401（没带凭证）、404（资源"
                    "不存在）属于另一类——同样的东西再发一次，服务端凭什么给你不同的答案？对第二类"
                    "重试，除了把日志刷满、把配额烧光，什么都不会发生。"
                ),
                (
                    "等多久也有讲究。服务端给了 Retry-After，就按它说的等：那是它自己的恢复预期，"
                    "比你的猜测准。没给就退避：第一次等 1 秒、第二次 2 秒、第三次 4 秒，每次翻倍，"
                    "并加一点随机抖动，免得所有客户端在同一毫秒一起回来，把还没站稳的服务再压垮"
                    "一次。退避一定要有上限：最多等几十秒、最多试三五次，然后老老实实报错。没有上限"
                    "的重试不是「更可靠」，是把一次故障拖成一次事故。"
                ),
                (
                    "最坏的处理是把它吞掉：错误分支里一句 pass，或者兜住之后 return None。状态码"
                    "带着两样东西——「谁的错」和「能不能补救」，吞掉等于当场把这两样扔了：用户看到"
                    "一片空白，日志里干干净净，几小时后才有人发现数据没写进去，而这时已经无从知道"
                    "当初坏在哪一步。错误不是噪音，它是唯一能告诉你「哪一层坏了」的线索。处理不了"
                    "可以，但必须让它可见：往上抛、记日志、给用户一句人话，三件事至少做一件。"
                ),
                (
                    "这件事在离线环境里完全练得出来：把真实调用时的两样东西——状态码与响应体原文"
                    "——存成文本当教材，再写两个纯函数：blame(status) 回答「谁的问题」，"
                    "retryable(status) 回答「要不要重试」。两个函数都只依赖参数、都返回结果，于是"
                    "你可以用一组状态码逐个断言，把「责任划分」从感觉变成可自测的代码。真接上网络"
                    "时，你只是把这两个函数的输入从常量换成了响应，判断逻辑一行都不用改。"
                ),
            ],
            "example": {
                "title": "三份离线响应：责任、重试、错误码，一行说清",
                "code": STATUS_EXAMPLE_CODE,
                "output": STATUS_EXAMPLE_OUTPUT,
                "notes": [
                    "blame 只认 4xx / 5xx 两段：责任分清了，下一步动作才有依据。",
                    "retryable 只列出 408 / 429 / 503：这三个的共同点是「换个时间点可能不一样」。",
                    "错误响应体里的 code 才是写分支的依据，message 只给人看。",
                    "两个函数都是纯函数：换一组状态码就能自测，不必真的去调坏一次接口。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把所有非 2xx 的响应都当成同一种「网络错误」",
                    "why": (
                        "责任没分清，下一步动作只能靠猜：该改请求的地方在等，该等的地方在反复改"
                        "代码。"
                    ),
                    "fix": "按第一位数字分开：4xx 去改请求（参数、地址、凭证），5xx 去等或重试。",
                },
                {
                    "mistake": "拿 message 里的文字判断错误类型，比如搜「超额」两个字",
                    "why": "message 是给人读的，措辞随时会改；文案一改，if 分支就静默失效。",
                    "fix": "用 code 写分支，message 只用于展示，details 只用于决定等多久、错在哪。",
                },
                {
                    "mistake": "对 400 / 401 / 404 也写 while 循环反复重试",
                    "why": (
                        "这几类的成因在请求本身，重试不改变请求，只会把日志和配额刷满，还可能触发"
                        "风控。"
                    ),
                    "fix": "只有 408 / 429 / 503 才进重试分支，并且带次数上限与退避上限。",
                },
                {
                    "mistake": "错误分支里一句 pass 吞掉，或者兜住之后 return None",
                    "why": (
                        "「谁的错」和「能不能补救」的信息当场消失：用户看到空白，日志干净，事后"
                        "无从定位。"
                    ),
                    "fix": "处理不了就往上抛；必须兜住时记一条带 code 的日志，并给用户一句人话。",
                },
            ],
            "self_check": [
                {
                    "question": "看到一个 404，第一件事是确认这是谁的问题，还是直接重试？",
                    "answer": (
                        "先确认责任：404 是 4xx，请求方的问题——先检查地址或资源标识是不是错的、"
                        "资源是不是被删了，重试不会让不存在的资源出现。"
                    ),
                },
                {
                    "question": "错误响应体的三段各自该用来做什么？",
                    "answer": (
                        "code 写分支（稳定可枚举）、message 给人看（一句说明）、details 给定位用"
                        "（哪个字段错了、多久后可以重试）。"
                    ),
                },
                {
                    "question": "为什么只有 408 / 429 / 503 值得自动重试？",
                    "answer": (
                        "因为重试只改变时间点、不改变请求：这三类的成因在外部条件上，等一会儿可能"
                        "就好了；其余错误再发一次，结果只会一样。"
                    ),
                },
                {
                    "question": "吞掉错误为什么比直接报错更糟？",
                    "answer": (
                        "报错至少留下了线索和现场；吞掉会让故障在无人知晓的情况下扩散，事后连"
                        "「坏在哪一层」都无法回答。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.llm.prompt",
        "skill_code": "route_a.a4",
        "stage": 4,
        "title": "把要求说清楚：提示词的四个零件",
        "summary": "角色 / 任务 / 约束 / 输出格式四件套写全，模糊要求才会换成模糊输出；few-shot 换来稳定形状但要付 token 与维护成本，抽取与判定这类任务用低温",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 13,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "能说出提示词的四个零件各自解决什么问题，并把一句「帮我看看」改写成四件齐全的"
                "提示词；知道为什么模糊要求只会得到模糊输出；知道 few-shot 示例的作用与代价；知道"
                "抽取、判定这类确定性任务该用低温，以及「让它自己决定输出格式」为什么通常不是好主意。"
            ),
            "explanation": [
                (
                    "提示词可以拆成四个零件：角色（谁在回答）、任务（做什么）、约束（边界与禁止项）、"
                    "输出格式（交回来什么形状）。分开写不是为了凑格式，而是因为这四件事各有各的错法："
                    "没写角色，模型会用「什么都不知道的助手」的口吻回答；没写任务，它会替你猜一个；"
                    "没写约束，它会把边界往外扩；没写输出格式，它会给你一段读得懂却接不进程序的散文。"
                    "四件缺哪一件，就在哪一件上失控。"
                ),
                (
                    "为什么模糊的要求只能得到模糊的输出？因为模型只能按你给的约束去补全其余部分，"
                    "而没说的部分它每次补的可能都不一样。你说「帮我看看这段回答写得怎么样」，它就"
                    "自己决定看什么：可能评语法、可能评逻辑、可能顺手改写一遍。这不是它不听话，是"
                    "这句话本身允许了太多种解释。把要求写清楚，本质上是把「由它决定」的那部分收回"
                    "来，由你自己决定。"
                ),
                (
                    "输出格式尤其不能交给模型决定。程序要用的东西必须形状固定：一行一条、三个键、"
                    "只回一个词。让它自己决定格式，你会得到「有时候是列表、有时候是编号段落、有时候"
                    "前面还带一句客套话」的结果，下游的解析代码就得为每一种意外写法写兜底——而这些"
                    "兜底本来一句话就能避免。定格式的时候顺手说清边界：读不出来怎么办（回「无法判断」"
                    "）、不要解释、不要重复我的问题。这些约束都是给下游省事。"
                ),
                (
                    "示例（few-shot）是把格式与判断标准一次讲清的最有效手段：给两三个「输入 -> 期望"
                    "输出」的样例，比描述十句格式规则更管用。代价有两条：token，每次请求都要把示例"
                    "带上，示例越长、调用越贵；维护，示例错了模型会稳定地学错——它比你的文字描述更"
                    "有说服力。所以示例要短、要覆盖边界（一个正常的、一个看着正常其实不行的），两三"
                    "个通常就够。不要靠堆二十个示例求「更保险」：示例之间互相矛盾时，模型只会挑一个"
                    "照做，而你还要维护二十份正确性。"
                ),
                (
                    "温度控制「每次回答有多不一样」。抽取字段、判定通过与否这类任务要的是稳定可复现："
                    "同一段输入跑两次，答案必须一样，否则下游没法用——这类任务用低温（0 或 0.1）。"
                    "改写、起标题、头脑风暴要的是多样，温度可以高一些。但要说清楚：低温不等于确定。"
                    "模型版本、服务端实现、上下文长度都会让结果变化，所以真正重要的结论不能只靠「温度"
                    "设成 0 就稳了」，还要在程序侧再校验一遍：长度、枚举值、关键字段是否存在。"
                ),
                (
                    "提示词工程也能被测试：把提示词当字符串拼，四个零件就是四个函数参数；再写一个"
                    "missing_parts(text) 找出缺了哪个零件——一句「帮我看看」在这套检查下会立刻暴露"
                    "缺两件。这一步不需要调用任何模型：能不能把要求说清楚，和你有没有模型可以调，是"
                    "两件独立的事。先把话说清楚，再谈模型好不好用。"
                ),
            ],
            "example": {
                "title": "四个零件拼成一条提示词，再用一个纯函数查出缺口",
                "code": PROMPT_EXAMPLE_CODE,
                "output": PROMPT_EXAMPLE_OUTPUT,
                "notes": [
                    "角色 / 任务 / 约束 / 输出格式各占一行：四行都在，读的人才知道边界在哪。",
                    "约束用「；」串起来：多条要求排成一行，比写成一整段更容易核对少没少。",
                    "missing_parts 只做一件事：拿四个零件名去原文里找，返回缺的那些。",
                    "整个文件不调用任何模型：把话说清楚这一步，离线就能练。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把一句话丢给模型：「帮我看看这段回答」",
                    "why": (
                        "任务、约束、输出格式全是空白，模型只能每次自己补，于是同一段输入得到"
                        "不同形状的结果。"
                    ),
                    "fix": "按四件套补齐：谁在回答、要做什么、不许做什么、交回什么形状。",
                },
                {
                    "mistake": "让它自己决定输出格式",
                    "why": (
                        "下游要么为每种意外写法写兜底，要么解析失败——这是把不确定性搬进了代码。"
                    ),
                    "fix": "自己定形状（一行一条 / 三个键 / 只回一个词），并规定读不出来时回什么。",
                },
                {
                    "mistake": "few-shot 塞进二十个示例求「更保险」",
                    "why": (
                        "token 每次都要付；示例互相矛盾时模型只会挑一个照做，你还要维护二十份"
                        "正确性。"
                    ),
                    "fix": "两三个示例，一个正常、一个看着正常其实不行，覆盖边界即可。",
                },
                {
                    "mistake": "抽取任务用默认的高温，结果每次不一样就怪模型不稳定",
                    "why": "抽取与判定要的是可复现，高温正是在制造不必要的随机性。",
                    "fix": "确定性任务用低温（0 或 0.1），并对关键字段做程序侧再校验。",
                },
            ],
            "self_check": [
                {
                    "question": "四个零件分别解决什么问题？",
                    "answer": (
                        "角色定口吻与立场、任务定做什么、约束定边界与禁止项、输出格式定交回来的"
                        "形状；四件各有各的错法，缺哪件就在哪件上失控。"
                    ),
                },
                {
                    "question": "为什么模糊要求会得到模糊输出？",
                    "answer": (
                        "没写的部分由模型补全，而补全方式每次可能不同；只有把这些决定权收回来，"
                        "结果才稳定。"
                    ),
                },
                {
                    "question": "few-shot 的两条代价是什么？",
                    "answer": (
                        "token（每次请求都要带上示例）与维护（示例错了模型会稳定地学错）；示例"
                        "多了还会互相矛盾。"
                    ),
                },
                {
                    "question": "温度设成 0 就等于结果一定相同吗？",
                    "answer": (
                        "不等于：模型版本、服务端实现与上下文长度都会影响结果，关键结论还要在"
                        "程序侧再校验一遍。"
                    ),
                },
            ],
        },
    },
)

EXERCISES_V5: tuple[dict[str, object], ...] = (
    # --- 课程 12：接口出错时，怎么读懂状态码 ---------------------------------
    {
        "lesson_code": "route_a.api.errors",
        "code": "route_a.api.errors.ex1",
        "title": "按状态码分责任、判是否该重试",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「谁的问题」和「要不要重试」写成两个纯函数，再用一个循环打印每条响应的结论。\n"
            "要做的事：\n"
            "1) blame(status)：400 到 499 返回「我的问题」，500 到 599 返回「对方的问题」，"
            "其余返回「正常」；\n"
            "2) retryable(status)：只有当状态码是 408、429、503 之一时返回 True，其余返回 False；\n"
            "3) 用 for 遍历 responses 里的三组「状态码, 响应体」，按「状态码 责任 重试=…」的格式"
            "打印一行；\n"
            "4) 期望输出三行：200 正常 重试=False / 404 我的问题 重试=False / "
            "503 对方的问题 重试=True。\n"
            "注意：400、401、404 返回 True 就是错的答案——它们再发一百次，结果也一样。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": ERRORS_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行输出 200 正常 重试=False：2xx 不是谁的错，也不用重试",
            },
            {
                "name": "自检 2",
                "expect": "第二行输出 404 我的问题 重试=False：4xx 属于请求方，重试没有意义",
            },
            {
                "name": "自检 3",
                "expect": "第三行输出 503 对方的问题 重试=True：5xx 里服务暂时不可用，值得等一会儿",
            },
            {
                "name": "自检 4",
                "expect": "把响应清单换成 429 / 400 再跑，两行结论跟着变——说明不是把三行写死的",
            },
        ],
        "required_patterns": [
            r"def\s+blame\s*\(",
            r"def\s+retryable\s*\(",
            r"400\s*<=\s*status",
            r"500\s*<=\s*status",
            r"return\s+",
            r"408[\s\S]*429[\s\S]*503",
            r"for\s+\w+(?:\s*,\s*\w+)*\s+in\s+",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 blame 判断这是谁的问题",
            "定义函数 retryable 判断要不要重试",
            "用 400 作为请求方错误的判断下界",
            "用 500 作为服务端错误的判断下界",
            "用 return 把结论交回调用方",
            "把 408、429、503 三个可重试状态码列在一起",
            "用 for 遍历响应清单",
            "用 print 把每条结论打印出来",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "200 正常 重试=False\n404 我的问题 重试=False\n503 对方的问题 重试=True"
        ),
    },
    {
        "lesson_code": "route_a.api.errors",
        "code": "route_a.api.errors.ex2",
        "title": "把错误响应体读成 code / message / details",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一段离线保存的出错响应原文读成三样东西（错误码、说明、该等几秒），并且不用 "
            "except 把它吞掉。\n"
            "要做的事：\n"
            "1) 导入 json，用 json.loads 把 ERROR_TEXT 解析成字典；\n"
            "2) read_code(text)：解析 text，返回其中 code 的值；\n"
            "3) wait_seconds(status, retry_after)：status 是 429 或 503 时返回 int(retry_after)，"
            "其余返回 0；\n"
            "4) 打印三行：错误码：… / 说明：… / 等待：… 秒；说明用 get 读取，缺这个键时打印"
            "「没有说明」；\n"
            "5) 期望输出三行：错误码：rate_limited / 说明：请求太频繁 / 等待：5 秒。\n"
            "注意：等待的秒数必须从 details 里取出来再转成整数，不许直接写成 5。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）；不许用 except 把错误"
            "原样吞掉。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": ERRORS_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行输出 错误码：rate_limited：code 才是写分支的依据",
            },
            {
                "name": "自检 2",
                "expect": "第二行输出 说明：请求太频繁：message 由 get 读出来，缺键时是「没有说明」",
            },
            {
                "name": "自检 3",
                "expect": "第三行输出 等待：5 秒：5 来自 details 里的 retry_after，不是写死的",
            },
            {
                "name": "自检 4",
                "expect": "把 ERROR_TEXT 换成 400 且不带 details 的一份响应，等待那行必须是 0 秒",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r"json\.loads\s*\(",
            r"def\s+read_code\s*\(",
            r"def\s+wait_seconds\s*\(",
            r"return\s+",
            r"\.get\s*\(",
            r"int\s*\(",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "导入 json 模块",
            "用 json.loads 把响应原文解析成字典",
            "定义函数 read_code 取出错误码",
            "定义函数 wait_seconds 算出该等几秒",
            "用 return 把取到的值交回调用方",
            "用 get 读说明，缺键时不报错",
            "用 int 把等待秒数的文本转成整数",
            "用 print 打印错误码、说明与等待秒数",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\bexcept\b",
            r"return\s+5\b",
        ],
        "expected_output": "错误码：rate_limited\n说明：请求太频繁\n等待：5 秒",
    },
    # --- 课程 13：把要求说清楚：提示词的四个零件 -----------------------------
    {
        "lesson_code": "route_a.llm.prompt",
        "code": "route_a.llm.prompt.ex1",
        "title": "用四个零件拼出一条提示词",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「角色 / 任务 / 约束 / 输出格式」四件零件拼成一条提示词，再用一个纯函数查出"
            "缺了哪些零件。\n"
            "要做的事：\n"
            "1) build_prompt(role, task, rules, fmt)：按「角色：… / 任务：… / 约束：… / "
            "输出格式：…」四行拼成一条文本并返回，行与行之间用换行符；约束这一行要把 rules 里的"
            "多条要求用「；」连起来；\n"
            "2) missing_parts(text)：返回 PARTS 里没有出现在 text 中的那些零件名组成的列表；\n"
            "3) 用这两个函数拼出一条完整提示词并打印；\n"
            "4) 再打印 missing_parts 对「角色：助教。任务：帮我看看这段回答写得怎么样」的检查"
            "结果，期望 ['约束', '输出格式']。\n"
            "注意：第二行结果恰好证明了两件事——这句话既没说自己要遵守什么，也没说交回什么形状。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": PROMPT_EX1_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "前四行分别是角色、任务、约束、输出格式四行，顺序与 PARTS 一致",
            },
            {
                "name": "自检 2",
                "expect": "第三行 约束：只回一个词；不要解释：多条约束用「；」连在了一行里",
            },
            {
                "name": "自检 3",
                "expect": "第五行输出 ['约束', '输出格式']：这句要求只写了角色和任务，缺的正是这两件",
            },
            {
                "name": "自检 4",
                "expect": "把 PARTS 里的四个名字逐个删掉再跑，missing_parts 的结果跟着变",
            },
        ],
        "required_patterns": [
            r"def\s+build_prompt\s*\(",
            r"def\s+missing_parts\s*\(",
            r"return\s+",
            r"角色[:：]",
            r"任务[:：]",
            r"约束[:：]",
            r"输出格式[:：]",
            r"\.join\s*\(",
            r"print\s*\(",
        ],
        "requirement_labels": [
            "定义函数 build_prompt 拼出四个零件",
            "定义函数 missing_parts 找出缺了哪个零件",
            "用 return 把拼好的结果交回调用方",
            "在提示词里写出角色这一行",
            "在提示词里写出任务这一行",
            "在提示词里写出约束这一行",
            "在提示词里写出输出格式这一行",
            "用 join 把多条约束连成一行",
            "用 print 打印拼好的提示词与缺口",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
        ],
        "expected_output": (
            "角色：你是一名严格的作业批改员\n"
            "任务：判断回答有没有讲清楚「返回」\n"
            "约束：只回一个词；不要解释\n"
            "输出格式：通过 / 不通过\n"
            "['约束', '输出格式']"
        ),
    },
    {
        "lesson_code": "route_a.llm.prompt",
        "code": "route_a.llm.prompt.ex2",
        "title": "按任务挑温度，并算清 few-shot 的代价",
        "order_index": 2,
        "difficulty": 2,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把「这类任务该用什么温度」和「few-shot 示例每次要多花多少 token」写成两个纯"
            "函数，再逐条打印结论。\n"
            "要做的事：\n"
            "1) pick_temperature(kind)：「抽取」「判定」返回 0.0，「改写」返回 0.7，其余返回 0.3；\n"
            "2) few_shot_cost(count, tokens_each)：返回 count * tokens_each——每个示例每次请求"
            "都要重新带上，所以代价是乘法；\n"
            "3) 用 for 遍历 tasks = [「抽取」,「判定」,「改写」]，按「抽取 温度=0.0」的格式打印"
            "三行；\n"
            "4) 再用 few_shot_cost(3, 80) 算出三个示例、每个 80 token 的总花费，打印一行"
            "「三个示例每次多花 240 token」；\n"
            "5) 期望输出四行：抽取 温度=0.0 / 判定 温度=0.0 / 改写 温度=0.7 / "
            "三个示例每次多花 240 token。\n"
            "注意：240 必须由 few_shot_cost 算出来，不许直接写进输出。\n"
            "禁止：不许访问网络（不导入任何联网的库、不发起任何请求）。\n"
            "预计 18 分钟，难度 2。"
        ),
        "starter_code": PROMPT_EX2_STARTER,
        "visible_tests": [
            {
                "name": "自检 1",
                "expect": "第一行 抽取 温度=0.0：抽取要的是可复现，用低温",
            },
            {
                "name": "自检 2",
                "expect": "第二行 判定 温度=0.0：判定是与否，同样要可复现",
            },
            {
                "name": "自检 3",
                "expect": "第三行 改写 温度=0.7：改写要的是变化，温度调高",
            },
            {
                "name": "自检 4",
                "expect": "第四行 三个示例每次多花 240 token：3 × 80 由 few_shot_cost 算出来",
            },
        ],
        "required_patterns": [
            r"def\s+pick_temperature\s*\(",
            r"def\s+few_shot_cost\s*\(",
            r"return\s+0\.0",
            r"return\s+0\.7",
            r"return\s+count\s*\*\s*tokens_each",
            r"for\s+\w+\s+in\s+tasks",
            r"few_shot_cost\s*\(\s*3\s*,\s*80\s*\)",
            r"print\s*\(\s*f['\"]",
        ],
        "requirement_labels": [
            "定义函数 pick_temperature 按任务挑温度",
            "定义函数 few_shot_cost 算出示例的代价",
            "抽取与判定这类确定性任务把温度定成 0.0",
            "改写任务把温度调高到 0.7",
            "用乘法算出每次请求示例的 token 代价",
            "用 for 逐个处理任务清单",
            "调用 few_shot_cost 传入三个示例与每个 80 token",
            "用 f 字符串把结论拼成一行再打印",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\b240\b",
        ],
        "expected_output": (
            "抽取 温度=0.0\n判定 温度=0.0\n改写 温度=0.7\n三个示例每次多花 240 token"
        ),
    },
)


def upgrade() -> None:
    """Seed the two Sprint 12 lessons and their four exercises (idempotent)."""
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
            for lesson in LESSONS_V5
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
            for exercise in EXERCISES_V5
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0017_sprint12_ai_core_content 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
