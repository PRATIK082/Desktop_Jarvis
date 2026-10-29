"""Audio device selection (Agent.md §7).

Lists available input/output devices and lets the UI select a microphone
and speaker. Degrades gracefully when no audio backend is available.
"""

from __future__ import annotations

try:
    import sounddevice as _sd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — sounddevice optional
    _sd = None

from dataclasses import dataclass

from jarvis.telemetry.logger import log_event


@dataclass(frozen=True)
class AudioDevice:
    """A single audio device."""
    id: str
    name: str
    is_input: bool
    sample_rate: int = 16000
    channels: int = 1


class AudioDeviceManager:
    """Discovers and selects audio devices.

    Uses the `sounddevice` package when available; otherwise returns an
    empty device list and defaults to None (system default). All methods
    are safe to call without a real audio backend.
    """

    def __init__(self) -> None:
        self._devices: list[AudioDevice] = []
        self._available = False
        self._discover()

    def _discover(self) -> None:
        if _sd is None:
            # sounddevice not installed — no real audio devices available.
            self._available = False
            return
        try:
            devices = _sd.query_devices()
            for idx, dev in enumerate(devices):
                try:
                    dev_id = str(idx)
                    name = str(dev.get("name", f"device {idx}"))
                    max_in = int(dev.get("max_input_channels", 0))
                    max_out = int(dev.get("max_output_channels", 0))
                    default_sr = int(dev.get("default_samplerate", 16000))
                    if max_in > 0:
                        self._devices.append(
                            AudioDevice(
                                id=dev_id,
                                name=name,
                                is_input=True,
                                sample_rate=default_sr,
                                channels=1,
                            )
                        )
                    if max_out > 0:
                        self._devices.append(
                            AudioDevice(
                                id=dev_id,
                                name=name,
                                is_input=False,
                                sample_rate=default_sr,
                                channels=1,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 — skip malformed device entries
                    log_event(
                        "jarvis.audio.devices",
                        "device_skip",
                        level="warn",
                        details={"error": str(exc)},
                    )
                    continue
            self._available = True
        except ImportError:
            self._available = False
        except Exception as exc:  # noqa: BLE001 — audio backend failure is non-fatal
            log_event(
                "jarvis.audio.devices",
                "discovery_failed",
                level="warn",
                details={"error": str(exc)},
            )
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def input_devices(self) -> list[AudioDevice]:
        return [d for d in self._devices if d.is_input]

    def output_devices(self) -> list[AudioDevice]:
        return [d for d in self._devices if not d.is_input]

    def default_input(self) -> AudioDevice | None:
        for d in self.input_devices():
            return d
        return None

    def default_output(self) -> AudioDevice | None:
        for d in self.output_devices():
            return d
        return None

    def find(self, device_id: str) -> AudioDevice | None:
        for d in self._devices:
            if d.id == device_id:
                return d
        return None

    def all_devices(self) -> list[AudioDevice]:
        return list(self._devices)

    def to_dict(self) -> list[dict[str, object]]:
        return [
            {
                "id": d.id,
                "name": d.name,
                "is_input": d.is_input,
                "sample_rate": d.sample_rate,
                "channels": d.channels,
            }
            for d in self._devices
        ]
