from flask import Blueprint, render_template, request, jsonify, session
from myapp.analytics.analytics_data import AnalyticsData, MissionType

# Create the blueprint
analytics_bp = Blueprint('analytics', __name__)

# Create analytics data instance for this module
analytics_data = AnalyticsData()

# Initialize with sample data for demonstration
def _initialize_sample_data():
    """Initialize with sample data for demonstration"""
    browsers = ['Chrome', 'Firefox', 'Safari', 'Edge']
    devices = ['Desktop', 'Mobile', 'Tablet']
    os_list = ['Windows', 'macOS', 'Linux', 'Android', 'iOS']
    
    import random
    
    # Create some sample sessions
    for i in range(5):
        session_id = analytics_data.start_session(
            user_agent=f"Mozilla/5.0 ({random.choice(os_list)}) {random.choice(browsers)}",
            user_ip=f"192.168.1.{i+1}"
        )
        
        # Add sample queries
        sample_queries = [
            "black dress summer",
            "running shoes nike",
            "leather jacket men",
            "smartwatch fitness",
            "backpack travel"
        ]
        
        for query in random.sample(sample_queries, random.randint(1, 3)):
            query_id = analytics_data.track_query(session_id, query, results_count=10)
            
            # Add sample clicks
            for _ in range(random.randint(0, 2)):
                analytics_data.track_click(
                    query_id,
                    doc_id=f"doc_{random.randint(1000, 9999)}",
                    doc_title=f"Product {random.randint(1, 100)}",
                    ranking_position=random.randint(1, 10)
                )
        
        analytics_data.end_session(session_id)

# Initialize sample data
_initialize_sample_data()

@analytics_bp.route('/dashboard')
def dashboard():
    """Main analytics dashboard page"""
    chart_data = analytics_data.get_chart_data_for_template()
    return render_template('dashboard.html', 
                         page_title="Analytics Dashboard",
                         chart_data=chart_data)

@analytics_bp.route('/api/stats')
def get_stats():
    """Get statistics data for AJAX updates"""
    chart_data = analytics_data.get_chart_data_for_template()
    return jsonify(chart_data)

@analytics_bp.route('/api/track-click', methods=['POST'])
def track_click():
    """Track a click on a search result"""
    data = request.json
    query_id = data.get('query_id')
    doc_id = data.get('doc_id')
    doc_title = data.get('doc_title', '')
    ranking_position = data.get('ranking_position', 1)
    
    if not query_id or not doc_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    click_id = analytics_data.track_click(query_id, doc_id, doc_title, ranking_position)
    return jsonify({"click_id": click_id})

@analytics_bp.route('/api/chart-data')
def get_chart_data():
    """Get chart data in Chart.js format"""
    chart_data = analytics_data.get_chart_data_for_template()
    
    # Format for Chart.js
    return jsonify({
        "browser_data": {
            "labels": list(chart_data.get("browser_stats", {}).keys()),
            "data": list(chart_data.get("browser_stats", {}).values()),
            "backgroundColor": [
                "#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", 
                "#9966FF", "#FF9F40", "#8AC926", "#1982C4"
            ]
        },
        "device_data": {
            "labels": list(chart_data.get("device_stats", {}).keys()),
            "data": list(chart_data.get("device_stats", {}).values()),
            "backgroundColor": ["#36A2EB", "#FF6384", "#FFCE56", "#4BC0C0"]
        }
    })