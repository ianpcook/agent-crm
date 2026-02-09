# Agent CRM

A complete CRM with no UI—just natural language. Track contacts, deals, interactions, and tasks through conversation with your AI agent.

## Why?

Traditional CRMs have clunky interfaces and steep learning curves. Agent CRM replaces all of that with natural conversation:

```
You: "Met Sarah Chen at the AI meetup. She's CTO at Replicate, interested in our API."

Agent: Created:
  • Contact: Sarah Chen (CTO @ Replicate)
  • Interaction: Met at AI meetup, interested in API
  
  Want me to set a follow-up task?
```

Data lives in SQLite. Your AI agent is the interface. Every action is audited.

## Features

- **Contacts** — Add, search, update contacts with companies, roles, and notes
- **Deals** — Track opportunities through pipeline stages with values and close dates
- **Interactions** — Log calls, emails, meetings, and notes linked to contacts
- **Tasks** — Create follow-ups with due dates and priorities
- **Pipeline Reports** — Visual charts and analytics on your sales funnel
- **Daily Digest** — Summary of activity, upcoming tasks, stale contacts
- **Alerts** — Notifications for overdue tasks, stuck deals, contacts needing attention
- **Ingest** — Parse emails and meeting notes into structured CRM data
- **Export** — CSV/JSON export of all data
- **Backup/Restore** — Full database backup with point-in-time restore

## Installation

### Claude Desktop

**Option A — Download ZIP (easiest):**
1. [Download this repo as ZIP](https://github.com/ianpcook/agent-crm/archive/refs/heads/main.zip)
2. In Claude Desktop: **Settings → Capabilities → Skills → Add → Upload .zip**
3. Select the downloaded ZIP file

**Option B — Clone and add folder:**
```bash
git clone https://github.com/ianpcook/agent-crm.git
```
Then in Claude Desktop: **Settings → Projects → Add Folder** → select the `agent-crm` folder

### OpenClaw

```bash
clawhub install agent-crm
```

### Claude Code

```bash
cd ~/.claude/skills
git clone https://github.com/ianpcook/agent-crm.git
```

### Manual

```bash
git clone https://github.com/ianpcook/agent-crm.git
cd agent-crm
# Add scripts/ to your PATH or invoke directly
```

**Requirements:** Python 3.10+ (matplotlib auto-installs on first chart)

## Quick Start

Once installed, just talk to your agent:

```
"Add John Smith from Acme Corp, he's the VP of Engineering"
"Create a $50K deal for Acme - enterprise license"
"Log a call with John - discussed timeline, they need it by Q2"
"What's my pipeline look like?"
"Show me overdue tasks"
"Who haven't I talked to in a while?"
```

## Scripts

| Script | Purpose |
|--------|---------|
| `crm.py` | Core CRUD operations |
| `crm-ingest.py` | Parse unstructured text → structured CRM data |
| `crm-digest.py` | Daily digest and pipeline summary |
| `crm-notify.py` | Alerts for overdue tasks, stale contacts |
| `crm-report.py` | Pipeline analytics, win/loss analysis |
| `crm-chart.py` | Visual charts (pipeline, forecast, activity) |
| `crm-export.py` | Export to CSV/JSON |
| `crm-backup.py` | Backup and restore database |
| `crm-webhook.py` | HTTP server for form/lead ingestion |

## Data Location

- **Database:** `~/.local/share/agent-crm/crm.db`
- **Backups:** `~/.local/share/agent-crm/backups/`
- **Charts:** `~/.local/share/agent-crm/charts/`
- **Exports:** `~/.local/share/agent-crm/exports/`

## Documentation

See [SKILL.md](./SKILL.md) for complete documentation including:
- Full CLI reference for all commands
- Deal stages and interaction types
- Confirmation rules for high-stakes actions
- Heartbeat integration for proactive monitoring
- Example conversation flows

## License

MIT
