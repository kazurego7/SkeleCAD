# Changelog

## 起動環境の整理（2026-09-05）

- ルートの `start.ps1` で、Python環境・依存・Hunyuan形状ソースとモデルの準備から起動まで実行。
- FreeCADの標準インストール先を検索し、非公開の `toolchain.local.json` で個別のアプリ配置に対応。
- OrcaSlicerの設定・環境検査・旧専用印刷経路を削除。現行処理が使う3MF検査は `print_package_audit.py` に分離。
- CPU環境の未使用8パッケージを削除。Hunyuan上流が読み込む推論側依存は維持。
- 外部依存の利用条件をREADMEと起動時に明記。独自コードのMITを取得物に適用するものではない。
- 形状・印刷方向・寸法・材料の変更なし。


## 2026-09-05 - Mirror-symmetric workflow socket slits

- Orient C4 socket slits using the symmetry plane normal projected into the
  socket cross-section. Bilateral sockets now mirror their slit positions;
  centre-plane sockets have reflection-symmetric slits.
- Preserve joint centres, axes, ball/cavity dimensions, slit width and depth,
  and print orientation. Retention remains subject to physical verification.
- Validate exact shell reflection on the user's Pteranodon: two bilateral pairs
  and two centre sockets have zero Boolean volume difference after reflection.
- Rebuild the current image job as a new mechanical revision, retaining prior
  revisions. Do not reuse old print approvals or print files for new geometry.

## 2026-09-05 - Hunyuan inference dependency update validated

- Validate unchanged Hunyuan3D 2.1 source with Python 3.14.7, PyTorch 2.14/CUDA
  13.2, Transformers 5.16.1 and Diffusers 0.40.0 using real shape inference.
- Adopt the new inference environment and freeze its 66 dependencies; preserve
  the prior environment and record manual rollback paths in toolchain settings.
- The robot fixture completes with a closed postprocessed mesh and a -0.04465%
  volume difference from the baseline. Existing models and parameters are unchanged.
- See `HUNYUAN_UPDATE.md` for reproduction, scope and comparison results.

## 2026-09-05 - Toolchain and dependency refresh

- Move CPU workflow processing to Python 3.14.7 with pinned current libraries;
  retain the upstream-compatible Hunyuan/CUDA inference environment separately.
- Update Blender to 5.2.1 LTS, Gmsh to 4.15.2 and CalculiX to 2.23.
- Resolve launcher, workflow worker and solver paths from toolchain configuration.
- Open the configured palm-size assembly and selected slicer, with the current
  production fit trial; refresh startup and persistence documentation.
- Geometry parameters and joint-v3 compatibility are unchanged.
- See `DEPENDENCY_UPDATE.md` for versions, sources, retained dependencies and QA.

## 2026-09-03 - Distinct centre-plane marker colour

- Display markers created on the YZ centre plane in purple and label them
  `中央面`; markers left on one side after symmetry removal remain green and
  are labelled `片側`. Bilateral markers retain their shared blue style.

## 2026-09-03 - Image generation pause and stop controls

- Add a pause/resume icon beside image-generation progress and a stop icon in
  the upper-right header while initial image inference is queued or running.
- Keep the pause/resume control pointer-enabled inside the otherwise
  click-through progress overlay so the visible button is operable.
- Suspend and resume the verified worker process tree without discarding GPU
  state, and freeze elapsed progress while paused.
- Make stop terminate the complete worker tree and remove the job directory,
  including the uploaded source image and partial generation outputs.

## 2026-09-03 - Pose and viewpoint snapshots

- Add an image-based right-side snapshot rail to articulated models, with a
  permanent front/neutral state and add, restore and delete actions.
- Store the collision-tested joint angles together with normalized camera pan,
  orbit, roll and zoom in browser-local storage.
- Restore changed joint sets by joint name, moving-part identity and nearest
  compatible parent, leaving newly introduced joints at neutral.
- Prevent snapshot thumbnails from starting a native image drag, so an
  accidental card drag cannot enter the image-to-3D upload workflow.
- Keep saved cards in creation order, appending each new snapshot below the
  existing cards while leaving the add card at the bottom.
- Replace the header add button with an icon-only camera card at the bottom of
  the list, remove the rail heading and card wording, and pin each delete icon
  to the card's upper-right corner.
- Add a brief reduced-motion-aware camera flash when saving, remove all visible
  card labels, and distinguish the permanent front card using a blue
  double-frame treatment.
- Fix the front card first and the camera card second, show saved snapshots
  newest-first, and persist drag-and-drop reordering of saved cards.
- Hide the redundant header reset button while the snapshot rail is available.
- Reserve scrollbar space at all times so adding enough snapshots to overflow
  the rail never changes the card width.
- Accept drops in the empty rail area as a move to the end and auto-scroll near
  the rail edges, making the true last position reachable while dragging.
- Treat drops on either fixed top card as a move to the first saved position,
  so the top end of the reorder range is equally reachable.

## 2026-09-03 - Exact accelerated joint machining

- Replace repeated per-angle 0.1 mm point sampling with batched ray/triangle
  intersections while retaining the 0.1 mm anchor grid and final point-in-solid
  verification.
- Add a 15 degree coarse probe that bounds the unchanged 5 degree ordered
  search; the selected axis remains the first valid full-resolution candidate.
- Reuse integrity-hashed cut-edge finishing and joint-axis results only when
  their complete or conservative local geometry dependencies are unchanged.
  Remote changes cannot invalidate a cached joint, while changed adjacent
  cutters always force recalculation.
- Keep topology, anatomy preservation, socket-interior intrusion and global
  collision audits unconditional. Ray failures and cache inconsistencies stop
  with explicit marker diagnostics; there is no alternate-algorithm fallback.
- Remove the remaining arbitrary-model geometry fallbacks: cut-edge finishing
  no longer retries weaker strengths, STL export no longer doubles its
  quantization tolerance, and malformed completed caches are reported.
- Record per-stage elapsed time and cache reuse counts in each successful
  mechanical revision.

## 2026-09-03 - Direct and visible print preparation

- Keep the completed header minimal: once preparation succeeds, hide the
  completion badge and download action and present only the `プリント` action.
- Keep automatic tree supports enabled by default for every production print
  preparation, audit the support clearances and interface layers in both the
  input and sliced 3MF.
- Remove the print-preparation confirmation dialog. A collision-free reviewed
  pose is submitted immediately when the reviewer presses the preparation
  button; this still creates files only and never starts a printer.
- Show preparation in progress, completion, and failure beside the header
  controls. On completion, replace the subtle link with a labelled print-file
  download button.
- Add a completion-only `プリント` action that opens Bambu Studio. The loopback server
  revalidates the current released 3MF files and starts the locally installed
  Bambu Studio with those exact files; it never sends a job to a printer.
- Fail the viewer server immediately with an actionable message when it is
  started outside the bundled modelling Python, instead of dropping the first
  print-preparation request with a network error.

## 2026-09-03 - Symmetry-constrained image-workflow joint axes

- Make central ZY-plane neck, tail and similar connections collinear through the
  socket centre instead of allowing independently selected anatomy anchors to
  pull the bridge or ball stem diagonally left or right.
- Give bilateral marker pairs mirrored joint axes and find both embedded anatomy
  anchors along those constrained axes. The two sides therefore remain mirror
  counterparts even when the generated surface tessellation differs slightly.
- Stop trimming or redirecting joints merely because socket shells or stems
  overlap externally. Record those contacts as allowed, while still rejecting
  foreign solids inside the spherical ball cavity and non-hardware
  anatomy collisions.
- Export the spherical cavity separately from the larger cavity-plus-flex-slot
  cutting tool, preventing stems in an open throat or slot from being reported
  as internal socket interference.
- Exclude the owning CAD socket and intended CAD ball from cavity-intrusion
  measurements, leaving only added anatomy or foreign-part material.
- Remove and record only disconnected Boolean fragments below the configured
  volume tolerance; any meaningful detached joint or anatomy remains rejected.
- Add a configured 0.1 mm axis-anchor sampling step and minimum-angle constrained
  axis search. The selected C4 joint dimensions, fit clearance and marker
  positions are unchanged.

## 2026-09-03 - Numbered marker machining diagnostics

- Show visible 1-based numbers inside partition markers and use the same numbers
  in spacing and machining error messages. Bilateral pair members share one
  number rather than consuming two display numbers.
- Apply local cuts in visible marker order and record the connected-component
  count before and after every cut. A rejected split now identifies the marker
  number whose cut did not create exactly one additional part, while retaining
  the unchanged source anatomy.
- Persist failed-marker geometry and pair identity independently from transient
  display numbers. Inserting or deleting markers therefore cannot move a red
  failure highlight to an unrelated marker; a failed bilateral pair highlights
  both members under their shared number. Opaque internal marker names remain
  private job state.

## 2026-09-03 - Rounded workflow socket backs

- Removed the cylindrical calibration-coupon mount and its identifying dimples
  from image-workflow sockets. The anatomy bridge already supplies the required
  attachment, so the socket now keeps its spherical outer back instead of a
  flat, perforated boss.
- Kept the C4 cavity, retention rim, four flexure slots, ball and bridge sizes
  unchanged. Standalone retention calibration coupons retain their mounts and
  labels.

## 2026-09-03 - Local socket-mount relief for dense workflow joints

- Kept the inferred kinematic parent/child and socket/ball ownership unchanged.
- Exported the dimensional socket shell and cavity separately while keeping the
  oblique mounting bridge inside the already validated one-piece CAD socket.
  Foreign socket-shell contacts are relieved only on the side whose measured
  cavity distance retains `printing.min_wall_mm`; cavities, balls and anatomical
  source meshes are never cut. The same rule covers a foreign ball touching a
  neighbouring socket exterior. Standalone bridge export was rejected because an
  otherwise valid oblique socket can contain a bridge/void intermediate that is
  not independently valid in OpenCascade.
- Uses the complete foreign shell or ball as the relief cutter rather than the
  pre-intersected overlap solid. The removed volume is identical, while avoiding
  coincident Boolean faces that can collapse into non-manifold STL edges.
- Records every relief and its retained wall in `hardware_trim.json`, reuses the
  original one-piece CAD socket when no bridge cut occurred, and still requires
  closed one-piece exports plus an exact collision-free neutral assembly.

## Oblique workflow socket robustness

- Keep a valid socket or ball Boolean result when OpenCascade's optional
  splitter-face refinement produces invalid topology at an oblique attachment.
  Joint dimensions, fit and anchor positions remain unchanged.
- Apply the spherical void to the support bridge before joining it to the already
  hollow socket. The equivalent Boolean order avoids the oblique micro-seam that
  previously produced an open STL despite a valid CAD solid.
- Record every skipped refinement in the per-revision CAD report so a recovered
  kernel edge case remains auditable instead of appearing as an unexplained
  generic machining failure.
- Derive the minimum marker spacing from the selected C4 socket's exact outer
  diameter. Conflicting markers are red, machining is unavailable while they
  overlap, and the server independently rejects stale or bypassed UI requests
  with the measured and required spacing before starting expensive CAD work.
- When a newer marker operation is already queued, reap the older successful
  worker without treating its exit as a failure of the new request. Successful
  partition and machining publications also clear any earlier retry error.

## Operation-driven live partition colour

- Remove the preview-update button. Every marker add, delete, pair/unpair and
  radius change immediately starts a background partition update.
- Keep edits made while an update is running and submit the latest marker state
  as soon as that update finishes; do not infer completion from an idle timer.
- Reload the exact server-generated part colours without resetting orbit, zoom,
  pan or marker-editing state.
- Keep the currently drawn mesh visible while the replacement colour buffers
  load, then swap them in one render step so the model never flashes blank.
- Suppress completed intermediate revisions whenever a newer marker operation is
  local or queued. Only the latest submitted marker state may replace the preview,
  preventing deleted markers or removed symmetry pairs from briefly returning.
- Treat an unexpected partition-process exit separately from image generation:
  retry the unchanged marker request once, then report a partition-specific
  failure with its exit code while preserving the last valid colour preview.

## Bilateral midline marker snapping

- Snap a slightly left/right-offset central marker onto the model's bilateral
  ZY plane by changing only its X coordinate. Preserve its selected Y/Z location
  and the existing camera-depth midpoint.
- Limit snapping to half the marker radius, so neck and tail midline points are
  straightened while genuinely lateral hip and shoulder points stay lateral.
- Keep midline markers single. Automatically create a bilateral pair for every
  newly placed or loaded user marker outside the midline snapping zone; manual
  marker double-click is no longer required for the default lateral case.

## Linked symmetric markers

- Treat every visible partition marker as active; remove the click-to-toggle
  state. Unwanted automatic or user markers can be removed directly.
- Render bilateral marker pairs in blue and persist their pair identity through
  preview regeneration.
- Double-click an ordinary marker to create or link its reflected counterpart
  when matching geometry exists. Double-click a paired marker again to keep the
  clicked side and remove its counterpart. Right-clicking either member removes
  the whole pair.
- For an explicit marker double-click, prioritize the user's bilateral intent:
  reflect across the model plane and snap the result to the opposite solid's
  camera-ray midpoint. If segmented preview surfaces make the inside test
  inconclusive, retain the reflected point instead of rejecting the explicit
  request. Keep the stricter neighbourhood-
  similarity rule only for unsolicited automatic pairing of a newly placed
  canvas marker.

## Symmetric marker placement

- While marker editing is active, use only the preview-update action; the
  redundant separate end-editing action is hidden.
- Mirror a newly added off-centre marker across the configured bilateral plane
  only when the reflected centre is inside the model and both neighbourhoods
  have similar sampled face counts and mean distances. Midline anatomy and
  dissimilar or missing opposite-side geometry are not duplicated.

## Marker depth centering

- Place a new user marker halfway between the first entry and exit surfaces on
  the clicked camera ray. This centres the joint in all three dimensions rather
  than estimating depth from a fixed radius.
- Detect legacy user markers without placement metadata and re-centre them from
  the fitted initial camera view. The corrected coordinates are persisted on
  the next partition-preview update; automatic geometry candidates are untouched.
- When several separate solids overlap along the same screen ray, choose the
  entry/exit interval nearest the existing marker rather than the front-most
  interval. A lazily built BVH keeps repeated depth correction interactive.

## Reversible partition and direct machining

- Start joint machining directly from the toolbar without an intermediate
  confirmation dialog.
- Restore the immutable pre-machining partition preview after machining,
  machining failure, print failure or print preparation, then reopen marker
  editing without discarding the source image or previous revision files.
- Draw the candidate sphere at the configured 6 mm production-ball diameter.
  Keep the larger marker partition envelope visible as a separate dashed ring.

## Joint-marker placement

- Keep a newly created spherical candidate on the camera ray through the
  double-clicked pixel. Sloped surface normals no longer push shoulder and limb
  markers sideways from the location selected in the viewer.

## Image-to-3D generation progress

- Show a compact progress bar for the selected image job with the current phase,
  percentage, elapsed time and estimated remaining time.
- Parse only bounded aggregate counters from the local Hunyuan inference log:
  50 diffusion steps followed by the volume-decoding cells. Never expose the
  worker log itself through the viewer API.
- Base the start-up estimate on the two recent RTX 3060 runs (4:11 and 4:13),
  then replace it with live phase progress as soon as counters are available.
- Remove generated floating debris only when a disconnected component is below
  both the configured face and relative-area thresholds. Preserve every major
  disconnected component and compute the 120 mm scale after debris removal.

## Marker-constrained image-mesh partition review

- Show automatic joint-region proposals directly on the generated mesh. A user
  can enable or disable each proposal, add multiple surface markers by double
  click, remove added markers by right click, and adjust their radius with the
  mouse wheel.
- Recompute a colored, non-printable partition preview using only the selected
  marker envelopes as allowed boundaries. All source faces are assigned exactly
  once; disconnected fragments are never discarded, and unselected proposals
  cannot create new part boundaries.
- Store each accepted preview as an immutable revision before any exact FreeCAD
  cut or joint machining. P3-SAM over-segmentation remains a planned provider;
  the current automatic proposals use the local geometry detector.

## Viewer controls and intentional joint-contact filtering

- Pan the camera with a middle-button drag and restore the original fitted view
  with a middle-button double-click. Camera orbit, roll, zoom and joint poses keep
  their existing behavior.
- Hide sampled interference only inside the configured ball radius plus the STL
  clearance sampling tolerance for each actual mating parent/child pair. Continue showing stem/socket, stem/anatomy and
  all non-mating-part collisions.
- Remove the redundant image-upload button; image drag/drop and its validation,
  queueing and progress feedback remain available.

## 1.3.1 — Physically selected S3 production joints

- Apply the physically preferred R3 S3 deep C-shaped four-slot socket to all
  eight joints of the 120 mm T. rex. Keep the 6.0 mm ball, 3.4 mm pole and
  5.4 mm retention opening; use a 5.90 mm spherical cavity (0.10 mm diametral
  interference).
- Extend only the left and right ankle ball poles by 2.0 mm. The ball centres
  and socket positions stay fixed while the thick foot connection begins farther
  from the socket; this removes the measured surrounding-part interference
  without cutting additional bone.
- Treat the exact socket/ball preload as the intended fit during neutral and
  discrete-motion collision checks. Continue reporting any overlap beyond it.
- Keep tree supports enabled for the A1 mini Bambu project, with 0.24 mm top-Z
  and 0.45 mm object-XY separation to make PLA Matte supports easier to remove.

## Holding trial R2 — four-slot sockets, thick stem, no mouth relief

- Follow physical feedback: retain the C4 direction and standardize the three
  test ball stems at 3.4 mm. Do not change production joint-v3 or the body.
- Compare cavity diameters 6.15, 6.05 and 5.95 mm on 6 mm balls. H3 has deliberate
  0.025 mm radial interference; actual holding torque and permanent set are unknown.
- No added mouth relief. Report reduced movement separately from intended
  spherical contact, with paired one/two/three-dot marks and supported Bambu output.

## Image workflow acceptance — automated prototype preparation

- Verify non-dinosaur image provenance, nine-part color review, eight articulating
  joints, angle/twist readout and collision-only red overlays in the live viewer.
- Recheck all exported STEP solids, closed part meshes, discrete motion, native
  Bambu geometry/toolpaths and the served 3MF hash. Record scope and limitations in
  `WORKFLOW_ACCEPTANCE.md`; no geometry, material or printer-dispatch change.

## Scope clarification — user-managed model edits

- The user handles model additions/corrections independently. No editing screen,
  separate editor, or dedicated correction-input workflow is wanted.
- Withdraw the proposed backend correction path before implementation. Preserve
  image generation/separation, review, print preparation and stale-release checks.

## Human corrections and print retry isolation

- Additions/corrections are human decisions. The choice of an in-viewer or
  separate editing surface is pending; no editor controls have been implemented.
- Isolate each Bambu slicing attempt so an earlier output cannot satisfy a retry.
  Revoke a prior ready release before preparing new output, while preserving its
  record and all attempt files for diagnosis.
- Recheck the actual model, part hashes and exact review approval before serving
  a print release. Changed geometry requires renewed review and print preparation.

## Viewer scope — review only

- Withdraw the unimplemented manual joint-addition/position-editing UI proposal.
  Keep geometry corrections in the automatic processing pipeline. The viewer is
  for visual, articulation and collision review, not editing the model.

## Image workflow — mechanical revisions and review-bound Bambu preparation

- Add finite FreeCAD joint-bulb excision and experimental C4_28 integration for
  arbitrary inferred part trees; production joint-v3 and dinosaur outputs unchanged.
- Require closed single-part STL exports, exact neutral-pose collision tests,
  embedded attachment anchors and bounded source-preserving cut-edge finishing.
- Add contextual machining and print-preparation actions without permanent cards;
  keep generated geometry, revisions and print outputs isolated by image job.
- Require a current geometry-bound review, independently test the reviewed pose,
  then prepare native supported Bambu plates through CUI. Never dispatch a printer.
- Candidate correction, missed-joint handling and arbitrary attachment strength
  remain unfinished; experimental geometry is not a physical fit certification.

## Retention trial R1 — user physical feedback, calibration only

- Old 1/2/3 snap coupons were reported loose and spread after insertion; do not
  interpret previous CAD capture checks as verified physical retention.
- Add all-printed split sockets with tapered double-dovetail keys (three fits),
  plus deeper four-slot C sockets with 2.4/2.8 mm stems. No added metal hardware.
- Keep the current body unchanged pending comparison prints. New calibration
  exports use native Bambu Studio, A1 mini 0.4 mm, PLA Matte and enabled supports.

## Print workflow — Bambu Studio 02.08.02.61

- Default CUI entry point now uses installed, hash-pinned Bambu Studio instead
  of Orca. Preserve the previous Orca projects/exports; no geometry changes.
- Resolve native A1 mini 0.4 / 0.16 mm Optimal / Bambu PLA Matte presets rather
  than importing Orca settings. Keep white, 4 walls, 55 C Textured PEI, supports.
- Native enum values eliminate the Orca-to-Bambu settings substitutions.
- Deliver only body and fit-kit 3MF files, without a ZIP or handoff document.

## 1.3.0 — 120 mm palm-size print preparation

- Scale the accepted August 30 anatomy to assembled length 120 mm; preserve
  6 mm joint-v3 balls and the user's 0.6 mm diametral fit without slicer scaling.
- Reposition limbs, head and tail to retain the anatomy and motion clearances.
- Certify actual STL quantization; allow a 0.00005 mm simplification fallback
  (maximum 0.0002 mm) and only sub-tolerance open-boundary welds, with <=0.001 mm3
  volume change and unchanged independent preservation checks.
- Prepare A1 mini stock 0.4 mm nozzle, white Bambu PLA Matte and stock Textured
  PEI profiles through CUI. Earlier 1.2.4 sliced files remain obsolete.

## 1.2.7 — Full rim coverage and machined-border blends

- Fix a real 1.2.6 half-rim fillet omission caused by revolve-seam quarter arcs.
  Revolve an analytic tangent R1 profile through 360 degrees, then cut the slit;
  validate CAD mirror symmetry and subsequent rigid-interference sweeps.
- Blend cut boundaries on arms, legs, head, torso, feet and tail before adding
  precision joints. Local 1.5 mm fairing band, 0.5 mm maximum vertex displacement;
  independent finite cut-border audit and no additive invasion of clearances.
- Keep 6 mm balls, 6.6 mm sockets, 1.5 mm nominal mouth height and placements.
  Preserve unmodified anatomy outside the bounded finish allowance.
- Regenerate geometry and previews; existing sliced G-code remains obsolete.

## 1.2.6 — Lower exterior socket mouths, compact neck and tail clearance

- Actually lower all socket mouth exteriors from nominal 2.811 to 1.5 mm in
  front of the ball centre, with R1 outer edge rounding. Preserve 6 mm balls and
  0.6 mm spherical clearance. Recompute calibration heights and final apertures.
- Remove the annotated original neck bulb from raw torso before hardware is
  added. Move head and neck centre 4.5 mm toward torso; use only the finite local
  trim plus socket cavity, disabling the broad neck target sphere.
- Extend the finite, rounded relief only at the annotated first upper tail-root
  projection. Preserve other limbs, torso-owned hip rings and part count.
- Show 1.2.6 in the existing viewer selector and expose fetched STL hashes for
  verification. Already loaded pages still require a reload after rebuilding.
- Regenerate all CAD, mesh, preview and test outputs. Old sliced G-code is stale.

## 1.2.5 — Full-circumference removable socket mouth

- Replace the proposed directional notch experiment with a full-circle inner
  lip relief for a 30-degree stem envelope. All eight sockets and calibration
  coupons use the same rule; left and right sides match.
- Preserve joint-v3, ball 6 mm, cavity 6.6 mm, 0.6 mm diametral fit, anatomy,
  torso-owned hip rings, positions and supports. The pre-trim retention setting
  remains 5.8 mm; nominal final aperture is sampled at approximately 5.828 mm.
- Prefer easy manual removal with a small remaining rigid withdrawal barrier.
  Do not claim a measured retention force, no wobble or fatigue resistance.
- Add negative and diagonal CAD motion checks and measure the final aperture.
  Regenerate all model exports; old versioned 1.2.4 slicer projects are stale.

## Viewer 3.4.0 — Direct twist gestures

- Add view roll by circular dragging in the outer 28% of the normalized screen
  radius, or by twisting two touch points. Central dragging still orbits; reset
  restores all camera axes. Screen roll is not model-world Z rotation.
- Add local joint twist by circular dragging from outside a part's projected
  centre ring. Starting inside bends as before. A thin guide is visible only
  during the gesture; Shift-drag remains a linear twist override. Torso stays
  fixed and camera gestures never edit joint poses.
- Use the same rolled camera basis for rendering and part picking. Test angle
  wrap, camera reset, finger twist, part twist/bend, guide cleanup and picking.
- Viewer-only changes; no joint dimensions or print exports changed.

## Viewer 3.3.2 — Restore fixed torso

- Remove the torso rotation control. Dragging the torso once again orbits the
  camera, like dragging the background. Keep the eight physical-joint controls,
  local angle readouts, opaque colors and collision checks unchanged.
- Viewer-only change; no geometry or print exports changed.

## Viewer 3.3.1 — Attached torso rotation

- Make torso the parent of head, arms, legs and tail. Feet remain children of
  their legs. Resolve transforms recursively, independent of definition order.
  Turning the torso now moves the assembly without detaching connections or
  overwriting the individual joint angles.
- Keep opaque colors, selection readout, collision checks and resets. Verify
  that whole-assembly rotation introduces no collision in the neutral real
  mesh, and that existing collision pairs and markers follow correctly.
- Viewer-only correction; no geometry or print export changes.

## Viewer 3.3.0 — Opaque parts and torso inspection

- Remove selection transparency entirely. All nine parts remain opaque during
  idle, part dragging, camera rotation and zoom. Retain the angle readout.
- Allow independent torso rotation about its mesh bounding-box centre through
  the same drag, twist, keyboard, reset and collision-check path. Label it
  preview-only; other parts do not inherit this transform. This is not a new
  physical joint or a claim of mechanically achievable motion.
- No geometry, joint configuration or print export changes.

## Viewer 3.2.1 — Opaque whole-model interaction

- Temporarily disable selection transparency during camera orbit and
  pinch/wheel zoom. Restore it when the gesture ends without clearing the
  selected part, angles or collision state. Cover pointer cancellation and
  lost capture, including switching from two fingers back to one.
- Viewer-only change; geometry and print exports remain unchanged.

## Viewer 3.2.0 — Selected-part angles and transparency

- Show the selected part and its three joint angles in a single unobtrusive
  bottom line. Initial pose is zero; ankle angles are relative to the leg.
  Commit angle readouts together with the tested, displayed pose.
- Keep the selected part opaque and render the other eight at 60% opacity,
  preserving part colors and fully opaque red collision markers. Sort
  translucent parts back-to-front and restore depth writes after rendering.
- Selecting the torso shows a fixed-part label; other models remain opaque
  and hide the angle readout. No joint cards or extra controls are introduced.
- Geometry remains revision 1.2.4. No CAD, STL, 3MF, material or CAE changes.

## 1.2.4 — Rounded shallow sockets and separate capture opening

- Shorten nominal socket front reach from 3.788 to 2.811 mm with a tangent
  R1 rim and 2 mm spherical wall; retain all eight centres and limb placements.
- Keep joint-v3, 6 mm balls and 0.6 mm diametral fit. Define an independent
  actual 5.8 mm capture opening shared by all three calibration clearances.
- Apply the new cup only as additive hardware; retain historical anatomy
  cavity cutters. Check direct attachment with the actual new shell, not a
  spherical proxy. Preserve all bones and both torso-owned hip rims.
- Add CAD seating/withdrawal barrier validation and regenerate fit coupons.
  Retention force, wobble, snap durability and wear still require physical tests.
  Archive the full 1.2.3 hybrid output before replacement.

## Viewer 3.1.0 — Real-time collision and model-first interface

- Remove the legend, color switch, joint card, sliders and permanent pivot
  marker. Always color the nine parts and use the full canvas. Retain only
  compact model selection/camera reset; show the top collision banner only
  when penetration is detected. Keep direct dragging, with Shift for twist,
  arrow keys for fine adjustment, Home/Escape for pose resets.
- Replace debounce/stale-result starvation with an immediate one-in-flight,
  latest-queued-pose scheduler. Atomically commit each tested pose and matching
  red overlay while dragging. Reuse unchanged pairs without lowering density.
- Test continuously held input, matching pose/collision revisions, cache versus
  uncached results, all model/error races, permanent colors and full canvas.
  Browser QA confirms collision updates before pointer release and a banner
  at the top only during detected collision. Geometry remains revision 1.2.3;
  CAD, STL, 3MF, joint dimensions, material and CAE outputs are unchanged.

## Viewer 3.0.0 — Interactive articulation and localized collision review

- Add part dragging and three rotation sliders for eight actual joints in the
  current nine-part assembly. Feet follow hips; joint centres come from the
  production configuration. Keep camera orbit, pinch zoom and part coloring.
- Show sampled penetrations as red points and list colliding part pairs. Run
  approximate two-sided mesh containment checks in a worker with latest-pose
  scheduling, stale-result rejection and explicit pending/error states.
- Add independent joint/pose resets. Warn that +/-60 degrees is an exploration
  range and that sampling may miss interference; no physical guarantee.
- Verify matrix/pivot hierarchy, cavities, picking, real neutral and colliding
  meshes, worker/configuration races, and live browser dragging/reset/display.
- Geometry revision remains 1.2.3. No CAD, STL, 3MF, material or CAE changes.

## 1.2.3 — Compact bilateral joints and local tail relief

- Mirror all shoulder, hip and arm placement changes to both sides. Retract
  shoulder centres by 4 mm and hip centres by 6 mm from 1.2.2; require direct
  socket-shell contact with the original torso, not only a bridging rod.
- Move both arms 2.5 mm forward and embed the standard stud endpoint inside
  the intact bone. Omit the unnecessary T-shaped capsule support. Legs/feet
  follow the hip retraction; ankle centres change from Y=+/-30 to +/-24 mm.
- Add only a 1 mm-edge-radius sloped relief to the first upper tail projection.
  The finite X=0..7.4, Y=+/-5.5, Z=54.3..65.5 mm envelope excludes other anatomy.
  Verify tail pitch from -15 to +15 degrees at 2.5-degree intervals.
- Keep joint-v3 and 6 mm / 0.6 mm fit dimensions. Keep both hip rims on torso.
  Validate mirrored parameters, intact anatomy, embedded stems and direct
  shell attachment. Generate the current nine-object OrcaSlicer package in
  every build; archive 1.2.2 production files before regeneration.

## 1.2.2 — Torso-owned hip rims and spaced limb connections

- Transfer both intact decorative hip rims from legs to torso through a local
  0.4 mm seam and a hidden inward lap; retain nine printable parts.
- Translate arms +/-12 mm in Y, legs and feet +/-14 mm. Move shoulder centres
  to Y=+/-20, hip centres to +/-23 and ankle centres to +/-30 mm.
- Disable shoulder/hip spherical motion-clearance subtraction. Preserve the
  raw anatomical bones and fit additive joint hardware in the increased space.
  Keep joint-v3 dimensions and printer fit clearance unchanged.
- Validate exact finite partition cuts, inverse placement, final removed
  volume against enabled cutters, and torso ownership of both rims. Add
  15-degree outward spreading samples for shoulders and hips.
- Preserve the previous production files in
  `backups/revision_1_2_1_before_hip_transfer/` before regeneration.

## Viewer 2.2.0 — Part colors

- Display the assembly using its nine actual named part STLs, with a distinct
  color per part and a Japanese legend. Individual part views retain that color.
- Enable coloring by default; the checkbox restores bone shading without
  resetting the camera. Unpartitioned references remain uncolored.
- No CAD geometry, joint dimensions, printable files or material properties
  changed. Tests verify exact vertex/normal preservation, assembly bounds and
  triangle count, grouped rendering, toggling and asynchronous loading errors.

## 1.2.1 — Restore hands, toes and inner legs

- Rejected the 1.2.0 box/global-plane partition. Restored all anatomy from the
  unchanged August 30 source. Recovered roughly 4.2 mm of finger reach and
  8.3 mm of toe reach, plus the shaved lateral/inner leg surfaces.
- `hybrid_new.partition_method=local_joint_discs`: cut radii neck 10 mm,
  shoulders 9 mm, hips 14 mm, ankles 10 mm, tail 12 mm. Disc thickness is still
  1.2 mm; tail disc offset is -1 mm along its joint axis (X=3 instead of X=4).
  Joint centres and 6 mm ball / 0.6 mm diametral fit clearance are unchanged.
- Source support for neck: (-71,0,83) -> (-72,0,91) mm to anchor into the
  solid skull roof instead of the cavity. No disconnected neck stud is discarded.
- Retain all nine partition components. Replace generic 200/600 mm³ fragment
  removal with <=0.001 mm³ numerical-fragment cleanup confined to joint envelopes.
- Mandatory preservation test: source vertices outside joint-local envelopes
  must survive within 0.001 mm, or be contained in additive support material.
  Each finished part is also compared with its intact raw partition. Regression
  check rejects the damaged 1.2.0 assembly. Add matched enlarged anatomy previews.

## 1.2.0 — August 30 inference joint processing

- Promoted the new `20260830_dfba1098/trex_new_200mm.stl` into nine parts/eight
  joints, separately stored in `build/hybrid_20260830`. Old hybrid outputs and
  the unprocessed source remain available. Viewer default is the new assembly.
- New `hybrid_new` centres (mm): neck (-63,0,82), shoulders (-47,±12,64.5),
  hips (-15,±13,55.5), ankles (-15,±16,14), tail (4,0,49).
- Anatomy part gap: new model 1.2 mm (old model 0.4 mm; intermediate trial 0.6 mm).
  Head split X=-63; shoulders Y=±12; hips Y=±13; ankle Z=14; tail X=4.
  Arm box X=-68..-42, Z=43..71; leg lower/upper X=-38/-27,
  step Z=42, top Z=64. Selection/removal boundaries offset by half gap on X/Z.
- Ball and target clearance radii 6.5 mm; male support radius 2.2 mm,
  hips 3 mm. All source/target support coordinates are explicitly recorded in
  `hybrid_new.connections` and the generated parameter-difference review.
- Preserved joint v3, ball 6 mm, socket 6.6 mm, throat 5.2 mm, neck 3.4 mm,
  outer socket 10.6 mm, slot 1 mm, stud reach 3.8 mm and mesh precision settings.
- Remove only exactly zero-area boolean triangles before topology validation.
  Sweeps now check all other parts and carry feet with hips; new hip outward
  yaw sign follows the new forward-knee anatomy. No tolerance relaxation.
- Assembly, side and reference-comparison previews now use the new model/image.
  CAD joint tools also export STEP. CAE scope remains standard specimens, not
  whole-animal or organic-support strength; physical qualification is pending.

## New appearance review — 2026-08-30

- Actually ran new Hunyuan3D 2.1 inference from the reattached reference image,
  seed 20260830, 50 steps, octree resolution 512. Archived original pixels and
  logged source/input/output SHA-256 hashes and UTC generation timestamps.
- Stored candidate files separately under `20260830_dfba1098`; no replacement
  of the prior production source, joints, assembly or print files.
- Viewer defaults to the explicitly labelled new appearance; the old August 21
  model is labelled as old. New candidate mechanical integration remains pending.
- Corrected winding after the handedness-changing image-mesh coordinate transform;
  candidate validation requires a closed single mesh with positive signed volume.

## 1.1.2

- Refined production joint-tool tessellation from 0.05 mm / 0.15 rad to
  0.025 mm / 0.10 rad, now sourced from `printing.joint_linear_deflection_mm`
  and `printing.joint_angular_deflection_rad`. The standalone joint, ball key,
  socket calibration strip and starter fit kit use the same precision profile
  (previously 0.08 mm / 0.25 rad). Nominal CAD geometry, joint v3, 6 mm ball,
  0.6 mm diametral fit clearance, material and anatomical placement are unchanged.
  Anatomical clearance cutters retain their existing 0.05 mm / 0.15 rad profile,
  now explicitly configured as `printing.clearance_linear_deflection_mm` and
  `printing.clearance_angular_deflection_rad`; each tool reports its profile.
- Viewer 2.1.0: added standalone joint and fit-calibration model choices, and
  allowlisted model deep links for opening the finished assembly directly.
  Retained the read-only UI and the uncut-appearance default; no editing or storage.
- STL validation now requires positive signed volume, so an inward-wound mesh
  cannot pass merely because its absolute volume is positive.
- Replaced the stalled browser-based SVG preview step with FreeCAD's bundled
  Qt SVG renderer. No browser profiles or historical review files are removed.


## 1.1.1

- Viewer 2.0.0: returned to a read-only model viewer with selection, orbit,
  wheel/pinch zoom and fit-to-view. Removed cutting, sculpting, joint manipulation,
  annotations, persistence code, their two helper modules and four dedicated tests.
  Added a focused simple-viewer test. Model/print files and browser-owned saved data
  were not deleted. No archive copy of the removed feature code was created.

- Viewer 1.20.0: depth-correct ball/socket display with owner-labelled, colour
  matched surface markers and dashed mounting-reference lines. Show centre-inside
  or centre-to-surface distance. References follow poses and sculpt changes,
  without embedding hardware, adding rods or changing placement/production parts.

- Viewer 1.19.0: autosave exact cut geometry/allowance, display offsets, ancestry,
  applied records and guides atomically in browser IndexedDB; restore without
  re-cutting. Show saving/saved/error status with retry and unsaved-exit warning.
  Protect previous saves on failed writes and stale-tab conflicts. Cut-piece
  sculpt changes persist; connector poses and production exports remain separate.

- Viewer 1.18.2: arrow keys pan the camera in screen coordinates in either stage
  (Shift speeds up), replacing the canvas-only part rotation shortcut. Native
  fields and axis handles keep their own keys. Desktop/mobile recenter buttons
  change only the view center; camera angles, zoom and all model edits stay intact.
  Production geometry and dimensions are unchanged.

- Viewer 1.18.1: preserve pending guides drawn on a parent after it is split.
  Rebind exact surviving surface locations to descendant triangle indices without
  moving the ink; show the pending guides at each descendant's display offset.
  Reject missing/modified surfaces explicitly, retaining all previous pieces.

- Retain split pieces when creating/editing another cut. Pick the visible piece
  in local coordinates and cumulatively replace only its successfully cut geometry.
  Current cut pieces now feed the joint stage, with selectable socket/ball owners,
  independent guides and pair-specific placement state across stage switches.

- Replaced closed-loop-completion gating with stroke-driven cutting sheets.
  Open strokes and gaps can cut the model; triangle intersections follow drawn
  positions and only supported contours detach. Original ink stays unchanged.
  Added open/curved/gapped/reversed-stroke, connected-branch and UI regression tests.

- Added bounded surface-path gap completion, short scribble cleanup, and an
  explicit selected-cut split into separate browser mesh objects. Removed
  separation-status colors while editing; colors appear only on split results.
  Source faces are preserved exactly once; supported cut rims are capped with
  rounded allowance. Added per-piece shaving/addition and independent Undo;
  shaving protects the closed base. Joint/print production output is unchanged.
- Replaced viewpoint buttons with editable cut records, a New cut action,
  toggle-to-exit selection, redraw/delete with Undo, and middle-button orbit
  during drawing. Added conservative edge-snapped surface-separation checking:
  orange/green cut status and region tinting, without changing production solids.
- Replaced camera-plane cut ink with nearest-surface ray-picked 3D samples.
  Surface strokes use depth-tested yellow rendering, stay anchored during orbit,
  do not bridge empty space, and support chronological Undo after camera changes.
  Kept legacy 2D data separately; production meshes and joints are unchanged.
- Corrected the cut stage to show the complete uncut appearance STL, not the
  existing split pair. Kept joint/sculpt meshes separate, retained per-stage
  cameras, removed split-only cut controls, and separated legacy guide storage
  to avoid projecting old split-view annotations onto the uncut source.
- Added cut-guide drawing in the cut stage: dashed strokes, saved camera views,
  per-view Undo, browser-local persistence, and phone input. Camera-plane
  coordinates preserve alignment across viewport resizing. These are guide
  annotations only; no mesh cutting, repartitioning or CAD changes occur.
- Added a separate responsive phone layout: compact header, expandable model
  menu, bottom operation dock, canvas space reserved above the dock, safe-area
  support and portrait-aware framing. Added pinch zoom and a phone Undo button;
  desktop layout and CAD geometry are unchanged.
- Separated cut review from joint placement. Added raw/allowance comparison,
  selected-part isolation, and live teal allowance tinting. Stage switches retain
  joint/sculpt state; cut view has no joint manipulation. Documented a proposed
  ownership-painting workflow (not yet a repartitioning implementation).
- Added browser-only rounded machining allowance to known split caps, with
  conforming refinement, source-surface protection while shaving, smaller brush
  steps, back-face exclusion and reset to the filled baseline. Both sides can
  overlap intentionally for manual clearance review. Production split/CAD
  geometry and joint dimensions are unchanged.
- Added the viewer host's root Serve route so bare-host entry and slashless
  `/3dviewer` redirects also work; refuse to replace an unrelated root service.
- Replaced the generic directory server with an allowlisted read-only viewer
  server. Root requests redirect to the viewer, including the private Tailscale
  `/3dviewer/` mount. Added optional Tailscale startup without changing existing
  unrelated Serve routes or enabling public Funnel access. CAD/STL unchanged.
- Added separate labelled body and connector translation gizmos. A body move
  carries only its owned ball/socket; a connector move edits only that side's
  local mounting position. Reconnection translates the selected group to the
  opposite joint centre without discarding either mounting edit or moving the
  target side. Both detached placement and fitted articulation are supported.
- Removed joint-neighbourhood warping from the viewer. The boundary lab now uses
  pre-joint raw split anatomy plus independent, stemless ball/socket placement
  guides. Shared-axis relocation leaves body vertices and existing poses intact;
  each guide follows its owning part. No auto-support, cavity cut or embedding
  is added, and production CAD/STL outputs are unchanged.
- Replaced the boundary lab's orbit/joint/part mode buttons with direct picking:
  part dragging articulates the selected side, background dragging orbits the
  view, and X/Y/Z arrow handles relocate a shared ball/socket centre. Both joint
  neighbourhoods move locally together. Collision colour is now restricted to
  sampled intersection regions rather than tinting a whole part red.
- Extended the browser boundary lab into the cut/joint/motion iteration loop:
  provisional joint centres can be dragged in the current view, moving parts
  follow the revised pivot, and sampled fixed/moving overlap is highlighted in
  red with an explicit collision-status readout.
- Hid the viewpoint pen panel without deleting its browser-local data and added
  the boundary lab for temporary clay-like add/remove edits, direct joint-centred
  part rotation, and translucent manual overlap review.
- Moved both shoulder and hip joint centres 3.0 mm inward into the torso so the
  complete arm and upper-leg silhouettes reach naturally to the joint boundary.
- Reduced the shoulder/hip source-side clearance cuts from 7.0/6.5 mm to
  5.6/5.8 mm and replaced
  thin exposed supports with 2.2 mm-radius shoulder and 3.0 mm-radius hip
  buttresses, preserving the joint-v3 6.0 mm ball interface.
- Tucked both hip socket bridges inside the torso so the added proximal-leg mass
  remains collision-free at the neutral assembly pose.
- Limited shoulder and hip validation to the collision-free 5-degree outward-yaw
  direction; the restored proximal bone mass is now the intentional pitch stop.

## 1.1.0

- Prioritized the approved organic belly, upper-leg and tail-root detail over a
  symmetric 25-degree motion envelope; preserved anatomy now acts as the stop.
- Replaced the long hip connector struts with short local buttresses so the
  generated legs retain their original bone form instead of becoming rods.
- Reduced the shared joint standard from an 8.0 mm ball to joint v3: 6.0 mm
  ball, 6.6 mm socket, 10.6 mm outer shell, 3.4 mm neck and 3.8 mm stud reach.
- Retained the selected 0.6 mm diametral fit and the stable legacy `*_v2` output
  filenames; printed joint-v2 parts are not compatible with joint v3.
- Changed actual hybrid motion validation to anatomy-compatible, directional
  samples up to 5 degrees while retaining all static topology and collision checks.
- Aligned the older procedural assembly check with the same 5-degree
  detail-first motion policy.

## 1.0.0

- Repartitioned the approved outward-normal appearance mesh into nine parts at
  the user's browser annotations and added eight ball/socket connections.
- Made the head, arms, upper legs, tail and feet the male sides while keeping the
  fixed one-piece head and validating all 36 static part pairs.

## 0.9.0

- Added a standalone `ball_connector_v2`: an 8.0 mm ball on a straight 4.4 mm
  diameter stem extending 4.8 mm beyond the ball surface.
- Made the unpartitioned appearance mesh the viewer default for the next joint
  placement review; the current partition remains available as reference only.
- Corrected only the unpartitioned viewer model's triangle winding and normals;
  vertex positions, faces, dimensions, components, and absolute volume are unchanged.
- Left every existing hybrid assembly part, socket, and integrated ball support
  unchanged.

## 0.8.1

- Added a minimal local browser-based 3D viewer for the current hybrid assembly.
- The viewer provides only drag rotation, wheel zoom and a side-view reset; it
  intentionally contains no joint editor, memo system or prompt generator.
- Kept FreeCAD as the hidden precision-generation backend rather than requiring
  it for everyday visual review.

## 0.8.0

- Removed the hybrid jaw cut, cheek lugs, hinge bore, knuckle and removable pin.
- Restored the accepted image-to-3D head as one fixed, watertight part with its
  naturally open mouth and retained only the FreeCAD-authored neck socket.
- Reduced the production hybrid assembly from nine parts to seven parts and the
  static collision matrix from 36 to 21 unique pairs.
- Preserved every joint-v2 dimension and all six ball-joint motion sweeps.

## 0.7.0

- Replaced the hand-built appearance as the user-facing production model with a
  concept-driven Hunyuan3D 2.1 shape mesh, while keeping all precision joints
  authored by FreeCAD.
- Partitioned the generated T. rex into nine printable parts: upper skull,
  hinged lower jaw and pin, front/rear torso, paired legs, and two tail sections.
- Independently placed the neck, spine, hips, tail and jaw centers from anatomy
  and required motion; the connector marks in the concept sheet remain ignored.
- Preserved joint v2: 8.0 mm ball, 8.6 mm socket, 13.0 mm shell and 1.0 mm slot.
- Moved both hip centers 2.5 mm rearward to x=17.0 mm and routed the pelvic
  supports outside the socket envelope, eliminating torso/hip motion conflicts.
- Added hybrid FCStd assembly/print-plate documents, individual STL/3MF files,
  a combined 3MF plate, topology checks, 36-pair collision checks and actual-part
  motion sweeps.

## 0.6.0

- Rebuilt the visual language around the supplied concept sheet while continuing
  to ignore its illustrated connector locations.
- Replaced the round, rail-like head with a 56 mm long domed and fenestrated
  skull, a deep maxilla, raised orbital/cheek arches, and dense blunt teeth.
- Increased the chest to seven 4.2 mm ribs, added scapular and cervical detail,
  and enlarged the vertebral landmarks and sternum.
- Rebuilt the pelvis as a heavy open loop, thickened femur, tibia, fibula, ankle,
  and three-segment toes, and added rounded printable claws.
- Increased both tail sections to dense, tapered vertebral chains with neural
  processes, transverse processes, and ventral chevrons.
- Added a lowered-head presentation pose and reduced preview edge weight so the
  bone mass is readable without changing the FreeCAD solids.
- Preserved joint v2 dimensions and verified the real parts through the full
  plus/minus 25-degree ball-joint sweep and the 30-degree jaw sweep.

## 0.5.0

- Replaced the block skull with an open cranial frame, larger fenestrae, cheek
  struts, a curved lower jaw, and a denser tooth row.
- Replaced the bar-and-cage torso with a beaded vertebral column, five swept rib
  pairs, a connected sternum, and more anatomical two-finger arms.
- Rebuilt the pelvis as an open triangular bone frame and changed the legs to a
  stronger theropod S-curve with a separate fibula and longer three-toed feet.
- Added tapered vertebral landmarks and ventral chevrons to both tail sections.
- Preserved joint v2 dimensions and all six connection centers while clearing
  the new bone masses from the full ±25-degree motion envelope.
- Refined the visual match after orthographic comparison: denser upper and lower
  teeth, visible cervical vertebrae, heavier femur/tibia proportions, shorter
  thicker toes, and a 31 mm shorter tail tip.
- Curved each rib through six swept landmarks and split every foot digit into a
  thicker metatarsal, knuckle, and distal toe segment for a less schematic silhouette.

## 0.4.0 motion-validation follow-up

- Added rigid interference sweeps using the actual adjacent T. rex parts at all
  six ball joints, not only a generic ball-and-socket coupon.
- Added a jaw sweep from -20 through +30 degrees around the real hinge center.
- Added a spaced, low-profile nine-part 3MF build plate for 256 mm-class printers.

## 0.4.0 — 2026-08-14

- Replaced the 51-piece separate-peg assembly with a nine-piece articulated T. rex.
- Ignored the concept sheet's marked connector positions and placed joints by
  function: hinge at the jaw, balls at neck/spine/hips/tail, integral knees/ankles.
- Added an 8.0 mm ball, 8.6 mm cavity, 13.0 mm socket shell, 2.2 mm radial wall,
  1.0 mm relief slot, and flared socket mouth as joint v2.
- Verified zero assembled overlap at all six ball connections and zero collisions
  across the full assembly.
- Verified at least 25° collision-free pitch and yaw with a rigid CAD motion sweep.
- Added a three-clearance socket strip and 8 mm ball key as the starter print kit.
- Added actual ball-stud Gmsh/CalculiX analysis: 10 N side load, 0.095 mm
  displacement, 12.30 MPa maximum von Mises stress.

## 0.3.0 — 2026-08-14

- Replaced the generic radial creature pose with an original modular T. rex.
- Added a long open-jaw skull with eye/nasal openings and blunt printable teeth.
- Added a one-piece four-rib cage, curved femur and shin, compact curved forearm,
  and two-finger claw.
- Rebuilt the assembly as a horizontal biped with a long counterbalancing tail,
  short arms, broad stance, and zero volumetric collisions.
- Changed the review renderer to an upright near-side profile so the dinosaur
  silhouette and paired limbs are easier to judge.
- Preserved connector v1 dimensions and calibration clearances.

## 0.2.0 — 2026-08-14

- Replaced the OpenSCAD prototype workflow with FreeCAD 1.1.3 automation.
- Added FCStd, STEP, STL, assembly, validation and CalculiX output targets.
- Retained connector v1 nominal 5.0 mm peg and 0.4 mm starting clearance.
- Increased hub diameter from 16.0 to 17.2 mm to eliminate internal collisions
  between perpendicular connector-v1 pegs without changing the joint interface.
- Added per-part 3MF output and a combined starter fit kit for printer calibration.
- Added actual-socketed-bone Gmsh/CalculiX analysis alongside the analytical
  equivalent-section baseline.
- Added a workspace-local OrcaSlicer launch path for the starter fit kit.
- Added automatic review snapshots, parameter diffs, and a Japanese confirmation
  sheet so conversational revisions can be compared and restored.
- Fixed the saved assembly visibility state so all review parts are visible when
  the FCStd file is opened from the beginner shortcut.
# 1.3.0 — 120 mm palm-size variant

- User selected A1 mini / stock 0.4 mm nozzle / white Bambu PLA Matte.
- Scale anatomy independently of 6 mm joint-v3 balls and 0.6 mm diametral fit.
- Move small anatomy away from cups rather than shaving limbs; preserve hip rims.
- Preserve the 1.2.7 build; separate output `build/palm_120/` and viewer entry.
- Export resolved dimensions and source hash; check final assembly length.
- STL quantization removes only zero-area / exact duplicate facets before validation.
- Plate is unconfirmed; sliced data remains conditional until its type is known.
# Image workflow integration (in progress)

- Added isolated local image jobs, drag/drop and upload button, sequential hidden
  inference, progress/status recovery, source hashes and allowlisted artifacts.
- Added color-independent image preparation, Y-up/Z-up normalization, spherical
  joint proposals, connectivity classification and lossless surface color groups.
- Added manifest-driven joint graphs and oblique axes; preview groups remain
  unmachined and non-printable until the remaining CAD/review/slicing stages exist.
- Verified fresh non-dinosaur robot inference; added HTTP security, image, mesh,
  graph and UI regressions. Production joint dimensions/material remain unchanged.
# Holding R3 incremental fit plate

- Added an independent three-step comparison plate based on the physically
  preferred H3 four-slot socket; production T. rex geometry remains unchanged.
- Compare 0.050, 0.075 and 0.100 mm diametral interference using the same 6 mm
  ball, 3.4 mm stem and 5.4 mm retention opening.
- Retained the easier-release support settings: 0.24 mm top Z gap, 0.45 mm XY
  gap and two top interface layers.

# Holding R2 support-release adjustment

- Kept all six R2 test-piece meshes and joint dimensions unchanged.
- Increased support top Z distance from 0.12 to 0.24 mm and object XY distance
  from 0.35 to 0.45 mm for easier removal at 0.12 mm layer height.
- Retained two top interface layers and automatic tree support; the native Bambu
  project audit now verifies the release gaps as well as actual support G-code.

## 過去データへの依存の解消

- プリント準備は空のBambuプロジェクトから生成。過去の3MFテンプレートは不要。
- 旧モデルの固定リスト・配信経路、旧マーカーの読み替え、旧エラーの自動復旧を削除。
- 現行の未スライス形式だけを採用。スライスはBambu Studioで実行。
- ビュワーの検証用データはテスト内で生成し、過去の出力ファイルに依存しない。

## FreeCADの手動インストールを不要化

- 初回起動時に公式FreeCAD 1.1.3ポータブル版と展開ツールを自動取得。両方のSHA-256を照合し、展開先でモジュール読み込みと形状計算を検証してから配置。
- FreeCADのGUIは起動せず、従来と同じPython APIで加工。取得済み環境は再利用。
- READMEの事前インストール一覧はBambu Studioのみに変更。

### Symmetry-specific editing states

- Keep independent original/left/right partition, joint and print-preparation states; switching back restores the latest saved state without reprocessing.
- Scope motion snapshots and retained joint poses to the same symmetry choice.
