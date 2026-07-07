"""
Punto de entrada del servicio G8 — Pago Simulado y Notificaciones.

Por ahora expone un endpoint de salud (/health) para que Render tenga
algo real que desplegar mientras el equipo construye los endpoints
definidos en docs/G8_Contratos.yaml.
"""

from fastapi import FastAPI

from app.routes import payments, notifications, integrations_g6

app = FastAPI(
    title="Grupo 8 - Payment & Notifications API",
    version="1.1.0",
    description="Mock API para la fase E2 del Mini-Marketplace Cloud."
)

@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "ok", 
        "message": "¡La API del G8 está corriendo perfectamente!",
        "fase": "E2 - Mock"
    }

app.include_router(payments.router)
app.include_router(notifications.router)
app.include_router(integrations_g6.router)