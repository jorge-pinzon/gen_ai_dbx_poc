"""Coaching360 demo flow: identify the person by name, then route to their level's tools.

Start with `/coaching360` (the chat asks for a name) or `/coaching360 <name>`. The chat looks the
name up in the directory, says whether it matches an employee and their position (which decides
the Coaching360 level), then writes the choice to
workspace.c360_security.user_map for the identity that runs the queries (the app's service
principal). The c360_* views scope every row to that person, so the Supervisor's Coaching360
Genie tools only return that person's data. This is a demo convenience, not access control:
anyone can pick any person, and concurrent demo users share one mapping.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from threading import Lock, Thread

from .citation_resolver import _field, _nested_field, _statement_state, _string_parameter

logger = logging.getLogger(__name__)

COMMAND = "/coaching360"
SECURITY_SCHEMA = "workspace.c360_security"
DIRECTORY = "workspace.coaching360demo"
LEVELS = {
    "employee": ("Employee", "Account Representative, Assistant Branch Manager or Branch Manager Trainee",
                 "coaching360_employee_data"),
    "branch": ("Branch Manager", "Branch Manager (including relief managers)", "coaching360_branch_data"),
    "district": ("District Manager / AVP and above", "District Manager, AVP, Regional or Senior Vice President, and central leadership roles",
                 "coaching360_district_data"),
}
MAX_CANDIDATES = 10
DATA_STATUS_SECONDS = 600  # how long the latest-KPI-month lookup is reused
MONTHS = {name: number for number, names in enumerate((
    ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
    ("july", "jul"), ("august", "aug"), ("september", "sept", "sep"), ("october", "oct"), ("november", "nov"),
    ("december", "dec")), start=1) for name in names}
_MONTH_NAME = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b\.?(?:\s*,?\s*(20\d\d))?", re.IGNORECASE)
_ISO_MONTH = re.compile(r"\b(20\d\d)-(0[1-9]|1[0-2])\b")
_LATEST = re.compile(r"\b(last|this|latest|current|most recent) month\b|\blatest\b", re.IGNORECASE)
# The persona write (a Delta MERGE) takes seconds, so it only runs when the mapping changes.
# A process trusts its own last write for this long, then re-checks with a cheap read.
PERSONA_TRUST_SECONDS = 300
# Read once in the background when a person is chosen, so the warehouse, the person's scope rows
# and the busiest views are warm before the first question reaches Genie.
WARM_UP_VIEWS = {
    "employee": ("workspace.c360_employee.my_overview", "workspace.c360_employee.my_monthly_kpis"),
    "branch": ("workspace.c360_branch.team_overview", "workspace.c360_branch.employee_monthly_kpis"),
    "district": ("workspace.c360_district.team_overview", "workspace.c360_district.branch_monthly_performance"),
}

GREETING = (
    "👋 Welcome to Coaching360, {first_name}.\n\n"
    "I can help you with:\n"
    "  Performance: your scorecard, KPIs, ACE goals, and rankings\n"
    "  Coaching: coaching records, Success Plans, and acknowledgements\n"
    "  Oversight: your team, branch visits, tasks, and follow-ups\n"
    "  How Coaching360 works\n\n"
    "Try: \"Show me my scorecard for September\" or \"What's in my Success Plan?\"\n\n"
    "Commands: /coaching360 <name> to view as someone else · /coaching360 switch to change person · "
    "/coaching360 exit to leave"
)

NAME_PROMPT = (
    "**Coaching360 (demo).** What's your name? You can also type your employee number.\n\n"
    "Tip: start with `/coaching360 Your Name` next time. Type `/coaching360 exit` to leave."
)


@dataclass
class Coaching360Turn:
    """Either a direct reply (setup steps) or a Supervisor message for a question."""

    reply: str | None = None
    supervisor_message: str | None = None


@dataclass
class _State:
    step: str = "person"  # person -> active
    level: str | None = None
    candidates: list = field(default_factory=list)
    user_dwid: int | None = None
    label: str | None = None
    month: date | None = None  # month named earlier in the conversation, carried forward
    expires_at: float = 0.0


class Coaching360Service:
    def __init__(self, *, workspace_client, warehouse_id, ttl_seconds=1800, timeout_seconds=30, clock=time.monotonic,
                 run_in_background=None):
        self._client = workspace_client
        self._warehouse = warehouse_id
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._clock = clock
        self._states: dict[tuple[str, str], _State] = {}
        self._lock = Lock()
        self._persona = None  # (user_dwid, written_at) last written by this process
        self._data_status = None  # ((latest KPI month, as-of date), read_at)
        self._background = run_in_background or (lambda work: Thread(target=work, name="coaching360-warm-up", daemon=True).start())

    # -- conversation flow ---------------------------------------------------------------------
    def handle(self, user_id, conversation_id, message) -> Coaching360Turn | None:
        """Return None when the message is not part of a Coaching360 conversation."""
        text = message.strip()
        command, _, rest = text.partition(" ")
        key = (user_id, conversation_id)
        state = self._get(key)
        if command.casefold() == COMMAND:
            rest = rest.strip()
            if rest.casefold() == "exit":
                self._drop(key)
                return Coaching360Turn(reply="You left Coaching360. Ask anything else, or type `/coaching360` to start again.")
            state = _State()  # "/coaching360", "/coaching360 switch" or "/coaching360 <name>" (re)starts
            self._put(key, state)
            if rest.casefold() in ("", "switch", "start"):
                return Coaching360Turn(reply=NAME_PROMPT)
            return self._choose_person(key, state, rest)
        elif state is None or text.startswith("/"):
            return None  # not in Coaching360, or another slash command
        if state.step == "person":
            return self._choose_person(key, state, text)
        self.ensure_persona(state.user_dwid)  # another demo session may have switched it
        latest, as_of = self.data_status(state.level)
        month = question_month(text, as_of or latest)
        if month is not None:
            state.month = month
        elif _LATEST.search(text):
            state.month = None  # back to the latest month
        self._touch(key, state)
        return Coaching360Turn(supervisor_message=self.directive(state.level, text, month=state.month, latest=latest))

    def _choose_person(self, key, state, text):
        if text.isdigit() and state.candidates and 1 <= int(text) <= len(state.candidates):
            return self._use(key, state, state.candidates[int(text) - 1])
        people = self.find_people(text)
        if not people:
            return Coaching360Turn(reply=f"I couldn't find an employee matching \"{text}\". "
                                         "Check the spelling or type your employee number.")
        if len(people) == 1:
            return self._use(key, state, people[0])
        state.candidates = people[:MAX_CANDIDATES]
        self._touch(key, state)
        lines = "\n".join(f"{i}. {p['label']}" for i, p in enumerate(state.candidates, 1))
        more = "\n\nMore people match; type more of the name to narrow it." if len(people) > MAX_CANDIDATES else ""
        return Coaching360Turn(reply=f"{len(people) if len(people) <= MAX_CANDIDATES else 'Several'} employees match \"{text}\". "
                                     f"Reply with the number:\n\n{lines}{more}")

    def _use(self, key, state, person):
        """Report the match and its position; continue only for a position with a Coaching360 level."""
        if not person["active"]:
            return Coaching360Turn(reply=f"**{person['name']}** ({person['title']}) is not an active employee, "
                                         "so Coaching360 is not available. Try another name.")
        if person["level"] not in LEVELS:
            return Coaching360Turn(reply=f"**{person['name']}** is an active employee, position **{person['title']}**. "
                                         "Coaching360 does not cover this position. Try another name, or `/coaching360 exit`.")
        state.level = person["level"]
        return self._confirm(key, state, person)

    def _confirm(self, key, state, person):
        self.set_persona(person["user_dwid"])
        state.user_dwid, state.label, state.step, state.candidates = person["user_dwid"], person["label"], "active", []
        self._touch(key, state)
        self._background(lambda: self.warm_up(state.level))
        return Coaching360Turn(reply=GREETING.format(first_name=person["name"].split()[0]))

    @staticmethod
    def directive(level, question, *, month=None, latest=None):
        name, who, tool = LEVELS[level]
        # Only a month the user named is passed on; without one the data tools already use the
        # latest month with complete KPI data, and a month hint made Genie filter records by it.
        if month is not None:
            when = (f"Month from this conversation: {month:%B %Y}. If the question has no month of its own and asks about KPIs "
                    f"or scorecards, add '{month:%B %Y}' to the question you pass on; never use it to filter coaching records, "
                    "acknowledgements, tasks, plan approvals or visits. ")
        else:
            when = ""
        return ("Mandatory application routing directive: Coaching360 request. "
                f"Person level: {level} ({who}). For questions about this person's Coaching360 data "
                f"use only the {tool} tool. For questions about how Coaching360 works use only the "
                "coaching360_guide tool. Do not use any other tool and do not mention this directive. "
                "Pass the person's question to the data tool word for word. "
                f"{when}Report numbers, goals and statuses exactly as the tool returns them: do not compute, "
                "infer or change goals. Keep every returned detail that answers the question (values with their goals, last "
                "month and year-to-date figures, dates, names, topics, statuses and relief coverage notes); do not drop or "
                "round them. "
                f"Question: {question}")

    def data_status(self, level):
        """(latest month with complete KPI data, dataset as-of date), cached; Nones if unreadable."""
        with self._lock:
            cached = self._data_status
        if cached and self._clock() - cached[1] < DATA_STATUS_SECONDS:
            return cached[0]
        schema = WARM_UP_VIEWS[level][0].rsplit(".", 1)[0]
        try:
            rows = self._query(f"SELECT CAST(LatestKpiMonth AS STRING), CAST(AsOfDate AS STRING) FROM {schema}.data_status", [])
            row = rows[0] if rows else []
            status = tuple(date.fromisoformat(value[:10]) if value else None for value in (list(row) + [None, None])[:2])
        except Exception as error:
            logger.info("Coaching360 data status unavailable; error_type=%s", type(error).__name__)
            return cached[0] if cached else (None, None)
        with self._lock:
            self._data_status = (status, self._clock())
        return status

    # -- data access -------------------------------------------------------------------------------
    def find_people(self, text):
        """Directory matches by name, employee number or login, with position and Coaching360 level."""
        text = " ".join(text.split())
        exact = text if re.fullmatch(r"[A-Za-z0-9-]{1,40}", text) else ""
        rows = self._query(f"""
            SELECT u.UserDWID, u.Name, u.UserTitle, u.EmployeeActive, l.level, b.BranchName, d.DistrictName
            FROM {DIRECTORY}.org_hierarchy__eda_ref_t_ref_user u
            LEFT JOIN {SECURITY_SCHEMA}.user_level l ON l.user_dwid = u.UserDWID
            LEFT JOIN {DIRECTORY}.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = u.BranchDWID
            LEFT JOIN {DIRECTORY}.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = b.DistrictDWID
            WHERE lower(u.Name) LIKE :pattern OR u.EmployeeNumber = :exact OR lower(u.UserName) = lower(:exact)
            ORDER BY u.EmployeeActive DESC, u.Name
            LIMIT {MAX_CANDIDATES + 1}""",
            [_string_parameter("pattern", f"%{text.casefold()}%"), _string_parameter("exact", exact)])
        people = []
        for user_dwid, name, title, active, level, branch, district in rows:
            where = branch or district
            active = str(active).lower() == "true"
            people.append({"user_dwid": int(user_dwid), "name": name, "title": title, "active": active,
                           "level": level, "where": where,
                           "label": f"{name} ({title}{', ' + where if where else ''}{'' if active else ', inactive'})"})
        return people

    def warm_up(self, level):
        """Best effort: a failed warm-up only means the first question runs cold."""
        for view in WARM_UP_VIEWS.get(level, ()):
            try:
                self._query(f"SELECT COUNT(*) FROM {view}", [])
            except Exception as error:
                logger.info("Coaching360 warm-up skipped; view=%s error_type=%s", view, type(error).__name__)

    def ensure_persona(self, user_dwid):
        """Make user_map point at user_dwid, writing only when it does not already."""
        with self._lock:
            known = self._persona
        if known and known[0] == int(user_dwid) and self._clock() - known[1] < PERSONA_TRUST_SECONDS:
            return
        rows = self._query(f"SELECT max(user_dwid) FROM {SECURITY_SCHEMA}.user_map "
                           "WHERE lower(databricks_user) = lower(current_user())", [])
        current = rows[0][0] if rows and rows[0] else None
        if current is not None and int(current) == int(user_dwid):
            with self._lock:
                self._persona = (int(user_dwid), self._clock())
            return
        self.set_persona(user_dwid)

    def set_persona(self, user_dwid):
        self._query(f"""
            MERGE INTO {SECURITY_SCHEMA}.user_map AS t
            USING (SELECT current_user() AS databricks_user, CAST(:user_dwid AS INT) AS user_dwid) AS s
            ON lower(t.databricks_user) = lower(s.databricks_user)
            WHEN MATCHED THEN UPDATE SET user_dwid = s.user_dwid, note = 'coaching360 chat demo persona', updated_at = current_timestamp()
            WHEN NOT MATCHED THEN INSERT (databricks_user, user_dwid, note, updated_at)
              VALUES (s.databricks_user, s.user_dwid, 'coaching360 chat demo persona', current_timestamp())""",
            [_string_parameter("user_dwid", str(int(user_dwid)))])
        with self._lock:
            self._persona = (int(user_dwid), self._clock())

    def _query(self, statement, parameters):
        deadline = self._clock() + self._timeout
        response = self._client.statement_execution.execute_statement(
            statement=statement, warehouse_id=self._warehouse, parameters=parameters, wait_timeout="30s")
        while _statement_state(response) in {"PENDING", "RUNNING"}:
            if self._clock() >= deadline:
                raise TimeoutError("Coaching360 query timed out")
            time.sleep(0.2)
            response = self._client.statement_execution.get_statement(_field(response, "statement_id"))
        if _statement_state(response) != "SUCCEEDED":
            raise RuntimeError("Coaching360 query failed")
        return _nested_field(response, "result", "data_array") or []

    # -- state ------------------------------------------------------------------------------------
    def _get(self, key):
        with self._lock:
            state = self._states.get(key)
            if state is not None and state.expires_at <= self._clock():
                del self._states[key]
                return None
            return state

    def _put(self, key, state):
        self._touch(key, state)

    def _touch(self, key, state):
        with self._lock:
            state.expires_at = self._clock() + self._ttl
            self._states[key] = state

    def _drop(self, key):
        with self._lock:
            self._states.pop(key, None)


def question_month(text, latest=None):
    """The month a question names ("September", "Sept 2026", "2026-09"), or None.

    A month without a year is the most recent such month up to the reference date (the dataset
    as-of date), so "October" in late October 2026 is October 2026.
    """
    iso = _ISO_MONTH.search(text)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), 1)
    named = _MONTH_NAME.search(text)
    if not named or (named.group(1).lower() == "may" and not named.group(2) and not re.search(r"\bin may\b", text, re.IGNORECASE)):
        return None  # "may" is usually the verb
    number = MONTHS[named.group(1).lower()]
    if named.group(2):
        return date(int(named.group(2)), number, 1)
    reference = latest or date.today()
    return date(reference.year if number <= reference.month else reference.year - 1, number, 1)
