import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('d:/Final Version/admin_advanced_analytics_endpoints.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'from schemas.chart_dto import LayerMetricsResponse',
    'from schemas.chart_dto import LayerMetricsResponse\nfrom cache_service import dashboard_cache'
)

# Use dict type hint fallback for FastAPI responses
content = content.replace(
    ') -> LayerMetricsResponse:',
    ') -> dict:'
)
content = content.replace(
    'response_model=LayerMetricsResponse,',
    'response_model=dict,'
)

content = content.replace(
    'return AnalyticsGapService(db).get_network_metrics(locale)',
    '''cache_key = f"adv_analytics:network:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_network_metrics(locale).model_dump(mode="json"),
        ttl_seconds=1800
    )'''
)

content = content.replace(
    'return AnalyticsGapService(db).get_governorate_metrics(gov_name, locale)',
    '''cache_key = f"adv_analytics:governorate:{gov_name}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_governorate_metrics(gov_name, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )'''
)

content = content.replace(
    'return AnalyticsGapService(db).get_kg_metrics(kg_id, locale)',
    '''cache_key = f"adv_analytics:kg:{kg_id}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_kg_metrics(kg_id, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )'''
)

content = content.replace(
    'return AnalyticsGapService(db).get_child_metrics(child_id, locale)',
    '''cache_key = f"adv_analytics:child:{child_id}:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_child_metrics(child_id, locale).model_dump(mode="json"),
        ttl_seconds=1800
    )'''
)

content = content.replace(
    'return AnalyticsGapService(db).get_predictive_metrics(locale)',
    '''cache_key = f"adv_analytics:predictive:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_predictive_metrics(locale).model_dump(mode="json"),
        ttl_seconds=3600
    )'''
)

content = content.replace(
    'return AnalyticsGapService(db).get_governance_metrics(locale)',
    '''cache_key = f"adv_analytics:governance:{locale}"
    return dashboard_cache.get_or_set(
        cache_key,
        lambda: AnalyticsGapService(db).get_governance_metrics(locale).model_dump(mode="json"),
        ttl_seconds=3600
    )'''
)

with open('d:/Final Version/admin_advanced_analytics_endpoints.py', 'w', encoding='utf-8') as f:
    f.write(content)
