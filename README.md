# Alteryx Auto Documenter

This project is an Alteryx macro/workflow designed to automatically generate documentation based on the content of a workflow.

## Features

- Supports workflows with containers
- Provides an execution order of tools to assist in rebuilding workflows
- Provides detailed configuration information of various tools
- Generates a full image map of the workflow as part of the documentation

## Installation

This project relies on Python dependencies. To install them, run:

```bash
pip install -r requirements.txt
```

Note: If running as a non-admin within Alteryx, ensure that the bundled installer (`Installer.yxwz`) is used to unpack the provided packages if you are not using standard `pip`.

## Usage

This project is built to be used within the Alteryx Designer environment.
1. Use the `Installer.yxwz` workflow to ensure packages and macros are configured correctly.
2. The core python logic is located at `scripts/AutodocScript_2020_05_19_CONTAINERS.py`.

## Git and Contributions

Unnecessary generated files (like reports in `outputs/` or python cache) have been added to `.gitignore` to keep the repository clean.