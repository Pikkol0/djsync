# Security policy

## Supported versions

| Version | Supported |
|---|---|
| Latest stable release | ✅ |
| Current pre-release (`-rc`) | ✅ |
| Older versions | ❌ — please update first (in *Settings*, the update check: *Check now*) |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting instead: **[Report a vulnerability](https://github.com/Pikkol0/djsync/security/advisories/new)**
(repository ▸ *Security* tab ▸ *Report a vulnerability*). Describe the problem, the affected version
and system, and how to reproduce it. Do not attach your Rekordbox library or USB drive contents.

What to expect: an acknowledgement within about a week (DJSync is maintained in spare time), then a
fix in the next release when the report is confirmed, with credit in the release notes if you wish.

## Scope

DJSync runs locally: it downloads music with yt-dlp, reads and writes Rekordbox databases and files on
your computer and USB drives, and checks GitHub for updates. Relevant reports include, for example:
writing outside the selected drive or library, a crafted file or database crashing DJSync or running
code, or the update mechanism installing something other than an official release.

---

**En français :** ne publiez pas de faille dans une issue publique ; utilisez
[Report a vulnerability](https://github.com/Pikkol0/djsync/security/advisories/new) (onglet *Security*
du dépôt). Seules la dernière version stable et la pré-version en cours sont suivies.
