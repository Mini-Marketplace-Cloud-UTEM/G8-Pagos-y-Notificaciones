"""
Punto de entrada del servicio G8 — Pago Simulado y Notificaciones.

Por ahora expone un endpoint de salud (/health) para que Render tenga
algo real que desplegar mientras el equipo construye los endpoints
definidos en docs/G8_Contratos.yaml.
"""

from fastapi import FastAPI

app = FastAPI(
    title="G8 - Payment & Notifications API",
    description="Servicio de Pago Simulado y Notificaciones del Grupo 8.",
    version="1.1.0",
)


@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de salud. Usado por Render para verificar que el servicio está vivo."""
    return {"status": "ok", "service": "g8-pagos-notificaciones"}


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "G8 - Payment & Notifications API",
        "docs": "/docs",
        "health": "/health",
    }

