# Testing and release checks

## Code tests

```powershell
python -m pytest -q
```

## Documentation

```powershell
mkdocs build --strict
mkdocs serve
```

The committed Vercel site is generated separately:

```powershell
mkdocs build --strict -d public
```

## Operational regression

```powershell
python scripts\run_regression_campaign.py `
  --repeats 100 `
  --seed 1000 `
  --output validation_reports\regression_campaign
```

## Release evidence checklist

- tests pass in the target environment;
- MkDocs strict build has no missing nav entries or links;
- campaign and hardware reports retain seeds and profile IDs;
- screenshots are paired with live state where making dynamic claims;
- mission manifests are complete and hashes verify;
- synthetic and hardware claims remain clearly separated.

