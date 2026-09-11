#!/bin/sh
cd /Users/eduardo/Desktop/featcode/talent/OpenATS/backend-py
. .venv/bin/activate
exec uvicorn app.main:asgi_app --reload --host 0.0.0.0 --port 8081
