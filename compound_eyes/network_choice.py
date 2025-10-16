from ntcore import (
    NetworkTable,
)
from linuxpy.video.device import (
    MenuControl,
    Device,
    FrameSizeType,
    FrameType,
)
from typing import Any


class NetworkChooser:
    def __init__(
        self, table: NetworkTable, name: str, options: list[str], default: str
    ):
        self.options = options
        self.active = default

        self.table = table.getSubTable(name)
        self.namePublisher = self.table.getStringTopic(".name").publish()
        self.typePublisher = self.table.getStringTopic(".type").publish()
        self.optionsPublisher = self.table.getStringArrayTopic("options").publish()
        self.defaultPublisher = self.table.getStringTopic("default").publish()
        self.activePublisher = self.table.getStringTopic("active").publish()
        self.selectedEntry = self.table.getStringTopic("selected").getEntry(self.active)

        self.namePublisher.set(name)
        self.typePublisher.set("String Chooser")
        self.optionsPublisher.set(self.options)
        self.defaultPublisher.set(self.active)
        self.activePublisher.set(self.active)
        self.selectedEntry.set(self.active)

    def get(self) -> Any:
        return self.active

    def periodic(self):
        selected = self.selectedEntry.get()

        if selected in self.options:
            self.active = selected
            self.defaultPublisher.set(selected)
            self.activePublisher.set(selected)
        else:
            self.selectedEntry.set(self.active)

    def sync(self):
        self.selectedEntry.set(self.active)


class NetworkMenuControl(NetworkChooser):
    def __init__(self, table: NetworkTable, control: MenuControl):
        self.inverted_index: dict[str, int] = {control[id]: id for id in control}
        super().__init__(
            table,
            control.config_name,
            [control[id] for id in control],
            control[control.value],
        )

    def get(self) -> int:
        return self.inverted_index[self.active]


class NetworkFormatControl(NetworkChooser):
    def __init__(self, table: NetworkTable, device: Device):
        self.formats = [
            format
            for format in device.info.frame_sizes
            if format.type == FrameSizeType.DISCRETE
        ]

        self.format_strs = [self.str_frame(format) for format in self.formats]

        default_format = self.format_strs[-1]
        super().__init__(
            table,
            "video_format",
            self.format_strs,
            default_format,
        )

    def str_frame(self, format: FrameType) -> str:
        return f"{format.width}x{format.height}px {format.pixel_format.name} {format.min_fps} fps"

    def get(self) -> FrameType:
        idx = self.format_strs.index(self.active)
        return self.formats[idx]
