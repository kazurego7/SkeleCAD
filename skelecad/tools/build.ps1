$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$freecadBin = Split-Path -Parent (Get-SkeleCADToolPath 'freecad')
$freecadCmd = Join-Path $freecadBin "freecadcmd.exe"
$python = Join-Path $freecadBin "python.exe"
$meshPython = Get-SkeleCADToolPath 'workflow_python'
$ccx = Get-SkeleCADToolPath 'calculix'
$gmsh = Get-SkeleCADToolPath 'gmsh'
$buildParameters = Get-Content -LiteralPath (Join-Path $project "config\parameters.json") -Raw | ConvertFrom-Json
$hybridDirectory = if ($buildParameters.hybrid_new) { $buildParameters.hybrid_new.output_directory } else { 'build/hybrid' }
if ($buildParameters.hybrid_new.palm_size.enabled) { $hybridDirectory = $buildParameters.hybrid_new.palm_size.output_directory }

foreach ($required in @($freecadCmd, $python, $meshPython, $ccx, $gmsh)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required tool not found: $required"
    }
}

Write-Host "[1/13] Verifying the pinned modelling toolchain"
& $python (Join-Path $project "src\check_environment.py")
if ($LASTEXITCODE -ne 0) { throw "Toolchain verification failed: $LASTEXITCODE" }

Write-Host "[2/13] Preserving the previous user-review revision"
& $python (Join-Path $project "src\review_bundle.py") archive-before-build
if ($LASTEXITCODE -ne 0) { throw "Review revision archival failed: $LASTEXITCODE" }

Write-Host "[3/13] Generating FreeCAD parts, STEP, STL, 3MF and assembly"
& $python (Join-Path $project "src\freecad_project.py")
if ($LASTEXITCODE -ne 0) { throw "FreeCAD generation failed: $LASTEXITCODE" }
if ($buildParameters.joint_retention_trial) {
    & $python (Join-Path $project 'src/joint_retention_trial.py')
    if ($LASTEXITCODE -ne 0) { throw 'Retention trial CAD generation failed' }
    & $python (Join-Path $project 'src/validate_retention_trial.py')
    if ($LASTEXITCODE -ne 0) { throw 'Retention trial mechanical geometry check failed' }
}

Write-Host "[4/13] Building the image-to-3D / FreeCAD hybrid T. rex"
if ($buildParameters.joint_holding_trial) {
    & $python (Join-Path $project 'src/freecad_project.py') --holding-trial
    if ($LASTEXITCODE -ne 0) { throw 'Holding trial CAD/motion check failed' }
    & $meshPython (Join-Path $project 'tools/validate_holding_meshes.py')
    if ($LASTEXITCODE -ne 0) { throw 'Holding trial STL/3MF topology check failed' }
}
if ($buildParameters.joint_holding_step_trial) {
    & $python (Join-Path $project 'src/freecad_project.py') --holding-step-trial
    if ($LASTEXITCODE -ne 0) { throw 'Holding step trial CAD/motion check failed' }
    & $meshPython (Join-Path $project 'tools/validate_holding_meshes.py') 'joint_holding_step_trial'
    if ($LASTEXITCODE -ne 0) { throw 'Holding step trial STL/3MF topology check failed' }
}
if ($buildParameters.joint_workflow_holding_trial) {
    & $python (Join-Path $project 'src/freecad_project.py') --workflow-holding-trial
    if ($LASTEXITCODE -ne 0) { throw 'Workflow holding trial CAD/motion failed' }
    & $meshPython (Join-Path $project 'tools/validate_holding_meshes.py') 'joint_workflow_holding_trial'
    if ($LASTEXITCODE -ne 0) { throw 'Workflow holding trial topology failed' }
    & $meshPython (Join-Path $project 'tools/prepare_workflow_holding_print.py')
    if ($LASTEXITCODE -ne 0) { throw 'Workflow holding trial packaging failed' }
}
if ($buildParameters.joint_workflow_holding_step_trial) {
    & $python (Join-Path $project 'src/freecad_project.py') --workflow-holding-step-trial
    if ($LASTEXITCODE -ne 0) { throw 'R5 holding CAD/motion failed' }
    & $meshPython (Join-Path $project 'tools/validate_holding_meshes.py') 'joint_workflow_holding_step_trial'
    if ($LASTEXITCODE -ne 0) { throw 'R5 holding topology failed' }
    & $meshPython (Join-Path $project 'tools/prepare_workflow_holding_print.py') 'joint_workflow_holding_step_trial'
    if ($LASTEXITCODE -ne 0) { throw 'R5 holding packaging failed' }
}
& $meshPython (Join-Path $project "src\prepare_generated_appearance.py") `
    --input (Join-Path $project "build\generated_appearance\trex_appearance_200mm.stl") `
    --output (Join-Path $project "build\generated_appearance\trex_appearance_200mm_outward.stl") `
    --skip-ground-cut
if ($LASTEXITCODE -ne 0) { throw "Appearance normal correction failed: $LASTEXITCODE" }
& $meshPython (Join-Path $project "src\hybrid_partition.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid appearance partition failed: $LASTEXITCODE" }
& $python (Join-Path $project "src\freecad_hybrid_tools.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid FreeCAD joint generation failed: $LASTEXITCODE" }
& $meshPython (Join-Path $project "src\hybrid_apply_joints.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid joint application failed: $LASTEXITCODE" }
if ($buildParameters.hybrid_new.cut_edge_finish) {
    & $meshPython (Join-Path $project "tools\test_cut_edge_finish.py")
    if ($LASTEXITCODE -ne 0) { throw "Local cut-edge finishing regression failed: $LASTEXITCODE" }
}
if ($buildParameters.hybrid_new.palm_size.enabled) {
    & $meshPython (Join-Path $project "tools\test_print_boundary_weld.py")
    if ($LASTEXITCODE -ne 0) { throw "Print boundary weld regression failed: $LASTEXITCODE" }
}
if ($buildParameters.hybrid_new.partition_method -eq 'local_joint_discs') {
    & $meshPython (Join-Path $project "src\validate_anatomy_preservation.py")
    if ($LASTEXITCODE -ne 0) { throw "Original anatomy preservation failed: $LASTEXITCODE" }
}
& $meshPython (Join-Path $project "src\hybrid_validate_assembly.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid assembly collision validation failed: $LASTEXITCODE" }
& $meshPython (Join-Path $project "src\hybrid_validate_motion.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid actual-part motion validation failed: $LASTEXITCODE" }
& $python (Join-Path $project "src\freecad_hybrid_documents.py")
if ($LASTEXITCODE -ne 0) { throw "Hybrid FreeCAD/3MF packaging failed: $LASTEXITCODE" }
if ($buildParameters.hybrid_new) {
    & $python (Join-Path $project "tools\package_parts_review.py")
    if ($LASTEXITCODE -ne 0) { throw "Named 3MF part packaging failed: $LASTEXITCODE" }
}

Write-Host "[5/13] Validating STL topology"
& $python (Join-Path $project "src\validate_stl.py")
if ($LASTEXITCODE -ne 0) { throw "STL validation failed: $LASTEXITCODE" }

Write-Host "[6/13] Validating 3MF packages"
& $python (Join-Path $project "src\validate_3mf.py")
if ($LASTEXITCODE -ne 0) { throw "3MF validation failed: $LASTEXITCODE" }

Write-Host "[7/13] Sweeping ball-joint motion clearance"
& $python (Join-Path $project "src\validate_joint_v2.py")
if ($LASTEXITCODE -ne 0) { throw "Ball-joint motion validation failed: $LASTEXITCODE" }
if ($buildParameters.joint.socket_profile) {
    & $python (Join-Path $project "src\validate_socket_fit.py")
    if ($LASTEXITCODE -ne 0) { throw "Shallow socket fit/capture validation failed: $LASTEXITCODE" }
}

Write-Host "[8/13] Sweeping motion with the actual T. rex parts"
& $python (Join-Path $project "src\validate_assembly_motion.py")
if ($LASTEXITCODE -ne 0) { throw "Assembly motion validation failed: $LASTEXITCODE" }

Write-Host "[9/13] Running equivalent-section CalculiX baseline"
& $python (Join-Path $project "src\cae_coupon.py") --ccx $ccx
if ($LASTEXITCODE -ne 0) { throw "CalculiX baseline failed: $LASTEXITCODE" }

Write-Host "[10/13] Running actual bone Gmsh + CalculiX analysis"
& $python (Join-Path $project "src\cae_actual_bone.py") --gmsh $gmsh --ccx $ccx
if ($LASTEXITCODE -ne 0) { throw "Actual-bone CAE failed: $LASTEXITCODE" }

Write-Host "[11/13] Running v2 ball-stud Gmsh + CalculiX analysis"
& $python (Join-Path $project "src\cae_ball_stud.py") --gmsh $gmsh --ccx $ccx
if ($LASTEXITCODE -ne 0) { throw "Ball-stud CAE failed: $LASTEXITCODE" }
if ($buildParameters.joint_retention_trial) {
    & $python (Join-Path $project 'src/cae_retention_trial.py')
    if ($LASTEXITCODE -ne 0) { throw 'Retention trial comparative CAE failed' }
}

Write-Host "[12/13] Rendering the user review image"
if ($buildParameters.joint_holding_trial) {
    & $python (Join-Path $project 'src/cae_holding_trial.py')
    if ($LASTEXITCODE -ne 0) { throw 'Holding trial comparative CAE failed' }
}
if ($buildParameters.joint_holding_step_trial) {
    & $python (Join-Path $project 'src/cae_holding_step_trial.py')
    if ($LASTEXITCODE -ne 0) { throw 'Holding step trial comparative CAE failed' }
}
if ($buildParameters.joint_workflow_holding_trial) {
    & $python (Join-Path $project 'src/cae_holding_trial.py') 'joint_workflow_holding_trial'
    if ($LASTEXITCODE -ne 0) { throw 'Workflow holding trial CAE failed' }
}
if ($buildParameters.joint_workflow_holding_step_trial) {
    & $python (Join-Path $project 'src/cae_holding_trial.py') 'joint_workflow_holding_step_trial'
    if ($LASTEXITCODE -ne 0) { throw 'R5 holding CAE failed' }
}
if (-not $buildParameters.hybrid_new) {
foreach ($preview in @(@{ Name = "orthographic"; Width = 1200; Height = 720 })) {
    $svg = (Resolve-Path -LiteralPath (Join-Path $project "build\preview\$($preview.Name).svg")).Path
    $png = Join-Path (Split-Path $svg) "$($preview.Name).png"
    & $python (Join-Path $project "tools\render_svg_preview.py") `
        --input $svg --output $png --width $preview.Width --height $preview.Height
    if ($LASTEXITCODE -ne 0) { throw "$($preview.Name) PNG preview rendering failed" }
}
}
$blender = Get-SkeleCADToolPath 'blender'
if (-not (Test-Path -LiteralPath $blender)) { throw "Portable Blender renderer not found: $blender" }
$hybridStl = Join-Path $project "$hybridDirectory/trex_hybrid_assembly.stl"
$hybridPreview = Join-Path $project "build\preview\hybrid_assembly.png"
& $blender --background --python-exit-code 1 --python (Join-Path $project "tools\render_generated_mesh.py") -- --input $hybridStl --output $hybridPreview --view hero
if ($LASTEXITCODE -ne 0) { throw "Hybrid assembly preview rendering failed: $LASTEXITCODE" }
Copy-Item -LiteralPath $hybridPreview -Destination (Join-Path $project "build\preview\assembly.png") -Force
if ($buildParameters.joint_workflow_holding_trial) {
    $fitOutput = Join-Path $project $buildParameters.joint_workflow_holding_trial.output_directory
    & $blender --background --python-exit-code 1 --python (Join-Path $project 'tools/render_generated_mesh.py') -- --input (Join-Path $fitOutput 'print/plate_preview.stl') --output (Join-Path $fitOutput 'print/preview.png') --view hero
    if ($LASTEXITCODE -ne 0) { throw 'Workflow holding trial preview failed' }
}

if ($buildParameters.joint_workflow_holding_step_trial) {
    $fitOutput = Join-Path $project $buildParameters.joint_workflow_holding_step_trial.output_directory
    & $blender --background --python-exit-code 1 --python (Join-Path $project 'tools/render_generated_mesh.py') -- --input (Join-Path $fitOutput 'print/plate_preview.stl') --output (Join-Path $fitOutput 'print/preview.png') --view top
    if ($LASTEXITCODE -ne 0) { throw 'R5 holding preview failed' }
}
if ($buildParameters.hybrid_new.partition_method -eq 'local_joint_discs') {
    & $meshPython (Join-Path $project "tools\render_preservation_review.py")
    if ($LASTEXITCODE -ne 0) { throw "Anatomy preservation review failed" }
}
if ($buildParameters.hybrid_new) {
    & $blender --background --python-exit-code 1 --python (Join-Path $project "tools\render_generated_mesh.py") -- --input $hybridStl --output (Join-Path $project "build\preview\orthographic.png") --view side
    if ($LASTEXITCODE -ne 0) { throw "New assembly side preview failed" }
}
& (Join-Path $project "tools\render_concept_comparison.ps1")
if ($LASTEXITCODE -ne 0) { throw "Concept comparison rendering failed: $LASTEXITCODE" }

Write-Host "[13/13] Creating the user-review bundle and change summary"
& $python (Join-Path $project "src\validate_appearance_candidate.py")
if ($LASTEXITCODE -ne 0) { throw "New appearance candidate validation failed: $LASTEXITCODE" }
& $python (Join-Path $project "src\review_bundle.py") finalize
if ($LASTEXITCODE -ne 0) { throw "Review bundle generation failed: $LASTEXITCODE" }

Write-Host "SkeleCAD build completed: $(Join-Path $project 'build')"
