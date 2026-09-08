const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("src/chatshare/assets/dufs/index.js", "utf8");

async function exercise(gateway) {
  const removed = [];
  const stored = [];
  const replaced = [];
  const listeners = {};
  const calls = [];
  const location = { search: "", pathname: "/folder/", href: "https://share.example/folder/", origin: "https://share.example", replace: value => replaced.push(value), reload: () => replaced.push("reload") };
  const context = vm.createContext({
    URL, URLSearchParams, TextEncoder, console,
    btoa: value => Buffer.from(value, "binary").toString("base64"),
    location,
    window: { location, addEventListener: (name, callback) => { listeners[name] = callback; } },
    document: {
      querySelector: () => gateway ? {} : null,
      documentElement: { style: {} },
      body: { replaceChildren: () => calls.push("clear-body") },
    },
    sessionStorage: {
      getItem: () => JSON.stringify({ username: "legacy", password: "test-only" }),
      setItem: (...args) => stored.push(args),
      removeItem: key => removed.push(key),
    },
    fetch: async (url, options) => {
      calls.push([url, options]);
      return { ok: true, json: async () => ({ authenticated: true, username: "alice" }) };
    },
  });
  vm.runInContext(source, context);
  const xhr = { headers: {}, open() {}, setRequestHeader(name, value) { this.headers[name] = value; }, addEventListener(name, callback) { this[name] = callback; } };
  context.xhr = xhr;
  vm.runInContext('openWithCredentials(xhr, "PUT", "/file")', context);
  if (gateway) {
    assert.deepEqual(removed, ["chatshare.dufs.credentials"]);
    assert.equal(vm.runInContext("getStoredCredentials()", context), null);
    vm.runInContext('storeCredentials({username: "new", password: "not-stored"})', context);
    assert.equal(stored.length, 0);
    assert.deepEqual(xhr.headers, { "X-ChatShare-CSRF": "1" });
    assert.equal(xhr.withCredentials, true);
    xhr.status = 401;
    xhr.load();
    assert.ok(replaced.pop().startsWith("/_chatshare/login?next="));
    assert.equal((await vm.runInContext("gatewaySession()", context)).username, "alice");
    await vm.runInContext("logout()", context);
    assert.equal(replaced.pop(), "/_chatshare/login");
    assert.ok(calls.includes("clear-body"));
    listeners.pageshow({ persisted: true });
    assert.equal(replaced.pop(), "reload");
    assert.ok(!source.includes('onclick="'));
  } else {
    assert.equal(removed.length, 0);
    assert.ok(xhr.headers.Authorization.startsWith("Basic "));
    assert.equal(vm.runInContext("getStoredCredentials().username", context), "legacy");
  }
}

exercise(true).then(() => exercise(false)).then(() => console.log("gateway and native UI contracts passed"));
