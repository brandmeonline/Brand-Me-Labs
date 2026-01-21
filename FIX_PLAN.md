# Brand-Me-Labs Fix Implementation Plan

This document outlines the systematic approach to fixing all issues identified in the repository diagnostic audit.

## Fix Priority Overview

| Priority | Issue ID | Description | Effort | Status |
|----------|----------|-------------|--------|--------|
| P0-1 | FIX-001 | Merge conflicts in `brandme-cube/src/main.py` | 30 min | PENDING |
| P0-2 | FIX-002 | Duplicate services in `docker-compose.yml` | 20 min | PENDING |
| P1-1 | FIX-003 | Rename `.env.*` to `.env.*.example` | 5 min | PENDING |
| P1-2 | FIX-004 | Add `.editorconfig` | 5 min | PENDING |
| P1-3 | FIX-005 | Add `.nvmrc` | 2 min | PENDING |
| P1-4 | FIX-006 | Add `.python-version` | 2 min | PENDING |
| P1-5 | FIX-007 | Create `SECURITY.md` | 10 min | PENDING |
| P1-6 | FIX-008 | Create `CONTRIBUTING.md` | 15 min | PENDING |
| P1-7 | FIX-009 | Add `.github/dependabot.yml` | 10 min | PENDING |
| P2-1 | FIX-010 | Add `.github/CODEOWNERS` | 5 min | PENDING |
| P2-2 | FIX-011 | Add `.github/pull_request_template.md` | 10 min | PENDING |
| P2-3 | FIX-012 | Add `.github/ISSUE_TEMPLATE/` | 15 min | PENDING |
| P2-4 | FIX-013 | Add `.pre-commit-config.yaml` | 10 min | PENDING |

---

## Detailed Fix Procedures

### FIX-001: Merge Conflicts in brandme-cube/src/main.py

**Problem:** File contains duplicate imports, duplicate docstrings, syntax errors from unresolved merge conflicts.

**Method:**
1. Read current file content
2. Identify and remove duplicate imports
3. Consolidate docstrings to single v9 version
4. Remove duplicate variable declarations
5. Fix duplicate function definitions
6. Validate Python syntax

**Validation:** `python -m py_compile brandme-cube/src/main.py`

---

### FIX-002: Duplicate Services in docker-compose.yml

**Problem:** `spanner-emulator`, `spanner-init`, and `cube` service have duplicate definitions.

**Method:**
1. Read current docker-compose.yml
2. Identify all duplicate service blocks
3. Merge configurations, keeping the most complete version
4. Remove YAML syntax errors
5. Validate YAML structure

**Validation:** `docker-compose config`

---

### FIX-003: Rename Environment Files

**Problem:** Actual environment files committed to repository instead of examples.

**Method:**
1. Rename `.env.development` to `.env.development.example`
2. Rename `.env.production` to `.env.production.example`
3. Rename `.env.staging` to `.env.staging.example`
4. Update `.gitignore` to exclude actual env files

**Validation:** Files renamed, gitignore updated

---

### FIX-004: Add .editorconfig

**Problem:** No editor configuration for consistent formatting.

**Method:** Create `.editorconfig` with settings for:
- UTF-8 encoding
- LF line endings
- 2-space indent for JS/TS/YAML
- 4-space indent for Python
- Trim trailing whitespace

**Validation:** File exists with correct content

---

### FIX-005: Add .nvmrc

**Problem:** No Node.js version pinning.

**Method:** Create `.nvmrc` with `18.17.0`

**Validation:** `nvm use` works (if nvm installed)

---

### FIX-006: Add .python-version

**Problem:** No Python version pinning.

**Method:** Create `.python-version` with `3.11`

**Validation:** `pyenv local` works (if pyenv installed)

---

### FIX-007: Create SECURITY.md

**Problem:** No security vulnerability disclosure policy.

**Method:** Create comprehensive security policy with:
- Supported versions
- Reporting process
- Response timeline
- Scope definition
- Security best practices

**Validation:** File exists with all sections

---

### FIX-008: Create CONTRIBUTING.md

**Problem:** No contribution guidelines.

**Method:** Create contribution guide with:
- Prerequisites
- Setup instructions
- Branch naming conventions
- Commit message format
- PR process
- Code standards

**Validation:** File exists with all sections

---

### FIX-009: Add dependabot.yml

**Problem:** No automated dependency updates.

**Method:** Create `.github/dependabot.yml` with:
- npm updates for all Node packages
- pip updates for all Python packages
- Docker image updates
- GitHub Actions updates
- Terraform updates

**Validation:** File exists with correct YAML

---

### FIX-010: Add CODEOWNERS

**Problem:** No code ownership definition.

**Method:** Create `.github/CODEOWNERS` mapping:
- Infrastructure files to devops team
- Frontend to frontend team
- Backend to backend team
- Security files to security team

**Validation:** File exists with correct syntax

---

### FIX-011: Add PR Template

**Problem:** No pull request template.

**Method:** Create `.github/pull_request_template.md` with:
- Description section
- Type of change checkboxes
- Testing checklist
- Reviewer notes

**Validation:** File exists

---

### FIX-012: Add Issue Templates

**Problem:** No issue templates.

**Method:** Create:
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/ISSUE_TEMPLATE/config.yml`

**Validation:** Files exist

---

### FIX-013: Add Pre-commit Config

**Problem:** No pre-commit hooks for code quality.

**Method:** Create `.pre-commit-config.yaml` with:
- Trailing whitespace checks
- YAML/JSON validation
- Python formatting (black, ruff)
- TypeScript linting
- Secret detection

**Validation:** `pre-commit run --all-files` works

---

## Execution Order

1. P0 fixes first (critical blockers)
2. P1 fixes (high priority governance)
3. P2 fixes (medium priority improvements)
4. Commit after each logical group
5. Push to branch
6. Create PR for review

---

*Plan created: 2026-01-21*
