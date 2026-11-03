import type { Metadata } from "next";
import { Card, CardBody, CardHeader, DemoTag, Tag } from "@/components/ui";
import { IconArrowRight } from "@/components/icons";

type Skill = {
  name: string;
  completion: number;
  mastery: number;
};

const SKILLS: Skill[] = [
  { name: "TypeScript 类型系统", completion: 82, mastery: 64 },
  { name: "React 与组件设计", completion: 60, mastery: 41 },
  { name: "后端接口设计", completion: 25, mastery: 12 },
  { name: "数据建模与 SQL", completion: 18, mastery: 8 },
  { name: "AI 应用与提示工程", completion: 8, mastery: 4 },
  { name: "工程化与调试", completion: 45, mastery: 30 },
];

const WEEKS = 12;
const DAYS = 7;

function mockLevel(index: number): number {
  const day = Math.floor(index / WEEKS);
  const week = index % WEEKS;
  if (day === 6) {
    return 0;
  }
  if (week < 3) {
    return 0;
  }
  return (week + day) % 4;
}

const LEVEL_CLASS: Record<number, string> = {
  0: "bg-elevated",
  1: "bg-accent/15",
  2: "bg-accent/30",
  3: "bg-accent/50",
  4: "bg-accent/70",
};

const HEATMAP = Array.from({ length: WEEKS * DAYS }, (_, index) => mockLevel(index));

const DAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

export const metadata: Metadata = {
  title: "学习进度",
};

export default function ProgressPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-muted">进度 · 近 12 周</p>
            <DemoTag />
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">学习进度</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
            进度页区分两个指标：走完了多少内容（完成率），以及能独立复现多少（掌握度）。
            两者不一致是常态，用来判断要不要放慢速度。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Tag>统计口径开发中</Tag>
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="能力维度"
              description="六个维度的完成率与掌握度对照；数值为演示数据。"
              action={<DemoTag />}
            />
            <CardBody className="space-y-5">
              <div className="flex flex-wrap items-center gap-4 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
                  完成率
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="size-2 rounded-full bg-muted" />
                  掌握度
                </span>
              </div>
              <ul className="space-y-4">
                {SKILLS.map((skill) => (
                  <li key={skill.name} className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[12px] font-medium text-fg">{skill.name}</span>
                      <span className="shrink-0 font-mono text-[11px] text-muted">
                        {skill.completion}% / {skill.mastery}%
                      </span>
                    </div>
                    <div className="space-y-1">
                      <div
                        className="h-1.5 w-full overflow-hidden rounded-full bg-elevated"
                        role="img"
                        aria-label={skill.name + " 完成率 " + skill.completion + "%"}
                      >
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: skill.completion + "%" }}
                        />
                      </div>
                      <div
                        className="h-1 w-full overflow-hidden rounded-full bg-elevated"
                        role="img"
                        aria-label={skill.name + " 掌握度 " + skill.mastery + "%"}
                      >
                        <div
                          className="h-full rounded-full bg-muted"
                          style={{ width: skill.mastery + "%" }}
                        />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="近 12 周学习分布"
              description="每格代表一天，颜色越深表示当天投入越多；数据为演示数据。"
              action={<DemoTag />}
            />
            <CardBody className="space-y-3">
              <div className="flex gap-2">
                <div className="grid grid-rows-[repeat(7,minmax(0,1fr))] gap-1 text-[10px] leading-none text-muted">
                  {DAY_LABELS.map((label) => (
                    <span key={label} className="flex items-center">
                      {label}
                    </span>
                  ))}
                </div>
                <div className="grid flex-1 grid-cols-12 gap-1">
                  {HEATMAP.map((level, index) => (
                    <span
                      key={index}
                      aria-hidden="true"
                      className={
                        "aspect-square rounded-[2px] " + (LEVEL_CLASS[level] ?? LEVEL_CLASS[0])
                      }
                    />
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span>少</span>
                  {[0, 1, 2, 3, 4].map((level) => (
                    <span
                      key={level}
                      aria-hidden="true"
                      className={"size-2.5 rounded-[2px] " + LEVEL_CLASS[level]}
                    />
                  ))}
                  <span>多</span>
                </div>
                <span className="font-mono text-[11px] text-muted">12 周 · 84 天</span>
              </div>
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card className="border-accent/30">
            <CardHeader
              title="完成率 ≠ 掌握度"
              description="这是进度页最重要的一条说明。"
              action={<Tag tone="accent">阅读提示</Tag>}
            />
            <CardBody className="space-y-3 text-[11px] leading-relaxed text-muted">
              <p>
                <span className="font-medium text-fg">完成率</span>
                只说明「看过 / 做过」的比例，进度条走完不等于会做。
              </p>
              <p>
                <span className="font-medium text-fg">掌握度</span>
                需要用复述、迁移与间隔复习来验证：能否不看资料复原，能否换一个场景复用。
              </p>
              <p>
                <span className="font-medium text-fg">当前状态：</span>
                判题引擎未实现，掌握度只能按练习结果粗略推算，当前所有数值为占位演示数据。
              </p>
              <p className="flex items-start gap-1.5 pt-1">
                <IconArrowRight className="mt-0.5 size-3 shrink-0" />
                当完成率明显高于掌握度时，优先回头做小练习，而不是继续推进新内容。
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="数据来源" description="当前版本的数据边界。" />
            <CardBody className="space-y-3">
              {[
                { label: "数据来源", value: "演示数据" },
                { label: "统计窗口", value: "近 12 周" },
                { label: "持久化", value: "未接入" },
                { label: "计算口径", value: "开发中" },
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