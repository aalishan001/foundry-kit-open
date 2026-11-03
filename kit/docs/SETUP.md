# Setup: about 20 minutes, once

## You need

- A Windows 11 computer and an internet connection.
- One of these two apps. Both use the same folder, so you can switch later without moving anything:
  - **OpenCode** with an **OpenRouter** key (pay as you go, about $1 a week; see the costs below). Setup installs
    OpenCode for you.
  - **Claude Code**: the Claude desktop app's **Code** tab, with a Claude Pro (or higher) plan.

## 1. Put the folder somewhere safe

1. Make a folder inside **OneDrive** or **Google Drive**, for example `OneDrive\Job Search`. Everything in it is then
   backed up automatically.
2. Extract the kit into that folder (right-click the zip → **Extract All**, or copy the `kit` folder from the
   repository).

## 2. If you'll use OpenCode: an OpenRouter key with the privacy settings on

Skip this if you'll use Claude Code, or if someone gave you a key.

1. Make an account at openrouter.ai and add credit (Settings → **Credits**; $10 lasts most people a couple of months).
2. **Settings → Privacy. These two are not optional:**
   - switch **off** every option that allows providers which **may train on your data** (paid and free models);
   - switch **on** **Zero Data Retention** for every model group.
   The kit also asks for zero-data-retention, no-training providers on every request, but set the account too.
3. Settings → **API Keys** → **Create key**. Give it a credit limit (for example $10) so a mistake can never cost more.
   Copy the key; you'll paste it once during setup.
4. Optional: Settings → **Notifications** → a low-balance alert (for example at $3).

Free models are never used: the free endpoints log or train on what you send, and your profile, pay and resume go
with every request.

## 3. Run the setup

1. Open the folder and double-click **setup.cmd**.
2. If Windows asks "Do you want to allow this app to make changes?", choose **Yes**. Setup installs Python, Git,
   OpenCode and four small helper packages, for your user account only.
3. It asks two questions:
   - **Read the careers sites and job alerts every morning at 08:30 by itself?** Press Enter for yes. If the computer
     is off or asleep at 08:30, it runs as soon as it's back on.
   - **Use OpenCode with an OpenRouter key?** Press Enter for yes, then paste the key when asked (typing stays
     hidden). It's kept in Windows Credential Manager, never in a file. Answer **n** if you'll only use Claude Code.
4. Wait until it prints **Done**. Each line says OK, INSTALLED or ACTION NEEDED. If a line says ACTION NEEDED, do what
   it says (often "restart the computer"), then double-click setup.cmd again. Running it twice is safe.

## 4. Before the first session: your master resume

Put **one long master resume or career brain dump** in the folder's **inbox**: everything you've ever done, with no
page limit. The kit never invents anything, so it can only use what you give it. `MASTER_RESUME.md` (in this
folder) has the checklist of what to include, and why.

## 5. Open it and run /start

- **OpenCode:** double-click **Job search (OpenCode)** on your desktop. A window opens in this folder.
- **Claude Code:** open the Claude desktop app, choose the **Code** tab, and choose this folder.

Then type **/start**. It's an interview, one question at a time, and you can stop and type `/start` again any time:

1. **Your field.** Software engineering has its own pack (levels, role families, a starter company list, interview
   questions). For any other field, choose "any other field" and give the job titles you're after.
2. **Your documents.** It reads everything in `inbox` and drafts short facts about your work. You confirm, edit or
   delete each one. Only confirmed facts ever appear in a resume.
3. **The gaps.** Questions that pull out what resumes usually leave out: scale, numbers, decisions, incidents, tools.
   "I don't know" is a fine answer; a number you're unsure of is kept exactly as you said it.
4. **Who you are.** Name, email, phone, links, city.
5. **Your search rules**, each with its default said out loud:
   - your current title (mapped to a level) and pay;
   - never a lower level than yours (a fixed rule);
   - a same-level move only if the pay rise clears your threshold (20% unless you choose another), on total pay or
     fixed pay;
   - the role families or titles you want;
   - where: your home country first, preferred cities (a bonus, never a filter), places to avoid, and countries
     abroad in your order of preference. Abroad, only established companies, never a startup; at home, a company's
     stability is shown but never filters;
   - whether pay matters more than place, your notice period, and any deal-breakers.
6. **Resume format:** PDF, Word or both; page limit; which contacts to show.
7. **Gmail (optional):** paste alert emails, or let the kit read a label (below).

Then `/radar` shows the companies you follow, and `/sweep` finds roles.

## 6. Job alerts, so you never have to go looking (optional, 20 minutes once)

1. Type `/radar recipes`. It makes **Job alerts setup.html** in this folder; double-click it.
2. Step 1 there imports a Gmail filter that puts every job alert under a **Job Alerts** label.
3. Then it lists the alerts to switch on at LinkedIn, Naukri, Indeed, foundit and iimjobs, and at the companies whose
   sites can't be read automatically. You set each one up yourself, signed in as usual; the kit never logs in
   anywhere, and never reads LinkedIn or Naukri pages.
4. To have the kit read the Job Alerts label every morning, double-click **Gmail setup.cmd**. It needs **2-Step
   Verification** on your Google account (Google only offers app passwords with it on), and walks you through making
   an app password. The kit only reads that one label; it never marks, moves or deletes anything. If you skip this,
   paste alert emails into `/sweep` instead.
5. Optional: **API keys.cmd** adds free keys for three job-search sites (Adzuna, Jooble, JSearch) that find roles
   posted elsewhere.

## What OpenCode costs

Measured on real runs (OpenRouter, zero-data-retention endpoints only; Claude Haiku 5.5 for most commands, Claude
Sonnet 5.5 for `/tailor` and `/prep`):

| Command | About |
|---|---|
| `/start` (once) | $0.19 with a short resume; more with a long master resume, still well under $1 |
| `/today`, `/radar`, `/help` | under $0.01 |
| `/update` | $0.01 |
| `/check` (one posting) | $0.01–$0.02 |
| `/grill` (a short mock interview) | $0.02–$0.03 |
| `/sweep` (ranking new roles) | $0.03 |
| `/applied` | $0.05 |
| `/prep` (one job's gaps) | $0.34 |
| `/tailor` (one pass: PDF, Word, notes and both fact checks) | $0.41; each revision round costs more |

The morning sweep uses no AI and costs nothing. A typical week (five sweeps and `/today`s, three checks, one tailored
resume, one prep, one mock interview, a few updates) comes to about **$1.04**, so **$10 lasts about 9 weeks**.

## If something goes wrong

- Type `/today` or `/help`. Most problems explain their own fix.
- Your files are never deleted, and every change to your profile and records is kept in history.
- Still stuck? Copy the message you see and send it to whoever set this up with you, or open an issue on the
  repository.
