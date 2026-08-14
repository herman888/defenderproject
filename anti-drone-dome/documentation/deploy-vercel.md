# Deploy Project LARP docs to Vercel

**Canonical (protected) docs URL:** `https://docs.projectlarp.com`  
**Public landing:** `https://www.projectlarp.com` and `https://projectlarp.com` (requires `www` + apex DNS — see [Access control](access-control.md)).

**Vercel default hostname:** `https://projectlarp.vercel.app` — treat as
**non-public** after cutover (block, protect, or redirect). Do not share it as
the partner URL.

Docs are **pre-built** into `anti-drone-dome/public/` and committed. Vercel only
**serves** that folder — no `pip` on Vercel. Authentication is **not** implemented
in MkDocs; it is enforced by Cloudflare in front of the custom domain.

Partner policy: [Security and privacy](security-privacy.md).

---

## Vercel settings (required)

**Settings → General**

- **Project Name:** `projectlarp` (creates `projectlarp.vercel.app`)

**Settings → Build and Deployment:**

| Setting | Value |
|---------|--------|
| **Root Directory** | `anti-drone-dome` |
| **Framework** | Other |
| **Install Command** | `echo 'no install'` (clear any `pip3` override) |
| **Build Command** | `echo 'prebuilt static site'` |
| **Output Directory** | `public` |

Then **Deployments → Redeploy** the newest commit.

If the project was previously named `defenderproject`, rename it to `projectlarp`
under **Settings → General → Project Name**, or add `projectlarp.vercel.app`
under **Domains**.

### Custom domain (required for Access)

1. Add `docs.yourdomain.com` (or your chosen host) under **Settings → Domains**.
2. Create the matching **proxied** DNS record in Cloudflare.
3. Complete the Access application and allowlist in
   [Access control](access-control.md).
4. Block or redirect `projectlarp.vercel.app` so it cannot bypass Access.
5. Set GitHub repository visibility to **private** (or keep sensitive docs out of
   public git) — site auth does not hide source.

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

Vercel will redeploy automatically. Access policies are edited in the Cloudflare
Zero Trust dashboard, not in this repo.

When the protected hostname is live, set `site_url` in `mkdocs.yml` to that URL
before rebuilding so sitemaps and canonical links match.

---

## Local preview

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs serve
```

Local `mkdocs serve` has **no** Cloudflare gate — use only on trusted machines.
