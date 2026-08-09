import json
d = json.load(open("evaluations/campaign/TERMINAL_VALIDATION_FREEZE_REPAIR.json"))
print("Runner SHA:", d["files_sha256"]["scripts/run_rbs_v4_holdout_frozen.py"])
print("Length:", len(d["files_sha256"]["scripts/run_rbs_v4_holdout_frozen.py"]))
print("Collection window:", d["references"]["data_collection_window"])