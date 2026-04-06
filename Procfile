# Heroku Procfile for G-Track Backend
# This file tells Heroku how to run the application

web: gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers 2 --timeout 60 --bind 0.0.0.0:\$PORT --access-logfile - --error-logfile -

# Release command (runs once during deployment)
release: python -c "from database import init_db; import asyncio; asyncio.run(init_db())"

# Optional: Worker for background tasks (if needed later)
# worker: celery -A tasks worker --loglevel=info
