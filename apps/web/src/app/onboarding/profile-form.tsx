"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, ErrorPanel, LoadingPanel } from "@/components/states";
import { Button, Field, Select, TextInput, fieldAria, fieldClass } from "@/components/form";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseUsersMe } from "@/lib/contract";
import type { UsersMe } from "@/lib/contract";
import { TIMEZONE_OPTIONS, WEEKDAYS, timezoneLabel, weekdayLabel } from "@/lib/labels";

type LoadState = "loading" | "ready" | "failed";

type FormErrors = {
  studyDays: string | null;
  dailyMinutes: string | null;
  timezone: string | null;
};

const EMPTY_ERRORS: FormErrors = {
  studyDays: null,
  dailyMinutes: null,
  timezone: null,
};

const DEFAULT_DAYS = [1, 3, 5];
const DEFAULT_MINUTES = "60";
const DEFAULT_TIMEZONE = "Asia/Shanghai";

function sortDays(days: number[]): number[] {
  const unique: number[] = [];
  for (const day of days) {
    if (day >= 1 && day <= 7 && unique.indexOf(day) < 0) {
      unique.push(day);
    }
  }
  return unique.sort((a, b) => a - b);
}

export function ProfileForm() {
  const router = useRouter();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadFailure, setLoadFailure] = useState<ApiFailure | null>(null);
  const [studyDays, setStudyDays] = useState<number[]>([]);
  const [dailyMinutes, setDailyMinutes] = useState(DEFAULT_MINUTES);
  const [timezone, setTimezone] = useState(DEFAULT_TIMEZONE);
  const [confirmed, setConfirmed] = useState(false);
  const [errors, setErrors] = useState<FormErrors>(EMPTY_ERRORS);
  const [saving, setSaving] = useState(false);
  const [saveFailure, setSaveFailure] = useState<ApiFailure | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<UsersMe>("/api/v1/users/me", { parse: parseUsersMe });
      if (!active) {
        return;
      }
      if (result.ok) {
        const me = result.data;
        setStudyDays(sortDays(me.profile.studyDays.length > 0 ? me.profile.studyDays : DEFAULT_DAYS));
        setDailyMinutes(
          me.profile.dailyMinutes >= 15 && me.profile.dailyMinutes <= 480
            ? String(me.profile.dailyMinutes)
            : DEFAULT_MINUTES,
        );
        setTimezone(me.user.timezone || DEFAULT_TIMEZONE);
        setConfirmed(me.user.timezoneSource === "user_confirmed");
        setLoadState("ready");
        return;
      }
      setLoadFailure(result.failure);
      setStudyDays(DEFAULT_DAYS);
      setDailyMinutes(DEFAULT_MINUTES);
      setTimezone(DEFAULT_TIMEZONE);
      setConfirmed(false);
      setLoadState("failed");
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const reload = useCallback(() => {
    setLoadState("loading");
    setLoadFailure(null);
    setReloadToken((value) => value + 1);
  }, []);

  const toggleDay = useCallback((day: number) => {
    setStudyDays((previous) => {
      if (previous.indexOf(day) >= 0) {
        return previous.filter((value) => value !== day);
      }
      return sortDays([...previous, day]);
    });
    setErrors((previous) => ({ ...previous, studyDays: null }));
  }, []);

  const validate = useCallback((): FormErrors => {
    const next: FormErrors = { ...EMPTY_ERRORS };
    const days = sortDays(studyDays);
    if (days.length === 0) {
      next.studyDays = "请至少选择 1 个学习日（周一至周日）。";
    }
    const minutes = Number(dailyMinutes);
    if (!Number.isFinite(minutes) || !Number.isInteger(minutes)) {
      next.dailyMinutes = "请输入整数分钟数。";
    } else if (minutes < 15 || minutes > 480) {
      next.dailyMinutes = "每天可投入时长需在 15–480 分钟之间。";
    }
    if (!timezone) {
      next.timezone = "请选择时区。";
    } else if (!confirmed) {
      next.timezone = "请勾选确认时区后再保存：时区决定「今天 / 本周」的计算边界。";
    }
    return next;
  }, [studyDays, dailyMinutes, timezone, confirmed]);

  const submit = useCallback(async () => {
    const nextErrors = validate();
    const hasError =
      nextErrors.studyDays !== null ||
      nextErrors.dailyMinutes !== null ||
      nextErrors.timezone !== null;
    setErrors(nextErrors);
    if (hasError || saving) {
      return;
    }
    setSaving(true);
    setSaveFailure(null);
    const result = await apiRequest<UsersMe>("/api/v1/users/me/profile", {
      method: "PUT",
      body: {
        study_days: sortDays(studyDays),
        daily_minutes: Number(dailyMinutes),
        timezone,
        timezone_confirmed: true,
      },
      parse: parseUsersMe,
    });
    setSaving(false);
    if (!result.ok) {
      setSaveFailure(result.failure);
      return;
    }
    router.push("/diagnostic");
  }, [validate, saving, studyDays, dailyMinutes, timezone, router]);

  const days = sortDays(studyDays);
  const minutesNumber = Number(dailyMinutes);
  const weeklyEstimate =
    days.length > 0 && Number.isFinite(minutesNumber) && minutesNumber > 0
      ? days.length * minutesNumber
      : 0;

  if (loadState === "loading") {
    return (
      <LoadingPanel
        title="正在读取学习档案"
        description="从 GET /api/v1/users/me 读取已保存的档案，用于预填表单。"
        rows={4}
      />
    );
  }

  return (
    <div className="space-y-6">
      {loadState === "failed" ? (
        <ErrorPanel
          failure={loadFailure}
          title="服务未就绪：无法读取已保存档案"
          onRetry={reload}
          extra={<p>表单已用契约中的默认值填充（study_days {DEFAULT_DAYS.join(",")} / {DEFAULT_MINUTES} 分钟 / {DEFAULT_TIMEZONE}），你可以先检查交互；保存时接口若仍不可用会给出可重试的错误。</p>}
        />
      ) : null}

      <Card>
        <CardHeader
          title="学习档案"
          description="三个字段都会写入 user_profiles 与 users.timezone_source。"
          action={<Tag>第 1 步 · 共 3 步</Tag>}
        />
        <CardBody className="space-y-6">
          <div>
            <p className="text-[12px] font-medium text-fg" id="study-days-label">
              学习日（可选 1–7 天，至少 1 天）
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted" id="study-days-hint">
              只有被选中的星期会分配学习内容，非学习日不排任何计划项。
            </p>
            <div
              role="group"
              aria-labelledby="study-days-label"
              aria-describedby={errors.studyDays ? "study-days-error" : "study-days-hint"}
              className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
            >
              {WEEKDAYS.map((day) => {
                const checked = days.indexOf(day.value) >= 0;
                return (
                  <label
                    key={day.value}
                    htmlFor={"study-day-" + String(day.value)}
                    className={
                      "flex cursor-pointer items-center gap-2 rounded-control border px-3 py-2 text-[12px] transition-colors " +
                      (checked
                        ? "border-accent bg-accent-soft text-fg"
                        : "border-line bg-surface text-fg hover:bg-elevated")
                    }
                  >
                    <input
                      id={"study-day-" + String(day.value)}
                      type="checkbox"
                      checked={checked}
                      aria-invalid={errors.studyDays ? true : undefined}
                      onChange={() => toggleDay(day.value)}
                      className="size-3.5 shrink-0 accent-[var(--accent)]"
                    />
                    <span>{day.label}</span>
                  </label>
                );
              })}
            </div>
            {errors.studyDays ? (
              <p id="study-days-error" role="alert" className="mt-2 text-[11px] leading-relaxed text-danger-text">
                {errors.studyDays}
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="daily-minutes"
              label="每个学习日可投入分钟数（15–480）"
              hint="只用于计算每周容量，不做进度催促。"
              error={errors.dailyMinutes}
            >
              <TextInput
                id="daily-minutes"
                type="number"
                inputMode="numeric"
                min={15}
                max={480}
                step={5}
                value={dailyMinutes}
                invalid={errors.dailyMinutes !== null}
                {...fieldAria("daily-minutes", errors.dailyMinutes, true)}
                onChange={(event) => {
                  setDailyMinutes(event.target.value);
                  setErrors((previous) => ({ ...previous, dailyMinutes: null }));
                }}
                className={fieldClass(errors.dailyMinutes !== null) + " font-mono"}
              />
            </Field>

            <Field
              id="timezone"
              label="时区"
              hint="「今天 / 本周」一律按此时区计算；未确认前不展示任何按周或按天的推导。"
              error={errors.timezone}
            >
              <Select
                id="timezone"
                value={timezone}
                invalid={errors.timezone !== null && !confirmed}
                {...fieldAria("timezone", errors.timezone, true)}
                onChange={(event) => {
                  setTimezone(event.target.value);
                  setConfirmed(false);
                  setErrors((previous) => ({ ...previous, timezone: null }));
                }}
              >
                {TIMEZONE_OPTIONS.map((zone) => (
                  <option key={zone.value} value={zone.value}>
                    {zone.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="rounded-control border border-line bg-surface px-4 py-3">
            <label htmlFor="timezone-confirm" className="flex cursor-pointer items-start gap-2.5">
              <input
                id="timezone-confirm"
                type="checkbox"
                checked={confirmed}
                aria-invalid={errors.timezone ? true : undefined}
                aria-describedby={errors.timezone ? "timezone-confirm-error" : "timezone-confirm-hint"}
                onChange={(event) => {
                  setConfirmed(event.target.checked);
                  setErrors((previous) => ({
                    ...previous,
                    timezone: event.target.checked ? null : previous.timezone,
                  }));
                }}
                className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
              />
              <span className="min-w-0">
                <span className="block text-[12px] font-medium text-fg">
                  我确认我的时区是 {timezoneLabel(timezone)}
                </span>
                <span id="timezone-confirm-hint" className="mt-1 block text-[11px] leading-relaxed text-muted">
                  勾选后保存时提交 timezone_confirmed=true，后端写入 users.timezone_source=&apos;user_confirmed&apos;。
                </span>
              </span>
            </label>
            {errors.timezone ? (
              <p id="timezone-confirm-error" role="alert" className="mt-2 text-[11px] leading-relaxed text-danger-text">
                {errors.timezone}
              </p>
            ) : null}
          </div>

          <dl className="grid grid-cols-2 gap-3 border-t border-line pt-4 text-[11px] sm:grid-cols-3">
            <div>
              <dt className="text-muted">学习日</dt>
              <dd className="mt-0.5 text-[12px] font-medium text-fg">
                {days.length > 0 ? days.map((day) => weekdayLabel(day)).join("、") : "未选择"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">每周可用时长（估算）</dt>
              <dd className="mt-0.5 font-mono text-[12px] font-medium text-fg">
                {weeklyEstimate > 0 ? String(weeklyEstimate) + " 分钟" : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">时区确认</dt>
              <dd className="mt-0.5 text-[12px] font-medium text-fg">
                {confirmed ? "已确认" : "未确认"}
              </dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      {saveFailure ? (
        <ErrorPanel failure={saveFailure} title="保存失败" onRetry={() => void submit()} />
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={() => void submit()} disabled={saving}>
          {saving ? "正在保存…" : "保存并进入诊断"}
        </Button>
        <Button variant="secondary" onClick={reload} disabled={saving}>
          重新读取已保存档案
        </Button>
        <Link
          href="/diagnostic"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          已有档案，直接进入诊断
        </Link>
      </div>

      {confirmed ? null : (
        <Alert tone="warning" title="保存前需要显式确认时区">
          <p>未确认时区时，页面不会展示任何「今天 / 本周」的推导数据（契约 I7）。</p>
        </Alert>
      )}
    </div>
  );
}
