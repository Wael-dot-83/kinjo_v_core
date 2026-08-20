"""Query repositories (ADMIN-002).

One module per aggregate root. Repositories own the SQLAlchemy queries so
that routers and services never build them inline.
"""
