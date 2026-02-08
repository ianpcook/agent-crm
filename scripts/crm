#!/usr/bin/env python3
"""
Agent CRM CLI - Core CRUD operations
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re

# Database location
DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))
SCHEMA_PATH = Path(__file__).parent.parent / 'schema.sql'

def get_db() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    needs_init = not db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    
    if needs_init and SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    
    return conn

def parse_date(s: str) -> Optional[str]:
    """Parse flexible date strings into ISO format."""
    if not s:
        return None
    
    s = s.lower().strip()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Relative dates
    if s == 'today':
        return today.isoformat()
    if s == 'tomorrow':
        return (today + timedelta(days=1)).isoformat()
    if s == 'yesterday':
        return (today - timedelta(days=1)).isoformat()
    
    # "next week", "next month"
    if s.startswith('next '):
        unit = s[5:]
        if unit == 'week':
            return (today + timedelta(weeks=1)).isoformat()
        if unit == 'month':
            return (today + timedelta(days=30)).isoformat()
    
    # "in N days/weeks"
    match = re.match(r'in (\d+) (day|week|month)s?', s)
    if match:
        n, unit = int(match.group(1)), match.group(2)
        if unit == 'day':
            return (today + timedelta(days=n)).isoformat()
        if unit == 'week':
            return (today + timedelta(weeks=n)).isoformat()
        if unit == 'month':
            return (today + timedelta(days=n*30)).isoformat()
    
    # Day names
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    if s in days or s.startswith('next ') and s[5:] in days:
        target_day = days.index(s.replace('next ', ''))
        current_day = today.weekday()
        delta = target_day - current_day
        if delta <= 0:
            delta += 7
        return (today + timedelta(days=delta)).isoformat()
    
    # Try parsing as date
    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d', '%B %d', '%b %d']:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year == 1900:  # No year specified
                dt = dt.replace(year=today.year)
                if dt < today:
                    dt = dt.replace(year=today.year + 1)
            return dt.isoformat()
        except ValueError:
            continue
    
    return s  # Return as-is if unparseable

def audit_log(conn: sqlite3.Connection, table: str, record_id: str, action: str,
              old: dict = None, new: dict = None, reason: str = None, conv_ref: str = None):
    """Log an action to the audit table."""
    conn.execute("""
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, reason, conversation_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (table, record_id, action, 
          json.dumps(old) if old else None,
          json.dumps(new) if new else None,
          reason, conv_ref))

# ============ CONTACTS ============

def add_contact(args):
    """Add a new contact."""
    conn = get_db()
    
    tags = json.dumps(args.tags.split(',')) if args.tags else None
    
    cursor = conn.execute("""
        INSERT INTO contacts (name, email, phone, company, role, source, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (args.name, args.email, args.phone, args.company, args.role, args.source, tags, args.notes))
    
    record_id = cursor.lastrowid
    # Get the actual ID
    row = conn.execute("SELECT id FROM contacts WHERE rowid = ?", (record_id,)).fetchone()
    
    audit_log(conn, 'contacts', row['id'], 'INSERT', new={
        'name': args.name, 'email': args.email, 'company': args.company
    }, reason=args.reason)
    
    conn.commit()
    
    print(json.dumps({
        'status': 'created',
        'id': row['id'],
        'name': args.name,
        'company': args.company,
        'email': args.email
    }, indent=2))

def find_contact(args):
    """Find contacts by name, email, or company."""
    conn = get_db()
    
    query = args.query.lower()
    rows = conn.execute("""
        SELECT * FROM contacts
        WHERE lower(name) LIKE ? OR lower(email) LIKE ? OR lower(company) LIKE ?
        ORDER BY updated_at DESC
        LIMIT ?
    """, (f'%{query}%', f'%{query}%', f'%{query}%', args.limit)).fetchall()
    
    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))

def list_contacts(args):
    """List all contacts."""
    conn = get_db()
    
    order = 'updated_at DESC' if args.recent else 'name ASC'
    rows = conn.execute(f"SELECT * FROM contacts ORDER BY {order} LIMIT ?", (args.limit,)).fetchall()
    
    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))

def update_contact(args):
    """Update a contact."""
    conn = get_db()
    
    # Find the contact
    row = conn.execute("""
        SELECT * FROM contacts WHERE id = ? OR lower(name) LIKE ?
    """, (args.id, f'%{args.id.lower()}%')).fetchone()
    
    if not row:
        print(json.dumps({'error': f'Contact not found: {args.id}'}))
        sys.exit(1)
    
    old = dict(row)
    updates = {}
    
    for field in ['name', 'email', 'phone', 'company', 'role', 'source', 'notes']:
        val = getattr(args, field, None)
        if val is not None:
            updates[field] = val
    
    if args.tags:
        updates['tags'] = json.dumps(args.tags.split(','))
    
    if not updates:
        print(json.dumps({'error': 'No updates provided'}))
        sys.exit(1)
    
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    updates['updated_at'] = datetime.now().isoformat()
    
    conn.execute(f"""
        UPDATE contacts SET {set_clause}, updated_at = ? WHERE id = ?
    """, (*updates.values(), row['id']))
    
    audit_log(conn, 'contacts', row['id'], 'UPDATE', old=old, new=updates, reason=args.reason)
    conn.commit()
    
    print(json.dumps({'status': 'updated', 'id': row['id'], 'changes': updates}, indent=2))

def delete_contact(args):
    """Delete a contact."""
    conn = get_db()
    
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (args.id,)).fetchone()
    if not row:
        print(json.dumps({'error': f'Contact not found: {args.id}'}))
        sys.exit(1)
    
    old = dict(row)
    conn.execute("DELETE FROM contacts WHERE id = ?", (args.id,))
    audit_log(conn, 'contacts', args.id, 'DELETE', old=old, reason=args.reason)
    conn.commit()
    
    print(json.dumps({'status': 'deleted', 'id': args.id, 'name': old['name']}, indent=2))

# ============ DEALS ============

def add_deal(args):
    """Add a new deal."""
    conn = get_db()
    
    # Find contact if specified
    contact_id = None
    if args.contact:
        row = conn.execute("""
            SELECT id FROM contacts WHERE id = ? OR lower(name) LIKE ?
        """, (args.contact, f'%{args.contact.lower()}%')).fetchone()
        if row:
            contact_id = row['id']
    
    expected_close = parse_date(args.expected_close) if args.expected_close else None
    
    cursor = conn.execute("""
        INSERT INTO deals (contact_id, title, value, currency, stage, probability, expected_close, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, args.title, args.value, args.currency or 'USD', 
          args.stage or 'lead', args.probability, expected_close, args.notes))
    
    row = conn.execute("SELECT id FROM deals WHERE rowid = ?", (cursor.lastrowid,)).fetchone()
    
    audit_log(conn, 'deals', row['id'], 'INSERT', new={
        'title': args.title, 'value': args.value, 'stage': args.stage or 'lead'
    }, reason=args.reason)
    
    conn.commit()
    
    print(json.dumps({
        'status': 'created',
        'id': row['id'],
        'title': args.title,
        'value': args.value,
        'stage': args.stage or 'lead'
    }, indent=2))

def list_deals(args):
    """List deals, optionally filtered by stage."""
    conn = get_db()
    
    if args.stage:
        rows = conn.execute("""
            SELECT d.*, c.name as contact_name 
            FROM deals d LEFT JOIN contacts c ON d.contact_id = c.id
            WHERE d.stage = ?
            ORDER BY d.value DESC
            LIMIT ?
        """, (args.stage, args.limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT d.*, c.name as contact_name 
            FROM deals d LEFT JOIN contacts c ON d.contact_id = c.id
            ORDER BY d.updated_at DESC
            LIMIT ?
        """, (args.limit,)).fetchall()
    
    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))

def update_deal(args):
    """Update a deal."""
    conn = get_db()
    
    row = conn.execute("""
        SELECT * FROM deals WHERE id = ? OR lower(title) LIKE ?
    """, (args.id, f'%{args.id.lower()}%')).fetchone()
    
    if not row:
        print(json.dumps({'error': f'Deal not found: {args.id}'}))
        sys.exit(1)
    
    old = dict(row)
    updates = {}
    
    for field in ['title', 'value', 'currency', 'stage', 'probability', 'notes']:
        val = getattr(args, field, None)
        if val is not None:
            updates[field] = val
    
    if args.expected_close:
        updates['expected_close'] = parse_date(args.expected_close)
    
    if args.stage in ('won', 'lost'):
        updates['closed_at'] = datetime.now().isoformat()
    
    if not updates:
        print(json.dumps({'error': 'No updates provided'}))
        sys.exit(1)
    
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    
    conn.execute(f"""
        UPDATE deals SET {set_clause}, updated_at = ? WHERE id = ?
    """, (*updates.values(), datetime.now().isoformat(), row['id']))
    
    audit_log(conn, 'deals', row['id'], 'UPDATE', old=old, new=updates, reason=args.reason)
    conn.commit()
    
    print(json.dumps({'status': 'updated', 'id': row['id'], 'changes': updates}, indent=2))

def pipeline(args):
    """Show pipeline summary."""
    conn = get_db()
    
    rows = conn.execute("""
        SELECT stage, COUNT(*) as count, SUM(value) as total_value
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
    
    result = {
        'stages': [dict(r) for r in rows],
        'total_deals': sum(r['count'] for r in rows),
        'total_value': sum(r['total_value'] or 0 for r in rows)
    }
    
    # Weighted value (probability-adjusted)
    weighted = conn.execute("""
        SELECT SUM(value * COALESCE(probability, 50) / 100.0) as weighted
        FROM deals WHERE stage NOT IN ('won', 'lost')
    """).fetchone()
    result['weighted_value'] = weighted['weighted'] or 0
    
    print(json.dumps(result, indent=2))

# ============ INTERACTIONS ============

def log_interaction(args):
    """Log an interaction."""
    conn = get_db()
    
    # Find contact
    contact_id = None
    if args.contact:
        row = conn.execute("""
            SELECT id FROM contacts WHERE id = ? OR lower(name) LIKE ?
        """, (args.contact, f'%{args.contact.lower()}%')).fetchone()
        if row:
            contact_id = row['id']
    
    occurred = parse_date(args.date) if args.date else datetime.now().isoformat()
    
    cursor = conn.execute("""
        INSERT INTO interactions (contact_id, deal_id, type, direction, summary, raw_content, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, args.deal, args.type, args.direction, args.summary, args.raw, occurred))
    
    row = conn.execute("SELECT id FROM interactions WHERE rowid = ?", (cursor.lastrowid,)).fetchone()
    
    audit_log(conn, 'interactions', row['id'], 'INSERT', new={
        'type': args.type, 'summary': args.summary[:100]
    }, reason=args.reason)
    
    conn.commit()
    
    print(json.dumps({
        'status': 'logged',
        'id': row['id'],
        'type': args.type,
        'contact_id': contact_id
    }, indent=2))

def list_interactions(args):
    """List interactions for a contact or recent."""
    conn = get_db()
    
    if args.contact:
        rows = conn.execute("""
            SELECT i.*, c.name as contact_name
            FROM interactions i
            LEFT JOIN contacts c ON i.contact_id = c.id
            WHERE i.contact_id = ? OR lower(c.name) LIKE ?
            ORDER BY i.occurred_at DESC
            LIMIT ?
        """, (args.contact, f'%{args.contact.lower()}%', args.limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT i.*, c.name as contact_name
            FROM interactions i
            LEFT JOIN contacts c ON i.contact_id = c.id
            ORDER BY i.occurred_at DESC
            LIMIT ?
        """, (args.limit,)).fetchall()
    
    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))

# ============ TASKS ============

def add_task(args):
    """Add a task."""
    conn = get_db()
    
    contact_id = None
    if args.contact:
        row = conn.execute("""
            SELECT id FROM contacts WHERE id = ? OR lower(name) LIKE ?
        """, (args.contact, f'%{args.contact.lower()}%')).fetchone()
        if row:
            contact_id = row['id']
    
    due = parse_date(args.due) if args.due else None
    
    cursor = conn.execute("""
        INSERT INTO tasks (contact_id, deal_id, title, due_at, priority)
        VALUES (?, ?, ?, ?, ?)
    """, (contact_id, args.deal, args.title, due, args.priority or 'normal'))
    
    row = conn.execute("SELECT id FROM tasks WHERE rowid = ?", (cursor.lastrowid,)).fetchone()
    
    audit_log(conn, 'tasks', row['id'], 'INSERT', new={'title': args.title, 'due': due}, reason=args.reason)
    conn.commit()
    
    print(json.dumps({
        'status': 'created',
        'id': row['id'],
        'title': args.title,
        'due_at': due
    }, indent=2))

def list_tasks(args):
    """List tasks."""
    conn = get_db()
    
    if args.pending:
        rows = conn.execute("""
            SELECT t.*, c.name as contact_name
            FROM tasks t
            LEFT JOIN contacts c ON t.contact_id = c.id
            WHERE t.completed_at IS NULL
            ORDER BY t.due_at ASC NULLS LAST
            LIMIT ?
        """, (args.limit,)).fetchall()
    elif args.overdue:
        rows = conn.execute("""
            SELECT t.*, c.name as contact_name
            FROM tasks t
            LEFT JOIN contacts c ON t.contact_id = c.id
            WHERE t.completed_at IS NULL AND t.due_at < datetime('now')
            ORDER BY t.due_at ASC
            LIMIT ?
        """, (args.limit,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT t.*, c.name as contact_name
            FROM tasks t
            LEFT JOIN contacts c ON t.contact_id = c.id
            ORDER BY t.created_at DESC
            LIMIT ?
        """, (args.limit,)).fetchall()
    
    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))

def complete_task(args):
    """Complete a task."""
    conn = get_db()
    
    row = conn.execute("""
        SELECT * FROM tasks WHERE id = ? OR lower(title) LIKE ?
    """, (args.id, f'%{args.id.lower()}%')).fetchone()
    
    if not row:
        print(json.dumps({'error': f'Task not found: {args.id}'}))
        sys.exit(1)
    
    old = dict(row)
    now = datetime.now().isoformat()
    
    conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (now, row['id']))
    audit_log(conn, 'tasks', row['id'], 'UPDATE', old=old, new={'completed_at': now}, reason=args.reason)
    conn.commit()
    
    print(json.dumps({'status': 'completed', 'id': row['id'], 'title': row['title']}, indent=2))

# ============ QUERY ============

def query(args):
    """Run a raw SQL query (SELECT only)."""
    conn = get_db()
    
    sql = args.sql.strip()
    if not sql.lower().startswith('select'):
        print(json.dumps({'error': 'Only SELECT queries allowed'}))
        sys.exit(1)
    
    try:
        rows = conn.execute(sql).fetchall()
        results = [dict(r) for r in rows]
        print(json.dumps(results, indent=2))
    except sqlite3.Error as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

def stats(args):
    """Show CRM statistics."""
    conn = get_db()
    
    result = {}
    
    result['contacts'] = conn.execute("SELECT COUNT(*) as count FROM contacts").fetchone()['count']
    result['deals'] = conn.execute("SELECT COUNT(*) as count FROM deals").fetchone()['count']
    result['open_deals'] = conn.execute(
        "SELECT COUNT(*) as count FROM deals WHERE stage NOT IN ('won', 'lost')"
    ).fetchone()['count']
    result['interactions'] = conn.execute("SELECT COUNT(*) as count FROM interactions").fetchone()['count']
    result['pending_tasks'] = conn.execute(
        "SELECT COUNT(*) as count FROM tasks WHERE completed_at IS NULL"
    ).fetchone()['count']
    result['overdue_tasks'] = conn.execute(
        "SELECT COUNT(*) as count FROM tasks WHERE completed_at IS NULL AND due_at < datetime('now')"
    ).fetchone()['count']
    
    # Pipeline value
    pipeline_row = conn.execute("""
        SELECT SUM(value) as total FROM deals WHERE stage NOT IN ('won', 'lost')
    """).fetchone()
    result['pipeline_value'] = pipeline_row['total'] or 0
    
    # Won this month
    won_row = conn.execute("""
        SELECT SUM(value) as total FROM deals 
        WHERE stage = 'won' AND closed_at >= date('now', 'start of month')
    """).fetchone()
    result['won_this_month'] = won_row['total'] or 0
    
    print(json.dumps(result, indent=2))

def init_db(args):
    """Initialize the database and show what was created."""
    from pathlib import Path
    
    db_path = Path(DB_PATH)
    already_exists = db_path.exists()
    
    # Get or create database
    conn = get_db()
    
    # Get table info
    tables = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()
    table_names = [t['name'] for t in tables]
    
    # Get counts
    counts = {}
    for table in table_names:
        count = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()['c']
        counts[table] = count
    
    # Get database size
    db_size = db_path.stat().st_size if db_path.exists() else 0
    
    result = {
        'status': 'existing' if already_exists else 'created',
        'database': str(db_path),
        'size_bytes': db_size,
        'tables': table_names,
        'record_counts': counts,
        'paths': {
            'database': str(db_path),
            'backups': str(db_path.parent / 'backups'),
            'charts': str(db_path.parent / 'charts'),
            'exports': str(db_path.parent / 'exports'),
        }
    }
    
    if not already_exists:
        result['message'] = 'Database created and ready to use'
    else:
        total_records = sum(counts.values())
        result['message'] = f'Database exists with {total_records} total records'
    
    print(json.dumps(result, indent=2))

# ============ MAIN ============

def main():
    parser = argparse.ArgumentParser(description='Agent CRM CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Common args
    def add_common(p):
        p.add_argument('--reason', help='Reason for this action (audit)')
    
    # Contact commands
    p = subparsers.add_parser('add-contact', help='Add a contact')
    p.add_argument('name', help='Contact name')
    p.add_argument('--email', '-e')
    p.add_argument('--phone', '-p')
    p.add_argument('--company', '-c')
    p.add_argument('--role', '-r')
    p.add_argument('--source', '-s')
    p.add_argument('--tags', '-t', help='Comma-separated tags')
    p.add_argument('--notes', '-n')
    add_common(p)
    p.set_defaults(func=add_contact)
    
    p = subparsers.add_parser('find-contact', help='Find contacts')
    p.add_argument('query', help='Search query')
    p.add_argument('--limit', '-l', type=int, default=10)
    p.set_defaults(func=find_contact)
    
    p = subparsers.add_parser('list-contacts', help='List contacts')
    p.add_argument('--limit', '-l', type=int, default=20)
    p.add_argument('--recent', '-r', action='store_true')
    p.set_defaults(func=list_contacts)
    
    p = subparsers.add_parser('update-contact', help='Update a contact')
    p.add_argument('id', help='Contact ID or name')
    p.add_argument('--name')
    p.add_argument('--email', '-e')
    p.add_argument('--phone', '-p')
    p.add_argument('--company', '-c')
    p.add_argument('--role', '-r')
    p.add_argument('--source', '-s')
    p.add_argument('--tags', '-t')
    p.add_argument('--notes', '-n')
    add_common(p)
    p.set_defaults(func=update_contact)
    
    p = subparsers.add_parser('delete-contact', help='Delete a contact')
    p.add_argument('id', help='Contact ID')
    add_common(p)
    p.set_defaults(func=delete_contact)
    
    # Deal commands
    p = subparsers.add_parser('add-deal', help='Add a deal')
    p.add_argument('title', help='Deal title')
    p.add_argument('--value', '-v', type=float)
    p.add_argument('--contact', '-c', help='Contact name or ID')
    p.add_argument('--stage', '-s', default='lead')
    p.add_argument('--probability', '-p', type=int)
    p.add_argument('--currency', default='USD')
    p.add_argument('--expected-close', '-e')
    p.add_argument('--notes', '-n')
    add_common(p)
    p.set_defaults(func=add_deal)
    
    p = subparsers.add_parser('list-deals', help='List deals')
    p.add_argument('--stage', '-s')
    p.add_argument('--limit', '-l', type=int, default=20)
    p.set_defaults(func=list_deals)
    
    p = subparsers.add_parser('update-deal', help='Update a deal')
    p.add_argument('id', help='Deal ID or title')
    p.add_argument('--title')
    p.add_argument('--value', '-v', type=float)
    p.add_argument('--stage', '-s')
    p.add_argument('--probability', '-p', type=int)
    p.add_argument('--currency')
    p.add_argument('--expected-close', '-e')
    p.add_argument('--notes', '-n')
    add_common(p)
    p.set_defaults(func=update_deal)
    
    p = subparsers.add_parser('pipeline', help='Show pipeline summary')
    p.set_defaults(func=pipeline)
    
    # Interaction commands
    p = subparsers.add_parser('log', help='Log an interaction')
    p.add_argument('type', choices=['email', 'call', 'meeting', 'note', 'linkedin', 'text'])
    p.add_argument('summary', help='What happened')
    p.add_argument('--contact', '-c')
    p.add_argument('--deal', '-d')
    p.add_argument('--direction', choices=['inbound', 'outbound'])
    p.add_argument('--date')
    p.add_argument('--raw', help='Raw content')
    add_common(p)
    p.set_defaults(func=log_interaction)
    
    p = subparsers.add_parser('list-interactions', help='List interactions')
    p.add_argument('--contact', '-c')
    p.add_argument('--limit', '-l', type=int, default=20)
    p.set_defaults(func=list_interactions)
    
    # Task commands
    p = subparsers.add_parser('add-task', help='Add a task')
    p.add_argument('title', help='Task title')
    p.add_argument('--contact', '-c')
    p.add_argument('--deal', '-d')
    p.add_argument('--due')
    p.add_argument('--priority', choices=['low', 'normal', 'high', 'urgent'])
    add_common(p)
    p.set_defaults(func=add_task)
    
    p = subparsers.add_parser('list-tasks', help='List tasks')
    p.add_argument('--pending', action='store_true')
    p.add_argument('--overdue', action='store_true')
    p.add_argument('--limit', '-l', type=int, default=20)
    p.set_defaults(func=list_tasks)
    
    p = subparsers.add_parser('complete-task', help='Complete a task')
    p.add_argument('id', help='Task ID or title')
    add_common(p)
    p.set_defaults(func=complete_task)
    
    # Query commands
    p = subparsers.add_parser('query', help='Run SQL query')
    p.add_argument('sql', help='SQL query (SELECT only)')
    p.set_defaults(func=query)
    
    p = subparsers.add_parser('stats', help='Show CRM statistics')
    p.set_defaults(func=stats)
    
    p = subparsers.add_parser('init', help='Initialize database')
    p.set_defaults(func=init_db)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
