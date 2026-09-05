# SkeleCAD design

SkeleCAD is an original family of rearrangeable skeletal-creature parts.
Revision 1.3.1 uses a free local image-to-3D model for the organic skeletal
appearance and FreeCAD for the exact 6 mm joint-v3 balls and slotted snap sockets.
The naturally open jaw is fixed as part of the head; it has no hinge hardware.

## S3 production fit selected from holding trial R3

Three deep C-shaped four-slot socket fits were compared. The user physically
selected S3, so revision 1.3.1 applies it to all eight joints of the 120 mm T. rex.
S3 uses a 6 mm ball, 3.4 mm pole, 5.4 mm retention opening and 5.90 mm spherical
cavity (0.10 mm diametral interference). The ankle pole is 2.0 mm longer than the
standard pole so the thick foot connection clears the socket-side anatomy without
additional bone removal. See `HOLDING_R3.md` for the calibration plate.

## Workflow

### Image workflow integration — verified automated prototype pipeline

The upload-to-Bambu preparation path has been exercised with a non-dinosaur image
and audited against the requested workflow. See `WORKFLOW_ACCEPTANCE.md` for
artifact hashes, live-view checks and limits. This is prototype automation, not
physical fit/strength or product-safety certification.

`tools/viewer_server.py` now accepts PNG/JPEG/WebP image jobs through a loopback,
same-origin API with a per-server request token, upload/pixel limits and fixed
artifact routes. The existing read-only production routes remain allowlisted.
Mutation and job APIs deliberately do not run through the Tailscale proxy.
Each image has a UUID directory under `build/workflows/`, an immutable original,
image/inference hashes, an atomic status file and separate generated artifacts.
One scheduler runs inference sequentially; a process identity includes creation
time so a recycled PID is not mistaken for a live worker. Queued jobs survive a
server restart; stopped active jobs are reported interrupted, never silently
restarted or labelled successful. A server lock prevents competing schedulers.

Images enter through whole-canvas drag/drop; there is no redundant upload button.
Generation progress uses a single bottom line; no permanent cards or legends were added.
Old geometry is cleared after an upload so it cannot masquerade as the new model.
The chosen job is recoverable via a `?job=` URL. Original supplied transparency is
preserved; simple backgrounds use border-seeded GrabCut without a hue filter.
Busy backgrounds are retained for review. This is not semantic background proof.

The Hunyuan child generates a fresh appearance mesh, independently of the source
fixture CAD. Y-up inference is rotated to Z-up and scaled to the configured 120 mm
longest extent. Exactly degenerate/duplicate faces can be removed; finite parts
are not deleted. Fitted spherical surface patches become joint proposals. A
surface connectivity pass distinguishes two-part junctions from terminal spheres
or rounded corners. It uses no dinosaur centres, names or seeds. Geodesic face
assignment creates colored surface groups while preserving every original face.
These groups have OPEN boundaries: they are expressly preview-only, NOT printable
parts or collision-valid closed solids. False proposals and missed/occluded joints
still need correction. Neck/ankle discovery is incomplete on the robot test.

The viewer consumes arbitrary part manifests and validated parent graphs;
oblique joint bases are orthonormal. Articulation remains disabled on open preview
groups. A contextual machining action now queues an isolated mechanical revision.
The FreeCAD authority authors finite sphere cuts around inferred old joint bulbs,
plus experimental C4_28 joints (6 mm ball, 6.15 mm cavity, 2.8 mm stem). These do
NOT replace production joint-v3 or claim physical fit. All resulting components
must map one-to-one to inferred cores; none are silently discarded. Local finishing
uses one declared strength and reports a hard error instead of weakening the operation.
Anchors must be
inside their own solid. Actual STL round trips require closed single components,
positive volume and <=0.001 mm3 export error. All neutral part pairs undergo Boolean
intersection and source loss is restricted to actual cuts and bounded finish tools.
CAD tools remain STEP/FCStd; organic anatomy is explicitly mesh geometry in the
assembly FCStd, with per-part STL/3MF exports, not a claimed parametric solid.

Only validated revisions become color-coded movable models. A geometry-bound
review action captures the displayed, collision-tested pose. The server rejects
stale/unfinished/colliding reviews; the print worker independently checks actual
meshes at that pose before slicing. Native Bambu presets, rigid auto-orientation,
multi-plate shelf placement and default tree supports produce per-plate 3MF files.
Before download, audits check source triangles/coordinates, globally unique object
IDs, rigid transforms, all sliced objects, machine/material/bed settings, G-code
checksums and actual extrusion bounds. Artifacts belong to a job/revision and the
download gate verifies the release and file hash. Nothing is sent to a printer.
Confirmation cancellation does not enqueue a job. Existing dinosaur/trial CAE
does not certify an arbitrary new organic model's attachment strength.

Each Bambu retry now slices into a fresh `print/plate_NN/attempts/<UUID>/`
directory. Earlier output/result files cannot satisfy a new invocation. A prior
release record is retained under `release_before_<UUID>.json`, and readiness is
revoked before packaging. Only audited output is copied to stable download names;
all plates and unchanged geometry/approval are required before atomic release.
The download gate rehashes the actual manifest, all part STLs, exact review
approval and requested 3MF, and matches the job's published record. Human edits
therefore invalidate existing releases, even if an old ready status remains.
It does not automatically restart an interrupted worker or orphaned subprocess.

The user will independently add/correct models using their own tools. An editing
screen, a separate editor, and a dedicated human-correction input/processing path
are explicitly outside this workflow's scope; do not implement them. Automatic
inference and joint proposals remain a starting point, not authority to silently
resolve ambiguous joints. Keep image upload/generation, part separation, visual
and motion review, and print preparation. Any geometry change must invalidate the
prior review/export. The implemented restart behavior preserves live workers and
reports interrupted jobs; automatic recovery of orphaned subprocesses is not
provided. Organic wall/attachment strength is not certified by this workflow.
The robot's neck/ankles are still fixed because inference did not expose suitable
spherical junctions. Discrete whole-model tests on the first mechanical revision
found 15–20 degree minimum samples at shoulders/hips and 30 degrees at elbows/knees
in twelve azimuths; these are not continuous-motion or physical-retention proofs.

Integration input `assets/workflow_tests/blue_robot.png` is a deterministic,
non-dinosaur render. Its actual image inference produced a 120 mm closed appearance
mesh (461,290 nondegenerate faces), 12 spherical proposals, eight two-core
junctions and nine preliminary color groups. `audit_workflow_preview.py` checks
the original/inference hashes and compares actual exported triangle multisets,
not just face counts. Later isolated mechanical revisions also exercise closed-part
machining, articulation and headless Bambu slicing; the first sliced robot plate
contains all nine parts, supports, an estimated 7,842 seconds and 43.8 g of filament.

### Holding calibration R2 — C4 selected after physical comparison

The user preferred the four-slot sockets and clarified that the next change is
holding a posed angle, not greater pull-out resistance. Use the thickest R1 ball
stem (3.4 mm), not another thin-stem comparison. No additional mouth relief is
permitted. The original C4_24 rolled profile, nominal 5.4 mm retention aperture,
four 1.2 mm slots and 2 mm wall construction remain; dimensions derived from the
cavity change with it. The 6 mm ball and production joint-v3 are unchanged.

`joint_holding_trial` generates separate H1/H2/H3 socket/key pairs under
`build/joint_holding_R2/`. Cavity diameters are 6.15/6.05/5.95 mm: H1 is the C4_24
fit reference with the thicker stem, H2 reduces diametral clearance by 0.10 mm,
and H3 by another 0.10 mm. H3 intentionally requires 0.025 mm radial accommodation
by the slotted shell. This is a fit experiment, not verified preload/holding torque.
One/two/three matching dimples identify the pairs. Do not force or hammer a ball;
stop on whitening, cracking or permanent spreading. The physical comparison,
including repeated movements and rest time, decides adoption in the body.

The no-relief, 3.4 mm stem deliberately trades away the previous thin-stem 30°
target. Record the actual twelve-direction sweeps and require at least 24° of
extra-stem-interference-free sampled movement. H3's centered spherical overlap
is reported separately and must never be labelled collision-free assembly.
Only the added stem/rim intersection is a motion failure. Require a positive
additional withdrawal barrier; this does not predict pull-out force. CalculiX
compares the ball keys under the existing 1 N side load, not socket plasticity,
friction, holding torque or fatigue. The Bambu output uses the user's A1 mini,
0.4 mm nozzle, white PLA Matte and enabled supports; body files stay unchanged.

### Retention calibration R1 — not integrated into the 120 mm body

Physical user feedback rejected all three old snap coupons: stiff insertion,
loose seating, and an opening that spread during insertion. Existing positive
rigid withdrawal overlap is NOT evidence of elastic recovery or physical holding
force. Old nominal radial play was 0.20/0.30/0.40 mm; radial lip capture was only
0.056/0.050/0.045 mm. Plastic set, damage and print error cannot be distinguished
without examining the physical coupons.

`joint_retention_trial` is a separate, all-printed experiment. It does not change
the production joint-v3, body geometry or material model. W1/W2/W3 split sockets
have 0.05/0.15/0.25 mm cavity clearance and 6 mm balls with 3.4 mm stems. Assemble
halves around the ball and insert two shallow-taper double-dovetail keys from
the mouth end. Keys positively resist half separation; their longitudinal
retention and friction/preload still require a real trial. Do not hammer keys.
Rails deliberately have generous external material for this coupon; integration
and compactness on the anatomy have NOT been approved or checked.

The requested C4_24/C4_28 alternatives have deeper rolled C-section rims, four
radial slots with rounded closed roots, 0.15 mm cavity clearance, and respectively
2.4/2.8 mm stems with 5.4/5.6 mm mouth retention diameters. One/two tactile dimples
pair each C4 socket and ball key; the three-dot ball is for split sockets.
Thinner stems reduce bending strength: test the exact specimens and report CAE
as a linear-static estimate, not printed strength or snap-cycle certification.
Require at least 30 degrees of sampled rigid motion in twelve azimuths for all
five variants, including the split sockets at first ball contact. Verify exported
topology, Bambu toolpaths and fit physically before modifying the body.
Use A1 mini 0.4 mm, white Bambu PLA Matte, stock Textured PEI, support enabled,
0.12 mm layers and slow outer walls for this calibration comparison.

### Palm-size production — revision 1.3.0

The user selected overall length 120 mm, A1 mini stock 0.4 mm nozzle and white
Bambu PLA Matte, with the stock Textured PEI plate. `hybrid_new.palm_size` scales
the accepted August 30 anatomy and finite partition tools, NOT joint-v3 hardware.
The effective parameters are resolved by `hybrid_context.py` and exported in
`build/palm_120/sizing.json` for the viewer and source provenance audit.
The unchanged 6 mm balls, 6.6 mm cavities, 2 mm spherical walls and 1.5 mm cup
height are regenerated. Do not use a slicer-wide scale on the old model.
Anatomy scale accounts for additional neck and tail spacing so assembled length
is 120 mm. Limb translations, shoulder/hip centre offsets and ankle spacing
preserve complete bones instead of thinning them. Target clearance spheres at
neck/tail/ankles are disabled; exact socket cavities remain necessary.
All existing cut-border finishing and preservation checks remain active.
Float64 Boolean geometry is quantized to actual STL coordinates before its
topology check; exactly collapsed or duplicate facets are removed. If float32
quantization still breaks topology, simplify initially within 0.00005 mm (maximum
0.0002 mm) before export. Weld only connected open boundaries wholly within that
span; do not fill larger holes. Require volume change <=0.001 mm3 and the unchanged
independent preservation audit. A 55 C bed override is within Bambu's Textured PEI
guidance; the inherited PLA vitrification warning is retained, never suppressed.
The old 1.2.7 is preserved under `backups/revision_1_2_7_before_palm_size/` and
its original output directory. The palm version has a separate viewer entry.
Physical holding force, layer adhesion and organic wall minimum are not certified
by specimen CAE or the sampled motion check. Material CAE values remain generic
PLA estimates, not measured white Bambu PLA Matte properties.

### Complete rim rounding and local cut-edge finishing — revision 1.2.7

Revision 1.2.6 had a real asymmetric rim defect: selecting circular edges by
length omitted the two quarter arcs created by the revolve seam. Construct
the outer R1 arc analytically in the meridian and revolve it 360 degrees,
then cut the flex slit. No post-cut edge selection is needed. This also avoids
unreliable subsequent CAD intersections from post-Boolean fillet surfaces.
All eight sockets and all three calibration variants must have zero mirrored
CAD difference within 1e-5 mm3 about both transverse planes. The outer mouth
fillet is R1; the 1.5 mm nominal height, 6 mm ball, 6.6 mm cavity and fit stay.

Finish anatomy BEFORE inserting dimensioned hardware. Recognize convex sharp
edges only where they lie on actual finite partition/seam/machining surfaces.
Refine triangles conformingly to 0.4 mm near these borders, fair within a 1.5 mm
compact-support band, and limit each vertex displacement to 0.5 mm. Intersect
the result with the original anatomy: no new material may enter clearance gaps.
The mesh finish is a gradual blend, not a claimed exact constant-radius fillet.
It is not a global smoothing/remeshing of the image-derived skeleton.

An independent seam tube clips the finishing subtraction; every whole cutter
triangle is conservatively certified within 2.1 mm of an actual cut border.
Stored pre-finish anatomy and seam records support revalidation. The preservation
audit admits only these bounded finishing tools in addition to existing cuts.
Internal finishing tools use float64 NPZ, not float32 STL, so their very thin
diagnostic faces survive serialization. Final printable parts still use STL/3MF
and are validated independently after loading those actual files.
Torso-owned hip rings remain on the torso; only their cut-border allowance is
exempted, not their entire shape. Both arms and legs use identical finishing
parameters; source asymmetry is retained. This does not change their placement.

Run topology, 36-pair collision, motion, socket fit/symmetry and specimen CAE
checks again. The old 1.2.4 sliced files remain stale. Physical finish, minimum
organic wall thickness, pull-out force and fatigue still need print testing.
The 1.2.6 geometry is backed up in `backups/revision_1_2_6_before_edge_finish/`.

### Exterior socket height and neck/tail cleanup — revision 1.2.6

The previous 1.2.5 operation relieved the inner mouth only: the visible exterior
height was unchanged. The user clarified that the actual cup height must be
reduced. Trim the complete mouth to 1.5 mm forward of the nominal ball centre
(previously 2.811 mm), then round the two outer mouth arcs with R1. The inner
chamfer remains. The cup's final exterior is used for all eight joints and the
calibration strip. This is not merely a viewer change.

Calibration mouth heights are derived as sqrt(ri^2 - ri_nominal^2 + h_nominal^2)
so changing the cavity clearance does not unintentionally eliminate capture at
the cutting plane. Their fronts are approximately 1.265/1.500/1.709 mm and their
sampled apertures approximately 5.888/5.899/5.911 mm for 0.4/0.6/0.8 mm cavity
clearances. These are CAD values, not physical holding-force guarantees. The
remaining rim is locally thinner than the untouched 2 mm spherical wall.

Remove the original image-derived neck bulb from the TORSO before adding new
hardware, using a finite R1 box X=-70..-55.5, Y=-10..10, Z=73..91 mm. The neck
target clearance sphere is disabled so it cannot erase neighbouring vertebrae;
the exact socket cavity is still necessary. Move the neck centre and entire
head +4.5 mm in X toward the body, from (-63,0,82) to (-58.5,0,82). Move its head
support by the same amount and anchor the torso support at (-53,0,82).
The original partition plane remains unchanged. Source-preservation checks
invert the head translation and allow only the named local trim/cavity tools.

Expand only the annotated first upper tail-root relief, within X=0..10.5,
Y=-6.5..6.5, Z=54.8..68 mm, sloping from lower-front X=9.8 to upper-front X=10.5
with R1 edges. No blanket cuts through the spine or limbs are permitted.
The shoulder/hip centres, limb placement, ball diameter and cavity clearance
are unchanged. Prior geometry is backed up under
`backups/revision_1_2_5_before_neck_tail_height/`.

Viewer loading now records SHA-256 digests of the actual fetched STL bytes on
the canvas for verification against disk, and identifies the revision in the
existing model selector. No new UI panel is added. Reloading is required after
geometry rebuilds; an already open view does not automatically replace meshes.

### Circumferential removable socket relief — revision 1.2.5

The user prefers hand-removable joints, not a hard snap. All eight sockets now
have a rotationally symmetric inner-mouth chamfer, generated from the envelope
of the 3.4 mm neck tilted by 30 degrees. This trims the entire circumference;
the proposed four directional notches were withdrawn and are NOT production.
The historical 1 mm flex slit remains. The exterior R1 profile, cavity diameter
6.6 mm, ball 6 mm, joint-v3, anatomy and all placements are unchanged.
Only socket hardware is trimmed; historical anatomy cutters stay unchanged.

`joint.socket_profile.circumferential_relief.angle_deg=30` and the standalone
required motion target is 30 degrees. Positive/negative pitch/yaw and two
diagonal sweeps are checked. Full assembly movement can still stop earlier on
the anatomy. A 35-degree full-circle trial removed the rigid withdrawal barrier
entirely, so it was not adopted. No physical pull-out force is predicted.

The 5.8 mm retention parameter now describes the PRE-TRIM profile. The sampled
finished nominal opening is approximately 5.828 mm; the nominal radial capture
is approximately 0.086 mm. The outer spherical wall remains 2 mm, but the rim
is intentionally locally relieved. Calibration variants 0.4/0.6/0.8 mm have
slightly different final mouths after the identical chamfer; report them rather
than claiming their final openings are identical. Evaluate easy removal versus
unwanted release with newly generated coupons and final-part print orientations.

Revision 1.2.4 geometry is preserved under
`backups/revision_1_2_4_before_stem_reliefs/`. Its `build/print_ready/` slicer files
remain explicitly versioned 1.2.4 and must not be mistaken for this new geometry.
The printer is confirmed as A1 mini with stock 0.4 mm nozzle; filament and plate
are not yet confirmed. New 1.2.5 model/print-layout exports require reslicing.

### Rounded shallow sockets — revision 1.2.4

All eight sockets use a constant 2 mm spherical wall and a tangent R1 rounded
rim instead of the long spherical/conical mouth. The nominal front reach from
the ball centre is 2.811 mm (formerly 3.788 mm, measured from tessellation).
Joint-v3, ball 6 mm, cavity 6.6 mm and diametral clearance 0.6 mm are unchanged.
The new `joint.socket_profile.retention_diameter_mm=5.8` is the actual narrow
opening, independent of cavity clearance; old `throat_diameter_mm=5.2` remains
only for the historical cone profile. A 1 mm relief slot allows elastic opening.

The profile is shared with the calibration sockets. Their diametral clearances
are 0.4/0.6/0.8 mm, each with the same 5.8 mm capture opening and 2 mm wall;
outer diameter therefore changes with clearance for those test variants.
The baseline shallow joint passes 25-degree pitch/yaw rigid-interference checks.
`validate_socket_fit.py` checks clear seating and sampled withdrawal barriers,
including transverse offsets across the nominal radial play. These are not
snap-force, fatigue, wear or preload simulations. The 0.6 mm diametral fit still
permits nominal 0.3 mm radial play and must not be called wobble-free.

Only the added hybrid socket shell changes. Source anatomy is cut with the
unchanged historical cavity tools before the new shell is united. Preservation
audits allow only those historical anatomy cutters; no new socket-lip cutter
may widen cuts into bones or torso-owned hip rims. All part placements, centres,
balls/studs and the previous small tail relief remain unchanged. Direct torso
attachment is measured using the actual standalone shallow shell, excluding
its bridge. Revision 1.2.3 is backed up before regeneration.

Print `build/print/starter_fit_kit.3mf` using the final printer, material and
settings. One/two/three dots identify the 0.4/0.6/0.8 mm variants. Assess seating,
free play, angular motion, manual pull-out resistance and repeated cycles before
choosing a clearance; the production setting is not changed automatically.

### Interactive motion review — viewer 3.4.0

The current August 30 nine-part assembly can be articulated in the browser.
Eight ball centres and mouth directions are read from `hybrid_new` in
`config/parameters.json`. Rigid display transforms rotate each movable part
about its actual fitted centre; feet inherit their leg transforms before their
own ankle rotation. Torso, jaw, knees and intermediate tail remain rigid.
The torso is the fixed parent of head, arms, legs and tail. Recursive resolution
preserves local joint angles and foot attachment regardless of definition order.
There is no torso rotation control.
Drag a movable part to move it, Shift-drag to twist, and drag torso/background or Alt-drag
to orbit. Middle-button drag pans in the rolled camera plane, while a middle-button
double-click restores the original fitted view. Arrow keys fine-tune the selected joint, Home resets it, and Escape
resets all joints independently of the camera. Other models do not articulate.
Part gestures lock their mode at pointer-down: the inner projected-bounds ring
bends; the outer portion uses angular movement around that screen-space centre
to change local twist. Shift always selects linear twist. The ring is a gesture
guide, not the physical joint pivot, and disappears on release/cancellation.
Left-button camera gestures starting outside normalized radius 0.72 roll the view; inside
they orbit. Two-finger angle changes roll while distance changes zoom. Rendering
and picking share the rolled up-vector. Camera reset clears roll as well.
The model occupies the full viewport. Part coloring is permanent. No legend,
part-name list, color switch, joint panel, sliders or reset cards are present.
The compact header retains only model selection, contextual workflow actions and camera reset.
A single bottom-line readout identifies the selected part and its three joint
angles, with the initial pose at zero and ankles relative to their parent legs.
Readouts commit with the displayed, tested pose rather than queued input.
All parts are always opaque, including during selection, dragging and camera
gestures. The red collision overlay remains fully opaque. The torso readout is
labelled fixed; other models hide the readout. Camera orbit leaves all eight
joint poses and their collision results unchanged.

A dedicated worker builds triangle BVHs and tests sampled surface vertices and
centroids against the other posed meshes, in both directions for all 36 pairs.
Red point overlays localize sampled penetrations, including hidden regions. For
each actual mating parent/child pair, samples inside the configured ball radius
plus the STL clearance sampling tolerance at the fitted ball centre are omitted
because the selected S3 preload intentionally makes
the ball and socket overlap. Samples beyond that sphere are retained, so ball-stem
contact with the socket/anatomy and every collision with a non-mating part remain visible;
one compact top banner names colliding pairs only when collision is detected.
There is no normal-state collision card or permanent pivot marker.
One worker check runs immediately while input replaces a single latest-pose
queue. Every completed check commits its tested pose and red overlay atomically,
even while the pointer remains down. This replaces the former 100 ms debounce
and latest-revision-only acceptance, which could starve updates during a drag.
Unchanged pairs reuse cached full-density results; changed pairs are recalculated
without reducing the sample density. Cache keys include both world transforms,
so inherited foot movement and reset invalidate the relevant entries.
Measured incremental medians on the development machine are approximately 5 ms
for the tail, 19 ms for a hip, 49 ms for a shoulder and 10 ms for an ankle;
initial preparation and initial all-pair checks are slower. These are measured
examples, not hardware-independent frame-rate promises. Errors are shown via
the loading/error message, never as a false clear result. Old-model results
are rejected after model changes.
This approximately 8,000-sample-per-part test may miss small/thin intersections;
it is not an exact Boolean, continuous collision test, contact simulation or
physical fit guarantee. The +/-60 degree controls are an exploration range,
not a verified range of motion. The assembly's neutral pose is tested clear;
35-degree upward tail pitch is a regression case for torso/tail penetration.

The right-side snapshot rail contains a permanent front/neutral card and locally
saved image cards. Each saved card records the collision-tested joint pose and
the current camera orientation, roll, zoom and normalized pan. It can be added,
restored or deleted without modifying geometry or print exports. Restore matches
joint names first, then stable moving-part names, then the nearest compatible
parent joint; unmatched new joints return to zero. This preserves as much of an
older pose as possible after joint definitions change. Camera values are stored
relative to the model bounds so a resized revision retains a comparable view.
Snapshots remain in browser-local storage and never leave the local viewer.

No geometry, dimensions, print exports or material properties change. No
production build or CAE rerun is required for this viewer-only update. The older
simple-viewer and boundary-lab descriptions below are historical, not the current
feature list.

### Current jointed assembly — revision 1.2.3

Apply the one-sided review symmetrically. Shoulder socket centres retract from
Y=+/-20 to +/-16 mm; hips retract from +/-23 to +/-17 mm. Each socket shell
must intersect the original torso by at least 1 mm3, independently of its
bridge. The 6 mm balls and 0.6 mm diametral fit are unchanged.

Arm placements are now (-2.5,+/-8,0) mm relative to the source: 4 mm inward
from 1.2.2 and 2.5 mm forward. The standard stud endpoint is embedded in the
original upper arm, so the extra capsule support (the visible T-shaped root)
is omitted. No arm anatomy is subtracted. Legs/feet use (0,+/-8,0), 6 mm inward
from 1.2.2, and ankle centres follow to Y=+/-24 mm. Decorative hip rims remain
on the torso and must retain their full reference volume.

Only the annotated first upper tail-root projection gets a new relief. A
FreeCAD-authored filleted wedge is bounded by X=0..7.4, Y=-5.5..5.5,
Z=54.3..65.5 mm, with its sloped front limit rising from X=4.5 at the bottom
to X=7.4 at the top. Cutter edge radius is 1 mm. The slope preserves attachment
of the remaining projection, unlike a rectangular pocket. The relief is
applied only to the tail; its exact solid is the sole new subtraction allowed
by the anatomy audit. Existing neck/tail/ankle joint cavities remain unchanged.
Tail pitch is sampled from -15 to +15 degrees in 2.5-degree steps; previous
shoulder/hip and other joint checks remain. These are discrete rigid-interference
checks, not guaranteed continuous movement or physical fit/strength tests.

### Current jointed assembly — revision 1.2.2

The decorative outer hip rims belong to the torso, not the moving legs. A
0.4 mm finite seam at (-11, +/-17, 50), normal X and radius 5 mm, separates
each rim from its leg. The intact rim is united with the torso using a hidden
inward lap of 1.4 mm (the former 1.2 mm partition gap plus 0.2 mm overlap).
Both rim reference solids are checked for complete inclusion in the torso.

The original partition centres are now independent of the mechanical centres.
Arms translate 12 mm outwards; legs and their feet translate 14 mm outwards.
Shoulder joint centres move from Y=+/-12 to +/-20 mm; hip centres move from
Y=+/-13 to +/-23 mm. Ankle centres follow the legs from Y=+/-16 to +/-30 mm.
All X/Z centres, the 6 mm ball and 0.6 mm diametral fit remain unchanged.
These are actual assembly placements, not an exploded-view display trick.

Shoulder/hip source and target motion-clearance spheres are disabled: move
the parts apart rather than thinning the anatomical bones. Socket cavities
remain necessary. Neck, tail and ankle machining retain their previous design.
The source-to-partition check exempts only the exact finite cutting discs,
not broad surrounding spheres, and inverses the rigid translations. Each raw
part is then checked against its final solid; removed volume may lie only
inside enabled machining tools. Arms have no allowed subtractive tools.
The motion review adds shoulder/hip outward spreading at 0/5/10/15 degrees;
the previous directional 5-degree samples remain. No continuous-motion or
whole-animal strength guarantee is implied.

### Current jointed assembly — revision 1.2.1

Revision 1.2.0 was rejected: its global neck plane clipped fingers, its leg box
clipped toes, and lateral hip planes shaved entire leg sides. Its mechanical
checks did not verify preservation and must not be interpreted as visual approval.
Revision 1.2.1 reconstructs all parts from the untouched August 30 mesh. It uses
finite joint-local disc cuts and connected-component assignment, not boxes or
whole-model planes. A source-preservation test is now mandatory in the build.
Every original surface vertex outside the finite joint machining envelopes is
required to remain on/in the assembly; every raw part is also tested against its
own finished part. Surface vertices buried by additive supports are reported
separately from removed geometry. Matched enlarged views show hands, feet and
inner legs before machining and after repair.

Cut disc radii in mm: neck 10, shoulders 9, hips 14, ankles 10, tail 12.
Disc thickness remains 1.2 mm. The tail disc is at X=3, one mm behind the joint
centre along its negative axis, to avoid grazing detached ornaments.
Head support anchor changes from (-71,0,83) in a skull cavity to (-72,0,91)
in solid roof material; this prevents the neck stud being a detached component.
Partitioning must produce exactly nine components and discard none.
Post-Boolean cleanup allows only fragments <=0.001 mm³ wholly inside a joint-local
envelope; the former 200/600 mm³ generic debris filtering is disabled.
The old box parameters remain for historical compatibility but are inactive.

The user approved joint processing of the new August 30 inference. Active
production now uses `hybrid_new` as an overlay of the preserved `hybrid` settings.
Outputs are in `build/hybrid_20260830/`; old `build/hybrid/` outputs are retained.
The viewer defaults to the NEW jointed assembly, with new parts, raw reference
and explicitly labelled historical models available separately.

New joint centres in mm are neck (-63,0,82), shoulders (-47,±12,64.5),
hips (-15,±13,55.5), ankles (-15,±16,14), tail (4,0,49).
Nine connected mesh parts carry eight FreeCAD-authored ball/socket connections.
The jaw, knees and intermediate tail remain fixed. Joint v3, ball 6 mm,
socket 6.6 mm and diametral clearance 0.6 mm remain unchanged.
Anatomy partition clearance is 1.2 mm, independent of ball/socket fit.
Clearance is restricted to the finite joint discs, never extended along a limb.

Validation covers all 36 static pairs and one joint at a time against every
other part at the configured discrete directions up to 5 degrees; feet follow
hip movement. It does not prove continuous or simultaneous motion.
Organic body FCStd documents contain meshes; exact joint tool solids are also
exported to `joint_tools.FCStd` and `joint_tools.step`.
CalculiX tests the standard bone and ball-stud specimens, not the new organic
supports, whole animal or socket contact. Image-derived walls and sharp tips
require physical/manufacturing review; this is an unqualified prototype.

### New appearance inference provenance — 2026-08-30

The unprocessed image-to-3D reference is separately stored at
`build/generated_appearance/20260830_dfba1098/trex_new_200mm.stl`.
It was inferred from the newly supplied `4e7dd74e-032a-4974-859c-590aaa02d1dd.png`
on 2026-08-30, with original/input/output hashes and UTC timestamps recorded.
This raw STL remains an appearance-only reference. Joint centres and cuts for
the processed assembly above were re-derived from its anatomy, not copied from
the old August 21 model. The historical `hybrid` outputs below still use the old
source and must not be cited as mechanical validation of the new assembly.

The following paragraphs document the earlier production workflow.

Revision 1.1.2 refines the production joint-tool mesh to 0.025 mm linear and
0.10 rad angular deflection. Matching precision is used for the standalone joint
and starter fit kit. These are CAD-to-mesh settings, not guaranteed printer
accuracy. The 6 mm ball, 6.6 mm socket, 2 mm radial wall, 1 mm flex slot and
all anatomical joint centres are unchanged. Viewer 2.1.0 additionally exposes
the standalone joint, calibration sockets and ball key. An allowlisted `model`
query parameter can open a specific model without changing the default below.

The active viewer is now read-only (viewer 2.0.0). It loads one STL at a time,
supports model selection, drag orbit, wheel/two-finger zoom and fit-to-view.
It starts with the uncut appearance model. There are no cut, sculpt, annotation,
joint-placement, collision or storage controls in the viewer. The corresponding
editor code and helper modules were removed at the user's request. Production
geometry, printer exports and existing browser-owned data were not deleted.

The modelling/build pipeline remains available separately:
concept image → appearance mesh → CAD/mesh generation → topology, collision,
CAE and physical review. The production outputs and earlier design decisions below
are historical modelling context, not features of the current simple viewer.

## Hybrid production outputs — revision 1.1.1

- FreeCAD review assembly: `build/hybrid/SkeleCAD_Hybrid_Assembly.FCStd`
- FreeCAD print layout: `build/hybrid/SkeleCAD_Hybrid_Print_Plate.FCStd`
- Individual printable files: `build/hybrid/parts/*.stl` and `*.3mf`
- Combined print plate: `build/hybrid/print/trex_hybrid_full_print_plate.3mf`
- Eight detail-first motion sweeps: direction-specific movement up to 5 degrees
- Fixed one-piece head: no jaw cut, hinge lugs, hole or removable pin
- Static assembly: all 36 unique part pairs checked for volume overlap

## Joint placement — revision 1.1.1

Viewer connector guides respect anatomy depth instead of being painted over all
surfaces. Cyan socket and yellow ball markers link each connector centre to the
nearest triangle point on its own part. These dashed lines and rings are explicit
mounting references, not support rods or proven physical joins. An owner-labelled
readout distinguishes centres inside anatomy from centre-to-surface distance.
Anchors follow part poses and update on connector relocation/sculpting; no mesh,
connector placement, joint dimensions or collision geometry is changed by them.

- Head: fixed one-piece image-to-3D form with a naturally open mouth.
- Neck: head side is male; torso side is socketed.
- Shoulders: both complete arm parts are male; the torso carries both sockets.
- Hips: both upper-leg parts are male; the torso carries both sockets.
- Tail: the complete tail is male; the torso carries the root socket.
- Ankles: both distal foot parts are male; the upper legs carry the sockets.

The socket has a 2.0 mm radial wall, a 1.0 mm flex slot, and a flared mouth.
Revision 1.1.0 deliberately keeps the organic belly, proximal leg and tail-root
geometry as natural articulation stops instead of excavating a full motion sphere.
The shoulder and hip ball centres sit 3 mm inside the appearance partition so the
original proximal limb silhouettes remain visible. Short 2.2 mm-radius shoulder
and 3.0 mm-radius hip buttresses replace exposed rod-like supports without changing
the 6 mm mating ball.

Joint placement starts from the unpartitioned outward-normal appearance model
in the browser viewer. The generated production assembly is the nine-part,
eight-joint result of the approved annotations.

The browser boundary lab is the working loop for tentative cutting, tentative
joint placement and range-of-motion review. Clicking anatomy selects that side;
dragging the selected anatomy rotates it about the provisional joint centre,
while dragging empty background rotates the camera. Two labelled X/Y/Z gizmos
are shown for the selected side: the body-centred gizmo translates the body and
its owned connector together, and the connector-centred gizmo translates only
that connector relative to its body. The opposite side stays unchanged. The
two independent placement guides are a bare ball and a hollow
socket cup, with no stem, bridge or attachment mass. Their diameters come from
config/parameters.json. The cup is a placement envelope, not the final slotted
printable socket. Raw split anatomy has no old integrated joint supports.

Connector-only relocation changes only the selected attachment transform;
neither nearby mesh vertices nor the posed world coordinates of either body
are changed. Each side has its own pivot while detached. The ball is attached by transform to its male-side
part and the cup to its socket-side part, so each follows its owner during part
manipulation. The reconnect action translates the selected body and connector
to coincide with the opposite connector centre, preserving both edited local
mounting positions, orientations, and the opposite body's pose. A separation
readout distinguishes detached placement from coincident-centre motion review.
Subsequent articulation stays about the fitted centre. Pivot relocation preserves
already-posed body transforms. No
automatic joint union, cavity cut, joint-to-body blending, support or embedding is performed; the
user decides how to integrate the guides with the anatomy during later remodeling.

Only sampled penetration regions are drawn in red, never the entire selected
part. A separate status indicator reports sampled anatomy-to-anatomy overlap;
intentional guide embedding is not treated as an anatomy collision. Both sides are tested
against the other mesh, but this interactive sampling is not an exact Boolean
collision guarantee. Temporary clay-like add/remove edits reserve the boundary
volume before detailed remodeling. Browser edits remain temporary review state;
approved values are transferred into the parametric production model afterward.

Every male side uses the joint-v3 profile: a 6.0 mm ball and a straight 3.4 mm
diameter stem extending 3.8 mm beyond the ball surface. Legacy `*_v2` output
filenames remain stable, but their generated metadata identifies joint version 3.
Internal supports are short local buttresses rather than long replacement rods.

The build checks only the anatomy-compatible directions, up to 5 degrees. The
shoulders and hips use outward yaw only; their preserved proximal bone mass is an
intentional pitch stop. The preserved belly and tail root are also articulation
stops. There is no independent jaw motion.

## Tyrannosaur part family — revision 1.1.0

- Fixed one-piece head with rear neck ball
- Single torso with neck, shoulder, hip and tail sockets
- Separate left and right arms with shoulder balls
- Separate left and right upper legs with hip balls and ankle sockets
- Separate left and right foot parts with ankle balls
- Single tail with a root ball
- joint-v3 socket strip and 6 mm ball test key for printer calibration
- Nine-piece bipedal T. rex assembly with eight annotated connections

## Visual-reference alignment — revision 0.6.0

The supplied concept sheet is used for silhouette, visual mass, and skeletal
detail density only. Its illustrated ball and socket locations are deliberately
not copied. Revision 0.6.0 instead uses the independently validated joint centers
described above.

The concept's stated 200 x 90 mm envelope has an aspect ratio of about 2.22.
The current posed CAD envelope is 228.3 x 98.0 mm, an aspect ratio of about 2.33.
The remaining offset preserves a functional counterbalancing tail. Compared with
revision 0.5.0, the head is deeper and more fenestrated, the seven-rib cage is
denser, the shoulder and pelvis are heavier, the limbs have enlarged joint ends,
and the tail has a much denser tapered vertebral rhythm.

## CAE baseline

The automated baseline is a CalculiX static cantilever calculation using the
configured PLA properties and a rectangular equivalent of the long bone shaft.
It verifies solver availability and gives an early stiffness/stress trend. It is
not yet a detailed socket-contact or impact analysis.

## Image-to-3D appearance reference — revision 0.8

The concept sheet now drives appearance through the local, shape-only Tencent
Hunyuan3D 2.1 model. Text, diagrams, connector annotations, the white page, and
the floor shadow are removed before generation. The accepted reference is
`build/generated_appearance/trex_hunyuan_v2_clean.glb`. It is a 200 mm-long,
watertight appearance mesh with the generated debris removed; the FreeCAD review
document is `build/generated_appearance/trex_image_to_3d_reference.FCStd`.

The generated mesh is not the dimensional authority for ball joints. FreeCAD
joint-v3 solids cut and add the final 6 mm balls, sockets and flex slots. The
head itself remains the accepted generated one-piece form, including its fixed
open mouth. The concept sheet's illustrated connector locations remain ignored.

## Marker-constrained partition review

Before marker review, an image-generated appearance may be made exactly
bilaterally symmetric across the YZ plane. The reviewer chooses the left or
right half as authoritative; the closed solid is clipped at `x=0`, that half is
reflected, and the two halves are Boolean-welded at the centre plane. The two
independently inferred sides are never averaged, so joint-like features cannot
retain a small left/right positional drift. The original `appearance.stl`, its
manifest, and the previous partition revision are integrity-hashed and retained.
Restoring returns all three together. A failed clip, weld, STL round-trip, or
symmetry audit is a hard error and leaves the currently published appearance
unchanged.

Image-workflow partitioning is an explicit review gate between appearance
generation and exact joint machining. Automatic spherical proposals are shown as
markers on the unchanged source mesh. Every visible marker is used; reviewers
remove unwanted markers, add several approximate regions on the surface, and
adjust each region radius. A marker can be promoted to a persisted bilateral
pair when a matching reflected surface exists. Paired markers use a distinct
colour and deleting either member deletes the pair.

Mechanical joint axes follow the same symmetry intent as the reviewed markers.
A marker snapped to the central ZY plane receives a collinear socket bridge and
ball stem whose axis remains inside that plane, preventing neck and tail
connections from drifting diagonally to either side. A bilateral marker pair
uses exactly mirrored axes and axis-aligned embedded anatomy anchors rather than
two independently tilted nearest-surface attachments. If the initially
constrained axis misses either anatomy part, the marker centre remains fixed and
the smallest valid rotation is selected while preserving the centre-plane or
bilateral-mirror constraint.

Joint-axis placement batches exact ray/triangle intersections and retains the
configured 0.1 mm anchor grid. A 15 degree probe bounds a subsequent 5 degree
search; the accepted result is still the earliest valid direction on the full
5 degree grid. A failed or inconsistent ray query is a marker-numbered hard
error. It is never replaced by the former repeated point-sampling algorithm.

Successful mechanical revisions retain integrity-hashed intermediate geometry.
On a later marker edit, cut components are reused only when their complete raw
mesh and adjacent cutter identities are unchanged. Joint axes are reused only
when the marker identity and exact triangle geometry throughout the entire
maximum 18 mm search neighbourhood are unchanged; remote geometry outside that
conservative neighbourhood is not a dependency. Every cached anchor is checked
again against the current closed anatomy. Cache corruption or a failed
revalidation is a hard error. Final global topology, source preservation,
socket-interior intrusion and pairwise collision audits always run, including
for reused regions.

Cut-edge finishing uses one declared strength, and arbitrary-model STL export
uses one declared quantization tolerance. Either stage stops with the affected
part and diagnostics rather than retrying with weaker finishing or a coarser STL.

Exterior socket shells and joint stems are allowed to overlap other joint
hardware without moving the reviewed centre or axis, and are not trimmed merely
to make their outside surfaces disjoint. Exact machining still rejects foreign
  solids inside the spherical ball cavity, plus any overlap that
  includes non-hardware anatomy. The diagnostic records allowed exterior hardware
  overlap separately from functional interior intrusion.
  The four open flex slots and the throat/tool extension are not treated as the
  ball cavity, so a stem or outer shell crossing those construction volumes does
  not create a false interior-collision result.
  The owning CAD socket and intended CAD ball are subtracted from this audit so
  STL tessellation differences at their designed cavity boundary are not
  mistaken for foreign intrusion.
Boolean operations may emit an inverted disconnected fragment below the same
configured volume tolerance when two exterior hardware shells graze. Such a
fragment is discarded and recorded; any detached component above tolerance is
still a hard failure.

Only the remaining visible marker envelopes are permitted to disconnect the
face-adjacency graph. Every other automatic boundary is ignored and its regions are merged. The
preview then assigns every original face exactly once by geodesic distance from
the surviving cores. Preview parts are open surface labels and are never described
as printable solids. The closed `appearance.stl` remains the dimensional input to
the later FreeCAD Boolean stage, and every preview revision records the source
manifest hash. P3-SAM is not yet a production dependency; its future face labels
must obey the same selected-marker-only merge policy before they can be displayed.

## Image-generation progress

The selected image job exposes a display-only progress summary while preparing,
generating or analysing. It combines the configured RTX 3060 phase estimates
with the most recent bounded Hunyuan counters for diffusion sampling and volume
decoding. The viewer shows phase, percentage, elapsed time and approximate time
remaining. It is an estimate rather than a completion guarantee; model loading,
GPU contention and mesh complexity can change the final duration. Raw logs and
paths remain private to the per-job directory.
The progress card provides a pause/resume icon, and the upper-right header shows
a stop icon while initial image inference is queued or running. Pause suspends
the verified worker process tree and keeps its GPU memory allocated; it is for a
short interruption and cannot survive an app or PC shutdown. Stop terminates the
complete worker tree and deletes that job directory, including its uploaded
source image and partial outputs. A stopped image must be uploaded and generated
again from the beginning. These controls do not affect partitioning, joint
machining or print preparation.

Generated-mesh normalization removes only disconnected components that are below
both `debris_cleanup.minimum_component_faces` and the configured fraction of the
total surface area. The largest component is always retained, as are all major
detached components. Cleanup occurs before centering and scaling so remote debris
cannot shrink the subject's final 120 mm envelope. The manifest records removed
component, face, area and volume totals for review.
