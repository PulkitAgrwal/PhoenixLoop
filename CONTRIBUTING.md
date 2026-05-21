# Contributing to PhoenixLoop

## Rules

### 1. Never commit secrets

API keys, tokens, passwords, and credentials must never appear in code or git history. We enforce this at three levels:

| Layer | What it does | When it catches secrets |
|---|---|---|
| **GitHub Secret Scanning + Push Protection** | GitHub's built-in scanner with 200+ provider patterns | Blocks the push before it lands in the repo |
| **Gitleaks (CI)** | Scans every commit in every PR with 700+ regex rules | Blocks the PR from merging |
| **`.gitignore`** | Prevents `.env`, `*.pem`, `*.key` from being staged | Before you even commit |

**Rules:**
- All secrets go in `.env` (which is gitignored)
- Use `.env.example` for placeholder values that get committed
- If you accidentally commit a secret: **rotate the key immediately**, then clean git history

**What counts as a secret:**
- API keys (`GOOGLE_API_KEY`, `PHOENIX_API_KEY`)
- Tokens (JWT, OAuth, session tokens)
- Passwords and connection strings with credentials
- Private keys (SSH, TLS)

**Enable GitHub Secret Scanning (repo admin):**
1. Go to your repo → **Settings** → **Code security**
2. Enable **"Secret scanning"** — scans for known provider token formats (Google, AWS, etc.)
3. Enable **"Push protection"** — blocks pushes that contain detected secrets *before* they enter git history
4. This is free for public repos. For private repos, requires GitHub Advanced Security.

### 2. Never commit directly to main

All changes go through a branch + pull request. No exceptions.

**Workflow:**
```bash
# 1. Make sure you're on latest main
git checkout main
git pull origin main

# 2. Cut a new branch
git checkout -b feat/your-feature-name

# 3. Do your work, commit
git add <files>
git commit -m "add: description of what you did"

# 4. Push and open a PR
git push -u origin feat/your-feature-name
# Then open a PR on GitHub
```

**Branch naming:**
| Prefix | Use for | Example |
|---|---|---|
| `feat/` | New features | `feat/experiment-dashboard` |
| `fix/` | Bug fixes | `fix/db-connection-leak` |
| `refactor/` | Code restructuring | `refactor/eval-runner` |
| `docs/` | Documentation only | `docs/deployment-guide` |
| `chore/` | Config, CI, tooling | `chore/add-docker-compose` |

### 3. PR descriptions are mandatory

Every pull request must have a meaningful description. Use the PR template (auto-loaded when you create a PR).

A good PR description answers:
- **What** changed?
- **Why** did it change?
- **How** can it be tested?

PRs with empty descriptions will be rejected.

### 4. CI must pass before merge

All GitHub Actions checks must be green before a PR can be merged:
- Backend tests (pytest)
- Frontend lint (ESLint)
- Frontend type check (tsc)
- Frontend build (next build)
- Docker build (both images)
- Secret scan (no leaked credentials)

Do not merge with failing checks. Fix them first.

### 5. Keep commits atomic

Each commit should be one logical change. Don't combine unrelated changes in a single commit.

**Good:**
```
add: failure aggregation threshold config
fix: release gate score calculation overflow
```

**Bad:**
```
update stuff
fix everything
wip
```

**Commit message format:**
```
<type>: <short description>

<optional body explaining why>
```

Types: `add`, `fix`, `update`, `refactor`, `docs`, `chore`, `test`

### 6. No force-push to main

Force-pushing to `main` rewrites shared history and can destroy other people's work. It is never acceptable.

If you need to fix a bad commit on main, revert it with a new commit:
```bash
git revert <commit-hash>
```

### 7. Review before merge

Read your own diff before requesting review. Check for:
- Leftover debug code (`console.log`, `print()`)
- Hardcoded values that should be in config
- Missing error handling on external calls
- Type safety (no `any` in TypeScript, no `Any` in Python)

---

## Setting Up Branch Protection on GitHub

To enforce these rules at the repository level:

1. Go to your repo on GitHub → **Settings** → **Branches**
2. Click **"Add branch protection rule"**
3. Set **Branch name pattern** to `main`
4. Enable these settings:

| Setting | Enable | Why |
|---|---|---|
| **Require a pull request before merging** | Yes | Enforces Rule 2 (no direct commits to main) |
| **Require approvals** (set to 1) | Optional | Useful if working in a team |
| **Require status checks to pass before merging** | Yes | Enforces Rule 4 (CI must pass) |
| **Require branches to be up to date before merging** | Yes | Prevents merge conflicts |
| **Do not allow bypassing the above settings** | Yes | Applies rules to admins too |
| **Restrict force pushes** | Yes | Enforces Rule 6 |
| **Restrict deletions** | Yes | Prevents accidental branch deletion |

5. Under **"Require status checks"**, add these checks:
   - `Backend Checks`
   - `Frontend Checks`
   - `Docker Build`
   - `Secret Scan`

6. Click **"Save changes"**

---

## Local Development Workflow

```
main (protected)
  │
  ├── feat/your-feature ← you work here
  │     │
  │     ├── commit 1
  │     ├── commit 2
  │     └── commit 3
  │
  └── PR: feat/your-feature → main
        │
        ├── CI checks pass?
        ├── Description filled out?
        ├── No secrets detected?
        └── ✅ Merge
```
