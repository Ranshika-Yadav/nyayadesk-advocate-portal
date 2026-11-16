# NyayaDesk — Premium Brown Full-Stack Advocate Portal

A self-hosted, responsive case-management application for demonstration and local evaluation. Built with a vanilla JavaScript frontend and a Python standard-library backend with SQLite. No `npm install` required.

## Start

Requires Python 3.10+.

```bash
cd nyayadesk-fullstack
python server.py
```

Open **http://localhost:8080** (do not open `index.html` directly). Create an account using an email address and password of at least 10 characters. Your local SQLite database and uploaded files will be created in `data/` automatically. Set `PORT=8081` to change the port.

## Features

- Brown/ivory dashboard, mobile navigation, case register, case details, hearing history and legal provisions
- Advocate account registration and login, password hashing (PBKDF2), HttpOnly session cookies
- Persistent SQLite case records, clients and reminders
- Upload/download/delete case documents (PDF, Word, text, common images; 10 MB limit)
- Hearing calendar and upcoming hearing listings
- Daily chamber cause list, with print action and explicit non-official-data label
- Case-aware legal research assistant: generic fallback or optional live model integration
- CSV case export, responsive tables, search and filters

## Optional AI integration

Set `OPENAI_API_KEY` in your server environment, then restart. The backend calls the Responses API. You may override the model using `OPENAI_MODEL`. Without a key, the assistant clearly labels itself demo mode and returns generic preparation checklists, not actual legal analysis.

## Important limitations before production

This is a **local/self-hosted demonstration**, not a production-hardened system. Case records are seeded with fictional examples. It has no eCourts or official cause-list feed, no email/SMS delivery service, no background scheduler for reminders, no audit logs, no MFA, no CSRF protection, no rate limiting, no encrypted-at-rest document storage, no external session persistence, and no backup/restore automation. Use only test or fictional data. Before exposing it to the internet or entering confidential client information, add TLS, secure-cookie deployment settings, persistent server-side sessions, CSRF protection, access/audit controls, data encryption, backups, abuse protection, and professional security review. The document section in the original case detail tab still records filenames only; use the dedicated Documents page for actual backend file storage. Verify all legal authorities, court orders, hearings and procedural guidance independently.
