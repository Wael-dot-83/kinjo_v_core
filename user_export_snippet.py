
@router.get("/users/export")
def export_users(
    format: str = Query("csv", regex="^(csv)$"),
    role: Optional[models.UserRole] = None,
    status_filter: Optional[models.UserStatus] = None, # Renamed to avoid conflict
    kindergarten_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export users list (Admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    query = db.query(models.User)
    
    if kindergarten_id:
        query = query.filter(models.User.kindergarten_id == kindergarten_id)
        
    query = query.filter(models.User.role != models.UserRole.ADMIN)

    if role:
        query = query.filter(models.User.role == role)
    if status_filter:
        query = query.filter(models.User.status == status_filter)

    users = query.all()

    import csv
    import io
    from fastapi.responses import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Email", "Role", "Status", "Kindergarten ID", "Created At"])

    for u in users:
        writer.writerow([
            u.id,
            u.username,
            u.email,
            u.role.value,
            u.status.value,
            u.kindergarten_id or "N/A",
            u.created_at
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users_export_{date.today()}.csv"}
    )
