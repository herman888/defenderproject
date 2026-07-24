# Deploy Project LARP docs to Vercel

Live URL: **https://projectlarp.vercel.app**

Docs are **pre-built** into `anti-drone-dome/public/` and committed. Vercel only **serves** that folder — no `pip` on Vercel.

---

## Vercel settings (required)

**Settings → General**

- **Project Name:** `projectlarp` (this creates `projectlarp.vercel.app`)

**Settings → Build and Deployment:**

| Setting | Value |
|---------|--------|
| **Root Directory** | `anti-drone-dome` |
| **Framework** | Other |
| **Install Command** | `echo 'no install'` (clear any `pip3` override) |
| **Build Command** | `echo 'prebuilt static site'` |
| **Output Directory** | `public` |

Then **Deployments → Redeploy** the newest commit.

If the project was previously named `defenderproject`, rename it to `projectlarp` under **Settings → General → Project Name**, or add `projectlarp.vercel.app` under **Domains**.

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
