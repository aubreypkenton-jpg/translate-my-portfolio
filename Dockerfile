FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# gunicorn instead of the Flask dev server for anything beyond local testing
RUN pip install --no-cache-dir gunicorn==23.0.0
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "run:app"]
