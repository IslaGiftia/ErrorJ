// 把 .tmp-mobile-audit/report.json 压成可读清单
import { readFile } from "node:fs/promises";

const report = JSON.parse(await readFile(".tmp-mobile-audit/report.json", "utf-8"));
const kinds = new Map();
for (const run of report.runs) {
  for (const issue of run.metrics.issues) {
    if (!kinds.has(issue.kind)) kinds.set(issue.kind, []);
    kinds.get(issue.kind).push({ where: `${run.viewport}/${run.page}`, ...issue });
  }
}

console.log(`浏览器: ${report.browser}`);
console.log(`运行组合: ${report.runs.length}\n`);

for (const [kind, items] of [...kinds.entries()].sort()) {
  const mobile = items.filter((i) => !i.where.startsWith("1440x900"));
  console.log(`## ${kind} — 共 ${items.length} 处（移动端 ${mobile.length} 处）`);
  for (const item of mobile.slice(0, 6)) {
    const detail = item.detail || "";
    console.log(`   ${item.where} [${item.severity}] ${detail}`);
    for (const one of (item.items || []).slice(0, 3)) {
      console.log(`     · ${JSON.stringify(one)}`);
    }
  }
  if (mobile.length > 6) console.log(`   ... 其余 ${mobile.length - 6} 处`);
  console.log();
}

// 固定栏与底部遮挡概览
console.log("## 固定栏概览（底部）");
for (const run of report.runs) {
  const bars = run.metrics.stats.bottomBars || [];
  if (!bars.length) continue;
  const desc = bars.map((b) => `${b.el} h=${b.height}`).join(" | ");
  console.log(`   ${run.viewport}/${run.page}: ${desc}`);
}

console.log("\n## 事件统计");
const evCount = new Map();
for (const run of report.runs) {
  for (const ev of run.events) {
    const key = `${ev.type}`;
    evCount.set(key, (evCount.get(key) || 0) + 1);
  }
}
console.log(Object.fromEntries(evCount));
const favicon404 = report.runs.flatMap((r) => r.events).filter((e) => /favicon/.test(e.text || ""));
console.log(`其中 favicon 相关 404: ${favicon404.length} 条`);
