import tomllib


def load_recorder(path):
    with open(path, "rb") as f:
        recorder_settings = tomllib.load(f)
    return recorder_settings


def apply_overrides(radio_config, args):
    overrides = {}
    for key in ["frequency_hz", "sample_rate", "lna_gain", "mixer_gain", "vga_gain"]:
        value = getattr(args, key)
        if value is not None:
            print(f"Warning: {key} overridden from command line: {radio_config[key]} -> {value}")
            radio_config[key] = value
            overrides[key] = value
    return overrides


def check_gains(radio_config):
    gain_limits = {"lna_gain": 14, "mixer_gain": 15, "vga_gain": 15} # I am not 100% sure of these gain values.(used claude to get these...) double check 
    for key, max_gain in gain_limits.items():
        if not 0 <= radio_config[key] <= max_gain:
            raise SystemExit(f"{key} must be 0-{max_gain}, got {radio_config[key]}")


def check_sample_type(radio_config):
    if radio_config["sample_type"] != "CS16":
        raise SystemExit(f"sample_type must be CS16, got {radio_config['sample_type']}")
