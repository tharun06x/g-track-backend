web: gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 120 --bind 0.0.0.0:$PORT
release: python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
