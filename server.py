"""
CareLink Dashboard Server
Serves static dashboard frontend files AND provides:
  - POST /api/trigger-scrape: triggers scraper.py in background on click
  - GET  /api/scrape-status:  checks if scraper is currently active
  - GET  /api/email-status:   whether email sending is configured
  - POST /api/send-email:     emails the staff member responsible for a dashboard item
"""

from collections import defaultdict, deque
from datetime import datetime, timezone
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time

from directory import StaffDirectory
import mailer

PORT = int(os.getenv("PORT", "8080"))
_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPER_SCRIPT = os.path.join(_DIR, "scraper.py")
DATA_FILE = os.path.join(_DIR, "data.json")

DATA_SECTIONS = {"incidents_needs_review", "incidents_open", "support_plans_overdue", "goals_overdue", "future_plans_overdue"}
MAX_BODY_BYTES = 8_000
MAX_NOTE_CHARS = 1_000
RATE_LIMIT = (10, 600)  # at most 10 emails per client IP per 10 minutes

# Email state (filled in main())
smtp_settings: "mailer.SmtpSettings | None" = None
email_log: dict[str, deque] = defaultdict(deque)
email_lock = threading.Lock()

# Concurrency state
scraper_lock = threading.Lock()
is_scraping = False
last_scrape_start = None
last_scrape_end = None
last_scrape_error = None


def run_scraper_thread():
    global is_scraping, last_scrape_start, last_scrape_end, last_scrape_error
    try:
        last_scrape_start = datetime.now(timezone.utc).isoformat()
        last_scrape_error = None
        print(f"\n[Server] >>> Launching live scraper at {last_scrape_start}...")

        # Run scraper.py as subprocess
        proc = subprocess.Popen(
            [sys.executable, SCRAPER_SCRIPT],
            cwd=_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in proc.stdout:
            print(f"[Scraper] {line.strip()}")

        proc.wait()
        if proc.returncode != 0:
            last_scrape_error = f"Exited with code {proc.returncode}"
            print(f"[Server] Scraper finished with error: {last_scrape_error}")
        else:
            print("[Server] Scraper completed successfully.")

    except Exception as e:
        last_scrape_error = str(e)
        print(f"[Server] Failed to run scraper: {e}")
    finally:
        with scraper_lock:
            is_scraping = False
            last_scrape_end = datetime.now(timezone.utc).isoformat()
        print(f"[Server] <<< Live scrape cycle ended at {last_scrape_end}.\n")


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS for local network devices
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/scrape-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            status_payload = {
                "running": is_scraping,
                "started_at": last_scrape_start,
                "finished_at": last_scrape_end,
                "error": last_scrape_error
            }
            self.wfile.write(json.dumps(status_payload).encode("utf-8"))
            return

        elif self.path == "/api/trigger-scrape":
            # Allow GET trigger for easy testing
            self.handle_trigger_scrape()
            return

        elif self.path == "/api/email-status":
            self.send_json(200, {"enabled": smtp_settings is not None})
            return

        # Never serve secrets or backend-only files to the browser
        if not self.is_public_path(self.path):
            self.send_error(404, "Not found")
            return

        # data.json is served with the CURRENT key worker names from residents.json added,
        # so names show even for data scraped before a residents.json change.
        if self.path.split("?")[0].lower() == "/data.json":
            self.serve_data_with_staff()
            return

        super().do_GET()

    def serve_data_with_staff(self):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.send_error(404, "No data yet - click Refresh Now")
            return
        except Exception as e:
            self.send_json(500, {"error": f"data.json could not be read: {e}"})
            return
        StaffDirectory.load().attach_staff_names(data)
        self.send_json(200, data)

    def do_POST(self):
        if self.path == "/api/trigger-scrape":
            self.handle_trigger_scrape()
            return
        if self.path == "/api/send-email":
            self.handle_send_email()
            return
        self.send_error(404, "Endpoint not found")

    # Only these files may be downloaded by a browser; everything else (.env, residents.json,
    # Python code, .git, ...) returns 404.
    PUBLIC_FILES = {"", "index.html", "app.js", "style.css", "cartoons.js", "data.json", "favicon.ico"}

    def is_public_path(self, path: str) -> bool:
        from urllib.parse import unquote, urlsplit
        clean = unquote(urlsplit(path).path)
        parts = [p for p in clean.replace("\\", "/").split("/") if p]
        if len(parts) > 1 or any(p.startswith(".") for p in parts):
            return False
        return (parts[0] if parts else "").lower() in self.PUBLIC_FILES

    def do_HEAD(self):
        if not self.is_public_path(self.path):
            self.send_error(404, "Not found")
            return
        super().do_HEAD()

    def send_json(self, status: int, payload: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def handle_send_email(self):
        if smtp_settings is None:
            self.send_json(503, {"error": "Email sending is not set up on this server."})
            return

        # ---- Parse and validate the request
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("bad length")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_json(400, {"error": "Invalid request."})
            return

        section = str(body.get("section", ""))
        item_id = str(body.get("item_id", ""))
        sender_email = str(body.get("sender_email", "")).strip()
        sender_name = " ".join(str(body.get("sender_name", "")).split())[:80]
        note = str(body.get("note", "")).strip()[:MAX_NOTE_CHARS]
        copy_sender = bool(body.get("copy_sender", True))

        if section not in DATA_SECTIONS or not item_id:
            self.send_json(400, {"error": "Unknown dashboard item."})
            return
        if not mailer.is_valid_email(sender_email):
            self.send_json(400, {"error": "Please enter a valid email address."})
            return

        # ---- Rate limit per client IP
        client = self.client_address[0]
        now = time.time()
        with email_lock:
            log = email_log[client]
            while log and now - log[0] > RATE_LIMIT[1]:
                log.popleft()
            if len(log) >= RATE_LIMIT[0]:
                self.send_json(429, {"error": "Too many emails sent. Please wait a few minutes."})
                return
            log.append(now)

        # ---- Find the item in the current data and its responsible staff member
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.send_json(500, {"error": "Dashboard data is not available."})
            return
        item = next((i for i in data.get(section, []) if str(i.get("id")) == item_id), None)
        if not item:
            self.send_json(404, {"error": "This item is no longer on the dashboard. Refresh and try again."})
            return

        resident_id = item_id[3:] if item_id.startswith("fp-") else ""
        staff = StaffDirectory.load().find(item.get("resident", ""), resident_id)
        if not staff or not mailer.is_valid_email(staff.get("staff_email", "")):
            self.send_json(404, {"error": f"No staff email is on file for {item.get('resident', 'this resident')}."})
            return

        # ---- Compose and send
        try:
            msg = mailer.build_message(smtp_settings, section, item, staff, sender_email, sender_name, note, copy_sender)
            mailer.send_message(smtp_settings, msg)
        except Exception as e:
            print(f"[Email] ERROR sending to {staff.get('staff_name')}: {e.__class__.__name__}: {e}")
            self.send_json(502, {"error": "The email could not be sent. Please try again later."})
            return

        print(f"[Email] Sent '{msg['Subject']}' to {staff.get('staff_name')} on behalf of {sender_email}.")
        self.send_json(200, {"status": "sent", "staff_name": staff.get("staff_name", "")})

    def handle_trigger_scrape(self):
        global is_scraping
        with scraper_lock:
            if is_scraping:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "already_running",
                    "message": "A live scrape is already currently in progress.",
                    "started_at": last_scrape_start
                }).encode("utf-8"))
                return

            is_scraping = True

        # Launch scraper thread
        t = threading.Thread(target=run_scraper_thread, daemon=True)
        t.start()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "started",
            "message": "Scraper started. Updating data in ~60-90s.",
            "started_at": last_scrape_start
        }).encode("utf-8"))


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    # Ask for Log My Care credentials once. They are kept in this process's environment
    # only, so the scraper subprocess started by "Refresh Now" inherits them.
    # Local secrets from .env (anything missing is asked for in the terminal)
    from envfile import load_env
    loaded = load_env()
    if loaded:
        print(f"[Config] Loaded from .env: {', '.join(sorted(loaded))}")

    from scraper import get_credentials
    get_credentials()

    # Optional: SMTP mailbox for the "Email staff" button (Enter skips it)
    global smtp_settings
    smtp_settings = mailer.get_smtp_settings()

    print(f"=" * 70)
    print(f"CareLink Live Dashboard Server running at http://localhost:{PORT}")
    print(f"Serving folder: {_DIR}")
    print(f"API endpoint available: POST /api/trigger-scrape")
    print(f"=" * 70)

    with ThreadedHTTPServer(("", PORT), DashboardRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dashboard server...")
            httpd.shutdown()


if __name__ == "__main__":
    main()
