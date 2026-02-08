---
name: Agent CRM
description: >
  A complete CRM with no UI—just natural language. Track contacts, deals, interactions, 
  and tasks through conversation. Use when: (1) adding/finding contacts, (2) creating or 
  updating deals and pipeline, (3) logging calls/emails/meetings, (4) managing follow-up 
  tasks, (5) generating pipeline reports or charts, (6) parsing emails/notes into CRM data.
  Supports: pipeline tracking, deal stages, activity logging, task management, alerts for 
  stale contacts, visual charts, CSV/JSON export, database backup/restore.
version: 1.0.1
author: Tyrell
category: productivity
agents:
  - claude-code
  - openclaw
---

# Agent CRM

A CRM with no UI. Just you, a database, and natural language.

## Overview

The Agent CRM replaces traditional CRM software with a conversational interface. Data lives in SQLite; you are the interface. Every action is audited with conversation context.

## Scripts

| Script | Purpose |
|--------|---------|
| `crm` | Core CRUD operations |
| `crm-ingest` | Parse unstructured text → structured CRM actions |
| `crm-digest` | Generate daily digest / pipeline summary |
| `crm-notify` | Check for alerts (overdue tasks, stale contacts, closing deals) |
| `crm-webhook` | HTTP server for form/lead ingestion |
| `crm-report` | Pipeline analytics, activity reports, win/loss analysis |
| `crm-chart` | Generate visual charts (auto-bootstraps matplotlib) |
| `crm-export` | Export data to CSV/JSON |
| `crm-backup` | Backup/restore database |

---

## CLI: `crm`

All scripts are in the `scripts/` directory. The database auto-initializes on first use.

### Contacts

```bash
# Add a contact
crm add-contact "Sarah Chen" --email sarah@replicate.com --company Replicate --role CTO --source "AI meetup"

# Find contacts
crm find-contact "sarah"
crm find-contact "replicate"

# List contacts
crm list-contacts
crm list-contacts --recent

# Update contact
crm update-contact "Sarah Chen" --phone "415-555-1234" --notes "Interested in API integration"

# Delete (use with caution)
crm delete-contact <id> --reason "Duplicate entry"
```

### Deals

```bash
# Add a deal
crm add-deal "Replicate API License" --value 50000 --contact "Sarah Chen" --stage qualified --expected-close "next month"

# List deals
crm list-deals
crm list-deals --stage proposal

# Update deal
crm update-deal "Replicate" --stage negotiation --probability 70

# Pipeline summary
crm pipeline
```

### Interactions

```bash
# Log an interaction
crm log call "Discussed pricing, she'll review with team" --contact "Sarah Chen" --direction outbound

crm log email "Sent proposal PDF" --contact "Sarah" --direction outbound

crm log meeting "Demo of API features, very positive" --contact "Sarah" --date yesterday
```

### Tasks

```bash
# Add task
crm add-task "Follow up on proposal" --contact "Sarah Chen" --due "next tuesday" --priority high

# List tasks
crm list-tasks --pending
crm list-tasks --overdue

# Complete task
crm complete-task "Follow up on proposal"
```

### Queries

```bash
# Pipeline stats
crm stats

# Raw SQL (SELECT only)
crm query "SELECT name, company FROM contacts WHERE company LIKE '%tech%'"
```

## Confirmation Rules

**Always confirm before:**
- Creating/updating deals > $10,000
- Changing deal stage to `won` or `lost`
- Deleting any record
- Bulk updates (future)

**Example flow:**
```
User: "Mark the Replicate deal as won"
You: "Confirm: Mark 'Replicate API License' ($50,000) as WON? (yes/no)"
User: "yes"
You: [execute] "Done. Deal closed at $50K. 🎉"
```

## Audit Trail

Every write operation is logged to `audit_log` table with:
- What changed (old → new values)
- Why (use `--reason` flag)
- When

View audit history:
```bash
crm query "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10"
```

## Data Location

- **Database:** `~/.local/share/agent-crm/crm.db`
- **Schema:** `skills/agent-crm/schema.sql`

## Stages

Valid deal stages (in order):
1. `lead` — Initial contact
2. `qualified` — Confirmed interest/budget
3. `proposal` — Sent proposal/quote
4. `negotiation` — Active negotiation
5. `won` — Closed won ✅
6. `lost` — Closed lost ❌

## Interaction Types

- `email` — Email correspondence
- `call` — Phone/video call
- `meeting` — In-person or scheduled meeting
- `note` — Internal note (no contact involved)
- `linkedin` — LinkedIn message/interaction
- `text` — SMS/iMessage/WhatsApp

---

## CLI: `crm-ingest`

Parses unstructured text (emails, meeting notes, call summaries) and extracts structured data.

```bash
# From stdin
echo "Met Sarah Chen at the AI meetup. She's CTO at Replicate, interested in API." | crm-ingest

# From file
crm-ingest --file meeting-notes.txt

# Force type detection
crm-ingest --type email --file forwarded-email.txt
```

**Output:** JSON with extracted entities and suggested actions:
- Contact names, emails, phones, companies
- Interaction type and direction
- Deal signals (stage hints, positive/negative indicators)
- Monetary amounts
- Potential tasks
- Suggested CRM actions for your review

**Workflow:**
1. User pastes text or forwards email
2. Run `crm-ingest` to extract entities
3. Review the suggested actions
4. Execute the ones that make sense via `crm` commands

---

## CLI: `crm-digest`

Generates a daily summary of CRM activity.

```bash
# Human-readable digest
crm-digest

# JSON output
crm-digest --json

# Custom time range
crm-digest --lookback 7 --lookahead 14
```

**Includes:**
- Recent activity (new contacts, deals, interactions)
- Pipeline summary by stage
- Tasks due today / overdue
- Deals closing soon
- Contacts needing follow-up (14+ days inactive)
- Won deals this month

**For daily briefings:** Schedule via cron or include in morning heartbeat.

---

## Confirmation Flow

**ALWAYS confirm before:**

| Action | Threshold |
|--------|-----------|
| Create deal | value > $10,000 |
| Update deal | value > $10,000 |
| Change stage | → `won` or `lost` |
| Delete any record | Always |

**Flow pattern:**
```
User: "Mark the Replicate deal as won"

You: "⚠️ Confirm: Mark 'Replicate API License' ($50,000) as WON?
      This will close the deal and log the win.
      Reply 'yes' to confirm."

User: "yes"

You: [run: crm update-deal "Replicate" --stage won --reason "User confirmed close"]
     "Done. Deal closed at $50K. 🎉
      Want me to create a follow-up task for invoicing?"
```

**Never auto-execute high-stakes actions.** Even if the user sounds certain, confirm first.

---

## Tips

1. **Be conversational.** User says "I just talked to Sarah" → you log the interaction
2. **Infer intelligently.** "Add Mike from Acme" → create contact with company=Acme
3. **Create follow-ups.** After logging a call, offer to create a task
4. **Summarize.** "What's my pipeline?" → run `crm pipeline` and present nicely
5. **Link things.** Deals to contacts, tasks to deals, interactions to everything
6. **Use ingest for bulk.** User pastes meeting notes → run through `crm-ingest` → execute sensible actions
7. **Daily digest.** Run `crm-digest` during morning heartbeat if CRM has data
8. **Check alerts.** Run `crm-notify` during heartbeat to catch overdue items
9. **Proactive follow-ups.** When `crm-notify` shows stale contacts, suggest reaching out

---

## CLI: `crm-notify`

Checks for items needing attention. Run from heartbeat or on-demand.

```bash
# All alerts
crm-notify

# JSON output
crm-notify --json

# Specific alert types
crm-notify --type overdue_task
crm-notify --type stale_contact

# Custom thresholds
crm-notify --stale-days 7 --closing-days 14 --stuck-days 30
```

**Alert types:**
- `overdue_task` — Tasks past due date
- `task_due_today` — Tasks due today
- `deal_closing_soon` — Deals with expected close within N days
- `stale_contact` — Contacts with open deals but no interaction in N days
- `deal_stuck` — Deals unchanged for N days

**Heartbeat integration:** Add to HEARTBEAT.md check cycle.

---

## CLI: `crm-webhook`

HTTP server for ingesting leads from external forms (Typeform, Tally, etc).

```bash
# Start server
crm-webhook --port 8901

# Endpoints:
# POST /lead    — Create contact from form submission
# POST /contact — Alias for /lead
# GET  /health  — Health check
```

**Supported formats:**
- Typeform webhooks
- Tally webhooks
- Generic JSON with standard field names (name, email, phone, company)

**Example curl:**
```bash
curl -X POST http://localhost:8901/lead \
  -H "Content-Type: application/json" \
  -d '{"name": "Alex Rivera", "email": "alex@datastack.io", "company": "DataStack"}'
```

**Log file:** `~/.local/share/agent-crm/webhook.log`

---

## CLI: `crm-report`

Analytics and pipeline reports.

```bash
# Pipeline summary with forecast
crm-report pipeline

# Activity report (last 30 days)
crm-report activity --days 30

# Win/loss analysis
crm-report winloss --days 90

# JSON output
crm-report pipeline --json
```

**Pipeline report includes:**
- Deals by stage with weighted values
- Forecast by expected close month
- Top 10 deals by value

**Activity report includes:**
- Interactions by type
- Tasks created vs completed
- Deal stage movements

**Win/loss report includes:**
- Win rate percentage
- Average deal value (won vs lost)
- Average sales cycle length

---

---

## CLI: `crm-chart`

Generate visual charts from CRM data. Auto-bootstraps its own venv with matplotlib on first run.

```bash
crm-chart pipeline    # Deal value by stage
crm-chart forecast    # Expected closes by month
crm-chart activity    # Interactions over time
crm-chart winloss     # Won vs lost by month
crm-chart summary     # Full dashboard
```

**Options:**
```bash
crm-chart forecast --months 6     # Forecast range
crm-chart activity --days 30      # Activity lookback
crm-chart pipeline --output /tmp/chart.png  # Custom output
```

**Output:** JSON with path to PNG:
```json
{"status": "success", "chart": "pipeline", "path": "/Users/.../.local/share/agent-crm/charts/pipeline_20260208.png"}
```

**Sending to user:** Run the chart, then use `message` tool with `filePath` to send the PNG.

**Example flow:**
```
User: "Show me the pipeline"
You: [run crm-chart pipeline]
     [send image via message tool with filePath]
```

---

## CLI: `crm-export`

Export CRM data to CSV or JSON.

```bash
crm-export contacts              # Export contacts (JSON)
crm-export deals --format csv    # Export deals (CSV)
crm-export all                   # Full database export
crm-export tasks --output /tmp   # Custom output dir
```

**Export types:** `contacts`, `deals`, `interactions`, `tasks`, `all`

**Output:** Files saved to `~/.local/share/agent-crm/exports/`

---

## CLI: `crm-backup`

Database backup and restore.

```bash
# Create backup
crm-backup backup
crm-backup backup --note "Before big import"

# List backups
crm-backup list

# Restore (requires --confirm)
crm-backup restore                     # Restore latest
crm-backup restore /path/to/backup.db --confirm

# Prune old backups
crm-backup prune --keep 5
```

**Safety:** Restore always creates a safety backup first.

**Output:** Backups saved to `~/.local/share/agent-crm/backups/`

---

## Heartbeat Integration

For proactive CRM monitoring, add to `HEARTBEAT.md`:

```markdown
## CRM Check (every 4 hours)

If 4+ hours since last CRM check:

1. Run `crm-notify` to check for alerts
2. If high-priority alerts exist, message Tyrell
3. Update `lastCrmCheck` in `memory/heartbeat-state.json`
```

---

## Example Conversation

```
User: Met Alex Rivera at the startup mixer. She's founder of DataStack, 
      looking for AI consulting. Could be a $30K engagement.

You: Created:
  • Contact: Alex Rivera (Founder @ DataStack)
    Source: startup mixer
  • Deal: "DataStack AI Consulting" — $30,000 (lead stage)
  • Interaction: Met at startup mixer, interested in AI consulting
  
  Want me to set a follow-up task?

User: Yeah, email her next week

You: Task created: "Email Alex Rivera" due Feb 15 (next Saturday)
```
