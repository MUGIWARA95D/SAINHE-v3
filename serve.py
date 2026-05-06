"""Simple static server for output/ — used by preview tool."""
import http.server, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "output"
os.chdir(ROOT)
port = int(sys.argv[1]) if len(sys.argv) > 1 else 7723
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=port)
