import argparse
from pathlib import Path

from modes_recorder.config import apply_overrides, check_gains, load_recorder
from modes_recorder.radio import Radio
from modes_recorder.record import record
from modes_recorder.config import apply_overrides, check_gains, check_sample_type, load_recorder

BASE_DIR = Path(__file__).resolve().parent.parent


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recorder", required=True, help="path to this recorder's .toml file")
    parser.add_argument("--duration", type=float, default=1800, help="recording length in seconds (default 1800s)")

    # can assign recorder location
    parser.add_argument("--site", required=True, help='site description, e.g. "RDU parking deck"')
    parser.add_argument("--lat", type=float, required=True, help="latitude in decimal degrees")
    parser.add_argument("--lon", type=float, required=True, help="longitude in decimal degrees (west is negative)")
    parser.add_argument("--alt", type=float, help="antenna GEOMETRIC altitude in meters ")

    # can edit the universal radio config through the cli
    parser.add_argument("--frequency-hz", type=float, help="override frequency_hz from radio.toml")
    parser.add_argument("--sample-rate", type=float, help="override sample_rate from radio.toml")
    parser.add_argument("--lna-gain", type=int, help="override lna_gain from radio.toml (0-14)")
    parser.add_argument("--mixer-gain", type=int, help="override mixer_gain from radio.toml (0-15)")
    parser.add_argument("--vga-gain", type=int, help="override vga_gain from radio.toml (0-15)")

    return parser.parse_args()


def main():
    radio_config = load_recorder(BASE_DIR / "config" / "radio.toml")
    args = parse_args()
    recorder_config = load_recorder(args.recorder)

    overrides = apply_overrides(radio_config, args)
    check_gains(radio_config)
    check_sample_type(radio_config)

    radio = Radio(radio_config)
    record(radio, args, radio_config, overrides, recorder_config, BASE_DIR / "recordings")

if __name__ == "__main__":
    main()
