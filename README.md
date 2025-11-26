# POS Ultra Pro Max (Skeleton)

Este repositorio contiene un esqueleto modular para el sistema POS inspirado en
Novedades Lupita. El objetivo es avanzar módulo por módulo (ventas, inventario,
apartados, multi-caja, etc.) siguiendo el megaprompt proporcionado.

## Estructura actual
- `pos_core.py`: capa de datos SQLite y utilidades básicas.
- `pos_app.py`: contenedor PySide6 con tabs y wizard de bienvenida simplificado.
- `initialize_pos_env.py`: crea carpetas, base de datos y archivo de configuración.
- `run_pos.py`: punto de entrada que inicializa y arranca la app.
- `server_main.py` + `server/api/`: esqueletos de FastAPI para modo servidor.
- `utils/theme_manager.py`: gestor mínimo de temas.

Cada módulo podrá ampliarse en futuras iteraciones según las secciones del
megaprompt.
