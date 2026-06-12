"""Backend de autenticación LDAP configurado en base de datos.

Lee la configuración del modelo ``core.LdapConfiguration`` (editable por el Owner)
y valida la contraseña contra el directorio usando ``ldap3``.

Regla de negocio (decisión congelada): SOLO autentica usuarios que YA existen
localmente (pre-creados por el Owner). No crea cuentas automáticamente. El login
usa un único formulario; Django prueba primero ModelBackend (local) y luego este.
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

logger = logging.getLogger(__name__)
User = get_user_model()


def _connect(config):
    """Abre una conexión ldap3 con la cuenta de servicio. Lanza excepción si falla."""
    import ldap3

    server = ldap3.Server(
        config.server_uri,
        use_ssl=config.use_ssl,
        connect_timeout=config.connect_timeout,
        get_info=ldap3.NONE,
    )
    conn = ldap3.Connection(
        server,
        user=config.bind_dn or None,
        password=config.bind_password or None,
        auto_bind=False,
        receive_timeout=config.connect_timeout,
    )
    if config.start_tls:
        conn.start_tls()
    if not conn.bind():
        raise RuntimeError(f"Bind de servicio falló: {conn.result}")
    return conn


def _find_user_dn(conn, config, login):
    search_filter = config.user_filter.replace("{login}", _escape(login))
    conn.search(config.user_search_base, search_filter, attributes=[config.email_attribute])
    if not conn.entries:
        return None
    return conn.entries[0].entry_dn


def _escape(value: str) -> str:
    """Escapa caracteres especiales de filtro LDAP (RFC 4515)."""
    out = []
    for ch in value:
        if ch in ("\\", "*", "(", ")", "\x00"):
            out.append("\\%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def test_connection(config):
    """Prueba el bind de servicio. Devuelve (ok: bool, mensaje: str)."""
    if not config.server_uri:
        return False, "Falta el servidor (URI)."
    try:
        conn = _connect(config)
        conn.unbind()
        return True, "Conexión y bind de servicio correctos."
    except Exception as exc:  # noqa: BLE001
        return False, f"No se pudo conectar: {exc}"


class DatabaseLDAPBackend(BaseBackend):
    """Autentica contra LDAP usando la config de core.LdapConfiguration."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        from apps.core.models import LdapConfiguration

        if not username or not password:
            return None

        config = LdapConfiguration.load()
        if not config.enabled or not config.server_uri:
            return None

        # Pre-creación obligatoria: el usuario debe existir localmente.
        user = User.objects.filter(email__iexact=username, is_active=True).first()
        if user is None:
            return None

        try:
            conn = _connect(config)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LDAP: bind de servicio falló: %s", exc)
            return None

        try:
            user_dn = _find_user_dn(conn, config, username)
            if not user_dn:
                return None
            # Verifica la contraseña haciendo bind como el propio usuario.
            import ldap3

            ok = ldap3.Connection(
                conn.server, user=user_dn, password=password,
                auto_bind=False, receive_timeout=config.connect_timeout,
            ).bind()
            return user if ok else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("LDAP: error autenticando a %s: %s", username, exc)
            return None
        finally:
            try:
                conn.unbind()
            except Exception:  # noqa: BLE001
                pass

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id).first()
