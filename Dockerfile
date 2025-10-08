FROM python:3.9-slim

WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
ENV PYTHONUNBUFFERED=1
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Run FastAPI with uvicorn
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]
