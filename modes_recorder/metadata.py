import json
import os
from datetime import UTC, datetime


def build_metadata(
    args,
    radio_config,
    overrides,
    recorder_config,
    output_path,
    start_time,
    stream_started_time,
    status,
    total_samples,
    overflows,
    elapsed_s,
    radio_info,
    backlog_drops,
):
    sample_rate = radio_config["sample_rate"]
    recorder_id = recorder_config["recorder_id"]

    metadata = {
        "recorder_id": recorder_id,
        "location": {
            "site": args.site,
            "lat": args.lat,
            "lon": args.lon,
            "alt_m": args.alt,  # geometric altitude
        },
        "status": status,
        "data_file": output_path.name,
        "format": "CS16 (interleaved int16 I/Q, little-endian)",
        "start_time_utc": start_time.isoformat(),
        "stream_started_utc": stream_started_time.isoformat() if stream_started_time else None,
        "last_update_utc": datetime.now(UTC).isoformat(),
        "time_source": "system clock",
        "sample_rate": sample_rate,
        "requested_duration_s": args.duration,
        "total_samples": total_samples,
        "samples_duration_s": total_samples / sample_rate,
        "elapsed_s": elapsed_s,
        "estimated_lost_time_s": elapsed_s - total_samples / sample_rate,
        "overflows": overflows,
        "backlog_drops": backlog_drops,
        "radio_config": radio_config,
        "radio_overrides": overrides,
        "radio_info": radio_info,
        "recorder_config": recorder_config,
    }
    return metadata


def save_metadata(metadata, metadata_path):
    # write a temp file, then swap it in, so a power cut can't leave half a JSON file
    temp_path = metadata_path.with_suffix(".json.tmp")
    with open(temp_path, "w") as f:
        json.dump(metadata, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, metadata_path)
