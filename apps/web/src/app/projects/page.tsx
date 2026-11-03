import type { Metadata } from "next";
import {
  Card,
  CardBody,
  CardHeader,
  DemoTag,
  DisabledButton,
  Tag,
} from "@/components/ui";
import { IconArrowRight } from "@/components/icons";

type CandidateProject = {
  title: string;
  goal: string;
  skills: string[];
  deliverable: string;
  difficulty: string;
  weeks: string;
};

const PROJECTS: CandidateProject[] = [
  {
    title: "个人知识库检索助手",
    goal: "把自己的笔记做成可检索的知识库，回答问题时给出引用来源。",
    skills: ["检索", "文本切分", "提示工程"],
    deliverable: "一个可导入笔记、能返回引用片段的命令行或网页工具",
    difficulty: "中等",
    weeks: "预计 2 周",
  },
  {
    title: "学习数据看板 API",
    goal: "为学习行为建模，提供可查询的统计接口，并接入本前端。",
    skills: ["HTTP 接口", "数据建模", "SQL"],
    deliverable: "一组 REST 接口 + 数据字典 + 接口文档",
    difficulty: "中等",
    weeks: "预计 2 周",
  },
  {
    title: "多步骤任务编排 Agent",
    goal: "把「查资料 → 整理 → 产出文件」拆成可观测的多个步骤。",
    skills: ["模型调用", "结构化输出", "错误处理"],
    deliverable: "一个带步骤日志与失败重试的编排流程 + 演示录屏",
    difficulty: "进阶",
    weeks: "预计 3 周",
  },
];

const SUBMIT_REQUIREMENTS = [
  { title: "公开仓库链接", detail: "包含完整源码，无密钥与隐私数据。" },
  { title: "运行说明", detail: "从零开始可复现的环境准备与启动步骤。" },
  { title: "演示录屏", detail: "时长不超过 3 分钟，覆盖主要使用流程。" },
  { title: "自评与复盘", detail: "说明取舍、未完成项与下一步计划。" },
];

export const metadata: Metadata = {
  title: "项目实践",
};

export default function ProjectsPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-muted">项目实践 · 阶段 4–6</p>
            <DemoTag />
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">项目实践</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
            从三个候选项目里选一个，按「目标 → 交付物 → 评审」推进。
            项目列表与提交要求为演示数据，提交入口尚未开放。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DisabledButton>选择项目</DisabledButton>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section aria-labelledby="candidates" className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 id="candidates" className="text-[13px] font-semibold tracking-tight text-fg">
                三个候选项目
              </h2>
              <DemoTag />
            </div>
            <div className="grid gap-4">
              {PROJECTS.map((project) => (
                <Card key={project.title}>
                  <CardBody className="space-y-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="text-[14px] font-semibold tracking-tight text-fg">
                          {project.title}
                        </h3>
                        <p className="mt-1 text-[12px] leading-relaxed text-muted">
                          {project.goal}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Tag>{project.difficulty}</Tag>
                        <Tag>{project.weeks}</Tag>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {project.skills.map((skill) => (
                        <Tag key={skill}>{skill}</Tag>
                      ))}
                    </div>
                    <div className="rounded-control bg-surface px-3 py-2.5">
                      <p className="text-[11px] text-muted">交付物</p>
                      <p className="mt-1 text-[12px] leading-relaxed text-fg">
                        {project.deliverable}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <DisabledButton>查看详情</DisabledButton>
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          </section>

          <Card>
            <CardHeader
              title="提交要求骨架"
              description="四项材料缺一不可；校验与上传功能开发中。"
              action={<DemoTag />}
            />
            <ul className="divide-y divide-line">
              {SUBMIT_REQUIREMENTS.map((item, index) => (
                <li key={item.title} className="flex items-start gap-3 px-5 py-3.5">
                  <span className="mt-0.5 font-mono text-[11px] text-muted">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-fg">{item.title}</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-muted">{item.detail}</p>
                  </div>
                  <Tag>待提交</Tag>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
              <DisabledButton>提交项目</DisabledButton>
              <span className="inline-flex items-center gap-1 text-[11px] text-muted">
                <IconArrowRight className="size-3" />
                提交与评审流程尚未接通
              </span>
            </div>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader title="评审标准" description="评审关注可运行、可解释、可复现。" />
            <CardBody className="space-y-3 text-[11px] leading-relaxed text-muted">
              <p>
                <span className="font-medium text-fg">可运行：</span>
                按说明从零启动，主要流程可以完整走通。
              </p>
              <p>
                <span className="font-medium text-fg">可解释：</span>
                能说清关键取舍，说明为什么不用另一种做法。
              </p>
              <p>
                <span className="font-medium text-fg">可复现：</span>
                依赖、配置、数据来源明确，不含密钥与隐私数据。
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="投入建议" action={<DemoTag />} />
            <CardBody className="space-y-3">
              {[
                { label: "建议周期", value: "2–3 周" },
                { label: "每周投入", value: "6–8 小时" },
                { label: "当前进度", value: "未开始" },
              ].map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between border-b border-line pb-2 text-[12px] last:border-b-0 last:pb-0"
                >
                  <span className="text-muted">{row.label}</span>
                  <span className="font-mono text-fg">{row.value}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}