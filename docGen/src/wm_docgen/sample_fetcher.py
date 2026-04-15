"""Fetch representative public webMethods package artifacts."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen


SAMPLE_FILES = {
    "Permafrost/Tundra": [
        "manifest.v3",
        "ns/tundra/content/deliver/flow.xml",
        "ns/tundra/content/deliver/node.ndf",
    ],
    "johnpcarter/JcPublicTools": [
        "manifest.v3",
        "ns/jc/tools/pub/client/sendSMS/flow.xml",
        "ns/jc/tools/pub/client/sendSMS/node.ndf",
    ],
    "ibm-wm-transition/webmethods-integrationserver-pgpencryption": [
        "PGP/manifest.v3",
        "PGP/ns/pgp/services/decrypt/decryptFile/flow.xml",
        "PGP/ns/pgp/services/decrypt/decryptFile/node.ndf",
    ],
    "ibm-wm-transition/WxSAPIntegration": [
        "WxSAPIntegration/manifest.v3",
        "WxSAPIntegration/ns/wx/sap/integration/configuration/apis/wxsapintegrationConfiguration_/services/sap/getConnection/flow.xml",
        "WxSAPIntegration/ns/wx/sap/integration/configuration/apis/wxsapintegrationConfiguration_/services/sap/getConnection/node.ndf",
    ],
}


def fetch_samples(out_dir: Path) -> list[Path]:
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for repo, paths in SAMPLE_FILES.items():
        branch = "main" if repo == "johnpcarter/JcPublicTools" else "master"
        for path in paths:
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
            destination = out_dir / repo.replace("/", "__") / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            with urlopen(url, timeout=30) as response:
                destination.write_bytes(response.read())
            written.append(destination)
    return written
