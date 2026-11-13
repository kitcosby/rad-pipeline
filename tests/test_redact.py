"""Redaction tests: secret keys and credential-shaped values are stripped."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radpipe.redact import REDACTED, redact

FAKE_GITHUB_TOKEN = "ghp_" + "A" * 36


class KeyRedactionTests(unittest.TestCase):
    def test_secret_keys_redacted(self):
        record = {
            "api_key": "abc123",
            "AUTH_TOKEN": "abc123",
            "db_password": "hunter2",
            "client_secret": "shh",
            "nested": {"aws_secret_access_key": "AKIAIOSFODNN7EXAMPLE"},
            "harmless": "keep me",
        }
        out = redact(record)
        for key in ("api_key", "AUTH_TOKEN", "db_password", "client_secret"):
            self.assertEqual(out[key], REDACTED, key)
        self.assertEqual(out["nested"]["aws_secret_access_key"], REDACTED)
        self.assertEqual(out["harmless"], "keep me")

    def test_secret_key_with_nonstring_value_redacted(self):
        out = redact({"token_count": 42, "refresh_token": {"complex": "object"}})
        self.assertEqual(out["refresh_token"], REDACTED)


class ValueRedactionTests(unittest.TestCase):
    def test_planted_fake_token_in_innocent_field(self):
        record = {"summary": f"probe used {FAKE_GITHUB_TOKEN} for auth"}
        out = redact(record)
        self.assertNotIn(FAKE_GITHUB_TOKEN, out["summary"])
        self.assertIn(REDACTED, out["summary"])

    def test_bearer_token(self):
        out = redact({"note": "Authorization: Bearer abc.def-123 sent"})
        self.assertNotIn("abc.def-123", out["note"])
        self.assertIn(REDACTED, out["note"])

    def test_url_password(self):
        out = redact({"dsn": "postgres://svc:s3cr3tpw@db.internal:5432/app"})
        self.assertNotIn("s3cr3tpw", out["dsn"])
        self.assertIn("svc", out["dsn"])  # username and host survive
        self.assertIn("db.internal", out["dsn"])

    def test_private_key_block(self):
        block = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEAfake\n"
            "-----END RSA PRIVATE KEY-----"
        )
        out = redact({"blob": f"prefix {block} suffix"})
        self.assertNotIn("MIIEowIBAAKCAQEAfake", out["blob"])
        self.assertIn(REDACTED, out["blob"])

    def test_aws_key_id_value(self):
        out = redact({"note": "saw AKIAIOSFODNN7EXAMPLE in the log"})
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", out["note"])

    def test_jwt_value(self):
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
        )
        out = redact({"note": f"token={jwt}"})
        self.assertNotIn(jwt, out["note"])

    def test_lists_and_scalars(self):
        out = redact({"items": ["plain", f"leaked {FAKE_GITHUB_TOKEN}", 7, None]})
        self.assertEqual(out["items"][0], "plain")
        self.assertNotIn(FAKE_GITHUB_TOKEN, out["items"][1])
        self.assertEqual(out["items"][2], 7)
        self.assertIsNone(out["items"][3])


class ImmutabilityTests(unittest.TestCase):
    def test_input_not_mutated(self):
        record = {"api_key": "abc123", "nested": {"items": [FAKE_GITHUB_TOKEN]}}
        snapshot = repr(record)
        redact(record)
        self.assertEqual(repr(record), snapshot)
        self.assertEqual(record["api_key"], "abc123")


if __name__ == "__main__":
    unittest.main()
