FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/common /app/services/common
COPY services/modelo /app/services/modelo
COPY services/api /app/services/api
RUN pip install /app/services/common /app/services/modelo /app/services/api
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
