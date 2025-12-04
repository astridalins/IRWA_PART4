import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
import uuid
import pandas as pd
import altair as alt
from dataclasses import dataclass, asdict, field
from enum import Enum

class DeviceType(Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"

class MissionType(Enum):
    RESEARCH = "research"
    SHOPPING = "shopping"
    BROWSING = "browsing"
    COMPARISON = "comparison"

@dataclass
class HTTPRequest:
    """Store HTTP request data"""
    request_id: str
    timestamp: datetime
    method: str
    endpoint: str
    status_code: int = 200
    response_time_ms: float = 0.0
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class QueryAnalytics:
    query_id: str
    query_text: str
    terms: List[str]
    term_count: int
    timestamp: datetime
    session_id: str
    filters_applied: Dict[str, Any] = None
    results_returned: int = 0
    algorithm_used: str = "tfidf"
    search_time_ms: float = 0.0
    
@dataclass
class ClickAnalytics:
    click_id: str
    query_id: str
    doc_id: str
    doc_title: str
    ranking_position: int
    click_time: datetime
    dwell_start: Optional[datetime] = None
    dwell_end: Optional[datetime] = None
    dwell_time_ms: Optional[int] = None
    session_id: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

@dataclass
class SessionAnalytics:
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    user_agent: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[DeviceType] = None
    ip_address: Optional[str] = None
    mission_type: Optional[MissionType] = None
    queries_count: int = 0
    clicks_count: int = 0
    total_dwell_time_ms: int = 0
    page_views: int = 0

class AnalyticsData:
    """
    An in memory persistence object for comprehensive analytics tracking.
    """
    
    def __init__(self):
        # HTTP Requests tracking
        self.http_requests: Dict[str, HTTPRequest] = {}
        self.requests_by_session: Dict[str, List[str]] = defaultdict(list)
        self.requests_by_endpoint: Dict[str, List[str]] = defaultdict(list)
        
        # Existing click tracking (legacy)
        self.fact_clicks = dict([])
        
        # Enhanced analytics storage
        self.queries: Dict[str, QueryAnalytics] = {}
        self.clicks: Dict[str, ClickAnalytics] = {}
        self.sessions: Dict[str, SessionAnalytics] = {}
        
        # Indexes for faster queries
        self.queries_by_session: Dict[str, List[str]] = defaultdict(list)
        self.clicks_by_query: Dict[str, List[str]] = defaultdict(list)
        self.clicks_by_doc: Dict[str, List[str]] = defaultdict(list)
        
        # Statistics
        self.query_terms_counter = Counter()
        self.query_popularity = Counter()
        self.doc_popularity = Counter()
        self.session_times = []
        
        # User agent parsing
        self.browser_stats = Counter()
        self.os_stats = Counter()
        self.device_stats = Counter()
        
        # Time-based data
        self.hourly_activity = [0] * 24
        self.daily_activity = [0] * 7  # 0=Monday, 6=Sunday
        self.monthly_activity = [0] * 12
        
        # Mission tracking
        self.missions_by_session: Dict[str, str] = {}  # session_id -> mission_type
        
        # Performance metrics
        self.response_times = []
        self.search_times = []
    
    # ========== 1. HTTP REQUEST TRACKING ==========
    
    def track_http_request(self, method: str, endpoint: str, status_code: int = 200,
                          response_time_ms: float = 0.0, session_id: Optional[str] = None,
                          user_agent: Optional[str] = None, ip_address: Optional[str] = None,
                          referrer: Optional[str] = None) -> str:
        """Track an HTTP request"""
        request_id = str(uuid.uuid4())
        
        request = HTTPRequest(
            request_id=request_id,
            timestamp=datetime.now(),
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response_time_ms=response_time_ms,
            user_agent=user_agent,
            ip_address=ip_address,
            referrer=referrer,
            session_id=session_id
        )
        
        self.http_requests[request_id] = request
        
        # Index by session
        if session_id:
            self.requests_by_session[session_id].append(request_id)
        
        # Index by endpoint
        self.requests_by_endpoint[endpoint].append(request_id)
        
        # Track performance
        self.response_times.append(response_time_ms)
        
        # Track page views for session
        if session_id and session_id in self.sessions:
            self.sessions[session_id].page_views += 1
        
        return request_id
    
    def track_click(self, query_id: str, doc_id: str, doc_title: str, 
                   ranking_position: int, session_id: Optional[str] = None,
                   user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> str:
        """Track a click on a search result"""
        click_id = str(uuid.uuid4())
        
        click = ClickAnalytics(
            click_id=click_id,
            query_id=query_id,
            doc_id=doc_id,
            doc_title=doc_title,
            ranking_position=ranking_position,
            click_time=datetime.now(),
            session_id=session_id,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        self.clicks[click_id] = click
        self.clicks_by_query[query_id].append(click_id)
        self.clicks_by_doc[doc_id].append(click_id)
        
        # Update click counters
        self.fact_clicks[doc_id] = self.fact_clicks.get(doc_id, 0) + 1
        self.doc_popularity[doc_id] += 1
        
        # Update session click count
        if session_id and session_id in self.sessions:
            self.sessions[session_id].clicks_count += 1
        
        return click_id
    
    # ========== 2. QUERY TRACKING ==========
    
    def track_query(self, session_id: Optional[str] = None, query_text: str = "", 
                   results_count: int = 0, search_time_ms: float = 0.0,
                   algorithm_used: str = "tfidf", 
                   filters: Optional[Dict[str, Any]] = None) -> str:
        """Track a search query with detailed metrics"""
        if session_id is None or session_id not in self.sessions:
            # Auto-start session if not exists
            session_id = self.start_session(
                user_agent="Unknown (auto-created)", 
                ip_address="0.0.0.0"
            )
        
        query_id = str(uuid.uuid4())
        terms = query_text.lower().split() if query_text else []
        
        query = QueryAnalytics(
            query_id=query_id,
            query_text=query_text,
            terms=terms,
            term_count=len(terms),
            timestamp=datetime.now(),
            session_id=session_id,
            filters_applied=filters,
            results_returned=results_count,
            algorithm_used=algorithm_used,
            search_time_ms=search_time_ms
        )
        
        self.queries[query_id] = query
        self.queries_by_session[session_id].append(query_id)
        self.query_popularity[query_text] += 1
        
        # Update term statistics
        for term in terms:
            self.query_terms_counter[term] += 1
        
        # Update session query count
        if session_id in self.sessions:
            self.sessions[session_id].queries_count += 1
        
        # Track search performance
        if search_time_ms > 0:
            self.search_times.append(search_time_ms)
        
        # Track hourly/daily/monthly activity
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        month = now.month - 1  # 0-based
        
        self.hourly_activity[hour] += 1
        self.daily_activity[weekday] += 1
        self.monthly_activity[month] += 1
        
        return query_id
    
    # ========== 3. RESULTS/DOCUMENTS TRACKING ==========
    
    def start_dwell_time(self, click_id: str):
        """Start tracking dwell time for a click"""
        if click_id in self.clicks:
            self.clicks[click_id].dwell_start = datetime.now()
    
    def track_dwell_time(self, click_id: str, dwell_time_ms: int):
        """Track dwell time for a click"""
        if click_id in self.clicks:
            self.clicks[click_id].dwell_time_ms = dwell_time_ms
            self.clicks[click_id].dwell_end = datetime.now()
            
            # Update session total dwell time
            click = self.clicks[click_id]
            if click.session_id and click.session_id in self.sessions:
                self.sessions[click.session_id].total_dwell_time_ms += dwell_time_ms
    
    def get_document_stats(self, doc_id: str) -> Dict[str, Any]:
        """Get statistics for a specific document"""
        if doc_id not in self.clicks_by_doc:
            return {"clicks": 0, "queries": [], "avg_position": 0}
        
        clicks = self.clicks_by_doc[doc_id]
        query_ids = set()
        positions = []
        dwell_times = []
        
        for click_id in clicks:
            click = self.clicks[click_id]
            query_ids.add(click.query_id)
            positions.append(click.ranking_position)
            if click.dwell_time_ms:
                dwell_times.append(click.dwell_time_ms)
        
        return {
            "clicks": len(clicks),
            "query_count": len(query_ids),
            "avg_ranking_position": round(sum(positions) / len(positions), 2) if positions else 0,
            "avg_dwell_time_ms": round(sum(dwell_times) / len(dwell_times)) if dwell_times else 0,
            "queries": list(query_ids)[:10]  # Top 10 queries
        }
    
    # ========== 4. USER CONTEXT/ VISITOR TRACKING ==========
    
    def start_session(self, user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> str:
        """Start a new user session"""
        session_id = str(uuid.uuid4())
        
        # Parse user agent
        browser = self._parse_browser(user_agent) if user_agent else "unknown"
        os = self._parse_os(user_agent) if user_agent else "unknown"
        device_type = self._parse_device(user_agent) if user_agent else DeviceType.DESKTOP
        
        # Update statistics
        self.browser_stats[browser] += 1
        self.os_stats[os] += 1
        self.device_stats[device_type.value] += 1
        
        # Create session object
        session = SessionAnalytics(
            session_id=session_id,
            start_time=datetime.now(),
            user_agent=user_agent,
            browser=browser,
            os=os,
            device_type=device_type,
            ip_address=ip_address
        )
        
        self.sessions[session_id] = session
        return session_id
    
    def end_session(self, session_id: str):
        """End a user session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.end_time = datetime.now()
            session_duration = (session.end_time - session.start_time).total_seconds()
            self.session_times.append(session_duration)
    
    def set_mission_type(self, session_id: str, mission_type: MissionType):
        """Set mission type for a session"""
        if session_id in self.sessions:
            self.sessions[session_id].mission_type = mission_type
            self.missions_by_session[session_id] = mission_type.value
    
    # ========== HELPER METHODS ==========
    
    def _parse_browser(self, user_agent: Optional[str]) -> str:
        if not user_agent:
            return "unknown"
        ua_lower = user_agent.lower()
        if "chrome" in ua_lower and "chromium" not in ua_lower:
            return "chrome"
        elif "firefox" in ua_lower:
            return "firefox"
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            return "safari"
        elif "edge" in ua_lower:
            return "edge"
        elif "opera" in ua_lower:
            return "opera"
        elif "msie" in ua_lower or "trident" in ua_lower:
            return "ie"
        return "other"
    
    def _parse_os(self, user_agent: Optional[str]) -> str:
        if not user_agent:
            return "unknown"
        ua_lower = user_agent.lower()
        if "windows" in ua_lower:
            return "windows"
        elif "mac" in ua_lower or "os x" in ua_lower:
            return "macos"
        elif "linux" in ua_lower:
            return "linux"
        elif "android" in ua_lower:
            return "android"
        elif "ios" in ua_lower or "iphone" in ua_lower:
            return "ios"
        elif "ubuntu" in ua_lower:
            return "ubuntu"
        elif "fedora" in ua_lower:
            return "fedora"
        return "other"
    
    def _parse_device(self, user_agent: Optional[str]) -> Optional[DeviceType]:
        if not user_agent:
            return DeviceType.DESKTOP
        ua_lower = user_agent.lower()
        if "mobile" in ua_lower:
            return DeviceType.MOBILE
        elif "tablet" in ua_lower or "ipad" in ua_lower:
            return DeviceType.TABLET
        elif "desktop" in ua_lower or ("windows" in ua_lower or "mac" in ua_lower or "linux" in ua_lower):
            return DeviceType.DESKTOP
        return DeviceType.DESKTOP
    
    # ========== ANALYTICS METHODS ==========
    
    def save_query_terms(self, terms: str) -> int:
        """Legacy method for compatibility"""
        term_list = terms.split()
        for term in term_list:
            self.query_terms_counter[term] += 1
        return len(term_list)
    
    def get_http_stats(self) -> Dict[str, Any]:
        """Get HTTP request statistics"""
        if not self.http_requests:
            return {
                "total_requests": 0,
                "avg_response_time": 0,
                "endpoint_stats": {},
                "status_codes": {}
            }
        
        # Count status codes
        status_codes = Counter()
        endpoint_stats = {}
        
        for request in self.http_requests.values():
            status_codes[request.status_code] += 1
            
            if request.endpoint not in endpoint_stats:
                endpoint_stats[request.endpoint] = {
                    "count": 0,
                    "avg_response_time": 0,
                    "total_time": 0
                }
            
            endpoint_stats[request.endpoint]["count"] += 1
            endpoint_stats[request.endpoint]["total_time"] += request.response_time_ms
        
        # Calculate averages
        for endpoint in endpoint_stats:
            if endpoint_stats[endpoint]["count"] > 0:
                endpoint_stats[endpoint]["avg_response_time"] = round(
                    endpoint_stats[endpoint]["total_time"] / endpoint_stats[endpoint]["count"], 2
                )
        
        return {
            "total_requests": len(self.http_requests),
            "avg_response_time": round(sum(self.response_times) / len(self.response_times), 2) if self.response_times else 0,
            "endpoint_stats": endpoint_stats,
            "status_codes": dict(status_codes.most_common(10))
        }
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Get query statistics"""
        if not self.queries:
            return {
                "total_queries": 0,
                "avg_terms": 0,
                "avg_search_time": 0,
                "algorithm_distribution": {}
            }
        
        total_terms = sum(q.term_count for q in self.queries.values())
        algorithm_dist = Counter(q.algorithm_used for q in self.queries.values())
        
        return {
            "total_queries": len(self.queries),
            "avg_terms": round(total_terms / len(self.queries), 2),
            "avg_search_time": round(sum(self.search_times) / len(self.search_times), 2) if self.search_times else 0,
            "algorithm_distribution": dict(algorithm_dist.most_common()),
            "unique_terms": len(self.query_terms_counter)
        }
    
    def get_document_stats_summary(self) -> Dict[str, Any]:
        """Get document statistics summary"""
        if not self.clicks:
            return {
                "total_clicks": 0,
                "unique_documents": 0,
                "avg_dwell_time": 0,
                "click_distribution": {}
            }
        
        dwell_times = [c.dwell_time_ms for c in self.clicks.values() if c.dwell_time_ms]
        
        # Click distribution by hour
        click_dist = [0] * 24
        for click in self.clicks.values():
            hour = click.click_time.hour
            click_dist[hour] += 1
        
        return {
            "total_clicks": len(self.clicks),
            "unique_documents": len(self.clicks_by_doc),
            "avg_dwell_time": round(sum(dwell_times) / len(dwell_times)) if dwell_times else 0,
            "click_distribution_by_hour": click_dist,
            "top_documents": self.get_popular_documents(10)
        }
    
    def get_user_context_stats(self) -> Dict[str, Any]:
        """Get user context statistics"""
        return {
            "browsers": dict(self.browser_stats.most_common()),
            "operating_systems": dict(self.os_stats.most_common()),
            "devices": dict(self.device_stats.most_common()),
            "hourly_activity": self.hourly_activity,
            "daily_activity": self.daily_activity,
            "monthly_activity": self.monthly_activity,
            "mission_distribution": dict(Counter(self.missions_by_session.values()).most_common())
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        if not self.sessions:
            return {
                "total_sessions": 0,
                "avg_duration": 0,
                "avg_queries": 0,
                "avg_clicks": 0,
                "avg_page_views": 0
            }
        
        total_queries = sum(s.queries_count for s in self.sessions.values())
        total_clicks = sum(s.clicks_count for s in self.sessions.values())
        total_page_views = sum(s.page_views for s in self.sessions.values())
        total_dwell_time = sum(s.total_dwell_time_ms for s in self.sessions.values())
        
        avg_duration = sum(self.session_times) / len(self.session_times) if self.session_times else 0
        
        return {
            "total_sessions": len(self.sessions),
            "avg_session_duration_sec": round(avg_duration, 2),
            "avg_queries_per_session": round(total_queries / len(self.sessions), 2),
            "avg_clicks_per_session": round(total_clicks / len(self.sessions), 2),
            "avg_page_views_per_session": round(total_page_views / len(self.sessions), 2),
            "avg_dwell_time_per_session_ms": round(total_dwell_time / len(self.sessions), 2) if self.sessions else 0
        }
    
    def get_popular_queries(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular queries"""
        return self.query_popularity.most_common(limit)
    
    def get_popular_documents(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most clicked documents"""
        return self.doc_popularity.most_common(limit)
    
    def get_popular_terms(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular search terms"""
        return self.query_terms_counter.most_common(limit)
    
    def get_click_through_rate(self) -> float:
        """Calculate click-through rate"""
        total_queries = len(self.queries)
        total_clicks = len(self.clicks)
        if total_queries == 0:
            return 0.0
        return round(total_clicks / total_queries * 100, 2)
    
    def get_avg_ranking_position(self) -> float:
        """Calculate average ranking position of clicked results"""
        if not self.clicks:
            return 0.0
        positions = [click.ranking_position for click in self.clicks.values()]
        return round(sum(positions) / len(positions), 2)
    
    # ========== VISUALIZATION METHODS ==========
    
    def plot_number_of_views(self):
        """Plot number of views per document"""
        data = [
            {"Document ID": doc_id, "Number of Views": count}
            for doc_id, count in self.fact_clicks.items()
        ]
        df = pd.DataFrame(data)
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="Document ID", y="Number of Views")
            .properties(title="Number of Views per Document", width=600)
        )
        return chart.to_html()
    
    def get_chart_data_for_template(self) -> Dict[str, Any]:
        """Get all data needed for the dashboard template"""
        return {
            "http_stats": self.get_http_stats(),
            "query_stats": self.get_query_stats(),
            "document_stats": self.get_document_stats_summary(),
            "user_context_stats": self.get_user_context_stats(),
            "session_stats": self.get_session_stats(),
            "popular_queries": self.get_popular_queries(10),
            "popular_documents": self.get_popular_documents(10),
            "popular_terms": self.get_popular_terms(15),
            "click_through_rate": self.get_click_through_rate(),
            "avg_ranking_position": self.get_avg_ranking_position()
        }


# ========== CLICKEDDOC CLASS (LEGACY COMPATIBILITY) ==========

class ClickedDoc:
    def __init__(self, doc_id, description, counter):
        self.doc_id = doc_id
        self.description = description
        self.counter = counter

    def to_json(self):
        return self.__dict__

    def __str__(self):
        """
        Print the object content as a JSON string
        """
        return json.dumps(self.__dict__)