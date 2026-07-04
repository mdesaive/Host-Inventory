"""VM Metadata Exporter – CLI entrypoint.

Usage::

    python main.py --source docker|vmware \n        --output csv-vms|csv-networks|prometheus-vms|prometheus-networks \n        --host <host>

Run ``python main.py --help`` for a full list of options.
"""

import argparse
import os
import sys
import tempfile
from typing import Callable, List, Optional, IO

from output.csv import write_csv
from output.prometheus import write_prometheus
from sources.base import VM
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
        choices=["csv-vms", "csv-networks", "prometheus"],
        help="Output format.",
    )
    parser.add_argument(
        "-o", "--outfile",
        default=None,
        help="Output file path. Default: stdout.",
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
        default=None,
        help="Password for VMware authentication. Prefer --password-file.",
    )
    parser.add_argument(
        "--password-file",
        default=None,
        dest="password_file",
        help="Path to a file containing the VMware password. "
             "Takes precedence over --password.",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        dest="no_verify_ssl",
        help="Disable TLS certificate verification.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress API call logging.",
    )
    return parser


def _resolve_password(args: argparse.Namespace) -> str:
    """Resolve the VMware password from --password-file or --password.

    Args:
        args: Parsed CLI arguments.

    Returns:
        The resolved password string.

    Raises:
        SystemExit: If neither --password-file nor --password is provided,
            or if the password file cannot be read.
    """
    if args.password_file:
        try:
            with open(args.password_file, "r", encoding="utf-8") as pw_file:
                return pw_file.read().strip()
        except OSError as exc:
            print(f"Error reading --password-file: {exc}", file=sys.stderr)
            sys.exit(1)
    if args.password:
        print(
            "Warning: \"--password\" exposes the secret in shell history and "
            "process listings. Prefer --password-file.",
            file=sys.stderr,
        )
        return args.password
    print("Error: --source vmware requires --password or --password-file.",
          file=sys.stderr)
    sys.exit(1)


def _write_output(
    write_fns: List[Callable[[List[VM], Optional[IO[str]]], None]],
    vms: List[VM],
    outfile: Optional[str],
) -> None:
    """Write output either atomically to a file or directly to stdout.

    When ``outfile`` is given the output is first written to a temporary
    file in the same directory, then atomically renamed to ``outfile``.
    This ensures node_exporter never reads a partially written file.

    When ``outfile`` is None the output is written directly to stdout.

    Args:
        write_fns: Output function to call, e.g. :func:`~output.prometheus.write_prometheus`.
        vms: List of :class:`~sources.base.VM` instances to emit.
        outfile: Destination file path, or None for stdout.
    """
    if outfile is None:
        for write_fn in write_fns:
            write_fn(vms, None)
        return

    dirpath = os.path.dirname(os.path.abspath(outfile))
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
            for write_fn in write_fns:
                write_fn(vms, tmp_file)
        os.replace(tmp_path, outfile)
        os.chmod(outfile, 0o644)
    except Exception:  # pylint: disable=broad-except
        os.unlink(tmp_path)
        raise


def main() -> int:
    """Parse arguments, fetch VM metadata, and write output.

    Returns:
        Exit code: ``0`` on success, ``1`` on error.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # Build source
    if args.source == "docker":
        source = DockerSource(host=args.host, no_verify_ssl=args.no_verify_ssl, quiet=args.quiet)
    elif args.source == "vmware":
        password = _resolve_password(args)
        source = VMwareSource(
            host=args.host,
            username=args.username,
            password=password,
            no_verify_ssl=args.no_verify_ssl,
            quiet=args.quiet,
        )
    else:
        raise ValueError(f"Unknown source: {args.source}")

    vms = source.fetch_vms()

    # Write output
    if args.output == "csv-vms":
        _write_output([write_csv], vms, args.outfile)
    elif args.output == "csv-networks":
        from output.csv_networks import write_csv_networks  # pylint: disable=import-outside-toplevel
        _write_output([write_csv_networks], vms, args.outfile)
    elif args.output == "prometheus":
        from output.prometheus_networks import write_prometheus_networks  # pylint: disable=import-outside-toplevel
        _write_output([write_prometheus, write_prometheus_networks], vms, args.outfile)
    else:
        raise ValueError(f"Unknown output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
