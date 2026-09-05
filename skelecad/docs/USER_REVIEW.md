# User review — revision 0.6.0

## Digitally verified

- FreeCAD 1.1.3 generation completed.
- Thirteen generated part/test families export as valid single CAD solids.
- Every STL is closed, two-manifold, non-degenerate, and one connected component.
- The nine-piece T. rex assembly has zero volumetric collisions.
- Six ball/socket connections have zero assembled material overlap.
- The common ball joint provides at least 25° pitch and 25° yaw without CAD interference.
- The actual v2 ball stud completed a 6,105-element tetrahedral analysis: at a
  10 N side load, displacement is 0.095 mm and maximum von Mises stress is
  12.30 MPa (linear-static reference safety factor 3.66 against 45 MPa).
- CalculiX 2.22 baseline completed with 384 C3D8 elements.
- 20 N equivalent-shaft end displacement: 0.607 mm.
- Euler-Bernoulli reference displacement: 0.624 mm.
- The socketed `bone_long` model completed a 2,015-element tetrahedral analysis.
- At 20 N, its loaded-rim displacement is 0.638 mm and maximum von Mises stress
  is 14.4 MPa. This is a linear-static estimate, not an impact or fatigue result.
- All fifteen 3MF packages passed package, unit, object, and triangle validation.
- OrcaSlicer 2.4.2 is available locally; the starter fit kit opens with
  `tools/open_print_kit.ps1`.

## User decisions requested

1. Visual direction: approve the T. rex silhouette or request changes to the
   skull, jaw, rib cage, legs, feet, arms, or tail proportions.
2. First physical fit: open `build/print/starter_fit_kit.3mf`, select the real
   printer and filament profile, print it, then report which diametral clearance
   (0.4, 0.6, or 0.8 mm) snaps and moves best.
3. Preferred first creature: biped, quadruped, flying creature, or aquatic creature.

## Still requires physical verification

- Repeated insertion/removal wear
- Ball-neck break strength, socket fatigue, and impact behaviour
- Real printer bridging/support behaviour around horizontal sockets
- Child-product safety and choking-hazard assessment
