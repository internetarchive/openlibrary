#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
COMPONENTS_DIR=openlibrary/components
OSP_DUMP_LOCATION=/solr-updater-data/osp_totals.db


.PHONY: all clean distclean git css js components lit-components icons i18n lint frontend \
	e2e-up e2e-stack e2e-assets e2e-index e2e-reindex test-e2e

all: git frontend i18n

frontend: node_modules icons
	# Regenerate the Custom Elements Manifest (committed; consumed by /developers/design)
	npx cem analyze
	node scripts/vite/build.mjs

node_modules: package-lock.json package.json
ifeq ($(LOCAL_DEV),true)
	npm ci --no-audit --no-fund
endif

css: node_modules
	node scripts/vite/build.mjs --only css

js: node_modules
	node scripts/vite/build.mjs --only js

components: node_modules icons
	# Regenerate the Custom Elements Manifest (committed; consumed by /developers/design)
	npx cem analyze
	node scripts/vite/build.mjs --only components

lit-components: components

icons:
	# Build the icon sprite and the Lit glyph module from static/icons/src/.
	# Neither is committed. No node_modules prerequisite — the script is pure Node.
	node scripts/build_icon_sprite.mjs

i18n:
	python ./scripts/i18n-messages compile

git:
	git submodule init
	git submodule sync
	git submodule update

clean:
	rm -rf $(BUILD)

distclean:
	git clean -fdx
	git submodule foreach git clean -fdx


reindex-solr:
    # Keep link in sync with ol-solr-updater-start and Jenkinsfile
	curl -C - -L "https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db" -o $(OSP_DUMP_LOCATION)
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep -E '/(lists|series)/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	parallel -j4 python ./scripts/solr_builder/solr_builder/index_subjects.py ::: subject person place time

lint:
	# See the pyproject.toml file for ruff's settings
	uv run --with-requirements requirements_test.txt ruff check .

PYTEST_ARGS ?= . --doctest-modules

test-py:
	pytest $(PYTEST_ARGS)

test-py-uv:
	uv run --with-requirements requirements_test.txt pytest $(PYTEST_ARGS)

test-i18n:
	# Valid locale codes should be added as arguments to validate
	python ./scripts/i18n-messages validate de es fr hr it ja zh

test:
	make test-py && npm run test && make test-i18n

# End-to-end tests
# ----------------
# Playwright drives a real browser on the host against the dev stack in Docker.
# `make e2e-up` once per session, then `make test-e2e` as often as you like.
# See tests/e2e/README.md.

E2E_PORT ?= 8080
E2E_SERVICES = db memcached mockservices infobase covers solr web fast_web
E2E_URL = http://localhost:$(E2E_PORT)

e2e-up: e2e-stack e2e-assets e2e-index
	npx playwright install chromium chromium-headless-shell

e2e-stack:
	docker compose up -d $(E2E_SERVICES)
	@echo "Waiting for $(E2E_URL) ..."
	@for i in $$(seq 1 90); do \
		curl -sf -o /dev/null $(E2E_URL)/ && exit 0; \
		sleep 2; \
	done; \
	echo "Timed out. Try: docker compose logs web fast_web" >&2; \
	exit 1

# static/build ships inside the image, built from master at image build time.
# Rebuild it from this working tree, or the browser tests stale bundles and
# passes against code that isn't yours.
e2e-assets:
	docker compose run --rm home npm run build-assets

# Solr starts empty, and the search, subject and author specs skip themselves
# when it has no documents -- a skipped test reads exactly like a pass. Query
# through the web container: a Solr that answers on localhost can still be
# unreachable from the app, which fails as a dozen confusing test failures.
e2e-index:
	@count=$$(docker compose exec -T web curl -sf "http://solr:8983/solr/openlibrary/select?q=*:*&rows=0" | grep -o '"numFound":[0-9]*' | cut -d: -f2); \
	if [ -z "$$count" ]; then \
		echo "The web container can't reach Solr. Try: docker compose up -d --force-recreate solr" >&2; \
		exit 1; \
	elif [ "$$count" = "0" ]; then \
		docker compose run --rm home make reindex-solr; \
	else \
		echo "Solr has $$count documents; skipping reindex (make e2e-reindex to force)."; \
	fi

e2e-reindex:
	docker compose run --rm home make reindex-solr

# A thin wrapper over the npm script, the way `test` wraps `npm run test`, so
# Playwright is invoked in exactly one place. Not folded into `test`: that runs
# on any checkout, and these need the stack up and Solr populated.
PLAYWRIGHT_ARGS ?=
test-e2e:
	npm run test:e2e -- $(PLAYWRIGHT_ARGS)
