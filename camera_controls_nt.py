from linuxpy.video.device import (
    Device,
    MenuControl,
    BooleanControl,
    IntegerControl,
    BaseControl,
    BufferType,
)
from ntcore import (
    NetworkTable,
)
import json
from source import CameraSource
from network_choice import NetworkMenuControl, NetworkFormatControl


class NTControl:
    def update(self):
        pass

    def sync(self):
        pass


class NTBooleanControl(NTControl):
    def __init__(self, device: Device, control: BooleanControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.topic = table.getBooleanTopic(control.config_name)
        self.entry = self.topic.getEntry(bool(self.control.default))

        self.metadata_topic = table.getStringTopic(f"{control.config_name}/.metadata")
        self.metadata_pub = self.metadata_topic.publish()

        metadata = {"default": bool(self.control.default)}
        self.metadata_pub.set(json.dumps(metadata))

    def update(self):
        val = int(self.entry.get())
        if int(val) != self.control.value:
            self.device.log.info(f"Updating {self.control.name}")
            self.control.value = int(val)
            self.device.log.info(f"Updated {self.control.name}")

    def sync(self):
        self.entry.set(bool(self.control.value))


class NTIntegerControl(NTControl):
    def __init__(self, device: Device, control: IntegerControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.topic = table.getIntegerTopic(control.config_name)
        self.entry = self.topic.getEntry(self.control.default)

        self.metadata_topic = table.getStringTopic(f"{control.config_name}/.metadata")
        self.metadata_pub = self.metadata_topic.publish()

        metadata = {
            "minimum": self.control.minimum,
            "maximum": self.control.maximum,
            "step": self.control.step,
            "default": self.control.default,
        }
        self.metadata_pub.set(json.dumps(metadata))

    def fix_val(self, val: int) -> int:
        val -= self.control.minimum
        offset = val % self.control.step
        val -= offset
        val += self.control.minimum
        val = min(val, self.control.maximum)

        return val

    def update(self):
        val = self.entry.get()
        val = self.fix_val(val)
        self.entry.set(val)

        if val != self.control.value:
            self.device.log.info(f"Updating {self.control.name}")
            self.control.value = val
            self.device.log.info(f"Updated {self.control.name}")

    def sync(self):
        self.entry.set(self.control.value)


class NTMenuControl(NTControl):
    def __init__(self, device: Device, control: MenuControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.chooser = NetworkMenuControl(table, control.config_name)

    def update(self):
        self.chooser.periodic()
        val = self.chooser.get()

        if val != self.control.value:
            self.device.log.info(f"Updating {self.control.name}")
            self.control.value = val
            self.device.log.info(f"Updated {self.control.name}")

    def sync(self):
        self.chooser.sync()


class NTFormatControl(NTControl):
    def __init__(self, device: Device, table: NetworkTable, source: CameraSource):
        self.device = device
        self.source = source
        self.chooser = NetworkFormatControl(table, device)

    def update(self):
        val = self.chooser.get()
        current_format = self.device.get_format()

        if (
            val.pixel_format != current_format.pixel_format
            or val.width != current_format.width
            or val.height != current_format.height
        ):
            self.device.log.info("Updating Video Format")
            try:
                self.source.stop()
                self.device.set_format(
                    BufferType.VIDEO_CAPTURE,
                    format.width,
                    format.height,
                    format.pixel_format.name,
                )
                self.source.start()
            except Exception:
                self.device.log.info("Could not update Video Format")
            else:
                self.device.log.info("Updated Video Format")

    def sync(self):
        self.chooser.sync()


class CameraControlsTable:
    def __init__(self, camera: Device, table: NetworkTable, source: CameraSource):
        self.table = table
        self.camera = camera
        self.source = source

        # Assigned in load_controls()
        self.controls: list[NTControl] = []

        self.setup_entry = table.getBooleanTopic("setup_mode").getEntry(False)
        self.setup_entry.set(self.setup_entry.get())

    def load_controls(self):
        self.camera.log.info(
            f"Device {self.camera.filename} has {len(self.camera.controls)} controls"
        )
        self.controls = [
            self.create_nt_control(control) for control in self.camera.controls.values()
        ]

        self.controls.append(NTFormatControl(self.camera, self.table, self.source))

    def unload_controls(self):
        self.controls = []

    def create_nt_control(self, control: BaseControl) -> NTControl:
        if isinstance(control, BooleanControl):
            return NTBooleanControl(self.camera, control, self.table)
        elif isinstance(control, IntegerControl):
            return NTIntegerControl(self.camera, control, self.table)
        elif isinstance(control, MenuControl):
            return NTMenuControl(self.camera, control, self.table)

        raise Exception(f"Unknown control type found {control}")

    def update(self):
        if self.setup_entry.get():
            for control in self.controls:
                control.update()
        else:
            for control in self.controls:
                control.sync()
