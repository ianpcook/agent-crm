#!/usr/bin/env python3
"""
CRM Export - Export data to CSV/JSON formats

Exports:
- contacts: All contacts
- deals: All deals with contact info
- interactions: All interactions
- tasks: All tasks
- all: Complete database dump
"""

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))
EXPORT_DIR = os.environ.get('CRM_EXPORT_DIR', os.path.expanduser('~/.local/share/agent-crm/exports'))

def get_db() -> sqlite3.Connection:
    """Get database connection."""
    if not Path(DB_PATH).exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_export_dir():
    """Create export directory if needed."""
    Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

def export_table(conn, table: str, query: str = None) -> list[dict]:
    """Export a table to list of dicts."""
    if query is None:
        query = f"SELECT * FROM {table}"
    rows = conn.execute(query).fetchall()
    return [dict(r) for r in rows]

def to_csv(data: list[dict], filepath: str):
    """Write data to CSV."""
    if not data:
        return
    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

def to_json(data: list[dict], filepath: str):
    """Write data to JSON."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def export_contacts(conn, format: str, output_dir: str) -> str:
    """Export contacts."""
    data = export_table(conn, 'contacts')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'csv':
        filepath = os.path.join(output_dir, f'contacts_{timestamp}.csv')
        to_csv(data, filepath)
    else:
        filepath = os.path.join(output_dir, f'contacts_{timestamp}.json')
        to_json(data, filepath)
    
    return filepath

def export_deals(conn, format: str, output_dir: str) -> str:
    """Export deals with contact info."""
    query = """
        SELECT d.*, c.name as contact_name, c.email as contact_email, c.company as contact_company
        FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        ORDER BY d.created_at DESC
    """
    data = export_table(conn, 'deals', query)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'csv':
        filepath = os.path.join(output_dir, f'deals_{timestamp}.csv')
        to_csv(data, filepath)
    else:
        filepath = os.path.join(output_dir, f'deals_{timestamp}.json')
        to_json(data, filepath)
    
    return filepath

def export_interactions(conn, format: str, output_dir: str) -> str:
    """Export interactions with contact info."""
    query = """
        SELECT i.*, c.name as contact_name, c.company as contact_company
        FROM interactions i
        LEFT JOIN contacts c ON i.contact_id = c.id
        ORDER BY i.occurred_at DESC
    """
    data = export_table(conn, 'interactions', query)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'csv':
        filepath = os.path.join(output_dir, f'interactions_{timestamp}.csv')
        to_csv(data, filepath)
    else:
        filepath = os.path.join(output_dir, f'interactions_{timestamp}.json')
        to_json(data, filepath)
    
    return filepath

def export_tasks(conn, format: str, output_dir: str) -> str:
    """Export tasks with contact info."""
    query = """
        SELECT t.*, c.name as contact_name, d.title as deal_title
        FROM tasks t
        LEFT JOIN contacts c ON t.contact_id = c.id
        LEFT JOIN deals d ON t.deal_id = d.id
        ORDER BY t.due_at ASC
    """
    data = export_table(conn, 'tasks', query)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'csv':
        filepath = os.path.join(output_dir, f'tasks_{timestamp}.csv')
        to_csv(data, filepath)
    else:
        filepath = os.path.join(output_dir, f'tasks_{timestamp}.json')
        to_json(data, filepath)
    
    return filepath

def export_all(conn, format: str, output_dir: str) -> dict:
    """Export everything."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'json':
        # Single JSON file with all data
        data = {
            'exported_at': datetime.now().isoformat(),
            'contacts': export_table(conn, 'contacts'),
            'deals': export_table(conn, 'deals', """
                SELECT d.*, c.name as contact_name 
                FROM deals d LEFT JOIN contacts c ON d.contact_id = c.id
            """),
            'interactions': export_table(conn, 'interactions', """
                SELECT i.*, c.name as contact_name 
                FROM interactions i LEFT JOIN contacts c ON i.contact_id = c.id
            """),
            'tasks': export_table(conn, 'tasks', """
                SELECT t.*, c.name as contact_name 
                FROM tasks t LEFT JOIN contacts c ON t.contact_id = c.id
            """),
            'audit_log': export_table(conn, 'audit_log')
        }
        filepath = os.path.join(output_dir, f'crm_export_{timestamp}.json')
        to_json(data, filepath)
        return {'format': 'json', 'path': filepath}
    else:
        # Multiple CSV files
        files = []
        files.append(export_contacts(conn, 'csv', output_dir))
        files.append(export_deals(conn, 'csv', output_dir))
        files.append(export_interactions(conn, 'csv', output_dir))
        files.append(export_tasks(conn, 'csv', output_dir))
        return {'format': 'csv', 'files': files}

def main():
    parser = argparse.ArgumentParser(description='Export CRM data')
    parser.add_argument('what', choices=['contacts', 'deals', 'interactions', 'tasks', 'all'],
                       help='What to export')
    parser.add_argument('--format', '-f', choices=['csv', 'json'], default='json',
                       help='Export format')
    parser.add_argument('--output', '-o', help='Output directory')
    
    args = parser.parse_args()
    
    conn = get_db()
    if not conn:
        print(json.dumps({'error': 'Database not found', 'path': DB_PATH}))
        return
    
    output_dir = args.output or EXPORT_DIR
    ensure_export_dir()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    exporters = {
        'contacts': export_contacts,
        'deals': export_deals,
        'interactions': export_interactions,
        'tasks': export_tasks,
        'all': export_all,
    }
    
    result = exporters[args.what](conn, args.format, output_dir)
    conn.close()
    
    if isinstance(result, dict):
        print(json.dumps({'status': 'success', **result}))
    else:
        print(json.dumps({'status': 'success', 'path': result}))

if __name__ == '__main__':
    main()
