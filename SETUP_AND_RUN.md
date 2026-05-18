# KinJo Platform - Setup and Run Guide

This guide helps you set up and run the KinJo platform on Windows, macOS, or Linux.

## Quick Start (Windows)

### Option 1: Using Batch Scripts (Recommended)

1. **Development Server** (with auto-reload):
   ```cmd
   run_server_dev.bat
   ```
   This script will:
   - Check for Python installation
   - Create a virtual environment if needed
   - Install dependencies automatically
   - Start the server with auto-reload

2. **Background Server**:
   ```cmd
   run_server_bg.bat
   ```
   Runs the server in a background window

### Option 2: Manual Setup

1. **Create and activate virtual environment**:
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```cmd
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```cmd
   copy .env.example .env
   ```
   Edit `.env` and set your `SECRET_KEY` and database URL

4. **Run the server**:
   ```cmd
   .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

## Quick Start (macOS/Linux)

1. **Create and activate virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your `SECRET_KEY` and database URL

4. **Run the server**:
   ```bash
   uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

## Environment Configuration

### Required Settings

Create a `.env` file from `.env.example`:

```env
# Security (REQUIRED)
SECRET_KEY=your-secret-key-here-change-in-production

# Database (choose one)
# PostgreSQL (recommended for production)
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/kinjo_db

# OR SQLite (for development/testing)
DATABASE_URL=sqlite:///./kinjo.db

# Application
ENVIRONMENT=development
TESTING=false
```

### Optional Settings

```env
# Token expiration
ACCESS_TOKEN_EXPIRE_MINUTES=30
ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER=10080  # 7 days for "remember me"

# Redis (for caching)
REDIS_URL=redis://localhost:6379/0

# Localization
DEFAULT_LANGUAGE=ar
# SUPPORTED_LANGUAGES uses default ["ar", "en"] - only override if needed
```

## Accessing the Application

Once the server is running:

- **Frontend**: http://127.0.0.1:8000/
- **API Documentation (Swagger)**: http://127.0.0.1:8000/docs
- **API Documentation (ReDoc)**: http://127.0.0.1:8000/redoc
- **Health Check**: http://127.0.0.1:8000/health
- **KPI Dashboard**: http://127.0.0.1:8000/kpi/dashboard

## Database Setup

### Initialize Database (First Time)

```python
python -c "from database import init_db; init_db()"
```

### Using Alembic Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create new migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Check current migration version
alembic current

# View migration history
alembic history
```

## Running Tests

```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest test_api.py -v

# Run specific test
pytest test_api.py::test_health_check -v
```

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
docker-compose up --build
```

This starts:
- Web service on port 8001 (maps to internal port 8000)
- PostgreSQL database with persistent storage

### Manual Docker Build

```bash
docker build -t kinjo-platform .
docker run -p 8000:8000 -v $(pwd)/data:/app/data kinjo-platform
```

## Production Deployment

### Checklist

1. **Environment Variables**:
   ```env
   ENVIRONMENT=production
   TESTING=false
   SECRET_KEY=<strong-random-key>
   DATABASE_URL=postgresql+psycopg2://...
   ```

2. **Database**:
   - Use PostgreSQL (required for production)
   - Run migrations: `alembic upgrade head`
   - Verify: `alembic current` matches `alembic heads`

3. **Run with Workers**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

4. **Security**:
   - Ensure `TESTING=false` (app will refuse to start if `TESTING=true` in production)
   - Use strong `SECRET_KEY`
   - Configure proper CORS origins
   - Use HTTPS/SSL in production

## Troubleshooting

### "No module named 'fastapi'"

Install dependencies:
```bash
pip install -r requirements.txt
```

### "SECRET_KEY Field required"

Create and configure `.env` file:
```bash
cp .env.example .env
# Edit .env and set SECRET_KEY
```

### "Connection refused" or "Database error"

For PostgreSQL:
- Ensure PostgreSQL is running
- Check `DATABASE_URL` in `.env`
- Verify database exists: `createdb kinjo_db`

For SQLite:
- SQLite creates the file automatically
- Ensure the directory is writable

### Port 8000 already in use

Use a different port:
```bash
uvicorn main:app --host 127.0.0.1 --port 8001
```

Or stop the existing process:
- Windows: Check Task Manager for Python/uvicorn processes
- Linux/macOS: `lsof -ti:8000 | xargs kill -9`

## Development Tips

### Auto-reload

Use `--reload` flag for development:
```bash
uvicorn main:app --reload
```

Changes to Python files will automatically restart the server.

### Debug Mode

Enable in `.env`:
```env
DEBUG=True
```

### API Testing

Use the interactive Swagger UI at http://127.0.0.1:8000/docs to:
- Test endpoints
- View request/response schemas
- Execute API calls with authentication

## Additional Resources

- **Main Documentation**: `README.md`
- **API Reference**: `API_QUICK_REFERENCE.md`
- **Manual Testing Guide**: `MANUAL_TESTING_GUIDE.md`
- **Troubleshooting**: `TROUBLESHOOTING.md`
- **SRS Document**: `KinJo_IEEE_SRS_and_Agile_Backlog_v1.2_Audit_Enhanced.docx`

## Support

For issues or questions:
1. Check `TROUBLESHOOTING.md`
2. Review the SRS document
3. Check GitHub issues
4. Contact the development team
