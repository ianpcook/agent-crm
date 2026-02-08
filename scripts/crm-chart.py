#!/usr/bin/env python3
"""
CRM Charts - Generate visual reports from CRM data

Charts:
- pipeline: Deal value by stage (horizontal bar)
- forecast: Expected closes by month (bar)
- activity: Interactions over time (line)
- funnel: Stage conversion funnel (funnel chart)

Output: PNG image suitable for sending via chat
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
VENV_DIR = SCRIPT_DIR / '.venv'
VENV_PYTHON = VENV_DIR / 'bin' / 'python'

def ensure_venv():
    """Ensure venv exists with matplotlib, re-exec if needed."""
    # If we're already in the venv, continue
    if sys.prefix != sys.base_prefix:
        return True
    
    # Check if venv exists
    if not VENV_PYTHON.exists():
        print(json.dumps({'status': 'installing', 'message': 'Setting up chart dependencies...'}))
        subprocess.run([sys.executable, '-m', 'venv', str(VENV_DIR)], check=True)
        subprocess.run([str(VENV_PYTHON), '-m', 'pip', 'install', '--quiet', 'matplotlib'], check=True)
    
    # Re-exec with venv python
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

# Ensure we're in venv before importing matplotlib
ensure_venv()

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
HAS_MATPLOTLIB = True

DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))
OUTPUT_DIR = os.environ.get('CRM_CHARTS_DIR', os.path.expanduser('~/.local/share/agent-crm/charts'))

# Color scheme
COLORS = {
    'lead': '#94a3b8',       # slate
    'qualified': '#60a5fa',  # blue
    'proposal': '#a78bfa',   # purple
    'negotiation': '#fbbf24', # amber
    'won': '#34d399',        # green
    'lost': '#f87171',       # red
    'primary': '#3b82f6',    # blue
    'secondary': '#8b5cf6',  # violet
    'accent': '#06b6d4',     # cyan
}

STAGE_ORDER = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost']

def get_db() -> sqlite3.Connection:
    """Get database connection."""
    if not Path(DB_PATH).exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_output_dir():
    """Create output directory if needed."""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def format_currency(value):
    """Format as currency."""
    if value >= 1_000_000:
        return f'${value/1_000_000:.1f}M'
    elif value >= 1_000:
        return f'${value/1_000:.0f}K'
    else:
        return f'${value:.0f}'

def chart_pipeline(output_path: str = None) -> str:
    """Generate pipeline chart - deals by stage."""
    conn = get_db()
    if not conn:
        return None
    
    rows = conn.execute("""
        SELECT stage, COUNT(*) as count, COALESCE(SUM(value), 0) as total_value
        FROM deals
        WHERE stage NOT IN ('won', 'lost')
        GROUP BY stage
    """).fetchall()
    conn.close()
    
    if not rows:
        return None
    
    # Organize by stage order
    data = {r['stage']: {'count': r['count'], 'value': r['total_value']} for r in rows}
    stages = [s for s in STAGE_ORDER if s in data]
    values = [data[s]['value'] for s in stages]
    counts = [data[s]['count'] for s in stages]
    colors = [COLORS.get(s, COLORS['primary']) for s in stages]
    
    # Create chart
    fig, ax = plt.subplots(figsize=(10, 5))
    
    y_pos = range(len(stages))
    bars = ax.barh(y_pos, values, color=colors, height=0.6)
    
    # Labels
    ax.set_yticks(y_pos)
    ax.set_yticklabels([s.title() for s in stages], fontsize=12)
    ax.invert_yaxis()
    
    # Value labels on bars
    for i, (bar, value, count) in enumerate(zip(bars, values, counts)):
        width = bar.get_width()
        label = f'{format_currency(value)} ({count} deal{"s" if count != 1 else ""})'
        if width > max(values) * 0.3:
            ax.text(width - max(values) * 0.02, bar.get_y() + bar.get_height()/2,
                   label, ha='right', va='center', color='white', fontweight='bold', fontsize=11)
        else:
            ax.text(width + max(values) * 0.02, bar.get_y() + bar.get_height()/2,
                   label, ha='left', va='center', color='#1f2937', fontsize=11)
    
    # Styling
    ax.set_xlabel('Deal Value', fontsize=12)
    ax.set_title('Pipeline by Stage', fontsize=16, fontweight='bold', pad=20)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_xlim(0, max(values) * 1.3 if values else 1)
    
    # Total annotation
    total = sum(values)
    ax.annotate(f'Total Pipeline: {format_currency(total)}',
                xy=(0.98, 0.02), xycoords='axes fraction',
                ha='right', va='bottom', fontsize=12, fontweight='bold',
                color=COLORS['primary'])
    
    plt.tight_layout()
    
    # Save
    ensure_output_dir()
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f'pipeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

def chart_forecast(months: int = 6, output_path: str = None) -> str:
    """Generate forecast chart - expected closes by month."""
    conn = get_db()
    if not conn:
        return None
    
    rows = conn.execute("""
        SELECT 
            strftime('%Y-%m', expected_close) as month,
            COUNT(*) as count,
            COALESCE(SUM(value), 0) as total_value,
            COALESCE(SUM(value * COALESCE(probability, 50) / 100.0), 0) as weighted_value
        FROM deals
        WHERE stage NOT IN ('won', 'lost')
        AND expected_close IS NOT NULL
        AND expected_close >= date('now')
        GROUP BY month
        ORDER BY month
        LIMIT ?
    """, (months,)).fetchall()
    conn.close()
    
    if not rows:
        return None
    
    months_list = [r['month'] for r in rows]
    values = [r['total_value'] for r in rows]
    weighted = [r['weighted_value'] for r in rows]
    counts = [r['count'] for r in rows]
    
    # Create chart
    fig, ax = plt.subplots(figsize=(10, 5))
    
    x = range(len(months_list))
    width = 0.35
    
    bars1 = ax.bar([i - width/2 for i in x], values, width, label='Total Value', color=COLORS['primary'], alpha=0.8)
    bars2 = ax.bar([i + width/2 for i in x], weighted, width, label='Weighted Value', color=COLORS['secondary'], alpha=0.8)
    
    # Labels
    ax.set_xticks(x)
    ax.set_xticklabels([datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months_list], fontsize=11)
    
    # Value labels
    for bar, val, count in zip(bars1, values, counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values) * 0.02,
               f'{count}', ha='center', va='bottom', fontsize=10, color='#6b7280')
    
    # Styling
    ax.set_ylabel('Deal Value', fontsize=12)
    ax.set_title('Forecast: Expected Closes by Month', fontsize=16, fontweight='bold', pad=20)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(loc='upper right')
    
    # Format y-axis as currency
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_currency(x)))
    
    plt.tight_layout()
    
    # Save
    ensure_output_dir()
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f'forecast_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

def chart_activity(days: int = 30, output_path: str = None) -> str:
    """Generate activity chart - interactions over time."""
    conn = get_db()
    if not conn:
        return None
    
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    rows = conn.execute("""
        SELECT 
            date(occurred_at) as day,
            type,
            COUNT(*) as count
        FROM interactions
        WHERE occurred_at >= ?
        GROUP BY day, type
        ORDER BY day
    """, (since,)).fetchall()
    conn.close()
    
    if not rows:
        return None
    
    # Organize data by day and type
    from collections import defaultdict
    daily = defaultdict(lambda: defaultdict(int))
    types = set()
    for r in rows:
        daily[r['day']][r['type']] = r['count']
        types.add(r['type'])
    
    days_list = sorted(daily.keys())
    types = sorted(types)
    
    # Create chart
    fig, ax = plt.subplots(figsize=(12, 5))
    
    type_colors = {
        'email': COLORS['primary'],
        'call': COLORS['secondary'],
        'meeting': COLORS['accent'],
        'note': '#94a3b8',
        'linkedin': '#0077b5',
        'text': '#25d366',
    }
    
    bottom = [0] * len(days_list)
    for t in types:
        values = [daily[d][t] for d in days_list]
        color = type_colors.get(t, '#6b7280')
        ax.bar(range(len(days_list)), values, bottom=bottom, label=t.title(), color=color, alpha=0.8)
        bottom = [b + v for b, v in zip(bottom, values)]
    
    # Labels
    # Show every Nth label to avoid crowding
    step = max(1, len(days_list) // 10)
    ax.set_xticks(range(0, len(days_list), step))
    ax.set_xticklabels([datetime.strptime(days_list[i], '%Y-%m-%d').strftime('%m/%d') 
                        for i in range(0, len(days_list), step)], fontsize=10)
    
    # Styling
    ax.set_ylabel('Interactions', fontsize=12)
    ax.set_title(f'Activity: Last {days} Days', fontsize=16, fontweight='bold', pad=20)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(loc='upper left', ncol=len(types))
    
    plt.tight_layout()
    
    # Save
    ensure_output_dir()
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f'activity_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

def chart_winloss(days: int = 90, output_path: str = None) -> str:
    """Generate win/loss chart."""
    conn = get_db()
    if not conn:
        return None
    
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    rows = conn.execute("""
        SELECT 
            strftime('%Y-%m', closed_at) as month,
            stage,
            COUNT(*) as count,
            COALESCE(SUM(value), 0) as total_value
        FROM deals
        WHERE stage IN ('won', 'lost')
        AND closed_at >= ?
        GROUP BY month, stage
        ORDER BY month
    """, (since,)).fetchall()
    conn.close()
    
    if not rows:
        return None
    
    # Organize data
    from collections import defaultdict
    monthly = defaultdict(lambda: {'won': 0, 'lost': 0, 'won_count': 0, 'lost_count': 0})
    for r in rows:
        if r['stage'] == 'won':
            monthly[r['month']]['won'] = r['total_value']
            monthly[r['month']]['won_count'] = r['count']
        else:
            monthly[r['month']]['lost'] = r['total_value']
            monthly[r['month']]['lost_count'] = r['count']
    
    months_list = sorted(monthly.keys())
    won_values = [monthly[m]['won'] for m in months_list]
    lost_values = [monthly[m]['lost'] for m in months_list]
    
    # Create chart
    fig, ax = plt.subplots(figsize=(10, 5))
    
    x = range(len(months_list))
    width = 0.35
    
    bars1 = ax.bar([i - width/2 for i in x], won_values, width, label='Won', color=COLORS['won'])
    bars2 = ax.bar([i + width/2 for i in x], lost_values, width, label='Lost', color=COLORS['lost'])
    
    # Labels
    ax.set_xticks(x)
    ax.set_xticklabels([datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months_list], fontsize=11)
    
    # Styling
    ax.set_ylabel('Deal Value', fontsize=12)
    ax.set_title('Win/Loss Analysis', fontsize=16, fontweight='bold', pad=20)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(loc='upper right')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_currency(x)))
    
    # Win rate annotation
    total_won = sum(won_values)
    total_lost = sum(lost_values)
    if total_won + total_lost > 0:
        win_rate = total_won / (total_won + total_lost) * 100
        ax.annotate(f'Win Rate: {win_rate:.0f}%',
                    xy=(0.02, 0.98), xycoords='axes fraction',
                    ha='left', va='top', fontsize=12, fontweight='bold',
                    color=COLORS['won'])
    
    plt.tight_layout()
    
    # Save
    ensure_output_dir()
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f'winloss_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

def chart_summary(output_path: str = None) -> str:
    """Generate summary dashboard with multiple metrics."""
    conn = get_db()
    if not conn:
        return None
    
    # Get all metrics
    stats = {}
    
    # Pipeline by stage
    rows = conn.execute("""
        SELECT stage, COUNT(*) as count, COALESCE(SUM(value), 0) as value
        FROM deals WHERE stage NOT IN ('won', 'lost')
        GROUP BY stage
    """).fetchall()
    stats['pipeline'] = {r['stage']: {'count': r['count'], 'value': r['value']} for r in rows}
    
    # Won this month
    month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    row = conn.execute("""
        SELECT COUNT(*) as count, COALESCE(SUM(value), 0) as value
        FROM deals WHERE stage = 'won' AND closed_at >= ?
    """, (month_start,)).fetchone()
    stats['won_month'] = {'count': row['count'], 'value': row['value']}
    
    # Tasks
    row = conn.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE completed_at IS NULL) as pending,
            COUNT(*) FILTER (WHERE completed_at IS NULL AND due_at < datetime('now')) as overdue
        FROM tasks
    """).fetchone()
    stats['tasks'] = {'pending': row['pending'], 'overdue': row['overdue']}
    
    # Contacts
    row = conn.execute("SELECT COUNT(*) as count FROM contacts").fetchone()
    stats['contacts'] = row['count']
    
    conn.close()
    
    # Create dashboard
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # Pipeline pie chart
    ax = axes[0, 0]
    if stats['pipeline']:
        stages = [s for s in STAGE_ORDER if s in stats['pipeline']]
        values = [stats['pipeline'][s]['value'] for s in stages]
        colors = [COLORS.get(s, '#6b7280') for s in stages]
        
        wedges, texts, autotexts = ax.pie(values, labels=[s.title() for s in stages], 
                                          colors=colors, autopct='%1.0f%%',
                                          pctdistance=0.75)
        ax.set_title('Pipeline Distribution', fontsize=14, fontweight='bold')
    else:
        ax.text(0.5, 0.5, 'No pipeline data', ha='center', va='center', fontsize=14)
        ax.set_title('Pipeline Distribution', fontsize=14, fontweight='bold')
    
    # Key metrics
    ax = axes[0, 1]
    ax.axis('off')
    
    total_pipeline = sum(d['value'] for d in stats['pipeline'].values())
    metrics_text = f"""
    📊 Key Metrics
    
    Pipeline Value: {format_currency(total_pipeline)}
    Open Deals: {sum(d['count'] for d in stats['pipeline'].values())}
    
    Won This Month: {format_currency(stats['won_month']['value'])}
    ({stats['won_month']['count']} deals)
    
    Contacts: {stats['contacts']}
    
    Tasks Pending: {stats['tasks']['pending']}
    Tasks Overdue: {stats['tasks']['overdue']}
    """
    ax.text(0.1, 0.9, metrics_text, transform=ax.transAxes, fontsize=13,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#f1f5f9', alpha=0.8))
    
    # Stage breakdown bar
    ax = axes[1, 0]
    if stats['pipeline']:
        stages = [s for s in STAGE_ORDER if s in stats['pipeline']]
        values = [stats['pipeline'][s]['value'] for s in stages]
        counts = [stats['pipeline'][s]['count'] for s in stages]
        colors = [COLORS.get(s, '#6b7280') for s in stages]
        
        bars = ax.barh(range(len(stages)), values, color=colors)
        ax.set_yticks(range(len(stages)))
        ax.set_yticklabels([s.title() for s in stages])
        ax.invert_yaxis()
        ax.set_title('Value by Stage', fontsize=14, fontweight='bold')
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_currency(x)))
        
        for bar, count in zip(bars, counts):
            ax.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height()/2,
                   f'{count}', va='center', fontsize=10)
    
    # Tasks status
    ax = axes[1, 1]
    task_labels = ['Pending', 'Overdue']
    task_values = [stats['tasks']['pending'] - stats['tasks']['overdue'], stats['tasks']['overdue']]
    task_colors = [COLORS['primary'], COLORS['lost']]
    
    if sum(task_values) > 0:
        ax.pie(task_values, labels=task_labels, colors=task_colors, autopct='%1.0f%%',
               startangle=90)
    else:
        ax.text(0.5, 0.5, 'No tasks', ha='center', va='center', fontsize=14)
    ax.set_title('Task Status', fontsize=14, fontweight='bold')
    
    plt.suptitle(f'CRM Dashboard — {datetime.now().strftime("%B %d, %Y")}', 
                 fontsize=18, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    # Save
    ensure_output_dir()
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f'summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description='Generate CRM charts')
    parser.add_argument('chart', choices=['pipeline', 'forecast', 'activity', 'winloss', 'summary'],
                       help='Chart type to generate')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--days', '-d', type=int, default=30, help='Days to analyze (activity/winloss)')
    parser.add_argument('--months', '-m', type=int, default=6, help='Months to forecast')
    
    args = parser.parse_args()
    
    chart_funcs = {
        'pipeline': lambda: chart_pipeline(args.output),
        'forecast': lambda: chart_forecast(args.months, args.output),
        'activity': lambda: chart_activity(args.days, args.output),
        'winloss': lambda: chart_winloss(args.days, args.output),
        'summary': lambda: chart_summary(args.output),
    }
    
    output_path = chart_funcs[args.chart]()
    
    if output_path:
        print(json.dumps({'status': 'success', 'chart': args.chart, 'path': output_path}))
    else:
        print(json.dumps({'status': 'error', 'message': 'No data to chart or database not found'}))
        sys.exit(1)

if __name__ == '__main__':
    main()
