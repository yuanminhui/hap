import os
import glob
import tempfile


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
