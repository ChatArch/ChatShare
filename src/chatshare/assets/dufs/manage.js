(() => {
  "use strict";
  const panel = document.getElementById("chatshare-manage");
  if (!panel) return;
  const directory = panel.dataset.directory;
  const jobsNode = document.getElementById("chatshare-downloads");
  const sharesNode = document.getElementById("chatshare-shares");
  const states = { queued: "排队中", downloading: "下载中", committing: "提交中", completed: "已完成", failed: "失败", cancelled: "已取消", interrupted: "已中断" };
  const actions = document.createElement("div");
  actions.className = "chatshare-actions";
  actions.append(document.getElementById("chatshare-download-open"), document.getElementById("chatshare-share-create"));
  const uploadPanel = document.querySelector(".upload-panel");
  if (uploadPanel) uploadPanel.insertAdjacentElement("afterend", actions);
  else panel.prepend(actions);

  async function request(url, options = {}) {
    const session = await gatewaySession();
    const headers = { ...(options.headers || {}) };
    if (options.method && !["GET", "HEAD"].includes(options.method)) headers["X-CSRF-Token"] = session.csrf_token;
    const response = await fetch(url, { ...options, headers, credentials: "same-origin", cache: "no-store" });
    if (response.status === 401) return gatewayLogin();
    if (!response.ok) {
      let message = `请求失败 (${response.status})`;
      try { message = (await response.json()).error || message; } catch (_) {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }

  function formatBytes(value) {
    if (!Number.isFinite(value)) return "未知大小";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return `${value.toLocaleString(undefined, { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
  }

  async function renderJobs() {
    const { jobs } = await request("/_chatshare/downloads");
    jobsNode.replaceChildren(text("h3", "链接下载任务"));
    for (const job of jobs) {
      const row = text("div", "", "chatshare-job");
      row.append(text("strong", `${job.target} · ${states[job.state] || job.state}`));
      const bar = document.createElement("progress");
      bar.setAttribute("aria-label", "下载进度");
      if (job.total != null) {
        bar.max = job.total > 0 ? job.total : 1;
        bar.value = job.total > 0 ? Math.min(job.transferred, job.total) : (job.state === "completed" ? 1 : 0);
      } else if (job.state === "completed") {
        bar.max = 1; bar.value = 1;
      } else if (["failed", "cancelled", "interrupted"].includes(job.state)) {
        bar.max = 1; bar.value = 0;
      }
      row.append(bar);
      const progress = job.total == null ? `${formatBytes(job.transferred)}（总大小未知）` : `${formatBytes(job.transferred)} / ${formatBytes(job.total)}`;
      const speed = job.state === "downloading" ? ` · ${formatBytes(job.speed)}/s` : "";
      row.append(text("div", `${progress}${speed} · 来源 ${job.source_host}`));
      if (job.error) row.append(text("div", job.error, "chatshare-error"));
      if (["queued", "downloading"].includes(job.state)) {
        const cancel = text("button", "取消");
        cancel.type = "button";
        cancel.addEventListener("click", async () => { await request(`/_chatshare/downloads/${job.id}`, { method: "DELETE" }); await renderJobs(); });
        row.append(cancel);
      }
      if (job.state === "completed") {
        const link = text("a", "打开文件");
        link.href = "/" + job.target.split("/").map(encodeURIComponent).join("/");
        row.append(link);
      }
      jobsNode.append(row);
    }
  }

  document.getElementById("chatshare-download-open").addEventListener("click", () => {
    if (panel.querySelector("form")) return;
    const form = document.createElement("form");
    const url = document.createElement("input");
    url.type = "url"; url.required = true; url.placeholder = "HTTP/HTTPS 文件直链"; url.setAttribute("aria-label", "下载链接");
    const target = document.createElement("input");
    target.required = true; target.value = directory.replace(/^\//, ""); target.placeholder = "当前目录中的目标文件名"; target.setAttribute("aria-label", "目标路径");
    const submit = text("button", "创建下载任务"); submit.type = "submit";
    form.append(url, target, submit);
    form.addEventListener("submit", async event => {
      event.preventDefault(); submit.disabled = true;
      try { await request("/_chatshare/downloads", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.value, target: target.value }) }); form.remove(); await renderJobs(); }
      catch (error) { form.append(text("div", error.message, "chatshare-error")); submit.disabled = false; }
    });
    panel.insertBefore(form, jobsNode);
    panel.scrollIntoView({ block: "start", behavior: "smooth" });
    url.focus();
  });

  async function renderShares() {
    const { shares } = await request("/_chatshare/shares");
    sharesNode.replaceChildren(text("h3", "目录分享"), text("p", "分享链接是访问凭证；撤销只关闭目录浏览，已有文件直链仍然公开。", "warning"));
    for (const share of shares.filter(item => item.directory === directory)) {
      const row = text("div", "", "chatshare-share");
      const link = text("a", new URL(share.url, location.origin).href); link.href = share.url;
      const copy = text("button", "复制链接"); copy.type = "button";
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(new URL(share.url, location.origin).href); copy.textContent = "已复制"; }
        catch (_) { copy.textContent = "请选择链接文本复制"; }
      });
      const revoke = text("button", "撤销"); revoke.type = "button";
      revoke.addEventListener("click", async () => { await request(`/_chatshare/shares/${share.id}`, { method: "DELETE" }); await renderShares(); });
      row.append(link, copy, revoke); sharesNode.append(row);
    }
  }

  document.getElementById("chatshare-share-create").addEventListener("click", async () => {
    try { await request("/_chatshare/shares", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ directory }) }); await renderShares(); }
    catch (error) { sharesNode.prepend(text("div", error.message, "chatshare-error")); }
  });

  Promise.all([renderJobs(), renderShares()]).catch(error => panel.append(text("div", error.message, "chatshare-error")));
  setInterval(() => renderJobs().catch(() => {}), 2000);
})();
