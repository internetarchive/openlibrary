# Issue PM AI Workflow

This directory contains the prompts/instructions used by GitHub Actions workflows that leverage AI to assist with issue management.

## Issue PM Instructions (`issue_pm_instructions.md`)

This file contains the system prompt used by the Issue PM AI workflow (`.github/workflows/issue_pm_ai.yml`) to automatically provide contextual follow-up comments on newly created issues.

### Purpose

The Issue PM AI workflow helps:
- Suggest relevant files and code locations
- Link to appropriate documentation
- Reference related PRs and issues
- Recommend appropriate labels
- Provide clear next steps for contributors

### When It Runs

The workflow triggers automatically when:
- A new issue is opened in the repository
- Only runs in the main `internetarchive/openlibrary` repository (not forks)

### How It Works

1. The workflow loads the instructions from this file
2. Sends the issue title and body to GitHub Models API (gpt-4o-mini)
3. The AI generates a contextual response following the instructions
4. Posts the response as a comment on the issue

### Modifying the Instructions

To update the AI's behavior:
1. Edit `issue_pm_instructions.md` 
2. Update the guidance, documentation links, or criteria
3. Test by creating a test issue (or wait for the next real issue)
4. The changes take effect immediately for new issues

### Documentation Links

Keep the documentation links in `issue_pm_instructions.md` up-to-date as the project evolves. Key resources include:
- Setup & Installation guides
- Development workflow documentation  
- Testing and debugging guides
- Architecture documentation
- API documentation

### Label Criteria

The instructions define when to apply special labels:
- `Needs: Staff` - For features requiring staff testing/access
- `Good First Issue` - For well-scoped, beginner-friendly issues

Update these criteria in the instructions file as project needs change.

## Troubleshooting

If the workflow isn't working:
1. Check GitHub Actions logs in the repository's Actions tab
2. Verify GitHub Models API access is available
3. Check that the workflow has proper permissions (`issues: write`)
4. Review recent changes to the instructions file for syntax issues
5. Ensure the issue was created in the main repository, not a fork

## API Usage

The workflow uses GitHub Models API which is:
- Part of GitHub's free tier for open source projects
- Rate-limited but generous for typical usage
- Requires standard `GITHUB_TOKEN` (automatically provided)

For more information on GitHub Models, see: https://docs.github.com/en/github-models
