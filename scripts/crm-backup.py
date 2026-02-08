#!/usr/bin/env python3
"""
CRM Backup/Restore - Database backup and restore operations

Commands:
- backup: Create a timestamped backup of the database
- restore: Restore from a backup file
- list: List available backups
- prune: Remove old backups (keep N most recent)
"""

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))
BACKUP_DIR = os.environ.get('CRM_BACKUP_DIR', os.path.expanduser('~/.local/share/agent-crm/backups'))

def ensure_backup_dir():
    """Create backup directory if needed."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

def get_backup_files() -> list[dict]:
    """Get list of backup files with metadata."""
    ensure_backup_dir()
    backups = []
    for f in Path(BACKUP_DIR).glob('crm_backup_*.db'):
        stat = f.stat()
        # Parse timestamp from filename
        try:
            ts_str = f.stem.replace('crm_backup_', '')
            ts = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
        except:
            ts = datetime.fromtimestamp(stat.st_mtime)
        
        backups.append({
            'path': str(f),
            'filename': f.name,
            'size_bytes': stat.st_size,
            'size_human': format_size(stat.st_size),
            'created_at': ts.isoformat(),
            'age_days': (datetime.now() - ts).days
        })
    
    return sorted(backups, key=lambda x: x['created_at'], reverse=True)

def format_size(bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f'{bytes:.1f} {unit}'
        bytes /= 1024
    return f'{bytes:.1f} TB'

def backup_database(note: str = None) -> dict:
    """Create a backup of the database."""
    if not Path(DB_PATH).exists():
        return {'error': 'Database not found', 'path': DB_PATH}
    
    ensure_backup_dir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'crm_backup_{timestamp}.db')
    
    # Use SQLite backup API for consistency
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    source.close()
    dest.close()
    
    # Get stats
    stat = Path(backup_path).stat()
    
    result = {
        'status': 'success',
        'path': backup_path,
        'size': format_size(stat.st_size),
        'timestamp': timestamp
    }
    
    if note:
        # Save note alongside backup
        note_path = backup_path + '.note'
        with open(note_path, 'w') as f:
            f.write(note)
        result['note'] = note
    
    return result

def restore_database(backup_path: str, confirm: bool = False) -> dict:
    """Restore database from backup."""
    if not Path(backup_path).exists():
        return {'error': 'Backup file not found', 'path': backup_path}
    
    if not confirm:
        return {
            'status': 'confirmation_required',
            'message': 'This will overwrite the current database. Pass --confirm to proceed.',
            'backup_path': backup_path,
            'current_db': DB_PATH
        }
    
    # Create safety backup first
    if Path(DB_PATH).exists():
        safety_backup = backup_database('Pre-restore safety backup')
        if 'error' in safety_backup:
            return {'error': 'Failed to create safety backup', 'details': safety_backup}
    
    # Restore
    shutil.copy2(backup_path, DB_PATH)
    
    # Verify
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT COUNT(*) FROM contacts")
        conn.close()
    except Exception as e:
        return {'error': 'Restored database appears corrupt', 'details': str(e)}
    
    return {
        'status': 'success',
        'message': 'Database restored successfully',
        'restored_from': backup_path,
        'safety_backup': safety_backup.get('path') if Path(DB_PATH).exists() else None
    }

def list_backups() -> dict:
    """List all available backups."""
    backups = get_backup_files()
    
    # Load notes
    for b in backups:
        note_path = b['path'] + '.note'
        if Path(note_path).exists():
            b['note'] = Path(note_path).read_text().strip()
    
    return {
        'count': len(backups),
        'backups': backups,
        'backup_dir': BACKUP_DIR
    }

def prune_backups(keep: int = 10) -> dict:
    """Remove old backups, keeping N most recent."""
    backups = get_backup_files()
    
    if len(backups) <= keep:
        return {
            'status': 'success',
            'message': f'No pruning needed. {len(backups)} backups exist, keeping {keep}.',
            'removed': 0
        }
    
    to_remove = backups[keep:]
    removed = []
    
    for b in to_remove:
        try:
            Path(b['path']).unlink()
            # Also remove note if exists
            note_path = b['path'] + '.note'
            if Path(note_path).exists():
                Path(note_path).unlink()
            removed.append(b['filename'])
        except Exception as e:
            pass
    
    return {
        'status': 'success',
        'kept': keep,
        'removed': len(removed),
        'removed_files': removed
    }

def main():
    parser = argparse.ArgumentParser(description='CRM backup and restore')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # backup
    p = subparsers.add_parser('backup', help='Create a backup')
    p.add_argument('--note', '-n', help='Note to attach to backup')
    
    # restore
    p = subparsers.add_parser('restore', help='Restore from backup')
    p.add_argument('path', nargs='?', help='Backup file path (uses latest if not specified)')
    p.add_argument('--confirm', action='store_true', help='Confirm overwrite')
    
    # list
    p = subparsers.add_parser('list', help='List backups')
    
    # prune
    p = subparsers.add_parser('prune', help='Remove old backups')
    p.add_argument('--keep', '-k', type=int, default=10, help='Number of backups to keep')
    
    args = parser.parse_args()
    
    if args.command == 'backup':
        result = backup_database(args.note)
    elif args.command == 'restore':
        path = args.path
        if not path:
            # Use latest backup
            backups = get_backup_files()
            if not backups:
                result = {'error': 'No backups found'}
            else:
                path = backups[0]['path']
                result = restore_database(path, args.confirm)
        else:
            result = restore_database(path, args.confirm)
    elif args.command == 'list':
        result = list_backups()
    elif args.command == 'prune':
        result = prune_backups(args.keep)
    
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
