"""Sprint 7 AI 内容：API 与 LLM 两节课，以及每课两道练习

Revision ID: 0011_sprint7_ai_content
Revises: 0010_capstone_review_requires_reviewer
Create Date: 2026-03-24 00:00:00+00:00

技能域 a3「API」与 a4「LLM」此前完全没有课程：产品叫「AI 学习」，却只有 5 节
Python 基础课。本迁移补上 route_a.api.json（25 分钟）与 route_a.llm.messages
（30 分钟）两节课，以及每课两道练习（共 4 道）。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 0001 建的表与六个技能域、0003 的 5 节课、0004 的 10 道练习一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习都只用「示例请求体 / 示例响应文本」当教材，
学习与判题都不需要联网、不需要密钥。4 道练习的 forbidden_patterns 都把
requests / urlopen / 真实 URL 字面量列为禁止项，静态判题会直接拒掉联网写法。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0011_sprint7_ai_content"
down_revision: str | None = "0010_capstone_review_requires_reviewer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库
# 生成，硬编码会在另一个库上指向错误的行（这正是 0003/0004 的写法）。
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

LESSONS_V2: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.api.json",
        "skill_code": "route_a.a3",
        "stage": 3,
        "title": "请求、响应与 JSON",
        "summary": "搞清一次接口调用的来去：方法、状态码，以及用 json.loads 把响应文本变成字典",
        "content_version": 1,
        "estimated_minutes": 25,
        "order_index": 6,
        "difficulty": 2,
        "content": {
            "schema_version": 1,
            "goal": (
                "能说清一次接口调用里谁发请求、谁回响应，知道 GET 与 POST 的区别、"
                "2xx / 4xx / 5xx 各自该先查什么，能把一段 JSON 文本用 json.loads 转成字典"
                "并取出需要的字段，也不再对响应文本直接做下标取值。"
            ),
            "explanation": [
                (
                    "接口（API）是程序之间约定好的对话方式：你按约定说清要什么，对方按约定回结果。"
                    "像去窗口办事，请求是你递上去的那张表，响应是窗口递回来的回执。你不需要知道"
                    "窗口后面怎么运作，只要把表填对、把回执读懂。学会读响应，才可能自己判断"
                    "「这一步到底成功了没有」。"
                ),
                (
                    "一个请求有四部分：方法、路径、请求头、请求体。方法说明你想做什么（GET 取数据、"
                    "POST 新建、PUT 或 PATCH 修改、DELETE 删除）；路径说明对哪个资源，例如 "
                    "/v1/lessons/6 表示第 6 节课；请求头放格式与身份信息；请求体只在要带数据的方法上"
                    "出现，通常是 JSON。新手最常搞错的是把数据塞进 GET 的路径里，而不是放进 POST 的请求体。"
                ),
                (
                    "一个响应有三部分：状态码、响应头、响应体。状态码按百位分段：2xx 成功"
                    "（200 正常、201 已创建、204 无内容）；4xx 是请求方的问题（400 参数格式错、"
                    "401 没登录、403 没权限、404 路径或 id 不存在、422 校验不通过）；5xx 是服务端"
                    "内部出错（500）。看到 4xx 先检查自己的请求，看到 5xx 不是你的锅，可以重试一次"
                    "并记下时间与响应里的追踪号。"
                ),
                (
                    "响应体几乎都是 JSON。JSON 只有六种形状：对象 {}、数组 []、字符串、数字、"
                    "true / false、null。它比 Python 严格得多：键与字符串只能用双引号，不能有"
                    "尾逗号，不能写注释，true / false / null 必须小写。所以别把 Python 字面量的"
                    "习惯写进 JSON，否则解析一定失败。"
                ),
                (
                    "拿到响应文本后的第一步永远是 json.loads(text)：它把文本变成 Python 的字典或"
                    "列表，之后才能用 [\"key\"] 或 .get(\"key\") 取值。字段形状并不保证：可能缺失，"
                    "也可能多一层嵌套。所以取字段时用 .get() 配默认值，取嵌套之前先确认上一层存在，"
                    "不要假设「一定有这么一层」。"
                ),
            ],
            "example": {
                "title": "用 json.loads 解析一段示例响应",
                "code": (
                    "import json\n"
                    "\n"
                    "# 一段示例响应文本（离线教材：真正调用会从网络把它取回来）\n"
                    'raw = """\n'
                    "{\n"
                    '  "status": 200,\n'
                    '  "data": {\n'
                    '    "lesson": {"code": "route_a.py.variables", "title": "变量与数据类型"},\n'
                    '    "exercises": [\n'
                    '      {"code": "route_a.py.variables.ex1", "minutes": 10},\n'
                    '      {"code": "route_a.py.variables.ex2", "minutes": 8}\n'
                    "    ]\n"
                    "  },\n"
                    '  "trace_id": null\n'
                    '}\n'
                    '"""\n'
                    "\n"
                    "response = json.loads(raw)                    # 文本 -> 字典\n"
                    "print(type(response))                         # <class 'dict'>\n"
                    'print(response["status"])                     # 200\n'
                    'print(response["data"]["lesson"]["title"])    # 变量与数据类型\n'
                    'total = sum(item["minutes"] for item in response["data"]["exercises"])\n'
                    "print(total)                                  # 18（10 + 8）\n"
                    'print(response.get("error", "没有错误"))        # 没有错误\n'
                ),
                "output": (
                    "<class 'dict'>\n200\n变量与数据类型\n18\n没有错误"
                ),
                "notes": [
                    "json.loads 只认双引号：把示例里的双引号换成单引号就会抛 JSONDecodeError。",
                    "先 print(type(response)) 再取值，能避开「以为拿到字典、其实是字符串」这类错误。",
                    "response.get(\"error\", 默认值) 在字段不存在时返回默认值，不会抛 KeyError。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "直接对响应文本做下标取值，例如 text[\"data\"]",
                    "why": (
                        "从网络拿到的是字符串，字符串的下标按字符取，取不到字段，还会报 "
                        "TypeError: string indices must be integers。"
                    ),
                    "fix": "先 parsed = json.loads(text) 得到字典，再用 parsed[\"data\"] 取值。",
                },
                {
                    "mistake": "把 JSON 写成 Python 字面量：单引号、尾逗号、行内注释",
                    "why": "json.loads 只接受严格 JSON，单引号、尾逗号和注释都会让它抛 JSONDecodeError。",
                    "fix": "键与字符串改成双引号，删掉最后一个元素后面的逗号与所有注释。",
                },
                {
                    "mistake": "用 status == \"200\" 判断成功",
                    "why": "JSON 里的 200 是数字不是字符串，字符串比较恒为 False，成功会被当成失败。",
                    "fix": "用数字比较，或者更稳地写 200 <= status < 300。",
                },
                {
                    "mistake": "假设字段一定存在，直接 response[\"error\"][\"message\"]",
                    "why": "成功响应里根本没有 error 字段，取不存在的键抛 KeyError，嵌套取值还可能报 TypeError。",
                    "fix": "先 if \"error\" in response，或用 response.get(\"error\", {}) 再取里面的键。",
                },
            ],
            "self_check": [
                {
                    "question": "GET 与 POST 最本质的区别是什么？",
                    "answer": (
                        "GET 用来取数据，参数放在路径或查询串里，不应改动服务端；POST 用来新建，"
                        "数据放在请求体里，通常会改变服务端状态。"
                    ),
                },
                {
                    "question": "收到 404 和收到 500，分别应该先查什么？",
                    "answer": (
                        "404 先查自己的路径拼写和 id 是否真实存在（资源没了）；500 是服务端内部错误，"
                        "先重试一次，再带上时间与响应里的追踪号去报障。"
                    ),
                },
                {
                    "question": "为什么 print(type(json.loads(raw))) 显示的是 dict 而不是 str？",
                    "answer": (
                        "json.loads 的返回值是 Python 对象：JSON 对象变成 dict、JSON 数组变成 list，"
                        "所以类型是 dict，而原始文本 raw 才是 str。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.llm.messages",
        "skill_code": "route_a.a4",
        "stage": 4,
        "title": "调用大模型的请求长什么样",
        "summary": "读消息数组里的 system / user / assistant，理解 temperature、max_tokens 与 token 计费",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 7,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能自己写出一段合法的大模型请求体（model + messages + temperature + max_tokens），"
                "能读懂示例响应里的 choices[0].message.content 与 usage 的三个 token 数字，"
                "能解释 token 为什么是计费单位，并知道模型不记得上一轮、历史要自己放回 messages。"
            ),
            "explanation": [
                (
                    "大模型接口看起来参数很多，其实只有一个动作：交给它一串消息，它接着往下写。"
                    "所以请求体的核心永远是 messages 数组——数组里每一条是一个对象，只有两个键："
                    "role 说明谁在说，content 说明说了什么。把这个结构记住，剩下都是调参。"
                ),
                (
                    "三个角色各有分工。system 是使用说明，用来设定身份与规则，放在数组最前面，"
                    "一次对话通常只有一条；user 是你说的话，也就是这次真正要问的问题；"
                    "assistant 是模型之前说过的话。模型本身没有记忆，所谓「记住上文」，"
                    "只是你把历史消息按从早到晚的顺序一起发了过去。"
                ),
                (
                    "两个最该先搞懂的参数：temperature 控制随机性，0 最稳、接近 1 更发散，"
                    "写代码、抽取事实用 0 到 0.3，创意写作才调高；max_tokens 是这次回答的长度上限，"
                    "不是必须用满，一旦撞到上限回答就会被截断，响应的 finish_reason 会变成 length。"
                    "model 则决定用哪个模型，不同模型的单价与能装下的上下文长度都不一样。"
                ),
                (
                    "token 是模型切分文本的最小记账单位，大致相当于一个常见英文单词或半个中文词。"
                    "输入（prompt）和输出（completion）都按 token 计费，所以 messages 越长、"
                    "回答越长，花的钱越多。一次调用的响应会给出 usage：prompt_tokens、"
                    "completion_tokens、total_tokens，前两者相加等于第三者，账单就是拿它算出来的。"
                ),
                (
                    "响应的形状是固定的：choices 是候选回答的列表，一般只取第一个；"
                    "choices[0].message.content 是文本，choices[0].finish_reason 说明为什么停下"
                    "（stop 正常结束、length 撞到上限）；usage 是这次的 token 账。读响应时先取 "
                    "content 再取 usage，别指望它是一段纯文本。"
                ),
                (
                    "最后是排错顺序：400 或 422 基本都在请求体上——漏了 role、content 写成列表、"
                    "temperature 写成 1.5、messages 写成一个字符串；429 是调用太频繁，等一会儿再试；"
                    "5xx 是服务端问题，保留响应里的追踪号再报障。先按状态码分类，比逐字读报错快得多。"
                ),
            ],
            "example": {
                "title": "构造一个请求体，再读懂一段示例响应",
                "code": (
                    "import json\n"
                    "\n"
                    "# 1) 请求体：模型看到的就是这个字典（离线教材，不发给任何服务）\n"
                    "payload = {\n"
                    '    "model": "example-chat-v1",\n'
                    '    "messages": [\n'
                    '        {"role": "system", "content": "你是 Python 助教，只回答 Python 问题。"},\n'
                    '        {"role": "user", "content": "range(1, 6) 会得到哪些数字？"},\n'
                    "    ],\n"
                    '    "temperature": 0.2,\n'
                    '    "max_tokens": 200,\n'
                    "}\n"
                    'print(len(payload["messages"]))                  # 2\n'
                    'print(payload["messages"][1]["role"])            # user\n'
                    "\n"
                    "# 2) 示例响应文本（真实调用会把这段 JSON 放进响应体）\n"
                    'response_text = """\n'
                    "{\n"
                    '  "choices": [\n'
                    '    {"message": {"role": "assistant", "content": "1、2、3、4、5"},\n'
                    '     "finish_reason": "stop"}\n'
                    "  ],\n"
                    '  "usage": {"prompt_tokens": 48, "completion_tokens": 9, "total_tokens": 57}\n'
                    '}\n'
                    '"""\n'
                    "\n"
                    "response = json.loads(response_text)\n"
                    'print(response["choices"][0]["message"]["content"])   # 1、2、3、4、5\n'
                    'usage = response["usage"]\n'
                    'print(usage["total_tokens"])                          # 57\n'
                    "\n"
                    "PRICE_PER_1K = 0.002      # 示例单价：每 1K token 0.002\n"
                    'cost = usage["total_tokens"] / 1000 * PRICE_PER_1K\n'
                    "print(round(cost, 6))                                 # 0.000114\n"
                ),
                "output": "2\nuser\n1、2、3、4、5\n57\n0.000114",
                "notes": [
                    "messages 的顺序就是对话顺序，system 放第一条。",
                    "content 是文本、usage 是数字，两者都在同一个字典里，取之前先确认形状。",
                    "57 / 1000 * 0.002 = 0.000114，这就是这一句话的账单。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把 messages 写成一个字符串：messages: \"你好\"",
                    "why": "接口要求 messages 是数组，每一项还得是带 role 与 content 的对象，格式不对直接 400 或 422。",
                    "fix": "写成 [{\"role\": \"user\", \"content\": \"你好\"}]。",
                },
                {
                    "mistake": "以为模型记得上一轮，只把新问题发过去",
                    "why": "每次请求都是独立的，模型只看得到这次 messages 里的内容，上一轮不在里面就等于没发生过。",
                    "fix": "把之前的 user 与 assistant 消息按从早到晚的顺序追加回 messages。",
                },
                {
                    "mistake": "把 temperature 设成 1.5 或 -0.1",
                    "why": "取值范围一般限制在 0 到 1（部分模型到 2），超出范围会被服务端直接拒绝。",
                    "fix": "抽取、代码、事实类任务用 0 到 0.3，只有创意写作才往上调。",
                },
                {
                    "mistake": "回答只说了半句就断了，还以为是模型坏了",
                    "why": "max_tokens 设得太小，撞到上限就停，finish_reason 会变成 length。",
                    "fix": "按需要留足 max_tokens，并在读数时先看 finish_reason。",
                },
            ],
            "self_check": [
                {
                    "question": "system 与 user 消息分别该放什么？",
                    "answer": "system 放身份与规则，放在数组最前面、一次对话通常一条；user 放这次的具体问题。",
                },
                {
                    "question": "usage 里三个 token 数字是什么关系？为什么它决定费用？",
                    "answer": "total_tokens = prompt_tokens + completion_tokens；输入与输出都计费，所以总数决定这次的花费。",
                },
                {
                    "question": "为什么说模型「不记得」上一轮？",
                    "answer": "每次请求都是独立的，只有出现在这次 messages 里的内容它才看得到，历史要靠调用方自己带上。",
                },
                {
                    "question": "temperature 取 0 和取 0.9 有什么区别？",
                    "answer": "0 最稳定、几乎每次一样，适合抽取与代码；0.9 更发散，适合创意，但事实准确性会下降。",
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

# 判题是纯文本的静态规则：required_patterns 是正则字符串（一律用 raw string，
# \b 不能被当成退格），能把「写对了」和「没写」区分开；visible_tests 是给人看的
# 自检说明，不参与自动执行。四道题都把联网写法列为 forbidden：静态规则会直接拒掉。
EXERCISES_V2: tuple[dict[str, object], ...] = (
    # --- 课程 6：请求、响应与 JSON -------------------------------------------
    {
        "lesson_code": "route_a.api.json",
        "code": "route_a.api.json.ex1",
        "title": "解析示例响应并取出字段",
        "order_index": 1,
        "difficulty": 2,
        "estimated_minutes": 15,
        "content_version": 1,
        "prompt": (
            "目标：raw 里已经放好了一段示例响应文本，用 json.loads 解析它，按顺序打印三行。\n"
            "要做的事：\n"
            "1) import json，用 json.loads(raw) 把文本转成字典并存进 response；\n"
            "2) 打印状态码：取 response 里的 status，期望输出 200（数字，不带引号）；\n"
            "3) 打印课程标题：沿 data -> lesson -> title 取值，期望输出 变量与数据类型；\n"
            "4) 用 sum() 累加 data 里 exercises 的 minutes，期望输出 18（10 + 8）。\n"
            "禁止：不许访问网络（requests、urllib、urlopen 一律不要用），不许把 raw 当字典直接取值"
            "（那是字符串，会报 TypeError）。\n"
            "预计 15 分钟，难度 2。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            "# 示例响应文本（离线教材：真正调用会从网络把它取回来）\n"
            'raw = """\n'
            '{"status": 200, "data": {"lesson": {"code": "route_a.py.variables", '
            '"title": "变量与数据类型"}, "exercises": [{"minutes": 10}, {"minutes": 8}]}}\n'
            '"""\n'
            "\n"
            "# 1) 用 json.loads 把 raw 转成字典，存进 response\n"
            "\n"
            "# 2) 打印状态码，期望 200（数字，不加引号）\n"
            "\n"
            "# 3) 打印课程标题：沿 data 里的 lesson 再取 title，期望 变量与数据类型\n"
            "\n"
            "# 4) 用内建 sum 累加 exercises 里每项的 minutes，期望 18\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 200（数字，不加引号）"},
            {"name": "自检 2", "expect": "第二行输出 变量与数据类型"},
            {"name": "自检 3", "expect": "第三行输出 18（10 + 8），说明是累加出来的而不是写死的"},
            {
                "name": "自检 4",
                "expect": "如果报 TypeError: string indices must be integers，说明忘了先 json.loads",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r"json\.loads\s*\(\s*raw\s*\)",
            r'response\s*\[\s*"status"\s*\]',
            r'\[\s*"data"\s*\]',
            r'\[\s*"lesson"\s*\]',
            r'\[\s*"title"\s*\]',
            r'\[\s*"exercises"\s*\]',
            r'sum\s*\(',
            r'\[\s*"minutes"\s*\]',
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
        ],
        "expected_output": "200\n变量与数据类型\n18",
    },
    {
        "lesson_code": "route_a.api.json",
        "code": "route_a.api.json.ex2",
        "title": "用状态码判断成功，并用 get 安全取值",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 15,
        "content_version": 1,
        "prompt": (
            "目标：success_raw 是一次成功响应，failure_raw 是一次 404 响应。写一个函数 describe(raw)，"
            "按状态码分别打印，全程用 .get() 取值。\n"
            "要做的事：\n"
            "1) 定义 describe(raw)：先 response = json.loads(raw)，再 status = response.get(\"status\", 0)；\n"
            "2) status 小于 400 时打印两行：先是「200 成功」，再是「课程：」加上 data 里 lesson 的 title；\n"
            "3) 否则打印一行：「404 失败：」加上 error 里 message 的内容；\n"
            "4) 对 success_raw 和 failure_raw 各调用一次 describe。\n"
            "禁止：不许访问网络；不许用 response[\"error\"] 这种直接下标（成功响应里没有 error 字段，"
            "会抛 KeyError）；不许写死 200 与 404 —— 状态码要从响应里读出来。\n"
            "预计 15 分钟，难度 3。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            'success_raw = \'{"status": 200, "data": {"lesson": {"title": "变量与数据类型"}}}\'\n'
            'failure_raw = \'{"status": 404, "error": {"code": "not_found", '
            '"message": "lesson 99 not found"}}\'\n'
            "\n"
            "# 1) 定义函数 describe，参数是 raw：先解析成字典，再用 get 取状态码（默认 0）\n"
            "\n"
            "# 2) 状态码小于 400 时打印两行：先「状态码 成功」，再「课程：」加上课程标题\n"
            "\n"
            '# 3) 否则打印一行：「状态码 失败：」加上 error 里的 message（用 get 兜底）\n'
            "\n"
            "# 4) 依次调用两次，分别传 success_raw 与 failure_raw\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 200 成功"},
            {"name": "自检 2", "expect": "第二行输出 课程：变量与数据类型"},
            {"name": "自检 3", "expect": "第三行输出 404 失败：lesson 99 not found"},
            {
                "name": "自检 4",
                "expect": "把 failure_raw 里的 error 字段删掉再跑，程序不能崩（.get 给了默认值）",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r"def\s+describe\s*\(",
            r"json\.loads\s*\(",
            r'\.get\s*\(\s*"status"',
            r'\.get\s*\(\s*"error"',
            r"status\s*<\s*400",
            r"print\s*\(",
        ],
        "forbidden_patterns": [
            r'\[\s*"error"\s*\]',
            r"\brequests\b",
            r"\burlopen\b",
            r"https?://",
        ],
        "expected_output": "200 成功\n课程：变量与数据类型\n404 失败：lesson 99 not found",
    },
    # --- 课程 7：调用大模型的请求长什么样 -------------------------------------
    {
        "lesson_code": "route_a.llm.messages",
        "code": "route_a.llm.messages.ex1",
        "title": "构造一个合法的大模型请求体",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一次请求的请求体写成字典 payload，再用 json.dumps 确认它可以变成文本。\n"
            "要做的事：\n"
            "1) payload 里放 model（写 example-chat-v1）、temperature（写 0.2）、max_tokens（写 200）；\n"
            "2) messages 是数组，第一条 role 是 system、content 写「你是 Python 助教，只回答 Python 问题。」；\n"
            "3) 第二条 role 是 user、content 写「range(1, 6) 会得到哪些数字？」；\n"
            "4) 依次打印：消息条数（2）、第一条的 role（system）、第二条的 role（user）、"
            "temperature 与 max_tokens（0.2 200）；\n"
            "5) 最后用 json.dumps(payload, ensure_ascii=False) 转成文本，打印它的类型（<class 'str'>）。\n"
            "禁止：不许访问网络（requests、urllib、openai 之类的库都不要 import），"
            "不许真的把请求发出去；temperature 必须在 0 到 1 之间。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            "# 1) 把请求体写完整：model / messages / temperature / max_tokens\n"
            "payload = {\n"
            '    "model": "",\n'
            '    "messages": [],\n'
            "}\n"
            "\n"
            "# 2) messages 里放两条：第一条角色是 system，content 写助教设定；\n"
            "#    第二条角色是 user，content 写「range(1, 6) 会得到哪些数字？」\n"
            "\n"
            "# 3) 依次打印消息条数、第一条的角色、第二条的角色、temperature 与 max_tokens\n"
            "\n"
            "# 4) 用 json 模块的 dumps 把 payload 变成文本（ensure_ascii=False），打印它的类型\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "len(payload[\"messages\"]) 输出 2：system 与 user 各一条"},
            {"name": "自检 2", "expect": "四条输出依次是 2 / system / user / 0.2 200"},
            {
                "name": "自检 3",
                "expect": "最后一行输出 <class 'str'>，说明 json.dumps 把字典变成了要发的文本",
            },
            {
                "name": "自检 4",
                "expect": "把温度改成 1.5 这种越界值，真实服务会拒绝——练习里保持在 0 到 1",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r'"messages"\s*:',
            r'"role"\s*:\s*"system"',
            r'"role"\s*:\s*"user"',
            r'"temperature"\s*:\s*0\.\d',
            r'"max_tokens"\s*:\s*\d+',
            r"json\.dumps\s*\(",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"\bopenai\b",
            r"https?://",
        ],
        "expected_output": "2\nsystem\nuser\n0.2 200\n<class 'str'>",
    },
    {
        "lesson_code": "route_a.llm.messages",
        "code": "route_a.llm.messages.ex2",
        "title": "读懂示例响应与这次调用的 token 账",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：response_text 里是一段示例响应原文，解析它、取出回答，并算出这次调用的花费。\n"
            "要做的事：\n"
            "1) 用 json.loads(response_text) 存进 response；\n"
            "2) 打印回答正文：沿 choices -> 第一个元素 -> message -> content，期望 1、2、3、4、5；\n"
            "3) 打印 prompt_tokens + completion_tokens == total_tokens 的比较结果，期望 True；\n"
            "4) 打印 finish_reason，期望 stop（说明是正常结束，不是被长度截断）；\n"
            "5) 用 PRICE_PER_1K = 0.002 算出 total_tokens / 1000 * PRICE_PER_1K，"
            "用 round(花费, 6) 打印，期望 0.000114。\n"
            "禁止：不许访问网络；不许把 token 数写死成字面量（必须从 usage 里读）；"
            "不许用 eval 或 exec。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            "# 示例响应文本（离线教材：真实调用会把这段 JSON 放进响应体）\n"
            'response_text = """\n'
            '{"choices": [{"message": {"role": "assistant", "content": "1、2、3、4、5"}, '
            '"finish_reason": "stop"}], "usage": {"prompt_tokens": 48, '
            '"completion_tokens": 9, "total_tokens": 57}}\n'
            '"""\n'
            "\n"
            "response = json.loads(response_text)\n"
            "\n"
            "# 1) 打印回答正文：先取候选列表的第一项，再沿 message 取 content，期望 1、2、3、4、5\n"
            "\n"
            "# 2) 打印 prompt_tokens 加 completion_tokens 是否等于总 token 数，期望 True\n"
            "\n"
            "# 3) 打印这次为什么停下（正常结束还是被长度截断），期望 stop\n"
            "\n"
            "PRICE_PER_1K = 0.002\n"
            "# 4) 用总 token 数算花费，保留 6 位小数后打印，期望 0.000114\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 1、2、3、4、5（choices[0] 里那条回答的正文）"},
            {"name": "自检 2", "expect": "第二行输出 True：48 + 9 = 57，总数就是输入加输出"},
            {"name": "自检 3", "expect": "第三行输出 stop；如果换成 length 说明回答被 max_tokens 截断了"},
            {"name": "自检 4", "expect": "最后一行输出 0.000114，这就是这一次调用、这一句话的账单"},
        ],
        "required_patterns": [
            r"import\s+json",
            r"json\.loads\s*\(\s*response_text\s*\)",
            r'\[\s*"choices"\s*\]',
            r'\[\s*"message"\s*\]',
            r'\[\s*"content"\s*\]',
            r'\[\s*"usage"\s*\]',
            r'\[\s*"total_tokens"\s*\]',
            r"round\s*\(",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
            r"\bexec\s*\(",
        ],
        "expected_output": "1、2、3、4、5\nTrue\nstop\n0.000114",
    },
)


def upgrade() -> None:
    """Seed the two Sprint 7 AI lessons and their four exercises (idempotent)."""
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
            for lesson in LESSONS_V2
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
            for exercise in EXERCISES_V2
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0011_sprint7_ai_content 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
