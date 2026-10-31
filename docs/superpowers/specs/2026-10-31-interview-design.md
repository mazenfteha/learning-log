# `/learning-log:interview` design

Date: 2026-10-31. Status: approved, implemented in 0.2.0.

## Why

A developer ships a ticket with an AI agent and barely follows what got built. Then a senior lead, a PM or a customer asks about it: "why a queue?", "what happens to users who already signed up?" The developer doesn't know. The only way to find out is to go back to the agent, often in front of the person who asked, and that's embarrassing.

`/learning-log:interview` puts the developer in the hot seat first. Right after a session, it asks the questions those people would plausibly ask about that exact work. The answers stay hidden. The developer answers, gets reviewed, and learns the real answer and a line they could say out loud. Everything is saved with the session's lesson and shown in Notion.

**Success:** after an interview, the developer can answer a teammate's question about this session without opening the agent again.

## Goals

- Questions come from what actually happened in this session (its decisions, business rules, trade-offs and edge cases), asked the way a senior lead, a PM or a customer would ask them.
- The developer can answer properly, give a rough answer and ask for review, or say "I don't know". They always get the real answer.
- The results are saved locally with the session's entry and synced to Notion like the rest of the entry.
- It works on its own. If the session isn't logged yet, the interview logs it first.

## Non-goals

- Resuming an interview in a later session. Interviews happen in the same chat as the work (see "Same chat only").
- Spaced repetition, scores over time, levels or streaks. The dropped `/review` loop stays dropped.
- Multiple-choice questions. The point is rehearsing a real spoken answer.
- Interviews about the whole project or about older sessions.

## Anti-goals (a failure even if it works)

- **Generic questions.** "What is a REST API?" or anything answerable without this session.
- **Showing answers early.** Answers must never appear, in chat or in Notion, before the developer has answered or given up.
- **Making `/learning-log:log` interactive.** The log stays read-only. Only `/learning-log:interview` asks the developer to type.
- **A harsh or condescending tone.** The reviewer is a senior who wants you to do well in the meeting.
- **Inventing facts.** A "real answer" the session didn't show is worse than no answer.

## Constraint: user-friendly and lightweight

This applies to the whole project, not only this feature. Where a choice comes up, pick the lighter, friendlier option.

- **Short chat.** A question is one line plus a counter, for example `(2/5)`. A review fits on a phone screen: the verdict and feedback in 2 to 3 sentences, then "Answer", "Say it" and the file. No headers, no walls of text.
- **No new setup.** No new dependencies, settings or commands to learn beyond `/learning-log:interview`. The Interview database creates itself on the next sync.
- **No permission-prompt spam.** The skill's allow-list covers every command it runs, so an interview never stops to ask for tool approval.
- **Easy to leave.** "stop" works at any moment. Answering is never required.
- **Small code.** The skill reads the log skill's steps rather than repeating them. `store.py` reuses the existing validate, merge, render and Notion helpers. Add only what this feature needs.

## Core principle change (approved in conversation)

Principle 1 "Read, no write" gets one explicit exception. `/learning-log:interview` is opt-in practice where the developer types answers. Everything else stays read-only. Update the principle's wording in `.claude/CLAUDE.md` and the README.

## How it works

### Invocation

The skill is `skills/interview/SKILL.md`, invoked as `/learning-log:interview`. It has `disable-model-invocation: true`, like `/learning-log:log`. Its tool allow-list matches `/learning-log:log`'s: git read commands, the three Python launchers running `store.py`, and the Notion MCP tools. It also needs Read, Grep and Glob, to check files and help the developer locate code.

### Flow

1. **Gather the session**, as `/learning-log:log` does: the conversation first, then git for what changed. The same rules apply: never rebuild an earlier session from git history, and never open secrets.
2. **Skip trivial sessions.** Use the same test as `/learning-log:log`. Reply `Nothing worth interviewing on: <reason>.` and stop. With no work in the chat, reply `Nothing worth interviewing on: no work in this session.`
3. **Log the session first, every time (B1).** Follow `skills/log/SKILL.md` steps 3 to 5 exactly. Read that file instead of copying its rules into the interview skill, so the two never drift apart. That covers working out the task id and reusing an existing entry's id from `STORE list --project <project>`. The rule is the same whether or not an entry exists, because `save` upserts:
   - **No entry yet:** this creates one.
   - **Logged earlier and the work went on:** the new work is added.
   - **Nothing new:** it prints `unchanged`.
   Running it every time also keeps the lesson in step with the questions, which come from the same session. Reply in one line only when something was saved, for example `Logged LOY-214 first.` or `Updated LOY-214.`
4. **Choose 5 questions.** Keep the list in your working context. Show only the current question, never the list or any answer. The real answer, `say_it` and the file are written at review time (step 7). They come from the session, not from the developer's reply. Mix:
   - **Asker:** mostly `senior`, at least one `pm`, and a `customer` only when the work touches something users see.
   - **Topic:** roughly half `technical` (design, trade-offs, failure modes) and half `product` (behaviour, edge cases, impact on users or the business).
   - Prefer the decisions, rejected alternatives, risks and "would bite again" traps from the session. Skip any question already stored in this entry's `interview` (same normalised question text).
5. **Ask one question at a time.** Say who is asking, for example `**PM asks:** What does a customer see if the payment fails halfway? (1/5)`, then end the turn.
6. **The developer replies** in plain chat with one of these:
   - **An answer.** It can come after digging in the editor.
   - **A rough answer plus "review this".** Treated the same as an answer.
   - **"I don't know" or "tell me".** Verdict `missed`, `my_answer` null.
   - **A "where is…?" question.** Point to the file or function without giving the answer, then wait for their answer to the original question.
   - **"stop", "done" or "later".** Every question not yet answered is saved as `skipped` (see step 8), then go to step 9.
7. **Review**, in the asker's voice addressed to "you". Give the verdict (`solid`, `partial` or `missed`), then what was right and what was missing or wrong (`feedback`). Then give the real answer with its file, and the `say_it` line, which is 1 to 2 sentences in the developer's own voice, ready to say in a meeting.
8. **Save each item as soon as it's done** with `STORE interview-add <task-id> "<dir>/interview-<n>.json"`. The file holds a JSON array with one or more items. Each file is written after its question has been answered, so the answer in it is already public, and the Write tool display gives nothing away. On stop, write the remaining questions with their answers and save them in one call as `skipped`. A question that was chosen but never shown counts as skipped too, because the developer can still read it in Notion later.

**No retries.** A saved item is final. Once the real answer has been shown, answering it again would be memorising, and that's the dropped `/review` loop. A second `/learning-log:interview` in the same chat asks new questions.

**Compaction.** If the context is compacted mid-interview and the question list is lost, end the interview cleanly. Report what's already saved. Don't invent the questions that were lost.
9. **Finish.** Sync to Notion the same way `/learning-log:log` step 6 does: read `skills/log/notion.md` and follow it, only when Notion tools exist. Reply with one or two lines, for example `Interview on LOY-214: 3 solid, 1 partial, 1 missed. ~/.learning-log/entries/loyalty-api/LOY-214.md`, plus the Notion link.

If the developer just leaves the chat, the answered items are already saved and only the unasked questions are lost. That's acceptable. The next `/learning-log:log` or `/learning-log:interview` that syncs to Notion also sends any items that never reached it, because the sync already covers pending items.

### Same chat only

The interview has to run in the chat where the work happened. A later session can't see the conversation, and the plugin already refuses to rebuild sessions from git. While a question is open, the developer can leave to read code in their editor and come back to the same chat.

## Data contract changes

`schema/entry.schema.json`, kept at `schema_version` 1 because the new field is optional and old entries stay valid:

- New optional top-level `interview`: an array of `interview_item`. There's no max on a stored entry. Each `interview-add` call takes 1 to 5 items.
- `interview_item` (no additional properties):
  - `question` (text, max 300), in the asker's voice
  - `asker`: `senior` | `pm` | `customer`
  - `topic`: `technical` | `product`
  - `verdict`: `solid` | `partial` | `missed` | `skipped`
  - `my_answer`: the developer's reply as typed (max 2000), or null when they didn't know or skipped
  - `feedback`: text (max 600), or null only when the verdict is `skipped`
  - `answer`: the real answer, 1 to 3 sentences (max 500)
  - `say_it`: 1 to 2 sentences in the developer's voice (max 300)
  - `file`: the path that proves the answer
  - `answered_at`: ISO 8601 date-time, set by `store.py`

`examples/entry.example.json` gets an `interview` array with three items: one `solid`, one `missed` and one `skipped`. `examples/entry.example.md` is re-rendered to match.

## `store.py` changes

- **Validation:** `_check_interview_item`, mirroring the schema. `feedback` must be null exactly when the verdict is `skipped`. `my_answer` must be null when the verdict is `skipped`. `scan_secrets` covers the interview items too. The developer's `my_answer` is free text and the likeliest place for a pasted key. On a secret error, the skill replaces the value with a description, as `/learning-log:log` does.
- **New command:** `interview-add <task-id> <file>`. It loads the existing entry (and fails clearly if there isn't one), validates the items, and sets `answered_at`. It appends the items, skipping any whose normalised `question` already exists (`_merge_key`), and an existing item is never overwritten. It bumps `updated_at`, re-renders the Markdown, removes the draft file and prints `added N, skipped M duplicates` with the paths.
- **`save` merge:** a full `save` keeps the stored `interview` array untouched. The skill's lesson draft never contains one, and if an incoming entry does, it's merged with the same rule as `interview-add`.
- **Markdown:** a new `## Interview` section after Quiz. Each item shows the asker and question, then the verdict, then my answer, the feedback, the real answer with its file, and "Say it". Skipped items show only the question, the answer, the file and "Say it".
- **Notion:**
  - Add `interview` to the kinds that get a database and pending-item sync. It's the 4th database, titled "Interview", with a `Task` relation `DUAL 'Interview'`.
  - Columns: Question (title), Asked by (select), Topic (select), Verdict (select), My answer, Feedback, Answer, Say it, File.
  - The setup check moves from 3 to 4 databases, so an existing workspace gets the Interview database on its next sync with no other change.
  - `MERGE_KEYS["interview"] = "question"`.
  - The task page body doesn't change. Interview rows live only in the Interview database and appear on the task through the relation, so adding items never rewrites the task page.
- **`skills/log/notion.md` recovery steps:** accept a page with or without the Interview database, record `setup:db:interview` when it's present, and rebuild interview rows keyed by Question.

## Tests

Tests use the standard library `unittest` with a temporary `LEARNING_LOG_HOME`, as the existing tests do. They cover:

- **Validation:** valid items, each enum, the null rules for `skipped` and `missed`, and the length limits.
- **`interview-add`:** adds items, skips duplicates, fails when the entry is missing, rejects secrets, removes the draft, re-renders the Markdown.
- **`save`:** keeps an existing interview.
- **Markdown:** renders the section, both full and skipped items.
- **`notion-plan`:**
  - creates the Interview database on a fresh workspace
  - adds only that database on a workspace that already has three
  - plans pending interview rows
  - records the returned URLs so the next plan is `done`
- **Example entry:** still validates.

After the skill exists, run it once on a real session and show the output, as the working agreement requires.

## Docs and release

- Update the README with what `/learning-log:interview` is, when to use it, and that it's the one command where you type.
- Update `.claude/CLAUDE.md`: the principle 1 exception, the repository layout, the entry contract, the `store.py` commands, and the four Notion databases.
- Bump `version` to 0.2.0 and run `claude plugin validate --strict .`

## Calls I made (not discussed, check these)

- Five questions per interview. The asker mix leans to `senior`, and `customer` only appears when the work touches something users see.
- The `say_it` line, saving after every answer, and the "where is…?" help that doesn't give the answer away.
- The voice: the question and feedback come from the asker ("you"), and `say_it` is in the developer's voice ("I"). The "I" rule in `/learning-log:log` doesn't apply to those fields.
- Skipped and unshown questions are saved with their answers, so Notion becomes a study sheet. The answers only become visible after the developer has stopped.
- No "To practice" Notion view for now. It could be added later as a filter on verdict ≠ solid.
- A separate `interview-add` command, so the interview items are saved apart from the lesson draft.
- Every interview runs the log's save first, not only when there's no entry. That keeps the lesson up to date and reuses `/learning-log:log`'s id matching. A small risk stays: with no ticket id, a different slug could create a second entry. `/learning-log:log` already has the same risk.
- Answers are written at review time, not drafted before the question is shown. Nothing hidden needs to survive between turns, and nothing leaks through a file or tool display.
- No retrying skipped or missed questions.

## Left to the builder

- Exact wording of the skill's steps and the review rubric text, within the rules above.
- Notion column colours, the exact DDL formatting and the Markdown layout details.
- Internal function names and how `interview-add` shares code with `save`.
