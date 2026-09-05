"""Create a FreeCAD review document for the generated appearance mesh."""

from pathlib import Path
import json

import FreeCAD as App
import Mesh
import Part


PROJECT = Path(__file__).resolve().parents[1]
BUILD = PROJECT / "build" / "generated_appearance"
STL = BUILD / "trex_appearance_200mm.stl"
OUTPUT = BUILD / "trex_image_to_3d_reference.FCStd"
PARAMETERS = json.loads((PROJECT / "config" / "parameters.json").read_text(encoding="utf-8"))
JOINT_VERSION = PARAMETERS["joint"]["version"]

doc = App.newDocument("TRex_ImageTo3D_Reference")

appearance = doc.addObject("Mesh::Feature", "GeneratedAppearance")
appearance.Label = "Image-to-3D appearance (200 mm reference)"
appearance.Mesh = Mesh.Mesh(str(STL))
if appearance.ViewObject:
    appearance.ViewObject.ShapeColor = (0.78, 0.65, 0.47)
    appearance.ViewObject.LineColor = (0.20, 0.14, 0.08)

joint_group = doc.addObject("App::DocumentObjectGroup", "ProposedJointCenters")
joint_group.Label = "Proposed anatomical rotation centers (review only)"

# These are independent anatomical proposals, not positions copied from the
# concept sheet. Final sockets are cut only after the part split is approved.
centers = {
    "NeckCenter": (-33.0, 0.0, 76.0),
    "TorsoCenter": (8.0, 0.0, 66.0),
    "LeftHipCenter": (28.0, 20.0, 51.0),
    "RightHipCenter": (28.0, -20.0, 51.0),
    "TailRootCenter": (48.0, 0.0, 55.0),
    "TailMidCenter": (73.0, 0.0, 48.0),
    "JawHingeCenter": (-69.0, 0.0, 75.0),
}

for name, center in centers.items():
    marker = doc.addObject("PartDesign::Feature", name)
    marker.Label = name.replace("Center", " rotation center")
    marker.Shape = Part.makeSphere(4.0, App.Vector(*center))
    if marker.ViewObject:
        marker.ViewObject.ShapeColor = (0.85, 0.10, 0.08)
        marker.ViewObject.Transparency = 20
    joint_group.addObject(marker)

note = doc.addObject("App::FeaturePython", "WorkflowNote")
note.addProperty("App::PropertyString", "AppearanceSource")
note.AppearanceSource = "Tencent Hunyuan3D 2.1 shape output"
note.addProperty("App::PropertyString", "MechanicalAuthority")
note.MechanicalAuthority = f"FreeCAD joint v{JOINT_VERSION}; markers are review proposals only"
note.addProperty("App::PropertyString", "NextStep")
note.NextStep = "Approve split centers, then cut parts and add exact ball/socket solids"

doc.recompute()
doc.saveAs(str(OUTPUT))
print(OUTPUT)
