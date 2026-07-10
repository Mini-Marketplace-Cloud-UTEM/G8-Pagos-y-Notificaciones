# G8 — Pagos con Mercado Pago y Notificaciones

Servicio backend del **Grupo 8** para el proyecto **Mini Marketplace Cloud (UTEM)**. Agrupa dos sub-servicios: **Pagos** y **Notificaciones**, que comparten repositorio, base de datos y despliegue.

## ¿Qué hace este servicio?

El módulo de **Pagos** actúa como pasarela de pagos del ecosistema. En la versión actual, el servicio se integra con **Mercado Pago Checkout Pro en ambiente de prueba**, creando una preferencia de pago y retornando un `checkoutUrl` para continuar el flujo desde el frontend.

El módulo de **Notificaciones** consume eventos generados por otros servicios del marketplace y crea notificaciones simuladas, almacenadas en base de datos. No envía correos reales ni SMS; las notificaciones se consultan desde la API.

Ambos sub-servicios garantizan **idempotencia**:

* En pagos, mediante el header `Idempotency-Key`.
* En notificaciones, mediante el campo `eventId`.

Esto evita que una solicitud duplicada cree pagos o notificaciones repetidas.

---

## Stack tecnológico

* **Backend:** Python + FastAPI
* **Base de datos:** Supabase / PostgreSQL
* **Pagos:** Mercado Pago Checkout Pro, ambiente de prueba
* **Mensajería / integración:** Google Cloud Pub/Sub para eventos de despacho
* **Despliegue:** Render
* **CI:** GitHub Actions
* **Contenedor:** Docker
* **Pruebas:** Postman

---

## Flujo principal de pagos

El flujo actualizado considera que **Grupo 4 - Checkout** orquesta el flujo de compra.

1. G4 Checkout recopila carrito, total, dirección y método de pago.
2. G4 solicita a G5 crear el pedido.
3. G5 crea el pedido con estado `PENDING_PAYMENT` y retorna `orderId`.
4. G4 llama a G8 mediante `POST /v1/payments`, usando ese `orderId`.
5. G8 crea una preferencia de pago en Mercado Pago usando credenciales de prueba.
6. G8 registra el pago en Supabase con estado `PENDING`.
7. G8 retorna a G4 el `checkoutUrl`.
8. G4 redirige al usuario al checkout de Mercado Pago.
9. Mercado Pago notifica el resultado a G8 mediante webhook.
10. G8 actualiza el estado interno del pago a `APPROVED`, `REJECTED` o `PENDING`.
11. G8 publica o registra el evento de resultado correspondiente.
12. G5 consume el resultado del pago y actualiza el estado del pedido.
13. G8 Notificaciones genera la notificación correspondiente.

---

## Contrato de la API

El contrato completo OpenAPI 3.0 está en:

```txt
docs/G8_Contratos.yaml
```

Este contrato define:

* Endpoints REST de pagos.
* Endpoints REST de notificaciones.
* Webhook técnico de Mercado Pago.
* Esquemas de request y response.
* Errores estandarizados.
* Paginación.
* Idempotencia.
* Flujo actualizado de integración.

Para visualizar el contrato de forma interactiva:

```bash
npx @stoplight/prism-cli mock docs/G8_Contratos.yaml
```

Esto levanta un mock local en:

```txt
http://127.0.0.1:4010
```

---

## Endpoints principales

### Pagos

| Método  | Endpoint                            | Descripción                                                                 |
| ------- | ----------------------------------- | --------------------------------------------------------------------------- |
| `POST`  | `/v1/payments`                      | Crea una preferencia de pago en Mercado Pago y registra el pago en Supabase |
| `GET`   | `/v1/payments/{paymentId}`          | Consulta un pago por ID                                                     |
| `GET`   | `/v1/payments?orderId=...`          | Lista pagos asociados a un pedido                                           |
| `PATCH` | `/v1/payments/{paymentId}/confirm`  | Confirma o rechaza manualmente un pago para pruebas internas                |
| `POST`  | `/v1/payments/webhooks/mercadopago` | Recibe notificaciones de Mercado Pago                                       |

### Notificaciones

| Método | Endpoint                       | Descripción                                         |
| ------ | ------------------------------ | --------------------------------------------------- |
| `GET`  | `/v1/notifications?userId=...` | Lista notificaciones de un usuario                  |
| `POST` | `/v1/notifications/test`       | Inyecta un evento manual para probar notificaciones |

### Integración con G6 - Despacho

| Método | Endpoint                        | Descripción                                              |
| ------ | ------------------------------- | -------------------------------------------------------- |
| `POST` | `/v1/integrations/g6/pull-once` | Consume manualmente eventos desde Pub/Sub para pruebas   |
| `POST` | `/v1/integrations/g6/pubsub`    | Endpoint alternativo para recepción tipo push, si se usa |

El endpoint `pull-once` es principalmente técnico y de prueba. No está pensado para ser consumido directamente por otros grupos, sino para demostrar que G8 puede leer eventos desde la suscripción Pub/Sub de G6.

---

## Ejemplo de creación de pago

### Request

```http
POST /v1/payments
Content-Type: application/json
Authorization: Bearer test
Idempotency-Key: 11111111-2222-4333-8444-555555555555
X-Correlation-Id: 99999999-8888-4777-9666-555555555555
```

```json
{
  "orderId": "ORD-20260710-001",
  "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
  "amount": 59990,
  "currency": "CLP",
  "method": "MERCADOPAGO"
}
```

### Response esperado

```json
{
  "paymentId": "PAY-a1b2c3d4-e5f6-7890-1234-56789abcdef0",
  "orderId": "ORD-20260710-001",
  "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
  "amount": 59990,
  "currency": "CLP",
  "method": "MERCADOPAGO",
  "status": "PENDING",
  "provider": "MERCADOPAGO",
  "providerPreferenceId": "123456789-abcd-efgh",
  "providerPaymentId": null,
  "checkoutUrl": "https://www.mercadopago.cl/checkout/v1/redirect?pref_id=123456789-abcd-efgh",
  "providerStatus": "created",
  "idempotencyKey": "11111111-2222-4333-8444-555555555555",
  "correlationId": "99999999-8888-4777-9666-555555555555",
  "failureReason": null,
  "createdAt": "2026-06-15T20:00:00Z",
  "updatedAt": "2026-06-15T20:00:01Z"
}
```

---

## Estados internos de pago

| Estado G8   | Significado                             |
| ----------- | --------------------------------------- |
| `PENDING`   | Pago creado o en espera de confirmación |
| `APPROVED`  | Pago aprobado                           |
| `REJECTED`  | Pago rechazado                          |
| `CANCELLED` | Pago cancelado                          |

Los estados entregados por Mercado Pago se mapean internamente a estos estados para mantener un contrato simple con el resto de los grupos.

---

## Integraciones por grupo

| Grupo                | Responsabilidad / Relación                                                    |
| -------------------- | ----------------------------------------------------------------------------- |
| Grupo 1 — Frontend   | Consume `GET /v1/notifications` y puede redirigir al usuario al `checkoutUrl` |
| Grupo 4 — Checkout   | Orquesta el checkout y llama a `POST /v1/payments`                            |
| Grupo 5 — Pedidos    | Crea pedidos, entrega `orderId` y actualiza estado según resultado del pago   |
| Grupo 6 — Despacho   | Publica eventos de despacho consumidos por G8 Notificaciones                  |
| Grupo 7 — Reportería | Puede consumir información o eventos de pagos para métricas                   |

---

## Eventos relevantes

G8 puede generar o procesar eventos relacionados con pagos y notificaciones.

### Eventos de pago

| Evento             | Descripción    |
| ------------------ | -------------- |
| `PAYMENT_APPROVED` | Pago aprobado  |
| `PAYMENT_REJECTED` | Pago rechazado |
| `PAYMENT_PENDING`  | Pago pendiente |

### Eventos consumidos por notificaciones

| Evento               | Origen                                                       |
| -------------------- | ------------------------------------------------------------ |
| `ORDER_CREATED`      | Grupo 5 - Pedidos                                            |
| `PAYMENT_APPROVED`   | Grupo 8 - Pagos                                              |
| `PAYMENT_REJECTED`   | Grupo 8 - Pagos                                              |
| `PAYMENT_PENDING`    | Grupo 8 - Pagos                                              |
| `SHIPMENT_CREATED`   | Grupo 6 - Despacho                                           |
| `SHIPMENT_DELIVERED` | Grupo 6 - Despacho                                           |
| `SHIPMENT_CANCELLED` | Grupo 6 - Despacho                                           |
| `STOCK_REJECTED`     | Grupo 4 - Inventario / Checkout, según definición de sección |

---

## Estructura del proyecto

```txt
G8-Pagos-y-Notificaciones/
├── app/
│   ├── main.py                         # Punto de entrada FastAPI
│   ├── database/
│   │   └── supabase_client.py          # Cliente Supabase
│   ├── routes/
│   │   ├── payments.py                 # Endpoints de pagos
│   │   ├── notifications.py            # Endpoints de notificaciones
│   │   └── integrations_g6.py          # Integración con G6 vía Pub/Sub
│   ├── schemas/
│   │   ├── payments.py                 # Schemas Pydantic de pagos
│   │   └── notifications.py            # Schemas Pydantic de notificaciones
│   └── services/
│       ├── payment_service.py          # Lógica de pagos e idempotencia
│       ├── mercadopago_service.py      # Integración con Mercado Pago
│       └── notification_service.py     # Lógica de notificaciones
├── docs/
│   └── G8_Contratos.yaml               # Contrato OpenAPI
├── tests/                              # Tests unitarios
├── .github/workflows/                  # GitHub Actions
├── .env.example                        # Variables de entorno de referencia
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Cómo correr el proyecto localmente

```bash
# 1. Clonar el repositorio
git clone https://github.com/Mini-Marketplace-Cloud-UTEM/G8-Pagos-y-Notificaciones.git
cd G8-Pagos-y-Notificaciones

# 2. Crear entorno virtual
python -m venv venv
```

En Linux/Mac:

```bash
source venv/bin/activate
```

En Windows:

```bash
venv\Scripts\activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Configurar variables de entorno:

```bash
cp .env.example .env
```

Completar `.env` con las credenciales correspondientes.

Levantar servidor local:

```bash
uvicorn app.main:app --reload
```

El servicio quedará disponible en:

```txt
http://localhost:8000
```

Swagger:

```txt
http://localhost:8000/docs
```

---

## Variables de entorno

Las credenciales reales nunca deben subirse al repositorio. Deben configurarse en `.env` para desarrollo local y en Render para despliegue.

| Variable                     | Descripción                                     |
| ---------------------------- | ----------------------------------------------- |
| `SUPABASE_URL`               | URL del proyecto Supabase                       |
| `SUPABASE_KEY`               | Key de Supabase usada por el backend            |
| `DATABASE_URL`               | Cadena de conexión directa a PostgreSQL         |
| `MERCADOPAGO_ACCESS_TOKEN`   | Access Token de prueba de Mercado Pago          |
| `FRONTEND_SUCCESS_URL`       | URL de retorno cuando el pago es exitoso        |
| `FRONTEND_FAILURE_URL`       | URL de retorno cuando el pago falla             |
| `FRONTEND_PENDING_URL`       | URL de retorno cuando el pago queda pendiente   |
| `MERCADOPAGO_WEBHOOK_URL`    | URL pública del webhook en Render               |
| `GCP_PROJECT_ID`             | ID del proyecto GCP de G6                       |
| `GCP_PUBSUB_SUBSCRIPTION_ID` | ID de la suscripción Pub/Sub usada por G8       |
| `GCP_SERVICE_ACCOUNT_JSON`   | JSON de credenciales del service account de GCP |
| `G6_DEFAULT_USER_ID`         | Usuario demo usado si G6 no entrega `userId`    |

Ejemplo local:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=xxxx
DATABASE_URL=postgresql://xxxx

MERCADOPAGO_ACCESS_TOKEN=TEST-xxxx
FRONTEND_SUCCESS_URL=https://arq-soft-proyecto-front-end.vercel.app/payment/success
FRONTEND_FAILURE_URL=https://arq-soft-proyecto-front-end.vercel.app/payment/failure
FRONTEND_PENDING_URL=https://arq-soft-proyecto-front-end.vercel.app/payment/pending
MERCADOPAGO_WEBHOOK_URL=https://g8-pagos-y-notificaciones.onrender.com/v1/payments/webhooks/mercadopago
Secciones SUCCESS, FAILURE Y PENDING por integrar.

GCP_PROJECT_ID=proyecto-arqui-g6
GCP_PUBSUB_SUBSCRIPTION_ID=g8-notificaciones-sub
GCP_SERVICE_ACCOUNT_JSON={}
G6_DEFAULT_USER_ID=e9d8c7b6-a543-2109-8765-fedcba098765
```

---

## Despliegue

El servicio se despliega en Render.

URL actual:

```txt
https://g8-pagos-y-notificaciones.onrender.com
```

Swagger en producción:

```txt
https://g8-pagos-y-notificaciones.onrender.com/docs
```

Después de modificar variables de entorno en Render, se debe redeployar el servicio:

```txt
Manual Deploy → Deploy latest commit
```

---

## Pruebas recomendadas en Postman

### 1. Health check

```http
GET /api/health
```

### 2. Crear pago con Mercado Pago

```http
POST /v1/payments
```

Headers:

```txt
Authorization: Bearer test
Idempotency-Key: UUID-unico
X-Correlation-Id: UUID-opcional
Content-Type: application/json
```

Body:

```json
{
  "orderId": "ORD-20260710-001",
  "userId": "e9d8c7b6-a543-2109-8765-fedcba098765",
  "amount": 59990,
  "currency": "CLP",
  "method": "MERCADOPAGO"
}
```

Validar que la respuesta incluya:

```txt
status: PENDING
provider: MERCADOPAGO
providerPreferenceId
checkoutUrl
```

### 3. Probar idempotencia

Enviar el mismo request con el mismo `Idempotency-Key`.

Debe responder `200` y no crear un pago duplicado.

### 4. Consultar pago

```http
GET /v1/payments/{paymentId}
```

### 5. Listar pagos por pedido

```http
GET /v1/payments?orderId=ORD-20260710-001
```

### 6. Consultar notificaciones

```http
GET /v1/notifications?userId=e9d8c7b6-a543-2109-8765-fedcba098765
```

### 7. Consumir eventos de G6

```http
POST /v1/integrations/g6/pull-once?max_messages=5
```

---

## Seguridad

* No subir `.env` al repositorio.
* No exponer `MERCADOPAGO_ACCESS_TOKEN` en frontend.
* No subir el JSON de service account de GCP a GitHub.
* Usar variables de entorno en Render.
* Mantener `Idempotency-Key` para evitar pagos duplicados.
* Mantener `eventId` único para evitar notificaciones duplicadas.

---

## Estado del proyecto

Proyecto en fase final, con:

* Backend FastAPI desplegado en Render.
* Base de datos Supabase conectada.
* Endpoints principales de pagos y notificaciones implementados.
* Integración con G6 mediante Pub/Sub probada.
* Contrato OpenAPI actualizado.
* Integración con Mercado Pago Checkout Pro en ambiente de prueba en implementación.

---

## Grupo 8

* Nicolás Céspedes Poblete
* Diego Vásquez Castillo
* Camilo Arteaga Oyarce
* Walter Olarte Ramirez
