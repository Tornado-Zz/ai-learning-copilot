/**
 * 依赖安全基线检查。
 *
 * 两件事：
 *   1. 运行时依赖（npm audit --omit=dev）必须为 0 —— 这是硬门禁。
 *   2. 开发依赖的告警数不得高于基线文件，新增的必须人工复核后显式调整基线。
 *
 * 为什么分开：当前 16 个 moderate 全部在 ESLint 开发链（minimatch 经 eslint-config-next
 * 传递引入），不进产物、不接收用户输入；而运行时依赖只有 next / react / react-dom，干净。
 * 混在一起报「16 个漏洞」会让人误以为线上有问题，实际上不是。
 *
 * 用法：node scripts/audit-check.mjs
 * 退出码：0 = 符合基线；1 = 出现运行时告警或开发依赖告警增加；2 = 审计不可用（离线等）
 */
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const HERE = fileURLToPath(new URL('.', import.meta.url));
const BASELINE = join(HERE, '..', 'security-baseline.json');

// Windows 上 npm 是 npm.cmd。Node 18.20 起（CVE-2024-27980）**默认拒绝**执行
// .cmd/.bat，必须给 shell: true，否则 spawn 直接 ENOENT。这与 start-dev.ps1 里
// Start-Process 不能直接启动 npm 是同一类问题，只是报错方式不同。
const NPM = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const SHELL = { shell: true };

function audit(extraArgs) {
  try {
    const out = execFileSync(NPM, ['audit', '--json', ...extraArgs], {
      cwd: join(HERE, '..'),
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      maxBuffer: 32 * 1024 * 1024,
      ...SHELL,
    });
    return JSON.parse(out);
  } catch (error) {
    // npm audit 在有告警时退出码非 0，但 stdout 仍是完整 JSON。
    if (error && typeof error.stdout === 'string' && error.stdout.trim().startsWith('{')) {
      return JSON.parse(error.stdout);
    }
    return null;
  }
}

const runtime = audit(['--omit=dev']);
const all = audit([]);
if (!runtime || !all) {
  console.log('审计不可用（可能处于离线状态），本次未做检查。');
  process.exit(2);
}

const runtimeTotal = runtime.metadata.vulnerabilities.total;
const allTotal = all.metadata.vulnerabilities.total;
const bySeverity = all.metadata.vulnerabilities;

console.log('运行时依赖告警 : ' + runtimeTotal);
console.log('全部依赖告警   : ' + allTotal + ' ' + JSON.stringify({
  critical: bySeverity.critical,
  high: bySeverity.high,
  moderate: bySeverity.moderate,
  low: bySeverity.low,
}));

const baseline = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : null;
const allowed = baseline ? baseline.dev.total : 0;
console.log('基线（开发依赖）: ' + allowed + (baseline ? '  ' + baseline.dev.note : '（无基线文件）'));

let failed = false;
if (runtimeTotal > 0) {
  console.log('');
  console.log('FAIL  运行时依赖出现告警，必须修复后才可发布。');
  failed = true;
}
if (allTotal > allowed) {
  console.log('');
  console.log('FAIL  开发依赖告警由 ' + allowed + ' 增加到 ' + allTotal + '，请复核新告警后再更新基线。');
  failed = true;
}
if (!failed && allTotal < allowed) {
  console.log('');
  console.log('NOTE  告警数低于基线（' + allTotal + ' < ' + allowed + '），可考虑下调基线。');
}
if (failed) process.exit(1);
console.log('');
console.log('符合基线。');
process.exit(0);