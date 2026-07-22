# Pixel anchors

The production art uses one canonical morning-newsroom frame and four sparse
transparent overlays for the presenters' talking and blinking states. Keeping
the background, bodies, and palette in a single base image prevents the visual
noise that appears when image-generation variants are animated as full frames.

`newsroom.png` contains both presenters with closed mouths. The other PNGs are
full-canvas overlays whose transparent pixels leave the base unchanged. The
renderer uses nearest-neighbor scaling so the pixel edges stay crisp.

Only ChatGPT and Claude are currently supported. Other configured speakers use
the renderer's existing safe fallback.
