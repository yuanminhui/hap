import os
import subprocess

from hap import hapinfo
from hap.lib import fileutil, typeutil


def get_gfa_version(filepath: str) -> float:
    """Get the version of a GFA file. When no `VN` tag in `H` line is
    provided, an examination will run."""

    # a quick scan on version record
    cmd_rv = [
        "head",
        "-n",
        "1",
        filepath,
        "|",
        "awk",
        """'$1 == "H" {for (i = 2; i <= NF; ++i) if ($i ~ /^VN:/) {split($i, a, ":"); print a[3]}}'""",
    ]
    ver = subprocess.check_output(" ".join(cmd_rv), shell=True, text=True)
    try:
        ver = float(ver)
    except ValueError:
        # examine the essential charistics a version has
        cmd_ec = [
            "LC_ALL=C",
            "grep",
            "-m",
            "1",
            "-o",
            "-E",
            "'^(E|J|W)'",
            filepath,
        ]
        res = subprocess.run(
            " ".join(cmd_ec), shell=True, text=True, capture_output=True
        )
        if res.returncode == 0:
            char = res.stdout
            if char == "E":
                ver = 2.0
            elif char == "J":
                ver = 1.2
            elif char == "W":
                ver = 1.1
        elif res.returncode == 1:
            ver = 1.0

    finally:
        return ver


def move_sequence(filepath: str, gfa_version: float, outdir: str):
    """Move the sequences in a GFA file to (gzipped) `{basename}.seq.gz`, leaving
    a `*` as placeholder, add `LN` tag if not exist, and return the file path of
    the modified GFA file."""

    basename = typeutil.remove_suffix_containing(os.path.basename(filepath), ".gfa")
    outdir = os.path.normpath(outdir)
    seqfp = outdir + "/" + basename + ".seq.gz"
    outfp = outdir + "/" + basename + ".min.gfa"
    if os.path.exists(seqfp):
        os.remove(seqfp)

    # `awk` -- move sequences and calculate segment length
    awk = ["awk"]
    if gfa_version < 2:
        awk.append(
            f"""'BEGIN {{cmd = "gzip >> {seqfp}"; OFS="\\t"}} /^S/ {{if ($3 != "*") {{print $2, $3 | cmd; len = length($3); $3 = "*"; if (!match($0, /LN:/)) $0 = $0 "\tLN:i:" len}}}} {{print}} END {{close(cmd)}}'"""
        )
    else:  # GFA 2
        awk.append(
            f"""'BEGIN {{cmd = "gzip >> {seqfp}"; OFS="\\t"}} /^S/ {{if ($4 != "*") {{print $2, $4 | cmd; $4 = "*"}}}} {{print}} END {{close(cmd)}}'"""
        )
    awk.extend([filepath, ">", outfp])

    subprocess.run(" ".join(awk), shell=True)

    return outfp


def extract_subgraph_names(
    filepath: str, gfa_version: float, chr_only: bool = True
) -> list[str]:
    """Extract the names of subgraphs from a GFA file. Segment names
    in `W` lines are treated as subgraph names. When no `W` line exists, `PanSN`
    naming convention is required for extracting segment name from ids in `P` or
    `O|U` lines."""

    # get awk scripts
    awkfp_pps = os.path.join(hapinfo.srcpath, "lib", "parse_pansn_str.awk")

    locale = ["LC_ALL=C"]
    grep = ["grep"]
    awk = [
        "|",
        "awk",
        "-f",
        awkfp_pps,
        "-e",
    ]
    # `grep1` -- get records containing subgraph names
    # `awk` -- extract subgraph names
    if gfa_version < 1.1:
        grep1 = grep + ["^P"]
        awk.append(
            """'{res = parse_pansn_str($2, pa); if (delim == "") exit; if (!res) next; else print pa[3]}'"""
        )
    elif gfa_version >= 2.0:
        grep1 = grep + ["-E", "^(O|U)"]
        awk.append(
            """'{res = parse_pansn_str($2, pa); if (delim == "") exit; if (!res) next; else print pa[3]}'"""
        )
    else:
        grep1 = grep + ["^W"]
        awk.append("'{print $4}'")
    sort = ["|", "sort", "-u"]

    cmd = locale + grep1 + [filepath] + awk + sort
    # filter out non-chromosome level subgraphs
    if chr_only:
        grep2 = ["|"] + grep + ["-E", "'^chr[[:digit:]]{0,2}[[:alpha:]]{0,1}$'"]
        cmd += grep2

    res = subprocess.run(" ".join(cmd), shell=True, text=True, capture_output=True)
    if res.returncode == 0:
        return res.stdout.splitlines()
    elif res.returncode == 1:
        return []


def extract_subgraph(name: str, gfa_path: str, gfa_version: float, outdir: str):
    """Extract a subgraph by name from a GFA file, returning the sub-GFA's file path."""

    outfp = outdir + "/" + name + ".gfa"

    # create temp files
    setfp, mainfp = fileutil.create_tmp_files(2)

    # get awk scripts
    awkfp_es1 = os.path.join(hapinfo.srcpath, "lib", "extract_subg1.awk")
    awkfp_es2 = os.path.join(hapinfo.srcpath, "lib", "extract_subg2.awk")

    # `grep` -- get records that contain set of nodes from the whole graph by subgraph name
    # `awk` -- extract node ids from set records, find related records by them
    grep = ["LC_ALL=C", "grep", "-E"]
    awk = ["awk", "-f"]
    if gfa_version < 2:
        grep.append(f"'^(P|W).*{name}'")
        awk.append(awkfp_es1)
    else:  # GFA 2
        grep.append(f"'^(O|U).*{name}'")
        awk.append(awkfp_es2)
    grep.extend([gfa_path, ">", setfp])
    awk.extend([setfp, gfa_path, ">", mainfp])

    # `cat` -- concatenate main records with set records
    cat = ["cat", mainfp, setfp, ">", outfp]

    try:
        subprocess.run(" ".join(grep), shell=True)
        subprocess.run(" ".join(awk), shell=True)
        subprocess.run(" ".join(cat), shell=True)
    finally:
        # remove temp files
        fileutil.remove_files([mainfp, setfp])

    return outfp


def preprocess_gfa(filepath: str, outdir: str):
    """Preprocess a GFA file for subsequent building."""

    gfafp = os.path.normpath(filepath)
    if not os.path.exists(gfafp):
        raise FileNotFoundError(f"File {filepath} not found.")
    outdir = os.path.normpath(outdir)
    if not os.path.exists(outdir):
        os.mkdir(outdir)

    if filepath.endswith(".gz"):
        gfafp = fileutil.ungzip_file(gfafp)  # temp ungzipped GFA

    try:
        gfaver = get_gfa_version(gfafp)
        gfamin = move_sequence(gfafp, gfaver, outdir)
    finally:
        if filepath.endswith(".gz"):
            os.remove(gfafp)

    return gfamin, gfaver
