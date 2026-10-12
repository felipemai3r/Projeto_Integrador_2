FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/common /app/services/common
COPY services/ingestor /app/services/ingestor
RUN pip install /app/services/common /app/services/ingestor
CMD ["python", "-m", "ingestor.main"]
