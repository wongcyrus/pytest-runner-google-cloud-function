import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock
import zipfile

from openpyxl import load_workbook

from export_final_submissions import export_archive


class ExportFinalSubmissionsTests(unittest.TestCase):
    def test_marks_legacy_and_latest_code(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        long_code = "# final code\n" + "#" * 40_000 + "\n"
        completed = [
            {"student_id": "1", "question": "lab/a/task.py", "source_code": "old", "time": now},
            {"student_id": "2", "question": "lab/a/task.py", "source_code": "legacy", "time": now},
        ]
        latest = [{
            "student_id": "1", "question": "lab/a/task.py", "source_code": long_code,
            "source_code_complete": True, "status": "fail", "time": now,
            "summary": {"passed": 1, "total": 2},
        }, {
            "student_id": "4", "question": "lab/a/other.py", "source_code": "",
            "source_code_complete": True, "status": "error", "time": now,
        }]
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "export.zip")
            counts = export_archive(
                [{"student_id": str(i)} for i in range(1, 5)], completed, latest, output)
            self.assertEqual(counts, (4, 3))
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                final, legacy, error = manifest
                self.assertEqual(final["earned_mark"], 1)
                self.assertEqual(final["latest_status"], "fail")
                self.assertEqual(final["code_completeness"], "complete")
                self.assertEqual(archive.read(final["code_file"]).decode("utf-8"), long_code)
                self.assertTrue(final["code_file"].startswith("latest/"))
                self.assertEqual(archive.read(final["passed_code_file"]), b"old")
                self.assertTrue(final["passed_code_file"].startswith("passed/"))
                self.assertEqual(legacy["latest_status"], "legacy_pass")
                self.assertEqual(legacy["code_completeness"], "possibly_truncated")
                self.assertEqual(error["earned_mark"], 0)
                self.assertEqual(archive.read(error["code_file"]), b"")
                workbook = load_workbook(io.BytesIO(archive.read("scores.xlsx")))
                scores = list(workbook.active.values)
                self.assertEqual(scores[3], ("3", 0, 0, 0))
                self.assertEqual(scores[1][1], 1)
                workbook.close()

    def test_empty_export(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "empty.zip")
            self.assertEqual(export_archive([], [], [], output), (0, 0))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(json.loads(archive.read("manifest.json")), [])

    def test_test_deployment_lab01_filter_and_provenance(self):
        completed = [
            {"student_id": "1", "question": question, "source_code": "old"}
            for question in ("lab/lab01/task.py", "lab/lab02/task.py", "lab/lab010/task.py")
        ]
        latest = [
            {"student_id": "1", "question": "lab/lab01/task.py",
             "source_code": "final", "status": "fail"},
            {"student_id": "1", "question": "lab/lab02/other.py",
             "source_code": "excluded", "status": "fail"},
        ]
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "test.zip")
            counts = export_archive(
                [{"student_id": "1"}, {"student_id": "2"}], completed, latest, output,
                project="pytest-runner-test-2627", lab="lab01")
            self.assertEqual(counts, (2, 1))
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(len(manifest), 1)
                self.assertEqual(manifest[0]["question"], "lab/lab01/task.py")
                self.assertEqual(manifest[0]["earned_mark"], 1)
                self.assertEqual(archive.read(manifest[0]["code_file"]), b"final")
                info = json.loads(archive.read("export_info.json"))
                self.assertEqual(info["project"], "pytest-runner-test-2627")
                self.assertEqual(info["lab"], "lab01")
                wb = load_workbook(io.BytesIO(archive.read("scores.xlsx")))
                self.assertEqual(list(wb.active.values), [
                    ("id", "score", "lab/lab01/task.py"), ("1", 1, 1), ("2", 0, 0)])
                wb.close()

    def test_untrusted_identifiers_are_safe_paths_and_not_excel_formulas(self):
        record = {"student_id": "=1+1", "question": "../../evil.py", "source_code": "print('ok')"}
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "export.zip")
            export_archive([], [], [dict(record, status="pending")], output)
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertNotIn("..", manifest[0]["code_file"])
                wb = load_workbook(io.BytesIO(archive.read("submissions.xlsx")))
                self.assertEqual(wb.active["A2"].data_type, "s")
                self.assertEqual(wb.active["A2"].value, "=1+1")
                wb.close()

    def test_gcs_latest_and_passing_use_recorded_generations(self):
        client = MagicMock()
        latest_ref = {"bucket": "private", "object": "new.py", "generation": "12"}
        passed_ref = {"bucket": "private", "object": "pass.py", "generation": "9"}
        client.bucket.return_value.blob.return_value.download_as_bytes.side_effect = [
            "\u00e9".encode("utf-8") * 600_000, b"value = 1"]
        common = {"student_id": "1", "question": "lab/lab01/task.py"}
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "gcs.zip")
            export_archive([], [dict(common, source_ref=passed_ref)],
                           [dict(common, source_ref=latest_ref, status="error")],
                           output, storage_client=client)
            with zipfile.ZipFile(output) as archive:
                entry = json.loads(archive.read("manifest.json"))[0]
                self.assertEqual(entry["earned_mark"], 1)
                self.assertEqual(entry["latest_source_ref"], latest_ref)
                self.assertEqual(entry["passed_source_ref"], passed_ref)
                self.assertEqual(len(archive.read(entry["code_file"])), 1_200_000)
                self.assertEqual(archive.read(entry["passed_code_file"]), b"value = 1")
        calls = client.bucket.return_value.blob.call_args_list
        self.assertEqual(calls[0].kwargs["generation"], 12)
        self.assertEqual(calls[1].kwargs["generation"], 9)
        downloads = client.bucket.return_value.blob.return_value.download_as_bytes.call_args_list
        self.assertEqual(downloads[0].kwargs["if_generation_match"], 12)
        self.assertEqual(downloads[1].kwargs["if_generation_match"], 9)

    def test_storage_failure_keeps_existing_archive_and_cleans_partial(self):
        client = MagicMock()
        client.bucket.return_value.blob.return_value.download_as_bytes.side_effect = RuntimeError("404")
        record = {"student_id": "1", "question": "lab/a/task.py",
                  "source_ref": {"bucket": "private", "object": "missing.py", "generation": "1"}}
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "existing.zip")
            output.write_bytes(b"existing export")
            with self.assertRaisesRegex(RuntimeError, "404"):
                export_archive([], [], [record], output, storage_client=client)
            self.assertEqual(output.read_bytes(), b"existing export")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_source_checksum_failure_is_not_hidden_by_legacy_fallback(self):
        client = MagicMock()
        client.bucket.return_value.blob.return_value.download_as_bytes.return_value = b"wrong"
        record = {"student_id": "1", "question": "lab/a/task.py", "source_code": "old",
                  "source_ref": {"bucket": "private", "object": "bad.py", "sha256": "incorrect"}}
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output = Path(directory, "bad.zip")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                export_archive([], [], [record], output, storage_client=client)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
