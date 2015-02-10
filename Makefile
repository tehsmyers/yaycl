sdist:
	./setup.py sdist

upload:
	./setup.py sdist upload

clean:
	rm -rf AUTHORS ChangeLog dist yaycl.egg-info __pycache__ *.egg .coverage
