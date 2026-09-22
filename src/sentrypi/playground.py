import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .compiler import compile_text

MAX_BODY = 64 * 1024

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SentryPi Playground</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
         background: #0d1117; color: #e6edf3; margin: 0; padding: 24px; }
  h1 { font-size: 20px; }
  h1 span { color: #2f81f7; }
  textarea { width: 100%; height: 220px; background: #161b22; color: #e6edf3;
             border: 1px solid #30363d; border-radius: 6px; padding: 12px;
             font-size: 13px; resize: vertical; box-sizing: border-box; }
  select, button { background: #238636; color: #fff; border: 0; border-radius: 6px;
                   padding: 10px 16px; font-size: 14px; cursor: pointer; }
  select { background: #21262d; color: #e6edf3; }
  pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
        padding: 12px; white-space: pre-wrap; font-size: 12px; min-height: 120px; }
  .bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; flex-wrap: wrap; }
  .ok { color: #3fb950; } .err { color: #f85149; } .warn { color: #d29922; }
</style>
</head>
<body>
<h1>🛡️ SentryPi <span>Playground</span></h1>
<p>Write <b>.pi</b> code and compile it through the Security Firewall — the backend
(secure container in production) returns the same stage output as <b>sentryc</b>.</p>
<div class="bar">
  <select id="example"></select>
  <button onclick="loadExample()">Load</button>
  <button onclick="compile()">▶ Compile</button>
</div>
<textarea id="src"></textarea>
<pre id="out">Ready. Enter code or load an example.</pre>
<script>
const ex = document.getElementById('example');
fetch('/examples').then(r => r.json()).then(list => {
  list.forEach(name => { const o = document.createElement('option'); o.value = name; o.textContent = name; ex.appendChild(o); });
});
function loadExample() {
  fetch('/examples/' + encodeURIComponent(ex.value)).then(r => r.text())
    .then(t => { document.getElementById('src').value = t; });
}
function compile() {
  const out = document.getElementById('out');
  out.textContent = 'Compiling…';
  fetch('/compile', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: document.getElementById('src').value }) })
    .then(r => r.json()).then(data => {
      let text = data.lines.join('\\n');
      if (data.artifacts) text += '\\n\\n--- artifacts ---\\n' + data.artifacts;
      if (data.map) text += '\\n\\n--- map ---\\n' + data.map;
      out.innerHTML = text.replace(/\\n/g, '\\n');
    }).catch(e => { out.textContent = String(e); });
}
</script>
</body>
</html>
"""


class PlaygroundHandler(BaseHTTPRequestHandler):
    examples_dir = Path(__file__).resolve().parents[2] / "examples"

    def log_message(self, _format, *_args):
        return

    def _send(self, code, body, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, _PAGE.encode("utf-8"), "text/html")
            return
        if self.path == "/examples":
            names = sorted(p.name for p in PlaygroundHandler.examples_dir.glob("*.pi"))
            self._send(200, json.dumps(names).encode("utf-8"))
            return
        if self.path.startswith("/examples/"):
            name = self.path.split("/", 2)[2]
            target = (PlaygroundHandler.examples_dir / name).resolve()
            if target.parent != PlaygroundHandler.examples_dir.resolve() or not target.is_file():
                self._send(404, b'{"error":"not found"}')
                return
            self._send(200, target.read_text(encoding="utf-8").encode("utf-8"), "text/plain")
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path != "/compile":
            self._send(404, b'{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                self._send(413, b'{"error":"payload too large"}')
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            source = payload.get("source", "")
        except Exception:
            self._send(400, b'{"error":"bad request"}')
            return

        lines = []

        def report(message):
            lines.append(message)

        out_dir = Path("/tmp/sentrypi-playground")
        result = compile_text(
            source, output_dir=str(out_dir), name="quickcheck", report=report
        )
        artifacts = []
        for path in (result.bin_path, result.map_path, result.sh_path, result.driver_path,):
            if path:
                artifacts.append(path)
        map_text = ""
        if result.map_path:
            try:
                map_text = Path(result.map_path).read_text(encoding="utf-8")
            except OSError:
                map_text = ""
        self._send(
            200,
            json.dumps(
                {
                    "ok": result.ok,
                    "exit": 0 if result.ok else 2,
                    "lines": lines,
                    "artifacts": "\n".join(artifacts),
                    "map": map_text,
                }
            ).encode("utf-8"),
        )


def serve(argv=None):
    parser = argparse.ArgumentParser(
        prog="sentryc serve",
        description="Launch the SentryPi web playground (localhost).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), PlaygroundHandler)
    print(f"[SentryPi] Playground live at http://{args.host}:{args.port}")
    print("[SentryPi] Production deployments should containerize this endpoint.")
    server.serve_forever()