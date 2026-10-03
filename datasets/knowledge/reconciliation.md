# Conciliación y settlement

## Conciliación adquirente-emisor
La conciliación compara autorizaciones, capturas y liquidaciones. Una diferencia se considera mismatch cuando el monto, moneda o identificador de referencia no coincide entre el registro del adquirente y el archivo de settlement.

## Trazabilidad
Cada evento debe conservar transaction_id, merchant_id, acquirer reference y timestamps. Los identificadores sensibles se enmascaran. Un mismatch no se corrige automáticamente en esta PoC; se crea un borrador de caso.

## Multi-hop
Para investigar TX-1008 se relacionan transacción, merchant, adquirente, lote de settlement y regla de conciliación. La conclusión requiere reunir más de una evidencia.
