"""
Log My Care - Real-time Dashboard Scraper
Scrapes:
  1. Incidents (Needs Review & Open) from /reports/incidents/list
  2. Support Plans (Overdue section only) from /reports/care-planning/care-plans
  3. Goals (Review status = Overdue) from /reports/goals/goals-management (expanding each resident)
  4. Future Plans (OVERDUE tag) from /residents/<id>/future-plans for every resident in residents.json
Saves output atomically to data.json for the live dashboard frontend.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
import re
import sys
from playwright.async_api import async_playwright, Page, BrowserContext

from directory import RESIDENTS_FILE, StaffDirectory, load_residents
from envfile import load_env

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BASE_URL = "https://careoffice.logmycare.co.uk/"

# Credentials are NEVER stored in code. They come from:
#   - GitHub Actions: repository secrets LMC_EMAIL / LMC_PASSWORD (passed as env vars)
#   - Local runs: typed into the terminal when prompted (kept in memory only)


def get_credentials() -> tuple[str, str]:
    """Return (email, password) from env vars, or prompt for them in an interactive terminal."""
    email = os.getenv("LMC_EMAIL", "").strip()
    password = os.getenv("LMC_PASSWORD", "")
    if email and password:
        return email, password

    if not sys.stdin or not sys.stdin.isatty():
        raise SystemExit(
            "[Credentials] LMC_EMAIL / LMC_PASSWORD are not set and no terminal is available to ask for them.\n"
            "              On GitHub, add them under Settings > Secrets and variables > Actions."
        )

    print("\nLog My Care login (used for this session only, never saved to disk)")
    while not email:
        email = input("  Email: ").strip()
    while not password:
        password = getpass.getpass("  Password (hidden): ")

    # Make them available to child processes started from this one (e.g. server.py -> scraper.py)
    os.environ["LMC_EMAIL"] = email
    os.environ["LMC_PASSWORD"] = password
    return email, password

INCIDENTS_URL = "https://careoffice.logmycare.co.uk/reports/incidents/list"
SUPPORT_PLANS_URL = "https://careoffice.logmycare.co.uk/reports/care-planning/care-plans"
GOALS_URL = "https://careoffice.logmycare.co.uk/reports/goals/goals-management"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_SCRIPT_DIR, "data.json")

def is_explicitly_overdue(text: str) -> bool:
    """
    Check if the text contains the word 'overdue' (case-insensitive word boundary).
    Only returns True if the word 'overdue' is written on it.
    """
    if not text:
        return False
    return bool(re.search(r"\boverdue\b", text, re.IGNORECASE))


def clean_text(text: str) -> str:
    """Collapse the double spaces LMC puts inside names ("Liam  Grinyer")."""
    return re.sub(r"\s+", " ", text or "").strip()


def initials_for(name: str) -> str:
    parts = [p for p in re.sub(r"[()]", "", name).split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


INCIDENT_ITEM_SEL = 'a[data-testid^="incident-list-item-"][data-testid$="-link"]'
INCIDENT_PAGINATION_SEL = '[data-testid="incidents-report-main-pagination"]'
MAX_INCIDENT_PAGES = 40  # safety cap so a broken "Next" button can never loop forever

# ==============================================================================
# LOGIN & NAVIGATION HELPERS
# ==============================================================================
async def login(page: Page, email: str, password: str) -> bool:
    print("[Login] Navigating to Log My Care...")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_load_state("load", timeout=20000)
    except Exception:
        pass

    email_locator = page.get_by_placeholder("Email")
    residents_tab = page.get_by_role("tab", name="Residents")

    for _ in range(60):
        if await residents_tab.is_visible():
            print("[Login] Already authenticated.")
            return True
        if await email_locator.is_visible():
            break
        await page.wait_for_timeout(500)

    if not await email_locator.is_visible() and await residents_tab.is_visible():
        print("[Login] Authenticated successfully.")
        return True

    print("[Login] Submitting credentials...")
    await email_locator.fill(email)
    next_btn = page.get_by_role("button", name="Next")
    if await next_btn.is_visible():
        await next_btn.click()

    password_locator = page.get_by_placeholder("Password")
    await password_locator.wait_for(state="visible", timeout=12000)
    await password_locator.fill(password)

    submit_btn = page.get_by_role("button", name="Submit")
    await submit_btn.click()

    try:
        await residents_tab.wait_for(state="visible", timeout=25000)
        print("[Login] Login succeeded.")
        return True
    except Exception as e:
        print(f"[Login] ERROR: Failed to reach dashboard after login: {e}")
        return False


# ==============================================================================
# PHASE 1: SCRAPE INCIDENTS (Needs Review & Open)
# ==============================================================================
async def scrape_incidents(page: Page) -> tuple[list[dict], list[dict]]:
    print("\n--- [Phase 1/4] Scraping Incidents ---")
    needs_review: list[dict] = []
    open_incidents: list[dict] = []

    try:
        await page.goto(INCIDENTS_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)

        # 1. Locate the VISIBLE Status filter dropdown
        print("[Incidents] Locating visible Status filter...")
        status_select = None
        for s in await page.locator('[data-testid="incident-filters-status-select"]').all():
            if await s.is_visible():
                status_select = s
                break

        # Fallback to Ant Design select matching 'Status' placeholder/text
        if not status_select:
            for s in await page.locator('.ant-select').all():
                if await s.is_visible():
                    txt = (await s.inner_text()).lower()
                    if "status" in txt:
                        status_select = s
                        break

        if status_select:
            print("[Incidents] Opening Status filter dropdown...")
            await status_select.click()
            await page.wait_for_timeout(600)

            # Check and select 'Needs review' and 'Open' while ensuring 'Closed' is unselected
            options = await page.locator(".ant-select-dropdown:visible .ant-select-item-option").all()
            for opt in options:
                txt = (await opt.inner_text()).strip()
                is_selected = "ant-select-item-option-selected" in (await opt.get_attribute("class") or "")
                if txt.lower() in ["needs review", "open"] and not is_selected:
                    print(f"[Incidents] Selecting '{txt}'...")
                    await opt.click()
                    await page.wait_for_timeout(350)
                elif txt.lower() == "closed" and is_selected:
                    print("[Incidents] Unselecting 'Closed'...")
                    await opt.click()
                    await page.wait_for_timeout(350)

            # Close dropdown overlay
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(2000)
        else:
            print("[Incidents] WARNING: Visible Status select filter not found.")

        # 2. Show 50 incidents per page instead of the default 10
        try:
            await set_incident_page_size(page, 50)
        except Exception as e:
            print(f"[Incidents] WARNING: could not set 50/page ({e}); continuing with default page size.")

        # 3. Walk every page of results (page 1, 2, 3, ... until "Next" is disabled)
        seen_keys = set()
        for page_no in range(1, MAX_INCIDENT_PAGES + 1):
            card_links = await page.locator(INCIDENT_ITEM_SEL).all()
            print(f"[Incidents] Page {page_no}: {len(card_links)} incident card link(s).")
            await parse_incident_cards(card_links, seen_keys, needs_review, open_incidents)

            if not await go_to_next_incident_page(page, page_no):
                break
        else:
            print(f"[Incidents] WARNING: stopped after {MAX_INCIDENT_PAGES} pages (safety cap).")

        print(f"[Incidents] Successfully extracted: {len(needs_review)} Needs Review, {len(open_incidents)} Open.")

    except Exception as e:
        print(f"[Incidents] ERROR scraping incidents: {e}")

    return needs_review, open_incidents


async def parse_incident_cards(card_links, seen_keys: set, needs_review: list, open_incidents: list) -> None:
    for card in card_links:
        try:
            details_el = card.locator('[data-testid$="-details"]').first
            title_el = card.locator('[data-testid$="-title"]').first
            status_el = card.locator('[data-testid$="-status-tag"]').first
            desc_el = card.locator('[data-testid$="-description"]').first

            details_text = clean_text(await details_el.inner_text()) if await details_el.count() > 0 else ""
            title = clean_text(await title_el.inner_text()) if await title_el.count() > 0 else ""
            status_raw = clean_text(await status_el.inner_text()) if await status_el.count() > 0 else ""
            desc = (await desc_el.inner_text()).strip() if await desc_el.count() > 0 else ""
            href = await card.get_attribute("href") or ""

            # Parse resident and date from details string: "Hollie Peet • 09/10/2026 18:59"
            resident, _, date_str = details_text.partition("•")
            resident = resident.strip() or "Resident"
            date_str = date_str.strip()

            # Normalize status (checked per row, so closed items are dropped even if the filter failed)
            upper_status = status_raw.upper()
            if "NEEDS REVIEW" in upper_status:
                status = "Needs review"
            elif upper_status == "OPEN":
                status = "Open"
            else:
                continue

            # The incident URL is unique per incident, so it is the safest de-duplication key
            item_key = href or f"{resident}-{title}-{status}-{date_str}"
            if item_key in seen_keys:
                continue
            seen_keys.add(item_key)

            incident_id = href.rstrip("/").rsplit("/", 1)[-1] if href else str(len(seen_keys))
            item = {
                "id": f"inc-{incident_id}",
                "resident": resident,
                "title": title or "Incident",
                "status": status,
                "date": date_str,
                "summary": desc.replace("\n", " ")[:300],
                "link": f"https://careoffice.logmycare.co.uk{href}" if href.startswith("/") else href
            }

            if status == "Needs review":
                needs_review.append(item)
            else:
                open_incidents.append(item)

        except Exception as e:
            print(f"[Incidents] Error parsing card: {e}")
            continue


async def wait_for_incident_list(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)


async def set_incident_page_size(page: Page, size: int = 50) -> None:
    """Switch the pagination size changer at the bottom from the default '10 / page' to '<size> / page'."""
    changer = page.locator(f"{INCIDENT_PAGINATION_SEL} .ant-pagination-options-size-changer").first
    if not await changer.count() or not await changer.is_visible():
        print("[Incidents] No page-size selector shown (results fit on one page).")
        return
    if clean_text(await changer.inner_text()).startswith(f"{size} "):
        return

    await changer.click()
    option = page.locator(f'.ant-select-dropdown:visible .ant-select-item-option[title="{size} / page"]').first
    await option.wait_for(state="visible", timeout=5000)
    await option.click()
    await wait_for_incident_list(page)
    print(f"[Incidents] Page size set to {size} / page.")


async def go_to_next_incident_page(page: Page, current_page_no: int) -> bool:
    """Click 'Next' in the pagination bar. Returns False when there is no further page."""
    pagination = page.locator(INCIDENT_PAGINATION_SEL).first
    if not await pagination.count():
        return False
    next_btn = pagination.locator("li.ant-pagination-next").first
    if not await next_btn.count() or "ant-pagination-disabled" in (await next_btn.get_attribute("class") or ""):
        return False

    first_link = page.locator(INCIDENT_ITEM_SEL).first
    first_href = await first_link.get_attribute("href") if await first_link.count() else None

    await next_btn.click()
    await pagination.locator(
        f'li.ant-pagination-item-active[title="{current_page_no + 1}"]'
    ).wait_for(state="visible", timeout=15000)

    # Wait until the list has actually re-rendered with the next page's rows
    for _ in range(40):
        if await first_link.count() and await first_link.get_attribute("href") != first_href:
            break
        await page.wait_for_timeout(250)
    await wait_for_incident_list(page)
    return True


# ==============================================================================
# PHASE 2: SCRAPE SUPPORT PLANS (Overdue only)
# ==============================================================================
JS_OVERDUE_PLAN_LINES = r"""
(row) => {
  // Each plan line is a <div> holding "• Plan name" text plus a red <span>"Overdue +N days"</span>
  const parent = row.querySelector('.lmc-list-item-parent-link');
  if (!parent) return [];
  const out = [];
  for (const line of parent.querySelectorAll(':scope > div > div')) {
    let name = '';
    for (const n of line.childNodes) if (n.nodeType === 3) name += n.textContent;
    const span = line.querySelector('span');
    out.push({ name: name.replace(/^[\s•]+/, '').trim(), overdue: span ? span.textContent.trim() : '' });
  }
  return out;
}
"""


async def scrape_support_plans(page: Page) -> list[dict]:
    """
    Reads ONLY the 'Overdue' section of the Support Plans report ('Today' and
    'Next 7 Days' are ignored). Returns one entry per resident with the list of
    their overdue plans and how long each is overdue.
    """
    print("\n--- [Phase 2/4] Scraping Support Plans (Overdue only) ---")
    residents: list[dict] = []

    try:
        await page.goto(SUPPORT_PLANS_URL, wait_until="domcontentloaded", timeout=30000)
        overdue_h2 = page.locator("h2").filter(has_text=re.compile(r"^\s*Overdue\s*$")).first
        await overdue_h2.wait_for(state="visible", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        # The section = nearest ancestor of the heading that also contains the collapsible body
        section = overdue_h2.locator("xpath=ancestor::div[.//div[contains(@class,'rah-')]][1]")

        # Expand the section if it is collapsed
        body = section.locator("div[class*='rah-']").first
        if await body.count() and "height-zero" in (await body.get_attribute("class") or ""):
            await section.locator(".toggle-section-open").first.click()
            await page.wait_for_timeout(800)

        rows = await section.locator(".lmc-list-item").all()
        print(f"[Support Plans] Overdue section has {len(rows)} resident row(s).")

        for idx, row in enumerate(rows):
            try:
                name_loc = row.locator(".lmc-list-item-link").first
                resident = clean_text(await name_loc.inner_text()) if await name_loc.count() else ""
                if not resident:
                    continue

                plans = []
                for p in await row.evaluate(JS_OVERDUE_PLAN_LINES):
                    if not p["name"] or not is_explicitly_overdue(p["overdue"]):
                        continue
                    m = re.search(r"(\d+)\s*day", p["overdue"], re.I)
                    days = int(m.group(1)) if m else None
                    plans.append({
                        "name": clean_text(p["name"]),
                        "overdue_days": days,
                        "overdue_text": f"+{days} day{'s' if days != 1 else ''}" if days is not None else "Overdue",
                    })

                if not plans:
                    continue

                plans.sort(key=lambda x: -(x["overdue_days"] or 0))
                residents.append({
                    "id": f"sp-{idx + 1}",
                    "resident": resident,
                    "initials": initials_for(resident),
                    "count": len(plans),
                    "max_overdue_days": max((x["overdue_days"] or 0) for x in plans),
                    "plans": plans,
                })
            except Exception as e:
                print(f"[Support Plans] Row {idx + 1} skipped: {e}")

        residents.sort(key=lambda r: (-r["max_overdue_days"], -r["count"]))
        total = sum(r["count"] for r in residents)
        print(f"[Support Plans] {total} overdue plan(s) across {len(residents)} resident(s).")

    except Exception as e:
        print(f"[Support Plans] ERROR scraping support plans: {e}")

    return residents


# ==============================================================================
# PHASE 3: SCRAPE GOALS (Overdue)
# ==============================================================================
GOALS_OVERDUE_URL = GOALS_URL + "?reviewStatuses%5B0%5D=overdue"  # same URL LMC sets when picking Review status = Overdue
GOAL_SECTION_SEL = '[data-testid="goals-management-goal-reports-section"]'
GOAL_ROW_SEL = '[data-testid^="goals-management-row-"][data-testid$="-goal-report-row"]'


async def goals_overdue_filter_active(page: Page) -> bool:
    selected = page.locator('[data-testid="goals-management-goal-selected-filters"]').first
    try:
        await selected.wait_for(state="visible", timeout=15000)
    except Exception:
        return False
    return bool(re.search(r"Review status\s*-\s*Overdue", clean_text(await selected.inner_text()), re.I))


async def apply_goals_overdue_filter_by_click(page: Page) -> None:
    """Fallback: open the visible 'Review status' select and pick 'Overdue'."""
    for sel in await page.locator('[data-testid="goals-management-goal-filters-review-status"]').all():
        if await sel.is_visible():
            await sel.locator(".ant-select-selector").first.click(force=True)
            break
    option = page.locator('.ant-select-dropdown:visible .ant-select-item-option[title="Overdue"]').first
    await option.wait_for(state="visible", timeout=5000)
    if "ant-select-item-option-selected" not in (await option.get_attribute("class") or ""):
        await option.click()
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(2000)


async def scrape_goals(page: Page) -> list[dict] | None:
    """
    Opens Goals Management with Review status = Overdue, expands every resident
    that appears and records each listed goal. Returns one entry per resident.
    Returns None (instead of a misleading empty list) if the Overdue filter
    could not be confirmed, because then the list would contain ALL goals.
    """
    print("\n--- [Phase 3/4] Scraping Goals Management (Review status = Overdue) ---")
    residents: list[dict] = []

    try:
        await page.goto(GOALS_OVERDUE_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        if not await goals_overdue_filter_active(page):
            print("[Goals] Overdue filter not active via URL - selecting it from the dropdown...")
            await page.goto(GOALS_URL, wait_until="domcontentloaded", timeout=30000)
            await page.locator('[data-testid="goals-management-goal-filters-review-status"]').first.wait_for(timeout=20000)
            await apply_goals_overdue_filter_by_click(page)
            if not await goals_overdue_filter_active(page):
                print("[Goals] ERROR: could not confirm the Overdue filter - keeping previous goals data.")
                return None
        print("[Goals] Filter confirmed: Review status - Overdue.")

        # Wait for either resident sections or the "no data" empty state to render
        sections_loc = page.locator(GOAL_SECTION_SEL)
        empty_loc = page.get_by_text("no data to show", exact=False)
        for _ in range(40):
            if await sections_loc.count() or await empty_loc.count():
                break
            await page.wait_for_timeout(250)
        await page.wait_for_timeout(800)

        sections = await sections_loc.all()
        print(f"[Goals] {len(sections)} resident(s) with overdue goals.")

        for idx, section in enumerate(sections):
            try:
                name_loc = section.locator("h5[class*='ResidentName']").first
                resident = clean_text(await name_loc.inner_text()) if await name_loc.count() else ""
                if not resident:
                    continue

                # Expand the resident's dropdown so the goals are actually shown
                body = section.locator("div[class*='rah-']").first
                if await body.count() and "height-zero" in (await body.get_attribute("class") or ""):
                    await section.locator('[data-testid="goals-management-goal-reports-section-header"]').first.click()
                    await page.wait_for_timeout(700)

                goals = []
                for row in await section.locator(GOAL_ROW_SEL).all():
                    title_loc = row.locator("[class*='GoalTitle']").first
                    title = clean_text(await title_loc.text_content()) if await title_loc.count() else ""
                    if not title:
                        continue
                    sub_loc = row.locator("[class*='GoalSubtitle']").first
                    prog_loc = row.locator("[class*='GoalProgress__SplitText']").first

                    # With a review filter active, each goal shows its review due status
                    # (e.g. "Overdue", "Due this week") next to the goal status tag ("In Progress").
                    due_loc = row.locator('[data-testid$="-goal-report-row-due-date"]').first
                    review_status = clean_text(await due_loc.text_content()) if await due_loc.count() else ""
                    if review_status and not is_explicitly_overdue(review_status):
                        continue  # goal is listed, but its own review is not overdue

                    tag_loc = row.locator('[data-testid$="-goal-report-row-status"] .ant-tag').first
                    goals.append({
                        "title": title[:160],
                        "progress": clean_text(await prog_loc.text_content()) if await prog_loc.count() else "",
                        "last_reviewed": clean_text(await sub_loc.text_content()) if await sub_loc.count() else "",
                        "review_status": review_status or "Overdue",
                        "goal_status": clean_text(await tag_loc.text_content()) if await tag_loc.count() else "",
                    })

                if goals:
                    residents.append({
                        "id": f"gl-{idx + 1}",
                        "resident": resident,
                        "initials": initials_for(resident),
                        "count": len(goals),
                        "goals": goals,
                    })
            except Exception as e:
                print(f"[Goals] Resident section {idx + 1} skipped: {e}")

        total = sum(r["count"] for r in residents)
        print(f"[Goals] {total} overdue goal(s) across {len(residents)} resident(s).")

    except Exception as e:
        print(f"[Goals] ERROR scraping goals: {e}")
        return None

    return residents


# ==============================================================================
# PHASE 4: SCRAPE FUTURE PLANS (Overdue)
# ==============================================================================
FUTURE_PLANS_URL = "https://careoffice.logmycare.co.uk/residents/{id}/future-plans"
PLAN_ITEM_SEL = '[data-testid^="contingency-plan-item-"]'


def days_since(date_str: str) -> int | None:
    """'10-10-2026' -> number of whole days since that date (positive = in the past)."""
    try:
        return (datetime.now().date() - datetime.strptime(date_str, "%d-%m-%Y").date()).days
    except ValueError:
        return None


async def read_resident_future_plans(page: Page, resident: dict) -> list[dict]:
    """Open one resident's Future Plans page and return the plans tagged OVERDUE."""
    await page.goto(FUTURE_PLANS_URL.format(id=resident["id"]), wait_until="domcontentloaded", timeout=30000)

    # The page shows either plan cards or the "No Contingency Plans" empty state
    await page.locator(PLAN_ITEM_SEL).or_(page.get_by_text("No Contingency Plans", exact=False)).first.wait_for(
        state="visible", timeout=20000
    )
    await page.wait_for_timeout(300)

    overdue = []
    for card in await page.locator(PLAN_ITEM_SEL).all():
        tags = " ".join([clean_text(await t.text_content()) for t in await card.locator(".ant-tag").all()])
        if not is_explicitly_overdue(tags):
            continue

        title_loc = card.locator("[class*='PlanTitle']").first
        sub_loc = card.locator("[class*='PlanSubtitle']").first
        title = clean_text(await title_loc.text_content()) if await title_loc.count() else "Future Plan"
        subtitle = clean_text(await sub_loc.text_content()) if await sub_loc.count() else ""

        # Subtitle: "Reviewed 10-09-2026 • Admin Support • Next review 10-10-2026"
        next_m = re.search(r"Next review\s+(\d{2}-\d{2}-\d{4})", subtitle, re.I)
        last_m = re.search(r"Reviewed\s+(\d{2}-\d{2}-\d{4})", subtitle, re.I)
        next_review = next_m.group(1) if next_m else ""
        days = days_since(next_review) if next_review else None

        overdue.append({
            "title": title,
            "next_review": next_review,
            "last_reviewed": last_m.group(1) if last_m else "",
            "overdue_days": days,
            "overdue_text": f"+{days} day{'s' if days != 1 else ''}" if days and days > 0 else "Overdue",
        })
    return overdue


async def scrape_future_plans(page: Page) -> list[dict] | None:
    """
    Visits each resident's Future Plans page directly by ID (from residents.json)
    and records every plan carrying the red OVERDUE tag. Returns one entry per
    resident. Returns None if most pages failed, so previous data is kept.
    """
    print("\n--- [Phase 4/4] Scraping Future Plans ---")
    residents_out: list[dict] = []

    try:
        residents = load_residents()
    except Exception as e:
        print(f"[Future Plans] ERROR: cannot read {RESIDENTS_FILE}: {e}")
        return None

    print(f"[Future Plans] Checking {len(residents)} resident(s) from residents.json...")
    failed: list[str] = []

    for resident in residents:
        plans = None
        for attempt in (1, 2):  # one retry for slow page loads
            try:
                plans = await read_resident_future_plans(page, resident)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"[Future Plans] {resident['name']}: page did not load ({e.__class__.__name__}).")
        if plans is None:
            failed.append(resident["name"])
            continue

        if plans:
            plans.sort(key=lambda x: -(x["overdue_days"] or 0))
            print(f"[Future Plans] {resident['name']}: {len(plans)} overdue.")
            residents_out.append({
                "id": f"fp-{resident['id']}",
                "resident": resident["name"],
                "initials": initials_for(resident["name"]),
                "count": len(plans),
                "max_overdue_days": max((p["overdue_days"] or 0) for p in plans),
                "link": FUTURE_PLANS_URL.format(id=resident["id"]),
                "plans": plans,
            })

    if failed:
        print(f"[Future Plans] WARNING: {len(failed)} resident page(s) could not be checked: {', '.join(failed)}")
    if residents and len(failed) > len(residents) // 2:
        print("[Future Plans] ERROR: most pages failed - keeping previous future plans data.")
        return None

    residents_out.sort(key=lambda r: (-r["max_overdue_days"], -r["count"]))
    total = sum(r["count"] for r in residents_out)
    print(f"[Future Plans] {total} overdue future plan(s) across {len(residents_out)} resident(s).")
    return residents_out


# ==============================================================================
# ATOMIC SAVE & MERGE
# ==============================================================================
def save_dashboard_data(
    needs_review: list[dict],
    open_incidents: list[dict],
    support_plans: list[dict],
    goals: list[dict] | None,
    future_plans: list[dict] | None
) -> None:
    # Live extracted data is authoritative.
    # Empty lists [] mean 0 items are overdue and must be saved as 0, not replaced with stale mock data.
    # None means the phase could not run reliably, so the previously saved data is kept.
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            previous = json.load(f)
    except Exception:
        previous = {}
    if goals is None:
        goals = previous.get("goals_overdue", [])
    if future_plans is None:
        future_plans = previous.get("future_plans_overdue", [])

    try:
        active_residents = len(load_residents())
    except Exception:
        active_residents = previous.get("stats", {}).get("total_active_residents", 0)

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_active_residents": active_residents,
            "incidents_needs_review": len(needs_review),
            "incidents_open": len(open_incidents),
            # support_plans holds one entry per resident; count the individual overdue plans
            "support_plans_overdue": sum(r.get("count", 0) for r in support_plans),
            "support_plans_residents": len(support_plans),
            # goals holds one entry per resident; count the individual overdue goals
            "goals_overdue": sum(r.get("count", 1) for r in goals),
            "goals_residents": len(goals),
            # future_plans holds one entry per resident; count the individual overdue plans
            "future_plans_overdue": sum(r.get("count", 1) for r in future_plans),
            "future_plans_residents": len(future_plans)
        },
        "incidents_needs_review": needs_review,
        "incidents_open": open_incidents,
        "support_plans_overdue": support_plans,
        "goals_overdue": goals,
        "future_plans_overdue": future_plans
    }

    # Attach the responsible staff member's NAME to every item (emails stay in the backend only)
    StaffDirectory.load().attach_staff_names(output)

    temp_file = f"{DATA_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    os.replace(temp_file, DATA_FILE)
    print(f"\n[Dashboard Data] Saved successfully to {DATA_FILE} at {output['last_updated']}")



# ==============================================================================
# MAIN CYCLE RUNNER
# ==============================================================================
async def run_cycle(email: str, password: str, headless: bool = True) -> bool:
    """Run one full scrape. Returns False if login failed (data.json is left untouched)."""
    print(f"\n{'='*70}\n[Scraper Cycle] Starting at {datetime.now().isoformat()}\n{'='*70}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            ok = await login(page, email, password)
            if not ok:
                print("[Scraper Cycle] Login failed (check email/password). Preserving current dashboard data.")
                return False

            needs_review, open_inc = await scrape_incidents(page)
            support_plans = await scrape_support_plans(page)
            goals = await scrape_goals(page)
            future_plans = await scrape_future_plans(page)

            save_dashboard_data(needs_review, open_inc, support_plans, goals, future_plans)

        finally:
            await context.close()
            await browser.close()
    print(f"[Scraper Cycle] Completed successfully.\n{'='*70}")
    return True


async def main():
    parser = argparse.ArgumentParser(description="Log My Care Live Dashboard Scraper")
    parser.add_argument("--loop", action="store_true", help="Run indefinitely every N seconds")
    parser.add_argument("--interval", type=int, default=600, help="Interval in seconds for loop mode (default: 600s / 10m)")
    parser.add_argument("--head", action="store_true", help="Run browser in visible mode (default: headless)")
    args = parser.parse_args()

    headless = not args.head
    load_env()  # local secrets from .env (GitHub Actions uses repository secrets instead)
    email, password = get_credentials()  # asked once if not in .env, reused for every loop cycle

    if args.loop:
        print(f"[Runner] Starting loop mode every {args.interval} seconds (headless={headless})...")
        while True:
            try:
                await run_cycle(email, password, headless=headless)
            except Exception as e:
                print(f"[Runner] Error during cycle: {e}")
            print(f"[Runner] Waiting {args.interval}s until next scrape cycle...")
            await asyncio.sleep(args.interval)
    else:
        # Non-zero exit on login failure so GitHub Actions stops before deploying
        if not await run_cycle(email, password, headless=headless):
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
