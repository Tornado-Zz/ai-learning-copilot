import type { SVGProps } from "react";
import { cx } from "@/components/ui";

type IconProps = SVGProps<SVGSVGElement>;

function iconClass(className?: string): string {
  return cx("size-4 shrink-0", className);
}

function Svg({ className, children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={iconClass(className)}
      {...props}
    >
      {children}
    </svg>
  );
}

export function LogoGlyph({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cx("size-3.5", className)}
    >
      <path d="M4 13.6l3.2-3.7 2.7 2.5L16 5.4" />
      <path d="M12.2 5.4H16v3.8" />
    </svg>
  );
}

export function IconToday({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <path d="M3.5 10h17M8.5 3.5V6M15.5 3.5V6" />
      <path d="M8.6 14.4l2.3 2.3 4.5-4.6" />
    </Svg>
  );
}

export function IconLearn({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M12 6.6C10.4 5.5 8.4 5 6.3 5H4v13.4h2.3c2.1 0 4.1.5 5.7 1.6 1.6-1.1 3.6-1.6 5.7-1.6H20V5h-2.3c-2.1 0-4.1.5-5.7 1.6z" />
      <path d="M12 6.6V20" />
    </Svg>
  );
}

export function IconPractice({ className }: IconProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="8.2" />
      <circle cx="12" cy="12" r="3.2" />
    </Svg>
  );
}

export function IconProjects({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M12 3.2l8.2 4.4-8.2 4.4L3.8 7.6z" />
      <path d="M3.8 12l8.2 4.4 8.2-4.4" />
      <path d="M3.8 16.4L12 20.8l8.2-4.4" />
    </Svg>
  );
}

export function IconProgress({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M5 20V10.5M12 20V4.5M19 20v-6.5" />
    </Svg>
  );
}

export function IconSun({ className }: IconProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
    </Svg>
  );
}

export function IconMoon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M20 14.4A8.4 8.4 0 0 1 9.6 4a8.4 8.4 0 1 0 10.4 10.4z" />
    </Svg>
  );
}

export function IconMonitor({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect x="3" y="4.5" width="18" height="12" rx="2" />
      <path d="M9 20h6M12 16.5V20" />
    </Svg>
  );
}

export function IconMenu({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  );
}

export function IconClose({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function IconArrowRight({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4.5 12h14M13 6.5l5.5 5.5L13 17.5" />
    </Svg>
  );
}

export function IconCheck({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M5 12.5l4.5 4.5L19 6.5" />
    </Svg>
  );
}

export function IconProfile({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect x="3.2" y="5" width="17.6" height="14" rx="2.2" />
      <circle cx="8.6" cy="10.4" r="2" />
      <path d="M5.6 16c.5-1.6 1.6-2.4 3-2.4s2.5.8 3 2.4" />
      <path d="M14.2 10h4.2M14.2 13.4h4.2" />
    </Svg>
  );
}

export function IconQuiz({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M7.5 6.5h12M7.5 12h12M7.5 17.5h12" />
      <path d="M4.2 6.5l.9.9 1.6-1.8M4.2 12l.9.9 1.6-1.8M4.2 17.5l.9.9 1.6-1.8" />
    </Svg>
  );
}

export function IconHistory({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M3.6 12a8.4 8.4 0 1 0 2.6-6.1" />
      <path d="M3.4 4.6v4h4" />
      <path d="M12 8.2V12l3 1.8" />
    </Svg>
  );
}

export function IconRoute({ className }: IconProps) {
  return (
    <Svg className={className}>
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="18" cy="18" r="2.2" />
      <path d="M6 8.2v4.3c0 1.6 1.3 2.9 2.9 2.9h4.4" />
      <path d="M11.6 13.2l2.2 2.2-2.2 2.2" />
    </Svg>
  );
}

export function IconKnowledge({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect x="3.4" y="4.6" width="11.4" height="10.4" rx="2" />
      <path d="M3.4 8.2h11.4" />
      <circle cx="15.2" cy="14.6" r="3.4" />
      <path d="M17.7 17.1l2.5 2.5" />
    </Svg>
  );
}

export function IconSpark({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z" />
      <path d="M18.5 16.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </Svg>
  );
}
