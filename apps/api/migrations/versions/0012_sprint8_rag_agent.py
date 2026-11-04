"""Sprint 8 AI 内容：RAG 与 Agent 两节课，以及每课两道练习

Revision ID: 0012_sprint8_rag_agent
Revises: 0011_sprint7_ai_content
Create Date: 2026-03-25 00:00:00+00:00

0011 补上了 a3（API）与 a4（LLM），但技能域 a5「RAG 与 Agent 基础」与
a6「简单 AI 项目」仍然一节课都没有。本迁移补上 route_a.rag.retrieval
（30 分钟）与 route_a.agent.tool（30 分钟）两节课，以及每课两道练习（共 4 道）。
至此六域里有五域各有对应课程（a2 编程实践由 a1 的练习覆盖）。

只发 INSERT，两处都带 ON CONFLICT (code) DO NOTHING：
* 既有 7 节课、14 道练习与全部用户数据一行不动，表结构不动；
* 对同一个库连续执行两次 upgrade head 不报错、不覆盖已有内容（幂等）；
* 不新增依赖、不建表、不改表；没有 downgrade 路径（项目契约禁止 DROP / DELETE）。

离线契约：两节课的正文与 4 道练习都只用「示例检索结果 / 示例工具调用响应」当教材，
学习与判题都不需要联网、不需要密钥。4 道练习的 forbidden_patterns 都把「导入网络库」
与「真实 URL 字面量」写成正则禁止项，静态判题会直接拒掉联网写法。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0012_sprint8_rag_agent"
down_revision: str | None = "0011_sprint7_ai_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# skill_id 与 lesson_id 一律用子查询按 code 取，不硬编码数字：种子表的 id 由数据库
# 生成（lessons 用 identity，0011 那两节课的真实 id 是 1058 / 1059），硬编码会在
# 另一个库上指向错误的行（这正是 0003/0004/0011 的写法）。
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

LESSONS_V3: tuple[dict[str, object], ...] = (
    {
        "code": "route_a.rag.retrieval",
        "skill_code": "route_a.a5",
        "stage": 5,
        "title": "检索增强：让回答有出处",
        "summary": "先查再答：把长文档切块、按关键词重合度打分取最高，再把命中块的原文塞进 prompt 并带上出处",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 8,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能说清 RAG「先查再答」的两步分别在做什么，能解释为什么长文档必须先切成块，"
                "能写出按关键词重合度打分并取最高分的 best_chunk，能把命中块的原文放进 prompt "
                "并要求回答带出处，也能说明为什么「有出处」比「听起来对」更可信。"
            ),
            "explanation": [
                (
                    "模型只会接着往下写，它的知识停在训练那一刻，也看不到你自己的资料。"
                    "RAG（检索增强生成）把一次回答拆成两步：先从你自己的资料里查（retrieve），"
                    "再把查到的原文放进问题里让它作答（generate）。为什么这一步值得多写几十行代码？"
                    "因为改资料比重新训练模型便宜太多，而且回答有了落脚点——你能指出这句话是从哪一段来的。"
                ),
                (
                    "为什么必须把长文档切成块（chunk）：模型一次能看的 token 有上限，整篇文档塞不进去；"
                    "就算塞得进去，里面九成内容是这次问题用不上的，重点会被稀释，钱也照付。切成块之后，"
                    "检索只需要从一堆小块里挑出最相关的那几块。切多大是个工程判断：切得太碎，一句话失去"
                    "上下文；切得太大，又回到「塞整篇」的老问题。按段落或标题切，通常比按固定字数硬切更稳。"
                ),
                (
                    "怎么从一堆块里挑：最简单可用的打分是关键词重合度——把问题拆成关键词，数每个块里"
                    "出现了几个，分数最高的就是最可能相关的那一块。它的局限很明确：同义不同词（「切块」与"
                    "「分片」）会漏掉，真实系统会换成向量相似度。但骨架是一样的：候选 -> 打分 -> 排序 -> "
                    "取 top1。先把这条骨架跑通，换打分函数就不用改结构。"
                ),
                (
                    "拿到最佳块之后要做什么：把它的原文和问题一起拼进 prompt，并明确要求「只根据参考资料"
                    "回答，答案后面标出处」。两处细节值得较真。第一，贴原文而不是你自己的概述：概述会把"
                    "原文的措辞和细节磨平，也顺手丢掉了可核对的依据。第二，要求标出处：让用户知道这句话"
                    "从哪一段来，也让你自己能在出问题时一眼分辨是检索错了还是模型编了。"
                ),
                (
                    "为什么「有出处」比「听起来对」更可信：模型最危险的地方不是答错，而是错得很流畅——"
                    "术语对、语气稳、结构完整。带上出处之后，验证成本从「重读整篇文档」降到「看一眼那一段」。"
                    "它并没有让答案变对，它让答案变得可核对：如果出处里的原文根本支撑不了结论，那就是模型"
                    "编的；如果检索出来的块本身不对，那是检索的问题。这两种错要分开修。"
                ),
                (
                    "最后是边界：RAG 不保证正确。文档里没有的内容，正确的做法是回答「资料里没有」，而不是"
                    "硬凑一个答案；检索错了，后面每一步都在错的基础上继续。所以排查顺序永远是先看检索结果、"
                    "再看 prompt、最后才怀疑模型。把「先查再答」当成一条流水线，你就知道该在哪一段装仪表。"
                ),
            ],
            "example": {
                "title": "切块 -> 打分取最高 -> 把原文塞进 prompt",
                "code": (
                    "# 三步：切块 -> 打分取最高 -> 把原文塞进 prompt（全程离线）\n"
                    "chunks = [\n"
                    '    {"id": "c1", "text": "长文档不能整篇塞给模型，要先切块（chunk）：'
                    '切成一段一段，每段单独检索。"},\n'
                    '    {"id": "c2", "text": "每段文字就是一个 chunk，方便单独拿出来放进 prompt。"},\n'
                    '    {"id": "c3", "text": "回答末尾标出出处，用户能自己核对这句话从哪一段来。"},\n'
                    "]\n"
                    'query = "切块 chunk"\n'
                    "\n"
                    "\n"
                    "def score(text, query):\n"
                    '    """关键词重合度：数一数问题里有几个词出现在这块文字里。"""\n'
                    '    return sum(1 for word in query.split() if word in text)\n'
                    "\n"
                    "\n"
                    "def best_chunk(chunks, query):\n"
                    "    for chunk in chunks:                 # 先把每块的分数打出来，看得见才好调\n"
                    '        print(chunk["id"], score(chunk["text"], query))\n'
                    '    return max(chunks, key=lambda chunk: score(chunk["text"], query))\n'
                    "\n"
                    "\n"
                    "best = best_chunk(chunks, query)\n"
                    'print("best:", best["id"])\n'
                    "\n"
                    "# 把命中块的原文（不是概述）和问题一起交给模型，并要求标出处\n"
                    "prompt = (\n"
                    '    f"问题：{query}\\n"\n'
                    "    f\"参考资料（出处 {best['id']}）：{best['text']}\\n\"\n"
                    '    f"请只根据参考资料回答，并在答案后面用 [出处: {best[\'id\']}] 标出来源。"\n'
                    ")\n"
                    "print(prompt)\n"
                ),
                "output": (
                    "c1 2\n"
                    "c2 1\n"
                    "c3 0\n"
                    "best: c1\n"
                    "问题：切块 chunk\n"
                    "参考资料（出处 c1）：长文档不能整篇塞给模型，要先切块（chunk）：切成一段一段，"
                    "每段单独检索。\n"
                    "请只根据参考资料回答，并在答案后面用 [出处: c1] 标出来源。"
                ),
                "notes": [
                    "关键词重合度只看字面：问题里写成「分片」而块里写「切块」，分数就是 0。",
                    "max 在并列时取第一个，所以「谁的分数一样时取前面的」不用额外写判断。",
                    "prompt 里贴的是块原文，不是「这段话讲切块」这种概括——概括丢掉了可核对的依据。",
                    "看到 best 那一行是 c1、分数是 2，就说明检索这一关过了，再去挑模型的问题。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把整篇文档直接塞进 prompt，不切块也不检索",
                    "why": (
                        "超出上下文上限会被截断或直接报错；即使塞得进去，无关内容也会稀释重点，"
                        "而且输入 token 全部计费。"
                    ),
                    "fix": "先切块，只把得分最高的那一块（或少数几块）原文放进 prompt。",
                },
                {
                    "mistake": "把问题自己也当块，或者把块的全部文本当关键词",
                    "why": (
                        "打分要比较的是「问题的关键词」出现在「块的文本」里多少次，两边搞反或搞混，"
                        "分数就没有意义。"
                    ),
                    "fix": "关键词来自 query.split()，被查的是 chunk[\"text\"]，方向固定。",
                },
                {
                    "mistake": "只把块塞进 prompt，不要求标出处",
                    "why": "没有出处的回答看起来一样流畅，但用户无法核对，你也分不清是检索错还是模型编。",
                    "fix": "在 prompt 里写死要求：只根据参考资料回答，并在答案后面用 [出处: id] 标出来源。",
                },
                {
                    "mistake": "检索结果不对，却先去调 temperature 或换模型",
                    "why": "RAG 的错大多出在检索：块选错了，再好的模型也只能基于错的资料作答。",
                    "fix": "先把每块的得分打出来看，确认 top1 就是该命中的那一块，再去看回答。",
                },
            ],
            "self_check": [
                {
                    "question": "RAG 的「先查再答」具体是哪两步？",
                    "answer": (
                        "第一步检索：从自己的资料库里找出与问题最相关的块；第二步生成：把块的原文"
                        "和问题一起放进 prompt，让模型基于这段资料作答。"
                    ),
                },
                {
                    "question": "为什么长文档一定要先切成块？",
                    "answer": (
                        "模型一次能看的 token 有上限，整篇塞不进去；塞进去也会被无关内容稀释重点并抬高成本。"
                        "切块后只需要挑最相关的少数几块。"
                    ),
                },
                {
                    "question": "关键词重合度打分有什么用、又漏掉了什么？",
                    "answer": (
                        "用处：几行代码就能把「候选 -> 打分 -> 取最高」跑通，且结果可解释（看得见分数）。"
                        "漏掉的：同义不同词、语序与语义，那些要靠向量相似度补。"
                    ),
                },
                {
                    "question": "为什么「有出处」比「听起来对」更可信？",
                    "answer": (
                        "它把验证成本从重读整篇文档降到看一眼那一段，并且能把错误定位成「检索错了」"
                        "还是「模型编了」；答案本身仍可能错，但它变得可核对。"
                    ),
                },
            ],
        },
    },
    {
        "code": "route_a.agent.tool",
        "skill_code": "route_a.a6",
        "stage": 6,
        "title": "第一次让模型用工具",
        "summary": "工具调用的形状：先声明 name / description / 参数 schema，模型只回「调用哪个工具、参数是什么」，由程序执行并回填结果",
        "content_version": 1,
        "estimated_minutes": 30,
        "order_index": 9,
        "difficulty": 3,
        "content": {
            "schema_version": 1,
            "goal": (
                "能写出一份合法的工具声明（最外层 type、里面的 name / description / parameters 参数 schema），"
                "能读懂示例响应里 tool_calls[0].function.name 与 arguments，能说清一次工具调用的四步循环"
                "（声明 -> 模型要调用 -> 程序执行 -> 结果回填再问一次），也能解释为什么工具必须由程序执行。"
            ),
            "explanation": [
                (
                    "模型只输出文本，它没有手：读不了你的数据库、查不了天气、也写不了文件。所谓「让模型用工具」"
                    "不是给它装上手脚，而是让它把「我想调用哪个工具、参数是什么」写成一段结构化输出，"
                    "再由你的程序去执行。这个分工是整件事的地基，理解错方向后面全是坑。"
                ),
                (
                    "动手之前先声明工具。一份工具声明至少三样东西：name（程序按它分派）、description"
                    "（给模型看的说明书：什么时候该用、参数是什么意思）、parameters（参数 schema，"
                    "写清类型、有哪些字段、哪些必填）。description 写含糊，模型就会该调不调、不该调乱调；"
                    "required 漏写，模型就可能少给一个参数，程序执行时直接崩在缺参上。"
                ),
                (
                    "真实的一次往返是这样的：把 messages 和 tools 一起发过去；模型回来的不是答案，"
                    "而是一条 tool_calls——里面是 name 和 arguments；注意 arguments 是一段 JSON 文本，"
                    "不是字典，要先解析；然后程序按 name 在分派表里找到对应函数执行；把执行结果包成一条"
                    "结果消息追加进 messages；再发一次，模型才基于工具的真实返回作答。响应的 finish_reason "
                    "是 tool_calls，说明它正在等你办事，而不是已经答完了。"
                ),
                (
                    "为什么工具必须由程序执行，而不是让模型自己「跑一遍」？因为模型的执行是假的：它不知道你"
                    "账户里有多少钱，也无法真的写文件，它只会生成一段看起来像执行结果的文本。执行权留在程序"
                    "手里，才能做三件事：校验参数（模型会把城市名写成它编的、把数字写成字符串）、限制范围"
                    "（哪个工具只读、哪个工具能写、哪些操作要人工确认）、留下日志（谁在什么时候调了什么、"
                    "返回了什么）。让模型自己宣布「已完成」，你拿到的是不可信的一句话，而不是可核对的记录。"
                ),
                (
                    "新手最常犯的四类错：把 tools 写成一句自然语言描述而不是结构化声明；拿到 arguments 就"
                    "直接下标取值（它还是文本）；程序执行完却忘了把结果回填进 messages 就又提问（模型只能"
                    "重复调用同一个工具）；没有分派表，模型返回什么名字都不知道该用哪个函数。"
                    "HANDLERS = {\"get_weather\": ...} 这种「名字 -> 函数」的映射，是整套循环的心脏。"
                ),
                (
                    "最后是边界：工具越多，模型选错的概率越高，所以每个工具的 description 要写清「什么时候用」，"
                    "工具集要尽量小。带副作用的工具（写库、发消息、动钱）必须加二次确认，不能给模型"
                    "「说了就执行」的权限。记住顺序就不会乱：先声明、模型要调用、程序执行、结果回填。"
                    "少了回填，模型就是在凭空作答。"
                ),
            ],
            "example": {
                "title": "声明一个工具，读懂一次工具调用响应，再由程序执行",
                "code": (
                    "import json\n"
                    "\n"
                    "# 1) 先声明工具：name + description + 参数 schema\n"
                    "weather_tool = {\n"
                    '    "type": "function",\n'
                    '    "function": {\n'
                    '        "name": "get_weather",\n'
                    '        "description": "查询某个城市此刻的天气；用户问到天气、温度、下雨时使用。",\n'
                    '        "parameters": {\n'
                    '            "type": "object",\n'
                    '            "properties": {\n'
                    '                "city": {"type": "string", "description": "城市名，例如 杭州"},\n'
                    "            },\n"
                    '            "required": ["city"],\n'
                    "        },\n"
                    "    },\n"
                    "}\n"
                    'print(weather_tool["function"]["name"])       # get_weather\n'
                    "\n"
                    "# 2) 模型返回的不是答案，而是「要调用哪个工具、参数是什么」（离线教材）\n"
                    'response_text = r"""\n'
                    '{"choices": [{"message": {"role": "assistant", "content": null,\n'
                    '  "tool_calls": [{"id": "call_1", "type": "function",\n'
                    '    "function": {"name": "get_weather", "arguments": "{\\"city\\": \\"杭州\\"}"}}]},\n'
                    '  "finish_reason": "tool_calls"}]}\n'
                    '"""\n'
                    "response = json.loads(response_text)\n"
                    'tool_call = response["choices"][0]["message"]["tool_calls"][0]\n'
                    'print(tool_call["function"]["name"])          # get_weather\n'
                    "\n"
                    "# 3) arguments 是一段 JSON 文本，先解析才能拿到参数\n"
                    'arguments = json.loads(tool_call["function"]["arguments"])\n'
                    'print(arguments["city"])                      # 杭州\n'
                    "\n"
                    "# 4) 程序执行工具（离线教材：真实系统这里会去查天气），把结果回填给模型\n"
                    'HANDLERS = {"get_weather": lambda city: f"{city} 26℃，晴"}\n'
                    'print(HANDLERS[tool_call["function"]["name"]](**arguments))   # 杭州 26℃，晴\n'
                    'print(response["choices"][0]["finish_reason"])  # tool_calls：它在等程序办事\n'
                ),
                "output": (
                    "get_weather\n"
                    "get_weather\n"
                    "杭州\n"
                    "杭州 26℃，晴\n"
                    "tool_calls"
                ),
                "notes": [
                    "arguments 里是一段文本而不是字典，不解析就直接下标会报 TypeError 或 KeyError。",
                    "程序用名字在 HANDLERS 里查表执行，模型永远碰不到函数本身。",
                    "finish_reason 是 tool_calls，说明这一轮的产物是一次调用请求，不是最终答案。",
                ],
            },
            "common_mistakes": [
                {
                    "mistake": "把 tools 写成一句话：「你能查天气」",
                    "why": (
                        "接口要的是结构化声明（name / description / parameters），一句自然语言没法让模型"
                        "知道参数叫什么、该填什么类型。"
                    ),
                    "fix": "按 type / function / name / description / parameters 的层级写成字典。",
                },
                {
                    "mistake": "对 arguments 直接下标：tool_call[\"function\"][\"arguments\"][\"city\"]",
                    "why": "arguments 是一段 JSON 文本，对它下标会报 TypeError: string indices must be integers。",
                    "fix": "先 arguments = json.loads(...)，再用 arguments[\"city\"] 取参数。",
                },
                {
                    "mistake": "程序执行完工具，不把结果回填就再问一次",
                    "why": "模型看不到工具返回，只会重复发起同一个调用，看起来像「卡住了」。",
                    "fix": "把执行结果作为一条结果消息追加进 messages，再发下一次请求。",
                },
                {
                    "mistake": "让模型自己输出「已执行完成」当作执行结果",
                    "why": (
                        "模型没有执行能力，那句话是生成的文本，不是可核对的事实；副作用也从未真正发生。"
                    ),
                    "fix": "执行只放在程序里：校验参数、限制权限、记日志，再把真实结果回给模型。",
                },
            ],
            "self_check": [
                {
                    "question": "一份工具声明至少要有哪三样东西？",
                    "answer": "name（程序按它分派）、description（给模型看的使用说明）、parameters（参数 schema，含类型与必填项）。",
                },
                {
                    "question": "模型收到工具之后，第一轮返回的是什么？",
                    "answer": (
                        "不是答案，而是一条 tool_calls：要调用哪个工具（name）和参数（arguments，一段 JSON 文本），"
                        "finish_reason 为 tool_calls。"
                    ),
                },
                {
                    "question": "为什么工具必须由程序执行？",
                    "answer": (
                        "模型只能生成看起来像结果的文本，它没有真实的执行能力。执行权在程序手里才能校验参数、"
                        "限制权限、留下可核对的日志。"
                    ),
                },
                {
                    "question": "工具执行完，下一次请求前必须做什么？",
                    "answer": "把执行结果回填成一条消息追加进 messages，否则模型看不到结果，只会重复调用。",
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
EXERCISES_V3: tuple[dict[str, object], ...] = (
    # --- 课程 8：检索增强：让回答有出处 ---------------------------------------
    {
        "lesson_code": "route_a.rag.retrieval",
        "code": "route_a.rag.retrieval.ex1",
        "title": "用关键词重合度挑出最相关的那一块",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：写一个 score 和一个 best_chunk，用关键词重合度从三段文档块里挑出最相关的一块。\n"
            "要做的事：\n"
            "1) score(text, query)：把 query 用 split() 拆成关键词，数一数有几个关键词出现在 text 里，"
            "返回这个个数；\n"
            "2) best_chunk(chunks, query)：遍历每一块，先打印「块的 id」和「这一块的分数」（用空格隔开），"
            "再用 max() 按分数取最高的那一块返回（并列时取排在前面的）；\n"
            "3) 调用 best_chunk，打印「best: 」加上胜出那一块的 id。\n"
            "期望输出四行：c1 2 / c2 1 / c3 0 / best: c1\n"
            "禁止：不许访问网络（任何联网的库都不要 import，也不许发起请求）；"
            "不许把分数写死成常数，分数必须由关键词重合算出来。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "# 三段切好的文档块（离线教材：真实系统里它们来自你自己的资料）\n"
            "chunks = [\n"
            '    {"id": "c1", "text": "长文档不能整篇塞给模型，要先切块（chunk）：切成一段一段，'
            '每段单独检索。"},\n'
            '    {"id": "c2", "text": "每段文字就是一个 chunk，方便单独拿出来放进 prompt。"},\n'
            '    {"id": "c3", "text": "回答末尾标出出处，用户能自己核对这句话从哪一段来。"},\n'
            "]\n"
            'query = "切块 chunk"\n'
            "\n"
            "\n"
            "def score(text, query):\n"
            "    # 1) 把问题拆成关键词\n"
            "    # 2) 数一数有几个关键词出现在这段文字里，把这个数字返回\n"
            "    pass\n"
            "\n"
            "\n"
            "def best_chunk(chunks, query):\n"
            "    # 3) 遍历每一块，打印「块的 id」和「这一块的分数」\n"
            "    # 4) 按分数取最高的那一块返回（并列时取排在前面的那一块）\n"
            "    pass\n"
            "\n"
            "\n"
            "# 5) 调用 best_chunk，打印 best: 加上胜出那一块的 id\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "前三行依次是 c1 2 / c2 1 / c3 0：每块一行，id 与分数用空格隔开"},
            {"name": "自检 2", "expect": "c1 的分数是 2，因为「切块」和 chunk 都出现在它的文字里"},
            {"name": "自检 3", "expect": "最后一行 best: c1：得分最高的那一块"},
            {
                "name": "自检 4",
                "expect": "把 query 改成「出处」，best 应该变成 c3——分数跟着关键词走，不是写死的",
            },
        ],
        "required_patterns": [
            r"def\s+score\s*\(",
            r"def\s+best_chunk\s*\(",
            r"\.split\s*\(\s*\)",
            r"for\s+chunk\s+in\s+chunks",
            r"max\s*\(",
            r"\[\s*['\"]text['\"]\s*\]",
            r"\[\s*['\"]id['\"]\s*\]",
            r"print\s*\(\s*['\"]best",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
        ],
        "expected_output": "c1 2\nc2 1\nc3 0\nbest: c1",
    },
    {
        "lesson_code": "route_a.rag.retrieval",
        "code": "route_a.rag.retrieval.ex2",
        "title": "把命中块的原文塞进 prompt 并带上出处",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把上一题命中那一块的原文拼进 prompt，并让回答带上可核对的出处。\n"
            "要做的事：\n"
            "1) build_prompt(question, chunk)：返回三行文本（用 \"\\n\".join([...]) 拼起来），三行依次是：\n"
            "   第 1 行：问题：<question 原文>\n"
            "   第 2 行：参考资料（出处 <chunk 的 id>）：<chunk 的 text 原文>\n"
            "   第 3 行：请只根据参考资料回答，并在答案后面用 [出处: <chunk 的 id>] 标出来源。\n"
            "2) cite(answer, chunk)：返回 answer 后面接一个空格，再接 [出处: <chunk 的 id>]；\n"
            "3) 打印 build_prompt(question, best) 的结果；\n"
            "4) 打印 print(cite(答案, best)) 的结果，答案是「先切块是为了只给模型看有用的部分，"
            "而不是把整篇塞进去。」\n"
            "禁止：不许访问网络（任何联网的库都不要 import，也不许发起请求）；"
            "不许只把问题塞进 prompt 而丢掉块的原文（概述不算原文）；不许用 eval。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "# 上一题挑出来的那一块（离线教材：真实系统会从你自己的资料里检索）\n"
            "best = {\n"
            '    "id": "c1",\n'
            '    "text": "长文档不能整篇塞给模型，要先切块（chunk）：切成一段一段，每段单独检索。",\n'
            "}\n"
            'question = "为什么要先切块？"\n'
            "\n"
            "\n"
            "def build_prompt(question, chunk):\n"
            "    # 1) 返回三行拼起来的字符串：问题 / 参考资料（带出处）/ 只根据资料回答并要求标出处\n"
            "    pass\n"
            "\n"
            "\n"
            "def cite(answer, chunk):\n"
            "    # 2) 返回 answer 后面接一个空格，再接 [出处: 块的 id]\n"
            "    pass\n"
            "\n"
            "\n"
            "# 3) 打印 build_prompt(question, best) 的结果\n"
            "# 4) 打印 cite(「先切块是为了只给模型看有用的部分，而不是把整篇塞进去。」, best) 的结果\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第 1 行是 问题：为什么要先切块？"},
            {
                "name": "自检 2",
                "expect": "第 2 行是 参考资料（出处 c1）：加上块原文，原文一个字都不能少",
            },
            {
                "name": "自检 3",
                "expect": "第 3 行明确要求「只根据参考资料回答」并给出处格式，否则模型会自由发挥",
            },
            {"name": "自检 4", "expect": "第 4 行是回答正文加 [出处: c1]，用户据此能回头核对"},
        ],
        "required_patterns": [
            r"def\s+build_prompt\s*\(",
            r"def\s+cite\s*\(",
            r"\[\s*['\"]text['\"]\s*\]",
            r"\[\s*['\"]id['\"]\s*\]",
            r"\\n",
            r"\[\s*出处",
            r"print\s*\(\s*cite\s*\(",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
        ],
        "expected_output": (
            "问题：为什么要先切块？\n"
            "参考资料（出处 c1）：长文档不能整篇塞给模型，要先切块（chunk）：切成一段一段，"
            "每段单独检索。\n"
            "请只根据参考资料回答，并在答案后面用 [出处: c1] 标出来源。\n"
            "先切块是为了只给模型看有用的部分，而不是把整篇塞进去。 [出处: c1]"
        ),
    },
    # --- 课程 9：第一次让模型用工具 -------------------------------------------
    {
        "lesson_code": "route_a.agent.tool",
        "code": "route_a.agent.tool.ex1",
        "title": "写一份合法的工具声明",
        "order_index": 1,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：把一份工具声明写完整——模型只能靠这份声明决定该不该调用、参数叫什么。\n"
            "要做的事：\n"
            "1) 把 starter 里的 weather_tool 补全：最外层 \"type\" 写 function；里面的 function 有\n"
            "   name（写 get_weather）、description（一句能看出「什么时候用」的说明）、"
            "parameters（\"type\" 写 object，\"properties\" 里放 city，city 的 type 是 string，"
            "\"required\" 写 [\"city\"]）；\n"
            "2) 打印工具名，期望 get_weather；\n"
            "3) 打印参数个数，期望 1；\n"
            "4) 打印参数名的有序列表（sorted），期望 ['city']；\n"
            "5) 用 json.dumps(weather_tool, ensure_ascii=False) 转成文本，打印它的类型，期望 <class 'str'>。\n"
            "禁止：不许访问网络（任何联网的库都不要 import，也不许真的把请求发出去）。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            "# 1) 把工具声明写完整：最外层 type 是 function，里面的 function 有 "
            "name / description / parameters\n"
            "weather_tool = {\n"
            '    "type": "",\n'
            '    "function": {\n'
            '        "name": "",\n'
            '        "description": "",\n'
            '        "parameters": {\n'
            '            "type": "object",\n'
            '            "properties": {},\n'
            '            "required": [],\n'
            "        },\n"
            "    },\n"
            "}\n"
            "\n"
            "# 2) 打印工具名（期望 get_weather）\n"
            "\n"
            "# 3) 打印参数个数（期望 1）\n"
            "\n"
            "# 4) 打印参数名的有序列表（期望 ['city']）\n"
            "\n"
            "# 5) 用 json.dumps(weather_tool, ensure_ascii=False) 转成文本，打印它的类型\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 get_weather"},
            {"name": "自检 2", "expect": "第二行输出 1：参数只有 city 一个"},
            {"name": "自检 3", "expect": "第三行输出 ['city']：参数名来自 properties 的键"},
            {
                "name": "自检 4",
                "expect": "最后一行输出 <class 'str'>：声明最终要变成要发出去的 JSON 文本",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r"\"type\"\s*:\s*\"function\"",
            r"\"name\"\s*:\s*\"get_weather\"",
            r"\"description\"\s*:\s*\"",
            r"\"parameters\"\s*:\s*\{",
            r"\"properties\"\s*:\s*\{",
            r"\"required\"\s*:\s*\[\s*\"city\"\s*\]",
            r"sorted\s*\(",
            r"json\.dumps\s*\(",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"\bopenai\b",
            r"https?://",
        ],
        "expected_output": "get_weather\n1\n['city']\n<class 'str'>",
    },
    {
        "lesson_code": "route_a.agent.tool",
        "code": "route_a.agent.tool.ex2",
        "title": "从示例响应里取出要调用的工具与参数",
        "order_index": 2,
        "difficulty": 3,
        "estimated_minutes": 18,
        "content_version": 1,
        "prompt": (
            "目标：response_text 里是一次工具调用响应。把工具名和参数取出来，再由程序执行。\n"
            "要做的事：\n"
            "1) 沿 choices -> 第一项 -> message -> tool_calls -> 第一项，取到这一次要调用的工具；\n"
            "2) 打印工具名，期望 get_weather；\n"
            "3) 把 function 里的 arguments 再解析一次（它是一段 JSON 文本，不是字典），打印其中的 city，"
            "期望 杭州；\n"
            "4) 打印这次为什么停下（取 choices 第一项的 finish_reason），期望 tool_calls；\n"
            "5) 在 HANDLERS 里按工具名查到函数，把参数传进去执行，打印执行结果，期望 杭州 26℃，晴。\n"
            "禁止：不许访问网络（任何联网的库都不要 import，也不许发起请求）；"
            "不许对 arguments 直接下标取值（那是文本，会报 TypeError）；"
            "不许把工具名或参数写死成字面量打印。\n"
            "预计 18 分钟，难度 3。"
        ),
        "starter_code": (
            "import json\n"
            "\n"
            "# 示例响应（离线教材）：模型没有回答，它只说「要调用哪个工具、参数是什么」\n"
            'response_text = r"""\n'
            '{"choices": [{"message": {"role": "assistant", "content": null,\n'
            '  "tool_calls": [{"id": "call_1", "type": "function",\n'
            '    "function": {"name": "get_weather", "arguments": "{\\"city\\": \\"杭州\\"}"}}]},\n'
            '  "finish_reason": "tool_calls"}]}\n'
            '"""\n'
            "\n"
            "response = json.loads(response_text)\n"
            "\n"
            "# 程序侧的分派表：模型给出名字，这里查表执行（离线教材：真实系统会去查天气）\n"
            'HANDLERS = {"get_weather": lambda city: f"{city} 26℃，晴"}\n'
            "\n"
            "# 1) 沿 choices -> 第一项 -> message -> tool_calls -> 第一项，取到这一次要调用的工具\n"
            "\n"
            "# 2) 打印工具名（期望 get_weather）\n"
            "\n"
            "# 3) 把 function 里的 arguments 再解析一次，打印其中的 city（期望 杭州）\n"
            "\n"
            "# 4) 打印 finish_reason（期望 tool_calls）\n"
            "\n"
            "# 5) 在分派表里按工具名找到函数，把参数传进去执行，打印执行结果\n"
        ),
        "visible_tests": [
            {"name": "自检 1", "expect": "第一行输出 get_weather：这是模型要求调用的工具名"},
            {
                "name": "自检 2",
                "expect": "第二行输出 杭州：arguments 解析之后才拿得到 city",
            },
            {
                "name": "自检 3",
                "expect": "第三行输出 tool_calls：说明这一轮的产物是调用请求，不是最终答案",
            },
            {
                "name": "自检 4",
                "expect": "第四行输出 杭州 26℃，晴：执行发生在程序里，模型只拿到结果",
            },
        ],
        "required_patterns": [
            r"import\s+json",
            r"json\.loads\s*\(\s*response_text\s*\)",
            r"\[\s*['\"]choices['\"]\s*\]",
            r"\[\s*['\"]tool_calls['\"]\s*\]",
            r"\[\s*['\"]arguments['\"]\s*\]",
            r"\[\s*['\"]finish_reason['\"]\s*\]",
            r"json\.loads\s*\(\s*tool_call\s*\[",
            r"HANDLERS\s*\[",
        ],
        "forbidden_patterns": [
            r"\brequests\b",
            r"\burlopen\b",
            r"\burllib\b",
            r"https?://",
            r"\beval\s*\(",
        ],
        "expected_output": "get_weather\n杭州\ntool_calls\n杭州 26℃，晴",
    },
)


def upgrade() -> None:
    """Seed the two Sprint 8 lessons and their four exercises (idempotent)."""
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
            for lesson in LESSONS_V3
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
            for exercise in EXERCISES_V3
        ],
    )


def downgrade() -> None:
    """No downgrade path: the project contract forbids every destructive statement."""
    raise RuntimeError(
        "0012_sprint8_rag_agent 不支持降级：项目契约禁止 DROP/DELETE/TRUNCATE 类语句"
    )
