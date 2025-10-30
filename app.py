import os
import re
import logging
import json
import uuid
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
from io import StringIO
import time
import threading

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global dictionary to track active search sessions
active_searches = {}

# Role hierarchy for search
ROLE_HIERARCHY = [
    "CEO", "Founder", "Co-Founder", "Managing Director",
    "CFO", "Finance Head", "Chief Financial Officer",
    "CHRO", "HR Head", "HR Manager", "HR Executive", "Talent Acquisition", "HR Business Partner",
    "Marketing Head", "Marketing Executive", "SEO Executive", "Link Builder", "Digital Marketing Manager"
]

# API Configuration
GOOGLE_API_KEYS = os.environ.get('GOOGLE_API_KEYS', '').split(',')
GOOGLE_CX_ID = os.environ.get('GOOGLE_CX_ID', '')
HUNTER_API_KEY = os.environ.get('HUNTER_API_KEY', '')

# API Key rotation index
api_key_index = 0

def get_next_google_api_key():
    """Rotate through Google API keys to avoid rate limits"""
    global api_key_index
    if not GOOGLE_API_KEYS or GOOGLE_API_KEYS[0] == '':
        return None
    key = GOOGLE_API_KEYS[api_key_index % len(GOOGLE_API_KEYS)]
    api_key_index += 1
    return key.strip()

def search_linkedin_profile(domain, role):
    """Search for LinkedIn profile using Google Custom Search API"""
    try:
        api_key = get_next_google_api_key()
        if not api_key:
            logger.error("No Google API key available")
            return None
        
        query = f'site:linkedin.com/in ("{role}") "{domain}"'
        url = "https://www.googleapis.com/customsearch/v1"
        
        params = {
            'key': api_key,
            'cx': GOOGLE_CX_ID,
            'q': query,
            'num': 3
        }
        
        logger.info(f"Searching for {role} at {domain}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'items' in data and len(data['items']) > 0:
                for item in data['items']:
                    linkedin_url = item.get('link', '')
                    title = item.get('title', '')
                    snippet = item.get('snippet', '')
                    
                    # Extract name from title (usually "Name - Title - LinkedIn")
                    name = extract_name_from_title(title)
                    
                    if linkedin_url and 'linkedin.com/in/' in linkedin_url:
                        return {
                            'name': name,
                            'title': extract_title(title, snippet),
                            'linkedin_url': linkedin_url,
                            'matched_role': role
                        }
        elif response.status_code == 429:
            logger.warning(f"Rate limit hit for API key, rotating...")
            time.sleep(1)
        else:
            logger.warning(f"Search failed with status {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error searching LinkedIn for {role} at {domain}: {str(e)}")
    
    return None

def extract_name_from_title(title):
    """Extract name from LinkedIn title"""
    # LinkedIn titles are usually "Name - Title - LinkedIn" or "Name | LinkedIn"
    if ' - ' in title:
        parts = title.split(' - ')
        return parts[0].strip()
    elif ' | ' in title:
        parts = title.split(' | ')
        return parts[0].strip()
    elif '|' in title:
        parts = title.split('|')
        return parts[0].strip()
    return title.split('-')[0].strip() if '-' in title else title.strip()

def extract_title(title, snippet):
    """Extract job title from title or snippet"""
    # Try to get title from the title field
    if ' - ' in title:
        parts = title.split(' - ')
        if len(parts) > 1:
            return parts[1].strip()
    
    # Try to extract from snippet
    if snippet:
        # Look for common title patterns
        lines = snippet.split('.')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['ceo', 'founder', 'manager', 'head', 'director', 'officer', 'executive']):
                return line.strip()
    
    return "Professional"

def find_email_with_hunter(domain, full_name):
    """Find email using Hunter.io API"""
    try:
        if not HUNTER_API_KEY:
            logger.error("Hunter API key not configured")
            return None
        
        url = "https://api.hunter.io/v2/email-finder"
        params = {
            'domain': domain,
            'full_name': full_name,
            'api_key': HUNTER_API_KEY
        }
        
        logger.info(f"Finding email for {full_name} at {domain}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data']:
                email = data['data'].get('email')
                confidence = data['data'].get('score', 0)
                
                if email and confidence > 0:
                    logger.info(f"Found email: {email} (confidence: {confidence})")
                    return email
        else:
            logger.warning(f"Hunter API returned status {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error finding email with Hunter: {str(e)}")
    
    return None

def process_domain(domain):
    """Process a single domain through the role hierarchy"""
    domain = domain.strip().lower()
    
    # Validate domain format
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$', domain):
        logger.warning(f"Invalid domain format: {domain}")
        return {
            'domain': domain,
            'name': 'Not Found',
            'title': 'Not Found',
            'email': 'Not Found',
            'linkedin_url': 'Not Found',
            'matched_role': 'Invalid Domain'
        }
    
    logger.info(f"Processing domain: {domain}")
    
    # Search through role hierarchy
    for role in ROLE_HIERARCHY:
        profile = search_linkedin_profile(domain, role)
        
        if profile:
            # Found a profile, now get email
            email = find_email_with_hunter(domain, profile['name'])
            
            result = {
                'domain': domain,
                'name': profile['name'],
                'title': profile['title'],
                'email': email if email else 'Not Found',
                'linkedin_url': profile['linkedin_url'],
                'matched_role': profile['matched_role']
            }
            
            logger.info(f"Successfully processed {domain}: found {role}")
            return result
    
    # No profile found in any role
    logger.info(f"No profile found for {domain}")
    return {
        'domain': domain,
        'name': 'Not Found',
        'title': 'Not Found',
        'email': 'Not Found',
        'linkedin_url': 'Not Found',
        'matched_role': 'No Match'
    }

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Initialize a search and return session ID"""
    try:
        data = request.get_json()
        domains = data.get('domains', [])
        
        if not domains:
            return jsonify({'error': 'No domains provided'}), 400
        
        # Validate API keys
        if not GOOGLE_API_KEYS or GOOGLE_API_KEYS[0] == '':
            return jsonify({'error': 'Google API keys not configured'}), 500
        
        if not GOOGLE_CX_ID:
            return jsonify({'error': 'Google CX ID not configured'}), 500
        
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        active_searches[session_id] = {
            'stop': False,
            'domains': domains,
            'results': [],
            'started': False
        }
        
        logger.info(f"Search session created: {session_id} with {len(domains)} domains")
        
        return jsonify({'session_id': session_id})
        
    except Exception as e:
        logger.error(f"Error creating search session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/search/stream/<session_id>')
def search_stream(session_id):
    """Stream domain search results with real-time progress using SSE"""
    if session_id not in active_searches:
        return jsonify({'error': 'Invalid session ID'}), 404
    
    def generate():
        """Generator function for SSE stream"""
        try:
            session = active_searches.get(session_id)
            if not session:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'})}\n\n"
                return
            
            domains = session['domains']
            results = session['results']
            total = len(domains)
            processed = 0
            
            logger.info(f"Starting search stream for session: {session_id}")
            
            # Send initial event
            yield f"data: {json.dumps({'type': 'init', 'session_id': session_id, 'total': total})}\n\n"
            
            # Mark as started
            session['started'] = True
            
            # Process domains sequentially to maintain real-time progress
            for domain in domains:
                # Check if stop requested
                if active_searches.get(session_id, {}).get('stop', False):
                    logger.info(f"Search stopped by user (session: {session_id})")
                    yield f"data: {json.dumps({'type': 'stopped', 'results': results})}\n\n"
                    break
                
                # Send progress event
                processed += 1
                yield f"data: {json.dumps({'type': 'progress', 'current': processed, 'total': total, 'domain': domain})}\n\n"
                
                # Process domain
                try:
                    result = process_domain(domain)
                    results.append(result)
                    session['results'] = results
                    
                    # Send result event
                    yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
                    
                except Exception as e:
                    logger.error(f"Error processing {domain}: {str(e)}")
                    error_result = {
                        'domain': domain,
                        'name': 'Error',
                        'title': 'Error',
                        'email': 'Error',
                        'linkedin_url': 'Error',
                        'matched_role': str(e)
                    }
                    results.append(error_result)
                    session['results'] = results
                    yield f"data: {json.dumps({'type': 'result', 'data': error_result})}\n\n"
            
            # Send completion event
            if not active_searches.get(session_id, {}).get('stop', False):
                yield f"data: {json.dumps({'type': 'complete', 'results': results})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in search stream: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        finally:
            # Cleanup session
            if session_id in active_searches:
                del active_searches[session_id]
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

@app.route('/stop-search', methods=['POST'])
def stop_search():
    """Stop an active search session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if session_id and session_id in active_searches:
            active_searches[session_id]['stop'] = True
            logger.info(f"Stop requested for session: {session_id}")
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Session not found'}), 404
        
    except Exception as e:
        logger.error(f"Error stopping search: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/export-csv', methods=['POST'])
def export_csv():
    """Export results to CSV"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        
        if not results:
            return jsonify({'error': 'No results to export'}), 400
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Convert to CSV
        csv_data = df.to_csv(index=False)
        
        return jsonify({'csv': csv_data})
        
    except Exception as e:
        logger.error(f"Error exporting CSV: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
