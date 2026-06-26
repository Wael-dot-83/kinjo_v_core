import re

path = r'D:\Final Version\static\css\dashboard-pro.css'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add premium modern UI styles at the end
modern_styles = """
/* =========================================================================
   Modern UI / UX Overhaul (Glassmorphism & High Readability)
   ========================================================================= */

/* Main Panel Modernization */
.admin-page-header {
    background: linear-gradient(135deg, rgba(79, 70, 229, 0.9), rgba(14, 165, 233, 0.9));
    color: #ffffff;
    padding: 2rem;
    border-radius: 16px;
    margin-bottom: 2rem;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
    -webkit-backdrop-filter: blur(12px);
    backdrop-filter: blur(12px);
}

.admin-page-title {
    font-size: 2rem;
    font-weight: 800;
    margin-bottom: 0.5rem;
    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.admin-page-subtitle {
    font-size: 1.1rem;
    opacity: 0.9;
}

/* Glassmorphism KPI Cards */
.admin-kpi-card {
    background: rgba(255, 255, 255, 0.85) !important;
    -webkit-backdrop-filter: blur(16px);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.4) !important;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05) !important;
    border-radius: 16px !important;
    padding: 1.5rem !important;
    transition: transform 0.3s ease, box-shadow 0.3s ease !important;
}

.admin-kpi-card:hover {
    transform: translateY(-5px) !important;
    box-shadow: 0 12px 25px rgba(0, 0, 0, 0.1) !important;
    background: rgba(255, 255, 255, 0.95) !important;
}

/* Improve Typography & Contrast for Readability */
.admin-kpi-card-value {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
    color: #1e293b !important; /* Slate 800 */
}

.admin-kpi-card-label {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #475569 !important; /* Slate 600 */
    margin-top: 0.5rem;
}

/* Chart Cards Modernization */
.admin-card {
    background: #ffffff;
    border-radius: 16px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
    border: 1px solid rgba(226, 232, 240, 0.8);
    overflow: hidden;
    margin-bottom: 1.5rem;
}

.admin-card-header {
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    padding: 1.25rem 1.5rem;
}

.admin-card-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
}

/* Quick Actions Cards */
.admin-quick-action-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.25rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    transition: all 0.2s ease;
    text-decoration: none;
    color: #1e293b;
    font-weight: 600;
}

.admin-quick-action-card:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    transform: translateX(-4px); /* RTL friendly hover */
}

.admin-quick-action-card-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    background: #e0e7ff;
    color: #4f46e5;
}
"""

if "Modern UI / UX Overhaul" not in content:
    with open(path, 'a', encoding='utf-8') as f:
        f.write("\n" + modern_styles)
    print("Modern UI styles injected into dashboard-pro.css")
else:
    print("Styles already present.")
