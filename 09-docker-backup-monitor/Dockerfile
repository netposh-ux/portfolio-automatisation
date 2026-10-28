# pg_dump must be at least as new as the server: start from the same Postgres image.
FROM postgres:16-alpine
RUN apk add --no-cache python3 bash tzdata
WORKDIR /app
COPY backupctl.py scheduler.sh ./
RUN adduser -D -u 1000 backup && mkdir -p /backups /status && chown backup /backups /status
USER backup
HEALTHCHECK --interval=5m --timeout=30s CMD python3 /app/backupctl.py status --dest /backups --max-age-hours 26 >/dev/null
CMD ["/app/scheduler.sh"]
