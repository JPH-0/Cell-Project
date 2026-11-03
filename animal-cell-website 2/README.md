# Animal Cell

An interactive 3D animal cell by Joseph. Watch the title write itself, cut the cell in half, and tap the glowing dots to learn what each part does.

## What's in this folder

| File | What it is |
|---|---|
| `index.html` | The website |
| `animal_cell_full.glb` | Closed cell, used for the intro and "Cut in half" |
| `animal_cell.glb` | Cutaway cell, used for "Explore the model" |
| `blender/animal_cell.py` | Blender script that builds both 3D models |

## Put it online (GitHub + Vercel)

1. On github.com, click **New repository**, name it `animal-cell-website`, and click **Create repository**.
2. Click **uploading an existing file**. Drag in everything that's *inside* this folder (not the folder itself), then click **Commit changes**.
3. On vercel.com, click **Add New → Project**, then **Import** your `animal-cell-website` repository.
4. Leave **Framework Preset** on **Other** and click **Deploy**.

Vercel gives you a link like `https://animal-cell-website.vercel.app`. Any time you upload changed files to GitHub, Vercel updates the site by itself.

## Rebuilding the 3D models

Open Blender, go to the **Scripting** tab, open `blender/animal_cell.py`, and click **Run Script**. It saves `animal_cell.glb` to `Desktop/AnimalCell`. For the closed cell, change the `MAKE_FULL_CELL = ...` line near the top to `MAKE_FULL_CELL = True` and run it again to get `animal_cell_full.glb`. Copy both into this folder.
