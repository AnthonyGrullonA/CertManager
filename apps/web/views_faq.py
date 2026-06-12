"""Ayuda / Preguntas frecuentes (FAQ) de toda la aplicación.

Contenido curado y estático (no requiere modelo): se agrupa por área y se rinde
con acordeones nativos ``<details>`` + un filtro de búsqueda en cliente.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

# (icono Forge, título, [(pregunta, respuesta), ...])
FAQ_SECTIONS = [
    ("layout-dashboard", _("Panel y navegación"), [
        (_("¿Qué muestra el Dashboard?"),
         _("Un resumen del ámbito activo: los KPIs (total, vigentes, por vencer, críticos, "
           "vencidos…), la distribución por estado (gráfico de dona) y las ventanas de "
           "vencimiento. Al hacer clic en un KPI, un segmento de la dona o una barra te lleva "
           "al listado de certificados ya filtrado.")),
        (_("¿Cómo cambio entre grupos (ámbito)?"),
         _("Con el selector «Todos los grupos» de la barra superior: filtra el dashboard, los "
           "certificados y las alertas al grupo elegido. «Todos los grupos» (sólo Owner) "
           "muestra la organización completa; el resto ve sus grupos. La selección se "
           "recuerda al navegar entre páginas.")),
    ]),
    ("shield-check", _("Certificados"), [
        (_("¿Cómo agrego un certificado a monitorear?"),
         _("Entra a Certificados → «Nuevo certificado» e indica el dominio (host) y el "
           "puerto (443 por defecto), el grupo dueño y, opcionalmente, grupos adicionales, "
           "destinatarios y una plantilla de correo. Con «Guardar y probar» se hace un "
           "chequeo en el momento.")),
        (_("¿Por qué no me deja agregar un dominio?"),
         _("Si ese dominio:puerto ya existe (en tu grupo o en otro) se bloquea para evitar "
           "duplicidad y se te indica en qué grupos está. Si el certificado existente está "
           "pausado, el mismo aviso te ofrece reactivarlo en vez de crear un duplicado.")),
        (_("¿Qué significan los estados y colores?"),
         _("Vigente (verde), Por vencer (ámbar), Crítico (rojo), Vencido (rojo), "
           "Error (naranja, no se pudo evaluar) y Sin chequear (gris, aún no evaluado).")),
        (_("¿Cada cuánto se revisan?"),
         _("Automáticamente, según el intervalo de monitoreo (lo ves en el pie del menú y "
           "en Configuración → Monitoreo). No necesitas dispararlo a mano.")),
        (_("¿Cómo lo pruebo ahora mismo?"),
         _("En el detalle del certificado, «Probar ahora» ejecuta un chequeo real y te "
           "muestra el resultado paso a paso.")),
        (_("¿Cómo pauso o reanudo el monitoreo?"),
         _("En el detalle, «Pausar monitoreo» (o «Reanudar»). Un certificado pausado no se "
           "chequea hasta reactivarlo y se marca con la etiqueta «Monitoreo pausado».")),
        (_("¿Cómo exporto los certificados a CSV?"),
         _("En Certificados, el botón «Exportar» descarga un archivo CSV con el listado tal "
           "como lo tienes filtrado en ese momento (los mismos filtros de búsqueda, estado, "
           "grupo y ventana de días se aplican a la exportación). El CSV incluye dominio, "
           "puerto, grupos, estado, días restantes, vencimiento, emisor y último chequeo.")),
    ]),
    ("layers", _("Grupos y roles"), [
        (_("¿Qué es un grupo?"),
         _("Una agrupación de certificados con sus miembros y valores por defecto "
           "(umbrales de alerta, canales y destinatarios) que los certificados heredan.")),
        (_("¿Un certificado puede pertenecer a varios grupos?"),
         _("Sí. Tiene un grupo dueño y, además, grupos adicionales de gestión/visualización. "
           "Los agregas con el campo «Grupos adicionales» del certificado o con la acción "
           "masiva «Agregar a grupo».")),
        (_("¿Qué puede hacer cada rol?"),
         _("Visualizador: ve certificados y genera/recibe reportes. "
           "Colaborador: además crea, edita y borra certificados en sus grupos. "
           "Admin de grupo: además gestiona plantillas, miembros y alertas compartidas. "
           "Owner: acceso total a toda la organización.")),
        (_("¿Quién puede gestionar un certificado multi-grupo?"),
         _("Cualquier usuario que sea Colaborador o Admin en alguno de los grupos del "
           "certificado (dueño o adicional).")),
    ]),
    ("users", _("Usuarios y acceso"), [
        (_("¿Cómo agrego o invito a una persona?"),
         _("En Usuarios (sólo Owner) → «Nuevo usuario»: indicas el correo, los grupos a los "
           "que pertenece y su rol en esos grupos (Visualizador, Colaborador o Admin). Le das "
           "una contraseña inicial o marcas «Autenticar por LDAP».")),
        (_("¿Cómo desactivo a una persona?"),
         _("En Usuarios, edita a la persona y desmarca «Cuenta activa» (o usa la acción de "
           "activar/desactivar). Una cuenta inactiva no puede iniciar sesión. No puedes "
           "desactivarte a ti mismo.")),
        (_("¿Puedo usar el directorio corporativo (LDAP)?"),
         _("Sí. El Owner configura la conexión en Configuración → Seguridad (sub-panel LDAP). "
           "Al crear una persona se marca «Autenticar por LDAP»: queda sin contraseña local y "
           "el inicio de sesión valida su correo contra el directorio. El mismo formulario de "
           "login sirve para cuentas locales y LDAP, sin botón aparte.")),
    ]),
    ("file-text", _("Reportes"), [
        (_("¿Cómo programo un reporte?"),
         _("En Reportes → «Nuevo» eliges la plantilla de reporte, la frecuencia, los "
           "destinatarios, los formatos (PDF, Excel o CSV) y, si quieres, una plantilla de "
           "correo para el cuerpo del email.")),
        (_("¿Cuándo se envían?"),
         _("Según la frecuencia: diaria, semanal, mensual, cada N días desde una fecha o el "
           "día 1 de cada mes. Si la fecha cae en fin de semana, el envío se difiere al lunes.")),
        (_("¿Puedo probarlo o previsualizarlo?"),
         _("Sí. «Enviar prueba» lo manda a un correo y al hacer clic en el reporte ves una "
           "vista previa de lo que saca.")),
    ]),
    ("bell", _("Alertas"), [
        (_("¿Cuándo se generan alertas?"),
         _("Cuando un certificado entra en riesgo (por vencer, crítico, vencido o con error). "
           "Se notifica por los canales activos del certificado/grupo.")),
        (_("¿Cómo gestiono las alertas?"),
         _("En Alertas puedes ver el detalle, marcarlas como leídas, resolverlas, posponerlas "
           "o limpiar el panel. Resolver y posponer (acciones del recurso compartido) son de "
           "Admin del grupo u Owner.")),
    ]),
    ("mail", _("Plantillas de correo"), [
        (_("¿Para qué sirven?"),
         _("Definen el cuerpo de los correos (de certificados y de reportes) con un editor "
           "por bloques: encabezado, texto, campos de dato, botón, separador y pie.")),
        (_("¿Quién puede crearlas o editarlas?"),
         _("Crear: cualquier usuario autenticado. Usar/adjuntar: todos. Editar o borrar: el "
           "Owner, un Admin de grupo o quien la creó.")),
        (_("¿Qué son los campos obligatorios (🔒)?"),
         _("Datos que siempre deben ir en el correo (por ejemplo dominio, estado, días "
           "restantes y vencimiento). Aparecen bloqueados en el lienzo y no se pueden quitar.")),
        (_("¿Cómo veo cómo queda una plantilla?"),
         _("Haz clic en el nombre de la plantilla: se abre una vista previa renderizada con "
           "datos de ejemplo, y desde ahí puedes «Corregir» (editarla).")),
        (_("¿Qué pasa si un certificado o reporte no tiene plantilla?"),
         _("Se usa la plantilla predeterminada de su tipo; si no hay ninguna, se envía en "
           "texto plano. Nunca se deja de enviar el correo.")),
    ]),
    ("settings", _("Notificaciones y configuración"), [
        (_("¿Por qué no veo la opción «Webhook»?"),
         _("El canal Webhook (Microsoft Teams / Slack) sólo aparece al crear o editar un "
           "certificado si hay webhooks configurados en Configuración → Integraciones.")),
        (_("¿Cómo configuro el webhook de Teams o Slack?"),
         _("Primero genera la URL del «webhook entrante» en tu canal: en Microsoft Teams, "
           "con un conector/Incoming Webhook del canal; en Slack, con una Incoming Webhook "
           "desde la app de Slack. Luego, en CertManager → Configuración → Integraciones "
           "(sólo Owner), pega esa URL en el campo de Teams o de Slack y guarda. Por seguridad "
           "las URLs se guardan write-only (no se muestran en claro después). Con un webhook "
           "configurado, el canal «Webhook» aparece al crear/editar certificados y las alertas "
           "se publican en ese canal.")),
        (_("¿Cómo configuro el envío de correo (SMTP)?"),
         _("En Configuración → SMTP (sólo Owner). Si no hay SMTP, los correos de prueba "
           "degradan a la consola del servidor.")),
    ]),
    ("lock", _("Seguridad y cuenta"), [
        (_("¿Cómo activo la verificación en dos pasos (2FA)?"),
         _("En Perfil → «Autenticación en dos pasos»: escanea el código QR con Google "
           "Authenticator o Microsoft Authenticator y confirma el código.")),
        (_("¿Cómo cambio mi contraseña o el idioma?"),
         _("En Perfil puedes actualizar tus datos, tu contraseña y el idioma de la interfaz.")),
    ]),
    ("key", _("API y tokens"), [
        (_("¿La aplicación tiene API?"),
         _("Sí. En «API & tokens» (Owner) puedes crear claves de API de acceso total o de "
           "solo lectura y consultar la documentación de los endpoints.")),
        (_("¿Qué puede hacer una clave de solo lectura?"),
         _("Sólo operaciones de lectura (GET). Las claves de acceso total permiten también "
           "crear y modificar, siempre dentro del ámbito y rol del usuario.")),
    ]),
]


class FaqView(LoginRequiredMixin, TemplateView):
    template_name = "ayuda/faq.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sections"] = FAQ_SECTIONS
        return ctx
