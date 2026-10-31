import argparse
from datetime import datetime, timezone
import tomllib
from pathlib  import Path 
import numpy as np 
import SoapySDR
from SoapySDR import SOAPY_SDR_RX,SOAPY_SDR_OVERFLOW, SOAPY_SDR_TIMEOUT
import json

BASE_DIR = Path(__file__).resolve().parent

def load_recorder(path):
    with open(path, 'rb') as f:
        recorder_settings = tomllib.load(f)
    return recorder_settings

radio_config = load_recorder(BASE_DIR/"config"/"radio.toml")

parser = argparse.ArgumentParser()
parser.add_argument("--recorder", required=True, help="path to this recorder's .toml file")
parser.add_argument("--duration", type=float, default=1800, help="recording length in seconds (default 1800s)")

#can assign recorder location
parser.add_argument("--site", required=True, help='site description, e.g. "RDU parking deck"')
parser.add_argument("--lat", type=float, required=True, help="latitude in decimal degrees")
parser.add_argument("--lon", type=float, required=True, help="longitude in decimal degrees (west is negative)")
parser.add_argument("--alt", type=float, help="antenna GEOMETRIC altitude in meters ")

#can edit the universal radio config through the cli
parser.add_argument("--frequency-hz", type=float, help="override frequency_hz from radio.toml")
parser.add_argument("--sample-rate", type=float, help="override sample_rate from radio.toml")
parser.add_argument("--lna-gain", type=int, help="override lna_gain from radio.toml (0-14)")
parser.add_argument("--mixer-gain", type=int, help="override mixer_gain from radio.toml (0-15)")
parser.add_argument("--vga-gain", type=int, help="override vga_gain from radio.toml (0-15)")

args = parser.parse_args()
recorder_config = load_recorder(args.recorder)
recorder_id = recorder_config["recorder_id"]


overrides = {}
for key in ["frequency_hz", "sample_rate", "lna_gain", "mixer_gain", "vga_gain"]:
    value = getattr(args, key)
    if value is not None:
        print(f"Warning: {key} overridden from command line: {radio_config[key]} -> {value}")
        radio_config[key] = value
        overrides[key] = value


gain_limits = {"lna_gain": 14, "mixer_gain": 15, "vga_gain": 15}
for key, max_gain in gain_limits.items():
    if not 0 <= radio_config[key] <= max_gain:
        raise SystemExit(f"{key} must be 0-{max_gain}, got {radio_config[key]}")

sdr = SoapySDR.Device(dict(driver =    "airspy"))
sample_rate = radio_config["sample_rate"]

if sample_rate not in sdr.listSampleRates(SOAPY_SDR_RX,0):
    raise SystemExit(f"sample rate {sample_rate} not supported by this airspy") 

sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
sdr.setFrequency(SOAPY_SDR_RX,0, radio_config["frequency_hz"])
sdr.setGainMode(SOAPY_SDR_RX,0,False)
sdr.setGain(SOAPY_SDR_RX,0,"LNA",radio_config["lna_gain"])
sdr.setGain(SOAPY_SDR_RX,0, "MIX", radio_config['mixer_gain'])
sdr.setGain(SOAPY_SDR_RX,0, "VGA", radio_config['vga_gain'])

rx_stream = sdr.setupStream(SOAPY_SDR_RX, radio_config["sample_type"],[0])
sdr.activateStream(rx_stream)

samples_per_read = sdr.getStreamMTU(rx_stream)
buffer = np.empty(2 * samples_per_read, dtype=np.int16)

output_dir= BASE_DIR/ "recordings"
output_dir.mkdir(exist_ok=True)
start_time = datetime.now(timezone.utc) #zulu time
output_path = output_dir/ f"{recorder_id}_{start_time.strftime('%Y%m%dT%H%M%SZ')}.cs16"

target_samples = int(args.duration * sample_rate)
total_samples = 0
overflows = []
metadata_path = output_path.with_suffix(".json")

def write_metadata(status):
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
        "last_update_utc": datetime.now(timezone.utc).isoformat(),
        "time_source": "system clock",
        "sample_rate": sample_rate,
        "requested_duration_s": args.duration,
        "total_samples": total_samples,
        "actual_duration_s": total_samples / sample_rate,
        "overflows": [
            {"sample_index": i, "time_s": i / sample_rate} for i in overflows
        ],
        "radio_config": radio_config,
        "radio_overrides": overrides,
        "recorder_config": recorder_config,
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

status = "recording"
write_metadata(status)
last_metadata_update = 0

try:
    with open(output_path, "wb") as f:
        while total_samples < target_samples:
            sr = sdr.readStream(rx_stream, [buffer], samples_per_read, timeoutUs=1_000_000)

            if sr.ret > 0:
                buffer[:2 * sr.ret].tofile(f)
                total_samples += sr.ret
            elif sr.ret == SOAPY_SDR_OVERFLOW:
                overflows.append(total_samples)
                print(f"Warning: overflow (samples dropped) at sample {total_samples}")
            elif sr.ret == SOAPY_SDR_TIMEOUT:
                status = "error: no samples for 1 second"
                break
            else:
                status = f"error: readStream returned {sr.ret}"
                break
            if total_samples - last_metadata_update >= 10 * sample_rate:
                write_metadata(status)
                last_metadata_update = total_samples

    if status == "recording":
        status = "complete"
except KeyboardInterrupt:
    status = "stopped by user"
except Exception as e:
    status = f"error: {e}"
    raise
finally:
    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    write_metadata(status)
    print(f"{status}: {total_samples} samples saved to {output_path}")