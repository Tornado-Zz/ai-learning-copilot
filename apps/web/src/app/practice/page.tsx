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

type Exercise = {
  title: string;
  topic: string;
  difficulty: "入门" | "中等" | "进阶";
  minutes: number;
  state: string;
};

const EXERCISES: Exercise[] = [
  {
    title: "用泛型约束实现类型安全的 fetch 封装",
    topic: "TypeScript · 类型系统",
    difficulty: "中等",
    minutes: 20,
    state: "未开始",
  },
  {
    title: "把组件内的状态提升到页面级",
    topic: "React · 状态管理",
    difficulty: "入门",
    minutes: 15,
    state: "未开始",
  },
  {
    title: "为列表渲染补齐 key 与空状态处理",
    topic: "React · 渲染",
    difficulty: "入门",
    minutes: 10,
    state: "未开始",
  },
  {
    title: "设计一张支持软删除的课程表",
    topic: "数据库 · 数据建模",
    difficulty: "进阶",
    minutes: 35,
    state: "未开始",
  },
  {
    title: "写一个带超时与重试的请求函数",
    topic: "工程化 · 网络",
    difficulty: "中等",
    minutes: 25,
    state: "未开始",
  },
];

const JUDGE_PENDING = [
  {
    title: "代码执行沙箱",
    detail: "在隔离环境中运行提交的代码，限制 CPU 与内存。",
  },
  {
    title: "测试用例与断言",
    detail: "每道题配套输入输出用例，覆盖边界与错误路径。",
  },
  {
    title: "评分与反馈",
    detail: "给出通过情况、失败原因与可读的改进提示。",
  },
];

export const metadata: Metadata = {
  title: "练习与判题",
};

export default function PracticePage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-muted">练习 · 判题引擎未接入</p>
            <DemoTag />
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">练习与判题</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
            练习列表的页面结构已经就位，题目内容与判题引擎尚未实现。
            当前所有条目都不能开始作答，避免让你误以为提交后会得到评分。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DisabledButton>开始练习</DisabledButton>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="练习列表"
              description="按阶段 3 的知识单元生成；列表内容为演示数据。"
              action={<DemoTag />}
            />
            <div className="hidden grid-cols-[1fr_120px_88px_72px] gap-3 border-b border-line px-5 py-2 text-[11px] text-muted sm:grid">
              <span>题目</span>
              <span>知识点</span>
              <span>难度</span>
              <span className="text-right">状态</span>
            </div>
            <ul className="divide-y divide-line">
              {EXERCISES.map((exercise) => (
                <li
                  key={exercise.title}
                  className="grid grid-cols-1 gap-2 px-5 py-4 sm:grid-cols-[1fr_120px_88px_72px] sm:items-center sm:gap-3"
                >
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-fg">{exercise.title}</p>
                    <p className="mt-1 text-[11px] text-muted sm:hidden">
                      {exercise.topic} · {exercise.difficulty} · {exercise.minutes} 分钟
                    </p>
                    <p className="mt-1 hidden text-[11px] text-muted sm:block">
                      预计 {exercise.minutes} 分钟 · {exercise.state}
                    </p>
                  </div>
                  <span className="hidden truncate text-[12px] text-muted sm:block">
                    {exercise.topic}
                  </span>
                  <span className="hidden sm:block">
                    <Tag>{exercise.difficulty}</Tag>
                  </span>
                  <span className="sm:text-right">
                    <Tag>开发中</Tag>
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader
              title="判题未实现说明"
              description="以下能力开发中，当前版本不提供任何判题结果。"
              action={<Tag>开发中</Tag>}
            />
            <CardBody className="space-y-3">
              {JUDGE_PENDING.map((item) => (
                <div key={item.title} className="rounded-control bg-surface px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <p className="text-[12px] font-medium text-fg">{item.title}</p>
                    <Tag>开发中</Tag>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted">{item.detail}</p>
                </div>
              ))}
              <p className="flex items-start gap-1.5 pt-1 text-[11px] leading-relaxed text-muted">
                <IconArrowRight className="mt-0.5 size-3 shrink-0" />
                在判题接入之前，页面不会显示通过率、得分或任何形式的自动评价。
              </p>
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader
              title="本周练习"
              description="统计口径待定；数值为演示数据。"
              action={<DemoTag />}
            />
            <CardBody className="space-y-3">
              {[
                { label: "已完成题目", value: "0 / 5" },
                { label: "已判题", value: "—" },
                { label: "正确率", value: "—" },
                { label: "平均用时", value: "—" },
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

          <Card>
            <CardHeader title="练习说明" />
            <CardBody className="space-y-3 text-[11px] leading-relaxed text-muted">
              <p>题目按知识单元组织，每道题对应一个可验证的小目标。</p>
              <p>难度分为入门、中等、进阶三档，用于估计投入时间，不代表评分。</p>
              <p>作答记录、草稿保存与历史提交功能开发中。</p>
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}