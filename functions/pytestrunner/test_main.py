import datetime
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from flask import Request
from werkzeug.test import EnvironBuilder

from functions.pytestrunner import main


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.source_ref = {"bucket": "private", "object": "source.py", "generation": "123"}
        for name, options in (
                ("get_student_id_by_api_key", {"return_value": "1"}),
                ("upload_submission", {"return_value": self.source_ref}),
                ("save_submission", {}),
                ("run_tests", {"return_value": ("report", "fail", {"total": 2, "passed": 1})})):
            patcher = patch.object(main, name, **options)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def request(self, code="value = 1", **extra):
        return Request(EnvironBuilder(
            method="POST", query_string={"key": "test-key"},
            json={"sourceCodeFilePath": "lab/a/task.py", "sourceCode": code, **extra}
        ).get_environ())

    def test_large_utf8_failure_saves_source_before_tests_not_firestore_code(self):
        code = "\u00e9" * 600_000
        calls = MagicMock()
        calls.attach_mock(self.upload_submission, "upload")
        calls.attach_mock(self.save_submission, "save")
        calls.attach_mock(self.run_tests, "run")
        self.assertEqual(main.pytestrunner(self.request(code)), "report")
        self.assertEqual([call[0] for call in calls.mock_calls], ["upload", "save", "run", "save"])
        self.assertEqual(self.upload_submission.call_args.args[2], code)
        self.assertEqual(self.save_submission.call_args.args[2], self.source_ref)
        self.assertEqual(self.save_submission.call_args.args[6], "fail")

    def test_success_and_error_with_empty_code(self):
        self.run_tests.return_value = ("{}", "pass", {"passed": 1, "total": 1})
        self.assertEqual(main.pytestrunner(self.request())[1], 200)
        self.assertEqual(self.save_submission.call_args.args[6], "pass")
        self.run_tests.side_effect = ValueError("invalid report")
        self.assertEqual(main.pytestrunner(self.request(""))[1], 500)
        self.assertEqual(self.upload_submission.call_args.args[2], "")
        self.assertEqual(self.save_submission.call_args.args[6], "error")

    def test_request_limit_counts_entire_http_body(self):
        response = main.pytestrunner(self.request("x" * main.MAX_REQUEST_BYTES))
        self.assertEqual(response[1], 413)
        self.upload_submission.assert_not_called()
        self.run_tests.assert_not_called()

    def test_limit_also_checks_unadvertised_body_and_get_query(self):
        request = self.request("x" * main.MAX_REQUEST_BYTES)
        request.environ.pop("CONTENT_LENGTH")
        request.environ["wsgi.input_terminated"] = True
        self.assertEqual(main.pytestrunner(request)[1], 413)
        request = Request(EnvironBuilder(
            method="GET", query_string="x" * (main.MAX_REQUEST_BYTES + 1)).get_environ())
        self.assertEqual(main.pytestrunner(request)[1], 413)
        self.upload_submission.assert_not_called()

    def test_credentials_are_not_given_to_storage(self):
        main.pytestrunner(self.request(serviceAccountKey="SECRET"))
        self.assertNotIn("SECRET", self.upload_submission.call_args.args)
        self.assertEqual(self.run_tests.call_args.args[2], "SECRET")
        self.assertTrue(self.save_submission.call_args.args[3])

    def test_upload_failure_does_not_test_or_claim_saved(self):
        self.upload_submission.side_effect = RuntimeError("GCS unavailable")
        response = main.pytestrunner(self.request())
        self.assertEqual(response[1], 503)
        self.assertNotIn("saved", response[0])
        self.save_submission.assert_not_called()
        self.run_tests.assert_not_called()

    def test_pending_metadata_failure_does_not_test(self):
        self.save_submission.side_effect = RuntimeError("Firestore unavailable")
        response = main.pytestrunner(self.request())
        self.assertEqual(response[1], 503)
        self.assertIn("metadata failed", response[0])
        self.run_tests.assert_not_called()

    def test_final_metadata_failure_does_not_claim_mark(self):
        self.run_tests.return_value = ("{}", "pass", {"total": 1, "passed": 1})
        self.save_submission.side_effect = [None, RuntimeError("Firestore unavailable")]
        response = main.pytestrunner(self.request())
        self.assertEqual(response[1], 503)
        self.assertIn("mark was not confirmed", response[0])

    def test_error_metadata_failure_is_explicit(self):
        self.run_tests.side_effect = RuntimeError("pytest unavailable")
        self.save_submission.side_effect = [None, RuntimeError("Firestore unavailable")]
        response = main.pytestrunner(self.request())
        self.assertEqual(response[1], 503)
        self.assertIn("may remain pending", response[0])


class StorageAndTransactionTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.records = {}
        self.refs = {}

        def collection(name):
            result = MagicMock()

            def document(document_id):
                key = name, document_id
                if key not in self.refs:
                    ref = MagicMock()
                    ref.key = key

                    def get(**kwargs):
                        return MagicMock(exists=key in self.records,
                                         to_dict=lambda: self.records.get(key, {}).copy())
                    ref.get.side_effect = get
                    self.refs[key] = ref
                return self.refs[key]
            result.document.side_effect = document
            return result

        self.db.collection.side_effect = collection
        self.db.transaction.return_value.set.side_effect = (
            lambda ref, data: self.records.__setitem__(ref.key, data.copy()))
        self.now = datetime.datetime.now(datetime.timezone.utc)
        self.key = "1->lab_a_task.py"
        self.source_ref = {"bucket": "private", "object": "source.py", "generation": "123"}

    def save(self, seconds, status, submission_id=None):
        with patch.object(main.firestore, "Client", return_value=self.db), \
                patch.object(main.firestore, "transactional", side_effect=lambda f: f):
            main.save_submission(
                "1", "lab/a/task.py", self.source_ref, False,
                self.now + datetime.timedelta(seconds=seconds),
                submission_id or str(seconds), status, {"total": 1})

    def record(self, name):
        return self.records[name, self.key]

    def test_out_of_order_latest_and_passing_and_mark_preservation(self):
        self.save(2, "pending")
        self.save(1, "pass")
        self.assertEqual(self.record("LatestSubmission")["status"], "pending")
        self.assertEqual(self.record("CompletedTask")["submission_id"], "1")
        self.save(3, "pass")
        self.save(2, "pass")
        self.assertEqual(self.record("CompletedTask")["submission_id"], "3")
        self.assertEqual(self.record("CompletedTask")["time"], self.now + datetime.timedelta(seconds=1))
        self.save(4, "fail")
        self.assertEqual(self.record("LatestSubmission")["status"], "fail")
        self.assertEqual(self.record("CompletedTask")["submission_id"], "3")
        self.assertNotIn("source_code", self.record("LatestSubmission"))
        self.assertNotIn("source_code", self.record("CompletedTask"))

    def test_ties_and_retries_do_not_regress_terminal_status(self):
        self.save(1, "pending", "a")
        self.save(1, "pass", "a")
        self.save(1, "pending", "a")
        self.save(1, "error", "a")
        self.assertEqual(self.record("LatestSubmission")["status"], "pass")
        self.save(1, "pending", "b")
        self.save(1, "fail", "a")
        self.assertEqual(self.record("LatestSubmission")["submission_id"], "b")
        self.assertEqual(self.record("CompletedTask")["submission_id"], "a")

    def test_passing_transaction_reads_both_records_before_writing(self):
        calls = MagicMock()
        self.save(1, "pending")
        calls.attach_mock(self.refs["LatestSubmission", self.key], "latest")
        # Materialize the passing reference before tracking transaction reads.
        completed_ref = self.db.collection("CompletedTask").document(self.key)
        calls.attach_mock(completed_ref, "completed")
        calls.attach_mock(self.db.transaction.return_value, "transaction")
        self.save(1, "pass")
        self.assertEqual([call[0] for call in calls.mock_calls],
                         ["latest.get", "completed.get", "transaction.set", "transaction.set"])

    def test_legacy_mark_is_preserved_and_latest_passing_code_is_replaced(self):
        old_time = (self.now - datetime.timedelta(days=1)).replace(tzinfo=None)
        self.records["CompletedTask", self.key] = {
            "student_id": "1", "question": "lab/a/task.py", "time": old_time,
            "source_code": "legacy",
        }
        self.save(1, "fail")
        self.assertEqual(self.record("CompletedTask")["source_code"], "legacy")
        self.save(2, "pass")
        self.assertEqual(self.record("CompletedTask")["time"], old_time)
        self.assertEqual(self.record("CompletedTask")["source_ref"], self.source_ref)
        self.assertNotIn("source_code", self.record("CompletedTask"))

    def test_immutable_upload_uses_safe_paths_full_utf8_and_generation(self):
        client = MagicMock()
        blob = client.bucket.return_value.blob.return_value
        blob.bucket.name = "private"
        blob.generation = 987
        code = "\u00e9\n" * 500_000
        with patch.object(main.storage, "Client", return_value=client), \
                patch.dict(main.os.environ, {"SUBMISSION_BUCKET": "private"}):
            reference = main.upload_submission("../student", "../../task", code, "abc")
        name = client.bucket.return_value.blob.call_args.args[0]
        self.assertTrue(name.startswith("students/"))
        self.assertNotIn("..", name)
        self.assertTrue(name.endswith("/submissions/abc.py"))
        blob.upload_from_string.assert_called_once_with(
            code.encode("utf-8"), content_type="text/plain; charset=utf-8", if_generation_match=0)
        self.assertEqual(reference["generation"], "987")
        self.assertEqual(reference["sha256"], hashlib.sha256(code.encode("utf-8")).hexdigest())
        client.close.assert_called_once()

    def test_real_pytest_pass_fail_and_collection_error(self):
        with tempfile.TemporaryDirectory(dir=".") as directory, \
                patch.object(tempfile, "tempdir", str(Path.cwd())):
            with zipfile.ZipFile(Path(directory, "assignments.zip"), "w") as bundle:
                bundle.writestr("lab/a/task.py", "")
                bundle.writestr(
                    "tests/a/test_task.py",
                    "import runpy\n"
                    "def test_value():\n"
                    "    assert runpy.run_path('lab/a/task.py')['value'] == 1\n")
            with patch.object(main, "__file__", str(Path(directory, "main.py"))):
                for code, expected in (
                        ("value = 1", "pass"), ("value = 2", "fail"),
                        ("value = 1\n" + "# unchanged\n" * 4000, "pass")):
                    with self.subTest(expected=expected):
                        _, status, summary = main.run_tests(
                            "lab/a/task.py", code, None, None, "1")
                        self.assertEqual(status, expected)
                        self.assertEqual(summary["total"], 1)
                with zipfile.ZipFile(Path(directory, "assignments.zip"), "w") as bundle:
                    bundle.writestr("lab/a/task.py", "")
                    bundle.writestr("tests/a/test_task.py", "this is not valid python !")
                _, status, _ = main.run_tests("lab/a/task.py", "", None, None, "1")
                self.assertEqual(status, "error")


if __name__ == "__main__":
    unittest.main()
