# Environment completion audit — 2026-08-14

## 1. Conversational modification through Codex

- Workspace and project `AGENTS.md` files define the source of truth, safety
  constraints, and mandatory post-change checks.
- User-facing geometry and material values are centralized in
  `config/parameters.json`.
- `tools/build.ps1` regenerates all deliverables from those sources.

Evidence: the complete nine-stage build passes from the workspace-local tools.

## 2. User review and revision loop

- `build/review/current/assembly.png` is the current visual confirmation image.
- `build/review/current/summary.md` is a Japanese confirmation sheet.
- `build/review/current/review.json` records parameter changes and all check gates.
- A changed model ID archives the prior bundle under `build/review/history/`;
  rebuilding an unchanged model creates no duplicate history entry.

Evidence: unchanged rebuild reported zero parameter changes; a no-geometry source
marker archived model `d8458c8a5956` with its image, summary, and parameters, then
the marker was removed.

## 3. Assembly

- FreeCAD assembly: `build/assembly/SkeleCAD_Assembly.FCStd`
- Neutral exchange assembly: `build/assembly/SkeleCAD_Assembly.step`
- Current revision 0.6.0 assembly contains nine user-assembly pieces and reports
  zero volumetric collisions.
- The user launcher opens the assembly in FreeCAD 1.1.3.

## 4. Computer-aided engineering

- An equivalent-section CalculiX baseline is checked against beam theory.
- The actual socketed long-bone geometry is tetrahedralized by Gmsh and solved by
  CalculiX.
- The active v2 ball stud is also tetrahedralized and solved under a 10 N side load.
- Current actual-part result at 20 N: 0.638 mm loaded-rim displacement and
  14.40 MPa maximum von Mises stress.

Scope: linear-static prototype estimate only; no contact, fatigue, or impact claim.

## 5. 3D-printer output

- Thirteen individual STL files pass closed two-manifold, connected-component,
  degeneracy, and positive-volume checks.
- Thirteen individual 3MF files plus the starter fit kit pass package, unit, object,
  and triangle checks.
- `tools/open_print_kit.ps1` opens the combined calibration kit in OrcaSlicer.
- Printer-specific G-code is intentionally produced only after the user selects
  the real printer, nozzle, and filament profile in the slicer.
- The starter kit now contains 0.4/0.6/0.8 mm-clearance slotted sockets and an
  8 mm ball test key.

## 6. Installed and pinned tools

- FreeCAD 1.1.3
- Gmsh 4.15.0
- CalculiX 2.22
- OrcaSlicer 2.4.2 portable

`config/toolchain.json` pins paths and versions. The build verifies all of them,
including the official OrcaSlicer archive size and SHA-256 digest, before modelling.

## Result

The requested local environment is operational end to end. Remaining activities
are design choices and physical calibration inputs, not missing environment
capabilities: visual direction, printer/profile selection, and the preferred
5.2/5.4/5.6 mm fit result.
