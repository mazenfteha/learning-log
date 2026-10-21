import json
import unittest

from test_store import StoreTestCase, example  # also puts scripts/ on sys.path

import store  # noqa: E402

PAGE = "https://www.notion.so/Learning-Log-%032x"


def url(n):
    return PAGE % n


def ds(n):
    return "collection://%08x-0000-0000-0000-%012x" % (n, n)


class NotionTestCase(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.save(example())

    def refs(self, plan):
        return [action["ref"] for action in plan["actions"]]

    def set_up_workspace(self):
        store.notion_record({"setup:page": {"url": url(1)}})
        store.notion_record({"setup:db:tasks": {"url": url(2), "data_source_id": ds(2)}})
        store.notion_record({
            "setup:db:decisions": {"url": url(3), "data_source_id": ds(3)},
            "setup:db:questions": {"url": url(4), "data_source_id": ds(4)},
            "setup:view:review_due": {"url": "view://%s" % ("e" * 32)},
        })
        store.notion_record({"setup:view:tech_debt": {"url": "view://%s" % ("f" * 32)}})


class SetupTests(NotionTestCase):
    def test_setup_runs_in_dependency_order(self):
        plan = store.notion_plan()
        self.assertEqual(plan["status"], "todo")
        self.assertEqual(self.refs(plan), ["setup:page"])
        call = plan["actions"][0]["calls"][0]
        self.assertEqual(call["tool"], "notion-create-pages")
        self.assertEqual(call["arguments"]["creation_mode"], "draft")

        store.notion_record({"setup:page": {"url": url(1)}})
        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["setup:db:tasks"])
        args = plan["actions"][0]["calls"][0]["arguments"]
        self.assertEqual(args["parent"], {"type": "page_id", "page_id": "%032x" % 1})
        self.assertIn("\"Project\" SELECT('loyalty-api':default)", args["schema"])
        self.assertIn("'Stripe webhooks':default", args["schema"])
        self.assertIn("\"Review due\" DATE", args["schema"])

        store.notion_record({"setup:db:tasks": {"url": url(2), "data_source_id": ds(2)}})
        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["setup:db:decisions", "setup:db:questions", "setup:view:review_due"])
        decisions_ddl = plan["actions"][0]["calls"][0]["arguments"]["schema"]
        self.assertIn("\"Task\" RELATION('00000002000000000000000000000002', DUAL 'Decisions')", decisions_ddl)
        view = plan["actions"][2]["calls"][0]["arguments"]
        self.assertEqual(view["configure"], 'FILTER "Review due" <= "today"; SORT BY "Review due" ASC')

        store.notion_record({
            "setup:db:decisions": {"url": url(3), "data_source_id": ds(3)},
            "setup:db:questions": {"url": url(4), "data_source_id": ds(4)},
            "setup:view:review_due": {"url": "view://%s" % ("e" * 32)},
        })
        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["setup:view:tech_debt"])
        self.assertIn('FILTER "Kind" IN ("workaround", "deferred")',
                      plan["actions"][0]["calls"][0]["arguments"]["configure"])

        store.notion_record({"setup:view:tech_debt": {"url": "view://%s" % ("f" * 32)}})
        self.assertEqual(self.refs(store.notion_plan()), ["task:LOY-214"])

    def test_nothing_to_do_without_entries(self):
        (self.home / "entries" / "loyalty-api" / "LOY-214.json").unlink()
        self.assertEqual(store.notion_plan()["status"], "done")

    def test_ddl_quotes_and_commas(self):
        entry = example()
        entry["task"]["stack"] = ["O'Reilly lib", "React, Next"]
        ddl = store.notion_ddl("tasks", [entry])
        self.assertIn("'O''Reilly lib':default", ddl)
        self.assertIn("'React Next':default", ddl)


class SyncTests(NotionTestCase):
    def setUp(self):
        super().setUp()
        self.set_up_workspace()

    def test_task_then_items_then_done(self):
        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["task:LOY-214"])
        page = plan["actions"][0]["calls"][0]["arguments"]["pages"][0]
        props = page["properties"]
        self.assertEqual(props["Name"], "Take loyalty points back when an order is refunded")
        self.assertEqual(props["Layers"], ["business logic", "architecture"])
        self.assertEqual(props["date:Review due:start"], "2026-10-17")
        self.assertEqual(props["date:Logged:is_datetime"], 0)
        self.assertIn("<toggle>", page["content"])

        store.notion_record({"task:LOY-214": {"url": url(10)}})
        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["decisions:LOY-214", "questions:LOY-214"])
        self.assertEqual(plan["links"], {"LOY-214": url(10)})
        decision_pages = plan["actions"][0]["calls"][0]["arguments"]["pages"]
        self.assertEqual(len(decision_pages), 4)
        self.assertEqual(decision_pages[0]["properties"]["Task"], [url(10)])
        self.assertEqual(decision_pages[0]["properties"]["Reversible"], "__NO__")
        self.assertEqual(decision_pages[0]["properties"]["Rejected"],
                         "UPDATE members.points_balance directly\nSoft-delete the original earn row")
        self.assertNotIn("Impact", decision_pages[2]["properties"])
        question = plan["actions"][1]["calls"][0]["arguments"]["pages"][0]["properties"]
        self.assertEqual(question["Rating"], 3)

        store.notion_record({
            "decisions:LOY-214": {"urls": [url(20 + i) for i in range(4)]},
            "questions:LOY-214": {"urls": [url(30), url(31)]},
        })
        self.assertEqual(store.notion_plan()["status"], "done")

    def test_changed_entry_updates_page_and_adds_only_new_items(self):
        store.notion_record({"task:LOY-214": {"url": url(10)}})
        store.notion_record({
            "decisions:LOY-214": {"urls": [url(20 + i) for i in range(4)]},
            "questions:LOY-214": {"urls": [url(30), url(31)]},
        })
        later = example()
        later["task"]["title"] = "Reverse loyalty points on full and partial refunds"
        later["decisions"] = [dict(later["decisions"][0], title="Round partial reversals down")]
        self.save(later)

        plan = store.notion_plan()
        self.assertEqual(self.refs(plan), ["task:LOY-214", "decisions:LOY-214"])
        update = plan["actions"][0]["calls"]
        self.assertEqual([c["arguments"]["command"] for c in update], ["update_properties", "replace_content"])
        self.assertEqual(update[0]["arguments"]["page_id"], "%032x" % 10)
        self.assertEqual(plan["actions"][0]["url"], url(10))
        new_decisions = plan["actions"][1]["calls"][0]["arguments"]["pages"]
        self.assertEqual([p["properties"]["Decision"] for p in new_decisions], ["Round partial reversals down"])

        store.notion_record({"task:LOY-214": {"url": url(10)}, "decisions:LOY-214": {"urls": [url(24)]}})
        self.assertEqual(store.notion_plan()["status"], "done")

    def test_record_is_idempotent_and_checks_counts(self):
        store.notion_record({"task:LOY-214": {"url": url(10)}})
        before = store.notion_state_path().read_text(encoding="utf-8")
        store.notion_record({"task:LOY-214": {"url": url(10)}})
        self.assertEqual(store.notion_state_path().read_text(encoding="utf-8"), before)

        with self.assertRaises(store.EntryError) as ctx:
            store.notion_record({"decisions:LOY-214": {"urls": [url(20)]}})
        self.assertIn('expected "urls" with 4 page URLs', str(ctx.exception))

    def test_rebuild_from_existing_rows(self):
        store.notion_record({"task:LOY-214": {"url": url(10)}})
        titles = {d["title"]: url(20 + i) for i, d in enumerate(example()["decisions"])}
        store.notion_record({"decisions:LOY-214": {"existing": titles}})
        self.assertEqual(self.refs(store.notion_plan()), ["questions:LOY-214"])

    def test_record_rejects_bad_input(self):
        with self.assertRaises(store.EntryError) as ctx:
            store.notion_record({"task:NOPE-1": {"url": url(10)}, "task:LOY-214": {"url": "not a url"}})
        message = str(ctx.exception)
        self.assertIn("task:NOPE-1: no local entry", message)
        self.assertIn('task:LOY-214: expected "url"', message)

    def test_cli_plan_and_record(self):
        result = self.run_cli("notion-plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["actions"][0]["ref"], "task:LOY-214")

        results = self.write_draft({"task:LOY-214": {"url": url(10)}}, folder=self.home / "tmp")
        recorded = self.run_cli("notion-record", str(results))
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertIn("recorded task:LOY-214", recorded.stdout)
        self.assertFalse(results.exists())


class NotionContentTests(unittest.TestCase):
    def test_escapes_markdown_syntax(self):
        self.assertEqual(store.notion_escape("a $10 refund <b> [x] *y*"), r"a \$10 refund \<b\> \[x\] \*y\*")

    def test_quiz_toggles_and_code(self):
        content = store.render_notion_content(example())
        self.assertNotIn("<details>", content)
        self.assertIn(
            "<toggle>\n**1. Predict.** A member earned 200 points on a \\$100 order, spent 150 of them, "
            "then gets a \\$50 refund. What happens to their points?\n\n",
            content)
        self.assertIn("Proof: `app/Points/RefundOrderPoints.php`\n</toggle>", content)
        self.assertIn("```php\n$member->points_balance -= $order->points_earned;", content)

    def test_notion_id(self):
        self.assertEqual(store.notion_id("https://www.notion.so/Tasks-" + "ab" * 16 + "?v=1"), "ab" * 16)
        self.assertEqual(store.notion_id("collection://f336d0bc-b841-465b-8045-024475c079dd"),
                         "f336d0bcb841465b8045024475c079dd")


if __name__ == "__main__":
    unittest.main()
