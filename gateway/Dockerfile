FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

USER appuser

EXPOSE 8080

CMD ["gunicorn", "--bind", ":8080", "--workers", "2", "--threads", "8", \
     "--timeout", "0", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
