# django_ma/Dockerfile

# Django용 베이스 이미지
FROM python:3.10

# 작업 디렉토리
WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 프로젝트 복사
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# 환경 변수 (gunicorn 실행용)
ENV DJANGO_SETTINGS_MODULE=web_ma.settings
ENV PYTHONUNBUFFERED=1

# 기본 실행 명령 (웹 서버는 docker-compose에서 override) / Render 호환 CMD (쉘 방식)
CMD sh -c "gunicorn web_ma.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT"