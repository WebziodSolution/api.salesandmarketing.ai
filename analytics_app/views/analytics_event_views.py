from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from common_app.models import Userlist, AnalyticsCsv, CampaignsEmailSend
from common_app.utils import get_final_tenant_id, api_response, get_client_id_by_tenant_id
from common_app.decrypt_string import DecryptString
from analytics_app.serializers import (AnalyticsDateFilterSerializer, AnalyticsDeviceUserCampaignSerializer, AnalyticsLogDataSerializer, AnalyticsEmailCampaignOpenMemberLinkSerializer)
from django.db import connection
import logging
import datetime
import base64
import json
import oracledb
# Connection configuration from settings
from salesandmarketingapi.envs import dev_settings, prod_settings
logger = logging.getLogger(__name__)

def with_oracle_db(view_func):
    """Decorator to inject Oracle DB cursor into the view."""
    def _wrapped_view(request, *args, **kwargs):
        try:
            connection.ensure_connection()
            raw_conn = connection.connection
            with raw_conn.cursor() as cursor:
                return view_func(request, cursor, *args, **kwargs)
        except Exception as e:
            logger.error(f"{view_func.__name__} error: {str(e)}")
            return api_response(500, str(e), {})
    _wrapped_view.__name__ = view_func.__name__
    return _wrapped_view

def get_start_and_end_date(date_filter_type, start_date=None, end_date=None):
    """
    Mirrors AnalyticsEventServiceImpl.getStartAndEndDate
    Returns timestamps in milliseconds.
    """
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + datetime.timedelta(days=1)
    
    if date_filter_type == "TODAY":
        start = today_start
        end = tomorrow_start
    elif date_filter_type == "YESTERDAY":
        start = today_start - datetime.timedelta(days=1)
        end = today_start
    elif date_filter_type == "LAST_7_DAYS":
        start = today_start - datetime.timedelta(days=6)
        end = tomorrow_start
    elif date_filter_type == "LAST_30_DAYS":
        start = today_start - datetime.timedelta(days=29)
        end = tomorrow_start
    elif date_filter_type == "THIS_MONTH":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = tomorrow_start
    elif date_filter_type == "LAST_MONTH":
        last_month_first_day = (today_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        this_month_first_day = today_start.replace(day=1)
        start = last_month_first_day
        end = this_month_first_day
    elif date_filter_type == "CUSTOM" and start_date and end_date:
        start = datetime.datetime.combine(start_date, datetime.time.min)
        end = datetime.datetime.combine(end_date, datetime.time.min) + datetime.timedelta(days=1)
    else: # ALL or default
        start = datetime.datetime(2000, 1, 1)
        end = now + datetime.timedelta(days=1)
        
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

def get_start_date_end_date_list_for_chart(date_filter_type, start_date=None, end_date=None):
    """
    Mirrors AnalyticsEventServiceImpl.getStartDateEndDateListForChart
    Returns list of date strings and start/end timestamps for each interval.
    """
    now = datetime.datetime.now()
    intervals = []
    
    if date_filter_type == "TODAY":
        for i in range(24):
            start = now.replace(hour=i, minute=0, second=0, microsecond=0)
            end = start + datetime.timedelta(hours=1)
            intervals.append({
                "label": start.strftime("%H:%M"),
                "start": int(start.timestamp() * 1000),
                "end": int(end.timestamp() * 1000)
            })
    elif date_filter_type == "YESTERDAY":
        yesterday = now - datetime.timedelta(days=1)
        for i in range(24):
            start = yesterday.replace(hour=i, minute=0, second=0, microsecond=0)
            end = start + datetime.timedelta(hours=1)
            intervals.append({
                "label": start.strftime("%H:%M"),
                "start": int(start.timestamp() * 1000),
                "end": int(end.timestamp() * 1000)
            })
    elif date_filter_type in ["LAST_7_DAYS", "LAST_30_DAYS", "CUSTOM", "THIS_MONTH", "LAST_MONTH"]:
        # Standard daily intervals
        s_ts, e_ts = get_start_and_end_date(date_filter_type, start_date, end_date)
        current = datetime.datetime.fromtimestamp(s_ts / 1000.0).replace(hour=0, minute=0, second=0, microsecond=0)
        final_end = datetime.datetime.fromtimestamp(e_ts / 1000.0)
        
        while current < final_end:
            next_day = current + datetime.timedelta(days=1)
            intervals.append({
                "label": current.strftime("%m/%d/%Y"),
                "start": int(current.timestamp() * 1000),
                "end": int(next_day.timestamp() * 1000)
            })
            current = next_day
    else: # ALL
        s_ts, e_ts = get_start_and_end_date(date_filter_type, start_date, end_date)
        intervals.append({
            "label": "All Time",
            "start": s_ts,
            "end": e_ts
        })
        
    return intervals

def get_minute_past_data(cursor, website_id, timestamp, call_count):
    """
    Python port of AnalyticsEventRepositoryCustomImpl.getMinutePastData
    """
    temp_count = call_count if (call_count is not None and call_count <= 30) else 30
    from_ts = timestamp - (temp_count * 60 * 1000)
    
    query = """
        SELECT 
            JSON_VALUE(DATA, '$.device_id'),
            MAX(JSON_VALUE(DATA, '$.host_data.address.country')),
            MAX(JSON_VALUE(DATA, '$.host_data.address.state')),
            MAX(JSON_VALUE(DATA, '$.host_data.address.city')),
            MAX(JSON_VALUE(DATA, '$.host_data.ip')),
            MAX(JSON_VALUE(DATA, '$.device_info.os')),
            MAX(JSON_VALUE(DATA, '$.device_info.browser')),
            MAX(JSON_VALUE(DATA, '$.device_info.device_type'))
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
          AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
          AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :timestamp
        GROUP BY JSON_VALUE(DATA, '$.device_id')
    """
    cursor.execute(query, {"website_id": website_id, "from_ts": from_ts, "timestamp": timestamp})
    rows = cursor.fetchall()
    
    results = []
    for r in rows:
        results.append({
            "deviceId": r[0],
            "country": r[1],
            "state": r[2],
            "city": r[3],
            "ip": r[4],
            "os": r[5],
            "browser": r[6],
            "deviceType": r[7]
        })
    return results

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getDashBoardComboList(request, cursor):
    website_id = request.GET.get("websiteId")

    # Unique Domains
    query_domains = """
        SELECT DISTINCT JSON_VALUE(DATA, '$.domain')
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
          AND JSON_VALUE(DATA, '$.domain') IS NOT NULL
    """
    cursor.execute(query_domains, {"website_id": website_id})
    domains = [row[0] for row in cursor.fetchall() if row[0]]

    # Parity: add www. if only 1 dot (root domain)
    processed_domains = []
    for d in domains:
        if d:
            if len(d.split('.')) == 2:
                processed_domains.append(f"www.{d}")
            processed_domains.append(d)

    # Unique Countries
    query_countries = """
        SELECT DISTINCT JSON_VALUE(DATA, '$.host_data.address.country')
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
          AND JSON_VALUE(DATA, '$.host_data.address.country') IS NOT NULL
    """
    cursor.execute(query_countries, {"website_id": website_id})
    countries = [row[0] for row in cursor.fetchall() if row[0]]

    return api_response(200, "Fetched successfully", {
        "domainList": sorted(list(set(processed_domains))),
        "countryList": sorted([c for c in countries if c])
    })

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getDevicesUsersCampaigns(request, cursor):
    """
    Returns unique devices, users, or campaigns based on filterType.
    Mirrors AnalyticsEventServiceImpl.getDevicesUsersCampaigns
    """
    serializer = AnalyticsDeviceUserCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    website_id = serializer.validated_data['websiteId']
    filter_type = serializer.validated_data['filterType'] # DEVICE, USER, CAMPAIGN, ALL
    date_filter = serializer.validated_data['dateFilterType']
    start_date = serializer.validated_data.get('startDate')
    end_date = serializer.validated_data.get('endDate')
    
    from_ts, to_ts = get_start_and_end_date(date_filter, start_date, end_date)
    final_member_id = get_final_tenant_id(request=request)
    
    results = []
    
    def process_devices():
        query = """
            SELECT 
                JSON_VALUE(DATA, '$.device_id'),
                MAX(JSON_VALUE(DATA, '$.host_data.address.country')),
                MAX(JSON_VALUE(DATA, '$.host_data.address.state')),
                MAX(JSON_VALUE(DATA, '$.host_data.address.city'))
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts
            GROUP BY JSON_VALUE(DATA, '$.device_id')
        """
        cursor.execute(query, {"website_id": website_id, "from_ts": from_ts, "to_ts": to_ts})
        devices = []
        for r in cursor.fetchall():
            devices.append({
                "deviceId": r[0],
                "country": r[1],
                "state": r[2],
                "city": r[3]
            })
            
        for d in devices:
            device_id = d.get("deviceId")
            country = d.get("country") or ""
            state = d.get("state") or ""
            city = d.get("city") or ""
            
            name_builder = "Anonymous: "
            if state:
                name_builder += state + " "
            if city:
                name_builder += "(" + city + "), "
            if country:
                name_builder += country
            
            # Remove trailing comma and space if country is empty
            if name_builder.endswith(", "):
                name_builder = name_builder[:-2]
                
            results.append({
                "value": device_id,
                "name": name_builder,
                "type": "DEVICE"
            })

    def process_users():
        query = """
            SELECT DISTINCT JSON_VALUE(DATA, '$.user_id')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
              AND JSON_VALUE(DATA, '$.user_id') IS NOT NULL
              AND JSON_VALUE(DATA, '$.user_id') != 'unknown'
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts
        """
        cursor.execute(query, {"website_id": website_id, "from_ts": from_ts, "to_ts": to_ts})
        users = [{"userId": r[0]} for r in cursor.fetchall() if r[0]]
        
        for u_doc in users:
            u = u_doc.get("userId")
            if not u:
                continue
            try:
                # Decodes base64 twice to match Java
                decoded_bytes = base64.b64decode(u.encode())
                decoded_str = base64.b64decode(decoded_bytes).decode('utf-8')
                user_id_val = int(decoded_str)
                
                user = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), emailId=user_id_val).first()
                if user is None:
                    continue
                
                results.append({
                    "value": u,
                    "name": f"User: {user.firstName or ''} {user.lastName or ''}",
                    "userId": user.emailId,
                    "groupId": user.groupId,
                    "type": "USER"
                })
            except Exception:
                continue

    if filter_type == "DEVICE":
        process_devices()
    elif filter_type == "USER":
        process_users()
    elif filter_type == "CAMPAIGN":
        query = """
            SELECT DISTINCT JSON_VALUE(DATA, '$.campaign_id')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
              AND JSON_VALUE(DATA, '$.campaign_id') IS NOT NULL
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts
        """
        cursor.execute(query, {"website_id": website_id, "from_ts": from_ts, "to_ts": to_ts})
        campaigns = [{"campaignId": r[0]} for r in cursor.fetchall() if r[0]]
        
        for c_doc in campaigns:
            c = c_doc.get("campaignId")
            if not c:
                continue
                
            users_data = []
            # Find all unique user_ids for this campaign
            query_users = """
                SELECT DISTINCT JSON_VALUE(DATA, '$.user_id')
                FROM ANALYTICS_EVENTS_LOGS
                WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
                  AND JSON_VALUE(DATA, '$.campaign_id') = :campaign_id
            """
            cursor.execute(query_users, {"website_id": website_id, "campaign_id": c})
            campaign_users = [{"userId": r[0]} for r in cursor.fetchall() if r[0]]
            
            for cu_doc in campaign_users:
                u = cu_doc.get("userId")
                if not u:
                    continue
                try:
                    decoded_bytes = base64.b64decode(u.encode())
                    decoded_str = base64.b64decode(decoded_bytes).decode('utf-8')
                    user_id_val = int(decoded_str)
                    
                    user = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), emailId=user_id_val).first()
                    if user is None:
                        continue
                    
                    users_data.append({
                        "value": u,
                        "name": f"{user.firstName or ''} {user.lastName or ''}",
                        "userId": user.emailId,
                        "groupId": user.groupId,
                        "type": "USER"
                    })
                except Exception:
                    continue
            
            try:
                decrypted_camp_id = DecryptString.set_enc_dec_user(c, "display", "Y")
                camp_send_id = int(decrypted_camp_id)
                campaign_email_send = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
            except Exception:
                continue
                
            if campaign_email_send is None:
                continue
                
            results.append({
                "value": c,
                "name": f"Campaign: {campaign_email_send.camp_name or ''}",
                "type": "CAMPAIGN",
                "users": users_data
            })
            
    elif filter_type == "ALL":
        # First process users, then process devices, exactly as Spring Boot does
        process_users()
        process_devices()
        
    return api_response(200, "Fetched successfully", {"list": results})

def _get_active_users_logic(cursor, website_id, from_ts, to_ts, date_filter, start_date, end_date, base_where, base_params):
    """Internal helper to calculate active users, counts and chart data."""
    def count_total_distinct_pages_by_timestamp_and_website():
        query = """
            SELECT COUNT(DISTINCT JSON_VALUE(DATA, '$.page_view_id'))
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.website_id') = :website_id
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
              AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts
        """
        cursor.execute(query, {"website_id": website_id, "from_ts": from_ts, "to_ts": to_ts})
        res = cursor.fetchone()
        return res[0] if res else 0

    def count_distinct(field, where_list, params_dict):
        field_expr = f"JSON_VALUE(DATA, '$.{field}')"
        query = f"""
            SELECT COUNT(DISTINCT {field_expr})
            FROM ANALYTICS_EVENTS_LOGS
            WHERE {" AND ".join(where_list)}
        """
        cursor.execute(query, params_dict)
        res = cursor.fetchone()
        return res[0] if res else 0

    unique_visitors = count_distinct("device_id", base_where, base_params)
    visits = count_distinct("session_id", base_where, base_params)
    page_views = count_total_distinct_pages_by_timestamp_and_website()
    page_per_visits = round(page_views / visits, 2) if visits > 0 else 0.0

    card_data = {
        "visits": visits,
        "pageViews": page_views,
        "pagePerVisits": page_per_visits,
        "uniqueVisitors": unique_visitors
    }

    # Chart Data
    chart_intervals = get_start_date_end_date_list_for_chart(date_filter, start_date, end_date)
    unique_visitor_chart = []
    visit_chart = []
    page_views_chart = []
    page_per_visits_chart = []

    for interval in chart_intervals:
        # Build interval match
        interval_where = []
        interval_params = {}
        for cond in base_where:
            if "$.timestamp" not in cond:
                interval_where.append(cond)
        
        # Copy other params
        for k, v in base_params.items():
            if k not in ["from_ts", "to_ts"]:
                interval_params[k] = v
                
        interval_where.append("JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :interval_start")
        interval_where.append("JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :interval_end")
        interval_params["interval_start"] = interval["start"]
        interval_params["interval_end"] = interval["end"]

        v_uv = count_distinct("device_id", interval_where, interval_params)
        v_v = count_distinct("session_id", interval_where, interval_params)

        # count_documents in interval_match
        query_count = f"""
            SELECT COUNT(*)
            FROM ANALYTICS_EVENTS_LOGS
            WHERE {" AND ".join(interval_where)}
        """
        cursor.execute(query_count, interval_params)
        res_count = cursor.fetchone()
        v_pv = res_count[0] if res_count else 0
        
        v_ppv = round(v_pv / v_v, 2) if v_v > 0 else 0.0

        unique_visitor_chart.append({f"{interval['label']}": v_uv})
        visit_chart.append({f"{interval['label']}": v_v})
        page_views_chart.append({f"{interval['label']}": v_pv})
        page_per_visits_chart.append({f"{interval['label']}": v_ppv})

    return {
        "cardData": card_data,
        "chartData": {
            "pageViewsChartData": page_views_chart,
            "visitsChartData": visit_chart,
            "pagePerVisitsChartData": page_per_visits_chart,
            "uniqueVisitorsChartData": unique_visitor_chart
        }
    }

def _get_page_log_data_logic(cursor, where_list, params_dict):
    query = f"""
        SELECT 
            JSON_VALUE(DATA, '$.page_url'),
            JSON_VALUE(DATA, '$.referrer')
        FROM ANALYTICS_EVENTS_LOGS
        WHERE {" AND ".join(where_list)}
    """
    cursor.execute(query, params_dict)
    rows = cursor.fetchall()
    
    from collections import defaultdict
    grouped = defaultdict(lambda: {"count": 0, "referrers": []})
    for r in rows:
        page_url = r[0]
        referrer = r[1]
        if not page_url:
            continue
        grouped[page_url]["count"] += 1
        if referrer is not None:
            grouped[page_url]["referrers"].append(referrer)
            
    results = []
    for page_url, data in grouped.items():
        results.append({
            "page_url": page_url,
            "count": data["count"],
            "referrers": data["referrers"]
        })
    return results

def _get_country_log_data_logic(cursor, where_list, params_dict):
    query = f"""
        SELECT 
            NVL(JSON_VALUE(DATA, '$.host_data.address.country'), 'Unknown') AS fullCountry,
            NVL(JSON_VALUE(DATA, '$.host_data.address.countryCode'), 'Unknown') AS country,
            COUNT(DISTINCT JSON_VALUE(DATA, '$.device_id')) AS value
        FROM ANALYTICS_EVENTS_LOGS
        WHERE {" AND ".join(where_list)}
        GROUP BY 
            NVL(JSON_VALUE(DATA, '$.host_data.address.country'), 'Unknown'),
            NVL(JSON_VALUE(DATA, '$.host_data.address.countryCode'), 'Unknown')
    """
    cursor.execute(query, params_dict)
    rows = cursor.fetchall()
    results = []
    for r in rows:
        results.append({
            "fullCountry": r[0],
            "country": r[1],
            "value": r[2]
        })
    return results

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getDashboardData(request, cursor):
    """
    Returns dashboard counts and chart data.
    Refactored for Java parity.
    """
    serializer = AnalyticsDateFilterSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    website_id = serializer.validated_data['websiteId']
    date_filter = serializer.validated_data['dateFilterType']
    start_date = serializer.validated_data.get('startDate')
    end_date = serializer.validated_data.get('endDate')
    domain_filter = serializer.validated_data.get('domainFilter', 'All')
    country_filter = serializer.validated_data.get('countryFilter', 'All')
    user_filter = serializer.validated_data.get('userFilter', 'All')
    
    from_ts, to_ts = get_start_and_end_date(date_filter, start_date, end_date)
    
    where_list = [
        "JSON_VALUE(DATA, '$.website_id') = :website_id",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts"
    ]
    params_dict = {
        "website_id": website_id,
        "from_ts": from_ts,
        "to_ts": to_ts
    }
    
    if domain_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.domain') = :domain_filter")
        params_dict["domain_filter"] = domain_filter
        
    if country_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.host_data.address.country') = :country_filter")
        params_dict["country_filter"] = country_filter
        
    if user_filter != "All":
        if user_filter == "Unknown":
            where_list.append("JSON_VALUE(DATA, '$.user_id') = 'unknown'")
        else:
            where_list.append("(JSON_VALUE(DATA, '$.user_id') IS NOT NULL AND JSON_VALUE(DATA, '$.user_id') != 'unknown')")
            
    active_users = _get_active_users_logic(
        cursor, website_id, from_ts, to_ts, date_filter, start_date, end_date, where_list, params_dict
    )
    
    return api_response(200, "Fetched successfully", {
        "cardData": active_users["cardData"],
        "chartData": active_users["chartData"],
        "countryData": _get_country_log_data_logic(cursor, where_list, params_dict),
        "pageData": _get_page_log_data_logic(cursor, where_list, params_dict)
    })

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getMinuteActiveUsers(request, cursor):
    """
    Refactored to match Java Implementation parity.
    Returns active users count and breakdown by country, state, city, and os.
    """
    serializer = AnalyticsDateFilterSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    website_id = serializer.validated_data.get('websiteId')
    timestamp = serializer.validated_data.get('timeStamp')
    call_count = serializer.validated_data.get('callCount')
    
    if not timestamp:
        timestamp = int(datetime.datetime.now().timestamp() * 1000)
    
    # Mirror Java: Get count for past 1 minute
    active_users_data = get_minute_past_data(cursor, website_id, timestamp, 1)
    
    # Mirror Java: Get data for past 'call_count' minutes for breakdown
    active_users_past_data = get_minute_past_data(cursor, website_id, timestamp, call_count)
    
    country_map = {}
    state_map = {}
    city_map = {}
    os_map = {}
    
    for user_data in active_users_past_data:
        country = user_data.get("country") or "Unknown"
        state = user_data.get("state") or "Unknown"
        city = user_data.get("city") or "Unknown"
        os = user_data.get("os") or "Unknown"
        
        country_map[country] = country_map.get(country, 0) + 1
        state_map[state] = state_map.get(state, 0) + 1
        city_map[city] = city_map.get(city, 0) + 1
        os_map[os] = os_map.get(os, 0) + 1
        
    res_body = {
        "activeUsersCount": len(active_users_data),
        "activeUsersData": {
            "country": country_map,
            "state": state_map,
            "city": city_map,
            "os": os_map
        }
    }
    
    return api_response(200, "Fetched successfully", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getPageLogData(request, cursor):
    """
    Returns page view counts and referrers. Refactored for parity.
    """
    serializer = AnalyticsDateFilterSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    website_id = serializer.validated_data['websiteId']
    date_filter = serializer.validated_data['dateFilterType']
    start_date = serializer.validated_data.get('startDate')
    end_date = serializer.validated_data.get('endDate')
    domain_filter = serializer.validated_data.get('domainFilter', 'All')
    country_filter = serializer.validated_data.get('countryFilter', 'All')
    user_filter = serializer.validated_data.get('userFilter', 'All')
    
    from_ts, to_ts = get_start_and_end_date(date_filter, start_date, end_date)
    
    where_list = [
        "JSON_VALUE(DATA, '$.website_id') = :website_id",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts"
    ]
    params_dict = {
        "website_id": website_id,
        "from_ts": from_ts,
        "to_ts": to_ts
    }
    if domain_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.domain') = :domain_filter")
        params_dict["domain_filter"] = domain_filter
    if country_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.host_data.address.country') = :country_filter")
        params_dict["country_filter"] = country_filter
    if user_filter != "All":
        if user_filter == "Unknown":
            where_list.append("JSON_VALUE(DATA, '$.user_id') = 'unknown'")
        else:
            where_list.append("(JSON_VALUE(DATA, '$.user_id') IS NOT NULL AND JSON_VALUE(DATA, '$.user_id') != 'unknown')")
        
    return api_response(200, "Fetched successfully", {"sessionData": {"data": _get_page_log_data_logic(cursor, where_list, params_dict)}})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getCountryLogData(request, cursor):
    """
    Returns country-wise unique visitor counts. Refactored for parity.
    """
    serializer = AnalyticsDateFilterSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    website_id = serializer.validated_data['websiteId']
    date_filter = serializer.validated_data['dateFilterType']
    start_date = serializer.validated_data.get('startDate')
    end_date = serializer.validated_data.get('endDate')
    domain_filter = serializer.validated_data.get('domainFilter', 'All')
    country_filter = serializer.validated_data.get('countryFilter', 'All')
    user_filter = serializer.validated_data.get('userFilter', 'All')
    
    from_ts, to_ts = get_start_and_end_date(date_filter, start_date, end_date)
    
    where_list = [
        "JSON_VALUE(DATA, '$.website_id') = :website_id",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts",
        "JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts"
    ]
    params_dict = {
        "website_id": website_id,
        "from_ts": from_ts,
        "to_ts": to_ts
    }
    if domain_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.domain') = :domain_filter")
        params_dict["domain_filter"] = domain_filter
    if country_filter != "All":
        where_list.append("JSON_VALUE(DATA, '$.host_data.address.country') = :country_filter")
        params_dict["country_filter"] = country_filter
    if user_filter != "All":
        if user_filter == "Unknown":
            where_list.append("JSON_VALUE(DATA, '$.user_id') = 'unknown'")
        else:
            where_list.append("(JSON_VALUE(DATA, '$.user_id') IS NOT NULL AND JSON_VALUE(DATA, '$.user_id') != 'unknown')")
        
    return api_response(200, "Fetched successfully", {"sessionData": {"data": _get_country_log_data_logic(cursor, where_list, params_dict)}})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getSessionPageLogData(request, cursor):
    """
    Returns detailed logs for a specific aggregation (device, user, or campaign).
    """
    serializer = AnalyticsLogDataSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    target_id = serializer.validated_data['id']
    website_id = serializer.validated_data['websiteId']
    log_data_by = serializer.validated_data['logDataBy'] # DEVICE, USER, CAMPAIGN
    date_filter = serializer.validated_data['dateFilterType']
    start_date = serializer.validated_data.get('startDate')
    end_date = serializer.validated_data.get('endDate')
    
    from_ts, to_ts = get_start_and_end_date(date_filter, start_date, end_date)
    
    field_map = {"DEVICE": "device_id", "USER": "user_id", "CAMPAIGN": "campaign_id"}
    match_field = field_map.get(log_data_by)
    
    # Step 1: Find unique sessions for this target_id
    query_sessions = f"""
        SELECT 
            JSON_VALUE(DATA, '$.session_id') AS session_id,
            MIN(JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER)) AS firstTimestamp
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.{match_field}') = :target_id
          AND JSON_VALUE(DATA, '$.website_id') = :website_id
          AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) >= :from_ts
          AND JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) < :to_ts
        GROUP BY JSON_VALUE(DATA, '$.session_id')
        ORDER BY firstTimestamp DESC
    """
    cursor.execute(query_sessions, {
        "target_id": target_id,
        "website_id": website_id,
        "from_ts": from_ts,
        "to_ts": to_ts
    })
    sessions = [{"_id": r[0], "firstTimestamp": r[1]} for r in cursor.fetchall() if r[0]]
    
    output = []
    for s in sessions:
        session_id = s["_id"]
        
        # Step 2: Get device/host info for this session
        query_info = """
            SELECT 
                JSON_QUERY(DATA, '$.device_info'),
                JSON_QUERY(DATA, '$.host_data')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.session_id') = :session_id
              AND ROWNUM = 1
        """
        cursor.execute(query_info, {"session_id": session_id})
        info_row = cursor.fetchone()
        
        info = {}
        if info_row:
            device_info_str = info_row[0]
            host_data_str = info_row[1]
            if hasattr(device_info_str, 'read'):
                device_info_str = device_info_str.read()
            if hasattr(host_data_str, 'read'):
                host_data_str = host_data_str.read()
                
            info = {
                "device_info": json.loads(device_info_str) if device_info_str else {},
                "host_data": json.loads(host_data_str) if host_data_str else {}
            }
        
        # Step 3: Get page logs for this session
        query_events = """
            SELECT 
                JSON_VALUE(DATA, '$.page_view_id'),
                JSON_VALUE(DATA, '$.referrer'),
                JSON_QUERY(DATA, '$.log')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.session_id') = :session_id
            ORDER BY JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) ASC
        """
        cursor.execute(query_events, {"session_id": session_id})
        events = cursor.fetchall()
        
        page_logs = []
        for e in events:
            page_view_id = e[0]
            referrer = e[1]
            log_str = e[2]
            if hasattr(log_str, 'read'):
                log_str = log_str.read()
            
            logs = json.loads(log_str) if log_str else []
            if not logs: continue
            logs.sort(key=lambda x: x.get("timestamp", 0))
            duration = logs[-1].get("timestamp", 0) - logs[0].get("timestamp", 0) + 2000
            page_logs.append({
                "pageViewId": page_view_id,
                "pageUrl": logs[0].get("page_url"),
                "pageTitle": logs[0].get("page_title"),
                "duration": duration,
                "referrer": referrer
            })
        
        output.append({
            "sessionId": session_id,
            "timestamp": s["firstTimestamp"],
            "pageLogs": page_logs,
            "deviceHostData": info
        })
        
    return api_response(200, "Fetched successfully", {"sessionData": output})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getEmailCampaignOpenMemberLink(request, cursor):
    """
    Returns unique links opened by a user in an email campaign.
    """
    serializer = AnalyticsEmailCampaignOpenMemberLinkSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    email_id = str(serializer.validated_data['emailId']) # This is decoded from doubly base64 encoded in Java service
    camp_id = serializer.validated_data['campId']
    
    query = """
        SELECT JSON_QUERY(DATA, '$.log')
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.session_id') IN (
            SELECT DISTINCT JSON_VALUE(DATA, '$.session_id')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
              AND JSON_VALUE(DATA, '$.user_id') = :email_id
        )
    """
    cursor.execute(query, {"camp_id": camp_id, "email_id": email_id})
    rows = cursor.fetchall()
    
    links = []
    for row in rows:
        log_str = row[0]
        if hasattr(log_str, 'read'):
            log_str = log_str.read()
        logs = json.loads(log_str) if log_str else []
        for l in logs:
            if isinstance(l, dict) and l.get("page_url"):
                links.append(l.get("page_url"))
                
    return api_response(200, "Fetched successfully", {"links": sorted(list(set(links)))})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getEmailCampaignOpenMemberLinkCSV(request, cursor):
    """
    Returns data for CSV exports of email campaign link opens.
    """
    serializer = AnalyticsEmailCampaignOpenMemberLinkSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    camp_id = serializer.validated_data['campId']
    
    # Step 1: Get unique users for campaign
    query_users = """
        SELECT DISTINCT JSON_VALUE(DATA, '$.user_id')
        FROM ANALYTICS_EVENTS_LOGS
        WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
          AND JSON_VALUE(DATA, '$.user_id') IS NOT NULL
          AND JSON_VALUE(DATA, '$.user_id') != 'unknown'
    """
    cursor.execute(query_users, {"camp_id": camp_id})
    user_ids = [row[0] for row in cursor.fetchall() if row[0]]
    
    output = []
    
    for uid_orig in user_ids:
        # Java: Double Base64 decode to get int emailId
        try:
            decoded = base64.b64decode(base64.b64decode(uid_orig)).decode('utf-8')
            internal_email_id = int(decoded)
        except:
            continue
            
        # Links
        query_links = """
            SELECT JSON_QUERY(DATA, '$.log')
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.session_id') IN (
                SELECT DISTINCT JSON_VALUE(DATA, '$.session_id')
                FROM ANALYTICS_EVENTS_LOGS
                WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
                  AND JSON_VALUE(DATA, '$.user_id') = :uid_orig
            )
        """
        cursor.execute(query_links, {"camp_id": camp_id, "uid_orig": uid_orig})
        rows = cursor.fetchall()
        all_links = set()
        for row in rows:
            log_str = row[0]
            if hasattr(log_str, 'read'):
                log_str = log_str.read()
            logs = json.loads(log_str) if log_str else []
            for l in logs:
                if isinstance(l, dict) and l.get("page_url"):
                    all_links.add(l.get("page_url"))
        
        # User Data from SQL
        user_data = {}
        try:
            user = Userlist.objects.get(emailId=internal_email_id)
            user_data = {
                "firstName": user.firstName, "lastName": user.lastName, "fullName": user.fullName,
                "email": user.email if user.email else "",
                "phoneNumber": user.phoneNumber, "phone": user.phone, "usDefaultLanguage": user.usDefaultLanguage,
                "streetAddress1": user.streetAddress1, "streetAddress2": user.streetAddress2,
                "city": user.city, "stateProvRegion": user.stateProvRegion, "zipPostalCode": user.zipPostalCode,
                "country": user.country,
                "birthday": user.birthday if user.birthday else "",
                "gender": user.gender, "emailDomain": user.emailDomain,
                "dateRegistered": user.dateRegistered.strftime("%m-%d-%Y %H:%M:%S") if user.dateRegistered else "",
                "status": user.status, "smsStatus": user.smsStatus
            }
        except Userlist.DoesNotExist:
            pass
            
        # Mirroing Java: totalOpen is the count of events for this campaign and user
        query_count = """
            SELECT COUNT(*)
            FROM ANALYTICS_EVENTS_LOGS
            WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
              AND JSON_VALUE(DATA, '$.user_id') = :uid_orig
        """
        cursor.execute(query_count, {"camp_id": camp_id, "uid_orig": uid_orig})
        res_count = cursor.fetchone()
        total_open = res_count[0] if res_count else 0
        
        user_data["totalOpen"] = total_open

        output.append({
            "emailId": uid_orig,
            "links": list(all_links),
            "userData": user_data
        })
        
    res_body = {
        "openMemberLinks": output
    }
    
    if user_ids:
        # Match Java: Headers are at the top level of resBody
        res_body["contactHeader"] = ["First Name", "Last Name", "Full Name", "Email", "Mobile", "Phone", "Language", "Street Address1", "Street Address2", "City", "State", "Zip Code", "Country", "Birthday", "Gender", "Email Domain", "Registered Date", "Status", "SMS Status", "Total Open"]
        res_body["contactHeaderKey"] = ["firstName", "lastName", "fullName", "email", "phoneNumber", "phone", "usDefaultLanguage", "streetAddress1", "streetAddress2", "city", "stateProvRegion", "zipPostalCode", "country", "birthday", "gender", "emailDomain", "dateRegistered", "status", "smsStatus", "totalOpen"]

    return api_response(200, "Fetched successfully", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def grabAnalyticsCsvData(request):
    """
    Creates a record to trigger CSV generation for analytics data.
    """
    final_member_id = get_final_tenant_id(request=request)
    campaignId = request.query_params.get('campaignId')
    
    try:
        csv_record = AnalyticsCsv.objects.create(
            member_id=get_client_id_by_tenant_id(final_member_id),
            campaign_id=campaignId,
            is_started=0,
            is_processed=0,
            percent_complete=0
        )
        
        return api_response(200, "CSV Data Grab request saved successfully", {"id": csv_record.id})
    except Exception as e:
        logger.error(f"grabAnalyticsCsvData error: {str(e)}")
        return api_response(500, str(e), {})

devConn = None
prodConn = None

def getDevConnection():
    global devConn
    if devConn is not None:
        try:
            devConn.ping()
        except Exception:
            devConn = None
    if devConn is None:
        db_config = dev_settings.DATABASES['default']
        devConn = oracledb.connect(
            user=db_config['USER'],
            password=db_config['PASSWORD'],
            dsn=db_config['NAME']
        )
    return devConn

def getProdConnection():
    global prodConn
    if prodConn is not None:
        try:
            prodConn.ping()
        except Exception:
            prodConn = None
    if prodConn is None:
        db_config = prod_settings.DATABASES['default']
        prodConn = oracledb.connect(
            user=db_config['USER'],
            password=db_config['PASSWORD'],
            dsn=db_config['NAME']
        )
    return prodConn

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def processMessage(request):
    """
    Python port of Main.processMessage from Java.
    Decodes the incoming payload (if wrapped in base64 like OCI Stream Message, or reads raw JSON).
    """
    try:
        payload = request.data
        
        # Support both direct JSON body and message format (base64 encoded String value)
        if isinstance(payload, dict) and "value" in payload:
            val = payload["value"]
            decoded_bytes = base64.b64decode(val)
            decoded_str = decoded_bytes.decode('utf-8')
            json_data = json.loads(decoded_str)
        elif isinstance(payload, str):
            try:
                decoded_bytes = base64.b64decode(payload)
                decoded_str = decoded_bytes.decode('utf-8')
                json_data = json.loads(decoded_str)
            except Exception:
                json_data = json.loads(payload)
        else:
            json_data = payload

        if not isinstance(json_data, dict):
            return api_response(400, "Request data must be a JSON object", {})

        serverType = json_data.get("server_type")
        deviceId = json_data.get("device_id")
        sessionId = json_data.get("session_id")
        pageViewId = json_data.get("page_view_id")

        conn = None
        if serverType == "prod":
            logger.info("Using production Oracle database.")
            conn = getProdConnection()
        else:
            logger.info("Using development Oracle database.")
            conn = getDevConnection()

        with conn.cursor() as cursor:
            # Query the database
            query = (
                "SELECT DATA FROM ANALYTICS_EVENTS_LOGS "
                "WHERE JSON_VALUE(DATA, '$.device_id') = :1 "
                "AND JSON_VALUE(DATA, '$.session_id') = :2 "
                "AND JSON_VALUE(DATA, '$.page_view_id') = :3 "
                "FETCH FIRST 1 ROWS ONLY"
            )
            cursor.execute(query, [deviceId, sessionId, pageViewId])
            row = cursor.fetchone()

            if not row:
                insert_query = "INSERT INTO ANALYTICS_EVENTS_LOGS (DATA) VALUES (:1)"
                cursor.execute(insert_query, [json.dumps(json_data)])
                conn.commit()
                logger.info("Inserted document into Oracle DB")
            else:
                existing_data = row[0]
                if hasattr(existing_data, 'read'):
                    existing_data = existing_data.read()
                
                existing_json = json.loads(existing_data) if isinstance(existing_data, str) else existing_data

                existing_logs = existing_json.get("log")
                if not isinstance(existing_logs, list):
                    existing_logs = []
                    existing_json["log"] = existing_logs

                new_logs = json_data.get("log")
                if isinstance(new_logs, list):
                    for log in new_logs:
                        existing_logs.append(log)

                update_query = (
                    "UPDATE ANALYTICS_EVENTS_LOGS SET DATA = :1 "
                    "WHERE JSON_VALUE(DATA, '$.device_id') = :2 "
                    "AND JSON_VALUE(DATA, '$.session_id') = :3 "
                    "AND JSON_VALUE(DATA, '$.page_view_id') = :4"
                )
                cursor.execute(update_query, [json.dumps(existing_json), deviceId, sessionId, pageViewId])
                conn.commit()
                logger.info("Updated existing document with additional log entries in Oracle DB.")

        return api_response(200, "Processed successfully", {})
    except Exception as e:
        logger.error(f"Error in processMessage: {str(e)}")
        return api_response(500, f"Database error: {str(e)}", {})
