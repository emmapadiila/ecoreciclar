# Diagrama entidad–relación

Las 18 tablas comparten una sola base PostgreSQL. La relación IA → solicitud es unidireccional. Las relaciones compuestas de asignación y recolección también se detallan en el [diccionario](modelo-datos.md).

```mermaid
erDiagram
    colectivos {
        bigint id PK
        text nombre
        text tipo_flujo UK
        boolean activo
    }
    configuraciones {
        bigint id PK
        text clave UK
        jsonb valor
        text descripcion
        timestamptz actualizado_en
    }
    contenidos_ambientales {
        bigint id PK
        text titulo
        text categoria
        text contenido
        text imagen_url
        boolean publicado
        timestamptz fecha
    }
    materiales {
        bigint id PK
        text nombre UK
        text categoria
        boolean aceptado
        boolean activo
    }
    usuarios {
        bigint id PK
        text nombre
        text telefono
        text whatsapp_id UK
        text correo UK
        text password_hash
        text rol
        text tipo_generador
        text direccion
        text sector
        boolean piloto_habilitado
        boolean activo
        timestamptz fecha_registro
    }
    conversaciones {
        bigint id PK
        bigint usuario_id FK
        text estado_actual
        jsonb datos_temporales
        timestamptz fecha_inicio
        timestamptz fecha_actualizacion
    }
    coordinadores_colectivo {
        bigint id PK
        bigint usuario_id FK
        bigint colectivo_id FK
        boolean activo
    }
    recolectores {
        bigint id PK
        bigint usuario_id FK
        bigint colectivo_id FK
        text nombre
        text telefono
        boolean activo
        timestamptz fecha_registro
    }
    reglas_puntos {
        bigint id PK
        bigint colectivo_id FK
        numeric puntos_por_kg
        timestamptz fecha_inicio
        timestamptz fecha_fin
        boolean aprobada
        bigint aprobada_por FK
    }
    solicitudes {
        bigint id PK
        text codigo UK
        bigint usuario_id FK
        bigint colectivo_id FK
        text tipo_generador
        text descripcion
        text direccion
        text horario_preferido
        text origen
        text estado
        timestamptz fecha_creacion
    }
    asignaciones {
        bigint id PK
        bigint solicitud_id FK
        bigint colectivo_id FK
        bigint coordinador_id FK
        bigint recolector_id FK
        timestamptz programada_en
        text observaciones
        timestamptz fecha_asignacion
    }
    clasificaciones_ia {
        bigint id PK
        bigint usuario_id FK
        bigint solicitud_id FK
        text imagen_referencia
        text objeto_detectado
        text categoria_sugerida
        boolean aprovechable
        boolean requiere_revision
        text categoria_confirmada
        text modelo_ia
        timestamptz fecha
    }
    historial_estados {
        bigint id PK
        bigint solicitud_id FK
        bigint usuario_actor_id FK
        text estado_anterior
        text estado_nuevo
        text observacion
        timestamptz fecha
    }
    mensajes_whatsapp {
        bigint id PK
        bigint conversacion_id FK
        text meta_message_id UK
        text direccion
        text tipo
        text contenido
        text estado_envio
        text estado_procesamiento
        timestamptz fecha
    }
    notificaciones {
        bigint id PK
        bigint usuario_id FK
        bigint solicitud_id FK
        text canal
        text tipo
        text mensaje
        text estado
        bigint intentos
        timestamptz fecha_creacion
    }
    solicitud_materiales {
        bigint id PK
        bigint solicitud_id FK
        bigint material_id FK
        text descripcion
        numeric estimado_kg
        jsonb sugerencia_ia
        boolean confirmado
    }
    recolecciones {
        bigint id PK
        bigint solicitud_id FK
        bigint asignacion_id FK
        numeric peso_real_kg
        timestamptz fecha_recoleccion
        bigint registrado_por FK
        text observaciones
    }
    movimientos_puntos {
        bigint id PK
        bigint usuario_id FK
        bigint recoleccion_id FK
        bigint regla_id FK
        numeric puntos
        text concepto
        timestamptz fecha
    }
    usuarios ||--o{ conversaciones : "usuario_id"
    colectivos ||--o{ coordinadores_colectivo : "colectivo_id"
    usuarios ||--o{ coordinadores_colectivo : "usuario_id"
    colectivos ||--o{ recolectores : "colectivo_id"
    usuarios |o--o{ recolectores : "usuario_id"
    usuarios |o--o{ reglas_puntos : "aprobada_por"
    colectivos ||--o{ reglas_puntos : "colectivo_id"
    colectivos ||--o{ solicitudes : "colectivo_id"
    usuarios ||--o{ solicitudes : "usuario_id"
    usuarios ||--o{ asignaciones : "coordinador_id"
    recolectores ||--o{ asignaciones : "recolector_id"
    solicitudes ||--o{ asignaciones : "solicitud_id"
    solicitudes |o--o{ clasificaciones_ia : "solicitud_id"
    usuarios ||--o{ clasificaciones_ia : "usuario_id"
    solicitudes ||--o{ historial_estados : "solicitud_id"
    usuarios ||--o{ historial_estados : "usuario_actor_id"
    conversaciones ||--o{ mensajes_whatsapp : "conversacion_id"
    solicitudes |o--o{ notificaciones : "solicitud_id"
    usuarios ||--o{ notificaciones : "usuario_id"
    materiales ||--o{ solicitud_materiales : "material_id"
    solicitudes ||--o{ solicitud_materiales : "solicitud_id"
    asignaciones ||--o{ recolecciones : "asignacion_id"
    usuarios ||--o{ recolecciones : "registrado_por"
    solicitudes ||--o{ recolecciones : "solicitud_id"
    recolecciones ||--o{ movimientos_puntos : "recoleccion_id"
    reglas_puntos ||--o{ movimientos_puntos : "regla_id"
    usuarios ||--o{ movimientos_puntos : "usuario_id"
```

Las cardinalidades de hijos están simplificadas: `recolecciones.solicitud_id`, `asignaciones.solicitud_id`, `movimientos_puntos.recoleccion_id` y `conversaciones.usuario_id` son UNIQUE (0..1). No existen borrados en cascada.
