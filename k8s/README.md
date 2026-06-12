# Aprovisionamiento en Kubernetes — CertManager

Manifiestos para desplegar el aplicativo en K8s. La **base de datos MySQL es
externa** (la provee Claro) y el **TLS** se termina en el Ingress con el
certificado **`*.claro.com.do`**.

> Equipo de plataforma: revisar `ingressClassName`, el registro de imágenes y la
> gestión de secretos (Vault/SealedSecrets) según el estándar de Claro.

## 0. Construir y publicar la imagen

```bash
docker build -t REGISTRO-CLARO/certmanager:1.0.0 .
docker push REGISTRO-CLARO/certmanager:1.0.0
# luego reemplazar REGISTRO-CLARO/certmanager:TAG en k8s/deploy.yaml
```

## 1. Namespace + configuración

```bash
kubectl apply -f k8s/deploy.yaml        # crea el namespace 'certmanager' + Job + Deployments + Service
kubectl apply -f k8s/configmap.yaml     # editar ALLOWED_HOSTS, DB_HOST, etc. antes
```

## 2. Secretos del aplicativo (NO versionar)

```bash
kubectl -n certmanager create secret generic certmanager-secrets \
  --from-literal=DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key as g;print(g())')" \
  --from-literal=DB_PASSWORD='<clave MySQL de Claro>' \
  --from-literal=CF_OWNER_PASSWORD='<clave del Owner>'
```
(o copiar `secret.example.yaml` a `app-secret.yaml` —gitignored— y completarlo.)

## 3. Certificado TLS *.claro.com.do  ← DÓNDE PONER EL CERTIFICADO

El wildcard se carga como un **Secret tipo TLS** llamado `certmanager-tls`, que el
Ingress referencia. Con los dos archivos del certificado (cert+cadena y clave):

```bash
kubectl -n certmanager create secret tls certmanager-tls \
  --cert=claro-wildcard.crt \   # certificado + cadena intermedia (fullchain PEM)
  --key=claro-wildcard.key      # clave privada (PEM)
```

> Si Claro gestiona los certificados con cert-manager/SealedSecrets, usar ese flujo
> en vez del `create secret tls` manual; el nombre del Secret debe seguir siendo
> `certmanager-tls` (o ajustarlo en `ingress.yaml`).

## 4. Exponer (Ingress 443)

```bash
kubectl apply -f k8s/ingress.yaml
```

## 5. Verificar

```bash
kubectl -n certmanager get pods,svc,ingress
kubectl -n certmanager logs job/certmanager-migrate
curl -fsS https://certmanager.claro.com.do/health/    # {"status":"ok","database":true}
```

## 6. Owner + configuración (bootstrap)

```bash
POD=$(kubectl -n certmanager get pod -l component=web -o jsonpath='{.items[0].metadata.name}')
kubectl -n certmanager exec "$POD" -- python manage.py data_update_certs_app --skip-certs
# (la carga de certificados desde cert.txt es OPCIONAL y para más adelante; ver
#  CLARO_NECESIDAD/04_aprovisionamiento_y_certificados.md)
```

## Notas
- **Scheduler = 1 réplica** (el lock es por-proceso; 2 réplicas duplicarían los jobs).
- El `Job` de migración corre una vez; re-aplícalo (borrándolo) en cada upgrade que traiga migraciones.
- Logs: la app emite JSON a **stdout**; recógelos con el stack de logging del clúster (Promtail/Fluentd → Loki).
