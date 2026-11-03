import SoapySDR
from SoapySDR import SOAPY_SDR_OVERFLOW, SOAPY_SDR_RX, SOAPY_SDR_TIMEOUT


def open_radio(radio_config):
    sdr = SoapySDR.Device({"driver": "airspy"})
    sample_rate = radio_config["sample_rate"]
    if sample_rate not in sdr.listSampleRates(SOAPY_SDR_RX, 0):
        raise SystemExit(f"sample rate {sample_rate} not supported by this airspy")

    sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
    sdr.setFrequency(SOAPY_SDR_RX, 0, radio_config["frequency_hz"])
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    sdr.setGain(SOAPY_SDR_RX, 0, "LNA", radio_config["lna_gain"])
    sdr.setGain(SOAPY_SDR_RX, 0, "MIX", radio_config["mixer_gain"])
    sdr.setGain(SOAPY_SDR_RX, 0, "VGA", radio_config["vga_gain"])
    return sdr


def setup_stream(sdr, radio_config):
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, radio_config["sample_type"], [0])
    samples_per_read = sdr.getStreamMTU(rx_stream)
    return rx_stream, samples_per_read


class Radio:
    def __init__(self, radio_config):
        self.sdr = open_radio(radio_config)

        self.rx_stream, self.samples_per_read = setup_stream(self.sdr, radio_config)

    def start(self):
        self.sdr.activateStream(self.rx_stream)

    def read(self, buffer):
        sr = self.sdr.readStream(self.rx_stream, [buffer], self.samples_per_read, timeoutUs=1_000_000)
        if sr.ret > 0:
            return sr.ret, None
        if sr.ret == SOAPY_SDR_OVERFLOW:
            return 0, "overflow"
        if sr.ret == SOAPY_SDR_TIMEOUT:
            return 0, "timeout"
        return 0, f"readStream returned {sr.ret}"

    def stop(self):
        self.sdr.deactivateStream(self.rx_stream)
        self.sdr.closeStream(self.rx_stream)

    def get_info(self):
        return {
            "serial": self.sdr.getHardwareInfo()["serial"],
            "soapysdr_version": SoapySDR.getLibVersion(),
            "driver_reported": {
                "sample_rate": self.sdr.getSampleRate(SOAPY_SDR_RX, 0),
                "frequency_hz": self.sdr.getFrequency(SOAPY_SDR_RX, 0),
                "lna_gain": self.sdr.getGain(SOAPY_SDR_RX, 0, "LNA"),
                "mixer_gain": self.sdr.getGain(SOAPY_SDR_RX, 0, "MIX"),
                "vga_gain": self.sdr.getGain(SOAPY_SDR_RX, 0, "VGA"),
            },
        }
