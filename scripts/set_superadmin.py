"""Designa (o revoca) el SUPERADMIN DE PLATAFORMA (hallazgo de seguridad H1).

El superadmin es el dueño del SaaS: el ÚNICO que puede crear/editar/borrar los
ROLES GLOBALES (que afectan a todos los talleres). Por seguridad, NO se puede
activar desde la app web — sólo con esta CLI, que controla el operador del SaaS.

Uso:
    python scripts/set_superadmin.py <taller_id> <usuario>          # conceder
    python scripts/set_superadmin.py <taller_id> <usuario> --off    # revocar

Respeta DATABASE_URL / DATABASE_PATH (usa el mismo motor que la app).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import get_engine  # noqa: E402
from migrations import asegurar_es_superadmin  # noqa: E402


def main() -> None:
    off = "--off" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)

    taller_id, usuario = args
    valor = 0 if off else 1

    asegurar_es_superadmin()  # garantiza la columna
    with get_engine().begin() as conn:
        res = conn.execute(
            text("UPDATE usuarios SET es_superadmin = :v "
                 "WHERE taller_id = :t AND usuario = :u"),
            {"v": valor, "t": int(taller_id), "u": usuario},
        )
        if res.rowcount == 0:
            print(f"[ERROR] No existe el usuario '{usuario}' en el taller {taller_id}.")
            sys.exit(2)

    accion = "Revocado" if off else "Concedido"
    print(f"[OK] {accion} superadmin de plataforma a '{usuario}' (taller {taller_id}).")
    print("     (debe volver a iniciar sesion para que surta efecto en su sesion)")


if __name__ == "__main__":
    main()
