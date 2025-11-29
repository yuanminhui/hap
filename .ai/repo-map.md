# Repo Map — hap

- pyproject.toml        # poetry config, deps, tool configs
- noxfile.py            # CI-like local sessions: lint, type, test, build
- src/
  └─ hap/
     ├─ commands/
     │  ├─ build.py     # CLI: build HAP from GFA to Postgres
     │  ├─ sequence.py  # CLI: sequence processing
     │  └─ __init__.py
     ├─ lib/
     │  ├─ gfa.py       # GFA object manipulation
     │  ├─ elements.py  # region/segment data classes (RST primitives)
     │  ├─ database.py  # database utilities
     │  ├─ util_obj.py  # helpers: batching, hashing, ids
     │  ├─ fileutil.py  # robust file/io utils
     │  ├─ config.py    # dataclass config
     │  └─ error.py     # domain exceptions
     └─ sql/
         └─ create_tables.sql # base schema (kept in sync)
- tests/                 # unit + integration (DB docker or local)
- docs/                  # minimal CLI & schema doc (optional)
- sql/                   # extra migrations or views
