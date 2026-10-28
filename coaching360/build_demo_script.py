"""Rebuild demo_script.html (repo root) from a demo run of the app.

    python3 coaching360/tests/regression_test.py --url http://127.0.0.1:5000 --cases coaching360/tests/demo_cases.json
    python3 coaching360/build_demo_script.py                      # uses the newest results file
    python3 coaching360/build_demo_script.py results/regression_<time>.json

The page's styles, logo and copy script are kept from the current demo_script.html (everything
before <main> and after the closing quote); the story, questions and app answers are rebuilt here.
"""
import html, json, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "demo_script.html"
RESULTS = ROOT / "coaching360" / "tests" / "results"

PEOPLE = {
    "Rowan Jessup": "emp", "Riley Quimby": "bm", "Felicia Umberto": "dm", "Keisha Foxworth": "rvp",
}

# (act id, tag, title, tagline, [(subheading or None, [question ids])])
ACTS = [
    ("act1", "Act 1 · Scorecards", "Clarity on performance", "Employees see their progress. Managers see the team.",
     [("Employee view", ["D1", "D2", "D3"]), ("Manager view", ["D4", "D5", "D6"])]),
    ("act2", "Act 2 · Success Plan", "You shape your success", "Monthly goals built from the employee's own KPIs.",
     [(None, ["D7", "D8", "D9"])]),
    ("act3", "Act 3 · Coaching", "Leaders coach with purpose",
     "Documented, KPI-grounded conversations the employee acknowledges.",
     [(None, ["D10", "D11", "D12", "D12b", "D13", "D14"])]),
    ("act4", "Act 4 · Oversight", "Visiting with purpose",
     "Know the branch before you walk in. Plan every visit with purpose.",
     [("District Manager", ["D15", "D16", "D17", "D18"]), ("Regional Vice President", ["D19", "D20"])]),
]

# What to point out while the answer is on screen.
SAY = {
    "D1": "One view: monthly KPIs against goal with last month and year to date, then the daily DPR metrics.",
    "D2": "The conversation keeps the month. LPE is well under goal and slipping.",
    "D3": "A quick split of what met goal and what missed. Higher delinquency counts as a miss.",
    "D4": "The whole branch on one screen, with each person's goal status and last month. The table is wide; scroll right for calls, contacts and ranks.",
    "D5": "The strongest and weakest producer at Laurel Fork, with the numbers behind them. LPE may show unrounded (0.9524 = 0.95, 0.2857 = 0.29).",
    "D6": "Riley also covers Shenandoah Mills as relief manager, so Reese Delacroix appears with a coverage note.",
    "D7": "Rowan's October plan: focus metrics, a competency and a goal statement, still waiting for approval.",
    "D8": "Last month's plan scored against the actual results: DACC hit, LPE missed.",
    "D9": "Riley's approval queue, including the relief branch.",
    "D10": "Every coaching record for Rowan in one place, most recent first.",
    "D11": "The last conversation, its root cause and the commitment Rowan made.",
    "D12": "The trend behind the coaching: LPE month by month.",
    "D12b": "A ready-made agenda for the next conversation, grounded in Rowan's numbers.",
    "D13": "Recognition is coaching too: a note built from Selena's actual results. If it says \"30-60 day\", that is the 30–89 day rate (2.98% vs 3.40%).",
    "D14": "Back as Rowan: the coaching records Rowan still has to acknowledge.",
    "D15": "Every branch in the district side by side; Laurel Fork stands out at the bottom.",
    "D16": "Where the follow-through is lagging: pending acknowledgements and open tasks by branch.",
    "D17": "A visit brief: branch numbers, the people, open items and the last visits.",
    "D18": "Closing the loop on the last visit: who owned the follow-up and when it was done.",
    "D19": "District 902 against its peers in the region.",
    "D20": "Visit cadence for each district manager: completed, scheduled and overdue.",
}


def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def markdown(md):
    """Enough Markdown for the app's answers: headings, lists, tables, rules and paragraphs."""
    out, lines, i = [], md.strip().splitlines(), 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
        elif re.match(r"^#{1,6}\s", line):
            out.append(f"<h5>{inline(line.lstrip('#').strip())}</h5>")
            i += 1
        elif re.match(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$", line):
            out.append("<hr>")
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            head, i = cells(line), i + 2
            body = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                body.append(cells(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tr = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')
        elif re.match(r"^([-*+]|\d+[.)])\s", line.lstrip()):
            # Top-level items; indented items become a nested list, and blank lines between items keep one list.
            tag = "ol" if line.lstrip()[0].isdigit() else "ul"
            items = []  # [text, [sub items]]
            while i < len(lines):
                row = lines[i]
                if not row.strip():
                    nxt = next((l for l in lines[i + 1:] if l.strip()), "")
                    if re.match(r"^(\s+([-*+]|\d+[.)])|([-*+]|\d+[.)]))\s", nxt) and (nxt[0].isspace() or nxt[0].isdigit() == (tag == "ol")):
                        i += 1
                        continue
                    break
                item = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)", row)
                if item and not item.group(1):
                    if item.group(2)[0].isdigit() != (tag == "ol"):
                        break
                    items.append([item.group(3), []])
                elif item and items:
                    items[-1][1].append(item.group(3))
                elif row.startswith("  ") and items:
                    target = items[-1][1] if items[-1][1] else items[-1]
                    target[-1 if target is items[-1][1] else 0] += " " + row.strip()
                else:
                    break
                i += 1
            out.append(f"<{tag}>" + "".join(
                f"<li>{inline(t)}" + (("<ul>" + "".join(f"<li>{inline(s)}</li>" for s in sub) + "</ul>") if sub else "") + "</li>"
                for t, sub in items) + f"</{tag}>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|\s*\||\s*([-*+]|\d+[.)])\s)", lines[i]):
                para.append(inline(lines[i].strip()))
                i += 1
            out.append("<p>" + "<br>".join(para) + "</p>")
    return "\n".join(out)


def card(turn, person, run_time):
    who = PEOPLE[person]
    ok = not turn["problems"]
    status = f"✅ Tested {run_time} · {turn['seconds']:.0f} s" if ok else f"⚠️ Check before the demo · {'; '.join(turn['problems'])}"
    say = SAY.get(turn["id"], "")
    return f"""    <li>
      <div><span class="as c-{who}">as {person}</span><span class="q">{html.escape(turn['ask'])}</span></div><button class="copy">Copy</button>
      <div class="tested {'pass' if ok else 'warn'}"><strong>{html.escape(status)}</strong>{' — ' + html.escape(say) if say else ''}</div>
      <div class="app-answer"><div class="app-meta">App answer · {turn['seconds']:.0f} s</div>
{markdown(turn['answer'])}
      </div>
    </li>"""


def build(results_path):
    results = json.loads(results_path.read_text())
    stamp = re.search(r"(\d{8})_(\d{4})", results_path.name)
    run_time = time.strftime("%m/%d %H:%M", time.strptime(stamp.group(1) + stamp.group(2), "%Y%m%d%H%M")) if stamp else "latest run"
    turns, person = {}, None
    for r in results:
        if r["ask"].startswith("/coaching360 "):
            person = r["ask"].split(" ", 1)[1]
        elif r["id"]:
            turns[r["id"]] = (r, person)
    asked = [q for act in ACTS for _, ids in act[4] for q in ids]
    missing = [q for q in asked if q not in turns]
    if missing:
        sys.exit(f"results file has no answers for {missing}")
    passed = sum(not turns[q][0]["problems"] for q in asked)

    order, last = [], None
    for q in asked:
        who = turns[q][1]
        if who != last:
            order.append([who, [q]])
            last = who
        else:
            order[-1][1].append(q)
    number = {q: n for n, q in enumerate(asked, 1)}
    cmds = []
    for who, ids in order:
        span = f"Q{number[ids[0]]}–{number[ids[-1]]}" if len(ids) > 1 else f"Q{number[ids[0]]}"
        cmds.append(f'    <div class="cmd"><div><span class="who"><strong>{who}</strong> · {span}</span><br><code>/coaching360 {who}</code></div>'
                    f'<button class="copy" data-copy="/coaching360 {who}">Copy</button></div>')
    cmds.append('    <div class="cmd"><div><span class="who"><strong>Finish</strong> · leave the chat</span><br><code>/coaching360 exit</code></div>'
                '<button class="copy" data-copy="/coaching360 exit">Copy</button></div>')

    sections, n = [], 0
    for act_id, tag, title, tagline, groups in ACTS:
        parts = [f'<section class="act" id="{act_id}">\n  <span class="act-tag">{tag}</span>\n  <h2>{title}</h2>\n  <p class="tagline">{tagline}</p>']
        for sub, ids in groups:
            if sub:
                parts.append(f"\n  <h3>{sub}</h3>")
            parts.append(f'  <ol class="qs" style="--start: {n}">\n' + "\n".join(card(*turns[q], run_time) for q in ids) + "\n  </ol>")
            n += len(ids)
        sections.append("\n".join(parts) + "\n</section>")

    page = PAGE.read_text()
    head = page[:page.index("<main>")]
    tail = page[page.index('<p class="closing">'):]
    nav = "".join(f'<span class="arrow">→</span><a href="#{a}">{t.split(" · ")[0].replace("Act ", "")} · {t.split(" · ")[1]}</a>' for a, t, *_ in ACTS)
    main = f"""<main>
<header>
  <div class="header-body">
  <span class="brand">Clarity · Empowerment · Purpose · Success</span>
  <h1>Coaching360 demo script</h1>
  <p>Questions to type into the <strong>/coaching360</strong> chat, following the promo video: Scorecards → Success Plan → Coaching → Oversight.</p>
  <nav class="chain">
    <a href="#access">Access a profile</a><span class="arrow">·</span>
    <a href="#cast">Cast</a>{nav}
  </nav>
  <p class="testsum"><strong>Tested in the app {run_time}:</strong> {passed} of {len(asked)} questions gave the expected answer. Open a question to see the app's reply from that run.</p>
    <div class="toolbar">
    <div class="note">Synthetic demo dataset, as-of 2026-10-20. Latest complete KPI month is September 2026. Wording can vary between runs; the numbers come from the data and should match. Click <strong>Show app answer</strong> under a question to see the reply.</div>
    <button id="toggle-answers">Show all app answers</button>
  </div>
  </div>
</header>

<section class="act" id="access">
  <span class="act-tag">Before you start</span>
  <h2>How to access a profile</h2>
  <p class="tagline">The chat answers as the person whose profile is open, so switch profiles to match the “as …” label on each question.</p>
  <ol class="steps">
    <li>In the chat, type <code>/coaching360 &lt;name&gt;</code> with the person's full name, for example <code>/coaching360 Rowan Jessup</code>. The greeting confirms whose profile you're viewing.</li>
    <li>Ask the questions labeled with that person's name, in order: follow-up questions rely on the earlier ones in the same chat.</li>
    <li>To change person, type <code>/coaching360 &lt;another name&gt;</code>, or <code>/coaching360 switch</code> to pick from a list.</li>
    <li>When the demo is done, type <code>/coaching360 exit</code> to leave.</li>
  </ol>
  <h3>Commands in demo order</h3>
  <div class="cmds">
{chr(10).join(cmds)}
  </div>
</section>

<section class="act" id="cast">
  <span class="act-tag">Cast</span>
  <h2>Branch 8011 Laurel Fork and its leaders</h2>
  <p class="tagline">Rowan is the lowest producer on a struggling team, Selena is the bright spot, Riley keeps coaching LPE without results, and Felicia's district trails the region.</p>
  <div class="tbl"><table>
    <thead><tr><th>Name</th><th>Role</th><th>Where</th></tr></thead>
    <tbody>
      <tr><td><span class="dot c-emp"></span><strong>Rowan Jessup</strong></td><td>Account Representative (focus employee)</td><td>8011 Laurel Fork</td></tr>
      <tr><td><span class="dot c-emp"></span><strong>Selena Driscoll</strong></td><td>Assistant Branch Manager (top performer)</td><td>8011 Laurel Fork</td></tr>
      <tr><td><span class="dot c-emp"></span><strong>Avery Northcott</strong></td><td>Account Representative</td><td>8011 Laurel Fork</td></tr>
      <tr><td><span class="dot c-bm"></span><strong>Riley Quimby</strong></td><td>Branch Manager; relief manager for 8012 Shenandoah Mills until 11/12</td><td>8011 Laurel Fork</td></tr>
      <tr><td><span class="dot c-dm"></span><strong>Felicia Umberto</strong></td><td>District Manager</td><td>District 902 Shenandoah (8007–8012)</td></tr>
      <tr><td><span class="dot c-rvp"></span><strong>Keisha Foxworth</strong></td><td>Regional Vice President</td><td>Region 1 Mid-Atlantic (901–903)</td></tr>
    </tbody>
  </table></div>
</section>

{chr(10).join(sections)}

"""
    PAGE.write_text(head + main + tail)
    print(f"wrote {PAGE.relative_to(ROOT)}: {passed}/{len(asked)} passed ({results_path.name})")


if __name__ == "__main__":
    build(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else max(RESULTS.glob("regression_*.json")))
