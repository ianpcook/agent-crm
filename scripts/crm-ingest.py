#!/usr/bin/env python3
"""
CRM Ingest - Parse unstructured text into CRM actions

Takes emails, meeting notes, voice transcripts and extracts:
- New contacts
- Interactions to log
- Deal updates
- Tasks to create

Outputs a JSON plan for agent review before execution.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

def extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))

def extract_phones(text: str) -> list[str]:
    """Extract phone numbers from text."""
    patterns = [
        r'\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
        r'\+[0-9]{1,3}[-.\s]?[0-9]{6,14}'
    ]
    phones = []
    for pattern in patterns:
        phones.extend(re.findall(pattern, text))
    return list(set(phones))

def extract_money(text: str) -> list[dict]:
    """Extract monetary amounts."""
    patterns = [
        (r'\$([0-9,]+(?:\.[0-9]{2})?)\s*(?:k|K)', lambda m: float(m.group(1).replace(',', '')) * 1000),
        (r'\$([0-9,]+(?:\.[0-9]{2})?)\s*(?:m|M)', lambda m: float(m.group(1).replace(',', '')) * 1000000),
        (r'\$([0-9,]+(?:\.[0-9]{2})?)', lambda m: float(m.group(1).replace(',', ''))),
        (r'([0-9,]+(?:\.[0-9]{2})?)\s*(?:dollars|USD)', lambda m: float(m.group(1).replace(',', ''))),
    ]
    amounts = []
    for pattern, converter in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            amounts.append({
                'raw': match.group(0),
                'value': converter(match),
                'currency': 'USD'
            })
    return amounts

def extract_dates(text: str) -> list[str]:
    """Extract date references."""
    patterns = [
        r'(?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        r'(?:next|this)\s+week',
        r'(?:next|this)\s+month',
        r'(?:in\s+)?[0-9]+\s+(?:day|week|month)s?(?:\s+from\s+now)?',
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+[0-9]{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*[0-9]{4})?',
        r'[0-9]{1,2}/[0-9]{1,2}(?:/[0-9]{2,4})?',
        r'tomorrow',
        r'today',
        r'end of (?:week|month|quarter|year)',
    ]
    dates = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            dates.append(match.group(0).strip())
    return list(set(dates))

def extract_names(text: str) -> list[dict]:
    """Extract potential person names with context."""
    names = []
    seen = set()
    
    # Common false positives to filter out
    stop_words = {
        'I', 'We', 'They', 'He', 'She', 'The', 'This', 'That', 'What', 'When', 
        'Where', 'How', 'If', 'But', 'And', 'For', 'Just', 'Also', 'Very', 
        'Really', 'Thanks', 'Thank', 'Hello', 'Hi', 'Hey', 'Best', 'Regards',
        'Sincerely', 'Cheers', 'Dear', 'To', 'From', 'Subject', 'Re', 'Fwd'
    }
    
    def add_name(name: str, role: str = None, company: str = None):
        name = name.strip()
        if not name or name in stop_words or len(name) <= 2:
            return
        # Filter out single words that are likely not names
        if ' ' not in name and len(name) < 4:
            return
        
        # If we've seen this name, update with new info (role/company)
        if name in seen:
            for entry in names:
                if entry['name'] == name:
                    if role and 'role' not in entry:
                        entry['role'] = role
                    if company and 'company' not in entry:
                        entry['company'] = company
            return
        
        entry = {'name': name}
        if role:
            entry['role'] = role
        if company:
            entry['company'] = company
        names.append(entry)
        seen.add(name)
    
    # Pattern 1: Name followed by "Title, Company" on next line (most specific first)
    # "Alex Rivera\nFounder, DataStack"
    title_company_pattern = r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\n\s*(CEO|CTO|COO|CFO|VP|Director|Manager|Founder|Co-Founder|President|Head of [A-Za-z]+|[A-Z][a-z]+ Engineer|[A-Z][a-z]+ Manager)[,\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)'
    for match in re.finditer(title_company_pattern, text, re.MULTILINE):
        name = match.group(1)
        role = match.group(2).strip()
        company = match.group(3).strip()
        add_name(name, role=role, company=company)
    
    # Pattern 1b: Name followed by just title on next line (no company)
    title_pattern = r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\n\s*(CEO|CTO|COO|CFO|VP|Director|Manager|Founder|Co-Founder|President|Head of [A-Za-z]+)\s*$'
    for match in re.finditer(title_pattern, text, re.MULTILINE):
        name = match.group(1)
        role = match.group(2).strip()
        add_name(name, role=role)
    
    # Pattern 2: Email signature - name on line after closing
    # "Best,\nAlex Rivera" or "Thanks,\nJohn Smith"
    sig_pattern = r'(?:Best|Thanks|Regards|Cheers|Sincerely|Warmly|Yours)[,.]?\s*\n+([A-Z][a-z]+\s+[A-Z][a-z]+)'
    for match in re.finditer(sig_pattern, text, re.MULTILINE):
        add_name(match.group(1))
    
    # Pattern 3: "Name, Title at Company" or "Name, Title"
    inline_title = r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*,\s*(CEO|CTO|COO|CFO|VP|Director|Manager|Founder|Co-Founder|President|Head of [A-Za-z]+|[A-Z][a-z]+ Engineer|[A-Z][a-z]+ Manager)(?:\s+(?:at|@)\s+([A-Z][A-Za-z]+))?'
    for match in re.finditer(inline_title, text):
        name = match.group(1)
        role = match.group(2)
        company = match.group(3) if len(match.groups()) > 2 else None
        add_name(name, role=role, company=company)
    
    # Pattern 4: "talked to/met with/spoke with Name"
    action_pattern = r'(?:talked to|met with|spoke with|call with|meeting with|heard from|email from|message from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
    for match in re.finditer(action_pattern, text, re.IGNORECASE):
        add_name(match.group(1))
    
    # Pattern 5: "Name from/at Company" - full two-word name
    company_pattern = r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:from|at|with|@)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)'
    for match in re.finditer(company_pattern, text):
        name = match.group(1)
        company = match.group(2)
        add_name(name, company=company)
    
    # Pattern 5b: "FirstName from/at Company" - single name with company context
    company_pattern_single = r'\b([A-Z][a-z]+)\s+(?:from|at|with|@)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)'
    for match in re.finditer(company_pattern_single, text):
        name = match.group(1)
        company = match.group(2)
        if name not in stop_words and len(name) >= 4:
            add_name(name, company=company)
    
    # Pattern 6: Email "From:" header with name
    from_pattern = r'From:\s*(?:"?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"?\s*<|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+[<\[])'
    for match in re.finditer(from_pattern, text):
        name = match.group(1) or match.group(2)
        if name:
            add_name(name)
    
    # Pattern 7: Standalone two-word capitalized name on its own line (likely signature)
    standalone = r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*$'
    lines = text.split('\n')
    for i, line in enumerate(lines):
        match = re.match(standalone, line.strip())
        if match:
            name = match.group(1)
            # Check if next line looks like a title or company
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^(CEO|CTO|COO|CFO|VP|Director|Founder|Manager|Engineer|Head|President)', next_line):
                    add_name(name, role=next_line.split(',')[0].strip())
                elif re.match(r'^[A-Z]', next_line) and len(next_line) < 50:
                    add_name(name, company=next_line.split(',')[0].strip())
                else:
                    add_name(name)
            else:
                add_name(name)
    
    return names

def extract_companies(text: str) -> list[str]:
    """Extract company names."""
    # Look for patterns like "at Acme Corp" or "from TechCo"
    patterns = [
        r'(?:at|from|with|for)\s+([A-Z][a-zA-Z]+(?:\s+(?:Corp|Inc|LLC|Ltd|Co|Labs?|AI|Tech|Software|Systems|Solutions))?)',
        r'([A-Z][a-zA-Z]+(?:\.(?:com|io|ai|co)))',
    ]
    
    companies = []
    seen = set()
    # Common false positives
    stop_words = {'I', 'We', 'They', 'He', 'She', 'The', 'This', 'That', 'What', 'When', 'Where', 'How', 'If', 'But', 'And', 'For', 'Just', 'Also', 'Very', 'Really', 'Thanks', 'Thank', 'Hello', 'Hi', 'Hey'}
    
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            company = match.group(1).strip()
            if company not in seen and company not in stop_words and len(company) > 2:
                companies.append(company)
                seen.add(company)
    
    return companies

def detect_interaction_type(text: str) -> str:
    """Detect the type of interaction from text."""
    text_lower = text.lower()
    
    if any(x in text_lower for x in ['subject:', 'from:', 'to:', 're:', 'fwd:']):
        return 'email'
    if any(x in text_lower for x in ['called', 'call with', 'phone call', 'spoke with', 'talked to']):
        return 'call'
    if any(x in text_lower for x in ['meeting', 'met with', 'conference', 'zoom', 'teams']):
        return 'meeting'
    if any(x in text_lower for x in ['linkedin', 'connected on']):
        return 'linkedin'
    if any(x in text_lower for x in ['texted', 'sms', 'imessage', 'whatsapp']):
        return 'text'
    
    return 'note'

def detect_deal_signals(text: str) -> dict:
    """Detect signals about deals."""
    text_lower = text.lower()
    
    signals = {
        'stage_hints': [],
        'positive': [],
        'negative': [],
        'actions': []
    }
    
    # Stage hints
    if any(x in text_lower for x in ['interested', 'wants to learn more', 'requested demo']):
        signals['stage_hints'].append('qualified')
    if any(x in text_lower for x in ['sent proposal', 'sending quote', 'pricing']):
        signals['stage_hints'].append('proposal')
    if any(x in text_lower for x in ['negotiating', 'reviewing contract', 'legal review', 'redlines']):
        signals['stage_hints'].append('negotiation')
    if any(x in text_lower for x in ['signed', 'closed', 'won', 'agreed', 'confirmed']):
        signals['stage_hints'].append('won')
    if any(x in text_lower for x in ['passed', 'declined', 'lost', 'went with competitor', 'no budget']):
        signals['stage_hints'].append('lost')
    
    # Positive signals
    if any(x in text_lower for x in ['excited', 'very interested', 'love it', 'great fit', 'impressed']):
        signals['positive'].append('high_interest')
    if any(x in text_lower for x in ['decision maker', 'can approve', 'has budget']):
        signals['positive'].append('authority')
    
    # Negative signals  
    if any(x in text_lower for x in ['not a priority', 'maybe later', 'next quarter', 'no budget']):
        signals['negative'].append('timing_issue')
    if any(x in text_lower for x in ['need to check', 'run it by', 'get approval']):
        signals['negative'].append('no_authority')
    
    # Follow-up actions
    if any(x in text_lower for x in ['will send', 'sending', 'follow up', 'get back to']):
        signals['actions'].append('follow_up_needed')
    if any(x in text_lower for x in ['schedule', 'set up a', 'book a']):
        signals['actions'].append('meeting_to_schedule')
    
    return signals

def extract_tasks(text: str) -> list[dict]:
    """Extract potential tasks/action items."""
    tasks = []
    
    # Common action patterns
    patterns = [
        r'(?:need to|should|will|must|have to)\s+([^.!?\n]+)',
        r'(?:follow up|send|schedule|call|email|review|check)\s+([^.!?\n]+)',
        r'(?:action item|todo|task):\s*([^.!?\n]+)',
        r'(?:by|before|due)\s+((?:monday|tuesday|wednesday|thursday|friday|next week|tomorrow|[a-z]+ [0-9]+)[^.!?\n]*)',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            task_text = match.group(1).strip()
            if len(task_text) > 10 and len(task_text) < 200:
                tasks.append({
                    'title': task_text[:100],
                    'source': match.group(0)
                })
    
    return tasks[:5]  # Limit to 5 tasks

def parse_email(text: str) -> dict:
    """Parse email-specific structure."""
    result = {
        'from': None,
        'to': None,
        'subject': None,
        'date': None,
        'body': text
    }
    
    lines = text.split('\n')
    body_start = 0
    
    for i, line in enumerate(lines):
        if line.lower().startswith('from:'):
            result['from'] = line[5:].strip()
            body_start = i + 1
        elif line.lower().startswith('to:'):
            result['to'] = line[3:].strip()
            body_start = i + 1
        elif line.lower().startswith('subject:'):
            result['subject'] = line[8:].strip()
            body_start = i + 1
        elif line.lower().startswith('date:'):
            result['date'] = line[5:].strip()
            body_start = i + 1
        elif line.strip() == '' and body_start > 0:
            result['body'] = '\n'.join(lines[i+1:])
            break
    
    return result

def ingest(text: str, source_type: str = 'auto') -> dict:
    """Main ingestion function - extract all structured data from text."""
    
    if source_type == 'auto':
        source_type = detect_interaction_type(text)
    
    # Parse email structure if applicable
    email_data = None
    if source_type == 'email':
        email_data = parse_email(text)
    
    # Extract all entities
    plan = {
        'source_type': source_type,
        'extracted_at': datetime.now().isoformat(),
        'raw_length': len(text),
        
        'contacts': {
            'names': extract_names(text),
            'emails': extract_emails(text),
            'phones': extract_phones(text),
            'companies': extract_companies(text)
        },
        
        'interaction': {
            'type': source_type,
            'direction': 'inbound' if email_data and email_data.get('to') else 'outbound',
            'summary': None,  # Agent should generate this
            'occurred_at': email_data.get('date') if email_data else 'today'
        },
        
        'deal_signals': detect_deal_signals(text),
        'money': extract_money(text),
        'dates': extract_dates(text),
        'potential_tasks': extract_tasks(text),
        
        'email_metadata': email_data,
        
        'suggested_actions': []
    }
    
    # Generate suggested actions
    if plan['contacts']['names']:
        for name_info in plan['contacts']['names']:
            plan['suggested_actions'].append({
                'action': 'create_or_update_contact',
                'data': name_info
            })
    
    if plan['money']:
        plan['suggested_actions'].append({
            'action': 'create_or_update_deal',
            'data': {
                'value': plan['money'][0]['value'],
                'signals': plan['deal_signals']
            }
        })
    
    if plan['deal_signals']['stage_hints']:
        plan['suggested_actions'].append({
            'action': 'update_deal_stage',
            'data': {
                'suggested_stage': plan['deal_signals']['stage_hints'][0]
            }
        })
    
    plan['suggested_actions'].append({
        'action': 'log_interaction',
        'data': {
            'type': source_type,
            'needs_summary': True
        }
    })
    
    for task in plan['potential_tasks'][:3]:
        plan['suggested_actions'].append({
            'action': 'create_task',
            'data': task
        })
    
    return plan

def main():
    parser = argparse.ArgumentParser(description='Parse unstructured text into CRM actions')
    parser.add_argument('--type', '-t', choices=['auto', 'email', 'call', 'meeting', 'note'],
                       default='auto', help='Source type')
    parser.add_argument('--file', '-f', help='Read from file instead of stdin')
    parser.add_argument('--text', help='Text to parse (alternative to stdin/file)')
    
    args = parser.parse_args()
    
    # Get input text
    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text()
    else:
        text = sys.stdin.read()
    
    if not text.strip():
        print(json.dumps({'error': 'No input text provided'}))
        sys.exit(1)
    
    result = ingest(text, args.type)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
