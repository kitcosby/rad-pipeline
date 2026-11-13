"""WP4 HTTP identity probe tests: a throwaway http.server on an
ephemeral port serves fixed responses; the probe must classify per
the WP2A taxonomy — content-marker success, HTTP 500 as a server
failure, connection refusal as transport, missing marker as semantic,
missing JSON key as schema, overrun as timeout. A 2xx alone is never
a pass. Fully offline (loopback only) and deterministic."""

import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter_fixture as fx

from radpipe.adapters import probe
from radpipe.adapters.bibleapp import BibleAppAdapter
from radpipe.evidence import EvidenceStore

OK_BODY = json.dumps({"status": "ok", "version": "1.2.3"}).encode("utf-8")
ERR_BODY = b"internal boom"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass

    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(OK_BODY)))
            self.end_headers()
            self.wfile.write(OK_BODY)
        elif self.path == "/err":
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(ERR_BODY)))
            self.end_headers()
            self.wfile.write(ERR_BODY)
        elif self.path == "/slow":
            time.sleep(5)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


class HttpProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_content_marker_success(self):
        result = probe.http_probe({
            "service": "staging-flask", "url": self.url("/ok"),
            "expect": {"status": 200, "markers": ["ok"],
                       "json_keys": ["status", "version"]},
        })
        self.assertEqual(result["classification"], "ok")
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["response_bytes"], len(OK_BODY))
        self.assertEqual(
            result["response_sha256"], hashlib.sha256(OK_BODY).hexdigest()
        )
        self.assertEqual(result["parse_verdict"], "json-ok")
        self.assertTrue(all(a["passed"] for a in result["assertions"]))
        self.assertEqual(len(result["assertions"]), 4)  # status+marker+2 keys

    def test_http_500_is_server_classification(self):
        result = probe.http_probe({
            "service": "staging-flask", "url": self.url("/err"),
            "expect": {"status": 200},
        })
        self.assertEqual(result["classification"], "server")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], 500)

    def test_connection_refused_is_transport(self):
        result = probe.http_probe({
            "service": "staging-api",
            "url": f"http://127.0.0.1:{fx.unused_port()}/health",
            "expect": {"status": 200},
        })
        self.assertEqual(result["classification"], "transport")
        self.assertIsNone(result["status"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["transport_outcome"], "transport")

    def test_missing_marker_is_semantic(self):
        result = probe.http_probe({
            "service": "staging-flask", "url": self.url("/ok"),
            "expect": {"status": 200, "markers": ["no-such-marker"]},
        })
        self.assertEqual(result["classification"], "semantic")
        self.assertFalse(result["passed"])

    def test_missing_json_key_is_schema(self):
        result = probe.http_probe({
            "service": "staging-flask", "url": self.url("/ok"),
            "expect": {"status": 200, "json_keys": ["missing_key"]},
        })
        self.assertEqual(result["classification"], "schema")
        self.assertFalse(result["passed"])

    def test_timeout_is_timeout(self):
        result = probe.http_probe({
            "service": "staging-flask", "url": self.url("/slow"),
            "timeout_s": 0.5, "expect": {"status": 200},
        })
        self.assertEqual(result["classification"], "timeout")
        self.assertFalse(result["passed"])

    def test_identity_evidence_block_in_adapter_cycle(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fixture = fx.make_repo(root)
        endpoint = {
            "service": "staging-flask", "url": self.url("/ok"),
            "method": "GET", "environment": "test",
            "expect": {"status": 200, "markers": ["ok"], "json_keys": ["status"]},
        }
        config = fx.make_config(root, fixture["repo"], endpoints=[endpoint])
        adapter = BibleAppAdapter(config, base_dir=root)
        run = adapter.run_cycle(cycle_id="bibleapp-http-001",
                                run_id="run-bibleapp-http-001")
        entry = run.report["identity"][0]
        self.assertEqual(entry["classification"], "ok")
        self.assertTrue(entry["passed"])
        self.assertEqual(entry["status"], 200)
        self.assertEqual(
            entry["response_sha256"], hashlib.sha256(OK_BODY).hexdigest()
        )
        store = EvidenceStore(config["evidence_path"])
        record = next(
            r for r in store.records()
            if r.get("evidence_id") == entry["evidence_id"]
        )
        self.assertEqual(record["class"], "DEMONSTRATED")
        self.assertEqual(record["api"]["status"], 200)
        self.assertEqual(record["api"]["service"], "staging-flask")
        self.assertEqual(
            record["api"]["response_sha256"], entry["response_sha256"]
        )
        self.assertEqual(len(record["api"]["assertion_results"]), 3)


if __name__ == "__main__":
    unittest.main()
