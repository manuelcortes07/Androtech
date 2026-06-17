"""Paginación clásica numerada, server-side (resto del bloque B5).

Patrón de uso en un handler:

    from pagination import paginar, page_arg
    total = s.scalar(select(func.count(Cliente.id)))          # COUNT scoped
    pag = paginar(total)                                       # page desde la URL
    filas = s.scalars(select(Cliente).order_by(...)
                      .limit(pag.per_page).offset(pag.offset)).all()
    return render_template("...", clientes=filas, pagina=pag, filters_query="")

Y en la plantilla, al final del listado:
    {% include "_paginacion.html" %}

`filters_query` es el query-string de filtros/búsqueda/orden SIN `page`, para que
los enlaces de página conserven el filtro activo.
"""

from __future__ import annotations

import os

from flask import request

PAGE_SIZE_DEFAULT = 25


def page_size() -> int:
    """Tamaño de página configurable por env (PAGE_SIZE, por defecto 25)."""
    try:
        n = int(os.environ.get("PAGE_SIZE", PAGE_SIZE_DEFAULT))
        return n if n >= 1 else PAGE_SIZE_DEFAULT
    except (TypeError, ValueError):
        return PAGE_SIZE_DEFAULT


def page_arg(nombre: str = "page") -> int:
    """Lee el nº de página de la URL de forma robusta (texto/0/negativo → 1)."""
    try:
        p = int(request.args.get(nombre, 1))
        return p if p >= 1 else 1
    except (TypeError, ValueError):
        return 1


class Pagina:
    """Estado de paginación calculado a partir del total y la página pedida.

    Clampa la página al rango válido [1, total_pages] → pedir page=9999 o page=0
    nunca rompe: se queda en la última o primera página.
    """

    def __init__(self, total: int, page: int, per_page: int):
        self.total = max(0, int(total or 0))
        self.per_page = max(1, int(per_page))
        self.total_pages = max(1, (self.total + self.per_page - 1) // self.per_page)
        self.page = max(1, min(int(page or 1), self.total_pages))
        self.offset = (self.page - 1) * self.per_page

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def prev_num(self) -> int:
        return self.page - 1

    @property
    def next_num(self) -> int:
        return self.page + 1

    @property
    def start(self) -> int:
        """Índice (1-based) del primer elemento mostrado; 0 si no hay nada."""
        return 0 if self.total == 0 else self.offset + 1

    @property
    def end(self) -> int:
        """Índice del último elemento mostrado."""
        return min(self.offset + self.per_page, self.total)

    def ventana(self, borde: int = 1, alrededor: int = 2):
        """Números de página a mostrar, con `None` como elipsis."""
        paginas: list = []
        ultimo = 0
        for n in range(1, self.total_pages + 1):
            if n <= borde or n > self.total_pages - borde or abs(n - self.page) <= alrededor:
                if ultimo and n - ultimo > 1:
                    paginas.append(None)
                paginas.append(n)
                ultimo = n
        return paginas


def paginar(total: int, page: int | None = None, per_page: int | None = None) -> Pagina:
    page = page if page is not None else page_arg()
    per_page = per_page or page_size()
    return Pagina(total, page, per_page)
