"""
A module for GFA file.

Classes:
    GFA: A class for GFA file.
"""

import os
import shutil
import subprocess
import multiprocessing as mp

import click
import igraph as ig
import pandas as pd

import hap
from hap.lib import fileutil
from hap.lib.error import DataInvalidError


class GFA:
    """A class for GFA file.

    Attributes:
        filepath (str): The file path of the GFA file.

    Methods:
        version(self) -> float: Get the version of the GFA file.
        contains_segment(self) -> bool: Check if the GFA file contains segment record.
        contains_edge(self) -> bool: Check if the GFA file contains edge record.
        contains_path(self) -> bool: Check if the GFA file contains path record.
        contains_sequence(self) -> bool: Check if the GFA file contains sequence record.
        contains_length(self) -> bool: Check if the GFA file contains length record.
        is_valid(self) -> bool: Check if the GFA file is valid.
        can_extract_length(self) -> bool: Check if the GFA file can extract length from sequence record.
        get_haplotypes(self) -> list[str]: Get the haplotypes from the GFA file.
        separate_sequence(self, output_dir: str): Move the sequences in segment records to `{basename}.seq.tsv`, leaving a `*` as placeholder, add `LN` tag if not exist, and return the file paths of the modified GFA file and the sequence file (if exists).
        ensure_length_completeness(self): Ensure all `S` records have length info: for GFA 1.x this means `LN` is present; for GFA 2.x length field exists by spec.
        extract_subgraph_names(self, chr_only: bool = True) -> list[str]: Extract the names of subgraphs from the GFA file.
        extract_subgraph_by_name(self, name: str, output_file: str = ""): Extract a subgraph by name from the GFA file, returning the sub-GFA's file path.
        divide_into_subgraphs(self, output_dir: str = "", chr_only: bool = True) -> list[tuple[str, str]]: Divide the GFA file into subgraphs by informative labels, saving the subgraphs into the output directory.
        to_igraph(self) -> ig.Graph: Convert the GFA file to an `igraph.Graph` object.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"GFA file {filepath} not found.")
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"{filepath} is not a file.")
        if not self.is_valid():
            raise DataInvalidError(f"{filepath} is not a valid GFA file.")

    @property
    def version(self) -> float:
        """Get the version of the GFA file. When no `VN` tag in `H` line is
        provided, scan the file for signs of different version."""

        # A quick scan on GFA header
        cmd_get_version_from_header = [
            "head",
            "-n",
            "1",
            self.filepath,
            "|",
            "awk",
            """'$1 == "H" {for (i = 2; i <= NF; ++i) if ($i ~ /^VN:/) {split($i, a, ":"); print a[3]}}'""",
        ]
        return_text = subprocess.check_output(
            " ".join(cmd_get_version_from_header), shell=True, text=True
        )
        try:
            version = float(return_text)
        except ValueError:
            # Examine the essential charistics a version possesses
            cmd_judge_version_by_sign = [
                "LC_ALL=C",
                "grep",
                "-m",
                "1",
                "-o",
                "-E",
                "'^(E|J|W)'",
                self.filepath,
            ]
            res = subprocess.run(
                " ".join(cmd_judge_version_by_sign),
                shell=True,
                text=True,
                capture_output=True,
            )
            if res.returncode == 0:
                char = res.stdout.rstrip("\n")
                if char == "E":
                    version = 2.0
                elif char == "J":
                    version = 1.2
                elif char == "W":
                    version = 1.1  # XXX: May be 1.2 too
            elif res.returncode == 1:
                version = 1.0  # HACK: Assume GFA 1.0 if no sign found
        finally:
            return version

    def contains_segment(self) -> bool:
        """Check if the GFA file contains segment record."""

        cmd = ["LC_ALL=C", "grep", "-m", "1", "^S", self.filepath]
        res = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if res.returncode == 0:
            return True
        elif res.returncode == 1:
            return False

    def contains_edge(self) -> bool:
        """Check if the GFA file contains edge record."""

        if self.version < 2:
            cmd = ["LC_ALL=C", "grep", "-m", "1", "^L", self.filepath]
        else:  # GFA 2
            cmd = ["LC_ALL=C", "grep", "-m", "1", "^E", self.filepath]
        res = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if res.returncode == 0:
            return True
        elif res.returncode == 1:
            return False

    def contains_path(self) -> bool:
        """Check if the GFA file contains path record."""

        if self.version == 1.0:
            cmd = ["LC_ALL=C", "grep", "-m", "1", "^P", self.filepath]
        elif self.version == 2.0:
            cmd = ["LC_ALL=C", "grep", "-m", "1", "-E", "'^(O|U)'", self.filepath]
        else:
            cmd = ["LC_ALL=C", "grep", "-m", "1", "^W", self.filepath]
        res = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if res.returncode == 0:
            return True
        elif res.returncode == 1:
            return False

    def validate_path_lines(self) -> tuple[bool, list[str]]:
        """Validate path lines exist and have correct format.

        Per plan.freeze.json phase 2: Only validate path lines EXIST in GFA,
        not segment associations. Path names in annotation files will be
        validated at annotation import time.

        Returns:
            tuple[bool, list[str]]: (is_valid, error_messages)
        """
        errors: list[str] = []

        if not self.contains_path():
            errors.append("No path lines found in GFA file")
            return False, errors

        # Validate path line format based on GFA version
        if self.version == 1.0:
            # P lines: P <path_name> <segment_names> <overlaps>
            with open(self.filepath, "r") as fh:
                for line_num, line in enumerate(fh, 1):
                    if not line.startswith("P\t"):
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        errors.append(
                            f"Line {line_num}: GFA 1.0 P line requires at least 3 fields (path_name, segment_names, overlaps)"
                        )
                    elif not parts[1]:  # path_name empty
                        errors.append(f"Line {line_num}: P line has empty path name")
                    elif not parts[2]:  # segment_names empty
                        errors.append(
                            f"Line {line_num}: P line has empty segment names"
                        )

        elif self.version >= 2.0:
            # O lines: O <path_name> <segment_names>
            # U lines: U <set_name> <id_list>
            with open(self.filepath, "r") as fh:
                for line_num, line in enumerate(fh, 1):
                    if line.startswith("O\t"):
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) < 3:
                            errors.append(
                                f"Line {line_num}: GFA 2.0 O line requires at least 3 fields (path_name, segment_names)"
                            )
                        elif not parts[1]:
                            errors.append(
                                f"Line {line_num}: O line has empty path name"
                            )
                        elif not parts[2]:
                            errors.append(
                                f"Line {line_num}: O line has empty segment names"
                            )
                    elif line.startswith("U\t"):
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) < 3:
                            errors.append(
                                f"Line {line_num}: GFA 2.0 U line requires at least 3 fields (set_name, id_list)"
                            )
                        elif not parts[1]:
                            errors.append(
                                f"Line {line_num}: U line has empty set name"
                            )

        else:  # GFA 1.1/1.2
            # W lines: W <sample> <hap_index> <seq_name> <start> <end> <walk>
            with open(self.filepath, "r") as fh:
                for line_num, line in enumerate(fh, 1):
                    if not line.startswith("W\t"):
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 7:
                        errors.append(
                            f"Line {line_num}: GFA 1.1/1.2 W line requires 7 fields (sample, hap_index, seq_name, start, end, walk, optional_fields)"
                        )
                    elif not parts[1]:  # sample empty
                        errors.append(f"Line {line_num}: W line has empty sample name")
                    elif not parts[3]:  # seq_name empty
                        errors.append(
                            f"Line {line_num}: W line has empty sequence name"
                        )
                    elif not parts[6]:  # walk empty
                        errors.append(f"Line {line_num}: W line has empty walk")
                    # Validate hap_index is integer
                    try:
                        int(parts[2])
                    except ValueError:
                        errors.append(
                            f"Line {line_num}: W line hap_index '{parts[2]}' is not an integer"
                        )
                    # Validate start/end are integers
                    try:
                        int(parts[4])
                        int(parts[5])
                    except ValueError:
                        errors.append(
                            f"Line {line_num}: W line start/end coordinates must be integers"
                        )

        if errors:
            return False, errors
        return True, []

    def parse_paths(self, path_genome_map: dict[str, str] = None) -> list[dict]:
        """Parse path information from GFA file using AWK for efficiency.

        Scans P, O, and W lines in a single pass. AWK script performs:
        - Forward-only orientation validation (rejects '-' orientations)
        - Walk normalization to space-separated segment IDs
        - Genome name resolution via PanSN/delimiter conventions
        - Empty path name handling

        Args:
            path_genome_map: Optional explicit mapping from path_name to genome_name.
                Overrides convention-based parsing for matched paths.

        Returns:
            list[dict]: List of path dictionaries with keys:
                - name: path name (str)
                - walk: list of segment_id strings (all forward orientation)
                - genome_name: genome/sample name (str)

        Raises:
            DataInvalidError: If no paths found, genome resolution fails,
                or any path contains reverse orientation.

        Per plan.freeze.json phase 3: Extract path walks for coordinate generation.
        """

        if not self.contains_path():
            raise DataInvalidError(
                f"No path lines found in GFA file '{self.filepath}'. "
                "Paths are required for building the pangenome."
            )

        # Run AWK script to extract and validate paths
        awk_script_func = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_pansn_str.awk"
        )
        awk_script_paths = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_gfa_paths.awk"
        )

        cmd = ["awk", "-f", awk_script_func, "-f", awk_script_paths, self.filepath]
        res = subprocess.run(cmd, text=True, capture_output=True)

        # Check for AWK script errors (orientation validation, etc.)
        if res.returncode != 0:
            raise DataInvalidError(
                f"Path validation failed:\n{res.stderr.strip()}"
            )

        if not res.stdout.strip():
            raise DataInvalidError(
                f"No paths found in GFA file '{self.filepath}'. "
                "Paths are required for building the pangenome."
            )

        # Parse AWK output (format: path_name\tgenome_name\tnormalized_walk)
        paths = []
        errors = []

        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue

            path_name, genome_name, normalized_walk = parts[0], parts[1], parts[2]

            # Apply explicit mapping if provided (overrides convention parsing)
            if path_genome_map is not None:
                if path_name in path_genome_map:
                    genome_name = path_genome_map[path_name]
                else:
                    errors.append(
                        f"Path '{path_name}' not found in provided path_genome_map. "
                        "All paths must be explicitly mapped when path_genome_map is provided."
                    )
                    continue

            # Check for genome resolution errors from AWK
            if genome_name.startswith("ERROR:"):
                if genome_name == "ERROR:EMPTY":
                    errors.append(f"Path '{path_name}' has empty name in GFA file.")
                else:
                    orig_path = genome_name[6:]  # Remove "ERROR:" prefix
                    errors.append(
                        f"Cannot resolve genome name for path '{orig_path}'. "
                        "Either provide path_genome_map or use naming convention "
                        "like 'sample#chr1' or 'sample.chr1'."
                    )
                continue

            # Parse normalized walk (simple space-separated segment IDs)
            # AWK already validated all orientations are forward (+)
            walk = normalized_walk.split() if normalized_walk else []

            paths.append({
                "name": path_name,
                "walk": walk,
                "genome_name": genome_name,
            })

        if errors:
            error_summary = "\n".join(errors[:10])
            if len(errors) > 10:
                error_summary += f"\n... and {len(errors) - 10} more error(s)"
            raise DataInvalidError(
                f"Path parsing failed with {len(errors)} error(s):\n{error_summary}"
            )

        return paths

    def contains_sequence(self) -> bool:
        """Check if the GFA file contains sequence record."""

        if self.version < 2:
            cmd = [
                "LC_ALL=C",
                "grep",
                "-m",
                "1",
                "-E",
                "'^S\t[^\t]+\t[^\t*]+'",
                self.filepath,
            ]
        else:
            cmd = [
                "LC_ALL=C",
                "grep",
                "-m",
                "1",
                "-E",
                "'^S\t[^\t]+\t[^\t]+\t[^\t*]+'",
                self.filepath,
            ]
        res = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if res.returncode == 0:
            return True
        elif res.returncode == 1:
            return False

    def contains_length(self) -> bool:
        """Check if the GFA file contains length record."""

        if self.version == 2:
            return True
        else:
            cmd = [
                "LC_ALL=C",
                "grep",
                "-m",
                "1",
                "-E",
                "'^S.*\tLN:'",
                self.filepath,
            ]
        res = subprocess.run(" ".join(cmd), shell=True, capture_output=True)
        if res.returncode == 0:
            return True
        elif res.returncode == 1:
            return False

    def is_valid(self) -> bool:
        """Check if the GFA file is valid."""

        if (
            fileutil.is_tab_delimited(self.filepath)
            and self.contains_segment()
            and self.contains_edge()
        ):
            return True
        else:
            return False

    def can_extract_length(self) -> bool:
        """Check if the GFA file can extract length from sequence record."""

        if self.contains_sequence() or self.contains_length():
            return True
        else:
            return False

    def ensure_length_completeness(self) -> None:
        """Ensure that each segment record has valid length information.

        For GFA 1.x, this requires that each `S` line contains an `LN` tag.
        For GFA 2.x, the length field is part of the specification and this
        check is a no-op.

        Raises:
            hap.lib.error.DataIncompleteError: If any GFA 1.x `S` record lacks an `LN` tag.
        """

        # GFA2 has a dedicated length field; nothing to validate here
        if self.version >= 2.0:
            return

        missing: list[str] = []
        with open(self.filepath, "r") as fh:
            for line in fh:
                if not line.startswith("S\t"):
                    continue
                if "\tLN:" in line:
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    missing.append(parts[1])
                else:
                    missing.append("<unknown>")
        if missing:
            preview = ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")
            from hap.lib.error import DataIncompleteError
            raise DataIncompleteError(
                f"Missing LN tag for {len(missing)} segment(s) in GFA: {preview}. "
                "Provide sequences for these IDs or include LN:i:<len> in GFA."
            )

    def get_haplotypes(self) -> list[str]:
        """Get the haplotypes from the GFA file. Haplotypes are extracted from
        the `P` lines in GFA 1.0, and the `O` and `U` lines in GFA 2.0, by
        path IDs that conform PanSN naming convention.

        Returns:
            list[str]: The names of haplotypes.
        """

        if not self.contains_path():
            return []

        awk_script_func = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_pansn_str.awk"
        )
        awk_script_gfa1 = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "extract_haplotype_names_gfa1.awk"
        )
        awk_script_gfa2 = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "extract_haplotype_names_gfa2.awk"
        )

        cmd = ["awk", "-f", awk_script_func, "-f"]
        if self.version < 2:
            cmd.append(awk_script_gfa1)
        else:
            cmd.append(awk_script_gfa2)
        cmd.append(self.filepath)
        res = subprocess.run(cmd, text=True, capture_output=True)
        if res.returncode == 0:
            return res.stdout.splitlines()
        elif res.returncode == 1:
            return []

    def separate_sequence(self, output_dir: str = None):
        """
        Move the sequences in segment records to `{basename}.seq.tsv`, leaving
        a `*` as placeholder, add `LN` tag if not exist, and return the file
        paths of the modified GFA file and the sequence file (if exists).

        Args:
            output_dir (str): The directory to save the sequence file and the
            modified GFA file.

        Returns:
            tuple[str, str]: The file paths of the modified GFA file and the
            sequence file if the GFA file contains sequences, otherwise `None`.
        """

        basename = fileutil.remove_suffix_containing(
            os.path.basename(self.filepath), ".gfa"
        )
        if not output_dir:
            output_dir = os.getcwd()
        output_dir = os.path.normpath(output_dir)

        # validate the output directory
        if os.path.exists(output_dir):
            if not os.path.isdir(output_dir):
                raise NotADirectoryError(f"{output_dir} is not a directory.")
        else:
            os.makedirs(output_dir, exist_ok=True)

        output_file = output_dir + "/" + basename + ".gfa"
        if os.path.exists(output_file):
            if click.confirm(
                f"{output_file} already exists. Overwrite it?", abort=True
            ):
                os.remove(output_file)
        if not self.contains_sequence():
            shutil.copy(self.filepath, output_file)
            return output_file, None
        sequence_file = output_dir + "/" + basename + ".seq.tsv"
        if os.path.exists(sequence_file):
            if click.confirm(
                f"{sequence_file} already exists. Overwrite it?", abort=True
            ):
                os.remove(sequence_file)

        # `awk` -- Move sequences and calculate segment length
        awk = ["awk"]
        if self.version < 2:
            awk.append(
                f"""'BEGIN {{FS = OFS = "\\t"}} /^S/ {{if ($3 != "*") {{print $2, $3 >> "{sequence_file}"; len = length($3); $3 = "*"; if (!match($0, /LN:/)) $0 = $0 "\tLN:i:" len}}}} {{print}}'"""
            )
        else:  # GFA 2
            awk.append(
                f"""'BEGIN {{FS = OFS = "\\t"}} /^S/ {{if ($4 != "*") {{print $2, $4 >> "{sequence_file}"; $4 = "*"}}}} {{print}}'"""
            )
        awk.extend([self.filepath, ">", output_file])

        subprocess.run(" ".join(awk), shell=True)

        return output_file, sequence_file

    def extract_subgraph_names(self, chr_only: bool = True) -> list[str]:
        """
        Extract the names of subgraphs from the GFA file. Segment names
        in `W` lines are treated as subgraph names. When no `W` line exists, `PanSN`
        naming convention is required for extracting segment name from ids in `P` or
        `O|U` lines.

        Args:
            chr_only (bool): If True, only names that start with `chr` (case insensitive) are returned.

        Returns:
            list[str]: The names of subgraphs.
        """

        awk_script_file = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_pansn_str.awk"
        )

        locale = ["LC_ALL=C"]
        grep = ["grep"]
        awk = [
            "|",
            "awk",
            "-f",
            awk_script_file,
            "-e",
        ]
        # `grep_1` -- Get records containing subgraph names
        # `awk` -- Extract subgraph names
        if self.version < 1.1:
            grep_1 = grep + ["^P"]
            awk.append(
                """'{res = parse_pansn_str($2, pa); if (delim == "") exit; if (!res) next; else print pa[3]}'"""
            )
        elif self.version >= 2.0:
            grep_1 = grep + ["-E", "^(O|U)"]
            awk.append(
                """'{res = parse_pansn_str($2, pa); if (delim == "") exit; if (!res) next; else print pa[3]}'"""
            )
        else:
            grep_1 = grep + ["^W"]
            awk.append("'{print $4}'")
        sort = ["|", "sort", "-u"]

        cmd = locale + grep_1 + [self.filepath] + awk + sort
        if chr_only:
            # `grep_2` -- Filter names that start with `chr` (case insensitive)
            grep_2 = ["|"] + grep + ["-E", "'^chr[[:digit:]]{0,2}[[:alpha:]]{0,1}$'"]
            cmd += grep_2

        res = subprocess.run(" ".join(cmd), shell=True, text=True, capture_output=True)
        if res.returncode == 0:
            return res.stdout.splitlines()
        elif res.returncode == 1:
            return []

    def extract_subgraph_by_name(self, name: str, output_file: str = ""):
        """
        Extract a subgraph by EXACT name matching from the GFA file.

        Fixed version that correctly distinguishes chr1 from chr10, chr1_alt, etc.
        Uses unified AWK scripts that work for all GFA versions (1.0, 1.1, 1.2, 2.0).

        Args:
            name (str): The exact name of the subgraph to extract (e.g., "chr1").
            output_file (str): The file path to save the subgraph. If not provided,
                the subgraph will be saved as `{basename}.{name}.gfa`.

        Returns:
            str: Path to the extracted subgraph GFA file.
        """

        if not output_file:
            output_file = self.filepath.replace(".gfa", f".{name}.gfa")

        path_records_file, main_file = fileutil.create_tmp_files(2)

        # Get AWK script paths
        awk_pansn = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_pansn_str.awk"
        )
        awk_extract_paths = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "extract_paths_by_name.awk"
        )
        awk_extract_main = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "extract_subgraph_unified.awk"
        )

        # Step 1: Extract path lines (P/O/W/U) with EXACT name matching
        cmd_paths = [
            "awk",
            "-v", f"subgraph_name={name}",
            "-f", awk_pansn,
            "-f", awk_extract_paths,
            self.filepath,
            ">", path_records_file
        ]

        # Step 2: Extract structural lines (H/S/L/E) for segments in paths
        cmd_main = [
            "awk",
            "-f", awk_extract_main,
            path_records_file,
            self.filepath,
            ">", main_file
        ]

        # Step 3: Concatenate main records with path records
        cmd_concat = [
            "cat", main_file, path_records_file, ">", output_file
        ]

        try:
            subprocess.run(" ".join(cmd_paths), shell=True, check=True)
            subprocess.run(" ".join(cmd_main), shell=True, check=True)
            subprocess.run(" ".join(cmd_concat), shell=True, check=True)
        finally:
            fileutil.remove_files([path_records_file, main_file])

        return output_file

    def divide_into_subgraphs(
        self, output_dir: str = "", chr_only: bool = True
    ) -> list[tuple[str, str]]:
        """
        Divide the GFA file into subgraphs by informative labels, saving the subgraphs
        into the output directory.

        Args:
            output_dir (str): The directory to save the subgraphs.
            chr_only (bool): If True, only subgraphs that start with `chr` (case insensitive) are saved.
        """

        if not output_dir:
            output_dir = os.path.dirname(self.filepath)
        else:
            output_dir = os.path.normpath(output_dir)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            if not os.path.isdir(output_dir):
                raise NotADirectoryError(f"{output_dir} is not a directory.")

        subgraph_names = self.extract_subgraph_names(chr_only)
        func_inputs = []
        for name in subgraph_names:
            filename = os.path.basename(self.filepath).replace(".gfa", f".{name}.gfa")
            output_file = os.path.join(output_dir, filename)
            func_inputs.append((name, output_file))
        with mp.Pool() as pool:
            pool.starmap(self.extract_subgraph_by_name, func_inputs)
        return func_inputs

    def to_igraph(self) -> ig.Graph:
        """Convert the GFA file to an `igraph.Graph` object.

        Returns:
            igraph.Graph: The graph object converted from the GFA file.

        Raises:
            hap.DataInvalidError: If the graph is not a DAG.
        """

        # Create temp files
        info_file, node_file, edge_file, edge_tmp_file = fileutil.create_tmp_files(4)

        # Get awk scripts
        awk_file_func = os.path.join(
            hap.SOURCE_ROOT, "awk", "gfa", "parse_pansn_str.awk"
        )
        awk_file_gfa1 = os.path.join(hap.SOURCE_ROOT, "awk", "gfa", "gfa12csv.awk")
        awk_file_gfa2 = os.path.join(hap.SOURCE_ROOT, "awk", "gfa", "gfa22csv.awk")

        # `awk` -- Convert the GFA format graph to CSV tables of nodes and edges, plus a info file
        awk = [
            "awk",
            "-v",
            f"infofp={info_file}",
            "-v",
            f"nodefp={node_file}",
            "-v",
            f"edgefp={edge_file}",
            "-f",
            awk_file_func,
            "-f",
        ]
        if self.version < 2:
            awk.append(awk_file_gfa1)
        else:  # GFA 2
            awk.append(awk_file_gfa2)
        awk.append(self.filepath)

        locale = ["LC_ALL=C"]

        # `sort` & `join` -- Remove edges with absent segment id
        sort = ["sort", "-t", r"$'\t'", "-k"]
        sort_node = sort + ["1,1", "-o", node_file, node_file]
        sort_edge_1 = sort + ["1,1", "-o", edge_tmp_file, edge_file]
        sort_edge_2 = ["|"] + sort + ["2,2", "|"]
        join = ["join", "-t", r"$'\t'"]
        join1 = join + ["-1", "1", "-2", "1", "-o", "2.1,2.2", node_file, edge_tmp_file]
        join2 = join + [
            "-1",
            "2",
            "-2",
            "1",
            "-o",
            "1.1,1.2",
            "-",
            node_file,
            ">",
            edge_file,
        ]

        # `sed` -- Add table headers
        sed = ["sed", "-i"]
        sed_node = sed + [r"1i\name\tlength\tfrequency\tsources", node_file]
        sed_edge = sed + [r"1i\source\ttarget", edge_file]

        cmd = locale + join1 + sort_edge_2 + join2
        try:
            subprocess.run(awk)
            subprocess.run(
                " ".join(locale + sort_node), shell=True, executable="/bin/bash"
            )
            subprocess.run(
                " ".join(locale + sort_edge_1), shell=True, executable="/bin/bash"
            )
            subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash")
            subprocess.run(sed_node)
            subprocess.run(sed_edge)

            # Convertions
            node_df = pd.read_csv(
                node_file,
                sep="\t",
                dtype={"name": "str", "length": "int32", "frequency": "float32"},
                converters={"sources": lambda s: s.split(",")},
            )
            edge_df = pd.read_csv(
                edge_file, sep="\t", dtype={"source": "str", "target": "str"}
            )

            g = ig.Graph.DataFrame(edge_df, vertices=node_df, use_vids=False)

            # Store metadata in graph attributes
            info_df = pd.read_csv(
                info_file, sep="\t", header=None, names=["key", "value"]
            )
            info_dict = info_df.set_index("key")["value"].to_dict()
            for k, v in info_dict.items():
                g[k] = v

        finally:
            fileutil.remove_files([info_file, node_file, edge_file, edge_tmp_file])

        return g
