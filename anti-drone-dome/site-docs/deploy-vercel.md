# Deploy Project LARP docs to Vercel

Public URL goal: **https://projectlarp.vercel.app**

The docs live in this folder (`anti-drone-dome/`). Vercel builds MkDocs and serves the static `public/` output.

---

## One-time setup (Vercel dashboard)

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import **`herman888/defenderproject`**
3. Configure the project:
   - **Project Name:** `projectlarp` (this makes `projectlarp.vercel.app`)
   - **Root Directory:** `anti-drone-dome` ← click Edit and set this
   - **Framework Preset:** Other
   - **Build Command:** `mkdocs build -d public` (or leave — `vercel.json` sets it)
   - **Output Directory:** `public`
   - **Install Command:** `pip3 install -r requirements-docs.txt`
4. Click **Deploy**

After the first deploy succeeds, every push to `main` that changes files under `anti-drone-dome/` will redeploy.

---

## CLI alternative

```bash
# install once
npm i -g vercel

cd anti-drone-dome
vercel login
vercel link --yes --project projectlarp
vercel --prod
```

When asked for root / settings, accept the values from `vercel.json`.

---

## Local preview (unchanged)

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs serve
```

---

## Notes

- Do **not** point Vercel at the repo root — it would try to build the whole monorepo.
- Python sim deps in `requirements.txt` are **not** used for the docs deploy (`requirements-docs.txt` only).
- Custom domain later: Vercel → Project → Settings → Domains.
