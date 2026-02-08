# Agent CRM — Scenario Tests

End-to-end user stories as validation. Each scenario is a complete user journey.
Run these against a fresh database to validate the system works as expected.

---

## Scenario 1: First Contact → Deal → Win

**Story:** Meet someone at an event, track them through to a closed deal.

**Steps:**

1. **Add contact from event**
   ```
   Input: "Met Sarah Chen at the AI meetup. She's CTO at Replicate, interested in our API. Email is sarah@replicate.com"
   
   Expected actions:
   - Create contact: Sarah Chen, CTO, Replicate, sarah@replicate.com, source: AI meetup
   - Log interaction: meeting, "Met at AI meetup, interested in API"
   
   Validate:
   - crm find-contact "sarah" returns 1 result with correct fields
   - crm list-interactions --contact "sarah" shows 1 meeting
   ```

2. **Create deal**
   ```
   Input: "Create a $50K deal for Replicate API integration"
   
   Expected actions:
   - Create deal: "Replicate API Integration", $50,000, stage=lead, contact=Sarah Chen
   
   Validate:
   - crm list-deals shows 1 deal at $50K
   - crm pipeline shows $50K in lead stage
   ```

3. **Log follow-up call**
   ```
   Input: "Had a call with Sarah. Very positive - she has budget approved. Moving to proposal stage."
   
   Expected actions:
   - Log interaction: call, outbound, summary of conversation
   - Update deal stage: lead → qualified (or proposal based on interpretation)
   - Offer to create follow-up task
   
   Validate:
   - crm list-interactions --contact "sarah" shows 2 interactions
   - Deal stage updated
   ```

4. **Close the deal**
   ```
   Input: "Sarah signed the contract. Mark the deal as won."
   
   Expected behavior:
   - Agent asks for confirmation (>$10K threshold)
   
   Input: "yes"
   
   Expected actions:
   - Update deal stage: → won
   - Set closed_at timestamp
   
   Validate:
   - crm list-deals --stage won shows 1 deal
   - crm-report winloss shows $50K won
   ```

**Success criteria:** Full journey from contact to closed-won with audit trail.

---

## Scenario 2: Email Ingest

**Story:** Forward a sales email, have it parsed and logged.

**Steps:**

1. **Forward email content**
   ```
   Input: """
   From: alex@datastack.io
   Subject: Re: AI Consulting Inquiry
   Date: Feb 8, 2026
   
   Hi,
   
   Thanks for the call yesterday. We're definitely interested in moving forward 
   with the AI consulting engagement we discussed. Budget is around $30K for 
   the initial phase.
   
   Can you send over a proposal by end of week?
   
   Best,
   Alex Rivera
   Founder, DataStack
   """
   
   Expected actions:
   - Run through crm-ingest
   - Create contact: Alex Rivera, Founder, DataStack, alex@datastack.io
   - Log interaction: email, inbound
   - Detect deal signals: $30K, "proposal" stage hint
   - Create task: "Send proposal to Alex" due Friday
   
   Validate:
   - Contact exists with correct company/role
   - Interaction logged as email
   - Deal created or suggested at $30K
   ```

**Success criteria:** Unstructured email → structured CRM data with minimal manual input.

---

## Scenario 3: Pipeline Review

**Story:** Ask for pipeline status, get actionable summary.

**Setup:** Create 3-4 deals at different stages.

**Steps:**

1. **Query pipeline**
   ```
   Input: "What's my pipeline look like?"
   
   Expected output:
   - Deals grouped by stage with counts and values
   - Total pipeline value
   - Weighted pipeline value
   - Highlight any deals closing soon or needing attention
   ```

2. **Drill into specific stage**
   ```
   Input: "Show me deals in proposal stage"
   
   Expected output:
   - List of deals with contact, value, expected close
   ```

3. **Ask for forecast**
   ```
   Input: "What's closing this month?"
   
   Expected output:
   - Deals with expected_close in current month
   - Total value at risk
   ```

**Success criteria:** Natural language queries return useful, formatted pipeline data.

---

## Scenario 4: Task Management

**Story:** Create, track, and complete follow-up tasks.

**Steps:**

1. **Create task with natural date**
   ```
   Input: "Remind me to follow up with Sarah next Tuesday"
   
   Expected actions:
   - Create task: "Follow up with Sarah", due next Tuesday, linked to Sarah contact
   
   Validate:
   - crm list-tasks --pending shows task with correct due date
   ```

2. **Check overdue**
   ```
   Setup: Create task due yesterday
   Input: "What's overdue?"
   
   Expected output:
   - List of overdue tasks with days overdue
   ```

3. **Complete task**
   ```
   Input: "Done with the Sarah follow-up"
   
   Expected actions:
   - Mark task completed
   
   Validate:
   - Task has completed_at set
   - crm list-tasks --pending no longer shows it
   ```

**Success criteria:** Task lifecycle with natural language and date parsing.

---

## Scenario 5: Stale Contact Alert

**Story:** System proactively alerts about contacts going cold.

**Setup:** 
- Create contact with deal 15 days ago
- No interactions logged since

**Steps:**

1. **Run notify check**
   ```
   Command: crm-notify --stale-days 14
   
   Expected output:
   - Alert for stale contact with open deal
   - Suggests follow-up
   ```

2. **Agent acts on alert**
   ```
   Input: (agent receives alert in heartbeat)
   
   Expected behavior:
   - Agent messages user about stale contact
   - Offers to create follow-up task or draft email
   ```

**Success criteria:** Proactive alerting catches contacts before they go cold.

---

## Scenario 6: Confirmation Flow

**Story:** High-stakes actions require explicit confirmation.

**Steps:**

1. **Try to close large deal**
   ```
   Input: "Mark the $75K Acme deal as won"
   
   Expected behavior:
   - Agent does NOT immediately execute
   - Agent asks: "Confirm: Mark 'Acme Deal' ($75,000) as WON?"
   ```

2. **Confirm**
   ```
   Input: "yes"
   
   Expected actions:
   - Deal updated to won
   - Audit log shows confirmation
   ```

3. **Try to delete**
   ```
   Input: "Delete the old contact John Smith"
   
   Expected behavior:
   - Agent asks for confirmation before delete
   ```

**Success criteria:** No high-stakes action executes without explicit user confirmation.

---

## Scenario 7: Webhook Ingestion

**Story:** External form submission creates CRM contact.

**Steps:**

1. **Start webhook server**
   ```
   Command: crm-webhook --port 8901 &
   ```

2. **Submit form data**
   ```
   Command: curl -X POST http://localhost:8901/lead \
     -H "Content-Type: application/json" \
     -d '{"name": "Jordan Lee", "email": "jordan@startup.io", "company": "StartupCo", "message": "Interested in your services"}'
   
   Expected response:
   - 201 Created
   - Contact ID returned
   ```

3. **Verify in CRM**
   ```
   Command: crm find-contact "jordan"
   
   Expected:
   - Contact exists with all fields populated
   - Source: webhook
   ```

**Success criteria:** Zero-touch lead capture from external forms.

---

## Running Scenarios

### Fresh Database Test

```bash
# Reset database
rm ~/.local/share/agent-crm/crm.db
crm init

# Run through scenarios manually or via agent
```

### Automated Validation

```bash
# After each scenario, validate with queries:
crm stats                          # Overall counts
crm query "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10"  # Audit trail
```

---

## Satisfaction Criteria

Following the StrongDM "dark factories" approach:

| Scenario | Pass Condition |
|----------|---------------|
| 1. First Contact → Win | Full lifecycle, all entities linked, audit complete |
| 2. Email Ingest | Correct entity extraction, >80% accuracy on fields |
| 3. Pipeline Review | Accurate totals, useful formatting |
| 4. Task Management | Date parsing works, completion tracked |
| 5. Stale Alert | Alert fires within 1 day of threshold |
| 6. Confirmation | Never auto-executes high-stakes without confirm |
| 7. Webhook | Contact created with correct source |

**Overall pass:** 6/7 scenarios pass with no critical failures.
