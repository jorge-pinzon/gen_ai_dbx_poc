const assert = require("node:assert/strict");
const test = require("node:test");

const { parse, parseChartSpec, render } = require("../src/mariner_genai_dbx/static/markdown.js");

class FakeNode {
  constructor(tagName = null, text = null) {
    this.tagName = tagName;
    this.text = text;
    this.children = [];
    this.attributes = {};
    this.className = "";
    this.dataset = {};
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  set textContent(value) {
    this.children = [new FakeNode(null, String(value))];
  }
}

global.document = {
  createElement: (tagName) => new FakeNode(tagName),
  createTextNode: (text) => new FakeNode(null, text),
};

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}

test("parses a standard table and detects its numeric column", () => {
  const blocks = parse(`| Region | Region Name | Employees |
|--------|-------------|----------|
| REG001 | Great Lakes Region | 12 |
| REG002 | Southwest Region | 11 |`);

  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "table");
  assert.deepEqual(blocks[0].alignments, ["left", "left", "right"]);
  assert.equal(blocks[0].rows[1][2], "11");
});

test("preserves text surrounding a right-aligned table", () => {
  const blocks = parse(`Here are the results:

| Region | Employees |
|-------|----------:|
| Great Lakes | 12 |
| Southwest | 11 |

The total is 23 employees.`);

  assert.deepEqual(blocks.map((block) => block.type), ["paragraph", "table", "paragraph"]);
  assert.equal(blocks[1].alignments[1], "right");
});

test("preserves inline Markdown within aligned table cells", () => {
  const blocks = parse(`| Region | Employees |
|:-------|----------:|
| REG001 | **12** |
| REG002 | **11** |
| **Total** | **23** |`);

  assert.deepEqual(blocks[0].alignments, ["left", "right"]);
  assert.equal(blocks[0].rows[2][0], "**Total**");
  assert.equal(blocks[0].rows[2][1], "**23**");
});

test("keeps a normal conversational answer as a paragraph", () => {
  const blocks = parse("Jamie Ortiz's latest review is available.");

  assert.deepEqual(blocks, [
    { type: "paragraph", lines: ["Jamie Ortiz's latest review is available."] },
  ]);
});

test("parses headings, tables, and bullet lists in one answer", () => {
  const blocks = parse(`## Regional performance

| Region | Employees |
|--------|----------:|
| Great Lakes | **12** |

- Current reporting period
- Synthetic test data`);

  assert.deepEqual(blocks.map((block) => block.type), ["heading", "table", "list"]);
  assert.equal(blocks[2].ordered, false);
});

test("does not classify a malformed table as a table", () => {
  const blocks = parse(`| Region | Employees |
| invalid separator |
| Great Lakes | 12 |`);

  assert.equal(blocks.some((block) => block.type === "table"), false);
});

test("renders tables into a responsive container with semantic cells", () => {
  const container = new FakeNode("article");
  render(container, `| Region | Employees |
|--------|----------:|
| Great Lakes | **12** |`);

  const nodes = descendants(container);
  assert.equal(nodes.some((node) => node.className === "table-container"), true);
  assert.equal(nodes.filter((node) => node.tagName === "table").length, 1);
  assert.equal(nodes.filter((node) => node.tagName === "th").length, 2);
  assert.equal(nodes.filter((node) => node.tagName === "td").length, 2);
  assert.equal(nodes.some((node) => node.tagName === "strong"), true);
});

test("renders raw HTML as text and rejects unsafe link protocols", () => {
  const container = new FakeNode("article");
  render(container, `<img src=x onerror=alert(1)> [open](javascript:alert(1))`);

  const nodes = descendants(container);
  assert.equal(nodes.some((node) => node.tagName === "img"), false);
  assert.equal(nodes.some((node) => node.tagName === "a"), false);
  assert.equal(
    nodes.some((node) => node.text?.includes("<img src=x onerror=alert(1)>")),
    true,
  );
});

test("parses a validated mariner chart payload", () => {
  const markdown = `\`\`\`mariner-chart
{"type":"bar","title":"Loans by branch","xLabel":"Branch","yLabel":"Loans per month","unit":"loans","labels":["Dallas","Plano"],"values":[10.8,6.3]}
\`\`\``;
  const blocks = parse(markdown);

  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "chart");
  assert.deepEqual(blocks[0].chart.values, [10.8, 6.3]);
});

test("renders a chart payload as accessible bars", () => {
  const container = new FakeNode("article");
  render(container, `\`\`\`mariner-chart
{"type":"bar","title":"Loans by branch","xLabel":"Branch","yLabel":"Loans per month","labels":["Dallas","Plano"],"values":[10.8,6.3]}
\`\`\``);

  const nodes = descendants(container);
  const figure = nodes.find((node) => node.className === "bar-chart");
  assert.equal(figure.attributes.role, "img");
  assert.equal(nodes.filter((node) => node.className === "bar-chart-row").length, 2);
  assert.equal(nodes.filter((node) => node.className === "bar-chart-bar").length, 2);
});

test("rejects unsafe or malformed chart payloads", () => {
  assert.equal(
    parseChartSpec({ type: "bar", labels: ["A"], values: [1] }),
    null,
  );
  const blocks = parse(`\`\`\`mariner-chart
{"type":"bar","title":"Invalid","labels":["A"],"values":[-1]}
\`\`\``);
  assert.equal(blocks[0].type, "code");
});
