#!/usr/bin/env python3
"""
CRM Notify - Check for items needing attention

Returns actionable alerts:
- Overdue tasks
- Tasks due today
- Deals closing soon (within N days)
- Stale contacts (no interaction in N days)
- Deals stuck in stage too long

Designed to be run from heartbeat/cron and output alerts for the agent to act on.
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

def check_alerts(
    stale_days: int = 14,
    closing_days: int = 7,
    stuck_days: int = 21
) -> dict:
    """Check for all alert conditions."""
    conn = get_db()
    if not conn:
        return {'error': 'Database not found', 'alerts': []}
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0).isoformat()
    today_end = now.replace(hour=23, minute=59, second=59).isoformat()
    
    alerts = []
    
    # Overdue tasks
    rows = conn.execute("""
        SELECT t.*, c.name as contact_name FROM tasks t
        LEFT JOIN contacts c ON t.contact_id = c.id
        WHERE t.completed_at IS NULL AND t.due_at < ?
        ORDER BY t.due_at ASC
    """, (today_start,)).fetchall()
    
    for row in rows:
        due = datetime.fromisoformat(row['due_at']) if row['due_at'] else None
        days_overdue = (now - due).days if due else 0
        alerts.append({
            'type': 'overdue_task',
            'priority': 'high' if days_overdue > 3 else 'medium',
            'task_id': row['id'],
            'title': row['title'],
            'contact': row['contact_name'],
            'due_at': row['due_at'],
            'days_overdue': days_overdue,
            'message': f"⚠️ Task overdue ({days_overdue}d): {row['title']}" + 
                      (f" ({row['contact_name']})" if row['contact_name'] else "")
        })
    
    # Tasks due today
    rows = conn.execute("""
        SELECT t.*, c.name as contact_name FROM tasks t
        LEFT JOIN contacts c ON t.contact_id = c.id
        WHERE t.completed_at IS NULL 
        AND t.due_at >= ? AND t.due_at <= ?
        ORDER BY t.priority DESC, t.due_at ASC
    """, (today_start, today_end)).fetchall()
    
    for row in rows:
        alerts.append({
            'type': 'task_due_today',
            'priority': row['priority'] or 'normal',
            'task_id': row['id'],
            'title': row['title'],
            'contact': row['contact_name'],
            'due_at': row['due_at'],
            'message': f"📋 Due today: {row['title']}" +
                      (f" ({row['contact_name']})" if row['contact_name'] else "")
        })
    
    # Deals closing soon
    closing_threshold = (now + timedelta(days=closing_days)).isoformat()
    rows = conn.execute("""
        SELECT d.*, c.name as contact_name FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        WHERE d.stage NOT IN ('won', 'lost')
        AND d.expected_close IS NOT NULL
        AND d.expected_close <= ?
        ORDER BY d.expected_close ASC
    """, (closing_threshold,)).fetchall()
    
    for row in rows:
        close_date = datetime.fromisoformat(row['expected_close']) if row['expected_close'] else None
        days_until = (close_date - now).days if close_date else 0
        value_str = f"${row['value']:,.0f}" if row['value'] else "TBD"
        alerts.append({
            'type': 'deal_closing_soon',
            'priority': 'high' if days_until <= 3 else 'medium',
            'deal_id': row['id'],
            'title': row['title'],
            'value': row['value'],
            'contact': row['contact_name'],
            'expected_close': row['expected_close'],
            'days_until_close': days_until,
            'message': f"💰 Deal closing in {days_until}d: {row['title']} ({value_str})"
        })
    
    # Stale contacts (no interaction in N days, but have a deal)
    stale_threshold = (now - timedelta(days=stale_days)).isoformat()
    rows = conn.execute("""
        SELECT c.*, d.title as deal_title, d.value as deal_value, d.stage as deal_stage,
               MAX(i.occurred_at) as last_interaction
        FROM contacts c
        JOIN deals d ON c.id = d.contact_id AND d.stage NOT IN ('won', 'lost')
        LEFT JOIN interactions i ON c.id = i.contact_id
        GROUP BY c.id
        HAVING last_interaction < ? OR last_interaction IS NULL
        ORDER BY d.value DESC NULLS LAST
    """, (stale_threshold,)).fetchall()
    
    for row in rows:
        last = datetime.fromisoformat(row['last_interaction']) if row['last_interaction'] else None
        days_stale = (now - last).days if last else 999
        alerts.append({
            'type': 'stale_contact',
            'priority': 'medium',
            'contact_id': row['id'],
            'name': row['name'],
            'company': row['company'],
            'deal': row['deal_title'],
            'deal_value': row['deal_value'],
            'last_interaction': row['last_interaction'],
            'days_since_contact': days_stale,
            'message': f"👋 No contact in {days_stale}d: {row['name']}" +
                      (f" ({row['deal_title']})" if row['deal_title'] else "")
        })
    
    # Deals stuck in stage
    stuck_threshold = (now - timedelta(days=stuck_days)).isoformat()
    rows = conn.execute("""
        SELECT d.*, c.name as contact_name FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        WHERE d.stage NOT IN ('won', 'lost', 'lead')
        AND d.updated_at < ?
        ORDER BY d.value DESC NULLS LAST
    """, (stuck_threshold,)).fetchall()
    
    for row in rows:
        updated = datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
        days_stuck = (now - updated).days if updated else 0
        value_str = f"${row['value']:,.0f}" if row['value'] else "TBD"
        alerts.append({
            'type': 'deal_stuck',
            'priority': 'low',
            'deal_id': row['id'],
            'title': row['title'],
            'value': row['value'],
            'stage': row['stage'],
            'days_in_stage': days_stuck,
            'message': f"🐌 Deal stuck {days_stuck}d in {row['stage']}: {row['title']} ({value_str})"
        })
    
    conn.close()
    
    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'normal': 2, 'low': 3}
    alerts.sort(key=lambda x: priority_order.get(x.get('priority', 'normal'), 2))
    
    return {
        'checked_at': now.isoformat(),
        'total_alerts': len(alerts),
        'by_type': {
            'overdue_tasks': len([a for a in alerts if a['type'] == 'overdue_task']),
            'tasks_due_today': len([a for a in alerts if a['type'] == 'task_due_today']),
            'deals_closing_soon': len([a for a in alerts if a['type'] == 'deal_closing_soon']),
            'stale_contacts': len([a for a in alerts if a['type'] == 'stale_contact']),
            'deals_stuck': len([a for a in alerts if a['type'] == 'deal_stuck'])
        },
        'alerts': alerts
    }

def format_alerts_text(result: dict) -> str:
    """Format alerts as human-readable text."""
    if 'error' in result:
        return f"❌ {result['error']}"
    
    if not result['alerts']:
        return "✅ No CRM alerts. All clear!"
    
    lines = []
    lines.append(f"🔔 **CRM Alerts** ({result['total_alerts']} items)")
    lines.append("")
    
    # Group by type
    current_type = None
    type_labels = {
        'overdue_task': '⚠️ Overdue Tasks',
        'task_due_today': '📋 Due Today',
        'deal_closing_soon': '💰 Deals Closing Soon',
        'stale_contact': '👋 Needs Follow-up',
        'deal_stuck': '🐌 Stuck Deals'
    }
    
    for alert in result['alerts']:
        if alert['type'] != current_type:
            if current_type is not None:
                lines.append("")
            current_type = alert['type']
            lines.append(f"**{type_labels.get(current_type, current_type)}:**")
        
        lines.append(f"• {alert['message']}")
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='Check CRM for items needing attention')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--stale-days', type=int, default=14, help='Days before contact is stale')
    parser.add_argument('--closing-days', type=int, default=7, help='Days to look ahead for closing deals')
    parser.add_argument('--stuck-days', type=int, default=21, help='Days before deal is considered stuck')
    parser.add_argument('--type', '-t', choices=['overdue_task', 'task_due_today', 'deal_closing_soon', 'stale_contact', 'deal_stuck'],
                       help='Filter to specific alert type')
    
    args = parser.parse_args()
    
    result = check_alerts(args.stale_days, args.closing_days, args.stuck_days)
    
    # Filter by type if specified
    if args.type and 'alerts' in result:
        result['alerts'] = [a for a in result['alerts'] if a['type'] == args.type]
        result['total_alerts'] = len(result['alerts'])
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_alerts_text(result))

if __name__ == '__main__':
    main()
