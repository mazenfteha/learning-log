#!/usr/bin/env python3
"""Learning Log store: validate, save, list and render entries.

Standard library only, Python 3.9+. The entry shape is defined in
schema/entry.schema.json; the validation below mirrors it by hand and must be
kept in sync with it.

    store.py save <entry.json>      validate, upsert, render .md, print the saved paths
    store.py validate <entry.json>  validate only, exit 1 with clear errors
    store.py list [--project P]     one line per entry: date, project, id, title, due
    store.py due [--project P]      entries due for review today or earlier
    store.py show <task-id>         print the rendered Markdown
    store.py home                   print the storage root and the temp dir for drafts
    store.py notion-plan [task-id]  print the next Notion tool calls to make, as JSON
    store.py notion-record <file>   record the Notion URLs those calls returned
"""

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1
FIRST_INTERVAL_DAYS = 3

# Per /log run. A stored entry merged over several runs may hold more.
COUNT_LIMITS = {"decisions": (0, 4), "questions": (1, 3), "quiz": (3, 5)}
# The field that identifies an item when merging, so re-running /log never duplicates it.
MERGE_KEYS = {"decisions": "title", "questions": "asked", "quiz": "question"}

LAYERS = ("business_logic", "code", "architecture", "stack")
RISKS = ("low", "medium", "high")
DECISION_KINDS = ("product", "architecture", "security", "workaround", "deferred", "process")
QUIZ_TYPES = ("predict", "why", "where", "trap")

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SNIPPET_LINES = 10

TOP_FIELDS = ("schema_version", "task", "decisions", "questions", "quiz", "code", "review")
TASK_FIELDS = (
    "id", "title", "project", "repo", "branch", "stack", "layers", "risk",
    "how_it_works", "surprised_me", "would_bite_again", "created_at", "updated_at",
)
TASK_REQUIRED = (
    "id", "title", "project", "stack", "layers", "risk",
    "how_it_works", "surprised_me", "would_bite_again",
)
DECISION_FIELDS = ("title", "chosen", "rejected", "why", "kind", "reversible", "files", "impact")
QUESTION_FIELDS = ("asked", "should_have_asked", "rating", "feedback")
QUIZ_FIELDS = ("type", "question", "answer", "file")
CODE_FIELDS = ("file", "before", "after", "note")
REVIEW_FIELDS = ("due", "interval_days", "last_reviewed", "times_reviewed")

# Values are never echoed in errors, so a rejected secret doesn't end up in a log either.
SECRET_PATTERNS = (
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("API secret key", re.compile(r"\b(?:sk|rk)[-_](?:[A-Za-z0-9]+[-_])*[A-Za-z0-9]{16,}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password in a URL", re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
    ("token in a URL", re.compile(r"://[A-Za-z0-9_-]{20,}@")),
    ("credential value", re.compile(
        r"(?i)(?<![a-z])(?:api[_-]?key|secret|token|password|passwd|pwd)[a-z0-9_-]*"
        r"[\"']?\s*[:=]\s*[\"']?[^\s\"'`,;.()\[\]{}<>$]{8,}(?=[\s\"'`,;]|$)"
    )),
)


class EntryError(Exception):
    """An entry that can't be saved. `errors` holds one message per problem."""

    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


# ---------------------------------------------------------------- paths


def home():
    override = os.environ.get("LEARNING_LOG_HOME")
    return Path(override).expanduser() if override else Path.home() / ".learning-log"


def entries_dir():
    return home() / "entries"


def tmp_dir():
    return home() / "tmp"


def entry_paths(project, task_id):
    base = entries_dir() / project / task_id
    return base.with_suffix(".json"), base.with_suffix(".md")


def find_entry(task_id):
    """Return the stored JSON path for a task id, matched case-insensitively, or None."""
    root = entries_dir()
    if not root.is_dir():
        return None
    wanted = task_id.casefold()
    for path in sorted(root.glob("*/*.json")):
        if path.stem.casefold() == wanted:
            return path
    return None


def iter_entries(project=None):
    root = entries_dir()
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*.json")):
        if project and path.parent.name != project:
            continue
        yield path, load_json(path)


# ---------------------------------------------------------------- validation


def validate_entry(data, mode="input"):
    """Return a list of error messages; empty means valid.

    mode="input" checks a fresh entry from /log, including count limits.
    mode="stored" skips the max-count limits, since merged entries can grow.
    """
    errors = []
    if not isinstance(data, dict):
        return ["entry: expected a JSON object"]
    _check_keys(data, "", TOP_FIELDS, ("schema_version", "task", "decisions", "questions", "quiz"), errors)

    if "schema_version" in data and data["schema_version"] != SCHEMA_VERSION:
        errors.append("schema_version: expected %d, got %s" % (SCHEMA_VERSION, _show(data["schema_version"])))

    if "task" in data:
        _check_task(data["task"], errors)

    item_checks = {"decisions": _check_decision, "questions": _check_question, "quiz": _check_quiz_item}
    for key, check in item_checks.items():
        if key not in data:
            continue
        items = data[key]
        if not isinstance(items, list):
            errors.append("%s: expected a list" % key)
            continue
        low, high = COUNT_LIMITS[key]
        if len(items) < low:
            errors.append("%s: expected at least %d item%s, got %d" % (key, low, "" if low == 1 else "s", len(items)))
        if mode == "input" and len(items) > high:
            errors.append("%s: expected at most %d items, got %d" % (key, high, len(items)))
        for i, item in enumerate(items):
            check(item, "%s[%d]" % (key, i), errors)

    if "code" in data:
        _check_code(data["code"], errors)
    if "review" in data:
        _check_review(data["review"], errors)

    errors.extend(scan_secrets(data))
    return errors


def scan_secrets(data, path=""):
    errors = []
    if isinstance(data, dict):
        for key, value in data.items():
            errors.extend(scan_secrets(value, _join(path, key)))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            errors.extend(scan_secrets(value, "%s[%d]" % (path, i)))
    elif isinstance(data, str):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(data):
                errors.append("%s: looks like it contains a %s. Remove it; never copy secrets into an entry"
                              % (path or "entry", name))
                break
    return errors


def _check_task(task, errors):
    path = "task"
    if not _check_keys(task, path, TASK_FIELDS, TASK_REQUIRED, errors):
        return
    if "id" in task:
        _check_pattern(task["id"], "task.id", TASK_ID_RE,
                       "letters, digits, '.', '_' or '-', starting with a letter or digit (max 100)", errors)
    if "title" in task:
        _check_text(task["title"], "task.title", errors, max_len=120)
    if "project" in task:
        _check_pattern(task["project"], "task.project", PROJECT_RE,
                       "a lowercase slug: a-z, 0-9, '.', '_' or '-' (max 64)", errors)
    for key in ("repo", "branch"):
        if key in task and task[key] is not None:
            _check_text(task[key], "task." + key, errors)
    if "stack" in task:
        _check_list(task["stack"], "task.stack", errors, min_items=1, unique=True)
    if "layers" in task:
        _check_list(task["layers"], "task.layers", errors, min_items=1, unique=True, choices=LAYERS)
    if "risk" in task:
        _check_enum(task["risk"], "task.risk", RISKS, errors)
    for key, max_len in (("how_it_works", 900), ("surprised_me", 400), ("would_bite_again", 400)):
        if key in task:
            _check_text(task[key], "task." + key, errors, max_len=max_len)
    for key in ("created_at", "updated_at"):
        if key in task:
            _check_datetime(task[key], "task." + key, errors)


def _check_decision(item, path, errors):
    if not _check_keys(item, path, DECISION_FIELDS, DECISION_FIELDS[:-1], errors):
        return
    if "title" in item:
        _check_text(item["title"], path + ".title", errors, max_len=120)
    for key in ("chosen", "why"):
        if key in item:
            _check_text(item[key], "%s.%s" % (path, key), errors)
    if "impact" in item:
        _check_text(item["impact"], path + ".impact", errors)
    if "rejected" in item:
        _check_list(item["rejected"], path + ".rejected", errors, min_items=1,
                    hint="name at least one real alternative that was not used")
    if "kind" in item:
        _check_enum(item["kind"], path + ".kind", DECISION_KINDS, errors)
    if "reversible" in item and not isinstance(item["reversible"], bool):
        errors.append("%s.reversible: expected true or false, got %s" % (path, _show(item["reversible"])))
    if "files" in item:
        _check_list(item["files"], path + ".files", errors, min_items=1)


def _check_question(item, path, errors):
    if not _check_keys(item, path, QUESTION_FIELDS, QUESTION_FIELDS, errors):
        return
    for key in ("asked", "should_have_asked", "feedback"):
        if key in item:
            _check_text(item[key], "%s.%s" % (path, key), errors)
    if "rating" in item:
        rating = item["rating"]
        if not _is_int(rating) or not 1 <= rating <= 5:
            errors.append("%s.rating: expected a whole number from 1 to 5, got %s" % (path, _show(rating)))


def _check_quiz_item(item, path, errors):
    if not _check_keys(item, path, QUIZ_FIELDS, QUIZ_FIELDS, errors):
        return
    if "type" in item:
        _check_enum(item["type"], path + ".type", QUIZ_TYPES, errors)
    if "question" in item:
        _check_text(item["question"], path + ".question", errors)
    if "answer" in item:
        _check_text(item["answer"], path + ".answer", errors, max_len=500)
    if "file" in item:
        _check_text(item["file"], path + ".file", errors)


def _check_code(code, errors):
    path = "code"
    if not _check_keys(code, path, CODE_FIELDS, CODE_FIELDS[:-1], errors):
        return
    for key in ("file", "note"):
        if key in code:
            _check_text(code[key], "%s.%s" % (path, key), errors)
    for key in ("before", "after"):
        if key not in code:
            continue
        snippet = code[key]
        if not isinstance(snippet, str):
            errors.append("%s.%s: expected a string, got %s" % (path, key, _show(snippet)))
        elif len(snippet.split("\n")) > MAX_SNIPPET_LINES:
            errors.append("%s.%s: expected at most %d lines, got %d"
                          % (path, key, MAX_SNIPPET_LINES, len(snippet.split("\n"))))


def _check_review(review, errors):
    path = "review"
    if not _check_keys(review, path, REVIEW_FIELDS, REVIEW_FIELDS, errors):
        return
    if "due" in review:
        _check_date(review["due"], "review.due", errors)
    if "last_reviewed" in review and review["last_reviewed"] is not None:
        _check_date(review["last_reviewed"], "review.last_reviewed", errors)
    if "interval_days" in review:
        value = review["interval_days"]
        if not _is_int(value) or value < 1:
            errors.append("review.interval_days: expected a whole number of at least 1, got %s" % _show(value))
    if "times_reviewed" in review:
        value = review["times_reviewed"]
        if not _is_int(value) or value < 0:
            errors.append("review.times_reviewed: expected a whole number of at least 0, got %s" % _show(value))


def _check_keys(obj, path, allowed, required, errors):
    """Check obj is an object with the required keys and nothing unknown. False if not an object."""
    label = path or "entry"
    if not isinstance(obj, dict):
        errors.append("%s: expected an object, got %s" % (label, _show(obj)))
        return False
    for key in required:
        if key not in obj:
            errors.append("%s: required field is missing" % _join(path, key))
    for key in obj:
        if key not in allowed:
            errors.append("%s: unknown field (allowed: %s)" % (_join(path, key), ", ".join(allowed)))
    return True


def _check_text(value, path, errors, max_len=None):
    if not isinstance(value, str):
        errors.append("%s: expected a string, got %s" % (path, _show(value)))
    elif not value.strip():
        errors.append("%s: must not be empty" % path)
    elif max_len is not None and len(value) > max_len:
        errors.append("%s: too long (%d characters, max %d)" % (path, len(value), max_len))


def _check_pattern(value, path, pattern, description, errors):
    if not isinstance(value, str):
        errors.append("%s: expected a string, got %s" % (path, _show(value)))
    elif not pattern.match(value):
        errors.append("%s: %s is not valid; use %s" % (path, _show(value), description))


def _check_enum(value, path, choices, errors):
    if value not in choices:
        errors.append("%s: %s is not one of %s" % (path, _show(value), ", ".join(choices)))


def _check_list(value, path, errors, min_items=0, unique=False, choices=None, hint=None):
    if not isinstance(value, list):
        errors.append("%s: expected a list, got %s" % (path, _show(value)))
        return
    if len(value) < min_items:
        message = "%s: expected at least %d item%s" % (path, min_items, "" if min_items == 1 else "s")
        errors.append(message + ("; " + hint if hint else ""))
    for i, item in enumerate(value):
        item_path = "%s[%d]" % (path, i)
        if choices is not None:
            _check_enum(item, item_path, choices, errors)
        else:
            _check_text(item, item_path, errors)
    if unique:
        seen = set()
        for item in value:
            if isinstance(item, str) and item in seen:
                errors.append("%s: %s is listed twice" % (path, _show(item)))
            seen.add(item if isinstance(item, str) else None)


def _check_datetime(value, path, errors):
    if not isinstance(value, str) or "T" not in value or parse_datetime(value) is None:
        errors.append("%s: expected an ISO 8601 date-time like 2026-10-21T14:05:00+00:00, got %s"
                      % (path, _show(value)))


def _check_date(value, path, errors):
    ok = isinstance(value, str) and DATE_RE.match(value)
    if ok:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            ok = False
    if not ok:
        errors.append("%s: expected a date like 2026-10-21, got %s" % (path, _show(value)))


def parse_datetime(value):
    try:
        # fromisoformat only accepts a trailing "Z" from Python 3.11 on.
        return dt.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _join(path, key):
    return "%s.%s" % (path, key) if path else key


def _show(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."


# ---------------------------------------------------------------- save / merge


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_entry_file(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        raise EntryError(["%s: file not found" % path])
    except json.JSONDecodeError as e:
        raise EntryError(["%s: not valid JSON (line %d, column %d: %s)" % (path, e.lineno, e.colno, e.msg)])


def save(src, now=None):
    """Validate the entry at src and upsert it by task.id.

    Returns a dict with status ("new", "updated" or "unchanged"), the saved paths
    and how many decisions, questions and quiz items were added.
    """
    src = Path(src)
    incoming = load_entry_file(src)
    errors = validate_entry(incoming, mode="input")
    if errors:
        raise EntryError(errors)

    now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    task = incoming["task"]
    json_path, md_path = entry_paths(task["project"], task["id"])
    existing_path = find_entry(task["id"])

    notes = []
    if "review" in incoming:
        notes.append("note: ignored the review block; review dates are managed by store.py")

    if existing_path is None:
        entry, added = _new_entry(incoming, now)
        status = "new"
    else:
        if existing_path.parent.name != task["project"]:
            raise EntryError(["task.id: %s is already saved under project %r (%s); use a different id or the same project"
                              % (task["id"], existing_path.parent.name, existing_path)])
        json_path, md_path = existing_path, existing_path.with_suffix(".md")
        existing = load_json(existing_path)
        entry, added = _merge(existing, incoming)
        status = "unchanged" if _without_updated_at(entry) == _without_updated_at(existing) else "updated"
        if status == "updated":
            entry["task"]["updated_at"] = now.isoformat()
        else:
            entry = existing

    stored_errors = validate_entry(entry, mode="stored")
    if stored_errors:
        raise EntryError(["merged entry is invalid: " + e for e in stored_errors])

    if status != "unchanged":
        _write_atomic(json_path, json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
    markdown = render_markdown(entry)
    if not md_path.exists() or md_path.read_text(encoding="utf-8") != markdown:
        _write_atomic(md_path, markdown)

    if _is_inside(src, tmp_dir()):
        src.unlink()

    return {"status": status, "id": entry["task"]["id"], "json": json_path, "md": md_path,
            "added": added, "notes": notes}


def _new_entry(incoming, now):
    entry = copy.deepcopy(incoming)
    entry.pop("review", None)
    task = entry["task"]
    task.setdefault("created_at", now.isoformat())
    task.setdefault("updated_at", task["created_at"])
    added = {}
    for key, field in MERGE_KEYS.items():
        entry[key] = _append_new([], entry[key], field)
        added[key] = len(entry[key])
    created = parse_datetime(task["created_at"]).date()
    entry["review"] = {
        "due": (created + dt.timedelta(days=FIRST_INTERVAL_DAYS)).isoformat(),
        "interval_days": FIRST_INTERVAL_DAYS,
        "last_reviewed": None,
        "times_reviewed": 0,
    }
    return canonical(entry), added


def _merge(existing, incoming):
    """Update task fields, append only new decisions/questions/quiz items, keep review."""
    entry = copy.deepcopy(existing)
    task = dict(existing["task"])
    task.update(incoming["task"])
    task["created_at"] = existing["task"]["created_at"]
    task["updated_at"] = existing["task"].get("updated_at", task["created_at"])
    entry["task"] = task
    entry["schema_version"] = SCHEMA_VERSION
    added = {}
    for key, field in MERGE_KEYS.items():
        before = len(entry.get(key, []))
        entry[key] = _append_new(entry.get(key, []), incoming[key], field)
        added[key] = len(entry[key]) - before
    if "code" in incoming:
        entry["code"] = copy.deepcopy(incoming["code"])
    return canonical(entry), added


def _append_new(items, new_items, field):
    result = list(items)
    seen = {_merge_key(item[field]) for item in items}
    for item in new_items:
        key = _merge_key(item[field])
        if key not in seen:
            seen.add(key)
            result.append(copy.deepcopy(item))
    return result


def _merge_key(text):
    return " ".join(text.split()).casefold()


def _without_updated_at(entry):
    entry = copy.deepcopy(entry)
    entry.get("task", {}).pop("updated_at", None)
    return entry


def canonical(entry):
    """Order keys like the schema so stored files diff cleanly."""
    orders = {"task": TASK_FIELDS, "code": CODE_FIELDS, "review": REVIEW_FIELDS}
    item_orders = {"decisions": DECISION_FIELDS, "questions": QUESTION_FIELDS, "quiz": QUIZ_FIELDS}
    out = {}
    for key in TOP_FIELDS:
        if key not in entry:
            continue
        value = entry[key]
        if key in orders:
            value = _ordered(value, orders[key])
        elif key in item_orders:
            value = [_ordered(item, item_orders[key]) for item in value]
        out[key] = value
    return out


def _ordered(obj, order):
    return {key: obj[key] for key in order if key in obj}


def _write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _is_inside(path, folder):
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- markdown

FENCE_LANGUAGES = {
    ".py": "python", ".php": "php", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript",
    ".tsx": "tsx", ".go": "go", ".rb": "ruby", ".java": "java", ".kt": "kotlin", ".rs": "rust",
    ".cs": "csharp", ".swift": "swift", ".sql": "sql", ".sh": "bash", ".c": "c", ".cpp": "cpp",
    ".ex": "elixir", ".dart": "dart", ".scala": "scala", ".vue": "vue", ".yml": "yaml", ".yaml": "yaml",
}


def render_markdown(entry):
    task = entry["task"]
    lines = ["# " + task["title"], ""]

    lines.append("- **Task:** `%s`" % task["id"])
    lines.append("- **Project:** " + task["project"])
    if task.get("repo"):
        lines.append("- **Repo:** " + task["repo"])
    if task.get("branch"):
        lines.append("- **Branch:** `%s`" % task["branch"])
    lines.append("- **Stack:** " + ", ".join(task["stack"]))
    lines.append("- **Layers:** " + ", ".join(layer.replace("_", " ") for layer in task["layers"]))
    lines.append("- **Risk:** " + task["risk"])
    logged = parse_datetime(task["created_at"]).date().isoformat() if task.get("created_at") else None
    if logged:
        lines.append("- **Logged:** " + logged)
    if entry.get("review"):
        lines.append("- **Review due:** " + entry["review"]["due"])
    lines.append("")

    for heading, key in (("How it works", "how_it_works"),
                         ("What surprised me", "surprised_me"),
                         ("What could bite again", "would_bite_again")):
        lines += ["## " + heading, "", task[key], ""]

    if entry["decisions"]:
        lines += ["## Decisions", ""]
        for i, d in enumerate(entry["decisions"], 1):
            lines.append("### %d. %s" % (i, d["title"]))
            lines.append("")
            lines.append("*%s, %s*" % (d["kind"], "reversible" if d["reversible"] else "hard to reverse"))
            lines.append("")
            lines.append("- **Chose:** " + d["chosen"])
            lines.append("- **Rejected:**")
            lines += ["  - " + alt for alt in d["rejected"]]
            lines.append("- **Why:** " + d["why"])
            if d.get("impact"):
                lines.append("- **Impact:** " + d["impact"])
            lines.append("- **Files:** " + ", ".join("`%s`" % f for f in d["files"]))
            lines.append("")

    lines += ["## Questions", ""]
    for q in entry["questions"]:
        lines.append("- **I asked:** " + q["asked"])
        lines.append("- **I should have asked:** " + q["should_have_asked"])
        lines.append("- **How I drove it (%d/5):** %s" % (q["rating"], q["feedback"]))
        lines.append("")

    lines += ["## Quiz", ""]
    for i, item in enumerate(entry["quiz"], 1):
        lines.append("**%d. %s.** %s" % (i, item["type"].capitalize(), item["question"]))
        lines.append("")
        lines.append("<details><summary>Answer</summary>")
        lines.append("")
        lines.append(item["answer"])
        lines.append("")
        lines.append("Proof: `%s`" % item["file"])
        lines.append("")
        lines.append("</details>")
        lines.append("")

    code = entry.get("code")
    if code:
        lines += ["## Code", "", "`%s`" % code["file"], ""]
        if code.get("note"):
            lines += [code["note"], ""]
        language = FENCE_LANGUAGES.get(os.path.splitext(code["file"])[1].lower(), "")
        for label, key in (("Before", "before"), ("After", "after")):
            fence = _fence_for(code[key])
            lines += ["**%s**" % label, "", fence + language, code[key], fence, ""]

    return "\n".join(lines).rstrip("\n") + "\n"


def _fence_for(text):
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


# ---------------------------------------------------------------- notion
#
# Notion is a one-way view of the local entries. notion_plan() works out the
# next Notion MCP calls to make, with arguments in the exact shape the tools
# take; the skill runs them verbatim and hands the returned URLs to
# notion_record(). Each round only plans calls whose inputs (page, database and
# data source IDs) are already recorded, so repeating plan -> calls -> record
# until the plan is empty does first-run setup, new pages and updates alike.
# Sync state lives in <home>/notion.json, never in the entries.

NOTION_PAGE_TITLE = "Learning Log"
NOTION_PAGE_INTRO = (
    "Lessons from my coding sessions, written by the /log skill. "
    "The JSON files in ~/.learning-log are the source of truth; this page is a view of them, "
    "so edits made here can be overwritten."
)
NOTION_TEXT_LIMIT = 2000
LAYER_LABELS = {"business_logic": "business logic", "code": "code",
                "architecture": "architecture", "stack": "stack"}
KIND_COLORS = (("product", "blue"), ("architecture", "purple"), ("security", "red"),
               ("workaround", "orange"), ("deferred", "yellow"), ("process", "gray"))
NOTION_VIEWS = {
    "review_due": {"database": "tasks", "name": "Review due",
                   "configure": 'FILTER "Review due" <= "today"; SORT BY "Review due" ASC'},
    "tech_debt": {"database": "decisions", "name": "Tech debt",
                  "configure": 'FILTER "Kind" IN ("workaround", "deferred"); SORT BY "Decision" ASC'},
}
# Characters Notion-flavored Markdown treats as syntax outside code.
NOTION_ESCAPE_RE = re.compile(r"([\\*~`$\[\]<>{}|^])")
DOTTED_NAME_RE = re.compile(r"(?<![\w`/:.-])(?:[\w-]+/)*[\w-]+(?:\.[\w-]+)+(?![\w`])")
NOTION_ID_RE = re.compile(r"([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


def notion_state_path():
    return home() / "notion.json"


def load_notion_state():
    path = notion_state_path()
    state = load_json(path) if path.exists() else {}
    state.setdefault("version", 1)
    state.setdefault("workspace", {})
    state["workspace"].setdefault("databases", {})
    state["workspace"].setdefault("views", {})
    state.setdefault("entries", {})
    return state


def notion_id(value):
    """The bare 32-hex ID inside a Notion URL, UUID or collection:// URI."""
    matches = NOTION_ID_RE.findall(value or "")
    if not matches:
        raise EntryError(["%r does not contain a Notion ID" % value])
    return matches[-1].replace("-", "").lower()


def notion_escape(text):
    return NOTION_ESCAPE_RE.sub(r"\\\1", text)


def notion_text(text):
    """Escape text for Notion, wrapping file and code names in inline code.

    Notion turns bare names like store.py or SKILL.md into web links (.py and
    .md are real domains), so anything shaped like a dotted name becomes code.
    """
    out = []
    last = 0
    for match in DOTTED_NAME_RE.finditer(text):
        name = match.group(0)
        if len(name.rsplit(".", 1)[1]) < 2 or not re.search(r"[A-Za-z]", name):
            continue  # "e.g", version numbers
        out.append(notion_escape(text[last:match.start()]))
        out.append("`%s`" % name)
        last = match.end()
    out.append(notion_escape(text[last:]))
    return "".join(out)


def render_notion_content(entry):
    """The Task page body: quiz toggles and the code snippet, in Notion-flavored Markdown."""
    lines = ["## Quiz", ""]
    for i, item in enumerate(entry["quiz"], 1):
        lines += [
            "<toggle>",
            "**%d. %s.** %s" % (i, item["type"].capitalize(), notion_text(item["question"])),
            "",
            notion_text(item["answer"]),
            "",
            "Proof: `%s`" % item["file"].replace("`", "'"),
            "</toggle>",
            "",
        ]
    code = entry.get("code")
    if code:
        lines += ["## Code", "", "`%s`" % code["file"].replace("`", "'"), ""]
        if code.get("note"):
            lines += [notion_text(code["note"]), ""]
        language = FENCE_LANGUAGES.get(os.path.splitext(code["file"])[1].lower(), "")
        for label, key in (("Before", "before"), ("After", "after")):
            fence = _fence_for(code[key])
            lines += ["**%s**" % label, "", fence + language, code[key], fence, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _rich(text):
    # Notion parses text properties as Markdown too, so they get the same escaping as page content.
    clipped = text if len(text) <= NOTION_TEXT_LIMIT else text[:NOTION_TEXT_LIMIT - 1] + "…"
    return notion_text(clipped)


def _option(text):
    # Notion option names can't contain commas.
    return " ".join(text.replace(",", " ").split())


def _date_props(name, value):
    return {"date:%s:start" % name: value, "date:%s:is_datetime" % name: 0}


def notion_task_properties(entry):
    task = entry["task"]
    props = {
        "Name": notion_text(task["title"]),
        "Task ID": task["id"],
        "Project": task["project"],
        "Repo": task.get("repo") or "",
        "Branch": task.get("branch") or "",
        "Stack": [_option(s) for s in task["stack"]],
        "Layers": [LAYER_LABELS[layer] for layer in task["layers"]],
        "Risk": task["risk"],
        "How it works": _rich(task["how_it_works"]),
        "What surprised me": _rich(task["surprised_me"]),
        "What could bite again": _rich(task["would_bite_again"]),
    }
    props.update(_date_props("Logged", parse_datetime(task["created_at"]).date().isoformat()))
    if entry.get("review"):
        props.update(_date_props("Review due", entry["review"]["due"]))
    return props


def notion_decision_properties(decision, task_url):
    props = {
        "Decision": notion_text(decision["title"]),
        "Chosen": _rich(decision["chosen"]),
        "Rejected": _rich("\n".join(decision["rejected"])),
        "Why": _rich(decision["why"]),
        "Kind": decision["kind"],
        "Reversible": "__YES__" if decision["reversible"] else "__NO__",
        "Files": _rich(", ".join(decision["files"])),
        "Task": [task_url],
    }
    if decision.get("impact"):
        props["Impact"] = _rich(decision["impact"])
    return props


def notion_question_properties(question, task_url):
    return {
        "What I asked": notion_text(question["asked"]),
        "What I should have asked": _rich(question["should_have_asked"]),
        "Rating": question["rating"],
        "Feedback": _rich(question["feedback"]),
        "Task": [task_url],
    }


def notion_task_hash(entry):
    payload = {"properties": notion_task_properties(entry), "content": render_notion_content(entry)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _sql_options(values, colors=None):
    parts = []
    for value in values:
        quoted = "'%s'" % value.replace("'", "''")
        parts.append("%s:%s" % (quoted, colors.get(value, "default") if colors else "default"))
    return ", ".join(parts)


def notion_ddl(kind, entries=(), tasks_data_source_id=None):
    """CREATE TABLE statements for notion-create-database."""
    if kind == "tasks":
        projects = sorted({e["task"]["project"] for e in entries})
        stacks = sorted({_option(s) for e in entries for s in e["task"]["stack"]})
        layers = [LAYER_LABELS[layer] for layer in LAYERS]
        columns = [
            '"Name" TITLE', '"Task ID" RICH_TEXT',
            '"Project" SELECT(%s)' % _sql_options(projects),
            '"Repo" RICH_TEXT', '"Branch" RICH_TEXT',
            '"Stack" MULTI_SELECT(%s)' % _sql_options(stacks),
            '"Layers" MULTI_SELECT(%s)' % _sql_options(layers),
            '"Risk" SELECT(%s)' % _sql_options(RISKS, {"low": "green", "medium": "yellow", "high": "red"}),
            '"How it works" RICH_TEXT', '"What surprised me" RICH_TEXT', '"What could bite again" RICH_TEXT',
            '"Logged" DATE', '"Review due" DATE',
        ]
    elif kind == "decisions":
        columns = [
            '"Decision" TITLE', '"Chosen" RICH_TEXT', '"Rejected" RICH_TEXT', '"Why" RICH_TEXT',
            '"Impact" RICH_TEXT',
            '"Kind" SELECT(%s)' % _sql_options([k for k, _ in KIND_COLORS], dict(KIND_COLORS)),
            '"Reversible" CHECKBOX', '"Files" RICH_TEXT',
            "\"Task\" RELATION('%s', DUAL 'Decisions')" % tasks_data_source_id,
        ]
    else:
        columns = [
            '"What I asked" TITLE', '"What I should have asked" RICH_TEXT', '"Rating" NUMBER',
            '"Feedback" RICH_TEXT',
            "\"Task\" RELATION('%s', DUAL 'Questions')" % tasks_data_source_id,
        ]
    return "CREATE TABLE (%s)" % ", ".join(columns)


def _action(ref, calls, record, note=None):
    action = {"ref": ref, "calls": calls, "record": record}
    if note:
        action["note"] = note
    return action


def _call(tool, arguments):
    return {"tool": tool, "arguments": arguments}


def _setup_actions(ws, entries):
    page = ws.get("page")
    dbs = ws["databases"]
    if not page:
        return [_action("setup:page", [_call("notion-create-pages", {
            "creation_mode": "draft",
            "pages": [{"properties": {"title": NOTION_PAGE_TITLE}, "icon": "📓", "content": NOTION_PAGE_INTRO}],
        })], ["url"], note="Before creating, search Notion for an existing 'Learning Log' page holding "
                           "Tasks, Decisions and Questions databases; if one exists, record it instead.")]
    if "tasks" not in dbs:
        return [_action("setup:db:tasks", [_call("notion-create-database", {
            "parent": {"type": "page_id", "page_id": notion_id(page["url"])},
            "title": "Tasks",
            "schema": notion_ddl("tasks", entries),
        })], ["url", "data_source_id"])]
    actions = []
    tasks_ds = notion_id(dbs["tasks"]["data_source_id"])
    for kind, title in (("decisions", "Decisions"), ("questions", "Questions")):
        if kind not in dbs:
            actions.append(_action("setup:db:" + kind, [_call("notion-create-database", {
                "parent": {"type": "page_id", "page_id": notion_id(page["url"])},
                "title": title,
                "schema": notion_ddl(kind, tasks_data_source_id=tasks_ds),
            })], ["url", "data_source_id"]))
    for key, view in NOTION_VIEWS.items():
        db = dbs.get(view["database"])
        if key not in ws["views"] and db:
            actions.append(_action("setup:view:" + key, [_call("notion-create-view", {
                "database_id": notion_id(db["url"]),
                "data_source_id": db["data_source_id"],
                "name": view["name"],
                "type": "table",
                "configure": view["configure"],
            })], ["url"]))
    return actions


def _pending_items(entry, synced, kind):
    """The decisions or questions of an entry not yet in Notion, in entry order."""
    field = MERGE_KEYS[kind]
    done = synced.get(kind, {})
    return [item for item in entry[kind] if _merge_key(item[field]) not in done]


def notion_plan(task_id=None):
    state = load_notion_state()
    entries = [entry for _, entry in iter_entries()]
    if task_id:
        entries = [e for e in entries if e["task"]["id"].casefold() == task_id.casefold()]
    entries.sort(key=lambda e: (e["task"].get("created_at", ""), e["task"]["id"]))
    ws = state["workspace"]
    links = {}
    if not entries:
        return {"status": "done", "actions": [], "links": links}

    actions = _setup_actions(ws, entries)
    if actions or len(ws["databases"]) < 3:
        return {"status": "todo", "actions": actions, "links": links}

    dbs = ws["databases"]
    for entry in entries:
        tid = entry["task"]["id"]
        synced = state["entries"].get(tid, {})
        url = synced.get("page_url")
        properties = notion_task_properties(entry)
        content = render_notion_content(entry)
        if not url:
            actions.append(_action("task:" + tid, [_call("notion-create-pages", {
                "parent": {"type": "data_source_id", "data_source_id": notion_id(dbs["tasks"]["data_source_id"])},
                "pages": [{"properties": properties, "content": content}],
            })], ["url"]))
            continue
        links[tid] = url
        if synced.get("task_hash") != notion_task_hash(entry):
            page_id = notion_id(url)
            action = _action("task:" + tid, [
                _call("notion-update-page", {"page_id": page_id, "command": "update_properties",
                                             "properties": properties}),
                _call("notion-update-page", {"page_id": page_id, "command": "replace_content",
                                             "new_str": content}),
            ], ["url"], note="Updating an existing page: record this action's url.")
            action["url"] = url
            actions.append(action)
        for kind, build in (("decisions", notion_decision_properties), ("questions", notion_question_properties)):
            items = _pending_items(entry, synced, kind)
            if items:
                actions.append(_action("%s:%s" % (kind, tid), [_call("notion-create-pages", {
                    "parent": {"type": "data_source_id", "data_source_id": notion_id(dbs[kind]["data_source_id"])},
                    "pages": [{"properties": build(item, url)} for item in items],
                })], ["urls"]))
    return {"status": "todo" if actions else "done", "actions": actions, "links": links}


def notion_record(results):
    """Store the URLs returned by the calls of one plan round. Recording the same results twice is harmless."""
    if not isinstance(results, dict):
        raise EntryError(["results: expected an object mapping action refs to what they returned"])
    state = load_notion_state()
    ws = state["workspace"]
    entries = {e["task"]["id"]: e for _, e in iter_entries()}
    errors = []
    for ref, result in results.items():
        if not isinstance(result, dict):
            errors.append("%s: expected an object" % ref)
            continue
        kind, _, rest = ref.partition(":")
        try:
            if kind == "setup":
                _record_setup(ws, rest, result)
            elif kind == "task":
                entry = _entry_for(entries, rest)
                notion_id(_required_url(result, ref))
                synced = state["entries"].setdefault(entry["task"]["id"], {})
                synced["page_url"] = result["url"]
                synced["task_hash"] = notion_task_hash(entry)
            elif kind in ("decisions", "questions"):
                entry = _entry_for(entries, rest)
                synced = state["entries"].setdefault(entry["task"]["id"], {})
                _record_items(entry, synced, kind, result, ref)
            else:
                errors.append("%s: unknown action ref" % ref)
        except EntryError as e:
            errors.extend("%s: %s" % (ref, message) for message in e.errors)
    if errors:
        raise EntryError(errors)
    _write_atomic(notion_state_path(), json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    return state


def _required_url(result, ref):
    url = result.get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://", "view://", "collection://")):
        raise EntryError(["expected \"url\" with the Notion URL the call returned"])
    return url


def _record_setup(ws, what, result):
    url = _required_url(result, "setup:" + what)
    notion_id(url)
    if what == "page":
        ws["page"] = {"url": url}
    elif what.startswith("db:") and what[3:] in ("tasks", "decisions", "questions"):
        ds = result.get("data_source_id")
        if not isinstance(ds, str):
            raise EntryError(["expected \"data_source_id\" from the <data-source url=\"collection://...\"> tag"])
        ws["databases"][what[3:]] = {"url": url, "data_source_id": "collection://" + notion_id(ds)}
    elif what.startswith("view:") and what[5:] in NOTION_VIEWS:
        ws["views"][what[5:]] = {"url": url}
    else:
        raise EntryError(["unknown setup step"])


def _entry_for(entries, task_id):
    for tid, entry in entries.items():
        if tid.casefold() == task_id.casefold():
            return entry
    raise EntryError(["no local entry with task id %r" % task_id])


def _record_items(entry, synced, kind, result, ref):
    done = synced.setdefault(kind, {})
    if "existing" in result:
        # Rebuilding the map from rows already in Notion: {title or asked text: page URL}.
        for text, url in result["existing"].items():
            notion_id(url)
            done[_merge_key(text)] = url
        return
    urls = result.get("urls")
    pending = _pending_items(entry, synced, kind)
    if not isinstance(urls, list) or len(urls) != len(pending):
        raise EntryError(["expected \"urls\" with %d page URL%s, in the order the pages were sent"
                          % (len(pending), "" if len(pending) == 1 else "s")])
    for item, url in zip(pending, urls):
        notion_id(url)
        done[_merge_key(item[MERGE_KEYS[kind]])] = url


# ---------------------------------------------------------------- queries


def due_entries(today, project=None):
    result = []
    for path, entry in iter_entries(project):
        review = entry.get("review") or {}
        if review.get("due") and review["due"] <= today.isoformat():
            result.append((path, entry))
    result.sort(key=lambda pair: (pair[1]["review"]["due"], pair[1]["task"]["id"]))
    return result


def summary_line(entry):
    task = entry["task"]
    created = parse_datetime(task["created_at"]).date().isoformat() if task.get("created_at") else "----------"
    due = (entry.get("review") or {}).get("due", "-")
    return "%s  %-16s  %-24s  %s  (due %s)" % (created, task["project"], task["id"], task["title"], due)


# ---------------------------------------------------------------- CLI


def _cmd_save(args):
    result = save(args.entry)
    added = result["added"]
    if result["status"] == "unchanged":
        detail = "unchanged"
    else:
        detail = "%s: +%s, +%s, +%d quiz" % (
            result["status"], _plural(added["decisions"], "decision"),
            _plural(added["questions"], "question"), added["quiz"])
    for note in result["notes"]:
        print(note, file=sys.stderr)
    print("saved %s (%s)" % (result["id"], detail))
    print("json: %s" % result["json"])
    print("md:   %s" % result["md"])
    return 0


def _plural(count, noun):
    return "%d %s%s" % (count, noun, "" if count == 1 else "s")


def _cmd_validate(args):
    errors = validate_entry(load_entry_file(args.entry), mode="stored" if args.stored else "input")
    if errors:
        raise EntryError(errors)
    print("valid: %s" % args.entry)
    return 0


def _cmd_list(args):
    rows = sorted(iter_entries(args.project), key=lambda pair: pair[1]["task"].get("created_at", ""), reverse=True)
    if not rows:
        print("no entries yet in %s" % entries_dir())
    for _, entry in rows:
        print(summary_line(entry))
    return 0


def _cmd_due(args):
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    rows = due_entries(today, args.project)
    if not rows:
        print("nothing due for review")
    for _, entry in rows:
        print(summary_line(entry))
    return 0


def _cmd_show(args):
    path = find_entry(args.task_id)
    if path is None:
        raise EntryError(["%s: no entry with this task id in %s" % (args.task_id, entries_dir())])
    md_path = path.with_suffix(".md")
    sys.stdout.write(md_path.read_text(encoding="utf-8") if md_path.exists() else render_markdown(load_json(path)))
    return 0


def _cmd_home(args):
    tmp_dir().mkdir(parents=True, exist_ok=True)
    print("home: %s" % home())
    print("tmp:  %s" % tmp_dir())
    return 0


def _cmd_notion_plan(args):
    print(json.dumps(notion_plan(args.task_id), indent=2, ensure_ascii=False))
    return 0


def _cmd_notion_record(args):
    path = Path(args.results)
    results = load_entry_file(path)
    state = notion_record(results)
    if _is_inside(path, tmp_dir()):
        path.unlink()
    print("recorded %s (%d entries synced)" % (", ".join(results) or "nothing", len(state["entries"])))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="store.py", description="Learning Log local store.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("save", help="validate, upsert, render .md, print the saved paths")
    p.add_argument("entry")
    p.set_defaults(func=_cmd_save)

    p = sub.add_parser("validate", help="validate only")
    p.add_argument("entry")
    p.add_argument("--stored", action="store_true", help="skip per-run count limits (for merged entries)")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("list", help="one line per entry")
    p.add_argument("--project")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("due", help="entries due for review today or earlier")
    p.add_argument("--project")
    p.add_argument("--today", help="pretend today is YYYY-MM-DD")
    p.set_defaults(func=_cmd_due)

    p = sub.add_parser("show", help="print the rendered Markdown")
    p.add_argument("task_id")
    p.set_defaults(func=_cmd_show)

    p = sub.add_parser("home", help="print the storage root and the temp dir for drafts")
    p.set_defaults(func=_cmd_home)

    p = sub.add_parser("notion-plan", help="print the next Notion tool calls to make, as JSON")
    p.add_argument("task_id", nargs="?", help="only this entry (default: every entry)")
    p.set_defaults(func=_cmd_notion_plan)

    p = sub.add_parser("notion-record", help="record the Notion URLs returned by the planned calls")
    p.add_argument("results", help='JSON file: {"<action ref>": {"url": ...}, ...}')
    p.set_defaults(func=_cmd_notion_record)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except EntryError as e:
        print("error:", file=sys.stderr)
        for message in e.errors:
            print("  - " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
