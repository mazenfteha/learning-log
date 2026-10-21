import copy
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "scripts" / "store.py"
EXAMPLE = ROOT / "examples" / "entry.example.json"
sys.path.insert(0, str(STORE.parent))

import store  # noqa: E402

NOW = dt.datetime(2026, 10, 21, 9, 30, tzinfo=dt.timezone.utc)


def example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self.home = Path(self._home.name)
        patcher = mock.patch.dict(os.environ, {"LEARNING_LOG_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._home.cleanup)
        self._drafts = tempfile.TemporaryDirectory()
        self.addCleanup(self._drafts.cleanup)
        self.drafts = Path(self._drafts.name)

    def write_draft(self, entry, name="entry.json", folder=None):
        path = (folder or self.drafts) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry), encoding="utf-8")
        return path

    def save(self, entry, **kwargs):
        return store.save(self.write_draft(entry), now=kwargs.get("now", NOW))

    def stored(self, task_id="LOY-214", project="loyalty-api"):
        json_path, _ = store.entry_paths(project, task_id)
        return json.loads(json_path.read_text(encoding="utf-8"))

    def run_cli(self, *args):
        env = dict(os.environ, LEARNING_LOG_HOME=str(self.home))
        return subprocess.run([sys.executable, str(STORE)] + list(args), capture_output=True,
                              text=True, encoding="utf-8", env=env)


class SaveAndRenderTests(StoreTestCase):
    def test_example_is_valid(self):
        self.assertEqual(store.validate_entry(example()), [])

    def test_valid_entry_saves_and_renders(self):
        result = self.save(example())

        self.assertEqual(result["status"], "new")
        self.assertEqual(result["json"], self.home / "entries" / "loyalty-api" / "LOY-214.json")
        self.assertTrue(result["md"].exists())
        entry = self.stored()
        self.assertEqual(entry["task"]["created_at"], "2026-10-14T16:20:00+00:00")
        self.assertEqual(entry["review"], {"due": "2026-10-17", "interval_days": 3,
                                           "last_reviewed": None, "times_reviewed": 0})
        markdown = result["md"].read_text(encoding="utf-8")
        self.assertIn("# Take loyalty points back when an order is refunded", markdown)
        self.assertIn("## Quiz", markdown)
        self.assertIn("<details><summary>Answer</summary>", markdown)
        self.assertIn("Proof: `app/Tiers/TierCalculator.php`", markdown)
        self.assertIn("```php", markdown)
        self.assertIn("- **Repo:** github.com/acme/loyalty-api", markdown)
        self.assertIn("- **Branch:** `feature/LOY-214-refund-points`", markdown)

    def test_entry_without_repo_shows_branch_only(self):
        entry = example()
        entry["task"]["repo"] = None
        markdown = self.save(entry)["md"].read_text(encoding="utf-8")
        self.assertNotIn("**Repo:**", markdown)
        self.assertIn("- **Branch:** `feature/LOY-214-refund-points`", markdown)

    def test_new_entry_without_created_at_is_due_three_days_from_now(self):
        entry = example()
        del entry["task"]["created_at"]
        self.save(entry)

        saved = self.stored()
        self.assertEqual(saved["task"]["created_at"], NOW.isoformat())
        self.assertEqual(saved["task"]["updated_at"], NOW.isoformat())
        self.assertEqual(saved["review"]["due"], "2026-10-24")

    def test_incoming_review_is_ignored(self):
        entry = example()
        entry["review"] = {"due": "2020-01-01", "interval_days": 60, "last_reviewed": None, "times_reviewed": 9}
        result = self.save(entry)

        self.assertEqual(self.stored()["review"]["due"], "2026-10-17")
        self.assertTrue(result["notes"])

    def test_draft_in_tmp_is_removed_after_save(self):
        draft = self.write_draft(example(), folder=self.home / "tmp")
        store.save(draft, now=NOW)
        self.assertFalse(draft.exists())

    def test_draft_outside_tmp_is_kept(self):
        draft = self.write_draft(example())
        store.save(draft, now=NOW)
        self.assertTrue(draft.exists())


class ValidationTests(StoreTestCase):
    def assertError(self, entry, *fragments):
        errors = store.validate_entry(entry)
        joined = "\n".join(errors)
        for fragment in fragments:
            self.assertIn(fragment, joined)
        return errors

    def test_bad_enum_names_field_and_allowed_values(self):
        entry = example()
        entry["task"]["layers"] = ["business_logic", "frontend"]
        self.assertError(entry, "task.layers[1]", '"frontend" is not one of business_logic, code, architecture, stack')

    def test_missing_field(self):
        entry = example()
        del entry["task"]["risk"]
        self.assertError(entry, "task.risk: required field is missing")

    def test_unknown_field(self):
        entry = example()
        entry["decisions"][0]["owner"] = "me"
        self.assertError(entry, "decisions[0].owner: unknown field")

    def test_too_many_quiz_items(self):
        entry = example()
        entry["quiz"] = entry["quiz"] + entry["quiz"][:2]
        self.assertError(entry, "quiz: expected at most 5 items, got 6")

    def test_decision_needs_a_rejected_alternative(self):
        entry = example()
        entry["decisions"][0]["rejected"] = []
        self.assertError(entry, "decisions[0].rejected: expected at least 1 item")

    def test_rating_range_and_bad_id(self):
        entry = example()
        entry["questions"][0]["rating"] = 6
        entry["task"]["id"] = "#42"
        self.assertError(entry, "questions[0].rating: expected a whole number from 1 to 5", "task.id")

    def test_code_snippet_line_limit(self):
        entry = example()
        entry["code"]["after"] = "\n".join("line %d" % i for i in range(11))
        self.assertError(entry, "code.after: expected at most 10 lines, got 11")

    def test_invalid_entry_is_not_saved(self):
        entry = example()
        entry["task"]["risk"] = "extreme"
        with self.assertRaises(store.EntryError) as ctx:
            self.save(entry)
        self.assertIn("task.risk", str(ctx.exception))
        self.assertFalse((self.home / "entries").exists())

    def test_invalid_json_reports_line(self):
        draft = self.drafts / "broken.json"
        draft.write_text('{"task": {\n  "id": "x",\n}', encoding="utf-8")
        with self.assertRaises(store.EntryError) as ctx:
            store.save(draft)
        self.assertIn("not valid JSON (line 2", str(ctx.exception))


class SecretTests(StoreTestCase):
    # Built at runtime so no secret-shaped literal sits in the repo.
    SECRETS = {
        "API secret key": "sk-ant-api03-" + "Ab1" * 12,
        "AWS access key": "AKIA" + "ABCDEFGHIJ234567",
        "GitHub token": "ghp_" + "a1B2" * 9,
        "private key": "-----BEGIN RSA " + "PRIVATE KEY-----",
        "password in a URL": "postgres://app:" + "hunter2hunter2" + "@db.internal/loyalty",
        "credential value": "STRIPE_SECRET" + "=" + "whsec9f8e7d6c5b4a",
    }

    def test_entry_with_secret_is_rejected_without_echoing_it(self):
        for name, secret in self.SECRETS.items():
            with self.subTest(name):
                entry = example()
                entry["task"]["how_it_works"] = "Config used " + secret + " for the call."
                with self.assertRaises(store.EntryError) as ctx:
                    self.save(entry)
                message = str(ctx.exception)
                self.assertIn("task.how_it_works", message)
                self.assertIn(name, message)
                self.assertNotIn(secret, message)
                self.assertFalse((self.home / "entries").exists())

    def test_secret_in_code_snippet_is_rejected(self):
        entry = example()
        entry["code"]["after"] = "client = Client('" + self.SECRETS["API secret key"] + "')"
        self.assertIn("code.after", "\n".join(store.validate_entry(entry)))

    def test_ordinary_words_are_not_flagged(self):
        entry = example()
        entry["task"]["surprised_me"] = ("The task-risk score and password reset tokens are unrelated; "
                                         "config.password = settings.DB_PASSWORD reads it from the env.")
        self.assertEqual(store.validate_entry(entry), [])


class UpsertTests(StoreTestCase):
    def test_saving_same_task_twice_changes_nothing(self):
        first = self.save(example())
        json_before = first["json"].read_bytes()
        md_before = first["md"].read_bytes()

        second = self.save(example(), now=NOW + dt.timedelta(days=1))

        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["added"], {"decisions": 0, "questions": 0, "quiz": 0})
        self.assertEqual(first["json"].read_bytes(), json_before)
        self.assertEqual(first["md"].read_bytes(), md_before)
        entry = self.stored()
        self.assertEqual(len(entry["decisions"]), 4)
        self.assertEqual(len(entry["questions"]), 2)
        self.assertEqual(len(entry["quiz"]), 4)

    def test_resave_skips_existing_items_and_appends_new_ones(self):
        self.save(example())
        later = example()
        later["task"]["title"] = "Reverse loyalty points on full and partial refunds"
        later["decisions"] = later["decisions"][:1]
        later["decisions"][0]["title"] = "  reverse points with a LEDGER row,   not by editing the balance "
        later["decisions"].append({
            "title": "Round partial reversals down",
            "chosen": "intdiv() so a member never loses a fractional point they didn't earn.",
            "rejected": ["Round to nearest"],
            "why": "Rounding up could take back more points than the refund is worth.",
            "kind": "product",
            "reversible": True,
            "files": ["app/Points/RefundOrderPoints.php"],
        })
        later["questions"] = later["questions"][:1]
        later["quiz"] = later["quiz"][:3]
        del later["task"]["created_at"]

        result = self.save(later, now=NOW + dt.timedelta(days=2))

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["added"], {"decisions": 1, "questions": 0, "quiz": 0})
        entry = self.stored()
        self.assertEqual(entry["task"]["title"], "Reverse loyalty points on full and partial refunds")
        self.assertEqual(entry["task"]["created_at"], "2026-10-14T16:20:00+00:00")
        self.assertEqual(entry["task"]["updated_at"], (NOW + dt.timedelta(days=2)).isoformat())
        self.assertEqual([d["title"] for d in entry["decisions"]][-1], "Round partial reversals down")
        self.assertEqual(len(entry["decisions"]), 5)
        self.assertEqual(len(entry["questions"]), 2)
        self.assertEqual(len(entry["quiz"]), 4)
        self.assertEqual(entry["review"]["due"], "2026-10-17")

    def test_duplicates_within_one_entry_are_dropped(self):
        entry = example()
        entry["quiz"].append(copy.deepcopy(entry["quiz"][0]))
        self.save(entry)
        self.assertEqual(len(self.stored()["quiz"]), 4)

    def test_merged_entry_can_grow_past_per_run_limits(self):
        self.save(example())
        for n in range(3):
            more = example()
            more["decisions"] = [dict(more["decisions"][0], title="Extra decision %d" % n)]
            self.save(more)
        entry = self.stored()
        self.assertEqual(len(entry["decisions"]), 7)
        self.assertEqual(store.validate_entry(entry, mode="stored"), [])
        self.assertIn("decisions: expected at most 4 items", "\n".join(store.validate_entry(entry)))

    def test_same_id_under_other_project_is_rejected(self):
        self.save(example())
        other = example()
        other["task"]["project"] = "billing"
        with self.assertRaises(store.EntryError) as ctx:
            self.save(other)
        self.assertIn("already saved under project 'loyalty-api'", str(ctx.exception))


class DueTests(StoreTestCase):
    def save_created(self, task_id, created_at):
        entry = example()
        entry["task"]["id"] = task_id
        entry["task"]["created_at"] = created_at
        self.save(entry)

    def test_due_returns_only_entries_due_today_or_earlier(self):
        self.save_created("LOY-1", "2026-10-10T10:00:00+00:00")  # due 2026-10-13
        self.save_created("LOY-2", "2026-10-18T10:00:00+00:00")  # due 2026-10-21
        self.save_created("LOY-3", "2026-10-19T10:00:00+00:00")  # due 2026-10-22

        due = store.due_entries(dt.date(2026, 10, 21))

        self.assertEqual([entry["task"]["id"] for _, entry in due], ["LOY-1", "LOY-2"])
        self.assertEqual(store.due_entries(dt.date(2026, 10, 12)), [])

    def test_due_filters_by_project(self):
        self.save_created("LOY-1", "2026-10-10T10:00:00+00:00")
        self.assertEqual(store.due_entries(dt.date(2026, 10, 21), project="billing"), [])


class CliTests(StoreTestCase):
    def test_save_then_show_list_due(self):
        saved = self.run_cli("save", str(EXAMPLE))
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertIn("saved LOY-214 (new: +4 decisions, +2 questions, +4 quiz)", saved.stdout)

        one_more = example()
        one_more["questions"] = [dict(one_more["questions"][0], asked="One more request")]
        updated = self.run_cli("save", str(self.write_draft(one_more)))
        self.assertIn("saved LOY-214 (updated: +0 decisions, +1 question, +0 quiz)", updated.stdout)
        self.assertIn("LOY-214.md", saved.stdout)

        again = self.run_cli("save", str(EXAMPLE))
        self.assertIn("saved LOY-214 (unchanged)", again.stdout)

        shown = self.run_cli("show", "LOY-214")
        self.assertIn("# Take loyalty points back", shown.stdout)

        listed = self.run_cli("list")
        self.assertIn("LOY-214", listed.stdout)
        self.assertIn("due 2026-10-17", listed.stdout)

        due = self.run_cli("due", "--today", "2026-10-16")
        self.assertIn("nothing due", due.stdout)
        due = self.run_cli("due", "--today", "2026-10-17")
        self.assertIn("LOY-214", due.stdout)

    def test_validate_exits_nonzero_with_errors(self):
        entry = example()
        entry["quiz"][0]["type"] = "guess"
        result = self.run_cli("validate", str(self.write_draft(entry)))
        self.assertEqual(result.returncode, 1)
        self.assertIn('quiz[0].type: "guess" is not one of predict, why, where, trap', result.stderr)

    def test_show_unknown_id(self):
        result = self.run_cli("show", "NOPE-1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no entry with this task id", result.stderr)

    def test_home_creates_tmp(self):
        result = self.run_cli("home")
        self.assertEqual(result.returncode, 0)
        self.assertIn(str(self.home / "tmp"), result.stdout)
        self.assertTrue((self.home / "tmp").is_dir())


if __name__ == "__main__":
    unittest.main()
