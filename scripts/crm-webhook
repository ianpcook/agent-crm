#!/usr/bin/env python3
"""
CRM Webhook Server - Ingest leads from external forms

Accepts POST requests with contact/lead data and creates CRM entries.
Supports common form formats: Typeform, Tally, raw JSON.

Run: crm-webhook --port 8901
Then configure form webhooks to POST to http://localhost:8901/lead
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB_PATH = os.environ.get('CRM_DB', os.path.expanduser('~/.local/share/agent-crm/crm.db'))
CRM_SCRIPT = Path(__file__).parent / 'crm'
LOG_FILE = os.path.expanduser('~/.local/share/agent-crm/webhook.log')

def log(message: str):
    """Append to log file."""
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(f"{datetime.now().isoformat()} {message}\n")

def parse_typeform(data: dict) -> dict:
    """Parse Typeform webhook payload."""
    answers = data.get('form_response', {}).get('answers', [])
    
    result = {'source': 'typeform'}
    field_map = {
        'email': ['email'],
        'name': ['short_text', 'long_text'],
        'phone': ['phone_number'],
    }
    
    for answer in answers:
        field_type = answer.get('type')
        field_title = answer.get('field', {}).get('title', '').lower()
        
        # Try to map by field title
        if 'email' in field_title:
            result['email'] = answer.get('email')
        elif 'name' in field_title:
            result['name'] = answer.get('text')
        elif 'phone' in field_title:
            result['phone'] = answer.get('phone_number')
        elif 'company' in field_title:
            result['company'] = answer.get('text')
        elif 'message' in field_title or 'note' in field_title:
            result['notes'] = answer.get('text')
    
    # Fallback: first short_text is name, first email is email
    if 'name' not in result:
        for answer in answers:
            if answer.get('type') == 'short_text' and answer.get('text'):
                result['name'] = answer.get('text')
                break
    
    return result

def parse_tally(data: dict) -> dict:
    """Parse Tally webhook payload."""
    fields = data.get('data', {}).get('fields', [])
    
    result = {'source': 'tally'}
    
    for field in fields:
        label = field.get('label', '').lower()
        value = field.get('value')
        
        if not value:
            continue
            
        if 'email' in label:
            result['email'] = value
        elif 'name' in label:
            result['name'] = value
        elif 'phone' in label:
            result['phone'] = value
        elif 'company' in label:
            result['company'] = value
        elif 'message' in label or 'note' in label:
            result['notes'] = value
    
    return result

def parse_generic(data: dict) -> dict:
    """Parse generic JSON payload."""
    result = {'source': 'webhook'}
    
    # Common field names
    field_map = {
        'name': ['name', 'full_name', 'fullName', 'contact_name', 'contactName'],
        'email': ['email', 'email_address', 'emailAddress', 'mail'],
        'phone': ['phone', 'phone_number', 'phoneNumber', 'tel', 'telephone'],
        'company': ['company', 'company_name', 'companyName', 'organization', 'org'],
        'notes': ['notes', 'message', 'comment', 'description', 'body'],
        'role': ['role', 'title', 'job_title', 'jobTitle', 'position'],
    }
    
    for target, sources in field_map.items():
        for source in sources:
            if source in data and data[source]:
                result[target] = data[source]
                break
    
    return result

def create_contact(data: dict) -> dict:
    """Create contact via CRM CLI."""
    if not data.get('name'):
        return {'error': 'Name is required'}
    
    cmd = [str(CRM_SCRIPT), 'add-contact', data['name']]
    
    if data.get('email'):
        cmd.extend(['--email', data['email']])
    if data.get('phone'):
        cmd.extend(['--phone', data['phone']])
    if data.get('company'):
        cmd.extend(['--company', data['company']])
    if data.get('role'):
        cmd.extend(['--role', data['role']])
    if data.get('source'):
        cmd.extend(['--source', data['source']])
    if data.get('notes'):
        cmd.extend(['--notes', data['notes']])
    
    cmd.extend(['--reason', 'Webhook ingest'])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {'error': result.stderr or 'CLI error'}
    except Exception as e:
        return {'error': str(e)}

class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for webhook requests."""
    
    def log_message(self, format, *args):
        log(f"HTTP {args[0]}")
    
    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_GET(self):
        """Health check endpoint."""
        if self.path == '/health':
            self._send_json(200, {'status': 'ok', 'service': 'crm-webhook'})
        else:
            self._send_json(404, {'error': 'Not found'})
    
    def do_POST(self):
        """Handle incoming webhooks."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            # Try URL-encoded
            try:
                data = {k: v[0] for k, v in parse_qs(body.decode()).items()}
            except:
                self._send_json(400, {'error': 'Invalid JSON'})
                return
        
        log(f"Received webhook: {json.dumps(data)[:500]}")
        
        # Parse based on path or payload structure
        if self.path == '/lead' or self.path == '/contact':
            # Detect format
            if 'form_response' in data:
                parsed = parse_typeform(data)
            elif 'data' in data and 'fields' in data.get('data', {}):
                parsed = parse_tally(data)
            else:
                parsed = parse_generic(data)
            
            log(f"Parsed: {json.dumps(parsed)}")
            
            result = create_contact(parsed)
            
            if 'error' in result:
                log(f"Error: {result['error']}")
                self._send_json(400, result)
            else:
                log(f"Created: {result}")
                self._send_json(201, result)
        
        else:
            self._send_json(404, {'error': f'Unknown endpoint: {self.path}'})

def main():
    parser = argparse.ArgumentParser(description='CRM webhook server for form ingestion')
    parser.add_argument('--port', '-p', type=int, default=8901, help='Port to listen on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    
    args = parser.parse_args()
    
    server = HTTPServer((args.host, args.port), WebhookHandler)
    
    print(f"CRM Webhook server listening on {args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  POST /lead    - Create contact from form submission")
    print(f"  POST /contact - Create contact from form submission")
    print(f"  GET  /health  - Health check")
    print(f"")
    print(f"Log: {LOG_FILE}")
    print(f"Database: {DB_PATH}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
