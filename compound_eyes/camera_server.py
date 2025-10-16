from ntcore import NetworkTableInstance, NetworkTable
import socket


class PublishedCameraStream:
    def __init__(self, nt: NetworkTableInstance, camera: str):
        table = nt.getTable("CameraPublisher").getSubTable(
            f"{socket.gethostname()}_{camera}"
        )
        self.connected = table.getBooleanTopic("connected").publish()
        self.description = table.getStringTopic("description").publish()
        self.mode = table.getStringTopic("mode").publish()
        self.modes = table.getStringArrayTopic("modes").publish()
        self.source = table.getStringTopic("source").publish()
        self.streams = table.getStringArrayTopic("streams").publish()

    def enable(self, description, current_format, streams):
        self.connected.set(True)
        self.description.set(description)
        self.mode.set(current_format)
        self.modes.set([current_format])
        self.source.set("cv:")
        self.streams.set(streams)

    def disable(self):
        self.connected.set(False)
        self.streams.set([])
