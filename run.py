"""Start TipCheck: python run.py  ->  http://127.0.0.1:8000"""

import os
import sys
import threading
import webbrowser

if sys.version_info < (3, 11):
    sys.exit("TipCheck needs Python 3.11 or newer.")

import uvicorn

from backend import config

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    if not config.key_source():
        print("WARNING: no PORTKEY_API_KEY or OPENAI_API_KEY found in .env (this folder or the one above).")
    url = f"http://127.0.0.1:{port}"
    print(f"TipCheck running at {url}  (Ctrl+C to stop)")
    if host == "127.0.0.1" and "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.main:app", host=host, port=port, log_level="warning")
