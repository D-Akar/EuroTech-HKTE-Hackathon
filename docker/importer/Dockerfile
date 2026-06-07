# One-shot FHIR importer for CareLoop.
#
# Runs backend/scripts/import_fhir_to_mongo.py against the mongo service once the
# database is healthy, then exits. The script upserts by _id, so re-running on
# every `docker compose up` is idempotent - no duplicates, latest file wins.
FROM python:3.12-slim

# pymongo is the only dependency the import script needs (version pinned to match
# backend/requirements.txt).
RUN pip install --no-cache-dir "pymongo>=4.6"

WORKDIR /app

# The script and data are bind-mounted at runtime (see docker-compose.yml) so the
# image stays generic and picks up new patient records without a rebuild.
CMD ["python", "scripts/import_fhir_to_mongo.py", \
     "--src", "/app/data", \
     "--uri", "mongodb://mongo:27017"]
