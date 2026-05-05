# Playwright 공식 베이스 이미지 — chromium + 모든 시스템 의존성 미리 설치됨.
# Ubuntu 22.04 의 apt --with-deps 충돌 회피.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# asyncpg 빌드용 libpq-dev + 한글 폰트
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# chromium 은 베이스 이미지에 이미 포함 — playwright install 불필요

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
