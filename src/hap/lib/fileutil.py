import os
import glob
import tempfile
import gzip


def get_files_from_dir(dirpath: str, extension: str = None):
    """Get files with specified extension under a directory."""

    dirp = os.path.normpath(dirpath)
    if not os.path.isdir(dirp):
        raise NotADirectoryError(f"{dirpath} is not a directory.")
    else:
        fps = (
            glob.glob(f"{dirp}/*.{extension}*") if extension else glob.glob(f"{dirp}/*")
        )
        if len(fps) == 0:
            raise FileNotFoundError(
                f"No file with '{extension}' found in the directory."
            )

    return fps


def remove_files(filepaths: list[str]):
    """Remove files by given file paths."""

    for fp in filepaths:
        os.remove(fp)


def create_tmp_files(num: int) -> list[str]:
    """Create temporary files of `num`, return the file paths."""

    tmpfps = []
    for i in range(num):
        fd, fp = tempfile.mkstemp()
        tmpfps.append(fp)
        os.close(fd)

    return tmpfps


def gzip_file(filepath: str):
    """Gzip a file and return the compressed file path."""

    if filepath.endswith(".gz"):
        print(f"{filepath} is already gzipped.")
        return filepath

    outfp = filepath + ".gz"
    with open(filepath, "r") as fin, gzip.open(outfp, "wt") as fout:
        fout.writelines(fin)

    return outfp


def ungzip_file(filepath: str):
    """Ungzip a file and return the decompressed file path."""

    if not filepath.endswith(".gz"):
        print(f"{filepath} is not gzipped.")
        return filepath

    outfp = filepath.replace(".gz", "")
    with gzip.open(filepath, "rt") as fin, open(outfp, "w") as fout:
        fout.writelines(fin)

    return outfp


def is_dir_empty(dirpath: str) -> bool:
    """Check if a directory is empty."""

    return len(os.listdir(dirpath)) == 0


def remove_suffix_containing(string: str, suffix: str) -> str:
    i = string.rfind(suffix)
    str = string[:i] if i != -1 else string
    return str
