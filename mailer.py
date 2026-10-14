"""
Email notifications for the CareLink dashboard.

Deliverability (keeping mail out of spam):
  - Mail is sent FROM the authenticated SMTP mailbox (e.g. a fortix.co.uk Google Workspace
    account). fortix.co.uk's SPF record already authorises Google, so SPF/DKIM/DMARC pass.
  - The person who clicked "Email" goes in Reply-To (and optionally Cc). Their address is
    never used as From, because sending "as" an address the server does not own fails
    SPF/DMARC and is the most common reason such mail lands in spam.
  - Every message has a plain-text AND an HTML part, a Message-ID, a Date header, a
    specific subject line and no "urgent"/all-caps wording.

SMTP settings come from environment variables, or are asked for in the terminal when
server.py starts:
  SMTP_HOST (default smtp.gmail.com)   SMTP_PORT (default 587, STARTTLS)
  SMTP_USER  (mailbox to send from)    SMTP_PASSWORD (Google "App password")
  SMTP_FROM_NAME (default "CareLink Dashboard")
"""

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
import getpass
import html
import os
import re
import smtplib
import sys

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

LMC_LINKS = {
    "support_plans_overdue": "https://careoffice.logmycare.co.uk/reports/care-planning/care-plans",
    "goals_overdue": "https://careoffice.logmycare.co.uk/reports/goals/goals-management?reviewStatuses%5B0%5D=overdue",
}


def is_valid_email(address: str) -> bool:
    return bool(address) and len(address) <= 254 and bool(EMAIL_RE.match(address))


# ==============================================================================
# SMTP SETTINGS
# ==============================================================================
@dataclass
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str
    from_name: str = "CareLink Dashboard"

    def connect(self) -> smtplib.SMTP:
        if self.port == 465:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            server.starttls()
        server.login(self.user, self.password)
        return server

    def verify(self) -> None:
        """Log in once to fail fast on a wrong password / host."""
        with self.connect() as server:
            server.noop()


def get_smtp_settings() -> SmtpSettings | None:
    """SMTP settings from env vars, or ask in the terminal. Returns None if email is skipped."""
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    from_name = os.getenv("SMTP_FROM_NAME", "CareLink Dashboard").strip() or "CareLink Dashboard"

    interactive = bool(sys.stdin) and sys.stdin.isatty()

    if user and password:  # from environment variables
        settings = SmtpSettings(host, port, user, password, from_name)
        error = _try_login(settings)
        if error:
            print(f"[Email] ERROR: SMTP login for {user} failed: {error}\n        Email sending is disabled.")
            return None
        return settings

    if not interactive:
        print("[Email] SMTP_USER / SMTP_PASSWORD not set - email sending is disabled.")
        return None

    print("\nEmail sending (press Enter to skip and run without email)")
    print("  Use a FULL fortix.co.uk Google Workspace address (e.g. dashboard@fortix.co.uk)")
    print("  and its Google App Password (Google Account > Security > 2-Step Verification > App passwords).")

    for attempt in range(1, 4):
        user = input("  Send from mailbox: ").strip()
        if not user:
            print("[Email] Skipped - the Email button will be disabled.")
            return None
        if not is_valid_email(user):
            print("  That is not a full email address - it must look like name@fortix.co.uk.")
            continue
        password = getpass.getpass("  App password (hidden): ").replace(" ", "")
        settings = SmtpSettings(host, port, user, password, from_name)
        error = _try_login(settings)
        if not error:
            return settings
        print(f"  Login failed: {error}")
        if attempt < 3:
            print("  Try again (or press Enter to skip).")

    print("[Email] Email sending is disabled for this session.")
    return None


def _try_login(settings: SmtpSettings) -> str:
    """Log in once. Returns '' on success, otherwise a plain-English reason."""
    try:
        settings.verify()
        print(f"[Email] SMTP login OK - emails will be sent from {settings.user} via {settings.host}:{settings.port}.")
        return ""
    except smtplib.SMTPAuthenticationError:
        return ("Google rejected the email/password. Use an App Password (16 letters), not the normal "
                "account password, and make sure 2-Step Verification is on for that account.")
    except smtplib.SMTPServerDisconnected:
        return ("Google closed the connection. This usually means the mailbox is not a full email address "
                "or the App Password is wrong.")
    except (OSError, smtplib.SMTPException) as e:
        return f"could not reach {settings.host}:{settings.port} ({e.__class__.__name__}: {e})."


# ==============================================================================
# MESSAGE CONTENT
# ==============================================================================
def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def describe_item(section: str, item: dict) -> dict:
    """Turn a data.json item into subject / headline / detail lines / link."""
    resident = item.get("resident", "Resident")

    if section in ("incidents_needs_review", "incidents_open"):
        status = "needs review" if section == "incidents_needs_review" else "is open"
        title = item.get("title", "Incident")
        lines = [f"Incident: {title}", f"Status: {item.get('status', '')}"]
        if item.get("date"):
            lines.append(f"Recorded: {item['date']}")
        if item.get("summary"):
            lines.append(f"Summary: {item['summary']}")
        return {
            "subject": f"Incident {status}: {title} - {resident}",
            "headline": f"An incident for {resident} {status}.",
            "lines": lines,
            "link": item.get("link", ""),
        }

    if section == "support_plans_overdue":
        plans = item.get("plans", [])
        return {
            "subject": f"{_plural(len(plans), 'support plan')} overdue for review - {resident}",
            "headline": f"{resident} has {_plural(len(plans), 'support plan')} overdue for review.",
            "lines": [f"{p.get('name')} (overdue {p.get('overdue_text', '')})" for p in plans],
            "link": LMC_LINKS[section],
        }

    if section == "goals_overdue":
        goals = item.get("goals", [])
        return {
            "subject": f"{_plural(len(goals), 'goal review')} overdue - {resident}",
            "headline": f"{resident} has {_plural(len(goals), 'goal review')} overdue.",
            "lines": [f"{g.get('title')}" + (f" (progress {g['progress']})" if g.get("progress") else "") for g in goals],
            "link": LMC_LINKS[section],
        }

    if section == "future_plans_overdue":
        plans = item.get("plans", [])
        return {
            "subject": f"{_plural(len(plans), 'future plan')} overdue for review - {resident}",
            "headline": f"{resident} has {_plural(len(plans), 'future plan')} past the review date.",
            "lines": [f"{p.get('title')} (review was due {p.get('next_review') or 'earlier'})" for p in plans],
            "link": item.get("link", ""),
        }

    raise ValueError(f"Unknown section: {section}")


def build_message(settings: SmtpSettings, section: str, item: dict, staff: dict,
                  sender_email: str, sender_name: str = "", note: str = "", copy_sender: bool = True) -> EmailMessage:
    info = describe_item(section, item)
    staff_first = (staff.get("staff_name") or "there").split()[0]
    sender_label = f"{sender_name} ({sender_email})" if sender_name else sender_email
    resident = item.get("resident", "Resident")

    # ---- Plain text
    text = [f"Hi {staff_first},", "",
            f"{sender_label} has flagged the following on the CareLink dashboard for your attention.", "",
            f"Resident: {resident}", info["headline"], ""]
    text += [f"  - {line}" for line in info["lines"]]
    if note:
        text += ["", f"Note from {sender_name or sender_email}:", note]
    if info["link"]:
        text += ["", f"Open in Log My Care: {info['link']}"]
    text += ["", f"You can reply to this email to respond to {sender_name or sender_email} directly.",
             "", "Thanks,", settings.from_name, f"Sent on behalf of {sender_label}"]

    # ---- HTML
    esc = html.escape
    rows = "".join(f"<li style='margin:2px 0'>{esc(line)}</li>" for line in info["lines"])
    note_html = (f"<p style='margin:16px 0 4px'><strong>Note from {esc(sender_name or sender_email)}:</strong></p>"
                 f"<p style='margin:0;padding:10px 12px;background:#f8fafc;border-left:3px solid #4f46e5;white-space:pre-wrap'>{esc(note)}</p>") if note else ""
    link_html = (f"<p style='margin:16px 0'><a href='{esc(info['link'])}' style='color:#4f46e5'>Open in Log My Care</a></p>") if info["link"] else ""
    body_html = f"""<!doctype html>
<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#0f172a;line-height:1.5">
<p>Hi {esc(staff_first)},</p>
<p>{esc(sender_label)} has flagged the following on the CareLink dashboard for your attention.</p>
<p style="margin:12px 0 4px"><strong>Resident:</strong> {esc(resident)}<br>{esc(info['headline'])}</p>
<ul style="margin:4px 0 0;padding-left:20px">{rows}</ul>
{note_html}
{link_html}
<p>You can reply to this email to respond to {esc(sender_name or sender_email)} directly.</p>
<p>Thanks,<br>{esc(settings.from_name)}<br><span style="color:#64748b">Sent on behalf of {esc(sender_label)}</span></p>
</body></html>"""

    msg = EmailMessage()
    msg["Subject"] = info["subject"]
    msg["From"] = formataddr((settings.from_name, settings.user))
    msg["To"] = formataddr((staff.get("staff_name", ""), staff["staff_email"]))
    msg["Reply-To"] = formataddr((sender_name, sender_email))
    if copy_sender and sender_email.lower() != staff["staff_email"].lower():
        msg["Cc"] = formataddr((sender_name, sender_email))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.user.split("@")[-1])
    msg.set_content("\n".join(text))
    msg.add_alternative(body_html, subtype="html")
    return msg


def send_message(settings: SmtpSettings, msg: EmailMessage) -> None:
    with settings.connect() as server:
        server.send_message(msg)
