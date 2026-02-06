# -----------------------------------------------------------------------------
# Safety & Health
# -----------------------------------------------------------------------------

@router.get("/safety", response_class=HTMLResponse)
async def safety_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="safety/index.html", context={"current_user": current_user})

@router.get("/safety/incidents/new", response_class=HTMLResponse)
async def create_incident_page(request: Request, current_user: User = Depends(get_current_user)):
    # In a real app, we might pass list of children here for the dropdown
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={"current_user": current_user})

