"""Bootstrap de PRODUCCIÓN: usuario Owner + configuración default + certificados.

Carga, de forma idempotente:

  1. El usuario **Owner** de la organización (email y contraseña por entorno; NO
     se hardcodean secretos porque el repo es público). Es Owner de la app pero NO
     superusuario de Django (el admin de Django queda solo para el `createsuperuser`).
  2. La **configuración** global (OrganizationSettings) con los defaults de
     producción del sistema. El SMTP se toma de variables de entorno si están.
     NO toca grupos ni certificados existentes: solo la configuración.
  3. Los **certificados** desde un archivo con el formato legacy
     ``dominio|correo|umbral|puerto`` (por defecto ``./cert.txt`` en la raíz):
       - Monitoreo por **plataforma** y **correo** para todos.
       - **Ubicación**: dominios que empiezan con ``ntp``/``ntt`` -> "Servidor";
         los que contienen ``claro.com.do`` -> "netscaler".
       - **Grupos**: cada correo de soporte ``sp*`` se vuelve un Team; el cert se
         asigna a esos grupos (M2M). El Owner queda como Colaborador de
         ``sp_canales_electronicos`` (su grupo); los demás ``sp*`` se crean sin él.
       - **Destinatarios**: TODOS los correos del dominio (sp y no-sp) quedan como
         CertificateRecipient (notificación por correo).

Variables de entorno (secretos fuera del código):
    CF_OWNER_EMAIL      (default: jairol_grullon@claro.com.do)
    CF_OWNER_PASSWORD   (si falta, el Owner queda sin contraseña usable)
    CF_ORG_NAME         (opcional, nombre de la organización)
    CF_SMTP_HOST / CF_SMTP_PORT / CF_SMTP_USER / CF_SMTP_PASSWORD /
    CF_SMTP_FROM / CF_SMTP_USE_TLS   (opcionales; si no, SMTP queda vacío)

Uso:
    python manage.py data_update_certs_app --source ./cert.txt
    python manage.py data_update_certs_app --dry-run
"""
from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.certificates.models import Certificate, CertificateRecipient
from apps.core.enums import MembershipRole
from apps.core.models import OrganizationSettings
from apps.teams.models import Membership, Team

User = get_user_model()

DEFAULT_OWNER_EMAIL = "jairol_grullon@claro.com.do"
OWNER_GROUP = "sp_canales_electronicos"  # el grupo propio del Owner
DEFAULT_TEAM = "Sin asignar"             # team primario contenedor
DEFAULT_PORT = 443
# Sin ``$``: se usa .match() y se toma el prefijo válido, para salvar typos
# reales del cert.txt legado como ``user@claro.com.do@claro.com.do``.
EMAIL_RE = re.compile(r"[^@\s|]+@[^@\s|]+\.[^@\s|]+")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://")


def derive_location(domain: str) -> str:
    """Ubicación según el dominio: ntp/ntt -> Servidor, claro.com.do -> netscaler."""
    d = domain.lower()
    if d.startswith("ntp") or d.startswith("ntt"):
        return "Servidor"
    if "claro.com.do" in d:
        return "netscaler"
    return ""


def is_support_group(email: str) -> bool:
    """Correos de grupos de soporte: la parte local empieza con 'sp'."""
    local = email.split("@", 1)[0].lower()
    return local.startswith("sp")


def team_name_from_email(email: str) -> str:
    """Nombre del Team a partir del correo de soporte, normalizado.

    Minúsculas + guiones a guion bajo, para que variantes del mismo grupo caigan
    en UN solo Team (p.ej. ``sp_adm-finanzas`` y ``sp_adm_finanzas`` ->
    ``sp_adm_finanzas``). No colisiona grupos distintos: solo unifica los que ya
    difieren únicamente por ``-`` vs ``_``.
    """
    return email.split("@", 1)[0].lower().replace("-", "_")


class Command(BaseCommand):
    help = "Bootstrap de producción: Owner + configuración default + certificados (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="cert.txt", help="Ruta al cert.txt (default: ./cert.txt).")
        parser.add_argument(
            "--owner-email",
            default=os.environ.get("CF_OWNER_EMAIL", DEFAULT_OWNER_EMAIL),
            help="Email del Owner (o CF_OWNER_EMAIL).",
        )
        parser.add_argument("--skip-certs", action="store_true", help="Solo Owner + configuración.")
        parser.add_argument("--dry-run", action="store_true", help="No escribe en la BD; solo reporta.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        with transaction.atomic():
            owner = self._ensure_owner(options["owner_email"], dry)
            self._seed_config(dry)
            if not options["skip_certs"]:
                self._import_certs(Path(options["source"]), owner, dry)
            if dry:
                self.stdout.write(self.style.NOTICE("Dry-run: revirtiendo, no se escribió nada."))
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Listo."))
        if not options["skip_certs"] and not dry:
            self.stdout.write("Sugerencia: corre `python manage.py check_certificates` para poblar el estado real.")

    # --- 1) Owner ---------------------------------------------------------
    def _ensure_owner(self, email: str, dry: bool):
        owner, created = User.objects.get_or_create(
            email=email,
            defaults={"is_owner": True, "is_staff": False, "is_superuser": False},
        )
        if not created and not owner.is_owner:
            owner.is_owner = True
            owner.save(update_fields=["is_owner"])
        password = os.environ.get("CF_OWNER_PASSWORD")
        if password:
            owner.set_password(password)
            owner.save()
            self.stdout.write(f"Owner {'creado' if created else 'actualizado'}: {email} (contraseña fijada por CF_OWNER_PASSWORD).")
        else:
            if created:
                owner.set_unusable_password()
                owner.save()
            self.stdout.write(self.style.WARNING(
                f"Owner {'creado' if created else 'existente'}: {email}. "
                "Sin CF_OWNER_PASSWORD: contraseña NO fijada (usa `changepassword` o exporta la variable)."
            ))
        return owner

    # --- 2) Configuración -------------------------------------------------
    def _seed_config(self, dry: bool):
        org = OrganizationSettings.load()  # crea el singleton con los defaults de producción
        if name := os.environ.get("CF_ORG_NAME"):
            org.org_name = name
        # SMTP por entorno (secretos fuera del código). Si no hay host, se deja vacío.
        host = os.environ.get("CF_SMTP_HOST")
        if host:
            org.smtp_host = host
            org.smtp_port = int(os.environ.get("CF_SMTP_PORT", org.smtp_port or 587))
            org.smtp_user = os.environ.get("CF_SMTP_USER", org.smtp_user)
            if pwd := os.environ.get("CF_SMTP_PASSWORD"):
                org.smtp_password = pwd
            org.smtp_from = os.environ.get("CF_SMTP_FROM", org.smtp_from)
            org.smtp_use_tls = os.environ.get("CF_SMTP_USE_TLS", "1") not in ("0", "false", "False")
        # Ventana de chequeo por defecto (horario valle 02:00–05:00) si no está fijada.
        if org.preferred_check_window_start is None:
            org.preferred_check_window_start = datetime.time(2, 0)
        if org.preferred_check_window_end is None:
            org.preferred_check_window_end = datetime.time(5, 0)
        org.save()
        win = ""
        if org.preferred_check_window_start:
            win = f"; ventana {org.preferred_check_window_start:%H:%M}–{org.preferred_check_window_end:%H:%M}"
        self.stdout.write(
            f"Configuración cargada (chequeo {org.check_interval_hours}h, timeout {org.connect_timeout}s, "
            f"reintentos {org.retries}, TZ {org.timezone}{win})"
            + (f"; SMTP {org.smtp_host}:{org.smtp_port}." if org.smtp_host else "; SMTP sin configurar.")
        )

    # --- 3) Certificados --------------------------------------------------
    def _import_certs(self, source: Path, owner, dry: bool):
        if not source.exists():
            raise CommandError(
                f"No existe el archivo de certificados: {source}. "
                "Coloca el cert.txt en la raíz o pasa --source <ruta>."
            )
        # Agrega correos por (dominio, puerto), preservando umbral por correo.
        certs: dict[tuple[str, int], dict] = {}
        skipped = 0
        for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = self._parse_line(raw.strip())
            if not parsed:
                skipped += 1
                continue
            for domain, email, threshold, port in parsed:
                entry = certs.setdefault((domain, port), {"threshold": threshold, "emails": {}})
                if threshold is not None:
                    entry["threshold"] = max(entry["threshold"] or threshold, threshold)
                prev = entry["emails"].get(email)
                entry["emails"][email] = max(prev or threshold or 0, threshold or 0) or None

        # Team contenedor + caché de teams de soporte (sp*).
        default_team = self._get_team(DEFAULT_TEAM, owner)
        owner_group_team = self._get_team(OWNER_GROUP, owner)
        self._ensure_membership(owner, owner_group_team)  # Owner = ADMIN de su grupo
        team_cache: dict[str, Team] = {DEFAULT_TEAM: default_team, OWNER_GROUP: owner_group_team}

        created = updated = recipients_added = 0
        for (domain, port), data in certs.items():
            location = derive_location(domain)
            emails = sorted(data["emails"].items())
            sp_teams = []
            for email, _t in emails:
                if is_support_group(email):
                    name = team_name_from_email(email)
                    if name not in team_cache:
                        team_cache[name] = self._get_team(name, owner)
                    if team_cache[name] not in sp_teams:
                        sp_teams.append(team_cache[name])

            # Idempotencia robusta: busca por (dominio, puerto) en cualquier team.
            cert = Certificate.objects.filter(domain=domain, port=port).first()
            if cert is None:
                cert = Certificate.objects.create(
                    team=default_team,
                    domain=domain,
                    port=port,
                    location=location,
                    alert_threshold_days=data["threshold"],
                    notify_platform=True,
                    notify_email=True,
                    notify_webhook=False,
                    notify_sms=False,
                    tags=["produccion"],
                    notes="Cargado por data_update_certs_app.",
                    created_by=owner,
                )
                created += 1
            else:
                cert.location = location
                cert.alert_threshold_days = data["threshold"]
                cert.notify_platform = True
                cert.notify_email = True
                cert.save(update_fields=[
                    "location", "alert_threshold_days", "notify_platform", "notify_email", "updated_at"
                ])
                updated += 1

            if sp_teams:
                cert.groups.add(*sp_teams)  # M2M aditivo (no toca el team dueño)

            for email, threshold in emails:
                _, r_created = CertificateRecipient.objects.get_or_create(
                    certificate=cert, email=email, defaults={"alert_threshold_days": threshold},
                )
                recipients_added += int(r_created)

        self.stdout.write(self.style.SUCCESS(
            f"Certificados: {created} nuevos, {updated} actualizados, {recipients_added} destinatarios; "
            f"{len(team_cache) - 2} grupos de soporte; {skipped} líneas ignoradas."
        ))

    # --- helpers ----------------------------------------------------------
    def _parse_line(self, line: str):
        """Parsea una línea del cert.txt legado -> lista de (dominio, correo,
        umbral, puerto), o None si no se puede salvar.

        Tolera las variantes reales del archivo:
          - URLs en el campo dominio (``https://host:puerto/ruta`` -> host/puerto).
          - Varios correos separados por ``;`` o ``,``.
          - Correos con typo ``user@dom@dom`` (se toma el prefijo válido).
          - Líneas de solo 2 campos ``dominio|correo`` (umbral hereda del grupo).
        """
        if not line:
            return None
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            return None
        domain, url_port = self._clean_domain(parts[0])
        emails = []
        for token in re.split(r"[;,]", parts[1].lower()):
            m = EMAIL_RE.match(token.strip())
            if m and m.group(0) not in emails:
                emails.append(m.group(0))
        if not domain or not emails:
            return None
        threshold = None
        if len(parts) >= 3:
            try:
                threshold = int(parts[2])
            except ValueError:
                threshold = None
        port = url_port or DEFAULT_PORT
        if len(parts) >= 4 and parts[3]:
            try:
                port = int(parts[3])
            except ValueError:
                pass
        return [(domain, email, threshold, port) for email in emails]

    @staticmethod
    def _clean_domain(raw: str):
        """Normaliza el campo dominio: quita esquema/ruta de URLs y extrae el
        puerto embebido (``host:puerto``) si lo hay. -> (dominio, puerto|None)"""
        d = SCHEME_RE.sub("", raw.lower())
        d = d.split("/", 1)[0].split("#", 1)[0].split("?", 1)[0]
        port = None
        if ":" in d:
            d, _, p = d.partition(":")
            if p.isdigit():
                port = int(p)
        return d.strip(), port

    def _get_team(self, name: str, owner) -> Team:
        team, created = Team.objects.get_or_create(
            name=name,
            defaults={"description": "Grupo cargado por data_update_certs_app.", "created_by": owner},
        )
        if created:
            self.stdout.write(f"Grupo creado: {name}")
        return team

    def _ensure_membership(self, user, team):
        # El rol Admin de grupo no existe: el Owner ya gestiona todo por rol
        # global; su membresía en el grupo es de Colaborador.
        Membership.objects.get_or_create(
            user=user, team=team, defaults={"role": MembershipRole.CONTRIBUTOR}
        )
