"use strict";
try { sessionStorage.removeItem("chatshare.dufs.credentials"); } catch {}
document.querySelector("form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  document.querySelector("#error").textContent = "";
  try {
    const sessionResponse = await fetch("/_chatshare/session", { credentials: "same-origin", cache: "no-store" });
    const session = await sessionResponse.json();
    const response = await fetch("/_chatshare/login", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token || "" },
      body: JSON.stringify({ username: form.username.value, password: form.password.value }),
    });
    form.password.value = "";
    if (!response.ok) throw new Error(response.status === 429 ? "登录尝试过多，请稍后重试。" : "登录失败，请检查用户名和密码。 ");
    const next = new URLSearchParams(location.search).get("next") || "/";
    const target = new URL(next, location.origin);
    location.replace(target.origin === location.origin && next.startsWith("/") && !next.startsWith("//") ? target.href : "/");
  } catch (error) {
    form.password.value = "";
    document.querySelector("#error").textContent = error.message || "登录失败，请稍后重试。";
  } finally {
    button.disabled = false;
  }
});
