# `/learning-log:interview` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/learning-log:interview`. It grills the developer on the session they just finished, with questions a senior lead, a PM or a customer would ask. It reviews each answer and stores the results with the entry, locally and in Notion.

**Architecture:** The entry gets an optional `interview` array, validated in `store.py`. A new `store.py interview-add` command appends items to an existing entry, and a full `save` keeps them. Notion gets a 4th database, "Interview", that's synced through the existing plan/record loop. A new skill, `skills/interview/SKILL.md`, runs the conversation. It reuses `/learning-log:log`'s steps by reference to log the session first.

**Tech Stack:** Python 3.9+, standard library only. `unittest`. Claude Code plugin skills. Notion MCP, driven by `store.py notion-plan`.

**Spec:** `docs/superpowers/specs/2026-10-31-interview-design.md`

## Global Constraints

- Python 3.9+, standard library only. No new dependencies.
- Tests use `unittest` with a temporary `LEARNING_LOG_HOME`. Run them on this machine with `py -3 -m unittest discover -s tests` (`python3` is a Store stub here).
- `schema_version` stays `1`, and `interview` is optional, so old entries must stay valid.
- Lightweight and user-friendly (spec "Constraint" section):
  - Short chat output.
  - No new setup.
  - No tool-permission prompts during an interview.
  - Reuse existing helpers. Don't build parallel machinery.
- Never echo a detected secret. Use the existing `scan_secrets` messages.
- `/learning-log:log` stays read-only. Only the interview asks the developer to type.
- Commits: small, one logical change each, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **An entry saved before this feature (no `interview` key) goes through `save`, `interview-add`, render and Notion sync unchanged.** Task 1 tests the validation, Task 2 tests `interview-add` on an entry with no `interview` key, and Task 3 checks the plan for an entry without an interview.
2. **A full `save` after `interview-add` must keep the interview.** This is the B1 flow: the interview runs the log's save every time. Task 2 test.
3. **The developer pastes a secret into `my_answer`.** It must be rejected without echoing the value, and nothing is written. Task 2 test.
4. **An existing Notion workspace with 3 databases** gets exactly one new action, `setup:db:interview`, then syncs interview rows. Task 3 test.
5. **`interview-add` with an unknown task id, or an empty list,** fails with a clear error and writes nothing. Task 2 test.

---

### Task 1: Contract (schema, example, validation)

**Files:**
- Modify: `schema/entry.schema.json`
- Modify: `examples/entry.example.json`
- Modify: `scripts/store.py` (constants near line 33, `validate_entry` near line 134, new `_check_interview_item` after `_check_quiz_item`, `canonical` near line 531)
- Test: `tests/test_store.py` (`ValidationTests`)

**Interfaces:**
- Produces:
  - **Constants in `store.py`:**
    - `INTERVIEW_ASKERS = ("senior", "pm", "customer")`
    - `INTERVIEW_TOPICS = ("technical", "product")`
    - `INTERVIEW_VERDICTS = ("solid", "partial", "missed", "skipped")`
    - `INTERVIEW_FIELDS = ("question", "asker", "topic", "verdict", "my_answer", "feedback", "answer", "say_it", "file", "answered_at")`
    - `INTERVIEW_REQUIRED`, which is `INTERVIEW_FIELDS` without `answered_at`
    - `INTERVIEW_ADD_LIMITS = (1, 5)`
  - **`TOP_FIELDS`** gains `"interview"` between `"quiz"` and `"code"`.
  - **`_check_interview_item(item, path, errors)`**, with these rules:
    - Limits: `question` text max 300, `my_answer` max 2000, `feedback` max 600, `answer` max 500, `say_it` max 300.
    - `my_answer` and `feedback` are text or `None`, and both must be `None` when the verdict is `skipped`.
    - `feedback` must be text when the verdict isn't `skipped`.
    - `answered_at` is optional and is checked with `_check_datetime`.
  - **`validate_entry`** checks an optional `interview` list in both modes, with no count limit.
  - **`canonical`** orders interview items by `INTERVIEW_FIELDS`.

- [ ] **Step 1: Add the `interview` array and `$defs.interview_item` to `schema/entry.schema.json`.** It's optional and not in `required`. Use the exact fields, enums and max lengths above. `my_answer` and `feedback` are `["string","null"]`. Express the skipped rule with `allOf`/`if`/`then`: if the verdict is `skipped`, then `my_answer` and `feedback` are null, else `feedback` is text. Update the top-level `description` to mention that `/learning-log:interview` appends interview items.
- [ ] **Step 2: Add three items to `examples/entry.example.json` under `"interview"`.** Use the LOY-214 facts already in the example:
  - **A `solid` item from the `senior`, topic `technical`:** "Why add a ledger row instead of editing the balance?" with `file` `app/Points/PointsBalance.php`.
  - **A `missed` item from the `pm`, topic `product`:** a member who already spent the points gets refunded, so what does finance see? Set `my_answer: null` and `file` `app/Points/RefundOrderPoints.php`.
  - **A `skipped` item from the `customer`, topic `product`:** "I refunded the order that made me Gold. Am I still Gold?" Set `my_answer` and `feedback` to null and `file` `app/Tiers/TierCalculator.php`.
  - **Wording:** each item has `answered_at` `2026-10-21T10:05:00+00:00`. `say_it` is first person and `feedback` addresses "you".
- [ ] **Step 3: Write the failing tests in `ValidationTests`.**
  ```python
  def test_example_interview_is_valid(self):
      self.assertEqual(store.validate_entry(example()), [])
      self.assertEqual(len(example()["interview"]), 3)

  def test_entry_without_interview_is_still_valid(self):
      e = example(); del e["interview"]
      self.assertEqual(store.validate_entry(e), [])

  def test_interview_enums_and_skipped_rules(self):
      e = example()
      e["interview"][0]["asker"] = "cto"
      e["interview"][2]["feedback"] = "Should be null"
      e["interview"][1]["feedback"] = None
      errors = store.validate_entry(e)
      self.assertTrue(any(m.startswith("interview[0].asker") for m in errors))
      self.assertTrue(any(m.startswith("interview[2].feedback") for m in errors))
      self.assertTrue(any(m.startswith("interview[1].feedback") for m in errors))

  def test_interview_length_limits(self):
      e = example(); e["interview"][0]["say_it"] = "x" * 301
      self.assertTrue(any(m.startswith("interview[0].say_it") for m in store.validate_entry(e)))
  ```
- [ ] **Step 4: Run `py -3 -m unittest tests.test_store.ValidationTests -v`.** Expected: the new tests FAIL. `test_example_interview_is_valid` fails on `interview: unknown field`, or similar.
- [ ] **Step 5: Implement the constants, `_check_interview_item`, and the `validate_entry`/`canonical`/`TOP_FIELDS` changes.** Mirror `_check_quiz_item`'s style.
- [ ] **Step 6: Run `py -3 -m unittest discover -s tests`.** Expected: all PASS. Notion tests that compare exact action lists may now fail, because the example has interview items but nothing plans them yet. If so, leave them for Task 3, which updates them, and note it in the commit message. Everything outside `tests/test_notion.py` must pass.
- [ ] **Step 7: Commit:** `git add schema/entry.schema.json examples/entry.example.json scripts/store.py tests/test_store.py`, then `git commit -m "Schema: add optional interview items to the entry contract"`.

### Task 2: `interview-add`, save merge, Markdown

**Files:**
- Modify: `scripts/store.py` (`_merge`, `_new_entry`, new `add_interview`, `render_markdown`, CLI `_cmd_interview_add` and its parser entry, the module docstring)
- Modify: `examples/entry.example.md` (re-rendered)
- Test: `tests/test_store.py` (new `InterviewTests` class)

**Interfaces:**
- Consumes (Task 1): `_check_interview_item`, `INTERVIEW_ADD_LIMITS`, `INTERVIEW_FIELDS`.
- Produces:
  - **`add_interview(task_id, src, now=None) -> dict`** returns `{"status": "updated"|"unchanged", "id", "json": Path, "md": Path, "added": int, "skipped": int}`.
    - The file at `src` must be a JSON list of 1 to 5 items. Each is validated with `_check_interview_item` at path `interview[i]`, plus `scan_secrets` on the list.
    - `answered_at` is set to `now.isoformat()` when it's missing.
    - Items are appended with `_append_new(existing.get("interview", []), items, "question")`. Existing items are never changed.
    - When something was added, it bumps `task.updated_at`, re-validates in `stored` mode and writes atomically.
    - It always re-renders the Markdown.
    - It deletes `src` when it's inside `tmp_dir()`.
    - It raises `EntryError` when there's no entry: `"<id>: no entry with this task id in <dir>; save the lesson first"`. It also raises `EntryError` on a validation or secret error, in which case nothing is written and the draft is kept.
  - **`_merge`:** keeps `existing["interview"]` and appends only new incoming interview items by `question`. The key is present only when the result is non-empty.
  - **`_new_entry`:** de-duplicates an incoming `interview` by `question` when present.
  - **CLI:** `store.py interview-add <task_id> <items.json>` prints:
    ```
    saved LOY-214 (interview: +3, 1 duplicate skipped)
    json: <path>
    md:   <path>
    ```
    It prints `(interview: unchanged)` when `added == 0`.
  - **Markdown:** a `## Interview` section after Quiz, only when there are items. Each item renders as:
    ```
    **1. Senior asks:** <question>

    - **Verdict:** solid
    - **My answer:** <my_answer>        (omitted when null)
    - **Feedback:** <feedback>          (omitted when null)
    - **Answer:** <answer> (`<file>`)
    - **Say it:** <say_it>
    ```
    The asker labels are `Senior`, `PM` and `Customer`. A `missed` item with a null `my_answer` shows `- **My answer:** I didn't know.`

- [ ] **Step 1: Write the failing tests in `InterviewTests(StoreTestCase)`.** The helper `entry_no_interview()` returns `example()` with `interview` deleted, and `items()` returns `copy.deepcopy(example()["interview"])`.
  ```python
  def test_add_appends_and_skips_duplicates(self):
      self.save(entry_no_interview())
      r = store.add_interview("LOY-214", self.write_draft(items()[:2], "i1.json"), now=NOW)
      self.assertEqual((r["status"], r["added"], r["skipped"]), ("updated", 2, 0))
      r = store.add_interview("loy-214", self.write_draft(items(), "i2.json"), now=NOW)
      self.assertEqual((r["added"], r["skipped"]), (1, 2))
      self.assertEqual(len(self.stored()["interview"]), 3)

  def test_add_sets_answered_at_when_missing(self):
      self.save(entry_no_interview())
      item = items()[0]; del item["answered_at"]
      store.add_interview("LOY-214", self.write_draft([item], "i.json"), now=NOW)
      self.assertEqual(self.stored()["interview"][0]["answered_at"], NOW.isoformat())

  def test_add_without_entry_fails_and_writes_nothing(self):
      with self.assertRaises(store.EntryError) as cm:
          store.add_interview("NOPE-1", self.write_draft(items()[:1], "i.json"), now=NOW)
      self.assertIn("save the lesson first", cm.exception.errors[0])

  def test_add_rejects_empty_list_and_too_many(self):
      self.save(entry_no_interview())
      for bad in ([], items() * 2):
          with self.assertRaises(store.EntryError):
              store.add_interview("LOY-214", self.write_draft(bad, "i.json"), now=NOW)
      self.assertNotIn("interview", self.stored())

  def test_secret_in_my_answer_is_rejected_without_echo(self):
      self.save(entry_no_interview())
      item = items()[0]; item["my_answer"] = "I used sk_live_" + "a" * 24
      with self.assertRaises(store.EntryError) as cm:
          store.add_interview("LOY-214", self.write_draft([item], "i.json"), now=NOW)
      self.assertTrue(any("interview[0].my_answer" in m for m in cm.exception.errors))
      self.assertFalse(any("sk_live_" in m for m in cm.exception.errors))
      self.assertNotIn("interview", self.stored())

  def test_full_save_keeps_interview(self):
      self.save(entry_no_interview())
      store.add_interview("LOY-214", self.write_draft(items(), "i.json"), now=NOW)
      self.save(entry_no_interview())
      self.assertEqual(len(self.stored()["interview"]), 3)

  def test_markdown_renders_interview(self):
      result = self.save(example())
      md = result["md"].read_text(encoding="utf-8")
      self.assertIn("## Interview", md)
      self.assertIn("**1. Senior asks:**", md)
      self.assertIn("- **My answer:** I didn't know.", md)
      self.assertIn("**3. Customer asks:**", md)

  def test_markdown_without_interview_has_no_section(self):
      result = self.save(entry_no_interview())
      self.assertNotIn("## Interview", result["md"].read_text(encoding="utf-8"))

  def test_draft_in_tmp_removed(self):
      self.save(entry_no_interview())
      path = self.write_draft(items()[:1], "i.json", folder=store.tmp_dir())
      store.add_interview("LOY-214", path, now=NOW)
      self.assertFalse(path.exists())

  def test_cli_interview_add(self):
      self.save(entry_no_interview())
      out = self.run_cli("interview-add", "LOY-214", str(self.write_draft(items(), "i.json")))
      self.assertEqual(out.returncode, 0, out.stderr)
      self.assertIn("saved LOY-214 (interview: +3, 0 duplicates skipped)", out.stdout)
  ```
- [ ] **Step 2: Run `py -3 -m unittest tests.test_store.InterviewTests -v`.** Expected: FAIL, because `add_interview` isn't defined.
- [ ] **Step 3: Implement `add_interview`, the `_merge`/`_new_entry` changes, the `render_markdown` section, `_cmd_interview_add` and the parser entry `interview-add` (help text: "append interview items to a saved entry").** Add the new command to the module docstring.
- [ ] **Step 4: Run `py -3 -m unittest tests.test_store -v`.** Expected: all PASS.
- [ ] **Step 5: Re-render the example Markdown.** Run `py -3 -c "import sys,json;sys.path.insert(0,'scripts');import store;print(store.render_markdown(json.load(open('examples/entry.example.json',encoding='utf-8'))),end='')" > examples/entry.example.md`. Check that `git diff examples/entry.example.md` shows only the new Interview section.
- [ ] **Step 6: Commit:** `git add scripts/store.py tests/test_store.py examples/entry.example.md`, then `git commit -m "store.py: add interview-add and render interview items"`.

### Task 3: Notion "Interview" database

**Files:**
- Modify: `scripts/store.py`:
  - `MERGE_KEYS` area: a new `NOTION_ITEM_KEYS`
  - `notion_ddl`
  - a new `notion_interview_properties`
  - `_setup_actions`
  - `_pending_items`
  - `notion_plan`, where the `< 3` check moves to `< 4`
  - `notion_record`
  - `_record_setup`
  - the `setup:page` note
- Modify: `skills/log/notion.md` (recovery steps)
- Test: `tests/test_notion.py`

**Interfaces:**
- Consumes: interview items (Task 1).
- Produces:
  - **`NOTION_ITEM_KEYS = dict(MERGE_KEYS, interview="question")`.** `_pending_items` and `_record_items` use it, and read items with `entry.get(kind, [])`.
  - **`notion_ddl("interview", tasks_data_source_id=...)`** produces these columns:
    - `"Question" TITLE`
    - `"Asked by" SELECT('senior':blue, 'pm':purple, 'customer':green)`
    - `"Topic" SELECT('technical':gray, 'product':orange)`
    - `"Verdict" SELECT('solid':green, 'partial':yellow, 'missed':red, 'skipped':default)`
    - `"My answer" RICH_TEXT`, `"Feedback" RICH_TEXT`, `"Answer" RICH_TEXT`, `"Say it" RICH_TEXT`, `"File" RICH_TEXT`
    - `"Task" RELATION('<tasks ds>', DUAL 'Interview')`
  - **`notion_interview_properties(item, task_url) -> dict`** returns `Question`, `Asked by`, `Topic`, `Verdict`, `Answer`, `Say it`, `File` and `Task: [task_url]`. `My answer` and `Feedback` are included only when they aren't null. Text goes through `_rich`, and the title through `notion_text`.
  - **The plan sync loop** iterates `("decisions", …), ("questions", …), ("interview", notion_interview_properties)`, and the action refs are `interview:<task-id>`.
  - **`_setup_actions`** creates `setup:db:interview`, titled "Interview", in the same loop as decisions and questions.
  - **`notion_record`** accepts `interview:<id>`, including the `{"existing": {...}}` rebuild keyed by question. `_record_setup` accepts `db:interview`.
  - **The `render_notion_content` and task hash don't change.**

- [ ] **Step 1: Update `NotionTestCase.set_up_workspace`** to also record `"setup:db:interview": {"url": url(5), "data_source_id": ds(5)}`. Update any existing exact-ref assertions so they expect `setup:db:interview` next to decisions and questions, and `interview:LOY-214` after `questions:LOY-214`.
- [ ] **Step 2: Write the failing tests.**
  ```python
  def test_existing_three_db_workspace_gets_only_interview_db(self):
      # record page, tasks, decisions, questions, both views — no interview
      ...
      plan = store.notion_plan()
      self.assertEqual(self.refs(plan), ["setup:db:interview"])
      ddl = plan["actions"][0]["calls"][0]["arguments"]["schema"]
      self.assertIn("\"Task\" RELATION('00000002000000000000000000000002', DUAL 'Interview')", ddl)
      self.assertIn("'missed':red", ddl)

  def test_interview_rows_sync_then_done(self):
      self.set_up_workspace()
      store.notion_record({"task:LOY-214": {"url": url(10)}})
      plan = store.notion_plan()
      action = next(a for a in plan["actions"] if a["ref"] == "interview:LOY-214")
      pages = action["calls"][0]["arguments"]["pages"]
      self.assertEqual(len(pages), 3)
      self.assertEqual(pages[0]["properties"]["Asked by"], "senior")
      self.assertNotIn("My answer", pages[2]["properties"])   # skipped item
      # record decisions/questions/interview urls, then:
      self.assertEqual(store.notion_plan()["status"], "done")

  def test_entry_without_interview_plans_no_interview_action(self): ...

  def test_rebuild_interview_from_existing_rows(self): ...  # {"existing": {question: url}} then no interview action
  ```
- [ ] **Step 3: Run `py -3 -m unittest tests.test_notion -v`.** Expected: the new tests FAIL.
- [ ] **Step 4: Implement the interfaces above.** Change the `setup:page` note and `notion.md` from "Tasks, Decisions and Questions databases" to "Tasks, Decisions and Questions databases (and Interview, if present)".
- [ ] **Step 5: Update `skills/log/notion.md` "Before the first setup call".** Record `setup:db:interview` when the page has an Interview database. Rebuild `interview:<id>` with `{"existing": {"<Question>": "<row url>"}}`. Keep it to two short added clauses.
- [ ] **Step 6: Run `py -3 -m unittest discover -s tests`.** Expected: all PASS.
- [ ] **Step 7: Commit:** `git add scripts/store.py tests/test_notion.py skills/log/notion.md`, then `git commit -m "Notion: sync interview items to a new Interview database"`.

### Task 4: The `/learning-log:interview` skill

**Files:**
- Create: `skills/interview/SKILL.md`

**Interfaces:**
- Consumes:
  - `STORE interview-add <task-id> <file>` (Task 2)
  - `skills/log/SKILL.md` steps 1 to 5
  - `skills/log/notion.md`
- Produces: the `/learning-log:interview` command.

- [ ] **Step 1: Write the frontmatter.**
  - `name: interview`
  - `description`: "Grill the developer on the session they just finished with questions a senior lead, PM or customer would ask, review each answer, and save the results with the session's Learning Log entry. Use when the user runs /learning-log:interview."
  - `disable-model-invocation: true`
  - `allowed-tools`: copy `skills/log/SKILL.md`'s list exactly, then add `Read Grep Glob`. `${CLAUDE_SKILL_DIR}/../../scripts/store.py` resolves to the same script, because both skills sit at `skills/<name>/`.
- [ ] **Step 2: Write the body as short numbered steps that follow spec "Flow" 1 to 9.** Keep it under about 90 lines. Pin these points in it:
  - **Steps 1 to 3:** say "Read `${CLAUDE_SKILL_DIR}/../log/SKILL.md` and do its steps 1 to 5". Its "Nothing worth logging" replies become "Nothing worth interviewing on". Don't repeat its rules.
  - **The question format**, with the asker label, the question and the counter: `**PM asks:** <question> (2/5)`. Then end the turn. Never show the list or any answer.
  - **The reply cases:** an answer, "review this", "I don't know", "where is…?" (point to the file without the answer), and "stop".
  - **The review format**, kept short enough for a phone screen:
    ```
    **Partial.** <what was right, what was missing — 2-3 sentences, to "you">
    **Answer:** <1-3 sentences> (`<file>`)
    **Say it:** "<1-2 sentences, first person>"
    ```
  - **The item JSON shape** (copy the field list from the spec) and the save command `STORE interview-add <task-id> "<dir>/interview-<n>.json"`. Write each file only after its answer is shown.
  - **The rules:**
    - Questions come only from this session.
    - Don't invent facts.
    - Check every `file` exists.
    - No secrets: describe them instead. If `interview-add` reports a secret in `my_answer`, replace that part with a description and save again.
    - No retries.
    - If the context was compacted and the question list is lost, end the interview cleanly.
  - **Finish:** do the Notion sync via `${CLAUDE_SKILL_DIR}/../log/notion.md` only when the Notion tools exist. The final reply is one line, `Interview on <id>: N solid, N partial, N missed[, N skipped]. <md path>`, plus the Notion link.
- [ ] **Step 3: Check the empty-session case.** Run `claude plugin validate --strict .`. Expected: passes. Then run the local copy headless in a scratch folder with a scratch home. In PowerShell: `$env:LEARNING_LOG_HOME = "$env:TEMP\ll-test"; claude -p --plugin-dir D:\learning-log "/learning-log:interview"`. Check `claude --help` for the plugin-dir flag name first. Expected reply: `Nothing worth interviewing on: no work in this session.`
- [ ] **Step 4: Ask the developer to run `/learning-log:interview` in an interactive session that has real work in it, with `LEARNING_LOG_HOME` pointing to a scratch folder.** Show the output: the questions asked, one review, and the saved Markdown section. This is the working agreement's "run it once on a real session". Fix anything that reads long or unclear.
- [ ] **Step 5: Commit:** `git add skills/interview/SKILL.md`, then `git commit -m "Add /learning-log:interview skill"`.

### Task 5: Docs and release

**Files:**
- Modify: `README.md`, `.claude/CLAUDE.md`, `.claude-plugin/plugin.json`, `docs/superpowers/specs/2026-10-31-interview-design.md` (the status line)

- [ ] **Step 1: Update `README.md`.** Add a short "Interview yourself" section: what `/learning-log:interview` does, when to run it (right after the work, in the same chat), and that it's the one command where you type. Show one example question and one example review. Mention the Interview database in the Notion part.
- [ ] **Step 2: Update `.claude/CLAUDE.md`:**
  - **Principle 1:** add the exception: "`/learning-log:interview` is opt-in practice where the developer types answers; everything else stays read-only."
  - **Product line:** mention `/learning-log:interview`.
  - **Architecture:** add the interview skill.
  - **Repository layout:** add `skills/interview/SKILL.md` and `docs/superpowers/`.
  - **Entry contract:** add an **interview** (optional) part with the fields.
  - **`store.py` commands:** add `interview-add <task-id> <items.json>`.
  - **Phase 2 text:** four databases.
  - **New lightweight rule:** add to Core principles or Conventions: "Keep the plugin user-friendly and lightweight: pick the option with less setup, shorter output and less new code."
- [ ] **Step 3: Release prep.** Set `version` to `0.2.0` in `.claude-plugin/plugin.json`, and mention `/learning-log:interview` in its `description`. Update CLAUDE.md "current: 0.1.1" to 0.2.0. Set the spec's status to "approved, implemented".
- [ ] **Step 4: Verify.** Run `claude plugin validate --strict .` and `py -3 -m unittest discover -s tests`. Expected: validation passes, and all tests PASS.
- [ ] **Step 5: Commit:** `git add README.md .claude/CLAUDE.md .claude-plugin/plugin.json docs/superpowers/`, then `git commit -m "Release 0.2.0: /learning-log:interview"`. Don't push without asking.
