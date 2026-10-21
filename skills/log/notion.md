# Sync to Notion

Notion is a view of the local entries; the JSON files stay the source of truth. `store.py` decides every Notion call and its exact arguments. Your job is to run those calls and report back what Notion returned. Don't write Notion payloads yourself, because the script already formats properties, dates, relations and page content the way the Notion tools expect.

`STORE` and `<dir>` (the tmp folder) mean the same as in SKILL.md. A planned tool name such as `notion-create-pages` means the Notion MCP tool in this session whose name ends with it, for example `mcp__claude_ai_Notion__notion-create-pages`.

## Rounds

Repeat until the plan says `done`, at most 8 rounds. First-run setup takes about six rounds; a normal `/log` takes one or two.

1. Run `STORE notion-plan`. It prints JSON with `status`, `actions` and `links`.
2. If `status` is `done`, stop. `links` maps each task id to its Notion page.
3. For each action, make its `calls` in order. Pass `arguments` exactly as given: don't reformat, translate or add anything. If a result is an `async_task`, poll `notion-get-async-task` with its id until it is `succeeded` (then use the result inside it) or `failed`.
4. From each action's results, collect what its `record` list asks for:
   - `url`: the URL of the page, database or view that was created. For an update, use the action's own `url`.
   - `data_source_id`: the `collection://…` URL in the `<data-source>` tag of a created database.
   - `urls`: the URLs of the created pages, in the order they were sent.
5. Write everything to `<dir>/notion-results.json` as `{"<action ref>": {...}}`, for example `{"task:LOY-214": {"url": "https://www.notion.so/…"}}`. Then run `STORE notion-record "<dir>/notion-results.json"`.

## Before the first setup call

The `setup:page` action is first-run setup. Before creating anything, search Notion for `Learning Log`. If a page with that title contains Tasks, Decisions and Questions databases (fetch it to check), this machine lost its sync state, and you must reuse that page instead of creating a second one:

1. **Record the workspace without creating anything:**
   - `setup:page` with the page URL.
   - `setup:db:<tasks|decisions|questions>` with each database's URL and the `collection://` URL from its `<data-source>` tag.
   - `setup:view:review_due` and `setup:view:tech_debt` with the "Review due" and "Tech debt" views, if they exist.
2. **Rebuild the entry map**, so nothing is created twice:
   - Query each database's default view with `notion-query-data-sources`, using `mode: "view"`.
   - For each Tasks row whose Task ID matches a local entry, record `task:<id>` with the row URL.
   - Record that task's decisions as `decisions:<id>` with `{"existing": {"<Decision title>": "<row url>"}}`, using the rows whose Task relation points to that task page. Do the same for questions, keyed by "What I asked".
3. **Continue with the normal rounds.** Whatever is still missing is planned then.

## If something fails

- Stop syncing at the first failed call.
- Record what already succeeded, so the next run doesn't create it again.
- Add one line to the reply: `Notion sync stopped: <short reason>. Saved locally; the next /log retries.`
- Never retry with arguments you changed yourself.
