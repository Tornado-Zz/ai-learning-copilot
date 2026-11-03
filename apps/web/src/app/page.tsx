import type { Metadata } from "next";
import { SystemStatusCard } from "@/components/system-status";
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

type TodayTask = {
  title: string;
  detail: string;
  state: string;
};

const TODAY_TASKS: TodayTask[] = [
  {
    title: "复习昨日笔记：React 状态与渲染",
    detail: "预计 12 分钟 · 路线 A · 阶段 3",
    state: "待开始",
  },
  {
    title: "完成 3 道 TypeScript 类型练习",
    detail: "预计 25 分钟 · 练习",
    state: "待开始",
  },
  {
    title: "补齐项目 README 的「本地运行」一节",
    detail: "预计 15 分钟 · 项目实践",
    state: "未开始",
  },
];

const WEEK_GOALS = [
  { label: "学习时长", value: "4 / 6 小时", percent: 67 },
  { label: "练习完成", value: "7 / 10 道", percent: 70 },
  { label: "项目推进", value: "2 / 3 项", percent: 67 },
];

export const metadata: Metadata = {
  title: "今日概览",
};

export default function TodayPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-muted">
              路线 A · 第 3 阶段 · 第 12 天
            </p>
            <DemoTag />
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">
            今日概览
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
            今天只需要推进三件事：补上昨天的复习、完成一组类型练习、把项目说明补完整。
            系统不会催促进度，只把下一步放在眼前。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DisabledButton>继续学习：阶段 3 · 第 2 节</DisabledButton>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="今日任务"
              description="3 项任务，预计共 52 分钟；任务清单为演示数据。"
              action={<DemoTag />}
            />
            <ul className="divide-y divide-line">
              {TODAY_TASKS.map((task) => (
                <li
                  key={task.title}
                  className="flex items-start gap-3 px-5 py-4"
                >
                  <span
                    aria-hidden="true"
                    className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-[3px] border border-line-strong bg-surface"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-fg">{task.title}</p>
                    <p className="mt-1 text-[12px] text-muted">{task.detail}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Tag>{task.state}</Tag>
                    <DisabledButton>开始</DisabledButton>
                  </div>
                </li>
              ))}
            </ul>
            <div className="border-t border-line px-5 py-3">
              <p className="text-[11px] leading-relaxed text-muted">
                勾选与计时功能开发中；当前任务条目不参与任何数据写入。
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="继续学习"
              description="从上次停下的位置继续；进度为演示数据。"
              action={<DemoTag />}
            />
            <CardBody className="space-y-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[12px] text-muted">路线 A · 六阶段自学路线</p>
                  <p className="mt-1 text-[15px] font-semibold tracking-tight text-fg">
                    阶段 3 · React 与组件思维
                  </p>
                  <p className="mt-1 text-[12px] text-muted">
                    下一节：自定义 Hooks 与状态提升 · 预计 18 分钟
                  </p>
                </div>
                <Tag tone="accent">进行中</Tag>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[11px] text-muted">
                  <span>阶段进度</span>
                  <span className="font-mono">60%</span>
                </div>
                <Meter value={60} label="阶段进度" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <DisabledButton>进入下一节</DisabledButton>
                <span className="inline-flex items-center gap-1 text-[11px] text-muted">
                  <IconArrowRight className="size-3" />
                  课程内容尚未接入
                </span>
              </div>
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-6">
          <SystemStatusCard />

          <Card>
            <CardHeader
              title="本周目标"
              description="第 12 周目标；数据为演示数据。"
              action={<DemoTag />}
            />
            <CardBody className="space-y-4">
              {WEEK_GOALS.map((goal) => (
                <div key={goal.label} className="space-y-2">
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-muted">{goal.label}</span>
                    <span className="font-mono text-fg">{goal.value}</span>
                  </div>
                  <Meter value={goal.percent} tone="muted" label={goal.label} />
                </div>
              ))}
            </CardBody>
            <div className="border-t border-line px-5 py-3">
              <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted">
                <IconCheck className="mt-0.5 size-3 shrink-0" />
                目标调整功能开发中，当前仅展示占位进度。
              </p>
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}
