# Deploy Project LARP docs to Vercel

Public URL goal: **https://projectlarp.vercel.app** (or `defenderproject.vercel.app` if you keep that name)

The docs live in this folder (`anti-drone-dome/`). Vercel builds MkDocs and serves the static `public/` output.

---

## One-time setup (Vercel dashboard)

1. Go to [vercel.com/new](https://vercel.com/new) (or use your existing **defenderproject** Vercel project)
2. Import / connect **`herman888/defenderproject`**
3. **Settings → Build and Deployment:**
   - **Root Directory:** `anti-drone-dome` ← required
   - **Framework Preset:** Other
   - **Install Command:** `true`
   - **Build Command:** `python3 -m pip install -r requirements-docs.txt && python3 -m mkdocs build -d public`
   - **Output Directory:** `public`
4. **Deployments → Redeploy**

`vercel.json` in this folder already sets those commands for new deploys.

After a green deploy, every push to `main` under `anti-drone-dome/` will update the site.

---

## Fix: `pip3 install ... exited with 1`

That means Vercel’s Install step couldn’t run `pip3` (common). Use **Install = `true`** and put pip inside **Build Command** with `python3 -m pip` (see above). Then Redeploy.

Also confirm **Root Directory** is exactly `anti-drone-dome` so `requirements-docs.txt` is found.

---

## CLI alternative

```bash
npm i -g vercel
cd anti-drone-dome
vercel login
vercel link --yes --project projectlarp
vercel --prod
```

---

## Local preview

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs serve
```

---

## Notes

- Do **not** leave Root Directory empty — that builds the whole monorepo.
- Do **not** use `requirements.txt` for the docs build (that’s the sim stack). Docs use `requirements-docs.txt` only.
