from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in casecentral/__init__.py
from casecentral import __version__ as version

setup(
	name="casecentral",
	version=version,
	description="Legal Practice Management Application",
	author="4C Solutions",
	author_email="info@4csolutions.in",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
