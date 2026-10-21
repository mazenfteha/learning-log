---
name: log
description: Turn the current coding session into a short, project-specific lesson saved to the local Learning Log (JSON plus readable Markdown). Use when the user runs /log or asks to log what they learned in this session.
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git show *) Bash(git rev-parse *) Bash(git remote *) Bash(python3 --version) Bash(python --version) Bash(py -3 --version) Bash(python3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) Bash(python "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) Bash(py -3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(git status *) PowerShell(git diff *) PowerShell(git log *) PowerShell(git show *) PowerShell(git rev-parse *) PowerShell(git remote *) PowerShell(python3 --version) PowerShell(python --version) PowerShell(py -3 --version) PowerShell(python3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(python "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(py -3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) mcp__claude_ai_Notion__notion-search mcp__claude_ai_Notion__notion-fetch mcp__claude_ai_Notion__notion-create-pages mcp__claude_ai_Notion__notion-update-page mcp__claude_ai_Notion__notion-create-database mcp__claude_ai_Notion__notion-create-view mcp__claude_ai_Notion__notion-query-data-sources mcp__claude_ai_Notion__notion-get-async-task
---

# Learning Log: /log

Turn this session into a lesson the developer only has to read. You write everything; the developer types nothing. The lesson is saved as JSON (the source of truth) and rendered to Markdown by `store.py`.

Paths used below:

- `STORE` means `<python> "${CLAUDE_SKILL_DIR}/../../scripts/store.py"`, where `<python>` is found at the start of step 3. Always keep the quotes: on Windows the path has backslashes.
- The entry contract is `${CLAUDE_SKILL_DIR}/../../schema/entry.schema.json`. A complete good entry is `${CLAUDE_SKILL_DIR}/../../examples/entry.example.json`. Read the example once before drafting if you haven't seen it in this session.

## 1. Gather the session

Start from this conversation: what the developer asked, what you did, what went wrong and was redone, what you decided (including choices you made silently while coding), and what you explained.

Then check what really changed:

- `git status --short`
- `git diff --stat`, then `git diff` and `git diff --staged` for the files that matter
- `git log --oneline -15`, and `git show --stat <sha>` for commits made in this session
- `git rev-parse --abbrev-ref HEAD` for the branch, and `git remote get-url origin` for the repo

If it is not a git repository, use the conversation and the files you edited. Never open `.env` files, key files or credentials to fill in an entry.

## 2. Decide if it is worth logging

Log only if there is something worth taking away: a business rule, a non-obvious bug, a design decision, a new library or framework concept, or a pattern in this codebase.

If the session was trivial (renames, formatting, typos, copy changes, routine dependency bumps), reply with one line, `Nothing worth logging: <reason>.`, and stop. An empty log is better than a padded one.

## 3. Draft the entry

First find Python: run `python3 --version`, then `python --version`, then `py -3 --version`, and stop at the first that prints `Python 3.`. That command is `<python>`. On Windows, `python3` and `python` are often Store stubs that print "Python was not found"; that counts as a failure.

Write one JSON object that follows the schema. Set `schema_version` to 1. Do not write `review`, `created_at` or `updated_at`; `store.py` manages them.

**task**
- `id`: use the ticket ID if the branch, commits or conversation name one (`PROJ-123`; GitHub issue #42 becomes `gh-42`). Otherwise use `<project>-<YYYYMMDD>-<short-slug>` with today's date. First run `STORE list --project <project>`. If this task is already logged, reuse its id, because the id is what keeps a re-run from creating a duplicate.
- `project`: the repository directory name as a lowercase slug. `repo`: the remote URL with any `user:password@` or token removed, or null. `branch`: the current branch, or null.
- `layers`: business_logic (rules of the domain), code (how something is written), architecture (how parts fit together), stack (a library, framework or tool).
- `risk`: high for auth, payments, migrations, infrastructure or data deletion; medium if a bug would reach users; otherwise low.
- `how_it_works`: 2 to 4 sentences on the mechanism, not the diff. Test it this way: would someone who wasn't here understand how the feature works?
- `surprised_me`: the non-obvious part. `would_bite_again`: the concrete trap next time.

**decisions** (0 to 4): only choices where a real alternative existed, including ones you made silently. `rejected` names alternatives that were considered or were the obvious default. `kind` is one of:
- `workaround`: a hack to revisit
- `deferred`: left for later; name the ticket if there is one
- `product`, `architecture`, `security` or `process`

**questions** (1 to 3), one per main request:
- `asked`: the request, paraphrased.
- `should_have_asked`: the most useful line in the entry. Name the specific question that would have saved real rework or added real understanding in this session. Never generic advice like "ask for tests".
- `rating` (how the developer drove the session, not how hard the task was):
  - 5: clear goal, gave context, checked the result, asked why at least once
  - 4: clear goal and context, but accepted the result without checking or asking why
  - 3: clear goal, but missing context made the agent guess or redo work
  - 2: a vague request that led to several wrong attempts
  - 1: the request and the result didn't match, and nobody noticed
- `feedback`: what went well and one thing to do differently. Honest, encouraging, specific.

**quiz** (3 to 5): mix the types `predict` (what happens if...), `why`, `where` (which file or function decides...) and `trap` (what breaks if...). Each question must need knowledge of this project to answer. Each answer is 1 to 3 sentences. `file` is a real path from this session that proves the answer; check it exists.

**code** (optional): the one before/after snippet that best shows the change, under 10 lines each. Only include it if it helps.

**Style:** write in the developer's voice ("I", "my project") everywhere, including `feedback` ("I pointed at…", never "You pointed at…"). Use short sentences and plain words.

**Facts:** state only what this session showed: code you read or ran, output you saw, docs you checked. A claim about how a tool or framework behaves that nobody verified ("there is no bare /log") becomes a wrong lesson that gets quizzed later. Leave it out, or say it's unverified. Use real file, function, table and rule names. No filler such as "This session focused on…". Don't restate the diff line by line.

**Secrets:** never include API keys, tokens, passwords, `.env` values, connection strings or customer data. Describe them instead ("the Stripe secret from the environment").

Before saving, check the draft against these points:
- A stranger would understand the mechanism.
- At least one decision names a real rejected alternative.
- "Should have asked" is specific to this session.
- Every quiz file is real.
- Nothing in it could have been written without seeing this session.

## 4. Write the draft

Run `STORE home`. It prints `tmp: <dir>` and creates that folder. Write the entry with the Write tool to `<dir>/<task-id>.json`.

## 5. Save

Run `STORE save "<dir>/<task-id>.json"`.

- **It succeeds.** `store.py` removes the draft and prints the saved paths.
- **It prints errors.** Each one names the exact field (for example `quiz[2].file: required field is missing`). Fix only those fields, rewrite the file and run save once more. For a secret error, remove or describe the value; never repeat it.
- **It fails again.** Show the errors and the draft path, then stop.

## 6. Sync to Notion

If this session has Notion MCP tools (a tool name ending in `notion-create-pages`), read `${CLAUDE_SKILL_DIR}/notion.md` and follow it. That also sends older entries that never reached Notion, so run it even when save printed `unchanged`. Without Notion tools, skip this step and don't mention Notion.

## 7. Reply

Reply in one or two lines, based on the save output. Say what was logged and give the Markdown path, then the Notion page from the plan's `links` if step 6 ran. For example:

`Logged LOY-214: 2 decisions, 1 question, 4 quiz. ~/.learning-log/entries/loyalty-api/LOY-214.md`
`Notion: https://www.notion.so/…`

If save printed `unchanged`, say the session was already logged and nothing new was added.
