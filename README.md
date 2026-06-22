# G8 — Pago Simulado y Notificaciones

Servicio backend del **Grupo 8** para el proyecto Mini Marketplace Cloud (UTEM). Agrupa dos sub-servicios: **Pago Simulado** y **Notificaciones**, que comparten repositorio y stack tecnológico.

## ¿Qué hace este servicio?

**Pago Simulado** actúa como pasarela de pagos interna del ecosistema. No procesa dinero real: recibe solicitudes de pago desde el servicio de Pedidos (Grupo 5) y simula un resultado (`APPROVED`, `REJECTED` o `PENDING`), publicando ese resultado como evento para el resto de los servicios.

**Notificaciones** escucha los eventos publicados por otros grupos del ecosistema y genera notificaciones simuladas, almacenadas en base de datos (sin envío real de emails).

Ambos sub-servicios garantizan **idempotencia**: una confirmación de pago duplicada o un evento duplicado no generan procesamiento ni notificaciones repetidas.

## Stack tecnológico

- **Backend:** Python + FastAPI
- **Base de datos:** Supabase (Postgres)
- **Despliegue:** Render
- **CI/CD:** GitHub Actions
- **Contenedor:** Docker

## Contrato de la API

El contrato completo (OpenAPI 3.0) está en [`docs/G8_Contratos.yaml`](./docs/G8_Contratos.yaml). Define los 6 endpoints REST, los eventos publicados y consumidos, y los esquemas de error, paginación y dinero acordados con el resto de los grupos del curso.

Para visualizar el contrato de forma interactiva:

bash
npx @stoplight/prism-cli mock docs/G8_Contratos.yaml

Esto levanta un mock local en `http://127.0.0.1:4010` que responde con los ejemplos definidos en el contrato.


## Estructura del proyecto

G8-Pagos-y-Notificaciones/
├── app/
│   ├── main.py              # Punto de entrada FastAPI
│   ├── models/               # Entidades Payment, Notification
│   ├── routes/                # Endpoints REST
│   ├── schemas/               # Validación con Pydantic
│   └── services/              # Lógica de negocio e idempotencia
├── tests/                      # Tests unitarios
├── docs/
│   └── G8_Contratos.yaml      # Contrato OpenAPI
├── .github/workflows/          # GitHub Actions (CI/CD)
├── .env.example                 # Variables de entorno de referencia
├── Dockerfile
├── requirements.txt
└── README.md


## Cómo correr el proyecto localmente

bash
# 1. Clonar el repositorio
git clone https://github.com/Mini-Marketplace-Cloud-UTEM/G8-Pagos-y-Notificaciones.git
cd G8-Pagos-y-Notificaciones

# 2. Crear entorno virtual e instalar dependencias
python -m venv venv
source venv/bin/activate       # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# completar .env con las credenciales de Supabase (pedirlas al líder del grupo)

# 4. Levantar el servidor de desarrollo
uvicorn app.main:app --reload


El servicio quedará disponible en `http://localhost:8000`. La documentación interactiva (Swagger) se genera automáticamente en `http://localhost:8000/docs`.

## Variables de entorno

Ver [`.env.example`](./.env.example) para la lista completa. Las credenciales reales **nunca se suben al repositorio**; se comparten de forma privada entre el equipo.

| Variable | Descripción |
|---|---|
| `SUPABASE_URL` | URL del proyecto de Supabase |
| `SUPABASE_KEY` | Publishable key de Supabase (segura para compartir) |
| `DATABASE_URL` | Cadena de conexión directa a Postgres |

## Grupo 8

Nicolás Céspedes · Diego Vásquez · Camilo Arteaga · Walter Olarte

## Integraciones

| Grupo | Relación |
|---|---|
| Grupo 5 — Pedidos | Inicia pagos vía `POST /v1/payments` |
| Grupo 6 — Despacho | Publica el evento `ShipmentDelivered` que consumimos |
| Grupo 1 — Frontend | Consume `GET /v1/notifications` |
| Grupo 7 — Reportería | Consume nuestros eventos de pago para reportes |

## Estado del proyecto

🚧 En desarrollo — Fase E2 (Mock y modelo de datos) del proyecto integrado.
