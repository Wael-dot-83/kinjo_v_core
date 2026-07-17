from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class AdminGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Placeholder admin check – replace with real auth logic
        if not request.headers.get("x-admin", "false").lower() == "true":
            return Response("Forbidden: admin access required", status_code=403)
        response = await call_next(request)
        return response
