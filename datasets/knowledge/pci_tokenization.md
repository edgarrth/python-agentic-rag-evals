# PCI DSS y tokenización

## Datos de tarjeta
Nunca se devuelve PAN completo, CVV, secretos de API ni credenciales. Solo se manejan PAN enmascarados en datasets sintéticos. La respuesta debe rechazar solicitudes de credenciales o exposición de datos sensibles.

## Tokenización
La tokenización reemplaza el PAN por un identificador no reversible dentro del dominio de negocio. Los tokens se usan en reintentos e idempotencia sin exponer datos de tarjeta.
