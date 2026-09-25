(function (globalScope) {
  "use strict";

  function splitTableRow(line) {
    let value = line.trim();
    if (value.startsWith("|")) value = value.slice(1);
    if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);

    const cells = [];
    let cell = "";
    let escaped = false;
    let inCode = false;
    for (const character of value) {
      if (escaped) {
        cell += character === "|" ? "|" : `\\${character}`;
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === "`") {
        inCode = !inCode;
        cell += character;
      } else if (character === "|" && !inCode) {
        cells.push(cell.trim());
        cell = "";
      } else {
        cell += character;
      }
    }
    if (escaped) cell += "\\";
    cells.push(cell.trim());
    return cells;
  }

  function separatorAlignment(cell) {
    const marker = cell.trim();
    if (!/^:?-{3,}:?$/.test(marker)) return null;
    if (marker.startsWith(":") && marker.endsWith(":")) return "center";
    if (marker.endsWith(":")) return "right";
    if (marker.startsWith(":")) return "left";
    return "auto";
  }

  function isNumericMarkdown(value) {
    const plain = value
      .replace(/\*\*|__|`/g, "")
      .replace(/\[[^\]]+\]\([^)]*\)/g, "")
      .trim();
    return /^\(?[-+]?[$€£]?\d[\d,]*(?:\.\d+)?%?\)?$/.test(plain);
  }

  function parseTable(lines, startIndex) {
    if (startIndex + 1 >= lines.length || !lines[startIndex].includes("|")) {
      return null;
    }

    const header = splitTableRow(lines[startIndex]);
    const separators = splitTableRow(lines[startIndex + 1]);
    if (
      header.length === 0 ||
      separators.length !== header.length ||
      separators.some((cell) => separatorAlignment(cell) === null)
    ) {
      return null;
    }

    const rows = [];
    let nextIndex = startIndex + 2;
    while (nextIndex < lines.length && lines[nextIndex].trim() && lines[nextIndex].includes("|")) {
      const cells = splitTableRow(lines[nextIndex]);
      if (cells.length !== header.length) break;
      rows.push(cells);
      nextIndex += 1;
    }

    const alignments = separators.map((separator, columnIndex) => {
      const explicitAlignment = separatorAlignment(separator);
      if (explicitAlignment !== "auto") return explicitAlignment;
      const values = rows.map((row) => row[columnIndex]).filter((value) => value !== "");
      return values.length > 0 && values.every(isNumericMarkdown) ? "right" : "left";
    });

    return {
      block: { type: "table", header, rows, alignments },
      nextIndex,
    };
  }

  function parseChartSpec(text) {
    let value;
    try {
      value = JSON.parse(text);
    } catch (_error) {
      return null;
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    if (value.type !== "bar" || typeof value.title !== "string") return null;
    if (!Array.isArray(value.labels) || !Array.isArray(value.values)) return null;
    if (
      value.labels.length < 1 ||
      value.labels.length > 30 ||
      value.labels.length !== value.values.length
    ) {
      return null;
    }
    if (
      value.labels.some((label) => typeof label !== "string" || !label.trim()) ||
      value.values.some(
        (number) => typeof number !== "number" || !Number.isFinite(number) || number < 0,
      )
    ) {
      return null;
    }
    for (const field of ["title", "xLabel", "yLabel", "unit"]) {
      if (value[field] !== undefined && typeof value[field] !== "string") return null;
      if (typeof value[field] === "string" && value[field].length > 160) return null;
    }
    return {
      type: "bar",
      title: value.title.trim() || "Chart",
      xLabel: (value.xLabel || "Category").trim(),
      yLabel: (value.yLabel || "Value").trim(),
      unit: (value.unit || "").trim(),
      labels: value.labels.map((label) => label.trim()),
      values: value.values,
    };
  }

  function startsBlock(lines, index) {
    const line = lines[index] || "";
    return (
      !line.trim() ||
      /^```/.test(line.trim()) ||
      /^(#{1,6})\s+/.test(line) ||
      /^\s*[-*+]\s+/.test(line) ||
      /^\s*\d+[.)]\s+/.test(line) ||
      /^\s*>\s?/.test(line) ||
      parseTable(lines, index) !== null
    );
  }

  function parse(markdown) {
    const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
      if (!lines[index].trim()) {
        index += 1;
        continue;
      }

      const table = parseTable(lines, index);
      if (table) {
        blocks.push(table.block);
        index = table.nextIndex;
        continue;
      }

      const fence = lines[index].trim().match(/^```([^`]*)$/);
      if (fence) {
        const code = [];
        index += 1;
        while (index < lines.length && !/^```\s*$/.test(lines[index].trim())) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        const language = fence[1].trim().toLowerCase();
        const codeText = code.join("\n");
        const chart = language === "mariner-chart" ? parseChartSpec(codeText) : null;
        blocks.push(
          chart
            ? { type: "chart", chart }
            : { type: "code", language, text: codeText },
        );
        continue;
      }

      const heading = lines[index].match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() });
        index += 1;
        continue;
      }

      const unordered = lines[index].match(/^\s*[-*+]\s+(.+)$/);
      const ordered = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        const orderedList = Boolean(ordered);
        const pattern = orderedList ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
        const items = [];
        while (index < lines.length) {
          const item = lines[index].match(pattern);
          if (!item) break;
          items.push(item[1]);
          index += 1;
        }
        blocks.push({ type: "list", ordered: orderedList, items });
        continue;
      }

      if (/^\s*>\s?/.test(lines[index])) {
        const quoteLines = [];
        while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
          quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
          index += 1;
        }
        blocks.push({ type: "quote", lines: quoteLines });
        continue;
      }

      const paragraphLines = [lines[index]];
      index += 1;
      while (index < lines.length && !startsBlock(lines, index)) {
        paragraphLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "paragraph", lines: paragraphLines });
    }

    return blocks;
  }

  function safeLinkTarget(target) {
    try {
      const resolved = new URL(target, globalScope.location?.href || "https://localhost/");
      return ["http:", "https:", "mailto:"].includes(resolved.protocol) ? resolved.href : null;
    } catch (_error) {
      return null;
    }
  }

  function appendInline(parent, value) {
    const text = String(value);
    const tokenPattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\[[^\]\n]+\]\([^\s)]+\)|\*[^*\n]+\*|_[^_\n]+_)/g;
    let cursor = 0;
    let match;
    while ((match = tokenPattern.exec(text)) !== null) {
      if (match.index > cursor) parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
      const token = match[0];
      if (token.startsWith("`")) {
        const code = document.createElement("code");
        code.textContent = token.slice(1, -1);
        parent.appendChild(code);
      } else if (token.startsWith("**") || token.startsWith("__")) {
        const strong = document.createElement("strong");
        appendInline(strong, token.slice(2, -2));
        parent.appendChild(strong);
      } else if (token.startsWith("[")) {
        const closingBracket = token.indexOf("](");
        const label = token.slice(1, closingBracket);
        const target = safeLinkTarget(token.slice(closingBracket + 2, -1));
        if (target) {
          const link = document.createElement("a");
          link.href = target;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          appendInline(link, label);
          parent.appendChild(link);
        } else {
          parent.appendChild(document.createTextNode(label));
        }
      } else {
        const emphasis = document.createElement("em");
        appendInline(emphasis, token.slice(1, -1));
        parent.appendChild(emphasis);
      }
      cursor = tokenPattern.lastIndex;
    }
    if (cursor < text.length) parent.appendChild(document.createTextNode(text.slice(cursor)));
  }

  function appendInlineLines(parent, lines) {
    lines.forEach((line, index) => {
      if (index > 0) parent.appendChild(document.createElement("br"));
      appendInline(parent, line);
    });
  }

  function renderTable(container, block) {
    const wrapper = document.createElement("div");
    wrapper.className = "table-container";
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", "Scrollable data table");

    const table = document.createElement("table");
    const head = document.createElement("thead");
    const headerRow = document.createElement("tr");
    block.header.forEach((value, columnIndex) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.className = `align-${block.alignments[columnIndex]}`;
      appendInline(cell, value);
      headerRow.appendChild(cell);
    });
    head.appendChild(headerRow);
    table.appendChild(head);

    const body = document.createElement("tbody");
    for (const row of block.rows) {
      const tableRow = document.createElement("tr");
      row.forEach((value, columnIndex) => {
        const cell = document.createElement("td");
        cell.className = `align-${block.alignments[columnIndex]}`;
        appendInline(cell, value);
        tableRow.appendChild(cell);
      });
      body.appendChild(tableRow);
    }
    table.appendChild(body);
    wrapper.appendChild(table);
    container.appendChild(wrapper);
  }

  function renderChart(container, block) {
    const chart = block.chart;
    const figure = document.createElement("figure");
    figure.className = "bar-chart";
    figure.setAttribute("role", "img");
    figure.setAttribute(
      "aria-label",
      `${chart.title}. ${chart.yLabel} by ${chart.xLabel}.`,
    );

    const caption = document.createElement("figcaption");
    caption.textContent = chart.title;
    figure.appendChild(caption);

    const scaleMaximum = Math.max(...chart.values, 1);
    const rows = document.createElement("div");
    rows.className = "bar-chart-rows";
    chart.labels.forEach((label, index) => {
      const row = document.createElement("div");
      row.className = "bar-chart-row";

      const category = document.createElement("span");
      category.className = "bar-chart-label";
      category.textContent = label;

      const track = document.createElement("span");
      track.className = "bar-chart-track";
      const bar = document.createElement("span");
      bar.className = "bar-chart-bar";
      bar.setAttribute("style", `--bar-size: ${(chart.values[index] / scaleMaximum) * 100}%`);
      bar.setAttribute("aria-hidden", "true");
      track.appendChild(bar);

      const metric = document.createElement("span");
      metric.className = "bar-chart-value";
      metric.textContent = `${chart.values[index].toLocaleString()}${chart.unit ? ` ${chart.unit}` : ""}`;
      row.appendChild(category);
      row.appendChild(track);
      row.appendChild(metric);
      rows.appendChild(row);
    });
    figure.appendChild(rows);

    const axis = document.createElement("div");
    axis.className = "bar-chart-axis-label";
    axis.textContent = chart.yLabel;
    figure.appendChild(axis);
    container.appendChild(figure);
  }

  function render(container, markdown) {
    const blocks = parse(markdown);
    for (const block of blocks) {
      if (block.type === "table") {
        renderTable(container, block);
      } else if (block.type === "chart") {
        renderChart(container, block);
      } else if (block.type === "heading") {
        const heading = document.createElement(`h${block.level}`);
        appendInline(heading, block.text);
        container.appendChild(heading);
      } else if (block.type === "list") {
        const list = document.createElement(block.ordered ? "ol" : "ul");
        for (const itemText of block.items) {
          const item = document.createElement("li");
          appendInline(item, itemText);
          list.appendChild(item);
        }
        container.appendChild(list);
      } else if (block.type === "code") {
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        if (block.language) code.dataset.language = block.language;
        code.textContent = block.text;
        pre.appendChild(code);
        container.appendChild(pre);
      } else if (block.type === "quote") {
        const quote = document.createElement("blockquote");
        appendInlineLines(quote, block.lines);
        container.appendChild(quote);
      } else {
        const paragraph = document.createElement("p");
        appendInlineLines(paragraph, block.lines);
        container.appendChild(paragraph);
      }
    }
  }

  const api = Object.freeze({ parse, parseChartSpec, render });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (globalScope) globalScope.MarinerMarkdown = api;
})(typeof window !== "undefined" ? window : globalThis);
