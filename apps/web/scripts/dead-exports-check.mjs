/**
 * 找出「导出但从不被其它文件引用」的符号（死导出）。
 *
 * 零依赖、基于正则的启发式检查：能抓住真正的遗留导出（本项目已经用它清掉 13 个），
 * 但无法覆盖动态引用。因此它是「发布前自查」，不作为 CI 硬门禁。
 *
 * 用法：node scripts/dead-exports-check.mjs
 * 退出码：0 = 没有死导出；1 = 发现死导出（会逐条列出）
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath 会正确解码：仓库路径含中文，直接取 URL.pathname 会得到 %E8%87%AA… 而读不到目录。
const ROOT = fileURLToPath(new URL('../src/', import.meta.url));

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      walk(full, out);
    } else if (name.endsWith('.ts') || name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

const files = walk(ROOT);
const sources = new Map(files.map((f) => [f, readFileSync(f, 'utf8')]));
const DECL = /^export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)/gm;

const dead = [];
let total = 0;
for (const [file, text] of sources) {
  for (const match of text.matchAll(DECL)) {
    const name = match[1];
    total += 1;
    const pattern = new RegExp('\\b' + name + '\\b');
    let usedElsewhere = false;
    for (const [other, otherText] of sources) {
      if (other !== file && pattern.test(otherText)) {
        usedElsewhere = true;
        break;
      }
    }
    const ownUses = (text.match(new RegExp('\\b' + name + '\\b', 'g')) || []).length;
    if (!usedElsewhere && ownUses <= 1) {
      dead.push({ file: relative(ROOT, file), name });
    }
  }
}

for (const item of dead) {
  console.log('DEAD  ' + item.file + ' -> ' + item.name);
}
console.log('');
console.log('exports scanned: ' + total + ' | dead exports: ' + dead.length);
process.exit(dead.length === 0 ? 0 : 1);