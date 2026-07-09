# Aurelia OS V2 — static GitHub Pages version

Upload the **contents** of this folder to a public GitHub repository:

- `index.html`
- `assets/`
- `favicon.svg`
- `.nojekyll`
- `README_DEPLOY_STATIC.md`

Then go to **Settings → Pages** and set:

- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/root**

No build, no GitHub Actions, no paid backend.

## Optional Google Calendar connection

The app works without keys using manual events and `.ics` import. For direct Google Calendar read access:

1. Go to Google Cloud Console.
2. Create/select a project.
3. Enable **Google Calendar API**.
4. Create an **OAuth Client ID** for a **Web application**.
5. Add your GitHub Pages origin, for example: `https://YOURNAME.github.io`.
6. Copy the Client ID into the app: **Settings → Google Calendar Client ID**.

This is a browser OAuth Client ID, not a secret. Do not put API secrets in a static GitHub Pages app.

## Data updates without coding

Use **Settings → Export Data** to save your app data.
Use **Settings → Import Data** to restore it.
Use **Settings → Import Data Pack** to add new knowledge cards, links, hidden-gem books, workouts, or skincare notes from a JSON file.
