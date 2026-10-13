FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/common /app/services/common
COPY services/modelo /app/services/modelo
RUN pip install /app/services/common /app/services/modelo
CMD ["python", "-m", "modelo.correlacao", "--help"]
