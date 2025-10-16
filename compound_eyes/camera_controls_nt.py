from linuxpy.video.device import (
    Device,
    MenuControl,
    BooleanControl,
    IntegerControl,
    BaseControl,
    BufferType,
    FrameType,
    FrameIntervalType,
)
from ntcore import (
    NetworkTable,
)
import json
from .network_choice import NetworkMenuControl, NetworkFormatControl


class NTControl:
    def update(self):
        pass

    def sync(self):
        pass

    def changed(self) -> bool:
        return False


class NTBooleanControl(NTControl):
    def __init__(self, device: Device, control: BooleanControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.topic = table.getBooleanTopic(control.config_name)
        self.entry = self.topic.getEntry(bool(self.control.default))
        self.entry.set(bool(self.control.value))

        self.metadata_topic = table.getStringTopic(f".metadata/{control.config_name}")
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

    def changed(self) -> bool:
        val = int(self.entry.get())
        return int(val) != self.control.value


class NTIntegerControl(NTControl):
    def __init__(self, device: Device, control: IntegerControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.topic = table.getIntegerTopic(control.config_name)
        self.entry = self.topic.getEntry(self.control.value)

        self.metadata_topic = table.getStringTopic(f".metadata/{control.config_name}")
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

    def changed(self) -> bool:
        val = self.entry.get()
        val = self.fix_val(val)
        self.entry.set(val)

        return val != self.control.value


class NTMenuControl(NTControl):
    def __init__(self, device: Device, control: MenuControl, table: NetworkTable):
        self.device = device
        self.control = control
        self.chooser = NetworkMenuControl(table, control)

    def update(self):
        self.chooser.periodic()
        val = self.chooser.get()

        if val != self.control.value:
            self.device.log.info(f"Updating {self.control.name}")
            self.control.value = val
            self.device.log.info(f"Updated {self.control.name}")

    def sync(self):
        self.chooser.sync()

    def changed(self) -> bool:
        self.chooser.periodic()
        val = self.chooser.get()

        return val != self.control.value


class NTFormatControl(NTControl):
    def __init__(self, device: Device, table: NetworkTable):
        self.device = device
        self.chooser = NetworkFormatControl(table, device)

    def update(self):
        self.chooser.periodic()
        val = self.chooser.get()
        current_format = self.get_format()

        if (
            val.pixel_format != current_format.pixel_format
            or val.width != current_format.width
            or val.height != current_format.height
            or val.max_fps != current_format.max_fps
        ):
            self.device.log.info("Updating Video Format")
            try:
                self.device.set_format(
                    BufferType.VIDEO_CAPTURE,
                    val.width,
                    val.height,
                    val.pixel_format.value,
                )
                self.device.set_fps(BufferType.VIDEO_CAPTURE, val.max_fps)
            except Exception as e:
                self.device.log.error(f"Could not update Video Format: {e}")
            else:
                self.device.log.info("Updated Video Format")

    def get_format(self) -> FrameType:
        format = self.device.get_format(BufferType.VIDEO_CAPTURE)
        fps = self.device.get_fps(BufferType.VIDEO_CAPTURE)

        return FrameType(
            type=FrameIntervalType.DISCRETE,
            pixel_format=format.pixel_format,
            width=format.width,
            height=format.height,
            min_fps=fps,
            max_fps=fps,
            step_fps=fps,
        )

    def sync(self):
        self.chooser.sync()

    def changed(self):
        self.chooser.periodic()
        val = self.chooser.get()
        current_format = self.device.get_format(BufferType.VIDEO_CAPTURE)

        return (
            val.pixel_format != current_format.pixel_format
            or val.width != current_format.width
            or val.height != current_format.height
        )


class CameraControlsTable:
    def __init__(self, camera: Device, table: NetworkTable):
        self.table = table
        self.camera = camera

        # Assigned in load_controls()
        self.controls: list[NTControl] = []

    def load_controls(self):
        self.camera.log.info(
            f"Device {self.camera.filename} has {len(self.camera.controls)} controls"
        )
        self.controls = [
            self.create_nt_control(control) for control in self.camera.controls.values()
        ]

        self.controls.append(NTFormatControl(self.camera, self.table))

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
        for control in self.controls:
            control.update()

    def sync(self):
        for control in self.controls:
            control.sync()

    def changed(self):
        return any(control.changed() for control in self.controls)
