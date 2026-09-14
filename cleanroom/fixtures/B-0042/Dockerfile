FROM eclipse-temurin:21-jre-alpine

RUN addgroup -S app && adduser -S app -G app
COPY target/order-service.jar /app/order-service.jar

# VIOLATES ADR-0042: no HEALTHCHECK, so the orchestrator cannot tell running from serving.

# ADR-0041: the process runs unprivileged.
USER app
ENTRYPOINT ["java", "-jar", "/app/order-service.jar"]
