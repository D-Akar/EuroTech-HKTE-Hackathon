# Featured patients - real FHIR data

List the MongoDB patient `_id`s (the patient UUIDs) you want shown as **real data**
on the dashboard, one per `-` bullet below. Each id is bound, top to bottom, to a
dashboard patient slot: the first id becomes patient 1, the second patient 2, and so
on (skipping the live Garmin patient). Those slots show the real name, age, and
medical profile pulled from MongoDB; every other patient stays mock.

Notes:
- The database must be running and populated (`docker compose up`) for this to take
  effect, and the backend reads this file at startup - restart it after editing.
- Ids not found in Mongo are skipped (that slot stays mock). Lines starting with `#`
  and anything that isn't a UUID are ignored.
- There are 30 dashboard slots; one is the live Garmin patient (skipped here), so the
  29 remaining slots are all bound from the list below - no patient stays mock.
- Find ids with:
  `docker exec careloop-mongo mongosh careloop --quiet --eval 'db.fhir_patients.find({}, {_id:1}).limit(10).forEach(d => print(d._id))'`

- d8e3a701-d108-74ff-2ce3-156537276a14
- 4ca722b8-631c-fc54-1145-8d2c4d66809f
- 9acc871f-b577-5530-b8ad-fa95b58cea25
- bf113937-f532-94bb-66e1-9c7111f68207
- 6a6a1b30-9966-bd68-e732-b7ce2c0b6ade
- 34b1b3b3-73ce-1bc2-b26e-dce20c4f6cbc
- d00d8a67-a23f-6fda-d97d-2a6391685500
- 1f629a95-5a68-0aec-b3ce-32d2beee7da9
- 407ef75b-0a9c-ec23-60e5-c90ba86e27af
- 2c098b38-279d-88b3-d553-e87b56eb1b04
- c99968ac-6782-9ae2-aab2-98277ae5a8e8
- 7d28d76a-9ac8-67b4-3c88-0a75be3d0851
- 78a50f0f-cce6-17f0-cc9f-bd605ce78292
- a25e9984-9c96-bcd4-07f9-9f763e077366
- da97668c-bf70-6c4d-3157-24aae70ed237
- ff0e4d0e-6181-e36e-d817-64dbcaecb5d0
- 9ac43dbb-44d6-871e-b411-a1c18c61b55e
- 5136cc20-a63c-c7c8-00ae-fc5fa86be863
- 6f0b58f9-cb95-1fb3-5fef-cd914f9b4de3
- 8761af66-90ad-7f7d-2102-58b767495473
- d7bb0340-9894-8bd0-056a-29efc5444fa0
- 3a4e4953-19cb-5a92-d896-cfeaa03f5ba8
- 79b1d90a-0eaf-be78-9bbf-91c638626012
- a8c08d9f-a2ae-46c6-0371-f596ed13d1cf
- 355a3cad-a055-c14b-117e-47accfc708ca
- 6d2fc252-7270-aa59-e5e0-0c21432984ba
- 7442e18c-ac59-805d-6140-6db8778408b5
- 730963e3-8472-75ab-fc64-5be33cdcc125
- d1ac7006-362b-cc1d-d516-f11d65055473
- 2e555528-3530-497a-222a-7a3bbb35d938
