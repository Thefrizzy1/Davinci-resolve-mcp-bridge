"""Bridge keep-alive: many requests reuse one connection instead of exhausting ports."""

import json
import os
import secrets
import socket
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import resolve_bridge as rb  # noqa: E402
from src.utils import resolve_bridge_client as rc  # noqa: E402

CFG = {"host": "127.0.0.1", "port": 0, "token": "k" * 48, "auth_clock_skew_seconds": 30}


class KeepAliveTest(unittest.TestCase):
    def setUp(self):
        self.connections = 0
        original = rb._Handler.handle

        def counting(handler):
            self.connections += 1
            return original(handler)

        patcher = mock.patch.object(rb._Handler, "handle", counting)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bridge = rb.Bridge(object(), CFG, lambda op, args: {"n": args.get("n")}).start()
        self.addCleanup(self.bridge.stop)
        self.transport = rc.BridgeTransport({**CFG, "port": self.bridge.port}, timeout=5)
        self.addCleanup(self.transport.close)

    def test_many_requests_share_one_connection(self):
        for n in range(500):
            self.assertEqual(self.transport.request("ping", {"n": n}), {"n": n})
        self.assertEqual(self.connections, 1)

    def test_reconnects_after_the_bridge_closes_an_idle_connection(self):
        with mock.patch.object(rb, "KEEPALIVE_IDLE_S", 0.6):
            self.transport.request("ping", {"n": 1})
            time.sleep(1.5)
            self.assertEqual(self.transport.request("ping", {"n": 2}), {"n": 2})
        self.assertEqual(self.connections, 2)

    def _raw(self, payload):
        sock = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=5)
        self.addCleanup(sock.close)
        sock.sendall((json.dumps(payload) + "\n").encode())
        reader = sock.makefile("rb")
        return json.loads(reader.readline()), reader.readline()

    def test_legacy_client_without_keepalive_is_closed_after_one_reply(self):
        payload = {"protocol": rb.PROTOCOL_VERSION, "id": str(uuid.uuid4()), "timestamp": int(time.time()),
                   "nonce": secrets.token_urlsafe(24), "operation": "ping", "arguments": {"n": 3}}
        payload["signature"] = rb.sign_request(CFG["token"], payload)
        reply, after = self._raw(payload)
        self.assertTrue(reply["ok"])
        self.assertNotIn("keepalive", reply)
        self.assertEqual(after, b"")

    def test_unauthenticated_connection_is_never_kept(self):
        reply, after = self._raw({"protocol": rb.PROTOCOL_VERSION, "keepalive": True})
        self.assertEqual(reply["error"]["code"], "unauthorized")
        self.assertEqual(after, b"")

    def test_stop_drains_with_an_idle_kept_alive_connection(self):
        self.transport.request("ping", {"n": 1})
        self.bridge.request_stop("exit")
        self.assertTrue(self.bridge._drain(5.0))


class CodexEntryTest(unittest.TestCase):
    def test_timeouts_and_windows_environment(self):
        import install

        with mock.patch.dict(os.environ, {"SYSTEMROOT": r"C:\Windows"}):
            entry = install.build_codex_entry(r"C:\py.exe", r"C:\s.py", r"C:\API", r"C:\l.dll",
                                              system="Windows", python_home=r"C:\Py")
        self.assertEqual(entry["env"]["SYSTEMROOT"], r"C:\Windows")
        table = install.render_codex_table(entry)
        self.assertIn("startup_timeout_sec = 120", table)
        self.assertIn("tool_timeout_sec = 600", table)
        merged = install.merge_codex_toml(
            '[mcp_servers.davinci-resolve]\ncommand = "x"\nstartup_timeout_sec = 300\n', entry)
        self.assertEqual(merged.count("startup_timeout_sec"), 1)
        self.assertIn("startup_timeout_sec = 300", merged)


if __name__ == "__main__":
    unittest.main()
