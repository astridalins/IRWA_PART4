import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
import uuid
import pandas as pd
import altair as alt
from dataclasses import dataclass, asdict
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
class QueryAnalytics:
    query_id: str
    query_text: str
    terms: List[str]
    term_count: int
    timestamp: datetime
    session_id: str
    filters_applied: Dict[str, Any] = None
    results_returned: int = 0
    
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

class AnalyticsData:
    """
    An in memory persistence object for comprehensive analytics tracking.
    """
    
    def __init__(self):
        # Existing click tracking
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
        
        # User agent parsing (simplified)
        self.browser_stats = Counter()
        self.os_stats = Counter()
        self.device_stats = Counter()
        
        # Time-based data
        self.hourly_activity = [0] * 24
        self.daily_activity = [0] * 7  # 0=Monday, 6=Sunday
        
        # Mission tracking
        self.missions_by_session: Dict[str, str] = {}  # session_id -> mission_type
    
    def start_session(self, user_agent: Optional[str] = None, user_ip: Optional[str] = None) -> str:
        """Start a new user session"""
        session_id = str(uuid.uuid4())
        
        # Utilitza valors per defecte si no es proporcionen
        if user_agent is None:
            user_agent = "Unknown"
        if user_ip is None:
            user_ip = "0.0.0.0"
        
        # Parse browser info from user agent
        browser = self._parse_browser(user_agent)
        os = self._parse_os(user_agent)
        device_type = self._parse_device(user_agent)
        
        # Update statistics
        self.browser_stats[browser] += 1
        self.os_stats[os] += 1
        self.device_stats[device_type.value] += 1
        
        # Create session object (CORREGIT: utilitza SessionAnalytics, no diccionari)
        session = SessionAnalytics(
            session_id=session_id,
            start_time=datetime.now(),
            user_agent=user_agent,
            browser=browser,
            os=os,
            device_type=device_type,
            ip_address=user_ip
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
    
    def track_query(self, session_id: Optional[str] = None, query_text: str = "", 
                   results_count: int = 0, 
                   filters: Optional[Dict[str, Any]] = None) -> str:
        """Track a search query"""
        if session_id is None or session_id not in self.sessions:
            # Auto-start session if not exists
            session_id = self.start_session(
                user_agent="Unknown (auto-created)", 
                user_ip="0.0.0.0"
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
            results_returned=results_count
        )
        
        self.queries[query_id] = query
        self.queries_by_session[session_id].append(query_id)
        self.query_popularity[query_text] += 1
        
        # Update term statistics
        for term in terms:
            self.query_terms_counter[term] += 1
        
        # CORREGIT: Assegurar que la sessió és un objecte SessionAnalytics
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if isinstance(session, SessionAnalytics):
                session.queries_count += 1
            else:
                # Si per alguna raó és un diccionari, convertir-lo
                session = SessionAnalytics(
                    session_id=session_id,
                    start_time=datetime.now(),
                    user_agent=session.get('user_agent', 'Unknown'),
                    browser=session.get('browser', 'unknown'),
                    os=session.get('os', 'unknown'),
                    device_type=session.get('device_type', DeviceType.DESKTOP),
                    ip_address=session.get('user_ip', '0.0.0.0'),
                    queries_count=session.get('queries_count', 0) + 1
                )
                self.sessions[session_id] = session
        
        # Track hourly/daily activity
        hour = datetime.now().hour
        weekday = datetime.now().weekday()
        self.hourly_activity[hour] += 1
        self.daily_activity[weekday] += 1
        
        return query_id
    
    def track_click(self, query_id: str, doc_id: str, doc_title: str, 
                   ranking_position: int) -> str:
        """Track a click on a search result"""
        click_id = str(uuid.uuid4())
        
        click = ClickAnalytics(
            click_id=click_id,
            query_id=query_id,
            doc_id=doc_id,
            doc_title=doc_title,
            ranking_position=ranking_position,
            click_time=datetime.now()
        )
        
        self.clicks[click_id] = click
        self.clicks_by_query[query_id].append(click_id)
        self.clicks_by_doc[doc_id].append(click_id)
        
        # Update click counters
        self.fact_clicks[doc_id] = self.fact_clicks.get(doc_id, 0) + 1
        self.doc_popularity[doc_id] += 1
        
        # Update session click count
        query = self.queries.get(query_id)
        if query and query.session_id in self.sessions:
            session = self.sessions[query.session_id]
            if isinstance(session, SessionAnalytics):
                session.clicks_count += 1
            else:
                # Convertir diccionari a SessionAnalytics si cal
                session_obj = SessionAnalytics(
                    session_id=query.session_id,
                    start_time=datetime.now(),
                    user_agent=session.get('user_agent', 'Unknown'),
                    browser=session.get('browser', 'unknown'),
                    os=session.get('os', 'unknown'),
                    device_type=session.get('device_type', DeviceType.DESKTOP),
                    ip_address=session.get('user_ip', '0.0.0.0'),
                    queries_count=session.get('queries_count', 0),
                    clicks_count=session.get('clicks_count', 0) + 1
                )
                self.sessions[query.session_id] = session_obj
        
        return click_id
    
    def track_dwell_time(self, click_id: str, dwell_time_ms: int):
        """Track dwell time for a click"""
        if click_id in self.clicks:
            self.clicks[click_id].dwell_time_ms = dwell_time_ms
            self.clicks[click_id].dwell_end = datetime.now()
    
    def start_dwell_time(self, click_id: str):
        """Start tracking dwell time"""
        if click_id in self.clicks:
            self.clicks[click_id].dwell_start = datetime.now()
    
    def set_mission_type(self, session_id: str, mission_type: MissionType):
        """Set mission type for a session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if isinstance(session, SessionAnalytics):
                session.mission_type = mission_type
            self.missions_by_session[session_id] = mission_type.value
    
    def save_query_terms(self, terms: str) -> int:
        """Legacy method for compatibility"""
        term_list = terms.split()
        for term in term_list:
            self.query_terms_counter[term] += 1
        return len(term_list)
    
    # Helper methods for parsing
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
    
    # Analytics Methods
    def get_popular_queries(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular queries"""
        return self.query_popularity.most_common(limit)
    
    def get_popular_documents(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most clicked documents"""
        return self.doc_popularity.most_common(limit)
    
    def get_popular_terms(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular search terms"""
        return self.query_terms_counter.most_common(limit)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        if not self.sessions:
            return {
                "avg_duration": 0, 
                "total_sessions": 0,
                "total_queries": 0,
                "total_clicks": 0,
                "avg_queries_per_session": 0,
                "avg_clicks_per_session": 0
            }
        
        total_queries = 0
        total_clicks = 0
        
        for session in self.sessions.values():
            if isinstance(session, SessionAnalytics):
                total_queries += session.queries_count
                total_clicks += session.clicks_count
            else:
                # Si és un diccionari (per compatibilitat)
                total_queries += session.get('queries_count', 0)
                total_clicks += session.get('clicks_count', 0)
        
        if not self.session_times:
            avg_duration = 0
        else:
            avg_duration = sum(self.session_times) / len(self.session_times)
        
        return {
            "total_sessions": len(self.sessions),
            "avg_session_duration_sec": round(avg_duration, 2),
            "total_queries": total_queries,
            "total_clicks": total_clicks,
            "avg_queries_per_session": round(total_queries / len(self.sessions), 2) if self.sessions else 0,
            "avg_clicks_per_session": round(total_clicks / len(self.sessions), 2) if self.sessions else 0
        }
    
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
    
    def get_dwell_time_stats(self) -> Dict[str, float]:
        """Get dwell time statistics"""
        dwell_times = [
            click.dwell_time_ms for click in self.clicks.values() 
            if click.dwell_time_ms is not None
        ]
        
        if not dwell_times:
            return {"avg_ms": 0, "min_ms": 0, "max_ms": 0}
        
        return {
            "avg_ms": round(sum(dwell_times) / len(dwell_times)),
            "min_ms": min(dwell_times),
            "max_ms": max(dwell_times)
        }
    
    # Visualization Methods
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
        session_stats = self.get_session_stats()
        dwell_stats = self.get_dwell_time_stats()
        
        return {
            "stats": {
                "total_queries": len(self.queries),
                "total_clicks": len(self.clicks),
                "total_sessions": len(self.sessions),
                "click_through_rate": self.get_click_through_rate(),
                "avg_ranking_position": self.get_avg_ranking_position(),
                **session_stats,
                **dwell_stats
            },
            "popular_queries": self.get_popular_queries(10),
            "popular_documents": self.get_popular_documents(10),
            "popular_terms": self.get_popular_terms(15),
            "browser_stats": dict(self.browser_stats.most_common()),
            "os_stats": dict(self.os_stats.most_common()),
            "device_stats": dict(self.device_stats.most_common()),
            "hourly_activity": self.hourly_activity,
            "daily_activity": self.daily_activity,
            "click_distribution_by_rank": self._get_click_distribution_by_rank()
        }
    
    def _get_click_distribution_by_rank(self) -> List[Dict[str, Any]]:
        """Get distribution of clicks by ranking position"""
        if not self.clicks:
            return []
        
        positions = [click.ranking_position for click in self.clicks.values()]
        position_counts = Counter(positions)
        
        # Group positions 6-10 together
        distribution = []
        for rank in sorted(position_counts.keys()):
            if rank <= 5:
                distribution.append({"rank": f"#{rank}", "clicks": position_counts[rank]})
        
        # Add grouped 6-10 if any
        clicks_6_10 = sum(count for rank, count in position_counts.items() if 6 <= rank <= 10)
        if clicks_6_10 > 0:
            distribution.append({"rank": "#6-10", "clicks": clicks_6_10})
        
        # Add 11+ if any
        clicks_11_plus = sum(count for rank, count in position_counts.items() if rank > 10)
        if clicks_11_plus > 0:
            distribution.append({"rank": "#11+", "clicks": clicks_11_plus})
        
        return distribution


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