# UnifoLM-WorldPred-1 Website

Static GitHub Pages release. The site entry point is `index.html`.

## Refresh with high-quality open-loop results

Build the manifest and replace published video assets from a result directory that
contains `individual_views/`:

```bash
python3 build_high_quality_manifest.py /path/to/high_quality_openloop_10hz .
```

The generator validates every GT/prediction view before replacing `videos/`.
It retains one representative sample per task, except in the external tabletop
section, which retains both samples of each task for side-by-side comparison.

## Local preview

```bash
python3 -m http.server 8088
```

Then open `http://localhost:8088/`.
