"""
watch.py — Preview local instantané.
Lance un serveur HTTP + re-render automatique à chaque sauvegarde.

Usage :
    python watch.py

Puis ouvre http://localhost:8000 dans ton navigateur.
La page se rafraîchit toute seule dès que tu sauvegardes un fichier.
"""

import http.server
import subprocess
import sys
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

ROOT     = Path(__file__).resolve().parent
WATCH    = [ROOT / "templates", ROOT / "boxes", ROOT / "config.py", ROOT / "render_html.py"]
OUTPUT   = ROOT / "output"
PORT     = 8000
DEBOUNCE = 0.5  # secondes — évite les double-renders sur save


# ── Live-reload : injecte un petit script JS dans chaque page ──────────────

LIVERELOAD_JS = """
<script>
(function(){
  var last = null;
  setInterval(function(){
    fetch('/__ts__').then(r=>r.text()).then(function(t){
      if(last && t !== last) location.reload();
      last = t;
    });
  }, 800);
})();
</script>
"""

_last_render = str(time.time())


class InjectHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def do_GET(self):
        if self.path == "/__ts__":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(_last_render.encode())
            return
        super().do_GET()

    def send_head(self):
        # Injecte le JS de live-reload dans les pages HTML
        path = self.translate_path(self.path)
        if path.endswith(".html") or self.path in ("/", ""):
            try:
                content = Path(path if path.endswith(".html") else str(OUTPUT / "index.html")).read_bytes()
                content = content.replace(b"</body>", LIVERELOAD_JS.encode() + b"</body>", 1)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._injected = content
                return self
            except Exception:
                pass
        return super().send_head()

    def copyfile(self, source, outputfile):
        if hasattr(self, "_injected"):
            outputfile.write(self._injected)
            del self._injected
        else:
            super().copyfile(source, outputfile)

    def log_message(self, *args):
        pass  # silencieux


# ── Watcher ────────────────────────────────────────────────────────────────

class RenderHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer = None

    def on_modified(self, event):
        if event.is_directory:
            return
        if "__pycache__" in event.src_path:
            return
        self._schedule()

    on_created = on_modified

    def _schedule(self):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE, self._render)
        self._timer.start()

    def _render(self):
        global _last_render
        print("  → changement détecté, re-render...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "render_html.py")],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            _last_render = str(time.time())
            print("OK ✓")
        else:
            print("ERREUR")
            print(result.stderr[-500:])


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Render initial
    print("SAINHE Watch — http://localhost:8000")
    print("Render initial...", end=" ", flush=True)
    subprocess.run([sys.executable, str(ROOT / "render_html.py")], check=False)
    print("OK ✓")
    print("Surveille : templates/, boxes/, config.py")
    print("Ctrl+C pour arrêter\n")

    # Observateur de fichiers
    observer = Observer()
    handler  = RenderHandler()
    for path in WATCH:
        if Path(path).is_dir():
            observer.schedule(handler, str(path), recursive=True)
        elif Path(path).is_file():
            observer.schedule(handler, str(Path(path).parent), recursive=False)
    observer.start()

    # Serveur HTTP
    server = http.server.HTTPServer(("", PORT), InjectHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
        observer.stop()
    observer.join()
