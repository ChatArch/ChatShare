const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('src/chatshare/assets/dufs/index.js', 'utf8');
const requests = [];
let headLength = String(2 * 1024 ** 3);
let throwOnSend = false;
class FakeXHR {
  constructor() {
    this.upload = { addEventListener: (name, fn) => { this.upload[name] = fn; } };
    this.handlers = {};
    this.status = 0;
    this.statusText = '';
    requests.push(this);
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader() {}
  getResponseHeader(name) { return name.toLowerCase() === 'content-length' ? headLength : null; }
  send(body) {
    if (throwOnSend) throw new Error('The selected file could not be read');
    this.body = body;
    if (this.method === 'HEAD') {
      this.status = 200;
      queueMicrotask(() => this.onload?.());
    }
  }
  emit(name, event) { this.handlers[name]?.(event); }
}
const context = vm.createContext({
  URL, URLSearchParams, TextEncoder, console, XMLHttpRequest: FakeXHR,
  btoa: text => Buffer.from(text, 'binary').toString('base64'),
  window: { location: { search: '', href: 'https://share.example/', origin: 'https://share.example' }, addEventListener() {} },
  location: { search: '', href: 'https://share.example/', origin: 'https://share.example' },
  document: { querySelector: () => null },
  sessionStorage: { getItem: () => null, removeItem() {} },
});
vm.runInContext(source, context);
vm.runInContext('DATA = { href: "/", uri_prefix: "/" }', context);
function makeUploader(size, offset = 0, name = 'large.bin') {
  Object.assign(context, { fileSize: size, fileName: name });
  const u = vm.runInContext('new Uploader({ name: fileName, size: fileSize, slice(start) { return { start }; } }, [])', context);
  u.$uploadStatus = { innerHTML: '' };
  u.uploadOffset = offset;
  vm.runInContext('Uploader.runnings = 1; Uploader.queues = []', context);
  return u;
}
(async () => {
  const size = 11 * 1024 ** 3;
  const u = makeUploader(size);
  u.ajax();
  const xhr = requests.at(-1);
  assert.match(u.$uploadStatus.innerHTML, /<progress\b/);
  assert.match(u.$uploadStatus.innerHTML, /11\s*GB/);
  xhr.upload.progress({ lengthComputable: true, loaded: 2 * 1024 ** 3, total: size });
  assert.match(u.$uploadStatus.innerHTML, /value="18/);
  assert.match(u.$uploadStatus.innerHTML, /2\s*GB.*11\s*GB/);
  xhr.upload.progress({ lengthComputable: true, loaded: size, total: size });
  assert.match(u.$uploadStatus.innerHTML, /等待服务器确认/);
  assert.doesNotMatch(u.$uploadStatus.innerHTML, /上传完成/);
  xhr.readyState = 4; xhr.status = 201; xhr.emit('readystatechange');
  assert.match(u.$uploadStatus.innerHTML, /上传完成/);
  assert.equal(vm.runInContext('Uploader.runnings', context), 0);
  xhr.upload.progress({ loaded: 1, total: size });
  assert.match(u.$uploadStatus.innerHTML, /上传完成/);

  const resumed = makeUploader(size, 2 * 1024 ** 3);
  resumed.ajax();
  const request = requests.at(-1);
  assert.equal(request.method, 'PATCH');
  assert.equal(request.body.start, 2 * 1024 ** 3);
  request.upload.progress({ loaded: 4 * 1024 ** 3, total: size - 2 * 1024 ** 3 });
  assert.match(resumed.$uploadStatus.innerHTML, /6\s*GB.*11\s*GB/);
  request.readyState = 4; request.status = 413; request.statusText = 'Payload Too Large';
  request.emit('readystatechange'); request.emit('error');
  assert.match(resumed.$uploadStatus.innerHTML, /上传失败/);
  assert.doesNotMatch(resumed.$uploadStatus.innerHTML, /上传完成/);
  assert.equal(vm.runInContext('Uploader.runnings', context), 0);

  // Retry must use the real XHR HEAD adapter, then return to scheduler ownership.
  const retry = makeUploader(size);
  retry.finished = true;
  vm.runInContext('Uploader.runQueue = () => {}', context);
  await retry.retry();
  assert.equal(requests.at(-1).method, 'HEAD');
  assert.equal(retry.uploadOffset, 2 * 1024 ** 3);
  assert.equal(vm.runInContext('Uploader.queues.length', context), 1);
  assert.match(retry.$uploadStatus.innerHTML, /排队中/);
  for (const length of [null, '-1', 'NaN', String(size + 1), '1.5', '']) {
    const invalid = makeUploader(size); invalid.finished = true;
    headLength = length;
    await invalid.retry();
    assert.match(invalid.$uploadStatus.innerHTML, /上传失败/);
    assert.equal(vm.runInContext('Uploader.queues.length', context), 0);
  }

  const malicious = makeUploader(10, 0, 'x" onmouseover="alert(1).bin');
  malicious.ajax();
  assert.doesNotMatch(malicious.$uploadStatus.innerHTML, /onmouseover="alert/);

  const unreadable = makeUploader(4 * 1024 ** 3);
  throwOnSend = true;
  assert.doesNotThrow(() => unreadable.ajax());
  throwOnSend = false;
  assert.match(unreadable.$uploadStatus.innerHTML, /上传失败.*selected file/);
  assert.equal(vm.runInContext('Uploader.runnings', context), 0);

  const timeout = makeUploader(size); timeout.ajax();
  requests.at(-1).emit('timeout');
  assert.match(timeout.$uploadStatus.innerHTML, /上传失败/);
  assert.ok(timeout.$uploadStatus.innerHTML.includes(vm.runInContext('encodedStr("上传超时")', context)));
  assert.equal(vm.runInContext('Uploader.runnings', context), 0);

  const disconnected = makeUploader(size); disconnected.ajax();
  requests.at(-1).emit('error');
  assert.match(disconnected.$uploadStatus.innerHTML, /上传失败/);
  assert.ok(disconnected.$uploadStatus.innerHTML.includes(vm.runInContext('encodedStr("网络连接中断")', context)));
  assert.equal(vm.runInContext('Uploader.runnings', context), 0);

  const rows = [];
  const body = { insertAdjacentHTML: (position, html) => rows.push(html) };
  let bodyExists = false;
  const table = {
    querySelector: () => bodyExists ? body : null,
    insertAdjacentHTML: (position, html) => {
      assert.equal(html, '<tbody></tbody>');
      bodyExists = true;
    },
    classList: { remove() {} },
  };
  context.oldTable = table;
  context.emptyFolder = { classList: { add() {} } };
  context.document.getElementById = () => ({ innerHTML: '', addEventListener() {} });
  vm.runInContext('$uploadersTable = oldTable; $emptyFolder = emptyFolder', context);
  makeUploader(size).upload();
  assert.equal(bodyExists, true);
  assert.equal(rows.length, 1);
  assert.match(rows[0], /class="uploader"/);
  assert.equal(vm.runInContext('Uploader.queues.length', context), 1);

  console.log('Upload progress, server confirmation, retry validation and startup failure passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
