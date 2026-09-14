FROM eclipse-temurin:21-jre-alpine

RUN addgroup -S app && adduser -S app -G app
COPY target/order-service.jar /app/order-service.jar

# ADR-0042: the image declares how to tell running from serving.
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -q -O- http://localhost:8080/actuator/health || exit 1

# ADR-0041: the process runs unprivileged.
USER app
ENTRYPOINT ["java", "-jar", "/app/order-service.jar"]
