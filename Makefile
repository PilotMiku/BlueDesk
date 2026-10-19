.PHONY: install run demo test screenshots icons clean

install:
	python -m pip install -e .

run:
	PYTHONPATH=src python -m bluedeck

demo:
	PYTHONPATH=src python -m bluedeck --demo

test:
	QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q

screenshots:
	QT_QPA_PLATFORM=offscreen PYTHONPATH=src python scripts/capture_demo.py

icons:
	PYTHONPATH=src python scripts/export_icons.py

clean:
	rm -rf build dist .pytest_cache src/*.egg-info
