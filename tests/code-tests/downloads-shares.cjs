const assert = require("node:assert/strict");
const fs = require("node:fs");

const source = fs.readFileSync("src/chatshare/assets/dufs/manage.js", "utf8");
for (const contract of [
  '"/_chatshare/downloads"',
  '"/_chatshare/shares"',
  '"X-CSRF-Token"',
  'credentials: "same-origin"',
  '总大小未知',
  '分享链接是访问凭证',
  'completed',
  'cancelled',
  'interrupted',
  'document.createElement("progress")',
  '复制链接',
  'chatshare-actions',
  'navigator.clipboard.writeText',
  '["failed", "cancelled", "interrupted"].includes(job.state)',
]) assert.ok(source.includes(contract), `missing UI contract: ${contract}`);

assert.ok(source.includes("textContent"));
assert.ok(!source.includes("innerHTML"));
assert.ok(!source.includes('onclick="'));
assert.ok(!source.includes("localStorage"));
assert.ok(!source.includes("sessionStorage"));
console.log("Download jobs and directory-share UI contracts passed");
