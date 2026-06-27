"""CSV output module.

Writes VM metadata as semicolon-delimited CSV to stdout.
"""

import dataclasses
import sys

from sources.base import VM


def write_csv(vms: list[VM]) -> None:
    """Write a list of VMs as semicolon-delimited CSV to stdout.

    The first row contains the field names derived from the :class:`~sources.base.VM`
    dataclass.  Each subsequent row contains the corresponding field values.

    Args:
        vms: List of :class:`~sources.base.VM` instances to serialise.
    """
    fields = [f.name for f in dataclasses.fields(VM)]
    header = ";".join(fields)
    print(header, file=sys.stdout)

    for vm in vms:
        row = ";".join(str(getattr(vm, f)) for f in fields)
        print(row, file=sys.stdout)
