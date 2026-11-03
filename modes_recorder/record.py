import time
from datetime import UTC, datetime

import numpy as np

from modes_recorder.metadata import build_metadata, save_metadata
from modes_recorder.writer import BlockWriter


def record(radio, args, radio_config, overrides, recorder_config, output_dir):
    recorder_id = recorder_config["recorder_id"]
    sample_rate = radio_config["sample_rate"]
    stream_started_time = None
    monotonic_start = None
    elapsed_s = 0.0

    spare_buffer = np.empty(2 * radio.samples_per_read, dtype=np.int16)
    backlog_drops = []
    radio_info = radio.get_info()

    output_dir.mkdir(exist_ok=True)
    start_time = datetime.now(UTC)  # zulu time
    output_path = output_dir / f"{recorder_id}_{start_time.strftime('%Y%m%dT%H%M%SZ')}.cs16"
    metadata_path = output_path.with_suffix(".json")
    target_samples = int(args.duration * sample_rate)
    total_samples = 0
    overflows = []

    def write_metadata(status, samples):
        metadata = build_metadata(
            args,
            radio_config,
            overrides,
            recorder_config,
            output_path,
            start_time,
            stream_started_time,
            status,
            samples,
            overflows,
            elapsed_s,
            radio_info,
            backlog_drops,
        )
        save_metadata(metadata, metadata_path)

    # runs on the writer thread every 10 seconds of samples
    def checkpoint(samples_written):
        write_metadata(status, samples_written)

    status = "recording"
    write_metadata(status, total_samples)

    try:
        with open(output_path, "wb") as f:
            writer = BlockWriter(
                f, radio.samples_per_read, on_checkpoint=checkpoint, checkpoint_samples=int(10 * sample_rate)
            )
            writer.start()
            try:
                start_time = datetime.now(UTC)
                monotonic_start = time.monotonic()
                radio.start()
                stream_started_time = datetime.now(UTC)
                while total_samples < target_samples:
                    if writer.error:
                        raise writer.error

                    buffer = writer.get_free_buffer()
                    backlogged = buffer is None
                    if backlogged:
                        buffer = spare_buffer

                    samples, problem = radio.read(buffer)
                    elapsed_s = time.monotonic() - monotonic_start

                    if problem is not None and not backlogged:
                        writer.release(buffer)

                    if problem is None and backlogged:
                        if backlog_drops and backlog_drops[-1]["sample_index"] == total_samples:
                            backlog_drops[-1]["samples_lost"] += samples
                        else:
                            backlog_drops.append(
                                {
                                    "sample_index": total_samples,
                                    "samples_lost": samples,
                                    "utc": datetime.now(UTC).isoformat(),
                                    "elapsed_s": elapsed_s,
                                }
                            )
                            print(f"Warning: disk too slow, samples dropped at sample {total_samples}")
                    elif problem is None:
                        writer.submit(buffer, samples)
                        total_samples += samples
                    elif problem == "overflow":
                        overflows.append(
                            {
                                "sample_index": total_samples,
                                "file_position_s": total_samples / sample_rate,
                                "utc": datetime.now(UTC).isoformat(),
                                "elapsed_s": elapsed_s,
                            }
                        )
                        print(f"Warning: overflow (samples dropped) at sample {total_samples}")
                    elif problem == "timeout":
                        status = "error: no samples for 1 second"
                        break
                    else:
                        status = f"error: {problem}"
                        break
            finally:
                writer.finish()
                total_samples = writer.samples_written

        if writer.error:
            raise writer.error

        if status == "recording":
            status = "complete"
    except KeyboardInterrupt:
        status = "stopped by user"
    except Exception as e:
        status = f"error: {e}"
        raise
    finally:
        try:
            radio.stop()
        finally:
            write_metadata(status, total_samples)
            print(f"{status}: {total_samples} samples saved to {output_path}")
