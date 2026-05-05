# Sorteo verificable para socios

Sorteo con compromiso criptográfico (commit-reveal). Cualquier socio puede verificar
de forma independiente que el sorteo no ha sido manipulado.

## Requisitos
- Python 3.7 o superior. Sin dependencias externas.

## Formato del CSV de participantes

```
Customer ID,Customer Email
cus_AbCdEfGhIjKlMn,socio@example.com
...
```

## Flujo del sorteo (organizador)

### 1. Antes de cerrar inscripciones — generar compromiso

```
python sorteo.py commit
```

Esto crea dos archivos:
- `semilla_PRIVADA_<fecha>.txt` — guárdalo en secreto, no lo compartas todavía.
- `compromiso_PUBLICO_<fecha>.txt` — contiene el hash SHA256 de la semilla.

**Publica ese hash a los socios antes del cierre de inscripciones** (por email,
en la web, etc.). Es tu compromiso: te ata a una semilla concreta sin revelarla aún.

### 2. Cerrar inscripciones y fijar la lista

Exporta el CSV definitivo de participantes desde Stripe. A partir de aquí no debe
modificarse.

### 3. Realizar el sorteo

```
python sorteo.py sortear participantes.csv <ruta_semilla> <n_ganadores> <n_suplentes>
```

Ejemplo: 3 ganadores y 5 suplentes:

```
python sorteo.py sortear participantes.csv semilla_PRIVADA_20260504_172150.txt 3 5
```

La semilla se pasa como **ruta al archivo** `semilla_PRIVADA_<fecha>.txt`, no como
texto en la línea de comandos. Así no queda registrada en el historial de la shell
ni es visible con `ps`.

Genera dos informes con un identificador único de fecha+hora:
- `informe_publico_<id>.txt` — solo Customer IDs. **Es el que compartes con los socios.**
- `informe_PRIVADO_<id>.txt` — incluye los emails. Solo uso interno.

### 4. Si alguien rechaza el premio

No hace falta volver a sortear: los suplentes ya están sorteados y ordenados. Si el
ganador 2 rechaza, pasa al primer suplente; si también rechaza, al segundo, etc.
Esto está documentado en el informe público, así que es transparente.

## Verificación (cualquier socio)

Cualquiera con el script, el CSV de participantes y el informe público puede verificar:

```
python sorteo.py verificar participantes.csv informe_publico_<id>.txt [compromiso_PUBLICO_<fecha>.txt]
```

El último argumento (el archivo de compromiso) es opcional. Si se aporta, el script
cruza automáticamente el hash de la semilla con el compromiso publicado antes del
cierre. Si no, el script imprime el hash y deja que el verificador lo compare a mano
con el publicado.

El script comprueba tres cosas:
1. El hash de la lista de Customer IDs coincide con el del informe.
2. El hash de la semilla coincide con el compromiso publicado antes del sorteo.
3. Re-ejecutando el algoritmo se obtienen exactamente los mismos ganadores y suplentes.

Si las tres cosas dan ✅, el sorteo es matemáticamente irrefutable.

## Por qué es un sorteo limpio

- **No pudiste manipular la semilla**: te comprometiste con su hash antes de saber
  quién participaría. SHA256 hace imposible encontrar otra semilla con el mismo hash.
- **No pudiste manipular la lista**: su hash queda registrado en el informe junto a
  la semilla revelada. Si añades o quitas a alguien después, los hashes no cuadran.
- **El algoritmo es determinista**: dada la misma lista y la misma semilla, siempre
  se obtienen exactamente los mismos ganadores en el mismo orden. Cualquiera puede
  re-ejecutarlo.

## Sobre privacidad (RGPD)

El informe público solo contiene Customer IDs de Stripe, no datos personales.
Cada socio sabe cuál es el suyo (lo recibe en sus facturas/recibos de Stripe) y
puede comprobar si ha resultado ganador. Los emails solo aparecen en el informe
privado, que se usa internamente para contactar a los ganadores.


## Ejemplo

### Compromiso de sorteo

COMPROMISO DE SORTEO
Generado: 2026-05-04T17:24:21.618313
Hash SHA256 de la semilla: b1434d0902799af456deb3c187f6720d7ccbe7598fd913fb5fc7c13daca5e636

La semilla original se revelará tras el cierre de inscripciones.
Cualquiera podrá verificar entonces que sha256(semilla) == hash de arriba.

### Semilla privada generada

aa21b6ee06b5140b6eacca2d399b0e5ed0e9d00975521b9adf1232a2e58bacdb

### Informe público de sorteo
INFORME DE SORTEO
=================
ID del sorteo:        20260504_172442_b1434d09
Fecha y hora:         2026-05-04T17:24:42.575195
Total participantes:  82
Ganadores:            6
Suplentes:            10

VERIFICACIÓN CRIPTOGRÁFICA
--------------------------
Hash SHA256 de la lista de Customer IDs:  71905a02f5b8cef3658e3019235a96bee45618f47bbdfb4d966cf12f844f806e
Semilla revelada:                         aa21b6ee06b5140b6eacca2d399b0e5ed0e9d00975521b9adf1232a2e58bacdb
Hash SHA256 de la semilla:                b1434d0902799af456deb3c187f6720d7ccbe7598fd913fb5fc7c13daca5e636
  (este hash debe coincidir con el compromiso publicado antes del sorteo)

GANADORES (por orden de extracción)
-----------------------------------
  1. cus_EJEMPLOWIN0001
  2. cus_EJEMPLOWIN0002
  3. cus_EJEMPLOWIN0003
  4. cus_EJEMPLOWIN0004
  5. cus_EJEMPLOWIN0005
  6. cus_EJEMPLOWIN0006

SUPLENTES (en orden de prioridad si algún ganador rechaza)
------------------------------------------------------------
  1. cus_EJEMPLOSUP0001
  2. cus_EJEMPLOSUP0002
  3. cus_EJEMPLOSUP0003
  4. cus_EJEMPLOSUP0004
  5. cus_EJEMPLOSUP0005
  6. cus_EJEMPLOSUP0006
  7. cus_EJEMPLOSUP0007
  8. cus_EJEMPLOSUP0008
  9. cus_EJEMPLOSUP0009
  10. cus_EJEMPLOSUP0010

---
Cualquier socio puede verificar este sorteo ejecutando:
  python sorteo.py verificar <csv_participantes> informe_publico_20260504_172442_b1434d09.txt [compromiso_PUBLICO_XXX.txt]

### Informe privado de sorteo

INFORME DE SORTEO
=================
ID del sorteo:        20260504_172442_b1434d09
Fecha y hora:         2026-05-04T17:24:42.575195
Total participantes:  82
Ganadores:            6
Suplentes:            10

VERIFICACIÓN CRIPTOGRÁFICA
--------------------------
Hash SHA256 de la lista de Customer IDs:  71905a02f5b8cef3658e3019235a96bee45618f47bbdfb4d966cf12f844f806e
Semilla revelada:                         aa21b6ee06b5140b6eacca2d399b0e5ed0e9d00975521b9adf1232a2e58bacdb
Hash SHA256 de la semilla:                b1434d0902799af456deb3c187f6720d7ccbe7598fd913fb5fc7c13daca5e636
  (este hash debe coincidir con el compromiso publicado antes del sorteo)

Hash SHA256 de la lista (con emails):     fc67e5dce0ec6413f2ffe4502876c3eae5423c9073334fc17c2edce6fa2a301d
  (auditoría interna; no publicar)

⚠️  ARCHIVO PRIVADO — contiene emails. NO compartir públicamente.

GANADORES
-----------------------------------
  1. cus_EJEMPLOWIN0001  →  x@gmail.com
  2. cus_EJEMPLOWIN0002  →  x@gmail.com
  3. cus_EJEMPLOWIN0003  →  x@hotmail.com
  4. cus_EJEMPLOWIN0004  →  x@gmail.com
  5. cus_EJEMPLOWIN0005  →  x@gmail.com
  6. cus_EJEMPLOWIN0006  →  x@gmail.com

SUPLENTES (en orden de prioridad)
-----------------------------------
  1. cus_EJEMPLOSUP0001  →  x@gmail.com
  2. cus_EJEMPLOSUP0002  →  x@gmail.com
  3. cus_EJEMPLOSUP0003  →  x@yahoo.es
  4. cus_EJEMPLOSUP0004  →  x@gmail.com
  5. cus_EJEMPLOSUP0005  →  x@gmail.com
  6. cus_EJEMPLOSUP0006  →  x@@gmail.com
  7. cus_EJEMPLOSUP0007  →  x@gmail.com
  8. cus_EJEMPLOSUP0008  →  x@gmail.com
  9. cus_EJEMPLOSUP0009  →  x@gmail.com
  10. cus_EJEMPLOSUP0010  → x@gmail.com
