# Copilot Instructions for Open Library

You are assisting with the Open Library project - a free, open-source catalog of books with lending capabilities.

## Project Overview

Open Library is a digital library project by the Internet Archive that aims to create "one web page for every book ever published." The project includes:
- A catalog of millions of books with metadata
- Book lending/borrowing features
- Book editing and contribution tools
- Integration with Internet Archive's book scanning efforts

## Technology Stack

- **Backend**: Python (web.py framework, transitioning to FastAPI)
- **Frontend**: JavaScript, Vue.js components, legacy jQuery
- **Database**: PostgreSQL (via Infogami)
- **Search**: Solr
- **Infrastructure**: Docker-based development environment

## Key Areas of the Codebase

### Core Directories
- `openlibrary/` - Main application code
  - `openlibrary/plugins/` - Plugin modules (books, upstream, admin, etc.)
  - `openlibrary/templates/` - HTML templates
  - `openlibrary/components/` - Vue.js components
  - `openlibrary/utils/` - Utility functions
- `static/` - Static assets (CSS, JS, images)
- `scripts/` - Maintenance and deployment scripts
- `tests/` - Test suites
- `docker/` - Docker configuration files

### Important Patterns
- Books are identified by Open Library IDs (e.g., `/books/OL123M`)
- Works represent conceptual books, Editions are specific printings
- The system uses a custom data model built on Infogami

## Common Issue Categories

### Authentication & Accounts
**Files**: `openlibrary/plugins/upstream/account.py`, `openlibrary/accounts/`
**Labels**: `Needs: Staff` (requires production testing)
**Note**: Account-related features require staff testing as they involve sensitive operations

### Borrowing & Lending
**Files**: `openlibrary/plugins/upstream/borrow.py`, `openlibrary/plugins/upstream/mybooks.py`
**Labels**: `Needs: Staff` (requires access to lending infrastructure)
**Note**: Borrowing features integrate with Internet Archive's lending system

### Search & Discovery
**Files**: `openlibrary/plugins/worksearch/`, `openlibrary/solr/`
**Documentation**: Solr schema and search documentation
**Note**: Search changes may require Solr reindexing

### Book Editing & Data
**Files**: `openlibrary/plugins/upstream/addbook.py`, `openlibrary/catalog/`
**Note**: Book data changes must be carefully validated to maintain data quality

### Frontend/UI
**Files**: `static/css/`, `openlibrary/components/`, Vue components
**Labels**: Can be `Good First Issue` if well-scoped
**Documentation**: Frontend Guide on wiki

## Issue Triage Guidelines

### Labeling Criteria

**`Needs: Staff`** - Apply when issue involves:
- Authentication/login systems
- Borrowing/lending features  
- Account management operations
- Payment/donation processing
- Admin-only features
- Production database modifications
- Features requiring special access/permissions

**`Good First Issue`** - Apply ONLY when ALL true:
- Clear, well-defined scope (1-2 files)
- Straightforward changes (UI text, simple bug fix, small feature)
- Specific file locations or clear guidance provided
- No complex architecture knowledge required
- Does NOT require staff-only testing
- Be conservative - when in doubt, don't apply this label

### Information to Provide

When analyzing issues, use available repository data to provide:
1. **Relevant Files**: Use code search to identify files related to the issue
2. **Similar Issues**: Search for related open/closed issues
3. **Related PRs**: Find PRs that touched similar areas of code
4. **Documentation**: Link to relevant wiki pages, README files
5. **Next Steps**: Clear guidance based on issue state (needs priority, needs approach, ready for work)

### Skills/Tools Available

Use these tools to gather context:
- **GitHub CLI (`gh`)**: Query issues, PRs, repository data
- **Code search**: Find relevant files and code patterns
- **Repository structure**: Understand file organization
- **Git history**: Check recent changes to related files

## Response Guidelines

- Be specific and actionable
- Only suggest files/PRs/issues when confident of relevance
- Link to actual documentation, not generic advice
- Note if issue needs priority/lead assignment before work begins
- Remind about git workflow (rebase, pre-commit) when relevant
- Conservative with "Good First Issue" label - better to skip than mislabel

## Development Workflow

Contributors should:
1. Check wiki for setup instructions (Docker-based development)
2. Follow git workflow (rebase before creating branch, pre-commit hooks)
3. Write tests for changes (pytest for Python, Jest for JavaScript)
4. Get issue approved by lead with priority label before starting work
5. Reference the issue in PR title/description

## Common Documentation Links

- Setup: https://github.com/internetarchive/openlibrary/tree/master/docker
- Git Workflow: https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet
- Testing: https://github.com/internetarchive/openlibrary/wiki/Testing
- Contributing: https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md
- API Docs: https://openlibrary.org/developers/api
