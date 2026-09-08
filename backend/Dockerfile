FROM eclipse-temurin:21-jre
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data/events /app/reports
COPY target/terminal-agent-runtime-*.jar /app/app.jar
ENV DEVICE_AGENT_EVENT_LOG_DIR=/app/data/events \
    DEVICE_AGENT_SQLITE_PATH=/app/data/harness.db \
    DEVICE_AGENT_PERSISTENCE=sqlite
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=20 --start-period=25s \
  CMD curl -sf http://127.0.0.1:8080/api/v1/meta >/dev/null || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
