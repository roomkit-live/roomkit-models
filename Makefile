.PHONY: check build serve upstream-check

check:
	python3 -m unittest discover -s tests -v
	python3 scripts/catalogue.py validate
	node --check site/app.js

build:
	python3 scripts/catalogue.py build

serve: build
	python3 -m http.server 8765 --directory dist --bind 127.0.0.1

upstream-check:
	python3 scripts/upstream.py --report reports/upstream.md
