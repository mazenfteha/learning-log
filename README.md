# Learning Log

A Claude Code plugin that turns AI coding sessions into short, readable lessons, so you keep learning from the code your agent writes.

At the end of a session worth remembering, type `/log`. Claude writes a lesson about that session: how the feature works, what surprised you, the decisions made (and what was rejected), the question you should have asked, and a short quiz. You only read it. Trivial sessions are skipped.

**Status: Phase 2.** Entries are saved on your machine as JSON plus Markdown, and synced to Notion when it's connected. A `/review` quiz comes later.

## Try it locally

You need Claude Code and Python 3.9+. There's nothing to install and no setup.

```bash
git clone <this repo> learning-log
cd your-project
claude --plugin-dir /path/to/learning-log
```

Do some real work, then type `/log` (or `/learning-log:log`). The reply gives the path to the saved lesson.

If you edit the plugin during a session, run `/reload-plugins`.

## Where entries go

```
~/.learning-log/entries/<project>/<task-id>.json   # source of truth
~/.learning-log/entries/<project>/<task-id>.md     # readable copy
```

Set `LEARNING_LOG_HOME` to use another folder. Running `/log` again on the same task updates the entry and never duplicates decisions, questions or quiz items. Each new entry is due for review 3 days after it's created.

See [examples/entry.example.md](examples/entry.example.md) for what a lesson looks like, and [schema/entry.schema.json](schema/entry.schema.json) for the entry contract.

## Notion (optional)

Turn on the Notion connector in claude.ai (**Settings → Connectors → Notion**). That's the whole setup.

The next `/log` creates a private **Learning Log** page in your Notion containing:
- **Tasks**, one page per lesson. The quiz is on the page as toggles: click one to reveal the answer.
- **Decisions**, with a **Tech debt** view that lists workarounds and deferred decisions.
- **Questions**: what you asked, and what you should have asked.
- A **Review due** view on Tasks.

Every later `/log` updates that page and also sends any older entries that never reached Notion.

Sync is one way. The local JSON is the source of truth, and edits you make in Notion can be overwritten the next time that entry changes. Sync state lives in `~/.learning-log/notion.json`.

## store.py

The skill handles the judgment; `scripts/store.py` handles everything that must be exact. It uses only the standard library.

```bash
python3 scripts/store.py save <entry.json>      # validate, upsert, render .md
python3 scripts/store.py validate <entry.json>  # validate only; exit 1 with errors
python3 scripts/store.py list [--project P]
python3 scripts/store.py due [--project P]      # due for review today or earlier
python3 scripts/store.py show <task-id>         # print the Markdown
python3 scripts/store.py notion-plan            # next Notion calls for the skill, as JSON
python3 scripts/store.py notion-record <file>   # record what those calls returned
```

On Windows, use `py -3` in place of `python3`.

Entries that look like they contain a secret (API keys, tokens, private keys, passwords in URLs) are rejected.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Credits

The Tasks / Decisions / Questions structure, decision kinds, risk levels and the review-due idea are inspired by [swastij/claude-log-skill](https://github.com/swastij/claude-log-skill) (MIT).
