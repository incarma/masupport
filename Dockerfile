# django_ma/Dockerfile

# Django용 베이스 이미지
FROM python:3.10

# LibreOffice + 한글 폰트 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    fonts-noto-cjk \
    fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 프로젝트 복사
COPY . .

# Collect static files
RUN APP_ENV=prod python manage.py collectstatic --noinput

# 환경 변수 (gunicorn 실행용)
ENV DJANGO_SETTINGS_MODULE=web_ma.settings
ENV PYTHONUNBUFFERED=1

# 기본 실행 명령
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]