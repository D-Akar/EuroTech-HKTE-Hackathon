import json
import os

def extract_lotuscare_context(fhir_bundle_path):
    with open(fhir_bundle_path, 'r', encoding='utf-8') as f:
        bundle = json.load(f)
        
    # Initialize our streamlined profile
    compact_data = {
        "_id": None,
        "demographics": {},
        "caretakers": [],
        "chronic_conditions": [],
        "allergies": [],
        "active_medications": [],
        "past_medications": [],
        "recent_procedures": []
    }
    
    entries = bundle.get("entry", [])
    
    for entry in entries:
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")
        
        # 1. Parse Patient Demographics & Caretakers
        if resource_type == "Patient":
            compact_data["_id"] = resource.get("id")
            
            # Extract standard name
            names = resource.get("name", [])
            if names:
                compact_data["demographics"]["name"] = names[0].get("text") or f"{' '.join(names[0].get('given', []))} {names[0].get('family', '')}".strip()
            
            compact_data["demographics"]["gender"] = resource.get("gender")
            compact_data["demographics"]["birth_date"] = resource.get("birthDate")
            
            # Language Preferences
            comms = resource.get("communication", [])
            languages = [c.get("language", {}).get("coding", [{}])[0].get("display", "").lower() for c in comms]
            compact_data["demographics"]["preferred_language"] = languages[0] if languages else "cantonese"
            
            # Extract Caretakers / Contacts
            contacts = resource.get("contact", [])
            for contact in contacts:
                rel_types = [t.get("coding", [{}])[0].get("code", "").lower() for t in contact.get("relationship", [])]
                # Filter for caretakers, next of kin, or family partners
                if any(r in ['c', 'n', 'pr', 'f'] for r in rel_types):
                    c_name = contact.get("name", {}).get("text") or f"{' '.join(contact.get('name', {}).get('given', []))} {contact.get('name', {}).get('family', '')}".strip()
                    compact_data["caretakers"].append({
                        "name": c_name,
                        "relationship": contact.get("relationship", [{}])[0].get("coding", [{}])[0].get("display", "Contact"),
                        "phone": contact.get("telecom", [{}])[0].get("value") if contact.get("telecom") else None
                    })

        # 2. Parse Clinical Conditions (Skip historical/resolved if verified)
        elif resource_type == "Condition":
            clinical_status = resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "")
            if clinical_status == "active":
                # Condition.onset[x] is a choice type: prefer onsetDateTime, fall
                # back to onsetPeriod.start (other variants like onsetAge aren't dates).
                onset = resource.get("onsetDateTime") or resource.get("onsetPeriod", {}).get("start")
                compact_data["chronic_conditions"].append({
                    "name": resource.get("code", {}).get("text") or resource.get("code", {}).get("coding", [{}])[0].get("display"),
                    "onset_date": onset[:10] if onset else None
                })

        # 3. Parse Allergies
        elif resource_type == "AllergyIntolerance":
            compact_data["allergies"].append({
                "substance": resource.get("code", {}).get("text") or resource.get("code", {}).get("coding", [{}])[0].get("display"),
                "type": resource.get("type"),
                "criticality": resource.get("criticality")
            })

        # 4. Parse Medications (active = current, stopped = past/discontinued)
        elif resource_type == "MedicationRequest":
            status = resource.get("status")
            if status in ["active", "completed", "stopped"]:
                med_name = resource.get("medicationCodeableConcept", {}).get("text") or resource.get("medicationCodeableConcept", {}).get("coding", [{}])[0].get("display")

                if status == "stopped":
                    # Discontinued medication - kept for long-term/history context.
                    authored = resource.get("authoredOn")
                    compact_data["past_medications"].append({
                        "name": med_name,
                        "prescribed_date": authored[:10] if authored else None
                    })
                    continue

                # Parse basic dosage instruction strings if available
                dosage_list = resource.get("dosageInstruction", [])
                instruction = dosage_list[0].get("text") if dosage_list else "As directed"

                compact_data["active_medications"].append({
                    "name": med_name,
                    "frequency": instruction
                })

        # 5. Parse Recent Procedures (Operations)
        elif resource_type == "Procedure":
            status = resource.get("status")
            if status == "completed":
                # Procedure.performed[x] is a choice type: Synthea emits either
                # performedDateTime or a performedPeriod (start/end range).
                performed = resource.get("performedDateTime") or resource.get("performedPeriod", {}).get("start")
                compact_data["recent_procedures"].append({
                    "name": resource.get("code", {}).get("text") or resource.get("code", {}).get("coding", [{}])[0].get("display"),
                    "date": performed[:10] if performed else None
                })

    # Most-recent-first so the AI's memory surfaces the latest prescriptions.
    # Entries with no prescribed_date sort to the end.
    compact_data["past_medications"].sort(
        key=lambda m: m.get("prescribed_date") or "", reverse=True
    )

    return compact_data


def process_file(fhir_bundle_path, output_dir):
    """Extract the compact profile from a FHIR bundle and write it to
    output_dir, naming the file by the patient's unique id so the id is
    carried through to the processed files."""
    profile = extract_lotuscare_context(fhir_bundle_path)

    patient_id = profile.get("_id")
    if not patient_id:
        # Fall back to the source filename stem if no Patient resource was found
        patient_id = os.path.splitext(os.path.basename(fhir_bundle_path))[0]

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{patient_id}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    return output_path


if __name__ == "__main__":
    import sys

    # Usage: python preprocess_fhir.py <input_fhir.json> [output_dir]
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python preprocess_fhir.py <input_fhir.json> [output_dir]"
        )

    input_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "data/fhir_processed"

    written = process_file(input_path, out_dir)
    print(f"Wrote {written}")