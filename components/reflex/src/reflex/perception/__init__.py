"""Reflex Perception Package: Multi-modal UI observation and distillation."""

from reflex.perception.browser.cdp_provider import CDPObservationProvider
from reflex.perception.vision import (
    BaseVisionGrounder,
    CropAndRouteEngine,
    CropPacket,
    MockVisionGrounder,
    OpenCVVisualDiffer,
    VisualDetection,
    VisualDifferenceResult,
    VisualDifferPort,
    VisionGrounderPort,
)

from reflex.perception.native import (
    LinuxATSPIAdapter,
    LinuxATSPIObservationAdapter,
    MacOSAXAdapter,
    MacOSAXObservationAdapter,
    MockLinuxATSPISubstrate,
    MockMacOSAXSubstrate,
    MockWindowsUIASubstrate,
    NativeObservationConfig,
    NativeObservationFactory,
    NativeObservationPort,
    NativeUIElement,
    PlatformAdapterRegistry,
    WindowsUIAAdapter,
    WindowsUIAObservationAdapter,
)

__all__ = [
    "CDPObservationProvider",
    "VisualDifferenceResult",
    "VisualDifferPort",
    "OpenCVVisualDiffer",
    "CropPacket",
    "CropAndRouteEngine",
    "VisualDetection",
    "VisionGrounderPort",
    "BaseVisionGrounder",
    "MockVisionGrounder",
    "NativeObservationConfig",
    "NativeObservationPort",
    "NativeUIElement",
    "NativeObservationFactory",
    "PlatformAdapterRegistry",
    "WindowsUIAObservationAdapter",
    "WindowsUIAAdapter",
    "MockWindowsUIASubstrate",
    "MacOSAXObservationAdapter",
    "MacOSAXAdapter",
    "MockMacOSAXSubstrate",
    "LinuxATSPIObservationAdapter",
    "LinuxATSPIAdapter",
    "MockLinuxATSPISubstrate",
]
