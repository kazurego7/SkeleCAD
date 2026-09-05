# SkeleCAD project instructions

## Objective

Maintain an original, modular skeletal-creature construction system that Codex
can regenerate, assemble, analyse, preview, and export for 3D printing.

## Source of truth

- Read `config/parameters.json` and `docs/DESIGN.md` before changing geometry.
- All user-facing dimensions and material properties belong in
  `config/parameters.json`; do not duplicate them in model code.
- `src/freecad_project.py` is the authoritative geometry generator.
- `config/toolchain.json` pins the local tool versions and integrity metadata.
- Files under `build/` are generated artifacts. Never edit them manually.

## Required workflow after a geometry change

1. Run `tools/build.ps1`.
2. Require the pinned toolchain integrity check to pass.
3. Require every CAD solid to be valid and non-empty.
4. Require every STL to be a closed two-manifold mesh with positive volume.
5. Require every 3MF package to be structurally valid and use millimetres.
6. Regenerate the FCStd parts document, assembly document, STEP, STL and 3MF exports.
7. Run both the equivalent-section baseline and actual-part Gmsh + CalculiX analysis
   unless the change is documentation-only.
8. Preserve `build/review/history/` and use the generated current review bundle
   when presenting a change for user confirmation.
9. Update `docs/CHANGELOG.md` for compatibility or dimensional changes.
10. Report exact changed parameters, output paths, validation results, and any
   physical fit test still required.

## Compatibility and safety

- Do not change `joint.version` or nominal ball diameter without explicit user
  approval. Printed parts depend on that interface.
- Preserve the user's selected ball/socket fit clearance until a new calibration result is
  provided.
- Do not copy commercial toy geometry, branding, names, or exact part layouts.
- Avoid points sharper than 1 mm radius and walls thinner than `printing.min_wall_mm`.
- Detachable components are choking hazards. This prototype is not a certified
  children's product; never claim otherwise.
- CAE is an engineering estimate. Physical fit, fatigue, impact, and break tests
  remain mandatory before relying on the design.
