from fastapi import FastAPI
from app.routers.admin_reports import router as admin_reports_router

app = FastAPI(title="KinJo Admin Reports")
app.include_router(admin_reports_router)
