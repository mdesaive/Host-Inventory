"""CSV output module.

Writes VM metadata as semicolon-delimited CSV to stdout.
"""

import dataclasses
import sys

from typing import IO, Optional
from sources.base import VM


def write_csv(vms: list[VM], file: Optional[IO[str]] = None) -> None:
    """Write a list of VMs as semicolon-delimited CSV to stdout.

    The first row contains the field names derived from the :class:`~sources.base.VM`
    dataclass.  Each subsequent row contains the corresponding field values.

    Args:
        vms: List of :class:`~sources.base.VM` instances to serialise.
    """
    out = file or sys.stdout
    fields = [f.name for f in dataclasses.fields(VM)]
    header = ";".join(fields)
    print(header, file=out)

    for vm in vms:
        row = ";".join(str(getattr(vm, f)) for f in fields)
        print(row, file=out)
