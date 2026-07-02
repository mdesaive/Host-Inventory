"""
output/csv_networks.py
----------------------
Netzwerk-CSV-Output-Modul für den VM-Metadaten-Exporter.

Schreibt eine VM-Netzwerk-Zuordnung im Long Format als semikolon-getrenntes
CSV. Pro VM und Netzwerk wird eine eigene Zeile ausgegeben. Dieses Format
eignet sich für die Migrationsplanung: in Excel oder LibreOffice Calc lässt
sich daraus per Pivot-Tabelle eine breite Netzwerk-Matrix erstellen.

Beispielausgabe::

    source_type;host;name;network
    vmware;esx-01;web-01;frontend
    vmware;esx-01;web-01;backend
    vmware;esx-01;db-01;backend
    docker;node-01;nginx;frontend

VMs ohne Netzwerke erscheinen mit leerem ``network``-Feld.

Verwendung via CLI::

    python main.py --source vmware --output csv-networks
"""

import csv
import sys
from typing import IO, List, Optional

from sources.base import VM

_DELIMITER = ";"
_FIELDNAMES = ["source_type", "host", "name", "network"]


def write_csv_networks(vms: List[VM], file: Optional[IO[str]] = None) -> None:
    """Schreibt VM-Netzwerk-Zuordnung im Long Format als semikolon-getrenntes CSV.

    Pro VM wird eine Zeile pro Netzwerk ausgegeben. VMs ohne Netzwerke
    erscheinen mit leerem ``network``-Feld. Die erste Zeile enthält
    die Spaltenköpfe.

    Args:
        vms: Liste der auszugebenden VM-Objekte.
        file: Ausgabe-Dateiobjekt. Bei None wird auf stdout geschrieben.
    """
    if not vms:
        return

    out = file or sys.stdout
    writer = csv.DictWriter(
        out,
        fieldnames=_FIELDNAMES,
        delimiter=_DELIMITER,
        lineterminator="\n",
    )
    writer.writeheader()

    for vm in vms:
        networks = [n.strip() for n in vm.networks.split(",") if n.strip()]
        if not networks:
            writer.writerow({
                "source_type": vm.source_type,
                "host": vm.host,
                "name": vm.name,
                "network": "",
            })
        else:
            for network in networks:
                writer.writerow({
                    "source_type": vm.source_type,
                    "host": vm.host,
                    "name": vm.name,
                    "network": network,
                })
