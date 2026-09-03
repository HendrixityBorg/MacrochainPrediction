.PHONY: setup run offline test verify oracle freeze

setup:
	./setup.sh

run:
	./run.sh

offline:
	./run.sh --offline

test:
	./test.sh

verify:
	python3 -m macro_gold_latent.cli verify

oracle:
	python3 -m macro_gold_latent.cli oracle

freeze:
	python3 -m macro_gold_latent.cli freeze-protocol

