from __future__ import annotations
import logging
import platform
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import weakref as _weakref
from typing import TYPE_CHECKING

from ..exceptions import (
    PySimReconFileExistsError,
    PySimReconFileNotFoundError,
    PySimReconIOError,
    PySimReconOSError,
    PySimReconValueError,
)

if TYPE_CHECKING:
    from typing import Literal
    from os import PathLike
    from collections.abc import Generator

logger = logging.getLogger(__name__)

OTF_NAME_STUB = "OTF"
RECON_NAME_STUB = "recon"

_OUTPUT_TYPE_STUBS = {"otf": OTF_NAME_STUB, "recon": RECON_NAME_STUB}

_WINDOWS_FN_SUB = re.compile('[<>:"/\\|?*]')
_LINUX_FN_SUB = re.compile("/")
_DARWIN_FN_SUB = re.compile("[/:]")


def get_temporary_path(directory: Path, stem: str, suffix: str) -> Path:
    tiff_path = (directory / f"{stem}_{uuid4()}").with_suffix(suffix)
    if not tiff_path.exists():
        return tiff_path
    raise PySimReconFileExistsError(
        f"Failed to create temporary file as the following already exists: {tiff_path}"
    )


def ensure_unique_filepath(
    output_directory: Path, stem: str, suffix: str, max_iter: int = 99
) -> Path:
    path = output_directory / f"{stem}{suffix}"
    if not path.exists():
        return path
    if max_iter <= 1:
        raise PySimReconValueError("max_iter must be >1")
    output_path = None
    for i in range(1, max_iter + 1):
        output_path = output_directory / f"{stem}_{i}{suffix}"
        if not output_path.exists():
            logger.debug("'%s' was not unique, so '%s' will be used", path, output_path)
            return output_path
    error_str = f"Failed to create unique file path after {max_iter} attempts."
    if output_path is not None:
        error_str += f" Final attempt was '{output_path}'."
    raise PySimReconIOError(error_str)


def ensure_valid_filename(filename: str) -> str:
    rstrip = " "
    system = platform.system()
    if system == "Windows":
        invalid_chars = _WINDOWS_FN_SUB
        rstrip = " ."
    elif system == "Linux":
        invalid_chars = _LINUX_FN_SUB
    elif system == "Darwin":
        invalid_chars = _DARWIN_FN_SUB
    else:
        raise PySimReconOSError(f"{system} is not a supported system")

    new_filename = filename.rstrip(rstrip)
    new_filename = re.sub(invalid_chars, "_", new_filename)

    if filename != new_filename:
        logger.debug(
            "Removed invalid filename characters: '%s' is now '%s'",
            filename,
            new_filename,
        )

    return new_filename


def create_output_path(
    file_path: str | PathLike[str],
    output_type: Literal["otf", "recon"],
    suffix: str,
    output_directory: str | PathLike[str] | None = None,
    wavelength: int | None = None,
    mod_timestamp: bool = False,
    ensure_unique: bool = False,
    max_path_iter: int = 99,
) -> Path:
    file_path = Path(file_path)

    output_fp_parts = [file_path.stem, _OUTPUT_TYPE_STUBS[output_type]]

    if wavelength is not None:
        output_fp_parts.append(str(wavelength))

    if mod_timestamp:
        # datetime.isoformat fails on Windows due to colons being invalid in paths
        output_fp_parts.append(
            datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        )

    if output_directory is None:
        output_directory = file_path.parent
    else:
        output_directory = Path(output_directory)

    file_stem = "_".join(output_fp_parts)

    if ensure_unique:
        return ensure_unique_filepath(
            output_directory, stem=file_stem, suffix=suffix, max_iter=max_path_iter
        )
    return output_directory / ensure_valid_filename(f"{file_stem}{suffix}")


@contextmanager
def redirect_output_to(file_path: str | PathLike[str]) -> Generator[None, None, None]:
    # Can't use contextlib's redirect_stdout and redirect_stderr as the C++ output isn't captured
    file_path = Path(file_path)
    # Save original file descriptors
    stdout_fd = sys.stdout.fileno()
    stderr_fd = sys.stderr.fileno()
    saved_stdout_fd = os.dup(stdout_fd)
    saved_stderr_fd = os.dup(stderr_fd)
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    try:
        with file_path.open("w+", buffering=1) as f:
            f_fd = f.fileno()
            try:

                os.dup2(f_fd, stdout_fd)
                os.dup2(f_fd, stderr_fd)
                sys.stdout = f
                sys.stderr = f
                yield
            except Exception:
                logger.error(
                    "Failed to redirect output to log at %s", file_path, exc_info=True
                )
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os.fsync(f_fd)
                # Reset stdout and stderr file descriptors
                os.dup2(saved_stdout_fd, stdout_fd)
                os.dup2(saved_stderr_fd, stderr_fd)
                sys.stdout = saved_stdout
                sys.stderr = saved_stderr
    except Exception:
        logger.error("Failed to create log file %s", file_path)


def combine_text_files(
    output_path: str | PathLike[str],
    *paths: str | PathLike[str],
    header: str | None = None,
    sep_char: str = "-",
    sep_lines: int = 2,
    sep_length: int = 80,
) -> None:

    if sep_lines < 1:
        separator = "\n"
    else:
        if sep_length < 1:
            separator_line = ""
        else:
            separator_line = f"{sep_char * sep_length}"
        separator = f"\n{'\n'.join([separator_line] * sep_lines)}\n"
    contents_generator = (Path(fp).read_text() for fp in paths)
    with open(output_path, "w+") as f:
        if header is not None:
            f.write(header + separator)
        f.write(separator.join(contents_generator))
        os.fsync(f.fileno())


class NamedTemporaryDirectory(TemporaryDirectory):

    def __init__(
        self,
        directory: str | PathLike[str],
        name: str | None = None,
        parents: bool = True,
        allow_fallback: bool = True,
        ignore_cleanup_errors: bool = False,
        *,
        delete: bool = True,
    ) -> None:
        self.name: str
        if name is not None:
            path = Path(directory) / name
            if not path.parent.is_dir():
                if not parents:
                    raise PySimReconFileNotFoundError(
                        f"Parent directory {path.parent} does not exist"
                    )
                path.parent.mkdir(parents=True)
            if not path.exists():
                path.mkdir(exist_ok=False, parents=False)
                self.name = str(path)
                self._ignore_cleanup_errors = ignore_cleanup_errors
                self._delete = delete
                self._finalizer = _weakref.finalize(
                    self,
                    self._cleanup,  # type: ignore
                    self.name,
                    warn_message="Implicitly cleaning up {!r}".format(self),
                    ignore_errors=self._ignore_cleanup_errors,
                    delete=self._delete,
                )
                return
            elif not allow_fallback:
                raise PySimReconFileExistsError(
                    f"Directory cannot be created as '{path}' exists"
                )
        # Used if name is not defined or if the path already exists and allow_fallback is True
        super().__init__(
            prefix=name,
            dir=directory,
            ignore_cleanup_errors=ignore_cleanup_errors,
            delete=delete,
        )


@contextmanager
def delete_directory_if_empty(
    path: str | PathLike[str] | None,
) -> Generator[None, None, None]:
    if path is None:
        yield None
        return
    try_cleanup = not os.path.isdir(path)
    try:
        yield None
    finally:
        if try_cleanup and os.path.isdir(path):
            with os.scandir(path) as it:
                directory_empty = not any(it)  # False if any entries found
            if directory_empty:
                logger.info(
                    "Removing empty directory '%s'",
                    path,
                )
                os.rmdir(path)
