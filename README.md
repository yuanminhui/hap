# Hierarchical Pangenome toolkit

[![PyPI](https://img.shields.io/pypi/v/hap.svg)][pypi_]
[![Status](https://img.shields.io/pypi/status/hap.svg)][status]
[![Python Version](https://img.shields.io/pypi/pyversions/hap)][python version]
[![License](https://img.shields.io/pypi/l/hap)][license]

[![Read the documentation at https://hap.readthedocs.io/](https://img.shields.io/readthedocs/hap/latest.svg?label=Read%20the%20Docs)][read the docs]
[![Tests](https://github.com/yuanminhui/hap/workflows/Tests/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/yuanminhui/hap/branch/main/graph/badge.svg)][codecov]

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)][pre-commit]
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)][black]

A toolkit for data convertion and manipulation based on the Hierarchical Pangenome (HAP) model.

## Features

- Build a Hierarchical Pangenome from GFA(s)

## Requirements

Linux system,
bash, gawk installed

Python(>=3.10) and Pip, PostgreSQL

## Installation

Install via [pip] from [PyPI]:

```console
$ pip install hap
```

## Usage
### Database configuration
Initial database configuration through setting environment variables: (Change \<username> and \<password> to your username and password of the PostgresSQL database to store HAP data)
```bash
echo 'export HAP_DB_USER=<username>' >> ~/.bashrc
echo 'export HAP_DB_PASSWORD=<password>' >> ~/.bashrc
```

or through config:
```bash
hap config set db.user <username>
hap config set db.password <password>
```
See the full list of database configuration in [Command-line Reference].

### Build a Hierarchical Pangenome
Build from a GFA file:

```bash
hap build hprc.gfa -n hprc -a human
```

or from subgraphs:

```bash
hap build hprc_subgraphs/ -n hprc -a human
```

See the [Command-line Reference] for details.

## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.

## Authors

- [@yuanminhui](https://www.github.com/yuanminhui)

## License

This project is under [MIT license][license].

## Todos

- Refactor the code into 3-layer DDD-like structure
  - Build classes for HAP and RST model 
- Expose CLI & API for dividing GFA into subgraphs to end users
- Add loggings at command level with [loguru]
- Add tests for commands, classes and module functions
- Add docs (in code, `README.md`, guide & reference at [read the docs])
- Scrutiny and modify dev tooling configs
- Fix poetry installation in Github CI procedure

<!--Links-->

<!--badges-->

[pypi_]: https://pypi.org/project/hap/
[status]: https://pypi.org/project/hap/
[python version]: https://pypi.org/project/hap
[read the docs]: https://hap.readthedocs.io/
[tests]: https://github.com/yuanminhui/hap/actions?workflow=Tests
[codecov]: https://app.codecov.io/gh/yuanminhui/hap
[pre-commit]: https://github.com/pre-commit/pre-commit
[black]: https://github.com/psf/black
[pypi]: https://pypi.org/
[pip]: https://pip.pypa.io/

<!-- github-only -->

[file an issue]: https://github.com/yuanminhui/hap/issues
[license]: https://github.com/yuanminhui/hap/blob/main/LICENSE

<!-- misc -->
[command-line reference]: https://hap.readthedocs.io/en/latest/usage.html
[loguru]: https://github.com/Delgan/loguru