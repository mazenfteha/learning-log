---
name: learning-log
description: Use when the user runs /learning-log or asks to log, capture, or save what they learned in this coding session. Writes linked Tasks, Decisions and Questions entries plus a self-check quiz to Notion, so the developer learns from AI-written code by reading, not writing.
---

# Learning Log

The developer builds with an AI coding agent and ships fast, but the learning stays in the session. This skill turns the current session into a short, linked learning log in Notion that the developer only has to read.

The developer writes nothing. You write everything, from the session and the code.

## Step 1: Gather the session

Use what is already in this conversation: what the user asked for, what you did, what went wrong, what you decided, and what you explained.

Then check what actually changed in the code:

- `git status` and `git diff` for uncommitted changes
- `git log --oneline -10` and `git show <sha>` for commits made during this session

If the project is not a git repository, rely on the conversation and the files you edited.

## Step 2: Decide if it is worth logging

Log the session only if there is something worth taking away: a business rule, a non-obvious bug, a design decision, a new library or framework concept, or a pattern in this codebase.

If the session was trivial (renames, formatting, typo fixes, copy changes, dependency bumps with no surprises), tell the user in one line that there was nothing worth logging, and stop.

## Step 3: Find or set up the Learning Log in Notion

Use the Notion MCP tools that are available (search, fetch, create database, create pages, update page).

1. Look for a config file at `~/.claude/learning-log.json`. If it exists, it holds the IDs of the three databases. Use them.
2. If it does not exist, search Notion for a page titled "Learning Log".
   - If found, fetch it and find the three databases inside it.
   - If not found, create a page titled "Learning Log" and create the three databases inside it, with the schemas below.
3. Save the database IDs to `~/.claude/learning-log.json` so later runs skip this step.

If creating a relation property fails, create the databases without relations and link entries by putting a Notion page mention in a text property instead. Tell the user in one line.

### Tasks database (the hub, one entry per session)

| Property | Type | Content |
| --- | --- | --- |
| Name | Title | The task in plain words, e.g. "Add refund handling to loyalty points" |
| Date | Date | Today |
| Project | Select | The repository or project name |
| Stack | Multi-select | Languages and frameworks touched, e.g. Laravel, React, PostgreSQL |
| Layer | Multi-select | Any of: Business logic, Code, Architecture, Stack |
| How it works | Text | 2 to 4 sentences on how the thing built or fixed actually works |
| What surprised me | Text | 1 to 2 sentences on the non-obvious part |
| What could bite again | Text | 1 to 2 sentences on the trap to watch for next time |
| Reviewed | Checkbox | Leave unchecked. The developer ticks it after reading |
| Decisions | Relation | To the Decisions database |
| Questions | Relation | To the Questions database |

### Decisions database

| Property | Type | Content |
| --- | --- | --- |
| Decision | Title | Short, e.g. "Queue refund emails instead of sending inline" |
| Chosen approach | Text | What was done |
| Rejected | Text | The alternatives that were considered and not used |
| Why | Text | The reason, in 1 to 2 sentences |
| Files | Text | The main file paths involved |
| Task | Relation | Back to the Tasks entry |

### Questions database

| Property | Type | Content |
| --- | --- | --- |
| What I asked | Title | The developer's main request or question in this session, paraphrased |
| What I should have asked | Text | A better or additional question that would have led to a better result or more understanding |
| Approach rating | Select | 1 to 5, using the rubric below |
| Feedback | Text | 1 to 2 sentences: what went well and one thing to do differently |
| Task | Relation | Back to the Tasks entry |

## Step 4: Write the entries

Create, in this order:

1. One Tasks entry for the session.
2. One to four Decisions entries, only for real decisions where an alternative existed. Include decisions you made silently while coding, not only those discussed with the user. Skip this if there were no real decisions.
3. One to three Questions entries for the developer's main requests.
4. Link the Decisions and Questions entries to the Tasks entry.

Write in the developer's voice ("I", "my project"), as if they wrote it themselves.

### Approach rating rubric

Rate how the developer drove the session, not how hard the task was. Be honest and encouraging, never harsh.

- **5:** clear goal, gave useful context, checked the result, asked why at least once
- **4:** clear goal and context, accepted the result without checking or asking why
- **3:** goal was clear but context was missing, so the agent had to guess or redo work
- **2:** vague request that led to several wrong attempts
- **1:** the request and the result did not match, and nobody noticed

## Step 5: Add the quiz to the Tasks page

In the body of the Tasks entry, add a heading "Quiz" with 3 to 5 questions about this session. Write each question as a toggle block: the question is the toggle's title, and the answer hidden inside it.

The developer self-tests by reading the question, thinking, then opening the toggle. No typing needed.

Make the questions about this project, not general trivia:

- Predict: "A Gold user refunds an order that earned 200 points. What happens to the points?"
- Why: "Why are refund emails queued instead of sent inline?"
- Where: "Which file decides whether a coupon is expired?"
- Trap: "What breaks if two refunds for the same order arrive at the same time?"

Each answer is 1 to 3 sentences and ends with the file path that proves it.

Below the quiz, add a short "Code" section with the most important before and after snippet from the diff, if one helps. Keep each snippet under 10 lines.

## Step 6: Reply in chat

Reply in one or two lines: what was logged (for example "Logged: 1 task, 2 decisions, 2 questions, 4 quiz questions") and the link to the Tasks entry.

## Writing rules

- Plain words. Short sentences. No filler like "This session focused on...".
- Specific to this project: real names of functions, files, tables, and business rules.
- Explain the idea behind the code, not just what changed.
- Never copy secrets, API keys, tokens, passwords, customer data or `.env` values into Notion. Summarize instead.

## If Notion is not connected

If no Notion MCP tools are available, write the same content as one Markdown file at `~/learning-log/YYYY-MM-DD-<short-task-slug>.md`. Use sections: Task, How it works, What surprised me, What could bite again, Decisions, Questions, Quiz (each answer under a collapsed `<details>` block), and Code.

Then tell the user in one line that the log was saved locally, and that connecting the Notion MCP server will send future logs to Notion.
