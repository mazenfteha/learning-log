---
name: interview
description: Grill the developer on the session they just finished with questions a senior lead, PM or customer would ask, review each answer, and save the results with the session's Learning Log entry. Use when the user runs /learning-log:interview.
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git show *) Bash(git rev-parse *) Bash(git remote *) Bash(python3 --version) Bash(python --version) Bash(py -3 --version) Bash(python3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) Bash(python "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) Bash(py -3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(git status *) PowerShell(git diff *) PowerShell(git log *) PowerShell(git show *) PowerShell(git rev-parse *) PowerShell(git remote *) PowerShell(python3 --version) PowerShell(python --version) PowerShell(py -3 --version) PowerShell(python3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(python "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) PowerShell(py -3 "${CLAUDE_SKILL_DIR}/../../scripts/store.py" *) mcp__claude_ai_Notion__notion-search mcp__claude_ai_Notion__notion-fetch mcp__claude_ai_Notion__notion-create-pages mcp__claude_ai_Notion__notion-update-page mcp__claude_ai_Notion__notion-create-database mcp__claude_ai_Notion__notion-create-view mcp__claude_ai_Notion__notion-query-data-sources mcp__claude_ai_Notion__notion-get-async-task Read Grep Glob Write
---

# Learning Log: /interview

Put the developer in the hot seat before a real person does. Ask what a senior lead, a PM or a customer would ask about the work in this session, one question at a time, and review each answer. This is the one Learning Log command where the developer types; keep everything short and easy to leave.

- `STORE` means `<python> "${CLAUDE_SKILL_DIR}/../../scripts/store.py"`, with this skill's own `${CLAUDE_SKILL_DIR}`. Use exactly this form, even while following the log skill's steps; it's the form this skill's allowed tools cover, so no permission prompt appears.
- `<python>` is found as in the log skill (step 3 there), and `<dir>` is the `tmp:` folder that `STORE home` prints.

## 1. Log the session first

Read `${CLAUDE_SKILL_DIR}/../log/SKILL.md` and do its steps 1 to 5, every time, even if this session was logged before: `save` upserts, so it creates the entry, adds work done since, or prints `unchanged`. Two changes:

- Where it says `Nothing worth logging: <reason>.`, reply with only `Nothing worth interviewing on: <reason>.`, nothing before or after it, and stop.
- Don't reply after saving. If save printed `new` or `updated`, say it in one line before the first question (`Logged LOY-214 first.`).

Remember the task id: every item is saved under it.

## 2. Choose 5 questions

Pick them from what happened in this session: decisions and their rejected alternatives, business rules, edge cases, risks, the "would bite again" trap. Each must need this session to answer. Never generic ("What is a webhook?").

- **Asker:** mostly `senior`, at least one `pm`, and a `customer` only when the work changes something users see.
- **Topic:** about half `technical` (design, trade-offs, failure modes), half `product` (behaviour, edge cases, impact on users or the business).
- Ask each the way that person would. A PM doesn't say "idempotent"; a customer talks about their account.
- Run `STORE show <task-id>` and skip any question already under `## Interview`.

Keep the list to yourself. Never show the list or any answer before the developer has replied.

## 3. Ask one question

`**PM asks:** What does a customer see if the payment fails halfway? (2/5)`

That one line is the whole message. End the turn and wait.

## 4. Read the reply

- **An answer**, or a rough answer with "review this": review it (step 5).
- **"I don't know"** or **"tell me"**: verdict `missed`, `my_answer` null.
- **"Where is …?"**: point to the file or function in one line, without giving the answer, and wait again.
- **"stop"**, **"done"**, **"later"**: go to step 7.

## 5. Review

Speak as the asker, to "you". Keep it short enough to read on a phone:

```
**Partial.** <what was right, what was missing or wrong: 2-3 sentences>
**Answer:** <the real answer, 1-3 sentences> (`<file>`)
**Say it:** "<1-2 sentences in the developer's voice, ready for the meeting>"
```

- Verdict: **Solid** (right and complete), **Partial** (right idea, missing a key part), **Missed** (wrong or no answer).
- Be honest and warm: a senior who wants them to do well in the meeting.
- Only facts this session showed. Check the file exists. If you're not sure of something, say so instead of guessing.

## 6. Save it, then ask the next one

Write a JSON list with one item to `<dir>/interview-<n>.json`, then run `STORE interview-add <task-id> "<dir>/interview-<n>.json"`.

```json
[{
  "question": "What does a customer see if the payment fails halfway?",
  "asker": "pm",
  "topic": "product",
  "verdict": "partial",
  "my_answer": "The developer's reply, as typed",
  "feedback": "What was right and missing, to you",
  "answer": "The real answer, 1-3 sentences.",
  "say_it": "1-2 sentences in the developer's voice.",
  "file": "app/Payments/Checkout.php"
}]
```

`asker`: senior, pm, customer. `topic`: technical, product. `verdict`: solid, partial, missed, skipped. `my_answer` is null when they didn't know. Limits: question 300 characters, my_answer 2000, feedback 600, answer 500, say_it 300.

- **Secrets:** never copy keys, tokens, passwords or customer data into an item. If `interview-add` reports a secret in `my_answer`, replace that part with a description ("the Stripe key") and save again.
- **Errors:** fix only the fields named and save once more.

Then ask the next question (step 3). After the fifth, go to step 7.

## 7. Finish

- If they stopped early, save every question not yet answered in one call, each with `"verdict": "skipped"`, `my_answer` and `feedback` null, and the answer, say_it and file filled in. They can read them later.
- No retries: once an answer is shown, that question is done. Running `/learning-log:interview` again asks new questions.
- If this conversation was compacted and you no longer have your question list, stop here: report what was saved and don't invent the rest.
- If this session has Notion MCP tools (a tool name ending in `notion-create-pages`), read `${CLAUDE_SKILL_DIR}/../log/notion.md` and follow it. Otherwise skip Notion and don't mention it.

Reply in one or two lines:

`Interview on LOY-214: 3 solid, 1 partial, 1 missed. ~/.learning-log/entries/loyalty-api/LOY-214.md`
`Notion: https://www.notion.so/…`
