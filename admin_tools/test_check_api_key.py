import contextlib
import io
import os
import unittest
from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError

import check_api_key


class CheckApiKeyTests(unittest.TestCase):
    def test_argument_overrides_environment(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "environment-key"}):
            with patch("sys.argv", ["check_api_key.py", " argument-key "]):
                with patch.object(check_api_key, "lookup_api_key") as lookup:
                    check_api_key.main()
        lookup.assert_called_once_with("argument-key")

    def test_environment_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "environment-key"}):
            with patch("sys.argv", ["check_api_key.py"]):
                with patch.object(check_api_key, "lookup_api_key") as lookup:
                    check_api_key.main()
        lookup.assert_called_once_with("environment-key")

    def test_missing_or_blank_key(self):
        for argv in (["check_api_key.py"], ["check_api_key.py", " "]):
            with self.subTest(argv=argv):
                with patch.dict(os.environ, {}, clear=True):
                    with patch("sys.argv", argv):
                        with patch.object(check_api_key, "lookup_api_key") as lookup:
                            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                                with self.assertRaises(SystemExit) as error:
                                    check_api_key.main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn("Provide an API key", stderr.getvalue())
                lookup.assert_not_called()

    def test_missing_credentials(self):
        with patch("sys.argv", ["check_api_key.py", "test-key"]):
            with patch.object(
                check_api_key,
                "lookup_api_key",
                side_effect=DefaultCredentialsError("Missing credentials"),
            ):
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    with self.assertRaises(SystemExit) as error:
                        check_api_key.main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn("gcloud auth application-default login", stderr.getvalue())

    def test_lookup_request(self):
        with patch.object(check_api_key.api_keys_v2, "ApiKeysClient") as client:
            with contextlib.redirect_stdout(io.StringIO()):
                check_api_key.lookup_api_key("test-key")
        request = client.return_value.lookup_key.call_args.kwargs["request"]
        self.assertEqual(request.key_string, "test-key")


if __name__ == "__main__":
    unittest.main()
