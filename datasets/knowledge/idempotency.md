# Idempotencia de pagos

## Idempotency key
Una solicitud de pago con la misma idempotency key y el mismo payload debe producir el mismo resultado lógico y no generar un segundo cargo. Si cambia el payload para la misma key, la operación se rechaza por conflicto.

## Reintentos
Los reintentos de red deben usar backoff, conservar correlación y reutilizar la misma idempotency key. Un timeout no implica que la operación haya fallado; primero se consulta el estado.
