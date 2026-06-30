"""
app/db.py

Cliente único de Supabase para toda la aplicación.

Lee las credenciales desde variables de entorno (cargadas desde .env en
local; en Render se configuran en el panel del servicio):
  - SUPABASE_URL
  - SUPABASE_KEY

Se cachea con lru_cache para no crear un cliente nuevo en cada request.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

# Carga .env si existe (en local). En la nube las vars vienen del entorno.
load_dotenv()


@lru_cache
def get_supabase() -> Client:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_KEY") or "").strip()

    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL y/o SUPABASE_KEY. "
            "Define un archivo .env en local o configura las variables en Render."
        )

    return create_client(url, key)
