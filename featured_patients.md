# Featured patients — real FHIR data

List the MongoDB patient `_id`s (the patient UUIDs) you want shown as **real data**
on the dashboard, one per `-` bullet below. Each id is bound, top to bottom, to a
dashboard patient slot: the first id becomes patient 1, the second patient 2, and so
on (skipping the live Garmin patient). Those slots show the real name, age, and
medical profile pulled from MongoDB; every other patient stays mock.

Notes:
- The database must be running and populated (`docker compose up`) for this to take
  effect, and the backend reads this file at startup — restart it after editing.
- Ids not found in Mongo are skipped (that slot stays mock). Lines starting with `#`
  and anything that isn't a UUID are ignored.
- Find ids with:
  `docker exec careloop-mongo mongosh careloop --quiet --eval 'db.fhir_patients.find({}, {_id:1}).limit(10).forEach(d => print(d._id))'`

- 0ae08855-8e6c-5308-3ab5-da0080b36425
- 01d78eb5-7f50-45e9-f524-921196a3dffe
