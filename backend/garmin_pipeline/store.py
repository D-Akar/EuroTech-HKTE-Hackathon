"""MongoDB store for normalized wearable samples.

The team standardizes on MongoDB, so this replaces the earlier SQLite store while
keeping the same interface (upsert / all_dicts / latest_per_kind / kinds / count).
Each document uses the deterministic sample_id as its _id, so re-running a backfill
upserts in place rather than duplicating.
"""

from __future__ import annotations

from typing import Iterable, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient, ReplaceOne

from .models import Sample

_DEFAULT_TIMEOUT_MS = 3000


class SampleStore:
    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "careloop",
        collection_name: str = "garmin_samples",
        *,
        patient_id: str = "",
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> None:
        self.uri = uri
        self.db_name = db_name
        self.collection_name = collection_name
        self.patient_id = patient_id  # FHIR Patient id stamped on every sample, if set
        self._client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self._col = self._client[db_name][collection_name]
        self._col.create_index([("kind", ASCENDING), ("recorded_at", ASCENDING)])

    @classmethod
    def from_config(cls, cfg) -> "SampleStore":
        """Build a store from the loaded pipeline Config."""
        return cls(
            cfg.mongodb_uri,
            cfg.mongodb_db,
            cfg.mongodb_collection,
            patient_id=cfg.patient_uuid,
        )

    @property
    def target(self) -> str:
        """Human-readable destination, used in CLI status lines."""
        return f"{self.uri}/{self.db_name}.{self.collection_name}"

    def _to_doc(self, sample: Sample) -> dict:
        """Canonical sample dict with sample_id promoted to the Mongo _id."""
        doc = sample.with_id().to_dict()
        doc["_id"] = doc.pop("sample_id")
        if self.patient_id:
            doc["patient_id"] = self.patient_id
        return doc

    @staticmethod
    def _to_sample_dict(doc: dict) -> dict:
        """Mongo document back to the canonical sample dict the FHIR side consumes."""
        out = {
            "kind": doc["kind"],
            "value": doc["value"],
            "unit": doc["unit"],
            "recorded_at": doc["recorded_at"],
            "sample_id": doc["_id"],
            "source": doc["source"],
        }
        if doc.get("patient_id"):
            out["patient_id"] = doc["patient_id"]
        if doc.get("meta"):
            out["meta"] = doc["meta"]
        return out

    def upsert(self, samples: Iterable[Sample]) -> int:
        ops = []
        for sample in samples:
            doc = self._to_doc(sample)
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if not ops:
            return 0
        self._col.bulk_write(ops, ordered=False)
        return len(ops)

    def count(self) -> int:
        return int(self._col.count_documents({}))

    def kinds(self) -> dict[str, int]:
        cur = self._col.aggregate(
            [{"$group": {"_id": "$kind", "c": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
        )
        return {r["_id"]: r["c"] for r in cur}

    def all_dicts(self, kind: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
        query = {"kind": kind} if kind else {}
        cur = self._col.find(query).sort("recorded_at", ASCENDING)
        if limit:
            cur = cur.limit(limit)
        return [self._to_sample_dict(d) for d in cur]

    def latest_per_kind(self) -> list[dict]:
        cur = self._col.aggregate(
            [
                {"$sort": {"recorded_at": DESCENDING}},
                {"$group": {"_id": "$kind", "doc": {"$first": "$$ROOT"}}},
                {"$sort": {"_id": 1}},
            ]
        )
        return [self._to_sample_dict(r["doc"]) for r in cur]

    def close(self) -> None:
        self._client.close()
