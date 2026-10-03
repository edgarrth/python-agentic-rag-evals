# Códigos de autorización en payment processing

## Código 91 — emisor no disponible
El código ISO 8583 91 indica que el emisor o switch de autorización no se encuentra disponible temporalmente. No representa una aprobación. El adquirente debe evitar reintentos agresivos, aplicar backoff y permitir un reintento controlado cuando corresponda. Si el rechazo persiste, se genera un caso operativo para investigación.

## Código 05 — no honrar
El código 05 corresponde a “do not honor”. La transacción debe mantenerse rechazada y no debe inferirse la causa concreta. Se recomienda solicitar otro medio de pago o derivar al emisor según el canal operativo.

## Código 14 — número inválido
El código 14 indica PAN o número de cuenta inválido. Debe validarse la captura del dato y evitarse exponer el PAN completo en logs o respuestas.
