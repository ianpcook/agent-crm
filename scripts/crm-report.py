#!/usr/bin/env python3
"""
CRM Reports - Pipeline and activity analytics

Generates reports:
- Pipeline by stage (with trends)
- Activity summary (interactions, tasks)
- Win/loss analysis
- Forecast based on expected close dates
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

def pipeline_report() -> dict:
    """Generate pipeline report."""
    conn = get_db()
    if not conn:
        return {'error': 'Database not found'}
    
    now = datetime.now()
    
    # Current pipeline by stage
    stages = conn.execute("""
        SELECT 
            stage,
            COUNT(*) as count,
            SUM(value) as total_value,
            AVG(value) as avg_value,
            SUM(value * COALESCE(probability, 50) / 100.0) as weighted_value
        FROM deals
        WHERE stage NOT IN ('won', 'lost')
        GROUP BY stage
        ORDER BY 
            CASE stage 
                WHEN 'lead' THEN 1
                WHEN 'qualified' THEN 2
                WHEN 'proposal' THEN 3
                WHEN 'negotiation' THEN 4
            END
    """).fetchall()
    
    pipeline = {
        'stages': [dict(s) for s in stages],
        'totals': {
            'deals': sum(s['count'] for s in stages),
            'value': sum(s['total_value'] or 0 for s in stages),
            'weighted': sum(s['weighted_value'] or 0 for s in stages)
        }
    }
    
    # Deals by expected close month
    forecast = conn.execute("""
        SELECT 
            strftime('%Y-%m', expected_close) as month,
            COUNT(*) as count,
            SUM(value) as total_value,
            SUM(value * COALESCE(probability, 50) / 100.0) as weighted_value
        FROM deals
        WHERE stage NOT IN ('won', 'lost') 
        AND expected_close IS NOT NULL
        AND expected_close >= date('now')
        GROUP BY month
        ORDER BY month
        LIMIT 6
    """).fetchall()
    
    pipeline['forecast'] = [dict(f) for f in forecast]
    
    # Top deals
    top_deals = conn.execute("""
        SELECT d.*, c.name as contact_name
        FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        WHERE d.stage NOT IN ('won', 'lost')
        ORDER BY d.value DESC NULLS LAST
        LIMIT 10
    """).fetchall()
    
    pipeline['top_deals'] = [dict(d) for d in top_deals]
    
    conn.close()
    return pipeline

def activity_report(days: int = 30) -> dict:
    """Generate activity report for past N days."""
    conn = get_db()
    if not conn:
        return {'error': 'Database not found'}
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Interactions by type
    interactions = conn.execute("""
        SELECT type, direction, COUNT(*) as count
        FROM interactions
        WHERE logged_at >= ?
        GROUP BY type, direction
        ORDER BY count DESC
    """, (since,)).fetchall()
    
    # Tasks created vs completed
    tasks_created = conn.execute("""
        SELECT COUNT(*) as count FROM tasks WHERE created_at >= ?
    """, (since,)).fetchone()['count']
    
    tasks_completed = conn.execute("""
        SELECT COUNT(*) as count FROM tasks WHERE completed_at >= ?
    """, (since,)).fetchone()['count']
    
    # Contacts added
    contacts_added = conn.execute("""
        SELECT COUNT(*) as count FROM contacts WHERE created_at >= ?
    """, (since,)).fetchone()['count']
    
    # Deals created
    deals_created = conn.execute("""
        SELECT COUNT(*) as count, SUM(value) as total_value
        FROM deals WHERE created_at >= ?
    """, (since,)).fetchone()
    
    # Deal stage movements
    stage_changes = conn.execute("""
        SELECT 
            json_extract(old_values, '$.stage') as from_stage,
            json_extract(new_values, '$.stage') as to_stage,
            COUNT(*) as count
        FROM audit_log
        WHERE table_name = 'deals' 
        AND action = 'UPDATE'
        AND created_at >= ?
        AND json_extract(new_values, '$.stage') IS NOT NULL
        GROUP BY from_stage, to_stage
    """, (since,)).fetchall()
    
    conn.close()
    
    return {
        'period_days': days,
        'since': since,
        'interactions': [dict(i) for i in interactions],
        'total_interactions': sum(i['count'] for i in interactions),
        'tasks': {
            'created': tasks_created,
            'completed': tasks_completed,
            'completion_rate': tasks_completed / tasks_created if tasks_created else 0
        },
        'contacts_added': contacts_added,
        'deals': {
            'created': deals_created['count'],
            'total_value': deals_created['total_value'] or 0
        },
        'stage_movements': [dict(s) for s in stage_changes]
    }

def win_loss_report(days: int = 90) -> dict:
    """Analyze won vs lost deals."""
    conn = get_db()
    if not conn:
        return {'error': 'Database not found'}
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Won deals
    won = conn.execute("""
        SELECT COUNT(*) as count, SUM(value) as total_value, AVG(value) as avg_value
        FROM deals
        WHERE stage = 'won' AND closed_at >= ?
    """, (since,)).fetchone()
    
    # Lost deals
    lost = conn.execute("""
        SELECT COUNT(*) as count, SUM(value) as total_value, AVG(value) as avg_value
        FROM deals
        WHERE stage = 'lost' AND closed_at >= ?
    """, (since,)).fetchone()
    
    # Win rate
    total_closed = (won['count'] or 0) + (lost['count'] or 0)
    win_rate = (won['count'] or 0) / total_closed if total_closed else 0
    
    # Average deal cycle (created to closed)
    cycle = conn.execute("""
        SELECT AVG(julianday(closed_at) - julianday(created_at)) as avg_days
        FROM deals
        WHERE stage = 'won' AND closed_at >= ?
    """, (since,)).fetchone()
    
    conn.close()
    
    return {
        'period_days': days,
        'won': {
            'count': won['count'] or 0,
            'total_value': won['total_value'] or 0,
            'avg_value': won['avg_value'] or 0
        },
        'lost': {
            'count': lost['count'] or 0,
            'total_value': lost['total_value'] or 0,
            'avg_value': lost['avg_value'] or 0
        },
        'win_rate': win_rate,
        'avg_cycle_days': cycle['avg_days'] or 0
    }

def format_pipeline_text(report: dict) -> str:
    """Format pipeline report as text."""
    if 'error' in report:
        return f"❌ {report['error']}"
    
    lines = []
    lines.append("📊 **Pipeline Report**")
    lines.append("")
    
    # By stage
    lines.append("**By Stage:**")
    for stage in report['stages']:
        val = f"${stage['total_value']:,.0f}" if stage['total_value'] else "$0"
        weighted = f"${stage['weighted_value']:,.0f}" if stage['weighted_value'] else "$0"
        lines.append(f"• {stage['stage'].title()}: {stage['count']} deals — {val} (weighted: {weighted})")
    
    totals = report['totals']
    lines.append(f"• **Total:** {totals['deals']} deals — ${totals['value']:,.0f} (weighted: ${totals['weighted']:,.0f})")
    lines.append("")
    
    # Forecast
    if report['forecast']:
        lines.append("**Forecast by Month:**")
        for month in report['forecast']:
            lines.append(f"• {month['month']}: {month['count']} deals — ${month['total_value']:,.0f}")
        lines.append("")
    
    # Top deals
    if report['top_deals']:
        lines.append("**Top Deals:**")
        for deal in report['top_deals'][:5]:
            val = f"${deal['value']:,.0f}" if deal['value'] else "TBD"
            contact = f" ({deal['contact_name']})" if deal['contact_name'] else ""
            lines.append(f"• {deal['title']}{contact} — {val} [{deal['stage']}]")
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='CRM analytics and reports')
    parser.add_argument('report', choices=['pipeline', 'activity', 'winloss'],
                       help='Report type')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--days', '-d', type=int, default=30, help='Days to analyze')
    
    args = parser.parse_args()
    
    if args.report == 'pipeline':
        result = pipeline_report()
        if not args.json:
            print(format_pipeline_text(result))
            return
    elif args.report == 'activity':
        result = activity_report(args.days)
    elif args.report == 'winloss':
        result = win_loss_report(args.days)
    
    if args.json or args.report != 'pipeline':
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
