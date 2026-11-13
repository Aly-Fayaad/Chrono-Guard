# ASSET_CREDITS.md

All imagery is self-hosted in `/public/assets/space/` (downloaded from NASA's public
image library — **no hotlinking**; the app works fully offline). Procedural assets
(starfield canvas, SVG celestial bodies, orbit rings, gauges, moon-phase indicator,
constellation diagram) are generated in-app and require no attribution.

No NASA insignia (logo, "meatball", "worm") or other agency emblems are used. Nothing
in this product implies NASA endorsement.

| File | Title | NASA ID | Source | Credit line | Used in |
|---|---|---|---|---|---|
| `hub-earthrise.jpg` | A Breathtaking Earthset from Orion | `art002e021278` | https://images.nasa.gov/details/art002e021278 | NASA (Artemis II crew, Orion spacecraft) | Hub background — lunar horizon / Earthrise composition |
| `earth-blue-marble.jpg` | Most Amazing High Definition Image of Earth – Blue Marble 2012 | `GSFC_20171208_Archive_e001386` | https://images.nasa.gov/details/GSFC_20171208_Archive_e001386 | NASA/Goddard Space Flight Center | Earth view panel (Overview Effect) |
| `moon-full.jpg` | Full Moon | `201202070005HQ` | https://images.nasa.gov/details/201202070005HQ | NASA/Bill Ingalls | Moon imagery reserve (check-in detail panel) |
| `nebula-carina.jpg` | James Webb Space Telescope NIRCam Image of the "Cosmic Cliffs" in Carina Nebula | `carina_nebula` | https://images.nasa.gov/details/carina_nebula | NASA, ESA, CSA, STScI | Restore (guided breathing) backdrop |
| `stars-milky-way.jpg` | The Milky Way spans the night sky above a yellow-green airglow | `iss073e0982261` | https://images.nasa.gov/details/iss073e0982261 | NASA/JSC (Expedition 73) | Guidance constellation backdrop reserve |

Notes:

- Images are downloaded at NASA-library "large"/"medium" sizes as JPEG (a WebP
  encoder was not available in this environment; the files are already efficiently
  compressed — total ≈ 1.37 MB, only the 144 KB hub hero is eagerly loaded).
- Suggested conversion for further optimization (optional):
  `cwebp -q 80 in.jpg -o out.webp` then update the `src` references.
- Footer in the app reads: *"Imagery courtesy of NASA. ChronoGuard is not
  affiliated with or endorsed by NASA."* with an "Image credits" link to `#/credits`.
