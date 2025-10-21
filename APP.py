import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from transformers import pipeline
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import textstat
from datetime import datetime, timedelta
import json
import sqlite3
from collections import defaultdict
import re

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load API key from environment variable for security
API_KEY = os.getenv("CONGRESS_API_KEY", "Im5PSE4YRX9G2FZhVchtfXnwNuRQ9oKmU1G6YztB")

# Initialize models once at startup (not on every request)
print("Loading models...")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Models loaded successfully")

# Initialize database for enhanced features
def init_database():
    """Initialize SQLite database for bill tracking and user data"""
    conn = sqlite3.connect('bill_tracker.db')
    cursor = conn.cursor()
    
    # Bill progression tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bill_progression (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT,
            status TEXT,
            date TEXT,
            description TEXT,
            stage INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User preferences and demographics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            location TEXT,
            age_group TEXT,
            income_bracket TEXT,
            interests TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User activity tracking for statistics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            activity_type TEXT,
            bill_number TEXT,
            reading_time_seconds INTEGER,
            complexity_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Voting records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voting_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT,
            legislator_name TEXT,
            party TEXT,
            state TEXT,
            vote TEXT,
            date TEXT
        )
    ''')
    
    # User feed preferences
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feed_preferences (
            user_id TEXT PRIMARY KEY,
            feed_type TEXT DEFAULT 'personalized',
            notification_frequency TEXT DEFAULT 'weekly',
            complexity_preference TEXT DEFAULT 'all',
            topic_weights TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

def fetch_bill_details(bill_number):
    """Fetch detailed information for a specific bill"""
    url = f"https://api.congress.gov/v3/bill/118/hr/{bill_number}"
    params = {"api_key": API_KEY}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        bill_data = r.json().get("bill", {})
        
        # Extract sponsor info
        sponsors = bill_data.get("sponsors", [])
        sponsor_name = "N/A"
        if sponsors and len(sponsors) > 0:
            sponsor = sponsors[0]
            first_name = sponsor.get("firstName", "")
            last_name = sponsor.get("lastName", "")
            party = sponsor.get("party", "")
            state = sponsor.get("state", "")
            
            # Build full name
            full_name = f"{first_name} {last_name}".strip()
            if full_name and party and state:
                sponsor_name = f"{full_name} ({party}-{state})"
            elif full_name:
                sponsor_name = full_name
        
        # Extract latest action with date
        latest_action = bill_data.get("latestAction", {})
        action_text = latest_action.get("text", "N/A")
        action_date = latest_action.get("actionDate", "N/A")
        
        print(f"Bill {bill_number}: sponsor={sponsor_name}, status={action_text}, date={action_date}")
        
        return {
            "sponsor": sponsor_name,
            "status": action_text,
            "date": action_date
        }
    
    except Exception as e:
        print(f"Error fetching bill {bill_number} details: {e}")
        return {
            "sponsor": "N/A",
            "status": "N/A",
            "date": "N/A"
        }

def fetch_latest_bills(limit=250):
    """Fetch bills from Congress API with error handling"""
    url = f"https://api.congress.gov/v3/bill/118/hr"
    params = {
        "api_key": API_KEY,
        "limit": limit,
        "sort": "updateDate+desc"
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        bills_data = r.json().get("bills", [])
        
        bills = []
        for bill in bills_data:
            title = bill.get("title", "")
            bill_number = bill.get("number", "")
            
            # Create description for semantic search
            description = title
            if bill.get("latestAction"):
                latest_action = bill["latestAction"].get("text", "")
                description += f" {latest_action}"
            
            bills.append({
                "number": bill_number,
                "title": title,
                "description": description,
                "url": f"https://www.congress.gov/bill/118th-congress/house-bill/{bill_number}"
            })
        
        return bills
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching bills: {e}")
        return []

def find_relevant_bills(query, bills, top_k=12):
    """Use semantic similarity to find relevant bills"""
    if not bills:
        return []
    
    # Encode query
    query_embedding = semantic_model.encode([query])
    
    # Encode bill descriptions
    bill_texts = [f"{b['title']} {b['description']}" for b in bills]
    bill_embeddings = semantic_model.encode(bill_texts)
    
    # Calculate similarity
    similarities = cosine_similarity(query_embedding, bill_embeddings)[0]
    
    # Get top k indices
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    # Filter by minimum similarity threshold (lowered for more results)
    relevant_bills = []
    for idx in top_indices:
        if similarities[idx] > 0.15:  # Lowered threshold for more inclusive results
            bill = bills[idx].copy()
            bill['relevance_score'] = float(similarities[idx])
            relevant_bills.append(bill)
    
    # If we still don't have enough results, add more with lower threshold
    if len(relevant_bills) < 6:
        for idx in top_indices:
            if similarities[idx] > 0.1 and len(relevant_bills) < 8:
                bill = bills[idx].copy()
                bill['relevance_score'] = float(similarities[idx])
                if bill not in relevant_bills:
                    relevant_bills.append(bill)
    
    return relevant_bills

def analyze_reading_complexity(text):
    """Analyze reading complexity using multiple metrics"""
    if not text or len(text.strip()) < 10:
        return {
            "flesch_kincaid": 0,
            "flesch_reading_ease": 0,
            "gunning_fog": 0,
            "reading_level": "Unknown",
            "complexity_score": 0
        }
    
    try:
        # Calculate various readability metrics
        fk_grade = textstat.flesch_kincaid().flesch_kincaid(text)
        flesch_ease = textstat.flesch_reading_ease(text)
        gunning_fog = textstat.gunning_fog(text)
        
        # Determine reading level
        if fk_grade <= 6:
            reading_level = "Elementary"
        elif fk_grade <= 9:
            reading_level = "Middle School"
        elif fk_grade <= 12:
            reading_level = "High School"
        elif fk_grade <= 16:
            reading_level = "College"
        else:
            reading_level = "Graduate"
        
        # Create complexity score (0-100, higher = more complex)
        complexity_score = min(100, max(0, (fk_grade * 5) + (20 - flesch_ease/5)))
        
        return {
            "flesch_kincaid": round(fk_grade, 1),
            "flesch_reading_ease": round(flesch_ease, 1),
            "gunning_fog": round(gunning_fog, 1),
            "reading_level": reading_level,
            "complexity_score": round(complexity_score, 1)
        }
    except Exception as e:
        print(f"Error analyzing complexity: {e}")
        return {
            "flesch_kincaid": 12.0,
            "flesch_reading_ease": 30.0,
            "gunning_fog": 14.0,
            "reading_level": "College",
            "complexity_score": 75.0
        }

def analyze_bill_sections(bill_text):
    """Analyze different sections of a bill for complexity"""
    sections = {
        "title": "",
        "summary": "",
        "findings": "",
        "definitions": "",
        "main_provisions": ""
    }
    
    # Simple section extraction (can be enhanced with better parsing)
    text_lower = bill_text.lower()
    
    # Extract title (first line or section)
    lines = bill_text.split('\n')
    if lines:
        sections["title"] = lines[0][:200]
    
    # Extract summary section
    summary_match = re.search(r'(summary|abstract|overview)[\s\S]{0,50}?[:\-\n]([\s\S]{0,500})', text_lower)
    if summary_match:
        sections["summary"] = summary_match.group(2)
    
    # Extract findings section
    findings_match = re.search(r'(findings|whereas|background)[\s\S]{0,50}?[:\-\n]([\s\S]{0,800})', text_lower)
    if findings_match:
        sections["findings"] = findings_match.group(2)
    
    # Extract definitions
    def_match = re.search(r'(definitions|terms)[\s\S]{0,50}?[:\-\n]([\s\S]{0,600})', text_lower)
    if def_match:
        sections["definitions"] = def_match.group(2)
    
    # Main provisions (everything else)
    sections["main_provisions"] = bill_text[:1000]
    
    # Analyze complexity for each section
    complexity_analysis = {}
    for section_name, section_text in sections.items():
        if section_text.strip():
            complexity_analysis[section_name] = analyze_reading_complexity(section_text)
        else:
            complexity_analysis[section_name] = analyze_reading_complexity("No content available")
    
    return complexity_analysis

def create_age_appropriate_summary(text, title, age_group="adult"):
    """Create age-appropriate summary based on user's age group"""
    # Extract key sentences and create a quick summary
    sentences = text.split('.')
    
    # Take first 2-3 meaningful sentences
    summary_sentences = []
    for sentence in sentences[:3]:
        sentence = sentence.strip()
        if len(sentence) > 20:  # Skip very short fragments
            summary_sentences.append(sentence)
    
    if summary_sentences:
        base_summary = '. '.join(summary_sentences) + '.'
        
        # Adjust language based on age group
        if age_group == "child":
            # Simplify for children (ages 8-12)
            simplified = base_summary.replace("legislation", "law")
            simplified = simplified.replace("provisions", "rules")
            simplified = simplified.replace("appropriations", "money")
            simplified = simplified.replace("amendments", "changes")
            return f"This is a law about {title.lower()}. {simplified[:150]}..."
            
        elif age_group == "teen":
            # Moderate simplification for teens (ages 13-17)
            simplified = base_summary.replace("appropriations", "funding")
            simplified = simplified.replace("provisions", "sections")
            return f"This bill deals with {title.lower()}. {simplified[:180]}..."
            
        elif age_group == "senior":
            # More detailed for seniors who may want comprehensive info
            return f"Legislative Summary: {base_summary[:250]}..."
            
        else:  # adult (default)
            # Standard summary for adults
            if len(base_summary) > 200:
                return base_summary[:197] + "..."
            return base_summary
    else:
        # Fallback based on age group
        if age_group == "child":
            return f"This is a new law about {title.lower()}."
        elif age_group == "teen":
            return f"This bill is about {title.lower()} and how it affects people."
        else:
            return f"This bill, titled '{title}', addresses legislative matters related to the specified topic."

def create_fast_summary(text, title):
    """Create a fast summary without heavy AI processing"""
    return create_age_appropriate_summary(text, title, "adult")

def track_user_activity(user_id, activity_type, bill_number=None, reading_time=None, complexity_score=None):
    """Track user activity for statistics"""
    try:
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO user_activity 
            (user_id, activity_type, bill_number, reading_time_seconds, complexity_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, activity_type, bill_number, reading_time, complexity_score))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error tracking user activity: {e}")

def get_user_statistics(user_id):
    """Get comprehensive user statistics"""
    try:
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        # Get total bills read
        cursor.execute('''
            SELECT COUNT(DISTINCT bill_number) 
            FROM user_activity 
            WHERE user_id = ? AND activity_type = 'bill_read'
        ''', (user_id,))
        bills_read = cursor.fetchone()[0] or 0
        
        # Get total reading time
        cursor.execute('''
            SELECT SUM(reading_time_seconds) 
            FROM user_activity 
            WHERE user_id = ? AND reading_time_seconds IS NOT NULL
        ''', (user_id,))
        total_reading_time = cursor.fetchone()[0] or 0
        
        # Get average complexity of bills read
        cursor.execute('''
            SELECT AVG(complexity_score) 
            FROM user_activity 
            WHERE user_id = ? AND complexity_score IS NOT NULL
        ''', (user_id,))
        avg_complexity = cursor.fetchone()[0] or 0
        
        # Get activity by week
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM user_activity 
            WHERE user_id = ? AND created_at >= datetime('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        ''', (user_id,))
        daily_activity = cursor.fetchall()
        
        # Calculate time saved (assuming average bill reading time is 15 minutes without AI)
        estimated_time_without_ai = bills_read * 15 * 60  # 15 minutes per bill in seconds
        time_saved = max(0, estimated_time_without_ai - total_reading_time)
        
        # Get user's most read topics
        cursor.execute('''
            SELECT activity_type, COUNT(*) as count
            FROM user_activity 
            WHERE user_id = ? 
            GROUP BY activity_type
            ORDER BY count DESC
            LIMIT 5
        ''', (user_id,))
        top_activities = cursor.fetchall()
        
        conn.close()
        
        return {
            "bills_read": bills_read,
            "total_reading_time_minutes": round(total_reading_time / 60, 1),
            "time_saved_minutes": round(time_saved / 60, 1),
            "average_complexity": round(avg_complexity, 1),
            "daily_activity": daily_activity,
            "top_activities": top_activities,
            "reading_streak_days": calculate_reading_streak(user_id),
            "efficiency_score": calculate_efficiency_score(bills_read, total_reading_time, avg_complexity)
        }
        
    except Exception as e:
        print(f"Error getting user statistics: {e}")
        return {
            "bills_read": 0,
            "total_reading_time_minutes": 0,
            "time_saved_minutes": 0,
            "average_complexity": 0,
            "daily_activity": [],
            "top_activities": [],
            "reading_streak_days": 0,
            "efficiency_score": 0
        }

def calculate_reading_streak(user_id):
    """Calculate current reading streak in days"""
    try:
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT DATE(created_at) as date
            FROM user_activity 
            WHERE user_id = ? AND activity_type = 'bill_read'
            ORDER BY date DESC
        ''', (user_id,))
        
        dates = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not dates:
            return 0
        
        streak = 0
        current_date = datetime.now().date()
        
        for date_str in dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            days_diff = (current_date - date_obj).days
            
            if days_diff == streak:
                streak += 1
            elif days_diff == streak + 1:
                streak += 1
            else:
                break
                
        return streak
        
    except Exception as e:
        print(f"Error calculating reading streak: {e}")
        return 0

def calculate_efficiency_score(bills_read, total_time, avg_complexity):
    """Calculate user's reading efficiency score (0-100)"""
    if bills_read == 0:
        return 0
    
    # Base score from number of bills read
    base_score = min(50, bills_read * 2)
    
    # Bonus for reading complex bills
    complexity_bonus = min(25, avg_complexity / 4)
    
    # Efficiency bonus (more bills in less time)
    if total_time > 0:
        bills_per_hour = (bills_read * 3600) / total_time
        efficiency_bonus = min(25, bills_per_hour * 5)
    else:
        efficiency_bonus = 0
    
    return round(base_score + complexity_bonus + efficiency_bonus)

def summarize_text(text, max_length=200, min_length=80):
    """Summarize text with error handling"""
    try:
        # Skip if text is already short
        if len(text.split()) < min_length:
            return text
        
        # Truncate if too long for model
        max_input = 1024
        words = text.split()
        if len(words) > max_input:
            text = " ".join(words[:max_input])
        
        result = summarizer(
            text, 
            max_length=max_length, 
            min_length=min_length, 
            do_sample=False,
            truncation=True
        )
        return result[0]["summary_text"]
    
    except Exception as e:
        print(f"Summarization error: {e}")
        # Return truncated original if summarization fails
        return " ".join(text.split()[:80]) + "..."

@app.route("/search_bills", methods=["POST"])
def search_bills():
    """Search for relevant bills based on query with pagination"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        query = data.get("query", "").strip()
        page = data.get("page", 1)
        per_page = data.get("per_page", 5)
        
        if not query:
            return jsonify({"error": "Query parameter is required"}), 400
        
        # Fetch bills (reduced for faster initial load)
        print(f"Fetching bills for query: {query}, page: {page}")
        bills = fetch_latest_bills(limit=100)  # Reduced from 250
        
        if not bills:
            return jsonify({"error": "Unable to fetch bills from Congress API"}), 503
        
        # Find relevant bills using semantic search
        print(f"Finding relevant bills...")
        relevant_bills = find_relevant_bills(query, bills, top_k=20)  # Get more for pagination
        
        if not relevant_bills:
            return jsonify({
                "query": query,
                "bills": [],
                "total_found": 0,
                "page": page,
                "per_page": per_page,
                "has_more": False,
                "message": "No relevant bills found for your query"
            })
        
        # Sort by relevance score first, then by date (newest first)
        relevant_bills.sort(key=lambda x: (-x["relevance_score"], x.get("date", "0000-00-00")), reverse=False)
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_bills = relevant_bills[start_idx:end_idx]
        
        # Process only the bills for this page
        results = []
        for bill in paginated_bills:
            print(f"Processing bill H.R. {bill['number']}")
            
            # Get bill details for this page only
            details = fetch_bill_details(bill["number"])
            
            # Use faster summarization
            summary = create_fast_summary(bill["description"], bill["title"])
            
            results.append({
                "number": bill["number"],
                "title": bill["title"],
                "summary": summary,
                "sponsor": details["sponsor"],
                "status": details["status"],
                "date": details["date"],
                "relevance_score": bill["relevance_score"],
                "url": bill["url"]
            })
        
        # Sort results by date (newest first)
        results.sort(key=lambda x: parse_date_for_sorting(x["date"]), reverse=True)
        
        has_more = end_idx < len(relevant_bills)
        
        print(f"Returning {len(results)} results for page {page}")
        return jsonify({
            "query": query,
            "bills": results,
            "total_found": len(relevant_bills),
            "page": page,
            "per_page": per_page,
            "has_more": has_more
        })
    
    except Exception as e:
        print(f"Error processing request: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

def track_bill_progression(bill_number):
    """Track and store bill progression over time"""
    try:
        # Fetch bill actions/history
        url = f"https://api.congress.gov/v3/bill/118/hr/{bill_number}/actions"
        params = {"api_key": API_KEY, "limit": 50}
        
        response = requests.get(url, params=params, timeout=10)
        if not response.ok:
            return []
        
        actions_data = response.json().get("actions", [])
        
        # Store in database
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        progression_stages = []
        stage_mapping = {
            "introduced": 1,
            "committee": 2,
            "floor": 3,
            "passed": 4,
            "senate": 5,
            "signed": 6,
            "vetoed": 6
        }
        
        for action in actions_data:
            action_text = action.get("text", "").lower()
            action_date = action.get("actionDate", "")
            
            # Determine stage
            stage = 1  # default
            for keyword, stage_num in stage_mapping.items():
                if keyword in action_text:
                    stage = stage_num
                    break
            
            # Insert or update progression
            cursor.execute('''
                INSERT OR REPLACE INTO bill_progression 
                (bill_number, status, date, description, stage)
                VALUES (?, ?, ?, ?, ?)
            ''', (bill_number, action.get("text", ""), action_date, action_text, stage))
            
            progression_stages.append({
                "date": action_date,
                "status": action.get("text", ""),
                "stage": stage,
                "description": action_text
            })
        
        conn.commit()
        conn.close()
        
        return sorted(progression_stages, key=lambda x: x["date"])
        
    except Exception as e:
        print(f"Error tracking bill progression: {e}")
        return []

def calculate_demographic_impact(bill_text, bill_number):
    """Calculate potential impact on different demographic groups"""
    impact_keywords = {
        "seniors": ["medicare", "social security", "retirement", "elderly", "senior", "age 65"],
        "students": ["education", "student loan", "college", "university", "school", "tuition"],
        "families": ["child", "family", "parent", "dependent", "childcare", "maternity"],
        "workers": ["employment", "wage", "job", "worker", "labor", "minimum wage"],
        "veterans": ["veteran", "military", "armed forces", "va", "service member"],
        "small_business": ["small business", "entrepreneur", "startup", "sme", "business owner"],
        "healthcare": ["health", "medical", "hospital", "insurance", "patient", "doctor"],
        "environment": ["climate", "environment", "pollution", "clean energy", "carbon"],
        "rural": ["rural", "farm", "agriculture", "countryside", "small town"],
        "urban": ["city", "urban", "metropolitan", "downtown", "municipal"]
    }
    
    text_lower = bill_text.lower()
    impact_scores = {}
    
    for demographic, keywords in impact_keywords.items():
        score = 0
        mentions = []
        
        for keyword in keywords:
            count = text_lower.count(keyword)
            score += count * 10  # Weight each mention
            if count > 0:
                mentions.append(f"{keyword}: {count}")
        
        # Normalize score (0-100)
        normalized_score = min(100, score)
        
        impact_scores[demographic] = {
            "score": normalized_score,
            "level": "High" if normalized_score > 50 else "Medium" if normalized_score > 20 else "Low",
            "mentions": mentions[:5]  # Top 5 mentions
        }
    
    return impact_scores

def get_personalized_recommendations(user_location, user_interests, bills):
    """Generate personalized bill recommendations"""
    if not bills:
        return []
    
    # Weight bills based on user preferences
    weighted_bills = []
    
    for bill in bills:
        weight = bill.get("relevance_score", 0.5)
        
        # Location-based weighting
        if user_location:
            bill_text = f"{bill.get('title', '')} {bill.get('description', '')}".lower()
            if user_location.lower() in bill_text:
                weight += 0.2
        
        # Interest-based weighting
        if user_interests:
            interests_list = user_interests.split(',')
            bill_text = f"{bill.get('title', '')} {bill.get('description', '')}".lower()
            
            for interest in interests_list:
                if interest.strip().lower() in bill_text:
                    weight += 0.15
        
        bill_copy = bill.copy()
        bill_copy['personalized_score'] = min(1.0, weight)
        weighted_bills.append(bill_copy)
    
    # Sort by personalized score
    return sorted(weighted_bills, key=lambda x: x['personalized_score'], reverse=True)

def generate_voting_heatmap_data(bill_number):
    """Generate voting pattern data for heatmap visualization"""
    # This would typically fetch real voting data from Congress API
    # For now, we'll generate sample data structure
    
    states = [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
    ]
    
    # Generate sample voting data (in real implementation, fetch from API)
    voting_data = {}
    for state in states:
        # Sample data - replace with real API calls
        voting_data[state] = {
            "yes_votes": np.random.randint(0, 10),
            "no_votes": np.random.randint(0, 10),
            "abstain": np.random.randint(0, 3),
            "support_percentage": np.random.randint(20, 80)
        }
    
    return voting_data

def parse_date_for_sorting(date_str):
    """Parse date string for sorting (newest first)"""
    if not date_str or date_str in ['N/A', 'Recent', 'Loading...']:
        return "0000-00-00"  # Put unknown dates at the end
    
    try:
        # Try different date formats
        import re
        from datetime import datetime
        
        # Format: YYYY-MM-DD
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return date_str
        
        # Format: MM/DD/YYYY
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            month, day, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Format: Month DD, YYYY
        try:
            parsed = datetime.strptime(date_str, "%B %d, %Y")
            return parsed.strftime("%Y-%m-%d")
        except:
            pass
        
        return "0000-00-00"
    except:
        return "0000-00-00"

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route("/analyze_complexity", methods=["POST"])
def analyze_complexity():
    """Analyze reading complexity of bill sections"""
    try:
        data = request.get_json()
        bill_number = data.get("bill_number", "").strip()
        
        if not bill_number:
            return jsonify({"error": "Bill number is required"}), 400
        
        # Fetch full bill text (simplified - in real implementation, get full text)
        bill_details = fetch_bill_details(bill_number)
        bill_text = f"{bill_details.get('status', '')} {bill_details.get('sponsor', '')}"
        
        # Analyze sections
        complexity_analysis = analyze_bill_sections(bill_text)
        
        return jsonify({
            "bill_number": bill_number,
            "complexity_analysis": complexity_analysis,
            "overall_complexity": analyze_reading_complexity(bill_text)
        })
        
    except Exception as e:
        print(f"Error analyzing complexity: {e}")
        return jsonify({"error": "Failed to analyze complexity"}), 500

@app.route("/bill_progression", methods=["POST"])
def get_bill_progression():
    """Get bill progression timeline"""
    try:
        data = request.get_json()
        bill_number = data.get("bill_number", "").strip()
        
        if not bill_number:
            return jsonify({"error": "Bill number is required"}), 400
        
        progression = track_bill_progression(bill_number)
        
        return jsonify({
            "bill_number": bill_number,
            "progression": progression,
            "total_stages": len(progression)
        })
        
    except Exception as e:
        print(f"Error getting bill progression: {e}")
        return jsonify({"error": "Failed to get bill progression"}), 500

@app.route("/impact_calculator", methods=["POST"])
def calculate_impact():
    """Calculate demographic impact of a bill"""
    try:
        data = request.get_json()
        bill_number = data.get("bill_number", "").strip()
        
        if not bill_number:
            return jsonify({"error": "Bill number is required"}), 400
        
        # Get bill text (simplified)
        bill_details = fetch_bill_details(bill_number)
        bill_text = f"{bill_details.get('status', '')} {bill_details.get('sponsor', '')}"
        
        impact_analysis = calculate_demographic_impact(bill_text, bill_number)
        
        return jsonify({
            "bill_number": bill_number,
            "demographic_impact": impact_analysis
        })
        
    except Exception as e:
        print(f"Error calculating impact: {e}")
        return jsonify({"error": "Failed to calculate impact"}), 500

@app.route("/personalized_feed", methods=["POST"])
def get_personalized_feed():
    """Get personalized bill recommendations"""
    try:
        data = request.get_json()
        user_location = data.get("location", "")
        user_interests = data.get("interests", "")
        query = data.get("query", "healthcare")  # Default query
        
        # Fetch bills
        bills = fetch_latest_bills(limit=50)
        relevant_bills = find_relevant_bills(query, bills, top_k=20)
        
        # Apply personalization
        personalized_bills = get_personalized_recommendations(
            user_location, user_interests, relevant_bills
        )
        
        return jsonify({
            "personalized_bills": personalized_bills[:10],
            "total_analyzed": len(relevant_bills),
            "location": user_location,
            "interests": user_interests
        })
        
    except Exception as e:
        print(f"Error getting personalized feed: {e}")
        return jsonify({"error": "Failed to get personalized feed"}), 500

@app.route("/voting_heatmap", methods=["POST"])
def get_voting_heatmap():
    """Get voting pattern data for heatmap"""
    try:
        data = request.get_json()
        bill_number = data.get("bill_number", "").strip()
        
        if not bill_number:
            return jsonify({"error": "Bill number is required"}), 400
        
        heatmap_data = generate_voting_heatmap_data(bill_number)
        
        return jsonify({
            "bill_number": bill_number,
            "voting_data": heatmap_data,
            "data_type": "state_level"
        })
        
    except Exception as e:
        print(f"Error generating voting heatmap: {e}")
        return jsonify({"error": "Failed to generate voting heatmap"}), 500

@app.route("/save_user_profile", methods=["POST"])
def save_user_profile():
    """Save user profile for personalization"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        location = data.get("location", "")
        age_group = data.get("age_group", "")
        income_bracket = data.get("income_bracket", "")
        interests = data.get("interests", "")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles 
            (user_id, location, age_group, income_bracket, interests)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, location, age_group, income_bracket, interests))
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Profile saved successfully"})
        
    except Exception as e:
        print(f"Error saving user profile: {e}")
        return jsonify({"error": "Failed to save profile"}), 500

@app.route("/my_feed", methods=["POST"])
def get_my_feed():
    """Get personalized My Feed with user's preferences"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        # Get user profile
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT location, age_group, interests 
            FROM user_profiles 
            WHERE user_id = ?
        ''', (user_id,))
        
        profile = cursor.fetchone()
        conn.close()
        
        if profile:
            location, age_group, interests = profile
        else:
            location, age_group, interests = "", "adult", ""
        
        # Fetch bills based on interests or default topics
        query_topics = interests if interests else "healthcare,education,infrastructure,climate"
        
        # Fetch bills
        bills = fetch_latest_bills(limit=100)
        relevant_bills = find_relevant_bills(query_topics, bills, top_k=30)
        
        # Apply personalization
        personalized_bills = get_personalized_recommendations(location, interests, relevant_bills)
        
        # Add age-appropriate summaries
        for bill in personalized_bills:
            bill['summary'] = create_age_appropriate_summary(
                bill.get('description', ''), 
                bill.get('title', ''), 
                age_group
            )
        
        # Track activity
        track_user_activity(user_id, "feed_viewed")
        
        return jsonify({
            "personalized_bills": personalized_bills[:15],
            "user_profile": {
                "location": location,
                "age_group": age_group,
                "interests": interests
            },
            "total_analyzed": len(relevant_bills)
        })
        
    except Exception as e:
        print(f"Error getting my feed: {e}")
        return jsonify({"error": "Failed to get personalized feed"}), 500

@app.route("/user_statistics", methods=["POST"])
def get_user_stats():
    """Get comprehensive user statistics"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        stats = get_user_statistics(user_id)
        
        return jsonify({
            "user_id": user_id,
            "statistics": stats
        })
        
    except Exception as e:
        print(f"Error getting user statistics: {e}")
        return jsonify({"error": "Failed to get user statistics"}), 500

@app.route("/track_reading", methods=["POST"])
def track_reading():
    """Track bill reading activity"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        bill_number = data.get("bill_number", "")
        reading_time = data.get("reading_time_seconds", 0)
        complexity_score = data.get("complexity_score", 0)
        
        if not user_id or not bill_number:
            return jsonify({"error": "User ID and bill number are required"}), 400
        
        track_user_activity(user_id, "bill_read", bill_number, reading_time, complexity_score)
        
        return jsonify({"success": True, "message": "Reading activity tracked"})
        
    except Exception as e:
        print(f"Error tracking reading: {e}")
        return jsonify({"error": "Failed to track reading"}), 500

@app.route("/update_user_settings", methods=["POST"])
def update_user_settings():
    """Update user settings including age group for AI summaries"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        location = data.get("location", "")
        age_group = data.get("age_group", "adult")
        interests = data.get("interests", "")
        income_bracket = data.get("income_bracket", "")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        # Update or insert user profile
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles 
            (user_id, location, age_group, income_bracket, interests, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', (user_id, location, age_group, income_bracket, interests))
        
        conn.commit()
        conn.close()
        
        # Track settings update
        track_user_activity(user_id, "settings_updated")
        
        return jsonify({
            "success": True, 
            "message": "Settings updated successfully",
            "age_group": age_group
        })
        
    except Exception as e:
        print(f"Error updating user settings: {e}")
        return jsonify({"error": "Failed to update settings"}), 500

@app.route("/get_user_profile", methods=["POST"])
def get_user_profile():
    """Get user profile information"""
    try:
        data = request.get_json()
        user_id = data.get("user_id", "")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        conn = sqlite3.connect('bill_tracker.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT location, age_group, income_bracket, interests, created_at, updated_at
            FROM user_profiles 
            WHERE user_id = ?
        ''', (user_id,))
        
        profile = cursor.fetchone()
        conn.close()
        
        if profile:
            return jsonify({
                "user_id": user_id,
                "profile": {
                    "location": profile[0] or "",
                    "age_group": profile[1] or "adult",
                    "income_bracket": profile[2] or "",
                    "interests": profile[3] or "",
                    "created_at": profile[4],
                    "updated_at": profile[5]
                }
            })
        else:
            return jsonify({
                "user_id": user_id,
                "profile": {
                    "location": "",
                    "age_group": "adult",
                    "income_bracket": "",
                    "interests": "",
                    "created_at": None,
                    "updated_at": None
                }
            })
        
    except Exception as e:
        print(f"Error getting user profile: {e}")
        return jsonify({"error": "Failed to get user profile"}), 500

@app.route("/models_ready", methods=["GET"])
def models_ready():
    """Check if AI models are loaded and ready"""
    try:
        # Test if models are accessible
        test_text = "test"
        semantic_model.encode([test_text])
        summarizer("This is a test.", max_length=50, min_length=10, do_sample=False)
        return jsonify({"ready": True, "status": "Models loaded successfully"})
    except Exception as e:
        return jsonify({"ready": False, "status": f"Models not ready: {str(e)}"}), 503

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)