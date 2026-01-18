from fastapi import FastAPI
from database import init_db
from config import settings
from fastapi.middleware.cors import CORSMiddleware

# Initialize database at module level
init_db()

app = FastAPI(title='Test App')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/api/health')
def health():
    return {'status': 'healthy'}