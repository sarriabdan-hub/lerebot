# Vial-Sort Report — `docs/`

LaTeX report and supporting markdown for the language-conditioned vial-sorting
project. Written to be compiled in **Overleaf** (do **not** run locally).

## Contents
```
docs/
├── main.tex              # the report (compile this)
├── references.bib        # bibliography (BibTeX)
├── README.md             # this file
├── imgs/                 # <- drop your figure PNGs here (names must match main.tex)
│   └── README.md
├── imgs_links/
│   └── figures.md        # every figure: caption, what to capture, and SOURCE file
└── sections/             # the report content as editable markdown
    ├── 01_system_setup.md
    ├── 02_data_collection.md
    ├── 03_perception_depth.md
    ├── 04_training.md
    └── 05_experiments.md
```

## Build in Overleaf
1. Create a new project and upload `main.tex`, `references.bib`, and the `imgs/`
   folder with your figures.
2. Menu → Compiler: **pdfLaTeX**. Bibliography: **BibTeX**.
3. Compile order (Overleaf does this automatically on repeated compiles):
   `pdfLaTeX → BibTeX → pdfLaTeX → pdfLaTeX`.

## Figures
`main.tex` currently shows grey **placeholder boxes** so it compiles with no
images. For each figure, add the PNG to `imgs/` with the exact filename, then
**uncomment the `\includegraphics` line** and delete the matching
`\figplaceholder{...}` line. The list of figures, what each should show, and
where to get the source is in **`imgs_links/figures.md`**.

## Notes
- The `sections/*.md` files hold the same content as the report in plain
  markdown, for reading and editing outside LaTeX.
- Verify the citation details in `references.bib` (arXiv IDs / venues) before any
  formal submission.
- Author attribution: the physical rig was assembled and calibrated by the
  author; data collection, training, and evaluation were collaborative.
