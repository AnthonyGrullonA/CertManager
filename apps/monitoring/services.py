"""Servicio de chequeo de certificados SSL/TLS.

Portado y ampliado desde el `check_certificate_expiry` del sistema legacy
(`certapp_old/valida.py`). Es código puro: NO toca la base de datos ni envía
correos; sólo abre la conexión, parsea el certificado y devuelve un CheckResult.
Esto lo hace testeable y reutilizable por el command `check_certificates` y por
la acción "Probar ahora" de la API.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from apps.core.enums import CertificateStatus


class SSRFValidationError(Exception):
    """El host objetivo resuelve a una dirección no permitida (interna/metadata)."""


def _is_blocked_address(ip: str) -> bool:
    """True si la IP cae en un rango interno/metadata que debemos rechazar.

    Bloquea loopback, link-local (incluye metadata 169.254.169.254), privadas
    (10/8, 172.16/12, 192.168/16), unique-local IPv6 (fc00::/7, ::1), no
    especificadas, reservadas y multicast.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # No parseable como IP: por seguridad lo tratamos como bloqueado.
        return True
    # ipaddress cubre 127/8, ::1, 169.254/16, fe80::/10, 10/8, 172.16/12,
    # 192.168/16 y fc00::/7 mediante estas banderas.
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_public_host(domain: str) -> list[str]:
    """Resuelve `domain` y verifica que NINGUNA IP sea interna/metadata.

    Devuelve la lista de IPs resueltas (públicas). Lanza SSRFValidationError con
    una causa clara si la resolución falla o alguna dirección está bloqueada.
    """
    try:
        infos = socket.getaddrinfo(domain, None)
    except socket.gaierror:
        raise SSRFValidationError("No se pudo resolver el dominio (DNS).")
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise SSRFValidationError("No se pudo resolver el dominio (DNS).")
    for ip in ips:
        if _is_blocked_address(ip):
            raise SSRFValidationError(
                f"El host resuelve a una dirección interna o no permitida ({ip})."
            )
    return ips

try:  # cryptography es opcional en tiempo de import; requerida en runtime real
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    _HAS_CRYPTO = True
except Exception:  # pragma: no cover
    _HAS_CRYPTO = False


@dataclass
class CheckResult:
    """Resultado de un chequeo. `ok=False` indica error de conexión/verificación."""

    ok: bool
    status: str
    days_left: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    issuer: str = ""
    subject: str = ""
    serial: str = ""
    fingerprint_sha256: str = ""
    signature_algorithm: str = ""
    key_size: int | None = None
    san: list[str] = field(default_factory=list)
    chain: list[dict] = field(default_factory=list)
    error_message: str = ""
    latency_ms: int | None = None


def compute_status(days_left: int | None, threshold: int, critical: int) -> str:
    """Deriva el estado del certificado a partir de los días restantes."""
    if days_left is None:
        return CertificateStatus.SIN_CHEQUEAR
    if days_left < 0:
        return CertificateStatus.VENCIDO
    if days_left < critical:
        return CertificateStatus.CRITICO
    if days_left < threshold:
        return CertificateStatus.POR_VENCER
    return CertificateStatus.VIGENTE


class SSLChecker:
    """Abre una conexión TLS y extrae los datos del certificado del servidor."""

    def __init__(self, timeout: int = 10, allow_legacy_renegotiation: bool = True):
        self.timeout = timeout
        self.allow_legacy_renegotiation = allow_legacy_renegotiation

    def _build_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        # Equivalente al openssl.cnf legacy (UnsafeLegacyRenegotiation) para
        # servidores antiguos que lo requieren.
        if self.allow_legacy_renegotiation:
            legacy = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
            if legacy:
                context.options |= legacy
        return context

    def check(self, domain: str, port: int, threshold: int, critical: int) -> CheckResult:
        start = time.monotonic()
        # Validación anti-SSRF previa: resuelve el host y rechaza direcciones
        # internas/metadata ANTES de abrir cualquier conexión.
        try:
            validate_public_host(domain)
        except SSRFValidationError as exc:
            return self._error(str(exc), start)
        context = self._build_context()
        try:
            with socket.create_connection((domain, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    der = ssock.getpeercert(binary_form=True)
                    peercert = ssock.getpeercert()
                    chain = self._extract_chain(ssock)
            result = self._parse(der, peercert, threshold, critical)
            result.chain = chain
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result
        except ssl.SSLCertVerificationError as exc:
            return self._error(f"Verificación del certificado falló: {exc.verify_message or exc}", start)
        except ssl.CertificateError as exc:
            return self._error(f"El nombre del certificado no coincide: {exc}", start)
        except socket.gaierror:
            return self._error("No se pudo resolver el dominio (DNS).", start)
        except (socket.timeout, TimeoutError):
            return self._error("Tiempo de conexión agotado.", start)
        except (ConnectionError, OSError) as exc:
            return self._error(f"No se pudo conectar al dominio: {exc}", start)

    # --- internos ---------------------------------------------------------

    def _error(self, message: str, start: float) -> CheckResult:
        return CheckResult(
            ok=False,
            status=CertificateStatus.ERROR,
            error_message=message,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def _extract_chain(self, ssock) -> list[dict]:
        """Cadena de confianza si la versión de Python la expone."""
        chain = []
        getter = getattr(ssock, "get_unverified_chain", None) or getattr(
            ssock, "get_verified_chain", None
        )
        if not getter or not _HAS_CRYPTO:
            return chain
        try:
            for entry in getter():
                cert = x509.load_der_x509_certificate(entry.public_bytes())
                chain.append({
                    "subject": cert.subject.rfc4514_string(),
                    "issuer": cert.issuer.rfc4514_string(),
                })
        except Exception:
            pass
        return chain

    def _parse(self, der: bytes, peercert: dict, threshold: int, critical: int) -> CheckResult:
        # Fallback básico desde el dict de ssl (siempre disponible).
        valid_to = self._parse_ssl_date(peercert.get("notAfter")) if peercert else None
        valid_from = self._parse_ssl_date(peercert.get("notBefore")) if peercert else None

        result = CheckResult(ok=True, status=CertificateStatus.SIN_CHEQUEAR)

        if _HAS_CRYPTO and der:
            cert = x509.load_der_x509_certificate(der)
            valid_from = cert.not_valid_before_utc
            valid_to = cert.not_valid_after_utc
            result.issuer = cert.issuer.rfc4514_string()
            result.subject = cert.subject.rfc4514_string()
            result.serial = format(cert.serial_number, "x")
            result.fingerprint_sha256 = cert.fingerprint(hashes.SHA256()).hex(":")
            result.signature_algorithm = cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else ""
            result.key_size = self._key_size(cert)
            result.san = self._san(cert)
        elif peercert:
            result.issuer = self._rdn(peercert.get("issuer"))
            result.subject = self._rdn(peercert.get("subject"))
            result.san = [v for k, v in peercert.get("subjectAltName", []) if k == "DNS"]

        result.valid_from = valid_from
        result.valid_to = valid_to
        if valid_to:
            now = datetime.now(timezone.utc)
            result.days_left = (valid_to - now).days
        result.status = compute_status(result.days_left, threshold, critical)
        return result

    @staticmethod
    def _key_size(cert) -> int | None:
        try:
            pub = cert.public_key()
            if isinstance(pub, rsa.RSAPublicKey):
                return pub.key_size
            if isinstance(pub, ec.EllipticCurvePublicKey):
                return pub.curve.key_size
            return getattr(pub, "key_size", None)
        except Exception:
            return None

    @staticmethod
    def _san(cert) -> list[str]:
        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            return ext.value.get_values_for_type(x509.DNSName)
        except Exception:
            return []

    @staticmethod
    def _parse_ssl_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _rdn(rdn_seq) -> str:
        """Aplana la estructura de issuer/subject del dict de ssl a un string."""
        if not rdn_seq:
            return ""
        parts = []
        for rdn in rdn_seq:
            for key, val in rdn:
                parts.append(f"{key}={val}")
        return ", ".join(parts)
