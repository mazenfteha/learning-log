# Learning Log

A Claude Code plugin that turns AI coding sessions into short, readable lessons, so developers keep learning from the code their AI agent writes.

## The problem

Developers ship more than ever with AI coding agents, but the learning stays inside the session. After a few weeks they can't explain their own project: why it was built this way, how a business rule works, or what was rejected and why.

## The product in one line

At the end of a session worth remembering, the developer types `/log`. The plugin writes a lesson about that session. The developer only reads it, and is quizzed on it later.

## Core principles

These decide every trade-off. If a change conflicts with one of them, stop and ask.

1. **Read, no write.** The developer never has to type a lesson, an answer or a score. The most they do is press a key to reveal an answer or tick a checkbox.
2. **Zero setup.** Installing the plugin and connecting Notion is the whole setup. No tokens to copy, no IDs to paste, no templates to duplicate.
3. **Specific to the developer's project.** Lessons use real file names, functions, tables and business rules from the session. Never generic trivia.
4. **Skip what isn't worth it.** Trivial sessions (renames, formatting, typos, copy changes, routine dependency bumps) produce nothing. An empty log is better than a padded one.
5. **Local first.** Every entry is saved as a JSON file on the developer's machine first. Notion and anything else are views of that data, never the source of truth.
6. **Never leak secrets.** No API keys, tokens, passwords, `.env` values or customer data in any entry, ever.
7. **Any stack.** Nothing may depend on a specific language or framework. The inputs are the session transcript and the git diff, which every project has.

## Architecture

```
Coding session (transcript + git diff)
        │
        ▼
  /log skill  ──────►  entry JSON  ──────►  store.py save
  (the brain:                               │
   extracts the                             ├─► ~/.learning-log/entries/…json  (source of truth)
   lesson)                                  ├─► ~/.learning-log/entries/…md    (readable copy)
                                            └─► Notion (Phase 2, via Notion MCP)

  /review skill ──► store.py due ──► quiz in the terminal ──► store.py reviewed   (Phase 3)
```

- **The skill** does the judgment: what happened, what matters, what to ask. It writes one entry JSON.
- **`store.py`** does everything that must be exact: validation, saving, de-duplication, rendering Markdown, and review dates. Put logic in the script, not in prompts, whenever it can be deterministic.

## Repository layout

```
learning-log/
├── CLAUDE.md
├── README.md
├── LICENSE                       # MIT
├── .claude-plugin/
│   ├── plugin.json               # Phase 4
│   └── marketplace.json          # Phase 4
├── skills/
│   ├── log/SKILL.md              # Phase 1
│   └── review/SKILL.md           # Phase 3
├── scripts/
│   └── store.py                  # Phase 1
├── schema/
│   └── entry.schema.json         # Phase 1, the contract
├── examples/
│   ├── entry.example.json        # Phase 1
│   └── entry.example.md          # Phase 1, rendered output
├── tests/
│   └── test_store.py             # Phase 1
├── evals/                        # Phase 4
└── reference/                    # inputs we learned from; not shipped logic
```

## The entry contract

`schema/entry.schema.json` is the single source of truth for the entry shape. Everything else is built against it. Change it deliberately, update `examples/entry.example.json` in the same change, and keep validation in `store.py` in sync.

An entry has four parts:

**task** (required)
- `id`: the ticket ID if there is one (Jira, Linear, ClickUp, GitHub issue); otherwise `<project>-<YYYYMMDD>-<short-slug>`
- `title`: the task in plain words
- `project`, `repo`, `branch`
- `stack`: languages and frameworks touched
- `layers`: any of `business_logic`, `code`, `architecture`, `stack`
- `risk`: `low` | `medium` | `high` (high for auth, payments, migrations, infrastructure, data deletion)
- `how_it_works`: 2 to 4 sentences on the mechanism, not the diff
- `surprised_me`: the non-obvious part, 1 to 2 sentences
- `would_bite_again`: the trap to watch for next time, 1 to 2 sentences
- `created_at`, `updated_at`: ISO 8601

**decisions** (0 to 4)
- `title`, `chosen`, `rejected` (list of alternatives), `why`
- `kind`: `product` | `architecture` | `security` | `workaround` | `deferred` | `process`
- `reversible`: true or false
- `files`: main paths involved
- Include decisions the agent made silently while coding, not only ones discussed.

**questions** (1 to 3)
- `asked`: the developer's main request, paraphrased
- `should_have_asked`: a better question that would have saved rework or added understanding
- `rating`: 1 to 5, how well the developer drove the session (rubric in the skill)
- `feedback`: what went well and one thing to do differently, honest and encouraging

**quiz** (3 to 5)
- `type`: `predict` | `why` | `where` | `trap`
- `question`, `answer` (1 to 3 sentences), `file` (the path that proves the answer)

**review** (managed by `store.py`, never written by the skill)
- `due`, `interval_days`, `last_reviewed`, `times_reviewed`

Optional: `code` with one short `before`/`after` snippet (under 10 lines each).

## Storage

- Root: `~/.learning-log/` (override with the `LEARNING_LOG_HOME` environment variable).
- Entries: `~/.learning-log/entries/<project>/<task-id>.json` and a rendered `<task-id>.md` next to it.
- **Upsert by `task.id`.** Saving an entry with an existing id updates the task fields and adds new decisions, questions and quiz items, skipping any whose title or question text already exists. Re-running `/log` must never create duplicates.
- **Review schedule.** New entries are due 3 days after creation. Later intervals: 3, 7, 14, 30, 60 days.
- **Notion sync state:** `~/.learning-log/notion.json` holds the Notion page, database and view URLs, plus which entries and items were sent, with a hash of each task page. It is not part of the entry contract. Deleting it makes the next sync look for the existing "Learning Log" page and rebuild the map instead of duplicating.

## `store.py` commands

```
python3 scripts/store.py save <entry.json>      # validate, upsert, render .md, print the saved paths
python3 scripts/store.py validate <entry.json>  # validate only, exit non-zero with clear errors
python3 scripts/store.py list [--project P]     # one line per entry: date, project, title, due
python3 scripts/store.py due [--project P]      # entries due for review today or earlier
python3 scripts/store.py show <task-id>         # print the rendered Markdown
python3 scripts/store.py home                   # print the storage root and the tmp dir for drafts
python3 scripts/store.py notion-plan [task-id]  # next Notion MCP calls, with exact arguments, as JSON
python3 scripts/store.py notion-record <file>   # record the URLs those calls returned
```

Notion sync runs in rounds: `notion-plan` → the skill makes the listed calls verbatim → `notion-record`, until the plan says `done`. Each round only plans calls whose inputs are already recorded, so first-run setup, new pages and updates use the same loop.

`reviewed <task-id>` comes in Phase 3.

## Conventions

- **Python 3.9+, standard library only.** No pip installs, so the plugin works on any machine. Validation is hand-written in `store.py`, mirroring the schema.
- **Tests:** `unittest` from the standard library. Run with `python3 -m unittest discover -s tests`. Tests use a temporary `LEARNING_LOG_HOME`, never the real one.
- **Skill instructions:** plain, direct, numbered steps. Explain why when a rule is not obvious. Keep each skill focused; shared rules live here or in the schema.
- **Writing style of entries:** short sentences, plain words, no filler ("This session focused on…"), written in the developer's voice ("I", "my project").
- **Paths in skills:** the skill finds `store.py` relative to its own base directory (`../../scripts/store.py`). Before relying on any environment variable for the plugin root, check the current Claude Code plugin docs.
- **Commits:** small and focused, one logical change each, with a clear message.

## What a good entry looks like

- Someone who wasn't in the session understands how the feature works after reading it.
- At least one decision names a real rejected alternative.
- "Should have asked" is the most useful line in the entry, not a polite filler.
- Every quiz answer points to a real file.
- Nothing in it could have been written without seeing this specific session.

Anti-patterns: restating the diff line by line; generic advice ("write tests"); quiz questions answerable without knowing the project; padding a trivial session.

## Phases

1. **Local core (done).** Schema, example entry, `store.py` with tests, `/log` skill writing locally. Then tune lesson quality on real sessions.
2. **Notion (current).** First-run setup creates a "Learning Log" page with three linked databases (Tasks, Decisions, Questions) via the Notion MCP. Upsert by task id. Views for "Review due" and "Tech debt" (decisions of kind `workaround` or `deferred`). Local JSON stays the source of truth.
3. **Review.** `/review` skill: due questions one at a time, press Enter to reveal, `store.py reviewed` schedules the next date.
4. **Package.** Plugin manifest, marketplace file, README, evals (fires on real work, skips trivial sessions).
5. **Later.** Session-end nudge, Cursor and Codex support, the Debrief game on the same data.

Do not build ahead of the current phase. If something from a later phase seems needed, note it in the plan and ask.

## Working agreements for Claude

- Start each phase in plan mode and wait for approval before writing code.
- Build the contract first (schema and example), then the script, then the skill.
- After changes to `store.py`, run the tests. After changes to a skill, run it once on a real or example session and show the output.
- Ask before adding a dependency, changing the schema, or changing any core principle.
- When unsure how a Claude Code feature works (skills, plugins, hooks, MCP), check the current docs instead of guessing.

## Credits

The Tasks, Decisions and Questions structure, decision kinds, risk levels and the review-due idea are inspired by [swastij/claude-log-skill](https://github.com/swastij/claude-log-skill) (MIT). Credit it in the README.
