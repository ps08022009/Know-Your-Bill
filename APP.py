import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from transformers import pipeline
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from datetime import datetime, timedelta
import sqlite3

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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)