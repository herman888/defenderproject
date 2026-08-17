# Deploy Project LARP docs to Vercel

**Canonical (protected) docs URL:** `https://docs.projectlarp.com`  
**Public landing:** `https://www.projectlarp.com` (needs DNS — see [Access control](access-control.md)).

Docs are **pre-built** into `anti-drone-dome/public/` and committed. Vercel only
**serves** that folder — no `pip` on Vercel.

---

## If the build is red (checklist)

Open **Settings → Build and Deployment**. Turn **Override** OFF unless the value
matches the table.

| Setting | Required value |
|---------|----------------|
| **Root Directory** | `anti-drone-dome` |
| **Framework Preset** | Other (**not** Python, **not** Next.js) |
| **Install Command** | `true` (never `pip3`) |
| **Build Command** | `true` |
| **Output Directory** | `public` |

Then **Deployments → Redeploy** commit `7387c14` (or newer).

If Root Directory is the **repo root**, Output Directory must be
`anti-drone-dome/public`.

---

## Domains

Add in Vercel → Domains: `docs.projectlarp.com`, `www.projectlarp.com`, `projectlarp.com`.

Cloudflare DNS (proxied): `docs`, `www`, and `@` CNAME → `cname.vercel-dns.com`.

Access only on **docs** — not on www/apex.

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
