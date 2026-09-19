"""
seo_routes.py — sitemap.xml + robots.txt for MRK Agency.

Self-contained blueprint, same pattern as ai_assistant.py's ai_bp.
Registering this in app.py adds exactly two public, read-only routes
(GET /sitemap.xml, GET /robots.txt). It does not add, remove, or alter
any existing route, table, or piece of application logic.

Only genuinely public, unauthenticated, non-conditional pages are
listed in the sitemap:
  - /                 home()            — no auth, always live
  - /register         register()        — no auth, always live
  - /login             login()          — no auth, always live
  - /contractor-apply contractor_apply() — no auth, always live
  - /services         services_page()   — no auth, always live

Deliberately EXCLUDED (see chat for full reasoning):
  - /portfolio, /portfolio/<id>, /team — public when enabled, but
    gated behind a CEO visibility toggle (site_settings) and return
    404 when off. Since their live/dead state isn't guaranteed at
    any given time, they're left out to avoid the sitemap ever
    pointing at a 404. Safe to add later once confirmed permanently on.
  - Every /ceo/*, /contractor-dashboard, /contractor-login,
    /dashboard, /mrkceokhan7, /files, /api/*, and all POST-only
    action endpoints — private, authenticated, or internal by design.
"""

from flask import Blueprint, Response

seo_bp = Blueprint('seo', __name__)

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://mrkagency.com/</loc>
  </url>
  <url>
    <loc>https://mrkagency.com/register</loc>
  </url>
  <url>
    <loc>https://mrkagency.com/login</loc>
  </url>
  <url>
    <loc>https://mrkagency.com/contractor-apply</loc>
  </url>
  <url>
    <loc>https://mrkagency.com/services</loc>
  </url>
</urlset>
"""

ROBOTS_TXT = """User-agent: *
Allow: /

Sitemap: https://mrkagency.com/sitemap.xml
"""


@seo_bp.route('/sitemap.xml')
def sitemap():
    return Response(SITEMAP_XML, mimetype='application/xml')


@seo_bp.route('/robots.txt')
def robots():
    return Response(ROBOTS_TXT, mimetype='text/plain')
