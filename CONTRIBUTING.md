# Contributing to Brand.Me Labs

Thank you for your interest in contributing to Brand.Me Labs! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Pull Requests](#pull-requests)
- [Release Process](#release-process)

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Please treat all contributors with respect and professionalism.

## Getting Started

### Prerequisites

- **Node.js** 18+ (see `.nvmrc`)
- **Python** 3.11+ (see `.python-version`)
- **Docker** and **Docker Compose**
- **pnpm** 8+
- **kubectl** and **helm** (for deployment)

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/brandmeonline/Brand-Me-Labs.git
cd Brand-Me-Labs

# Install Node.js dependencies
pnpm install

# Install Python dependencies (for services)
pip install -r brandme_core/requirements.txt

# Start local development environment
make dev-up

# Verify services are running
make health-check
```

### Environment Configuration

1. Copy example environment files:
   ```bash
   cp .env.development.example .env.development
   ```

2. Update with your local settings (API keys, etc.)

3. Never commit actual `.env` files - only `.env.*.example`

## Development Workflow

### Branch Naming

Use the following prefixes:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feature/` | New features | `feature/add-molecular-face` |
| `fix/` | Bug fixes | `fix/consent-graph-query` |
| `docs/` | Documentation | `docs/update-api-guide` |
| `refactor/` | Code refactoring | `refactor/spanner-pool` |
| `test/` | Test additions | `test/cube-service-unit` |
| `chore/` | Maintenance | `chore/update-deps` |

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples**:

```bash
feat(cube): add molecular data face endpoint

- Add GET /cubes/{id}/molecular endpoint
- Implement molecular data validation
- Add unit tests

Closes #123
```

```bash
fix(consent): resolve graph traversal timeout

Increased query timeout from 10s to 30s for deep consent graphs.

Fixes #456
```

### Making Changes

1. Create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature
   ```

2. Make your changes

3. Run tests locally:
   ```bash
   make test
   ```

4. Run linting:
   ```bash
   make lint
   ```

5. Commit your changes (see commit message format above)

6. Push and open a PR

## Code Standards

### TypeScript

- Use ESLint configuration (`.eslintrc`)
- Use Prettier for formatting
- Prefer `const` over `let`
- Use async/await over callbacks
- Add types to all function parameters
- Export types from module index files

```typescript
// Good
export async function getCube(id: string): Promise<Cube> {
  const cube = await cubeService.findById(id);
  return cube;
}

// Avoid
export function getCube(id) {
  return cubeService.findById(id).then(cube => cube);
}
```

### Python

- Use Black for formatting (`black --line-length=100`)
- Use Ruff for linting
- Use type hints for all functions
- Follow PEP 8 conventions
- Use async functions for I/O operations

```python
# Good
async def get_cube(cube_id: str) -> Cube:
    """Get a cube by ID."""
    return await cube_service.find_by_id(cube_id)

# Avoid
def get_cube(cube_id):
    return cube_service.find_by_id(cube_id)
```

### SQL (Spanner)

- Use UPPER_CASE for keywords
- Use snake_case for table/column names
- Add comments for complex queries
- Use parameterized queries (never string interpolation)

```sql
-- Good
SELECT user_id, display_name, trust_score
FROM Users
WHERE region_code = @region
  AND is_active = TRUE
ORDER BY created_at DESC;
```

## Testing

### Test Structure

```
tests/
├── unit/           # Unit tests (fast, isolated)
├── integration/    # Integration tests (database, services)
└── e2e/            # End-to-end tests (full system)
```

### Running Tests

```bash
# Run all tests
make test

# Run Python tests only
make test-python

# Run TypeScript tests only
make test-ts

# Run with coverage
make test-coverage
```

### Test Requirements

- **Unit tests**: Required for all new functions
- **Integration tests**: Required for API endpoints
- **Coverage target**: 80% minimum

### Writing Tests

```python
# Python example
import pytest
from brandme_core.spanner.consent_graph import ConsentGraphClient

@pytest.mark.asyncio
async def test_get_consent_for_user(consent_graph: ConsentGraphClient):
    """Test consent retrieval for a user."""
    # Arrange
    user_id = "test-user-123"

    # Act
    consents = await consent_graph.get_consents(user_id)

    # Assert
    assert len(consents) > 0
    assert all(c.user_id == user_id for c in consents)
```

```typescript
// TypeScript example
import { describe, it, expect } from 'vitest';
import { buildCardanoTx } from '../services/blockchain';

describe('buildCardanoTx', () => {
  it('should return a valid transaction hash', async () => {
    // Arrange
    const data = { scanId: 'test-scan', garmentId: 'test-garment' };

    // Act
    const txHash = await buildCardanoTx(data);

    // Assert
    expect(txHash).toMatch(/^[a-f0-9]{64}$/);
  });
});
```

## Pull Requests

### Before Submitting

- [ ] Tests pass locally (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow convention
- [ ] Branch is up to date with `main`

### PR Template

Your PR description should include:

1. **Summary**: What does this PR do?
2. **Type**: Feature / Fix / Docs / Refactor / Test
3. **Testing**: How was this tested?
4. **Screenshots**: (if UI changes)
5. **Breaking Changes**: (if any)

### Review Process

1. At least 1 approval required
2. All CI checks must pass
3. CODEOWNERS will be auto-assigned
4. Address all review comments

## Release Process

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

Releases are managed by the core team. To request a release:

1. Ensure all features are merged to `main`
2. Create a release PR with changelog
3. Tag release after approval

## Questions?

- **GitHub Discussions**: For general questions
- **Issues**: For bugs and feature requests
- **Slack**: #brandme-dev (internal team)

---

Thank you for contributing to Brand.Me Labs!
