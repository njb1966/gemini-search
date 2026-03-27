FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir aiosqlite

COPY crawl.py .

CMD ["python", "crawl.py"]
