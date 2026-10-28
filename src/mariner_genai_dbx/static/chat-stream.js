(function (root) {
  "use strict";

  async function consume(response, onEvent) {
    if (!response.body?.getReader) throw new Error("Streaming is unavailable in this browser.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed = false;
    try {
      while (!completed) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, "\n");
        if (buffer.length > 2_000_000) throw new Error("The response is too large.");
        let end;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          const lines = frame.split("\n");
          const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
          const dataLines = lines.filter((line) => line.startsWith("data:"));
          if (!dataLines.length) continue;
          const data = JSON.parse(dataLines.map((line) => line.slice(5).trimStart()).join("\n"));
          if (!data || typeof data !== "object" || Array.isArray(data)) {
            throw new Error("The response format is invalid.");
          }
          await onEvent(event, data);
          if (event === "error") throw new Error(data.message || "The request failed.");
          if (event === "done") {
            completed = true;
            break;
          }
        }
        if (done) {
          if (!completed) throw new Error("The response was interrupted before completion.");
          break;
        }
      }
    } finally {
      try { await reader.cancel(); } catch (_) { /* Connection may already be closed. */ }
      reader.releaseLock();
    }
  }

  const api = { consume };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MarinerChatStream = api;
})(typeof window !== "undefined" ? window : globalThis);
