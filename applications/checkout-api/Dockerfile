FROM python:3.12-alpine

RUN apk upgrade --no-cache

WORKDIR /app
COPY app.py /app/app.py
RUN addgroup -S sentinel && adduser -S sentinel -G sentinel
USER sentinel
EXPOSE 8080
ENTRYPOINT ["python3", "/app/app.py"]
