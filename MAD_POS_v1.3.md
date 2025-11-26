# Manifiesto de Arquitectura y Diseño — POS Linux v1.3

## 1. Análisis de Arquitectura y Entorno
### 1.1. Abstracción Central
POS Linux v1.3 es un monolito modularizado escrito en Python que combina GUI, lógica de negocio, acceso a datos y un microservidor HTTP dentro de un único proceso. La filosofía de diseño prioriza la simplicidad de despliegue en entornos minoristas: el ciclo de vida de la aplicación se orquesta desde `main()`, que inicializa la base de datos SQLite, arranca un hilo dedicado para la API Flask y finalmente lanza el *event loop* de Qt. Cada subsistema se encapsula en clases/tabuladores especializados (por ejemplo, `SalesTab`, `ReportsTab`), lo que proporciona modularidad interna sin abandonar el paradigma monolítico. La comunicación entre módulos se apoya en un estado global ligero (`STATE`) y en el *facade* `DB` que centraliza todas las operaciones de persistencia.

### 1.2. Stack Tecnológico (Frameworks y Entorno)
- **Python 3.10+**: Base del runtime y punto de convergencia de todos los módulos; aprovecha tipado estático opcional y mejoras de rendimiento del intérprete moderno.
- **PySide6 (Qt for Python)**: Proporciona la GUI nativa con widgets ricos; permite implementar flujos de trabajo tipo POS con soporte para eventos, hilos (`QThread`) y componentes de escritorio (QTabWidget, QTableWidget, etc.).
- **Flask + Flask-CORS**: Expone una API REST interna que opera en paralelo al front-end local, habilitando integraciones con kioscos externos, aplicaciones móviles o paneles web.
- **SQLite3** (con WAL): Base de datos embebida que ofrece ACID y bajo mantenimiento; ideal para despliegue *standalone* en cajas registradoras Linux.
- **pandas + openpyxl**: Facilitan la exportación analítica (Excel) y permiten trabajar con datos tabulares y agregados complejos.
- **reportlab**: Genera reportes PDF formateados para gerencia o auditorías.
- **opencv-python + pyzbar** (opcionales): Transforman cualquier webcam en lector de códigos de barras/QR, eliminando hardware dedicado.
- **subprocess + CUPS (`lp`)**: Integración simple con impresoras térmicas compatibles con CUPS.
- **Módulos estándar** (`threading`, `hashlib`, `secrets`, `dataclasses`, etc.): Sostienen concurrencia, seguridad y conveniencias utilitarias.

### 1.3. Modelo de Hilos (Threading)
La arquitectura distingue tres ámbitos de ejecución:
1. **Hilo principal (Qt Event Loop)**: Responsable de la UI, manejo de eventos y sincronización con el usuario. Toda interacción visual ocurre aquí.
2. **Hilo de la API (`APIServer`)**: Instancia un `threading.Thread` marcado como *daemon* que aloja Flask. Atiende solicitudes REST concurrentes mientras la UI permanece receptiva.
3. **Hilos efímeros de captura (`BarcodeThread`)**: `QThread` dedicado a la webcam que emite señales hacia la UI al detectar códigos, integrándose con el modelo de eventos Qt.

SQLite se abre con `check_same_thread=False` y un `threading.Lock` global en `DB`, permitiendo que múltiples hilos compartan conexiones efímeras. El uso combinado de WAL, timeouts y caches reduce la probabilidad de bloqueos; no obstante, esta configuración requiere disciplina en la duración de transacciones para evitar contención.

## 2. Análisis de Base de Datos (SQLite)
### 2.1. Diseño del Esquema (`SCHEMA_SQL`)
- **`app_config`**: Tabla clave/valor para preferencias globales (ej. sucursal activa).
- **`branches`**: Catálogo de sucursales con `tax_rate` y `ticket_header`; `ticket_header` personaliza los recibos.
- **`users`**: Usuarios con roles (`admin`, `retailer`, `user`) y hashes de contraseña; `created_at` audita altas.
- **`categories` / `suppliers`**: Catálogos maestros.
- **`products`**: Catálogo global con atributos comerciales (`sku`, `price`, `cost`, `barcode`, `unit`).
- **`product_stocks`**: Tabla puente (`product_id`, `branch_id`) con stock y reservas por sucursal; `ON DELETE CASCADE` mantiene integridad ante bajas de productos o sucursales.
- **`inventory_logs`**: Historial de movimientos con `change_amount`, `reason` y `user_id`, esencial para trazabilidad y auditoría.
- **`customers`**: CRM básico con límites de crédito y saldo.
- **`sales` / `sale_items`**: Transacciones y partidas; las foráneas aseguran que la venta pertenezca a la sucursal y que los productos existan.
- **`layaways` / `layaway_items`**: Gestionan apartados con fechas de vencimiento, depósitos y estado (`pendiente`, `liquidado`, `cancelado`).

La estructura está normalizada: `products` conserva metadatos globales mientras `product_stocks` separa la dimensión de sucursal. Las tablas de detalle (`sale_items`, `layaway_items`) impiden duplicidad de datos y mantienen consistencia referencial.

### 2.2. Estrategia de Migración
`DB.init()` ejecuta `SCHEMA_SQL` completo al inicio, creando tablas idempotentes con `CREATE TABLE IF NOT EXISTS`. El bloque posterior garantiza usuarios iniciales con hashes y configura la sucursal predeterminada en `app_config`. Aunque no existe una función explícita de migraciones incrementales (ej. `ensure_column`), la naturaleza idempotente de los scripts permite despliegues repetibles. Actualizaciones estructurales mayores requerirían scripts complementarios.

### 2.3. Optimización de Rendimiento
- **PRAGMA `journal_mode=WAL`**: Habilita *Write-Ahead Logging*, permitiendo lecturas concurrentes durante escrituras, crucial cuando la UI y la API consultan simultáneamente.
- **PRAGMA `foreign_keys=ON`**: Garantiza integridad sin lógica adicional en la aplicación.
- **LRU Cache (`lru_cache`)** en consultas de producto y stock: Reduce IO para accesos frecuentes (ej. escaneo rápido de SKUs). La invalidación manual tras mutaciones asegura consistencia.
- **Bloqueo global (`_lock`)**: Coordina escrituras para minimizar conflictos, complementando el WAL.

En conjunto, la configuración soporta operaciones simultáneas (cajero facturando mientras un gerente ejecuta reportes) sin sacrificar integridad.

## 3. Análisis de Módulos (Lógica de Negocio)
### 3.1. Módulo de Autenticación y Roles
- **Seguridad**: `make_hash` usa PBKDF2-HMAC-SHA256 con 310 000 iteraciones y sales aleatorias (`secrets.token_hex`). `check_password` valida mediante comparación constante (`secrets.compare_digest`).
- **Permisos**: Tras el login, `STATE` almacena `user_id`, `username`, `role` y sucursal. `POSWindow` remueve pestañas del `QTabWidget` según el rol: *admin* ve todo; *retailer* pierde acceso a Productos y Configuración; *user* básico queda limitado a Ventas y Apartados.

### 3.2. Módulo Multi-Sucursal (Core)
`products` define el catálogo universal mientras `product_stocks` mantiene inventarios por sucursal. `STATE.branch_id` determina el contexto activo. `SalesTab._current_tax_rate()` consulta `branches.tax_rate` para aplicar impuestos específicos por sucursal. `DB.create_sale()` descuenta inventario mediante `DB.add_stock` usando `STATE.branch_id`, lo que garantiza que cada venta afecte la sucursal correcta.

### 3.3. Módulo de Ventas (`SalesTab`)
Flujo típico: el cajero introduce/escanea SKU → `add_item()` valida stock disponible (`stock - reserved`) y arma el carrito → `refresh_cart()` actualiza tablas y etiquetas con totales → `checkout()` confirma, crea venta y dispara impresión. `_totals()` calcula subtotal por línea, descuenta promociones (`self.discount`) y determina impuestos basados en la sucursal; el total final incorpora el IVA.

### 3.4. Módulo de Apartados (`LayawaysTab`)
- **`DB.reserve_stock`**: Incrementa `reserved` sin alterar `stock`, marcando unidades apartadas.
- **`DB.release_stock`**: Disminuye `reserved` al cancelar apartados, devolviendo disponibilidad.
- **`DB.consume_reserved_stock`**: Convierte reservas en ventas efectivas durante la liquidación, restando de `stock` y `reserved` en bloque.
- **`DB.add_stock`**: Ajusta inventario físico (entradas/salidas) con bitácora en `inventory_logs`.

La separación entre stock real y reservado evita sobreventas: el flujo de apartados opera sobre `reserved` hasta que se concreta o cancela la transacción.

### 3.5. Módulo de Reportes (`ReportsTab`)
Consulta agregada:
```sql
SELECT p.name,
       SUM(si.qty)                          AS q,
       SUM(si.subtotal)                     AS t,
       SUM(si.qty * (p.price - p.cost))     AS profit
FROM sale_items si
JOIN sales s ON s.id = si.sale_id
JOIN products p ON p.id = si.product_id
WHERE s.ts BETWEEN ? AND ?
  [AND s.branch_id = ?]
GROUP BY p.id, p.name
ORDER BY q DESC;
```
La rentabilidad calcula margen unitario (`p.price - p.cost`) multiplicado por cantidades vendidas. Exportaciones: CSV nativo (`csv.writer`), Excel vía `pandas`/`openpyxl`, y PDF mediante `reportlab` con tablas estilizadas. El módulo también genera series diarias para análisis temporal.

## 4. Diseño de Interfaz y Experiencia (UI/UX)
### 4.1. Wireframe Funcional
`POSWindow` monta un `QTabWidget` central con pestañas temáticas (Ventas, Productos, Inventario, Clientes, Historial, Apartados, Reportes, Configuración). Un `QMenuBar` agrega accesos rápidos (Respaldo DB) y la `QStatusBar` comunica contexto y notificaciones.

### 4.2. Ergonomía del Cajero
`SalesTab` fija el foco en el campo SKU (`returnPressed` dispara `add_item`), soporta escaneo con webcam (`BarcodeThread`) y muestra totales en tiempo real. Los botones de acción (Vaciar, Apartar, Cobrar) se agrupan para minimizar desplazamientos. Los controles de cantidad (`QSpinBox`) y combos de pago/cliente reducen errores manuales.

### 4.3. Ergonomía del Administrador
`ProductsTab` y `InventoryTab` combinan formularios agrupados (`QGroupBox`, `QFormLayout`) con tablas filtrables (`OptimizedTable`). `ReportsTab` provee rangos de fecha, filtros por sucursal y métricas clave visibles de inmediato. Los botones de exportación (PDF, Excel, CSV) están alineados para accesibilidad rápida.

## 5. Arquitectura de API e Integraciones
### 5.1. Diseño de la API (Flask)
- `GET /api/products`: Filtra por texto/categoría, retorna productos disponibles (solo stock positivo) enriquecidos con inventario de la sucursal activa.
- `GET /api/branches`: Devuelve listado completo de sucursales (id, name) para sincronización externa.
- `GET /api/layaways`: Consulta apartados recientes (últimos 100) por sucursal.
- `GET /api/customers`: Busca clientes por nombre/teléfono/email.

Las respuestas son JSON planos, pensados para consumo por terminales ligeras o integraciones móviles.

### 5.2. Modelo de Seguridad (API Key)
La versión actual expone la API sin autenticación. Una estrategia propuesta consiste en incorporar un validador `_require_api_key()` que lea `POS_API_KEY` de variables de entorno y verifique encabezados HTTP (`X-API-Key`), limitando el acceso a clientes autorizados.

### 5.3. Drivers de Hardware (Compatibilidad)
- **Impresión**: El uso de `subprocess.Popen(["lp", path])` delega la impresión al sistema CUPS, ofreciendo compatibilidad con una amplia gama de impresoras térmicas soportadas en Linux.
- **Escaneo**: `opencv-python` captura frames y `pyzbar` decodifica códigos de barras/QR, transformando webcams genéricas en lectores omnidireccionales sin SDK propietario.

## 6. Plan de Debugging y Robustez (QA)
### 6.1. Manejo de Errores
El código encapsula operaciones críticas en `try/except` con mensajes de usuario (`QMessageBox`) y bitácoras (`log.error`). Ejemplos: creación de ventas/apartados, exportaciones (CSV/PDF/Excel), respaldo de base de datos y llamadas API.

### 6.2. Puntos Críticos de Falla
1. **Condiciones de carrera en inventario**: Dos cajeros podrían vender/apartar el último artículo simultáneamente. WAL y los bloqueos reducen el riesgo, pero no eliminan colisiones si transacciones son largas.
2. **Disponibilidad de hardware**: Fallas en webcam o impresora no son fatales gracias a manejo de errores, pero impactan operatividad; se registran en logs.
3. **Integridad de datos en cancelaciones**: Si un producto se elimina mientras existen apartados o ventas asociadas, las FKs con `ON DELETE CASCADE` podrían borrar historiales críticos; requiere políticas de negocio (p. ej., desactivar productos en lugar de borrarlos).

### 6.3. Propuesta de Refactorización (Nivel 2.0)
```
pos/
├── __init__.py
├── main.py              # Punto de entrada (inicia Qt, hilos, estado)
├── db/
│   ├── __init__.py
│   ├── schema.py        # SCHEMA_SQL y migraciones
│   └── manager.py       # Clase DB, utilidades de caché
├── api/
│   ├── __init__.py
│   └── server.py        # APIServer y endpoints
├── ui/
│   ├── __init__.py
│   ├── state.py         # AppState y contexto
│   ├── main_window.py   # POSWindow
│   └── tabs/
│       ├── __init__.py
│       ├── sales.py
│       ├── products.py
│       ├── inventory.py
│       ├── customers.py
│       ├── history.py
│       ├── layaways.py
│       ├── reports.py
│       └── settings.py
├── utils/
│   ├── security.py      # make_hash, check_password
│   ├── printing.py      # Ticket printing helpers
│   └── camera.py        # BarcodeThread, detección
└── resources/
    └── config.py        # Constantes (paths, tasas por defecto)
```
Esta segmentación promueve reutilización, pruebas unitarias y escalabilidad futura (p. ej., sustituir Flask por FastAPI, o la GUI por cliente web).

## Conclusión
POS v1.3 ofrece una base monolítica bien integrada con seguridad sólida y módulos completos, apta para pequeñas cadenas, pero requiere modularización para escalar y endurecer su API.
