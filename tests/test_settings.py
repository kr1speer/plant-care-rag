"""Verify configuration independently of the developer's personal dotenv file."""

import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from dotenv import load_dotenv

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "app/config/settings.py"


class EnvironmentSettingsTests(SimpleTestCase):
    """Exercise required secrets, environment precedence and typed settings."""

    def read_settings(self, environment, dotenv_text=None):
        """Load real settings against an isolated environment and dotenv file.

        Args:
            environment: Variables supplied by the process.
            dotenv_text: Optional contents of the temporary dotenv file.

        Returns:
            The globals produced by executing the settings module.
        """
        with TemporaryDirectory() as directory:
            dotenv_file = Path(directory) / ".env"
            if dotenv_text is not None:
                dotenv_file.write_text(dotenv_text, encoding="utf-8")

            def isolated_dotenv(*args, **kwargs):
                return load_dotenv(dotenv_file, **kwargs)

            with (
                patch.dict(os.environ, environment, clear=True),
                patch("dotenv.load_dotenv", side_effect=isolated_dotenv),
            ):
                return runpy.run_path(str(SETTINGS_FILE))

    def test_secret_is_required_and_blank_values_are_rejected(self):
        """Reject absent or blank keys instead of falling back to a public key."""
        for environment in ({}, {"DJANGO_SECRET_KEY": ""}, {"DJANGO_SECRET_KEY": "  "}):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
                    self.read_settings(environment)

    def test_process_environment_works_without_dotenv(self):
        """Allow CI to configure the application without a dotenv file."""
        result = self.read_settings({"DJANGO_SECRET_KEY": "temporary-test-key"})
        self.assertEqual(result["SECRET_KEY"], "temporary-test-key")
        self.assertIs(result["DEBUG"], False)
        self.assertEqual(result["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]"])

    def test_dotenv_loads_values_without_overriding_process_environment(self):
        """Read a dotenv file while keeping the process key and debug setting."""
        result = self.read_settings(
            {"DJANGO_SECRET_KEY": "process-test-key", "DJANGO_DEBUG": "true"},
            "DJANGO_SECRET_KEY=file-test-key\nDJANGO_DEBUG=false\nDJANGO_ALLOWED_HOSTS=demo.local\n",
        )
        self.assertEqual(result["SECRET_KEY"], "process-test-key")
        self.assertIs(result["DEBUG"], True)
        self.assertEqual(result["ALLOWED_HOSTS"], ["demo.local"])

    def test_debug_accepts_only_case_insensitive_boolean_words(self):
        """Parse boolean words rather than interpreting any nonempty string as true."""
        for value, expected in (
            ("true", True),
            (" TRUE ", True),
            ("false", False),
            ("False", False),
        ):
            with self.subTest(value=value):
                result = self.read_settings(
                    {"DJANGO_SECRET_KEY": "test-key", "DJANGO_DEBUG": value}
                )
                self.assertIs(result["DEBUG"], expected)
        for value in ("", "1", "yes", "unexpected"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_DEBUG"):
                    self.read_settings(
                        {"DJANGO_SECRET_KEY": "test-key", "DJANGO_DEBUG": value}
                    )

    def test_allowed_hosts_is_a_trimmed_csv_list(self):
        """Discard blank host entries while preserving IPv6 brackets."""
        result = self.read_settings(
            {
                "DJANGO_SECRET_KEY": "test-key",
                "DJANGO_ALLOWED_HOSTS": " localhost, ,127.0.0.1, [::1], demo.local, ",
            }
        )
        self.assertEqual(
            result["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]", "demo.local"]
        )
