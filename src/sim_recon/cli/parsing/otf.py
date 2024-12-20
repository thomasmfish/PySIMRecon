from __future__ import annotations
import argparse
from typing import TYPE_CHECKING

from ...settings.formatting import filter_out_invalid_kwargs, OTF_FORMATTERS
from .shared import (
    add_general_args,
    add_override_args_from_formatters,
)

if TYPE_CHECKING:
    from typing import Any
    from collections.abc import Sequence

__all__ = ("parse_args",)


def parse_args(
    args: Sequence[str] | None = None,
) -> tuple[argparse.Namespace, dict[str, Any]]:
    parser = argparse.ArgumentParser(
        prog="sim-otf",
        description="SIM PSFs to OTFs",
        add_help=True,
    )
    parser.add_argument(
        "-p",
        "--psf",
        dest="psf_paths",
        required=True,
        nargs="+",
        help="Paths to PSF files to be reconstructed (multiple paths can be given)",
    )
    parser.add_argument(
        "-c",
        "--config-path",
        dest="config_path",
        help="Path to the root config that specifies the paths to the OTFs and the other configs (recommended)",
    )
    parser.add_argument(
        "-o",
        "--output-directory",
        help="If specified, the output directory in which the OTF files will be saved (otherwise each OTF will be saved in the same directory as its PSF)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="If specified, files will be overwritten if they already exist (unique filenames will be used otherwise)",
    )
    parser.add_argument(
        "--no-cleanup",
        dest="cleanup",
        action="store_false",
        help="If specified, files created during the OTF creation process will not be cleaned up",
    )
    parser.add_argument(
        "--shape",
        dest="xy_shape",
        default=None,
        nargs=2,
        type=int,
        help="Takes 2 integers (X Y), specifying the shape to crop PSFs to before converting (powers of 2 are fastest)",
    )
    parser.add_argument(
        "--centre",
        dest="xy_centre",
        default=None,
        nargs=2,
        type=float,
        help="Takes 2 floats (X Y), specifying the 0-indexed pixel coordinates that PSFs are cropped around (the image centre is used otherwise)",
    )

    add_general_args(parser)

    # Add arguments that override configured OTF settings
    add_override_args_from_formatters(parser, OTF_FORMATTERS)

    namespace, _ = parser.parse_known_args(args)

    # Split out kwargs to be used in makeotf
    otf_kwargs = filter_out_invalid_kwargs(
        vars(namespace), OTF_FORMATTERS, allow_none=False
    )

    return namespace, otf_kwargs


if __name__ == "__main__":
    parse_args()
