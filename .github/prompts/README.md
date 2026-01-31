# Issue PM AI Workflow - Copilot Skills-Based

This directory contains configurations for the GitHub Copilot Agent Skills-based issue triage workflow.

## Copilot Instructions (`.github/copilot-instructions.md`)

This file provides comprehensive context about the Open Library project to GitHub Copilot, including:
- Project overview and technology stack
- Key codebase areas and patterns
- Issue triage guidelines and labeling criteria
- Common documentation links

This serves as the knowledge base for the AI when analyzing issues.

## Issue PM AI Workflow (`.github/workflows/issue_pm_ai.yml`)

An automated workflow that uses **Copilot Agent Skills** to provide contextual follow-up on newly created issues.

### Skills-Based Architecture

The workflow implements a "Skills" pattern where it:
1. **Gathers repository context** using GitHub CLI (gh):
   - Similar issues (via search)
   - Related pull requests
   - Recent open issues
   - Potentially relevant files (based on keywords)

2. **Provides context to AI** as "Skills data":
   - All gathered information is passed to the AI
   - AI uses this real-time repository data to make informed suggestions

3. **Generates contextual response**:
   - Suggests relevant files based on actual codebase
   - References real similar issues and PRs
   - Recommends appropriate labels
   - Provides actionable next steps

### Purpose

The workflow helps:
- Suggest relevant files and code locations (from actual repository)
- Link to appropriate documentation
- Reference related PRs and issues (from live searches)
- Recommend appropriate labels (Needs: Staff, Good First Issue)
- Provide clear next steps for contributors

### When It Runs

The workflow triggers automatically when:
- A new issue is opened in the repository
- Only runs in the main `internetarchive/openlibrary` repository (not forks)

### How It Works (Skills Pattern)

1. **Load Copilot Instructions**: Loads project context from `copilot-instructions.md`
2. **Gather Repository Context (Skills)**:
   - Uses `gh` CLI to search for similar issues
   - Finds related PRs using GitHub API
   - Identifies potentially relevant files based on issue keywords
   - Collects recent issues for context
3. **Generate Response**: Sends all context to GitHub Models API with Copilot instructions
4. **Post Comment**: Posts the AI-generated response on the issue

### Skills/Tools Used

The workflow leverages these "skills" to gather context:
- **GitHub CLI (`gh`)**: Query issues, PRs, search across repository
- **Keyword matching**: Identify relevant file patterns
- **GitHub API**: Access repository metadata
- **Code patterns**: Understand common issue types and related files

### Modifying the Workflow

To update the AI's behavior:
1. **Edit `.github/copilot-instructions.md`** to change project context, guidelines, or criteria
2. **Edit workflow YAML** to add more Skills (e.g., code search, file content analysis)
3. Changes take effect immediately for new issues

### Documentation Links

Keep documentation links in `.github/copilot-instructions.md` up-to-date as the project evolves.

## Legacy Files

- `issue_pm_instructions.md` - Original static instructions (replaced by copilot-instructions.md)
- Can be removed if no longer needed

## Troubleshooting

If the workflow isn't working:
1. Check GitHub Actions logs in the repository's Actions tab
2. Verify GitHub Models API access is available
3. Ensure `gh` CLI commands succeed (check for API rate limits or auth errors in logs)
4. Check that the workflow has proper permissions (`issues: write`, `pull-requests: read`)
5. Review recent changes to the `.github/copilot-instructions.md` file

## Extending Skills

To add more "Skills" to the workflow:

### Example: Add code search
```yaml
- name: Search code for keywords
  run: |
    KEYWORDS=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]')
    CODE_RESULTS=$(gh search code --repo "$REPO" "$KEYWORDS" --json path,repository 2>&1)
    if [ $? -eq 0 ]; then
      CODE_MATCHES=$(echo "$CODE_RESULTS" | jq -r '.[] | .path')
      echo "CODE_MATCHES<<EOF" >> "$GITHUB_OUTPUT"
      echo "$CODE_MATCHES" >> "$GITHUB_OUTPUT"
      echo "EOF" >> "$GITHUB_OUTPUT"
    else
      echo "Warning: Code search failed"
      echo "CODE_MATCHES=No code matches found" >> "$GITHUB_OUTPUT"
    fi
```

### Example: Get file content
```yaml
- name: Get relevant file content
  run: |
    FILE_CONTENT=$(gh api repos/$REPO/contents/path/to/file --jq '.content' 2>&1 | base64 -d)
    if [ $? -eq 0 ]; then
      echo "FILE_CONTENT<<EOF" >> "$GITHUB_OUTPUT"
      echo "$FILE_CONTENT" >> "$GITHUB_OUTPUT"
      echo "EOF" >> "$GITHUB_OUTPUT"
    else
      echo "FILE_CONTENT=Unable to fetch file" >> "$GITHUB_OUTPUT"
    fi
```

### Example: Check recent commits
```yaml
- name: Get recent commits
  run: |
    COMMITS=$(gh api repos/$REPO/commits --jq '.[0:5] | .[] | {sha, message, author}' 2>&1)
    if [ $? -eq 0 ]; then
      echo "RECENT_COMMITS<<EOF" >> "$GITHUB_OUTPUT"
      echo "$COMMITS" >> "$GITHUB_OUTPUT"
      echo "EOF" >> "$GITHUB_OUTPUT"
    else
      echo "RECENT_COMMITS=Unable to fetch commits" >> "$GITHUB_OUTPUT"
    fi
```

## API Usage

The workflow uses:
- **GitHub CLI (`gh`)**: For repository queries (uses GITHUB_TOKEN)
- **GitHub Models API**: For AI-powered analysis
- Both are part of GitHub's free tier for open source projects

For more information:
- GitHub CLI: https://cli.github.com/
- GitHub Models: https://docs.github.com/en/github-models
