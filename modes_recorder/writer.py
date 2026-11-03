import os
import queue
import threading

import numpy as np


class BlockWriter:
    def __init__(self, f, samples_per_read, on_checkpoint=None, checkpoint_samples=None, num_buffers=184):
        self.f = f
        self.on_checkpoint = on_checkpoint
        self.checkpoint_samples = checkpoint_samples
        self.free_buffers = queue.Queue()
        self.full_buffers = queue.Queue()
        for _ in range(num_buffers):
            self.free_buffers.put(np.empty(2 * samples_per_read, dtype=np.int16))
        self.samples_written = 0
        self.error = None
        self.thread = threading.Thread(target=self._run)

    def start(self):
        self.thread.start()

    def get_free_buffer(self):
        try:
            return self.free_buffers.get_nowait()
        except queue.Empty:
            return None

    def submit(self, buffer, samples):
        self.full_buffers.put((buffer, samples))

    def release(self, buffer):
        self.free_buffers.put(buffer)

    def finish(self):
        self.full_buffers.put(None)
        self.thread.join()

    def _sync(self):
        self.f.flush()
        os.fsync(self.f.fileno())

    def _run(self):
        last_checkpoint = 0
        try:
            while True:
                item = self.full_buffers.get()
                if item is None:
                    self._sync()
                    return
                buffer, samples = item
                buffer[: 2 * samples].tofile(self.f)
                self.samples_written += samples
                self.free_buffers.put(buffer)

                # sync first, so the metadata never claims samples that aren't on disk yet
                if self.on_checkpoint and self.samples_written - last_checkpoint >= self.checkpoint_samples:
                    self._sync()
                    self.on_checkpoint(self.samples_written)
                    last_checkpoint = self.samples_written
        except Exception as e:  # noqa: BLE001 - any failure here must reach the read loop
            self.error = e
