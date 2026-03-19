# Development Workflow

This guide covers the complete workflow for developing and shipping code changes.

## Prerequisites

1. **Docker must be running** - The entire application stack runs in Docker
2. **Run all verification commands in Docker** - Never run lint, tests, or build commands on the host

## 1. Issue Investigation

Before writing any code, fully understand the issue:

### 1.1 Get Full Context

```bash
# Get the issue with all comments
gh issue view <issue-number> --comments

# Check for related PRs mentioned in the issue
gh issue view <issue-number> --json body
```

Read:

- Complete issue description
- Every comment on the issue
- Any linked PRs mentioned in comments
- Any related or linked issues

### 1.2 Understand the Problem

- Reproduce the issue if possible
- Identify root cause by tracing through relevant code
- Check if there's already a PR addressing a similar issue

### 1.3 Review Implementation Guidance

If the issue has maintainer comments:

- Pay attention to explicit preferences or constraints
- Check if the issue author suggested a specific approach
- Look for links to related PRs that added the relevant code

## 2. Development Setup

### 2.1 Ensure Docker is Running

```bash
docker compose ps
```

If containers aren't running:

```bash
docker compose up -d
```

### 2.2 Initialize Submodules (First Time Only)

```bash
make git
```

## 3. Create Working Environment

### 3.1 Create a Git Worktree (Recommended)

Worktrees keep your feature branch isolated from the main work directory:

```bash
# Create a new worktree with a feature branch
git worktree add ../openlibrary-<issue>-<type> <issue-number>/<type>/<slug> -b <issue-number>/<type>/<slug>

# Example:
git worktree add ../openlibrary-12042-fix-want-to-read -b 12042/fix/want-to-read
```

### 3.2 Or Work in Current Directory

```bash
# Make sure you're on master and up to date
git checkout master
git pull origin master

# Create feature branch
git checkout -b <issue-number>/<type>/<slug>
```

## 4. Develop the Solution

### 4.1 Explore and Understand

- Trace through the relevant code paths
- Understand how the feature currently works
- Identify what needs to change

### 4.2 Write Code Following Best Practices

- **Modular** - Break into clear, focused functions
- **Clear** - Use meaningful names, add comments where needed
- **Reproducible** - Ensure consistent behavior
- **Composable** - Functions should work together well
- **Testable** - Write testable code
- **DRY** - Don't Repeat Yourself

### 4.3 Commit at Logical Checkpoints

```bash
# Stage changes
git add <files>

# Commit with descriptive message
git commit -m "Brief description of changes

- Specific change 1
- Specific change 2
- Related consideration"
```

Commit early and often with clear messages. Each commit should be a coherent unit of work.

## 5. Verify Code Quality

### 5.1 Run Linting

**Always run in Docker:**

```bash
# Python lint (ruff)
docker compose run --rm home make lint

# JavaScript + CSS lint
docker compose run --rm home npm run lint

# Auto-fix if possible
docker compose run --rm home npm run lint-fix
```

### 5.2 Run Tests

**Always run in Docker:**

```bash
# Python tests
docker compose run --rm home make test-py

# JavaScript tests
docker compose run --rm home npm run test:js

# Run a specific test file
docker compose run --rm home pytest openlibrary/core/tests/test_models.py

# Run a specific test
docker compose run --rm home pytest openlibrary/core/tests/test_models.py::test_function_name -xvs
```

### 5.3 Build Assets (If Needed)

If you changed CSS, JS, or components:

```bash
# Build everything
docker compose run --rm home make all

# Watch mode for development
docker compose run --rm home npm run watch
```

## 6. Manual/Integration Testing

For UI changes or complex features, manual testing may be necessary:

### 6.1 Start the Dev Server

```bash
docker compose up
```

Visit http://localhost:8080

### 6.2 Test the Fix

1. Navigate to the relevant page
2. Verify the fix works as expected
3. Test edge cases
4. Test with JavaScript disabled (for JS-dependent features)
5. Test with JavaScript enabled

### 6.3 Test Critical Paths

- User authentication flows
- Data persistence
- Error handling
- Loading states

## 7. Self-Review

Before requesting review, verify:

### 7.1 No Secrets Committed

```bash
# Check for potential secrets
git diff --staged | grep -i "secret\|password\|token\|key\|api"
git log -1 -p | grep -i "secret\|password\|token\|key\|api"
```

### 7.2 Security Best Practices

- No hardcoded credentials
- No SQL injection vulnerabilities
- No XSS vulnerabilities
- Proper input validation
- Safe redirects

### 7.3 Code Quality

- Code follows project style guidelines
- No unnecessary complexity
- Good error handling
- Comments where logic is complex

## 8. Request Review

### 8.1 Push Branch to Remote

```bash
git push -u origin <branch-name>
```

### 8.2 Create Pull Request

```bash
gh pr create \
  --title "Fix: Brief description of the fix" \
  --body "$(cat <<'EOF'
## Summary
Brief overview of the changes.

## Solution
How the problem was solved.

## Considerations
- What might the reviewer need to know?
- Any potential risks?
- Performance implications?
- Special deploy instructions?

## Testing
How was this tested?

## Related Issues
Closes #<issue-number>
EOF
)"
```

### 8.3 Answer Reviewer Questions

Be responsive to feedback:

- Answer questions clearly
- Make requested changes
- Explain your reasoning if you disagree

## 9. Merge

Once approved:

```bash
# Merge via GitHub UI or:
gh pr merge <pr-number>
```

## Quick Reference

| Task                    | Command                                           |
| ----------------------- | ------------------------------------------------- |
| Get issue with comments | `gh issue view <num> --comments`                  |
| Start Docker            | `docker compose up -d`                            |
| Python lint             | `docker compose run --rm home make lint`          |
| JS/CSS lint             | `docker compose run --rm home npm run lint`       |
| Python tests            | `docker compose run --rm home make test-py`       |
| JS tests                | `docker compose run --rm home npm run test:js`    |
| Build assets            | `docker compose run --rm home make all`           |
| Run specific test       | `docker compose run --rm home pytest <path> -xvs` |
| Commit changes          | `git add . && git commit -m "message"`            |
| Push branch             | `git push -u origin <branch>`                     |
| Create PR               | `gh pr create --title "..." --body "..."`         |
