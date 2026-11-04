/**
 * 文档一致性检查：把文档里的「数字声明」与实现自动比对。
 *
 * 背景：这个项目多次因为「文档说 A、代码是 B」返工（例如 DATABASE.md 记了 4 张从未
 * 建过的表，README 说集成测试需要预置数据）。人工比对靠不住，所以做成可执行检查。
 *
 * 校验项（全部来自源码，不依赖运行中的服务）：
 *   1. 迁移 head        <-> 文档里 `XXXX_xxx (head)` 的说法
 *   2. 迁移版本数        <-> 「共 N 个版本」
 *   3. 业务表数          <-> 「N 张业务表」
 *   4. 接口操作数/路径数  <-> 「N 个操作 / M 条路径」
 *   5. 前端页面路由数    <-> 「N 条页面路由」
 *
 * 用法：node scripts/docs-consistency-check.mjs
 * 退出码：0 = 一致；1 = 发现不一致（逐条列出文件:行号）
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const MIGRATIONS_DIR = join(ROOT, 'apps/api/migrations/versions');
const ROUTES_DIR = join(ROOT, 'apps/api/app/api/v1/routes');
const APP_DIR = join(ROOT, 'apps/web/src/app');

function walk(dir, filter, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, filter, out);
    else if (filter(name)) out.push(full);
  }
  return out;
}

// ---- 实现侧的真值 ----
const migrationFiles = readdirSync(MIGRATIONS_DIR).filter((n) => n.endsWith('.py') && n !== '__init__.py');
const revisions = new Map();
const pointsTo = new Set();
const tables = new Set();
for (const name of migrationFiles) {
  const text = readFileSync(join(MIGRATIONS_DIR, name), 'utf8');
  // 迁移文件里两种写法都有：`revision = "..."` 与带标注的 `revision: str = "..."`。
  // 只匹配前一种会让 head 静默停在旧版本——检查器自己给出过期真值是最危险的失败方式。
  const rev = text.match(/^revision(?:\s*:\s*[^=\n]+)?\s*=\s*"([^"]+)"/m);
  const down = text.match(/^down_revision(?:\s*:\s*[^=\n]+)?\s*=\s*"([^"]+)"/m);
  if (rev) revisions.set(rev[1], name);
  if (down && down[1] !== 'None') pointsTo.add(down[1]);
  for (const m of text.matchAll(/CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)/g)) tables.add(m[1]);
}
const heads = [...revisions.keys()].filter((r) => !pointsTo.has(r));
const HEAD = heads[0];

const routeFiles = readdirSync(ROUTES_DIR).filter((n) => n.endsWith('.py'));
let operations = 0;
for (const name of routeFiles) {
  const text = readFileSync(join(ROUTES_DIR, name), 'utf8');
  operations += (text.match(/@router\.(get|post|put|patch|delete)\(/g) || []).length;
}
const pageRoutes = walk(APP_DIR, (n) => n === 'page.tsx').length;

// ---- 文档侧的自称 ----
const DOC_FILES = [
  'README.md',
  'CONTRIBUTING.md',
  'SECURITY.md',
  ...readdirSync(join(ROOT, 'docs')).filter((n) => n.endsWith('.md')).map((n) => 'docs/' + n),
];
const docTexts = DOC_FILES.map((rel) => ({ rel, text: readFileSync(join(ROOT, rel), 'utf8') }));

const problems = [];
function scan(pattern, label, expected) {
  for (const { rel, text } of docTexts) {
    const lines = text.split('\n');
    lines.forEach((line, index) => {
      const stripped = line.replace(/\*\*/g, '');
      for (const m of stripped.matchAll(pattern)) {
        const claimed = m[1];
        if (String(claimed) !== String(expected)) {
          problems.push(`${rel}:${index + 1}  ${label} 文档写 ${claimed}，实际 ${expected}`);
        }
      }
    });
  }
}

scan(/(\d+) 个操作/g, '接口操作数', operations);
scan(/(\d+) 张业务表/g, '业务表数', tables.size);
scan(/(\d+) 条页面路由/g, '页面路由数', pageRoutes);
scan(/共 (\d+) 个版本/g, '迁移版本数', migrationFiles.length);
// 刻意不检查「N 节课程 / N 道练习」：这两个数字在文档里既可能是「当前总数」，也可能是
// 「Sprint 7 的目标规模」（PRD 的 60 节）或「结业要求 / 排课规则」（至少 6 道练习、
// 一天最多 1 道）。试过加上，12 条命中全是误报——会喊狼的检查器比没有更糟。

// head 说法：形如 `0010_capstone_review_requires_reviewer (head)`
for (const { rel, text } of docTexts) {
  text.split('\n').forEach((line, index) => {
    for (const m of line.replace(/\*\*/g, '').matchAll(/`([0-9]{4}_[a-z0-9_]+) \(head\)`/g)) {
      if (m[1] !== HEAD) problems.push(`${rel}:${index + 1}  迁移 head 文档写 ${m[1]}，实际 ${HEAD}`);
    }
  });
}

console.log('实现真值：');
console.log('  head        =', HEAD);
console.log('  迁移版本    =', migrationFiles.length);
console.log('  业务表      =', tables.size);
console.log('  接口操作    =', operations);
console.log('  页面路由    =', pageRoutes);
console.log('');
if (problems.length === 0) {
  console.log('文档一致性：全部一致。');
  process.exit(0);
}
for (const p of problems) console.log('MISMATCH  ' + p);
console.log('');
console.log('文档一致性：' + problems.length + ' 处不一致。');
process.exit(1);