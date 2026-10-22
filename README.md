# Learning Log

**Keep learning from the code your AI agent writes.**

Learning Log is a Claude Code plugin. At the end of a coding session worth remembering, you type `/log`. Claude writes a short lesson about *that* session, using your real files, functions and business rules. You only read it.

Coding agents let you ship fast, but the understanding stays in the chat. A few weeks later it's hard to explain your own project: why it was built that way, how a rule works, or what was tried and rejected. Learning Log keeps that knowledge in a lesson you can re-read.

## What a lesson looks like

Each lesson answers the questions you'd forget first:

- **How it works:** the mechanism in 2–4 sentences, not a diff summary
- **What surprised me** and **what could bite again**
- **Decisions:** what was chosen, what was rejected, and why. This includes choices the agent made silently.
- **Questions:** what you asked, the better question you *should* have asked, and honest feedback on how you drove the session
- **Quiz:** 3–5 questions about your project, with each answer pointing to the file that proves it

A short excerpt:

> **Should have asked:** What should happen to points on a partial refund, and when the member has already spent them?
>
> **Quiz (trap):** A member refunds the order that got them to Gold. Do they drop back to Silver?
> <details><summary>Answer</summary>No. <code>TierCalculator</code> reads lifetime earned points, which a refund doesn't change. Proof: <code>app/Tiers/TierCalculator.php</code></details>

Full example: [examples/entry.example.md](examples/entry.example.md).

Trivial sessions (renames, typos, formatting, routine dependency bumps) produce nothing. An empty log is better than a padded one.

## Install

**Requirements:** [Claude Code](https://code.claude.com), git, and Python 3.9 or later. Python only needs the standard library, so there's nothing to `pip install`. On Windows, the `py` launcher is enough.

```bash
claude plugin marketplace add mazenfteha/learning-log
claude plugin install learning-log@learning-log
```

Then start a new Claude Code session, or reload the window in VS Code or the desktop app, so the plugin loads.

## Use it

1. Work with Claude Code as usual.
2. When the session taught you something, type **`/learning-log:log`** (typing `/learning` in the slash menu finds it). Newer Claude Code versions also accept the short **`/log`**, as long as no other command uses that name.
3. Claude replies with one line naming what was logged and the path to the lesson. That's all.

Running `/log` again on the same task updates the lesson. It never duplicates decisions, questions or quiz items.

## Where lessons are saved

Everything is saved on your machine first:

```text
~/.learning-log/entries/<project>/<task-id>.json   # the source of truth
~/.learning-log/entries/<project>/<task-id>.md     # readable copy
```

Set the `LEARNING_LOG_HOME` environment variable to use a different folder.

## Notion (optional)

To read your lessons in Notion, turn on the Notion connector in claude.ai: **Settings → Connectors → Notion**. That's the whole setup: no tokens, no IDs, no templates.

The next `/log` creates a private **Learning Log** page in your Notion containing:

- **Tasks:** one page per lesson. The quiz is on the page as toggles; click one to reveal the answer.
- **Decisions**, with a **Tech debt** view that lists workarounds and deferred decisions.
- **Questions:** what you asked, and what you should have asked.
- A **Review due** view showing lessons worth re-reading. Each lesson is flagged 3 days after it's logged.

Later runs update that page and also send any older lessons that never reached Notion. Sync is one way: your local JSON is the source of truth, so edits you make in Notion can be overwritten the next time that lesson changes. You can move the Learning Log page anywhere in your workspace without breaking the sync.

## Privacy

- Lessons are written from the current conversation and the git diff. Nothing is sent anywhere except Claude, which you're already using, and your own Notion if you connect it.
- Every lesson is checked for secrets before it's saved. Anything that looks like an API key, token, private key or a password in a URL is rejected, and the skill is told never to copy `.env` values or customer data.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `/log` doesn't appear | Type the full name, `/learning-log:log`. Older Claude Code versions don't link the short `/log` to plugins (`claude update` fixes that). Also start a new session or reload the window after installing, because plugins load when a session starts. |
| Changes to the plugin don't show up | Run `claude plugin marketplace update learning-log`, then `claude plugin update learning-log@learning-log`, then start a new session. |
| "Python was not found" on Windows | Install Python 3.9+ from python.org. The skill tries `python3`, `python` and `py -3` in that order. |
| "Nothing worth logging" | The session was trivial, or `/log` was run in a new, empty conversation. Run it at the end of the session where the work happened. |
| Nothing shows up in Notion | Check that the Notion connector is on in claude.ai. Lessons are always saved locally; the next `/log` retries the sync. |

## How it works

```text
your session (conversation + git diff)
        │
        ▼
   /log skill ──► entry JSON ──► scripts/store.py
   (judgment:                     ├─ validates against schema/entry.schema.json
    what mattered,                ├─ rejects secrets, de-duplicates, saves JSON + Markdown
    what to ask)                  └─ plans the exact Notion calls (if Notion is connected)
```

- **The skill does the judgment:** what happened, what matters, and what to ask.
- **`scripts/store.py` does everything that must be exact:** validation, saving, de-duplication, rendering and the Notion payloads. It's plain Python with only the standard library.

## Develop locally

```bash
git clone https://github.com/mazenfteha/learning-log
cd learning-log
claude --plugin-dir .                     # load the plugin for one session
python3 -m unittest discover -s tests     # run the tests (py -3 on Windows)
```

If you edit the plugin during a session, run `/reload-plugins`. Before a release, bump `version` in `.claude-plugin/plugin.json` and run `claude plugin validate --strict .`.

`store.py` also works on its own:

```bash
python3 scripts/store.py list               # every lesson: date, project, title
python3 scripts/store.py show <task-id>     # print one lesson
python3 scripts/store.py validate <file>    # check an entry against the schema
```

## Credits

The Tasks / Decisions / Questions structure, decision kinds, risk levels and the review-due idea are inspired by [swastij/claude-log-skill](https://github.com/swastij/claude-log-skill) (MIT).

## License

MIT. See [LICENSE](LICENSE).
