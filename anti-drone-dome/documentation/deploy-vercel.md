# Deploy Project LARP docs to Vercel

Live URL (after a green deploy): **https://defenderproject.vercel.app**  
(Rename the Vercel project to `projectlarp` if you want `projectlarp.vercel.app`.)

Docs are **pre-built** into `anti-drone-dome/public/` and committed. Vercel only **serves** that folder — no `pip` on Vercel.

---

## Vercel settings (required)

**Settings → Build and Deployment:**

| Setting | Value |
|---------|--------|
| **Root Directory** | `anti-drone-dome` |
| **Framework** | Other |
| **Install Command** | `echo 'no install'` (clear any `pip3` override) |
| **Build Command** | `echo 'prebuilt static site'` |
| **Output Directory** | `public` |

Then **Deployments → Redeploy** the **newest** commit (not the old red one).

---

## After you edit docs locally

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs build -d public
git add public documentation mkdocs.yml
git commit -m "Update Project LARP docs"
git push
```

Vercel will redeploy automatically.

---

## Local preview

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs serve
```
