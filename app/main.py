"""VM Metadata Exporter – CLI entrypoint.

Usage::

    python main.py --source docker|vmware --output csv|prometheus --host <host>

Run ``python main.py --help`` for a full list of options.
"""

import argparse
import sys

from output.csv import write_csv
from output.prometheus import write_prometheus
from sources.docker import DockerSource
from sources.vmware import VMwareSource


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        description="Collect VM/container metadata and emit CSV or Prometheus metrics.",
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=["docker", "vmware"],
        help="Metadata source type.",
    )
    parser.add_argument(
        "--output",
        required=True,
        choices=["csv", "prometheus"],
        help="Output format.",
    )
    parser.add_argument(
        "--host",
        default="",
        help="Connection endpoint of the source (URL or hostname).",
    )
    parser.add_argument(
        "--username",
        default="user",
        help="Username for VMware authentication (default: user).",
    )
    parser.add_argument(
        "--password",
        default="pass",
        help="Password for VMware authentication (default: pass).",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        dest="no_verify_ssl",
        help="Disable TLS certificate verification.",
    )
    return parser


def main() -> int:
    """Parse arguments, fetch VM metadata, and write output.

    Returns:
        Exit code: ``0`` on success, ``1`` on argument error.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # Build source
    if args.source == "docker":
        source = DockerSource(host=args.host, no_verify_ssl=args.no_verify_ssl)
    elif args.source == "vmware":
        source = VMwareSource(
            host=args.host,
            username=args.username,
            password=args.password,
            no_verify_ssl=args.no_verify_ssl,
        )
    else:
        raise ValueError(f"Unknown source: {args.source}")

    vms = source.fetch_vms()

    # Write output
    if args.output == "csv":
        write_csv(vms)
    elif args.output =="prometheus":
        write_prometheus(vms)
    else:
        raise ValueError(f"Unknown output: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
