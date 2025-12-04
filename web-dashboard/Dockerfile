FROM python:3.12-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Copy shared package
COPY ../shared /app/shared

# Copy frontend
COPY ../frontend /app/frontend

EXPOSE 8000

CMD ["python", "main.py"]
