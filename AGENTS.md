# 3D modelling workspace instructions

- The active production project is `skelecad/`.
- Before any modelling task, read `skelecad/AGENTS.md`,
  `skelecad/config/parameters.json`, and `skelecad/docs/DESIGN.md`.
- Treat `legacy_prototypes/` as read-only reference unless the user explicitly
  asks to restore something from it.
- After a geometry or material change, run `skelecad/tools/build.ps1` and report
  the CAD, STL topology, assembly collision, and CalculiX results.
- Regenerate `skelecad/build/preview/assembly.png` after assembly changes so the
  user can review the result in ChatGPT.
- Converse with the user in Japanese; keep parameter and file names stable.
