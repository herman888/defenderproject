# Contributing (add docs)

This site is **MkDocs Material**. Edit Markdown under `documentation/`; the
sidebar comes from `mkdocs.yml`.

---

## Run locally

```bash
cd anti-drone-dome
python3 -m venv .venv-docs
source .venv-docs/bin/activate
pip install -r requirements-docs.txt
mkdocs serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Edits auto-reload.

Next time (venv already created):

```bash
cd anti-drone-dome
source .venv-docs/bin/activate
mkdocs serve
```

Build static HTML (optional):

```bash
mkdocs build --strict
# output in anti-drone-dome/public/
```

---

## Add a new page

1. Create a file, e.g. `documentation/hardware/battery.md`
2. Write Markdown (headings, tables, code fences)
3. Register it in `mkdocs.yml` under `nav:`:

```yaml
  - Hardware:
      - Overview: hardware/overview.md
      - Flight Controllers: hardware/flight-controllers.md
      - Radio: hardware/radio.md
      - Battery: hardware/battery.md   # ← new
```

4. Save — the sidebar updates on refresh

---

## Add a new section

1. Create a folder: `documentation/guidance/`
2. Add `overview.md` (or any page)
3. Add a nav block in `mkdocs.yml`:

```yaml
  - Guidance:
      - Overview: guidance/overview.md
      - Intercept: guidance/intercept.md
```

---

## Style tips

- Use `!!! note` / `!!! warning` admonitions (Material)
- Prefer relative links: `[Radio](hardware/radio.md)`
- Keep one source of truth under `documentation/`; repository READMEs should
  link here rather than duplicate procedures.

---

## Deploy to Vercel

See [Deploy to Vercel](deploy-vercel.md) for connecting this docs site to **projectlarp.vercel.app**.
