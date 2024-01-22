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


A toolkit for data convertion and manipulation in Hierarchical Pangenome model.


## Features

- TODO


## Requirements

- TODO


## Installation

Install via [pip] from [PyPI]:

```console
$ pip install hap
```


## Usage

Build a hierarchical pangenome from a GFA file:

```bash
hap build hprc.gfa
```

or from subgraphs:

```bash
hap build hprc_subgraphs/
```

Divide a GFA build from a whole genome to chromosome or contig level:

```bash
hap divide hprc.gfa
```

Submit the built hierarchical pangenome to database:

```bash
hap submit hprc_hapout/ --dbstr 'postgresql://hap@localhost:5432/hap'
```

Please see the [Command-line Reference] for details.


## Issues

If you encounter any problems,
please [file an issue] along with a detailed description.


## Authors

- [@yuanminhui](https://www.github.com/yuanminhui)


## License

This project is under [MIT license][license].


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
[file an issue]: https://github.com/yuanminhui/hap/issues
[pip]: https://pip.pypa.io/

<!-- github-only -->
[license]: https://github.com/yuanminhui/hap/blob/main/LICENSE
[command-line reference]: https://hap.readthedocs.io/en/latest/usage.html