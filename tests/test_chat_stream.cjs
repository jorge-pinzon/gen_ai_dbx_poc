const assert = require("node:assert/strict");
const test = require("node:test");
const { consume } = require("../src/mariner_genai_dbx/static/chat-stream.js");

test("browser script exposes the consume function on window", async () => {
  const fs = require("fs");
  const vm = require("vm");
  const window = {};
  vm.runInNewContext(
    fs.readFileSync(require.resolve("../src/mariner_genai_dbx/static/chat-stream.js"), "utf8"),
    { window, TextDecoder },
  );
  assert.equal(typeof window.MarinerChatStream.consume, "function");
  const events = [];
  await window.MarinerChatStream.consume(
    responseFor('event: done\ndata: {}\n\n'),
    (event) => events.push(event),
  );
  assert.deepEqual(events, ["done"]);
});

function responseFor(text, chunkSize = 7) {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  const reader = {
    cancelled: false,
    released: false,
    async read() {
      if (offset >= bytes.length) return { done: true };
      const value = bytes.slice(offset, offset + chunkSize);
      offset += chunkSize;
      return { value, done: false };
    },
    async cancel() { this.cancelled = true; },
    releaseLock() { this.released = true; },
  };
  return { body: { getReader: () => reader }, reader };
}

test("handles split UTF-8 and SSE frames; delivers answer before sources", async () => {
  const response = responseFor(
    'event: answer\r\ndata: {"answer":"Coaching…","citationStatus":"pending"}\r\n\r\n' +
    'event: sources\ndata: {"sources":[{"label":"Policy"}]}\n\n' +
    'event: done\ndata: {}\n\n', 1);
  const events = [];
  await consume(response, (event, data) => events.push([event, data]));
  assert.deepEqual(events.map(([event]) => event), ["answer", "sources", "done"]);
  assert.equal(events[0][1].answer, "Coaching…");
  assert.equal(response.reader.released, true);
});

test("rejects a disconnected stream instead of treating the draft as complete", async () => {
  const response = responseFor('event: answer\ndata: {"answer":"Draft"}\n\n');
  await assert.rejects(consume(response, () => {}), /interrupted/);
  assert.equal(response.reader.cancelled, true);
});

test("reports citation failure after delivering the pending answer", async () => {
  const response = responseFor('event: answer\ndata: {"answer":"Draft"}\n\n' +
    'event: error\ndata: {"message":"Sources could not be verified"}\n\n');
  const events = [];
  await assert.rejects(consume(response, (event) => events.push(event)), /could not be verified/);
  assert.deepEqual(events, ["answer", "error"]);
});

test("rejects malformed data and releases the reader", async () => {
  const response = responseFor('event: answer\ndata: {broken}\n\n');
  await assert.rejects(consume(response, () => {}));
  assert.equal(response.reader.released, true);
});
