# Image with Python + Chromium already installed (needed to make PDFs)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DUKAAN_DATA_DIR=/data PORT=8080
# One worker so the database and approvals stay in one place; threads handle many chats.
CMD gunicorn run_app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 180
