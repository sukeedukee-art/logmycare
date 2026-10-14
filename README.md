# CareLink Live Monitor

A live dashboard for Log My Care. It shows:

| Section | Source in Log My Care |
|---|---|
| Incidents: Needs review / Open | Reports > Incidents list (filtered, every page at 50 per page) |
| Overdue support plans | Reports > Support Plans, **Overdue** section only |
| Overdue goals | Reports > Goals Management, Review status = **Overdue** |
| Overdue future plans | Each resident's Future Plans page (cards tagged **OVERDUE**) |

Every card shows the resident's **key worker**, and the details popup has an **Email** button that emails that key worker about the item.

| File | Purpose |
|---|---|
| `scraper.py` | Logs in to Log My Care and writes `data.json` |
| `directory.py` | Resident list + key worker lookup (from `residents.json` or a GitHub secret) |
| `server.py` | Local web server: dashboard, "Refresh Now" scraping, email sending |
| `mailer.py` | Builds and sends the key worker emails over SMTP |
| `index.html`, `app.js`, `style.css` | The dashboard page |
| `cartoons.js` | Animated background characters |

---

## Run it locally

```powershell
pip install -r requirements.txt
py -m playwright install chromium

py server.py
```

**Logins and passwords** live in a local `.env` file, never in the code:

1. Copy `.env.example` to `.env` and fill in the values:
   - `LMC_EMAIL` / `LMC_PASSWORD`: your Log My Care login
   - `SMTP_USER` / `SMTP_PASSWORD`: the mailbox the Email button sends from, and its Google App Password
2. Anything you leave empty is asked for in the terminal when the dashboard starts. Press Enter at the email prompt to run without email.

How `.env` is protected:

- It is in `.gitignore`, so it is never pushed to GitHub. Only the blank `.env.example` is.
- `server.py` only serves the dashboard files (`index.html`, `app.js`, `style.css`, `cartoons.js`, `data.json`). Requests for `.env`, `residents.json` or any code file get "not found".
- On Windows, limit the file to your own account:
  ```powershell
  icacls .env /inheritance:r /grant:r "$env:USERDOMAIN\$env:USERNAME:(R,W)"
  ```
- If you think a password has leaked, change it at the source (Log My Care, or revoke the App Password in Google Account > Security > App passwords), then update `.env`.

Open **http://localhost:8080**. Click **Refresh Now** to scrape fresh data (takes about 3 minutes).

To scrape automatically every 10 minutes, run this in a second terminal (it asks for the login once):

```powershell
py scraper.py --loop --interval 600
```

Add `--head` to watch the browser while it works.

**Resident list:** `residents.json` lists every resident and their key worker:

```json
[
  {"id": "67f5212138a52b3e64daa2cd", "name": "Alan Jones", "staff_name": "Amina", "staff_email": "amina@fortix.co.uk"},
  {"id": "68d40625095681a5154ccb12", "name": "Amelia Louise", "staff_name": "Abubakar", "staff_email": "abubakar@fortix.co.uk"}
]
```

- `id` is the part of the resident's Log My Care URL after `/residents/` (used to check Future Plans).
- `staff_name` appears on the dashboard cards. `staff_email` is only used by the server to send emails. It never appears on the page or in `data.json`, and the server refuses to serve `residents.json` to browsers.

Edit this file when residents join or leave or key workers change.

### Email setup (Google Workspace)

fortix.co.uk mail runs on Google Workspace, so send through Google's SMTP server (the default, `smtp.gmail.com:587`):

1. Pick the mailbox the emails should come from, e.g. `dashboard@fortix.co.uk` or your own.
2. On that account, turn on **2-Step Verification**, then create an **App password** (Google Account > Security > App passwords). Your Workspace admin may need to allow app passwords.
3. Enter the mailbox and app password when `server.py` asks. It checks the login straight away.

How an email is sent:

- **From:** "CareLink Dashboard" <the mailbox above>. It is always the real, signed-in mailbox, so Google signs it and fortix.co.uk's SPF/DKIM checks pass. This is what keeps it out of spam.
- **To:** the resident's key worker (looked up on the server).
- **Reply-To**, and **Cc** if "Send me a copy" is ticked: the person who clicked Send, so replies go straight to them.
- **Subject:** clear and specific, e.g. `7 support plans overdue for review - Liam Grinyer`.
- **Body:** plain text and HTML versions with the item details, any note you added, and a link to the right Log My Care page.

The server only accepts a dashboard item ID, never a recipient address, so it cannot be used to email anyone else. It also allows at most 10 emails per computer every 10 minutes.

---

## Deploy on GitHub

This folder **is** the repository. Push the contents of `Dashboard/` as the repo root, so `.github/workflows/dashboard.yml` ends up at the top level.

### 1. Push

```powershell
cd Dashboard
git init
git add .
git commit -m "CareLink live dashboard"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

`.gitignore` keeps personal data out of the repository: `data.json`, `residents.json`, `Residents.md`.

### 2. Add the secrets

Go to **Settings > Secrets and variables > Actions > New repository secret** and add:

| Secret | Value |
|---|---|
| `LMC_EMAIL` | Log My Care login email |
| `LMC_PASSWORD` | Log My Care login password |
| `LMC_RESIDENTS_JSON` | The full contents of your local `residents.json` (including the staff fields). Update it whenever you change that file. |

### 3. Turn on Pages

Go to **Settings > Pages > Build and deployment > Source** and choose **GitHub Actions**.

### 4. Run it

Go to **Actions > CareLink Live Dashboard > Run workflow**. After that it runs every 10 minutes by itself. Each run:

1. logs in with the secrets,
2. scrapes all four sections,
3. publishes only the page files and the fresh `data.json` to GitHub Pages.

Scraped data is never committed to the repository. If the login fails, the run stops and the last good dashboard stays online.

GitHub Pages only hosts files, so there is no server behind the hosted page:

- **Refresh Now** reloads the latest published data. Live scraping on click only works with `server.py`.
- The **Email** button is shown but disabled, with a note. Sending email only works with `server.py`, because only the server holds the staff emails and the SMTP login.

### Things to know

- **Who can see it:** a GitHub Pages site is public on the internet, even when the repository is private (except on GitHub Enterprise Cloud with private Pages). Anyone with the link sees resident names, key worker names and incident details. Staff email addresses are never published.
- **Timing:** GitHub can run scheduled jobs a few minutes late, and it pauses schedules in repositories with no activity for 60 days. Re-enable from the Actions tab if that happens.
- **Minutes:** a run takes about 4-5 minutes (scrape + deploy). Every 10 minutes adds up to roughly 20,000 Actions minutes a month. That is free for public repositories, but well over the 2,000 free minutes for private repositories on the Free plan. Change the `cron` line in `.github/workflows/dashboard.yml` to run less often (for example `'*/30 * * * *'`).

---

## The cartoon crew

Big animated characters (`cartoons.js`, original artwork) live in the background behind the dashboard:

- **Marmalade** the tabby cat chases **Pip** the mouse across the bottom of the screen every minute or so. Pip always makes it home.
- **Pip** peeks out of his mouse hole (bottom right) to say hello. Click the hole for a status update.
- **Biscuit** the puppy naps in the bottom-left corner. He wakes up and barks the news after every data refresh. Click him to wake him early.

The **Hide cartoons** tab on the right edge turns them off (the browser remembers this). They switch off automatically for people who have "reduce motion" turned on.
