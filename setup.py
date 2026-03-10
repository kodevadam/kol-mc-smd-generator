from setuptools import setup, find_packages

setup(
    name="ko2mc",
    version="1.0.0",
    description="Convert Knight Online .gtd/.opd map files to Minecraft worlds",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24.0",
    ],
    entry_points={
        "console_scripts": [
            "ko2mc=ko2mc.__main__:main",
        ],
    },
)
