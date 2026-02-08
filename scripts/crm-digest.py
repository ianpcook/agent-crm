#!/usr/bin/env python3
"""
CRM Daily Digest - Summary of CRM activity and upcoming items

Generates a daily briefing with:
- Yesterday's activity
- Pipeline summary  
- Tasks due today/overdue
- Contacts needing follow-up
- Deals closing soon
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))

def get_db() -> sqlite3.Connection:
    """Get database connection."""
    if not Path(DB_PATH).exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_digest(lookback_days: int = 1, lookahead_days: int = 7) -> dict:
    """Generate the daily digest."""
    conn = get_db()
    if not conn:
        return {'error': 'Database not found', 'path': DB_PATH}
    
    now = datetime.now()
    yesterday = (now - timedelta(days=lookback_days)).isoformat()
    week_ahead = (now + timedelta(days=lookahead_days)).isoformat()
    today_start = now.replace(hour=0, minute=0, second=0).isoformat()
    today_end = now.replace(hour=23, minute=59, second=59).isoformat()
    
    digest = {
        'generated_at': now.isoformat(),
        'period': {
            'lookback_days': lookback_days,
            'lookahead_days': lookahead_days
        }
    }
    
    # Recent activity
    activity = {}
    
    # New contacts
    rows = conn.execute("""
        SELECT COUNT(*) as count FROM contacts WHERE created_at >= ?
    """, (yesterday,)).fetchone()
    activity['new_contacts'] = rows['count']
    
    # New deals
    rows = conn.execute("""
        SELECT COUNT(*) as count, SUM(value) as total_value 
        FROM deals WHERE created_at >= ?
    """, (yesterday,)).fetchone()
    activity['new_deals'] = rows['count']
    activity['new_deal_value'] = rows['total_value'] or 0
    
    # Interactions logged
    rows = conn.execute("""
        SELECT type, COUNT(*) as count FROM interactions 
        WHERE logged_at >= ?
        GROUP BY type
    """, (yesterday,)).fetchall()
    activity['interactions'] = {r['type']: r['count'] for r in rows}
    activity['total_interactions'] = sum(r['count'] for r in rows)
    
    # Tasks completed
    rows = conn.execute("""
        SELECT COUNT(*) as count FROM tasks WHERE completed_at >= ?
    """, (yesterday,)).fetchone()
    activity['tasks_completed'] = rows['count']
    
    # Deal stage changes
    rows = conn.execute("""
        SELECT new_values, old_values FROM audit_log 
        WHERE table_name = 'deals' AND action = 'UPDATE' AND created_at >= ?
    """, (yesterday,)).fetchall()
    stage_changes = []
    for r in rows:
        try:
            old = json.loads(r['old_values']) if r['old_values'] else {}
            new = json.loads(r['new_values']) if r['new_values'] else {}
            if 'stage' in new and old.get('stage') != new.get('stage'):
                stage_changes.append({'from': old.get('stage'), 'to': new['stage']})
        except:
            pass
    activity['deal_stage_changes'] = stage_changes
    
    digest['recent_activity'] = activity
    
    # Pipeline summary
    rows = conn.execute("""
        SELECT stage, COUNT(*) as count, SUM(value) as total_value
        FROM deals WHERE stage NOT IN ('won', 'lost')
        GROUP BY stage
        ORDER BY CASE stage 
            WHEN 'lead' THEN 1
            WHEN 'qualified' THEN 2
            WHEN 'proposal' THEN 3
            WHEN 'negotiation' THEN 4
        END
    """).fetchall()
    
    pipeline = {
        'stages': [dict(r) for r in rows],
        'total_deals': sum(r['count'] for r in rows),
        'total_value': sum(r['total_value'] or 0 for r in rows)
    }
    
    # Weighted pipeline
    weighted = conn.execute("""
        SELECT SUM(value * COALESCE(probability, 50) / 100.0) as weighted
        FROM deals WHERE stage NOT IN ('won', 'lost')
    """).fetchone()
    pipeline['weighted_value'] = weighted['weighted'] or 0
    
    digest['pipeline'] = pipeline
    
    # Tasks due today
    rows = conn.execute("""
        SELECT t.*, c.name as contact_name FROM tasks t
        LEFT JOIN contacts c ON t.contact_id = c.id
        WHERE t.completed_at IS NULL 
        AND t.due_at >= ? AND t.due_at <= ?
        ORDER BY t.priority DESC, t.due_at ASC
    """, (today_start, today_end)).fetchall()
    digest['tasks_due_today'] = [dict(r) for r in rows]
    
    # Overdue tasks
    rows = conn.execute("""
        SELECT t.*, c.name as contact_name FROM tasks t
        LEFT JOIN contacts c ON t.contact_id = c.id
        WHERE t.completed_at IS NULL AND t.due_at < ?
        ORDER BY t.due_at ASC
        LIMIT 10
    """, (today_start,)).fetchall()
    digest['overdue_tasks'] = [dict(r) for r in rows]
    
    # Deals closing soon
    rows = conn.execute("""
        SELECT d.*, c.name as contact_name FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        WHERE d.stage NOT IN ('won', 'lost')
        AND d.expected_close <= ?
        ORDER BY d.expected_close ASC
        LIMIT 5
    """, (week_ahead,)).fetchall()
    digest['deals_closing_soon'] = [dict(r) for r in rows]
    
    # Contacts needing follow-up (no interaction in 14+ days)
    stale_date = (now - timedelta(days=14)).isoformat()
    rows = conn.execute("""
        SELECT c.*, MAX(i.occurred_at) as last_interaction
        FROM contacts c
        LEFT JOIN interactions i ON c.id = i.contact_id
        GROUP BY c.id
        HAVING last_interaction < ? OR last_interaction IS NULL
        ORDER BY last_interaction ASC
        LIMIT 10
    """, (stale_date,)).fetchall()
    digest['needs_followup'] = [dict(r) for r in rows]
    
    # Won deals this month
    month_start = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
    rows = conn.execute("""
        SELECT SUM(value) as total, COUNT(*) as count FROM deals
        WHERE stage = 'won' AND closed_at >= ?
    """, (month_start,)).fetchone()
    digest['won_this_month'] = {
        'count': rows['count'] or 0,
        'value': rows['total'] or 0
    }
    
    conn.close()
    return digest

def format_digest_text(digest: dict) -> str:
    """Format digest as human-readable text."""
    if 'error' in digest:
        return f"❌ {digest['error']}"
    
    lines = []
    lines.append(f"📊 **CRM Digest** — {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    
    # Recent activity
    act = digest['recent_activity']
    if any([act['new_contacts'], act['total_interactions'], act['tasks_completed']]):
        lines.append("**Recent Activity:**")
        if act['new_contacts']:
            lines.append(f"• {act['new_contacts']} new contact(s)")
        if act['new_deals']:
            lines.append(f"• {act['new_deals']} new deal(s) (${act['new_deal_value']:,.0f})")
        if act['total_interactions']:
            types = ', '.join(f"{v} {k}" for k, v in act['interactions'].items())
            lines.append(f"• {act['total_interactions']} interaction(s) logged ({types})")
        if act['tasks_completed']:
            lines.append(f"• {act['tasks_completed']} task(s) completed")
        if act['deal_stage_changes']:
            for change in act['deal_stage_changes']:
                lines.append(f"• Deal moved: {change['from']} → {change['to']}")
        lines.append("")
    
    # Pipeline
    pipe = digest['pipeline']
    if pipe['total_deals']:
        lines.append("**Pipeline:**")
        for stage in pipe['stages']:
            val = f"${stage['total_value']:,.0f}" if stage['total_value'] else "$0"
            lines.append(f"• {stage['stage'].title()}: {stage['count']} deal(s) ({val})")
        lines.append(f"• **Total:** {pipe['total_deals']} deals, ${pipe['total_value']:,.0f}")
        lines.append(f"• **Weighted:** ${pipe['weighted_value']:,.0f}")
        lines.append("")
    
    # Tasks
    if digest['overdue_tasks']:
        lines.append("**⚠️ Overdue Tasks:**")
        for task in digest['overdue_tasks'][:5]:
            contact = f" ({task['contact_name']})" if task['contact_name'] else ""
            lines.append(f"• {task['title']}{contact}")
        lines.append("")
    
    if digest['tasks_due_today']:
        lines.append("**Today's Tasks:**")
        for task in digest['tasks_due_today']:
            contact = f" ({task['contact_name']})" if task['contact_name'] else ""
            lines.append(f"• {task['title']}{contact}")
        lines.append("")
    
    # Deals closing soon
    if digest['deals_closing_soon']:
        lines.append("**Deals Closing Soon:**")
        for deal in digest['deals_closing_soon']:
            val = f"${deal['value']:,.0f}" if deal['value'] else "TBD"
            contact = f" - {deal['contact_name']}" if deal['contact_name'] else ""
            lines.append(f"• {deal['title']} ({val}){contact} — {deal['expected_close']}")
        lines.append("")
    
    # Follow-ups needed
    if digest['needs_followup']:
        lines.append("**Needs Follow-up (14+ days):**")
        for contact in digest['needs_followup'][:5]:
            company = f" @ {contact['company']}" if contact['company'] else ""
            lines.append(f"• {contact['name']}{company}")
        lines.append("")
    
    # Won this month
    won = digest['won_this_month']
    if won['count']:
        lines.append(f"**Won This Month:** {won['count']} deal(s) — ${won['value']:,.0f} 🎉")
    
    if len(lines) <= 2:
        lines.append("No activity to report. Database may be empty.")
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='Generate CRM daily digest')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--lookback', '-l', type=int, default=1, help='Days to look back')
    parser.add_argument('--lookahead', '-a', type=int, default=7, help='Days to look ahead')
    
    args = parser.parse_args()
    
    digest = generate_digest(args.lookback, args.lookahead)
    
    if args.json:
        print(json.dumps(digest, indent=2))
    else:
        print(format_digest_text(digest))

if __name__ == '__main__':
    main()
