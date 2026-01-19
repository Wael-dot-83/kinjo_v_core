"""
Test that analytics cache tables and indexes exist in the DB schema
"""
import pytest
from sqlalchemy import inspect
import models

def test_advanced_analytics_cache_table_exists(test_db):
    inspector = inspect(test_db.bind)
    tables = inspector.get_table_names()
    assert 'advanced_analytics_cache' in tables
    assert 'analytics_dimension_cache' in tables

def test_advanced_analytics_cache_indexes(test_db):
    inspector = inspect(test_db.bind)
    indexes = inspector.get_indexes('advanced_analytics_cache')
    index_names = {ix['name'] for ix in indexes}
    # These are the expected indexes from models.py
    assert 'ix_adv_analytics_cache_dim' in index_names
    assert 'ix_adv_analytics_cache_period' in index_names
    assert 'ix_adv_analytics_cache_lookup' in index_names

def test_analytics_dimension_cache_indexes(test_db):
    inspector = inspect(test_db.bind)
    indexes = inspector.get_indexes('analytics_dimension_cache')
    index_names = {ix['name'] for ix in indexes}
    assert 'ix_analytics_cache_dimension' in index_names
    assert 'ix_analytics_cache_period' in index_names
    assert 'ix_analytics_cache_lookup' in index_names
