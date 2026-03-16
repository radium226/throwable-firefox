import json
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urlparse
from urllib.request import urlretrieve
from zipfile import ZipFile

from loguru import logger


class Extension:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @staticmethod
    def from_url(url: str) -> "Extension":
        xpi_file_name = Path(urlparse(url).path).name or "extension.xpi"
        dest_dir = Path(mkdtemp())
        dest_path = dest_dir / xpi_file_name
        logger.debug("Downloading extension from {url} to {dest_path}", url=url, dest_path=dest_path)
        urlretrieve(url, dest_path)
        return Extension(dest_path)

    def addon_id(self) -> str:
        with ZipFile(str(self.path)) as zf:
            names = zf.namelist()

            # Modern WebExtensions store the ID in manifest.json
            if "manifest.json" in names:
                manifest = json.loads(zf.read("manifest.json"))
                gecko = (
                    (manifest.get("browser_specific_settings") or {}).get("gecko")
                    or (manifest.get("applications") or {}).get("gecko")
                    or {}
                )
                addon_id = gecko.get("id")
                if addon_id:
                    return addon_id

            # Legacy: extract from META-INF/mozilla.rsa certificate subject CN
            if "META-INF/mozilla.rsa" in names:
                return self._id_from_rsa(zf.read("META-INF/mozilla.rsa"))

        raise ValueError(f"Cannot determine addon ID from {self.path}")

    @staticmethod
    def _id_from_rsa(mozilla_rsa: bytes) -> str:
        from pyasn1.codec.der import decoder as der_decoder
        from pyasn1_modules import rfc5280, rfc5652

        content_info, _ = der_decoder.decode(mozilla_rsa, asn1Spec=rfc5652.ContentInfo())
        content_bytes = bytes(content_info.getComponentByName("content"))
        signed_data, _ = der_decoder.decode(content_bytes, asn1Spec=rfc5652.SignedData())

        for cert_choice in signed_data.getComponentByName("certificates"):
            cert_bytes = bytes(cert_choice)
            cert, _ = der_decoder.decode(cert_bytes, asn1Spec=rfc5280.Certificate())
            tbs = cert.getComponentByName("tbsCertificate")
            subject = tbs.getComponentByName("subject")
            for rdn in subject:
                for atv in rdn:
                    oid = str(atv.getComponentByName("type"))
                    if oid == "2.5.4.3":  # commonName
                        val_bytes = bytes(atv.getComponentByName("value"))
                        decoded_val, _ = der_decoder.decode(val_bytes)
                        return str(decoded_val)

        raise ValueError("No CN found in mozilla.rsa certificate")
