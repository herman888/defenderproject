# Security and privacy

This documentation describes a **confidential research and validation platform**
(Project LARP / AEGIS). It is shared **only with people we invite**, under our
request and permission (typically after an NDA or equivalent agreement).

!!! danger "Not a public product site"
    If you reached these pages without an invitation, do not copy, redistribute,
    or rely on the material. Contact the maintainers and close the session.

---

## Access model

| Topic | Practice |
|-------|----------|
| Who can read | Allowlisted email identities only |
| How you sign in | **Cloudflare Zero Trust Access** — email one-time PIN and/or Google |
| What we host | Prebuilt static MkDocs on Vercel, behind Cloudflare |
| Public browsing | **Not allowed** on the protected hostname |
| Operator runbook | [Access control](access-control.md) |

We do **not** use a password form inside the static site as the security boundary.
Authentication happens **before** page HTML is served.

To request access, email the maintainers (project contact: site author /
`herman.isayenka1@gmail.com` or the address given in your invitation) with:

- Your name and organization
- Work email to allowlist
- Purpose of review
- Confirmation you will not redistribute materials without written approval

---

## Intellectual property

- Documentation, software descriptions, architectures, evidence summaries, and
  related Work Product are proprietary to the project owners / company as defined
  in your agreement.
- Access is a **license to view** for the stated purpose — not a grant to copy
  into other products, train models on the corpus, or publish excerpts.
- Screenshots, exports, and downloads (if any) remain confidential.
- Internal tooling or second contractors must follow the same confidentiality
  rules; team outputs remain company Work Product where your contract says so.

---

## Privacy (authentication)

When you authenticate via Cloudflare Access:

- Cloudflare processes your **email** (and Google account attributes if you use
  Google) to complete login and enforce policy.
- Session cookies keep you signed in for the configured duration (operators
  typically use about 24 hours).
- We use identity for **access control and abuse prevention**, not for marketing.
- Auth logs may show successful/failed access attempts to operators of the
  Cloudflare account.

The documentation site itself is static content. It does not need an application
user database for reading pages. Do not submit secrets, credentials, or personal
data into docs issue trackers unless a maintainer asks through a secure channel.

---

## What this site is not

- Not a certified field C-UAS system
- Not export-controlled delivery by itself — still follow applicable law and your
  contract before sharing with additional parties
- Not authorization to operate hardware, weapons, or RF effectors
- Synthetic intercept and lab results are **not** real-world kill-probability or
  certification evidence

See [Implementation status](system/implementation-status.md) and
[Current evidence](results/current-evidence.md) for capability boundaries.

---

## Your responsibilities as a reader

1. Keep login credentials and OTP codes private; do not forward magic/OTP mail.
2. Do not share the docs URL broadly; access is per identity.
3. Do not scrape, mirror, or upload content to public AI/tools without approval.
4. Report suspected leaks to the maintainers immediately.
5. Stop using the site when your engagement or NDA ends; expect access to be revoked.

---

## Operator responsibilities (summary)

Maintainers must keep Access allowlists current, block unprotected Vercel
hostnames, and keep the source repository from publicly exposing the same IP.
Full checklist: [Access control](access-control.md).
