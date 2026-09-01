FROM python:3.12-alpine@sha256:1887c114801a8c82a4ec01daa52cfe7fc3f63573640e2247320289807ac1c3bb

RUN apk upgrade --no-cache

WORKDIR /app
COPY app.py /app/app.py
RUN addgroup -S sentinel && adduser -S sentinel -G sentinel
USER sentinel
EXPOSE 8080
ENTRYPOINT ["python3", "/app/app.py"]
