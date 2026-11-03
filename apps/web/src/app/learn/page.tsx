import type { Metadata } from "next";
import {
  Card,
  CardBody,
  CardHeader,
  DemoTag,
  DisabledButton,
  Meter,
  Tag,
} from "@/components/ui";
import { IconArrowRight, IconCheck } from "@/components/icons";

type StageState = "done" | "active" | "todo";

type Stage = {
  index: number;
  title: string;
  goal: string;
  weeks: string;
  progress: number;
  state: StageState;
};

const STAGES: Stage[] = [
  {
    index: 1,
    title: "编程基础与工具链",
    goal: "命令行、Git、编辑器与调试",
    weeks: "第 1–2 周",
    progress: 100,
    state: "done",
  },
  {
    index: 2,
    title: "Web 基础与 TypeScript",
    goal: "HTML/CSS 基础、类型系统与模块化",
    weeks: "第 3–5 周",
    progress: 100,
    state: "done",
  },
  {
    index: 3,
    title: "React 与组件思维",
    goal: "组件拆分、状态管理、数据流",
    weeks: "第 6–8 周",
    progress: 60,
    state: "active",
  },
  {
    index: 4,
    title: "后端与数据建模",
    goal: "HTTP 接口、数据库、数据一致性",
    weeks: "第 9–11 周",
    progress: 0,
    state: "todo",
  },
  {
    index: 5,
    title: "AI 集成与提示工程",
    goal: "模型调用、结构化输出、评估",
    weeks: "第 12–14 周",
    progress: 0,
    state: "todo",
  },
  {
    index: 6,
    title: "工程化与上线",
    goal: "测试、部署、可观测性",
    weeks: "第 15–16 周",
    progress: 0,
    state: "todo",
  },
];

function StageTag({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <Tag>
        <IconCheck className="mr-1 size-3" />
        已完成
      </Tag>
    );
  }
  if (state === "active") {
    return <Tag tone="accent">进行中</Tag>;
  }
  return <Tag>未开始</Tag>;
}

export const metadata: Metadata = {
  title: "学习路线",
};

export default function LearnPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-muted">路线 A · 六阶段 · 共 16 周</p>
            <DemoTag />
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">学习路线</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
            一条从编程基础到 AI 应用上线的自学路线：每个阶段都包含概念学习、练习与一次可展示的产出。
            阶段顺序固定，节奏可以按自己的时间调整。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DisabledButton>查看阶段说明</DisabledButton>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="阶段进度概览"
              description="六个阶段的完成情况；进度数据为演示数据。"
              action={<DemoTag />}
            />
            <ul className="divide-y divide-line">
              {STAGES.map((stage) => (
                <li key={stage.index} className="px-5 py-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[11px] text-muted">
                      {stage.index}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[13px] font-medium text-fg">{stage.title}</p>
                        <StageTag state={stage.state} />
                      </div>
                      <p className="mt-1 text-[12px] text-muted">
                        {stage.goal} · {stage.weeks}
                      </p>
                      <div className="mt-3 flex items-center gap-3">
                        <Meter
                          value={stage.progress}
                          tone={stage.state === "active" ? "accent" : "muted"}
                          label={stage.title}
                          className="max-w-[280px]"
                        />
                        <span className="shrink-0 font-mono text-[11px] text-muted">
                          {stage.progress}%
                        </span>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader
              title="下一步入口"
              description="从阶段 3 的进度继续；入口尚未接通课程内容。"
            />
            <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-fg">
                  阶段 3 · 第 2 节：自定义 Hooks 与状态提升
                </p>
                <p className="mt-1 text-[12px] text-muted">
                  预计 18 分钟 · 前置要求：阶段 3 第 1 节已完成
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <DisabledButton>开始本节</DisabledButton>
              </div>
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader title="路线结构" description="每个阶段的固定结构。" />
            <CardBody className="space-y-3">
              {[
                { title: "概念学习", detail: "5–8 个知识单元，每个 15–25 分钟" },
                { title: "配套练习", detail: "每个单元 3–5 道题，含即时反馈" },
                { title: "阶段产出", detail: "一个可运行、可展示的小作品" },
              ].map((item) => (
                <div key={item.title} className="rounded-control bg-surface px-3 py-2.5">
                  <p className="text-[12px] font-medium text-fg">{item.title}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted">{item.detail}</p>
                </div>
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="学习记录"
              description="阶段内的学习历史。"
              action={<DemoTag />}
            />
            <CardBody>
              <div className="rounded-control border border-dashed border-line-strong px-4 py-6 text-center">
                <p className="text-[12px] font-medium text-fg">暂无学习记录</p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted">
                  学习记录与笔记功能开发中，接入后这里会按时间列出每个阶段的完成情况。
                </p>
              </div>
              <div className="mt-4 flex items-center gap-1.5 text-[11px] text-muted">
                <IconArrowRight className="size-3" />
                数据持久化尚未实现
              </div>
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}