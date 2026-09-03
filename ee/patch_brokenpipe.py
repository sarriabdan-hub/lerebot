#!/usr/bin/env python3
"""Silence the BrokenPipeError traceback storm in vla_server.py _send().

A long /execute usually outlives its client (curl -m timeout, closed UI tab).
Writing the reply to that dead socket raises BrokenPipeError; the handler's
500-fallback then raises AGAIN on the same socket -> two long tracebacks for
what is really just "nobody was listening". The robot command already finished.

Idempotent + surgical; preserves all other local edits. Run ON THOR:
    python patch_brokenpipe.py /home/robot/dev/lerebot/ee/vla_server.py
"""
import shutil, sys
from pathlib import Path

OLD = '''    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)'''

NEW = '''    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            print(f"[http] client disconnected before the {code} reply "
                  f"(harmless -- the command itself finished)")'''

p = Path(sys.argv[1] if len(sys.argv) > 1 else "ee/vla_server.py")
src = p.read_text()
if "client disconnected before the" in src:
    print(f"already patched: {p}"); raise SystemExit(0)
if OLD not in src:
    print("ERROR: _send() body doesn't match the expected form — patch by hand:")
    print("wrap the send_response/end_headers/wfile.write block of _send() in")
    print("try/except (BrokenPipeError, ConnectionResetError).")
    raise SystemExit(1)
shutil.copy2(p, p.with_suffix(p.suffix + ".bak2"))
p.write_text(src.replace(OLD, NEW, 1))
print(f"PATCHED {p}\nbackup  {p}.bak2\nRestart vla_server.py.")
