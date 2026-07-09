# Ilona OS v3 — static GitHub Pages version

Upload these files/folders at the root of your GitHub repository:

- `assets/`
- `.nojekyll`
- `index.html`
- `manifest.webmanifest`
- `sw.js`
- `README_DEPLOY_STATIC.md`

Then go to:

Settings → Pages → Source: Deploy from a branch → Branch: main → Folder: /root → Save

No GitHub Actions needed.

## Data
Everything is saved locally in the browser. Use Settings → Export all data JSON often, especially before clearing browser data.

## Phone
Open the GitHub Pages link on your phone, then use “Add to Home screen”. This version includes a PWA manifest and service worker.
