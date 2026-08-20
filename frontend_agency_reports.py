"""Frontend pages for Admin Official Agency Reports."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import models
from dependencies import get_current_user_or_redirect, Permission, has_permission
from frontend import templates
from utils.time_utils import today_amman as _today

router = APIRouter(include_in_schema=False)


def _ensure_admin(current_user: models.User):
    if not has_permission(current_user, Permission.ADMIN_PANEL):
        return RedirectResponse(url="/dashboard", status_code=302)
    return None


@router.get("/admin/agency-reports", response_class=HTMLResponse)
async def admin_agency_reports_index(request: Request, current_user: models.User = Depends(get_current_user_or_redirect)):
    redirect = _ensure_admin(current_user)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="admin/agency_reports/index.html",
        context={"current_user": current_user, "today": _today()},
    )


@router.get("/admin/agency-reports/{agency_code}", response_class=HTMLResponse)
async def admin_agency_reports_agency(agency_code: str, request: Request, current_user: models.User = Depends(get_current_user_or_redirect)):
    redirect = _ensure_admin(current_user)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="admin/agency_reports/agency.html",
        context={"current_user": current_user, "today": _today(), "agency_code": agency_code},
    )


@router.get("/admin/agency-reports/{agency_code}/{report_code}", response_class=HTMLResponse)
async def admin_agency_reports_report(agency_code: str, report_code: str, request: Request, current_user: models.User = Depends(get_current_user_or_redirect)):
    redirect = _ensure_admin(current_user)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="admin/agency_reports/report.html",
        context={"current_user": current_user, "today": _today(), "agency_code": agency_code, "report_code": report_code},
    )
