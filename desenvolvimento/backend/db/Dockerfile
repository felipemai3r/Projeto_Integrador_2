FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/common /app/services/common
COPY db /app/db
RUN pip install /app/services/common
WORKDIR /app/db
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && python -m common.seed"]
