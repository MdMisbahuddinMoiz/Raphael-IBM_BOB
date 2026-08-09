import json

# Check actual collection window from JSONL
rows = [json.loads(l) for l in open("evaluations/campaign/rbs_v4_holdout.jsonl") if l.strip()]
timestamps = [r.get("timestamp") for r in rows if r.get("timestamp")]
print(f"Total rows with timestamps: {len(timestamps)}")
if timestamps:
    print(f"First: {timestamps[0]}")
    print(f"Last: {timestamps[-1]}")
    # Count unique timestamps
    uniq = sorted(set(timestamps))
    print(f"Unique timestamps: {len(uniq)}")
    # Parse and show range
    from datetime import datetime
    first_dt = datetime.fromisoformat(uniq[0].replace('Z', '+00:00'))
    last_dt = datetime.fromisoformat(uniq[-1].replace('Z', '+00:00'))
    print(f"First dt: {first_dt}")
    print(f"Last dt: {last_dt}")
    print(f"Duration: {last_dt - first_dt}")