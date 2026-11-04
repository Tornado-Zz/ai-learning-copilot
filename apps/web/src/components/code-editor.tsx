"use client";

import { useCallback, useLayoutEffect, useMemo, useRef } from "react";
import type { KeyboardEvent } from "react";

// 代码编辑器不引入任何新依赖：<textarea> 负责输入、选区与浏览器撤销栈，
// 行号侧栏是一列等宽数字，靠相同的字号（13px）与行高（leading-5 = 20px）逐行对齐，
// 纵向滚动时把 textarea 的 scrollTop 同步给侧栏。Tab 键在这里接管（原生 Tab 会离开编辑区），
// 插入两个空格缩进。编辑内容只作为文本提交给后端做模式比对，前端绝不执行它。

const INDENT = "  ";

export function CodeTextarea({
  id,
  value,
  onChange,
  rows = 16,
  describedBy,
  disabled = false,
}: {
  id: string;
  value: string;
  onChange: (next: string) => void;
  rows?: number;
  describedBy?: string;
  disabled?: boolean;
}) {
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const pendingSelection = useRef<[number, number] | null>(null);
  const lineCount = useMemo(() => value.split("\n").length, [value]);
  const lineNumbers = useMemo(
    () => Array.from({ length: lineCount }, (_, index) => index + 1),
    [lineCount],
  );

  // 受控 textarea 重新渲染后光标会跳到末尾，这里在绘制前把光标放回刚插入的位置。
  useLayoutEffect(() => {
    const selection = pendingSelection.current;
    const area = areaRef.current;
    if (!selection || !area) {
      return;
    }
    pendingSelection.current = null;
    area.setSelectionRange(selection[0], selection[1]);
  }, [value]);

  const syncScroll = useCallback(() => {
    const area = areaRef.current;
    const gutter = gutterRef.current;
    if (area && gutter) {
      gutter.scrollTop = area.scrollTop;
    }
  }, []);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Tab" || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      event.preventDefault();
      const area = event.currentTarget;
      const start = area.selectionStart;
      const end = area.selectionEnd;
      const selected = value.slice(start, end);
      if (selected.includes("\n")) {
        // 多行选区：每一行都缩进，并保持选区覆盖同样的文字。
        const indented = selected
          .split("\n")
          .map((line) => INDENT + line)
          .join("\n");
        onChange(value.slice(0, start) + indented + value.slice(end));
        pendingSelection.current = [start, end + INDENT.length * (indented.split("\n").length)];
        return;
      }
      onChange(value.slice(0, start) + INDENT + value.slice(end));
      pendingSelection.current = [start + INDENT.length, start + INDENT.length];
    },
    [onChange, value],
  );

  return (
    <div className="flex overflow-hidden rounded-control border border-line-strong bg-surface">
      <div
        ref={gutterRef}
        aria-hidden="true"
        className="shrink-0 overflow-hidden border-r border-line bg-canvas py-3 pl-3 pr-2 text-right font-mono text-[13px] leading-5 tabular-nums text-muted select-none"
      >
        {lineNumbers.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
      <textarea
        id={id}
        ref={areaRef}
        value={value}
        rows={rows}
        wrap="off"
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        aria-describedby={describedBy}
        disabled={disabled}
        onScroll={syncScroll}
        onKeyDown={handleKeyDown}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-0 flex-1 resize-y bg-transparent px-3 py-3 font-mono text-[13px] leading-5 text-fg"
      />
    </div>
  );
}
