import os
from json import JSONEncoder
import time

import httpagentparser  # for getting the user agent as json
from flask import Flask, render_template, session, request, jsonify, redirect
from flask import make_response

from myapp.analytics.analytics_data import AnalyticsData, ClickedDoc, MissionType
from myapp.search.load_corpus import load_corpus
from myapp.search.objects import Document, StatsDocument
from myapp.search.search_engine import SearchEngine
from myapp.generation.rag import RAGGenerator
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env


# *** for using method to_json in objects ***
def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)


_default.default = JSONEncoder().default
JSONEncoder.default = _default
# end lines ***for using method to_json in objects ***


# instantiate the Flask application
app = Flask(__name__)

# random 'secret_key' is used for persisting data in secure cookie
app.secret_key = os.getenv("SECRET_KEY")
# open browser dev tool to see the cookies
app.session_cookie_name = os.getenv("SESSION_COOKIE_NAME")
# instantiate our search engine
search_engine = SearchEngine()
# instantiate our in memory persistence
analytics_data = AnalyticsData()
# instantiate RAG generator
rag_generator = RAGGenerator()

# load documents corpus into memory.
full_path = os.path.realpath(__file__)
path, filename = os.path.split(full_path)
file_path = path + "/" + os.getenv("DATA_FILE_PATH")
corpus = load_corpus(file_path)
# Log first element of corpus to verify it loaded correctly:
print("\nCorpus is loaded... \n First element:\n", list(corpus.values())[0])


# Home URL "/"
@app.route("/")
def index():
    print("starting home url /...")

    # Track user session
    if 'session_id' not in session:
        user_agent = request.headers.get("User-Agent")
        user_ip = request.remote_addr
        
        # Extract IP from X-Forwarded-For if behind proxy
        if request.headers.get('X-Forwarded-For'):
            user_ip = request.headers.get('X-Forwarded-For').split(',')[0]
        
        session['session_id'] = analytics_data.start_session(user_agent, user_ip)
        session['start_time'] = time.time()
    
    # Store some data in session
    session["some_var"] = "Some value that is kept in session"

    user_agent = request.headers.get("User-Agent")
    print("Raw user browser:", user_agent)

    user_ip = request.remote_addr
    agent = httpagentparser.detect(user_agent)

    print("Remote IP: {} - JSON user browser {}".format(user_ip, agent))
    print("Session ID:", session.get('session_id'))
    return render_template("index.html", page_title="Welcome")


@app.route("/search", methods=["POST"])
def search_form_post():
    search_query = request.form["search-query"]
    session["last_search_query"] = search_query

    # Track the search query (legacy)
    search_id = analytics_data.save_query_terms(search_query)

    # Get session ID for tracking
    session_id = session.get('session_id', 'anonymous')
    
    # Track with new analytics system
    query_id = analytics_data.track_query(
        session_id=session_id,
        query_text=search_query,
        results_count=0  # Will update after search
    )
    
    # Store query_id for click tracking
    session['last_query_id'] = query_id

    algo = request.form.get("algo", "tfidf")
    results = search_engine.search(search_query, search_id, corpus, algo=algo)

    # Update results count in analytics
    if query_id in analytics_data.queries:
        analytics_data.queries[query_id].results_returned = len(results)

    # generate RAG response based on user query and retrieved results
    rag_response = rag_generator.generate_response(search_query, results)
    print("RAG response:", rag_response)

    found_count = len(results)
    session["last_found_count"] = found_count

    # Track mission type based on query content
    mission_type = _detect_mission_type(search_query, results)
    analytics_data.set_mission_type(session_id, mission_type)
    
    print(session)

    # Prepare results WITHOUT modifying objects directly
    # Create a wrapper for each result that includes tracking info
    results_with_tracking = []
    for i, result in enumerate(results):
        # Create a wrapper object instead of modifying the original
        class ResultWrapper:
            def __init__(self, original_result, position, qid):
                # Copy all attributes from original result
                self.__dict__.update(original_result.__dict__)
                # Add tracking attributes
                self.ranking_position = position
                self.query_id = qid
        
        wrapped_result = ResultWrapper(result, i + 1, query_id)
        results_with_tracking.append(wrapped_result)

    return render_template(
        "results.html",
        results_list=results_with_tracking,
        page_title="Results",
        found_counter=found_count,
        rag_response=rag_response,
        query_id=query_id
    )


@app.route("/search", methods=["GET"])
def search_form_get():
    """Handle GET requests to search (for direct URL access)"""
    search_query = request.args.get("query", "")
    if not search_query:
        return redirect("/")
    
    session["last_search_query"] = search_query
    
    # Get session ID for tracking
    session_id = session.get('session_id', 'anonymous')
    
    search_id = analytics_data.save_query_terms(search_query)
    
    # Track with new analytics system
    query_id = analytics_data.track_query(
        session_id=session_id,
        query_text=search_query,
        results_count=0
    )
    
    session['last_query_id'] = query_id
    
    algo = request.args.get("algo", "tfidf")
    results = search_engine.search(search_query, search_id, corpus, algo=algo)
    
    # Update results count in analytics
    if query_id in analytics_data.queries:
        analytics_data.queries[query_id].results_returned = len(results)
    
    rag_response = rag_generator.generate_response(search_query, results)
    
    found_count = len(results)
    session["last_found_count"] = found_count
    
    # Track mission type based on query content
    mission_type = _detect_mission_type(search_query, results)
    analytics_data.set_mission_type(session_id, mission_type)
    
    # Prepare results WITHOUT modifying objects directly
    results_with_tracking = []
    for i, result in enumerate(results):
        # Create a wrapper object instead of modifying the original
        class ResultWrapper:
            def __init__(self, original_result, position, qid):
                # Copy all attributes from original result
                self.__dict__.update(original_result.__dict__)
                # Add tracking attributes
                self.ranking_position = position
                self.query_id = qid
        
        wrapped_result = ResultWrapper(result, i + 1, query_id)
        results_with_tracking.append(wrapped_result)
    
    return render_template(
        "results.html",
        results_list=results_with_tracking,
        page_title="Results",
        found_counter=found_count,
        rag_response=rag_response,
        query_id=query_id
    )


@app.route("/doc_details", methods=["GET"])
def doc_details():
    # 1. Get PID from URL
    pid = request.args.get("pid")
    if pid is None:
        return "Error: missing PID parameter", 400

    # 2. Ensure PID exists in corpus
    if pid not in corpus:
        return f"Document with PID {pid} not found.", 404

    # 3. Fetch the full document object
    doc = corpus[pid]
    
    # 4. Get query_id for tracking
    query_id = request.args.get("query_id") or session.get('last_query_id')
    ranking_position = request.args.get("ranking_position", 1, type=int)
    
    # 5. Track the click
    if query_id:
        click_id = analytics_data.track_click(
            query_id=query_id,
            doc_id=pid,
            doc_title=doc.title,
            ranking_position=ranking_position
        )
        session['last_click_id'] = click_id
        
        # Start dwell time tracking
        analytics_data.start_dwell_time(click_id)

    # 6. Update legacy analytics
    analytics_data.fact_clicks[pid] = analytics_data.fact_clicks.get(pid, 0) + 1

    # 7. Render template with the document
    return render_template("doc_details.html", 
                         doc=doc, 
                         page_title=doc.title,
                         click_id=session.get('last_click_id'))


@app.route("/doc_details/back", methods=["GET"])
def doc_details_back():
    """Handle when user returns from document details to results"""
    click_id = request.args.get("click_id")
    if click_id:
        # Calculate dwell time (time spent on document)
        dwell_time = request.args.get("dwell_time", 0, type=int)
        analytics_data.track_dwell_time(click_id, dwell_time)
    
    # Redirect back to results or search page
    last_query = session.get('last_search_query', '')
    if last_query:
        return redirect(f"/search?query={last_query}")
    return redirect("/")


@app.route("/stats", methods=["GET"])
def stats():
    """
    Show simple statistics example. ### Replace with yourdashboard ###
    :return:
    """

    docs = []
    for doc_id in analytics_data.fact_clicks:
        row: Document = corpus[doc_id]
        count = analytics_data.fact_clicks[doc_id]
        doc = StatsDocument(
            pid=row.pid,
            title=row.title,
            description=row.description,
            url=row.url,
            count=count,
        )
        docs.append(doc)

    # simulate sort by ranking
    docs.sort(key=lambda doc: doc.count, reverse=True)
    return render_template("stats.html", clicks_data=docs)


@app.route("/dashboard", methods=["GET"])
def dashboard():
    visited_docs = []
    for doc_id in analytics_data.fact_clicks.keys():
        d: Document = corpus[doc_id]
        doc = ClickedDoc(doc_id, d.description, analytics_data.fact_clicks[doc_id])
        visited_docs.append(doc)

    # simulate sort by ranking
    visited_docs.sort(key=lambda doc: doc.counter, reverse=True)

    for doc in visited_docs:
        print(doc)
    return render_template("dashboard.html", visited_docs=visited_docs)


# New route added for generating an examples of basic Altair plot (used for dashboard)
@app.route("/plot_number_of_views", methods=["GET"])
def plot_number_of_views():
    return analytics_data.plot_number_of_views()


# ========== ANALYTICS ROUTES ==========

@app.route("/analytics/dashboard")
def analytics_dashboard():
    """Direct route to analytics dashboard"""
    print("Loading analytics dashboard...")
    try:
        chart_data = analytics_data.get_chart_data_for_template()
        print(f"Chart data loaded: {len(chart_data.get('popular_terms', []))} terms")
        return render_template('dashboard.html', 
                             page_title="Analytics Dashboard",
                             chart_data=chart_data)
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        # Fallback to legacy dashboard
        visited_docs = []
        for doc_id in analytics_data.fact_clicks.keys():
            d: Document = corpus[doc_id]
            doc = ClickedDoc(doc_id, d.description, analytics_data.fact_clicks[doc_id])
            visited_docs.append(doc)
        visited_docs.sort(key=lambda doc: doc.counter, reverse=True)
        return render_template("dashboard.html", visited_docs=visited_docs)


@app.route("/analytics/api/stats")
def analytics_api_stats():
    """API endpoint for analytics stats"""
    chart_data = analytics_data.get_chart_data_for_template()
    return jsonify(chart_data)


@app.route("/analytics/api/track-click", methods=['POST'])
def analytics_track_click():
    """Track a click on a search result"""
    data = request.json
    query_id = data.get('query_id')
    doc_id = data.get('doc_id')
    doc_title = data.get('doc_title', '')
    ranking_position = data.get('ranking_position', 1)
    
    if not query_id or not doc_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    click_id = analytics_data.track_click(query_id, doc_id, doc_title, ranking_position)
    return jsonify({"click_id": click_id, "status": "success"})


@app.route("/analytics/api/chart-data")
def analytics_chart_data():
    """Get chart data in Chart.js format"""
    chart_data = analytics_data.get_chart_data_for_template()
    
    # Format for Chart.js
    response_data = {
        "browser_data": {
            "labels": list(chart_data.get("browser_stats", {}).keys()),
            "data": list(chart_data.get("browser_stats", {}).values()),
            "backgroundColor": ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF"]
        },
        "device_data": {
            "labels": list(chart_data.get("device_stats", {}).keys()),
            "data": list(chart_data.get("device_stats", {}).values()),
            "backgroundColor": ["#36A2EB", "#FF6384", "#FFCE56"]
        },
        "hourly_data": {
            "labels": [f"{h:02d}:00" for h in range(24)],
            "data": chart_data.get("hourly_activity", [0]*24)
        },
        "rank_data": {
            "labels": [item["rank"] for item in chart_data.get("click_distribution_by_rank", [])],
            "data": [item["clicks"] for item in chart_data.get("click_distribution_by_rank", [])],
            "backgroundColor": ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF", "#FF9F40"]
        }
    }
    return jsonify(response_data)


@app.route("/api/analytics/track-session-end", methods=["POST"])
def track_session_end():
    """Track when user ends their session"""
    session_id = session.get('session_id')
    if session_id:
        analytics_data.end_session(session_id)
    
    # Clear session
    session.clear()
    return jsonify({"status": "success"})


@app.route("/api/analytics/current-stats", methods=["GET"])
def get_current_stats():
    """Get current analytics stats for AJAX updates"""
    chart_data = analytics_data.get_chart_data_for_template()
    return jsonify(chart_data)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "corpus_size": len(corpus),
        "sessions_count": len(analytics_data.sessions),
        "queries_count": len(analytics_data.queries),
        "clicks_count": len(analytics_data.clicks)
    })


def _detect_mission_type(query: str, results: list) -> MissionType:
    """Detect mission type based on query and results"""
    query_lower = query.lower()
    
    # Simple heuristics for mission detection
    if any(word in query_lower for word in ['compare', 'vs', 'versus', 'difference']):
        return MissionType.COMPARISON
    elif any(word in query_lower for word in ['buy', 'purchase', 'price', 'cost', 'sale']):
        return MissionType.SHOPPING
    elif any(word in query_lower for word in ['research', 'study', 'learn', 'information']):
        return MissionType.RESEARCH
    elif len(results) > 10:  # Many results suggests browsing
        return MissionType.BROWSING
    else:
        return MissionType.BROWSING


# Add before_request handler for analytics
@app.before_request
def before_request():
    """Track page views and ensure session exists"""
    if request.endpoint and request.endpoint not in ['static', 'plot_number_of_views']:
        # Ensure session exists
        if 'session_id' not in session:
            user_agent = request.headers.get("User-Agent")
            user_ip = request.remote_addr
            
            if request.headers.get('X-Forwarded-For'):
                user_ip = request.headers.get('X-Forwarded-For').split(',')[0]
            
            session['session_id'] = analytics_data.start_session(user_agent, user_ip)


if __name__ == "__main__":
    print("\n" + "="*50)
    print("Starting IRWA Search Engine with Analytics")
    print("="*50)
    print(f"Dashboard available at: http://localhost:8088/analytics/dashboard")
    print("="*50 + "\n")
    
    app.run(port=8088, host="0.0.0.0", threaded=False, debug=os.getenv("DEBUG"))