# Open Library Development Instructions

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

**Bootstrap and Build the Repository:**
- Initialize git submodules: `make git` -- takes ~3 seconds
- Install Node.js dependencies: `npm install --no-audit` -- takes ~3 minutes. NEVER CANCEL. Set timeout to 5+ minutes.
- Install Python dependencies: `pip3 install -r requirements_test.txt` -- takes ~2-5 minutes depending on network
- Build JavaScript assets: `make js` -- takes ~18 seconds
- Build CSS assets: `make css` -- takes ~4 seconds  
- Build Vue components: `make components` -- takes ~14 seconds
- Build all assets at once: `npm run build-assets` -- takes ~35 seconds. NEVER CANCEL. Set timeout to 2+ minutes.
- Compile internationalization: `make i18n` -- takes ~2 seconds

**Run Tests:**
- JavaScript tests: `npm run test:js` -- takes ~11 seconds. All 308 tests should pass.
- Python tests: `make test-py` -- takes ~12 seconds. NEVER CANCEL. Set timeout to 2+ minutes. Expect 2700+ tests to pass.
- i18n validation: `make test-i18n` -- takes ~2 seconds
- Run all tests: `make test` -- takes ~25 seconds total. NEVER CANCEL. Set timeout to 3+ minutes.

**Code Quality:**
- Lint JavaScript/Vue: `npm run lint:js` -- takes ~4 seconds
- Lint CSS/LESS: `npm run lint:css` -- takes ~2 seconds
- Lint all: `npm run lint` -- takes ~6 seconds
- Python linting: `make lint` -- uses ruff for Python linting

**Docker Development (Note: May fail in CI environments):**
- Build containers: `docker compose build` -- takes 15+ minutes. NEVER CANCEL. Set timeout to 30+ minutes.
- Run application: `docker compose up` -- runs the full application stack
- Access at: http://localhost:8080 when running in Docker

## Critical Build Information

**NEVER CANCEL BUILDS OR TESTS** - All build and test commands must complete:
- `npm install` can take 3-5 minutes depending on network
- `npm run build-assets` takes ~35 seconds but can vary
- `make test` takes ~25 seconds but comprehensive
- `docker compose build` takes 15+ minutes when working
- Always use timeouts of 2x the expected time minimum

**Build Artifacts Location:**
- JavaScript builds go to: `static/build/*.js`
- CSS builds go to: `static/build/*.css` 
- Vue components go to: `static/build/components/`
- All builds create source maps for debugging

## Validation Scenarios

**ALWAYS test functionality after making changes:**
1. **Build Validation**: Run `npm run build-assets` and verify no errors
2. **Test Validation**: Run `make test` and verify all tests pass
3. **Lint Validation**: Run `npm run lint` and fix any issues
4. **Manual Testing**: If working on frontend code, inspect `static/build/` for generated assets

**Before Committing Changes:**
- Always run `make test` to ensure tests pass
- Always run `npm run lint` and fix any linting issues  
- If modifying Python code, run `make lint` for Python linting
- If modifying i18n files, run `make test-i18n`

## Development Environment

**Prerequisites (already available in development environment):**
- Python 3.12+ 
- Node.js 20+
- Git with SSH access for submodules

**Key Dependencies:**
- Backend: Python with web.py framework, PostgreSQL, Solr, Memcached
- Frontend: JavaScript, Vue.js 3, Webpack, LESS stylesheets
- Testing: pytest (Python), Jest (JavaScript)
- Quality: ruff (Python), ESLint (JavaScript), Stylelint (CSS)

**Important Files:**
- `package.json` - Node.js dependencies and scripts
- `requirements*.txt` - Python dependencies  
- `Makefile` - Build and test commands
- `compose.yaml` - Docker configuration
- `.pre-commit-config.yaml` - Code quality hooks
- `pyproject.toml` - Python project configuration

## Code Organization

**Main directories:**
- `openlibrary/` - Core application code (Python)
- `openlibrary/plugins/` - Plugin system and controllers
- `openlibrary/templates/` - Jinja2 templates for web pages
- `openlibrary/components/` - Vue.js components
- `static/` - Frontend assets (CSS, JS, images)
- `tests/` - Test files for both Python and JavaScript
- `scripts/` - Utility and maintenance scripts
- `conf/` - Configuration files
- `docker/` - Docker setup and configuration

**Key Frontend Files:**
- `static/css/` - LESS stylesheets
- `openlibrary/plugins/openlibrary/js/` - JavaScript modules
- `webpack.config.js` - JavaScript build configuration
- `vue.config.js` - Vue.js configuration

## Known Issues and Workarounds

**Docker in CI environments:**
- `docker compose build` may fail with SSL certificate errors in sandboxed environments
- This is an environment limitation, not a code issue
- Use direct Node.js/Python commands for validation instead

**Pre-commit hooks:**
- May fail in CI environments due to network timeouts
- Install with: `pip3 install pre-commit`  
- Run manually with: `pre-commit run --files .pre-commit-config.yaml`
- Network timeouts are environmental, not code issues

**Git Submodules:**
- MUST use SSH clone: `git clone git@github.com:internetarchive/openlibrary.git`
- HTTPS cloning breaks submodule access
- Always run `make git` after fresh clone to initialize submodules

## Performance Notes

**Build times (typical):**
- Full clean build: ~45 seconds
- Incremental builds: ~5-15 seconds
- Test suite: ~25 seconds total
- Linting: ~6 seconds

**Memory requirements:**
- JavaScript builds require ~4GB RAM minimum
- Increase Docker memory to 4GB+ if using containers
- Node.js builds can be memory intensive

## Troubleshooting

**Build failures:**
- Run `make git` to ensure submodules are initialized
- Clear builds: `rm -rf static/build` then rebuild
- Node modules issues: `rm -rf node_modules && npm install --no-audit`

**Test failures:**
- Python import errors: Check `pip3 install -r requirements_test.txt` completed
- JavaScript test failures: Ensure `npm install --no-audit` completed successfully
- Database-related test issues are expected in some CI environments

**Linting issues:**
- JavaScript: `npm run lint-fix:js` auto-fixes many issues
- CSS: `npm run lint-fix:css` auto-fixes many issues
- Python: Use ruff for Python code formatting