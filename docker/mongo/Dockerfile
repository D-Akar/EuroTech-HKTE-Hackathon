# MongoDB for CareLoop — FHIR patient store (db: careloop, collection: fhir_patients).
#
# This is a thin wrapper over the official image: MongoDB itself needs no build
# step, so we just pin the version and declare the port + a healthcheck. The
# runtime config (port publish, persistent volume) lives in docker-compose.yml.
FROM mongo:7

EXPOSE 27017

# Report unhealthy until the server answers a ping, so `docker compose up --wait`
# and orchestrators only consider the DB ready once it can actually serve queries.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD mongosh --quiet --eval "db.adminCommand('ping').ok" localhost:27017/test || exit 1
