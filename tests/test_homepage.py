import re

from main import app
from dependencies import get_current_user_optional
from api.kindergartens import router as kindergartens_router


def test_home_page_renders_200_and_bilingual_contract(client):
    client.cookies.set("kinjo_lang", "en")
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text

    client.cookies.set("kinjo_lang", "ar")
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'lang="ar"' in response.text
    assert 'dir="rtl"' in response.text


def test_home_page_contains_search_form(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'id="kg-search-input"' in response.text
    assert 'id="kg-filter-governorate"' in response.text
    assert 'id="kg-filter-district"' in response.text
    assert 'id="kg-filter-status"' in response.text
    assert 'id="kg-search-btn"' in response.text


def test_home_page_contains_value_cards(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'kinjo-home-value-card' in response.text
    assert 'أولياء الأمور' in response.text
    assert 'المشرفون والمدققون التربويون' in response.text
    assert 'إدارات الحضانات والروضات' in response.text


def test_home_page_contains_app_ecosystem_section(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'KinJo in Your Pocket' in response.text or 'KinJo في جيبك' in response.text
    assert 'Google Play' in response.text
    assert 'App Store' in response.text
    assert 'notifications_active' in response.text or 'analytics' in response.text


def test_home_page_footer_has_updated_heading_and_no_copyright(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert 'الجهات والمؤسسات المستفيدة' in response.text
    assert 'الجهات والمؤسسات الشريكة المعتمدة' not in response.text
    assert '© 2024' not in response.text
    assert 'جميع الحقوق محفوظة' not in response.text


def test_home_page_loads_home_search_js(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert '/static/js/home-search.js' in response.text
