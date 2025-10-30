# Corporate Contact Finder

## Overview
A full-stack web application that searches for corporate contacts by finding LinkedIn profiles and verifying email addresses using Google Custom Search API and Hunter.io.

**Current State:** Fully functional MVP with API key rotation, hierarchical role search, and CSV export capabilities.

**Last Updated:** October 29, 2025

## Recent Changes
- **October 29, 2025**: Implemented EventSource-based real-time progress tracking
  - Split search into POST /search (initialize) and GET /search/stream/<session_id> (stream)
  - Frontend uses native EventSource API for reliable SSE consumption
  - Real-time progress bar, log updates, and incremental result display
  - Functional stop button that halts server-side processing mid-run
- Initial project setup with Flask backend and vanilla JavaScript frontend
- Implemented API key rotation system for Google Custom Search API (13 keys)
- Created hierarchical role search functionality (CEO → CFO → CHRO → Marketing roles)
- Integrated Hunter.io email verification
- Built responsive UI with Tailwind CSS
- Added CSV export functionality

## Project Architecture

### Backend (Flask)
- **app.py** - Main Flask application with:
  - API key rotation logic for rate limit handling
  - LinkedIn profile search via Google Custom Search API
  - Hunter.io email verification integration
  - ThreadPoolExecutor for parallel domain processing
  - CSV export endpoint

### Frontend
- **templates/index.html** - Main UI with Tailwind CSS
  - Multi-domain input textarea
  - Real-time progress tracking
  - Dynamic results table
  - Search log display
- **static/script.js** - Frontend logic
  - Fetch API for backend communication
  - Progress updates and result rendering
  - CSV download functionality
- **static/style.css** - Custom styling and animations

### Configuration
- **.gitignore** - Python/Flask specific ignores
- **pyproject.toml** - Python dependencies managed by uv

## Environment Variables
Required secrets (configured via Replit Secrets):
- `GOOGLE_API_KEYS` - Comma-separated list of Google Custom Search API keys (13 keys for rotation)
- `GOOGLE_CX_ID` - Google Custom Search Engine ID
- `HUNTER_API_KEY` - Hunter.io API key for email verification
- `SESSION_SECRET` - Flask session secret (auto-configured)

## Role Hierarchy
The app searches LinkedIn profiles in this order and stops at first match:
1. CEO, Founder, Co-Founder, Managing Director
2. CFO, Finance Head, Chief Financial Officer
3. CHRO, HR Head, HR Manager, HR Executive, Talent Acquisition, HR Business Partner
4. Marketing Head, Marketing Executive, SEO Executive, Link Builder, Digital Marketing Manager

## Features
- Multi-domain batch processing
- Automatic API key rotation to handle rate limits
- Real-time progress tracking
- Search log with timestamps
- Results table with LinkedIn profile links
- CSV export with all results
- Error handling and validation
- Responsive design for mobile/desktop

## User Preferences
- None specified yet

## Technical Notes
- Uses ThreadPoolExecutor with max 3 workers for parallel processing
- Google Custom Search API query format: `site:linkedin.com/in ("{ROLE}") "{DOMAIN}"`
- Hunter.io Email Finder API for email verification
- Server binds to 0.0.0.0:5000 for Replit compatibility
