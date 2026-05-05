#!/usr/bin/env python3
"""
Sorteo verificable con commit-reveal para socios de una asociación.

Uso:
  1) Generar compromiso (antes del cierre de inscripciones):
     python sorteo.py commit

  2) Realizar el sorteo (tras el cierre, leyendo la semilla del archivo privado):
     python sorteo.py sortear participantes.csv semilla_PRIVADA_XXX.txt <n_ganadores> <n_suplentes>

  3) Verificar un sorteo ya realizado (opcionalmente con el compromiso original):
     python sorteo.py verificar participantes.csv informe_publico_XXX.txt [compromiso_PUBLICO_XXX.txt]
"""

import argparse
import csv
import hashlib
import re
import secrets
import sys
from datetime import datetime
from pathlib import Path

CUSTOMER_ID_PATTERN = re.compile(r"^cus_[A-Za-z0-9]{14}$")


class ParticipantList:
    """Lista de participantes ordenada de forma determinista por customer_id.

    El orden determinista es crítico: garantiza que el resultado del sorteo no
    depende del orden de las filas en el CSV.
    """

    def __init__(self, items):
        # items: lista de tuplas (customer_id, email)
        self.items = items

    def __len__(self):
        return len(self.items)

    @classmethod
    def from_csv(cls, csv_path):
        participants = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns = {c.strip(): c for c in reader.fieldnames or []}
            if "Customer ID" not in columns or "Customer Email" not in columns:
                raise ValueError(
                    "El CSV debe tener las columnas 'Customer ID' y 'Customer Email'"
                )
            id_col = columns["Customer ID"]
            email_col = columns["Customer Email"]

            for row_num, row in enumerate(reader, start=2):
                cid = (row.get(id_col) or "").strip()
                email = (row.get(email_col) or "").strip().lower()

                if not cid:
                    continue
                if not CUSTOMER_ID_PATTERN.match(cid):
                    raise ValueError(
                        f"Fila {row_num}: Customer ID inválido '{cid}'. "
                        f"Debe tener formato cus_ + 14 caracteres alfanuméricos."
                    )
                if cid in participants:
                    raise ValueError(f"Fila {row_num}: Customer ID duplicado '{cid}'.")
                if not email:
                    raise ValueError(f"Fila {row_num}: email vacío para {cid}.")

                participants[cid] = email

        ordered = sorted(participants.items(), key=lambda x: x[0])
        return cls(ordered)

    def public_hash(self):
        """SHA256 de los Customer IDs (sin emails, publicable)."""
        content = "\n".join(cid for cid, _ in self.items)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def private_hash(self):
        """SHA256 incluyendo emails (auditoría interna, no publicar)."""
        content = "\n".join(f"{cid}|{email}" for cid, email in self.items)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class Commitment:
    """Una semilla y su hash SHA256."""

    def __init__(self, seed):
        self.seed = seed

    @classmethod
    def generate(cls):
        return cls(secrets.token_hex(32))

    @classmethod
    def from_file(cls, path):
        seed = Path(path).read_text(encoding="utf-8").strip()
        if not seed:
            raise ValueError(f"El archivo de semilla '{path}' está vacío.")
        return cls(seed)

    @property
    def hash(self):
        return hashlib.sha256(self.seed.encode("utf-8")).hexdigest()


class Draw:
    """Algoritmo determinista de extracción con rejection sampling.

    Para cada posición i del 0 al n_total-1:
      - calcula sha256(semilla + '-' + i + '-' + intento), empezando con intento=0
      - si el valor cae fuera del mayor múltiplo de n que entra en 2^256, se
        descarta y se incrementa 'intento' (en la práctica casi nunca ocurre,
        pero garantiza distribución uniforme exacta)
      - usa el valor aceptado como índice en la lista de disponibles y extrae
    """

    def __init__(self, participants, commitment):
        self.participants = participants
        self.commitment = commitment

    def run(self, n_total):
        if n_total > len(self.participants):
            raise ValueError(
                f"Pedidos {n_total} pero solo hay {len(self.participants)} participantes."
            )

        available = list(self.participants.items)
        chosen = []
        seed = self.commitment.seed
        for i in range(n_total):
            n = len(available)
            max_valid = (2**256 // n) * n
            attempt = 0
            while True:
                h = hashlib.sha256(f"{seed}-{i}-{attempt}".encode("utf-8")).hexdigest()
                v = int(h, 16)
                if v < max_valid:
                    idx = v % n
                    break
                attempt += 1
            chosen.append(available.pop(idx))
        return chosen


class Report:
    """Informe del sorteo. Encapsula el formato (escritura) y el parseo (lectura).s"""

    def __init__(
        self,
        draw_id,
        timestamp,
        n_participants,
        list_hash,
        seed,
        seed_hash,
        winners,
        alternates,
        private_list_hash=None,
    ):
        self.draw_id = draw_id
        self.timestamp = timestamp
        self.n_participants = n_participants
        self.list_hash = list_hash
        self.seed = seed
        self.seed_hash = seed_hash
        self.winners = winners
        self.alternates = alternates
        self.private_list_hash = private_list_hash

    @property
    def n_winners(self):
        return len(self.winners)

    @property
    def n_alternates(self):
        return len(self.alternates)

    def _header(self):
        return (
            f"INFORME DE SORTEO\n"
            f"=================\n"
            f"ID del sorteo:        {self.draw_id}\n"
            f"Fecha y hora:         {self.timestamp}\n"
            f"Total participantes:  {self.n_participants}\n"
            f"Ganadores:            {self.n_winners}\n"
            f"Suplentes:            {self.n_alternates}\n\n"
            f"VERIFICACIÓN CRIPTOGRÁFICA\n"
            f"--------------------------\n"
            f"Hash SHA256 de la lista de Customer IDs:  {self.list_hash}\n"
            f"Semilla revelada:                         {self.seed}\n"
            f"Hash SHA256 de la semilla:                {self.seed_hash}\n"
            f"  (este hash debe coincidir con el compromiso publicado antes del sorteo)\n\n"
        )

    def write_public(self, path):
        path = Path(path)
        lines = [
            self._header(),
            "GANADORES (por orden de extracción)\n",
            "-" * 35 + "\n",
        ]
        for i, (cid, _) in enumerate(self.winners, 1):
            lines.append(f"  {i}. {cid}\n")
        lines.append("\nSUPLENTES (en orden de prioridad si algún ganador rechaza)\n")
        lines.append("-" * 60 + "\n")
        for i, (cid, _) in enumerate(self.alternates, 1):
            lines.append(f"  {i}. {cid}\n")
        lines.append(
            "\n---\nCualquier socio puede verificar este sorteo ejecutando:\n"
            f"  python sorteo.py verificar <csv_participantes> informe_publico_{self.draw_id}.txt [compromiso_PUBLICO_XXX.txt]\n"
        )
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def write_private(self, path):
        if self.private_list_hash is None:
            raise ValueError(
                "No se puede escribir el informe privado sin private_list_hash."
            )
        path = Path(path)
        lines = [
            self._header(),
            f"Hash SHA256 de la lista (con emails):     {self.private_list_hash}\n"
            f"  (auditoría interna; no publicar)\n\n",
            "⚠️  ARCHIVO PRIVADO — contiene emails. NO compartir públicamente.\n\n",
            "GANADORES\n",
            "-" * 35 + "\n",
        ]
        for i, (cid, email) in enumerate(self.winners, 1):
            lines.append(f"  {i}. {cid}  →  {email}\n")
        lines.append("\nSUPLENTES (en orden de prioridad)\n")
        lines.append("-" * 35 + "\n")
        for i, (cid, email) in enumerate(self.alternates, 1):
            lines.append(f"  {i}. {cid}  →  {email}\n")
        path.write_text("".join(lines), encoding="utf-8")
        return path

    @classmethod
    def parse_public(cls, path):
        """Lee un informe público y devuelve un Report (sin emails: cid, None)."""
        text = Path(path).read_text(encoding="utf-8")

        def extract(pattern):
            m = re.search(pattern, text)
            if not m:
                raise ValueError(f"No se encontró '{pattern}' en el informe.")
            return m.group(1).strip()

        n_winners = int(extract(r"Ganadores:\s+(\d+)"))
        n_alternates = int(extract(r"Suplentes:\s+(\d+)"))
        declared_ids = re.findall(r"\d+\.\s+(cus_[A-Za-z0-9]{14})", text)
        if len(declared_ids) != n_winners + n_alternates:
            raise ValueError(
                f"El informe declara {n_winners + n_alternates} elegidos pero "
                f"se encontraron {len(declared_ids)} Customer IDs en el texto."
            )

        return cls(
            draw_id=extract(r"ID del sorteo:\s+(\S+)"),
            timestamp=extract(r"Fecha y hora:\s+(\S+)"),
            n_participants=int(extract(r"Total participantes:\s+(\d+)")),
            list_hash=extract(r"Hash SHA256 de la lista de Customer IDs:\s+(\S+)"),
            seed=extract(r"Semilla revelada:\s+(\S+)"),
            seed_hash=extract(r"Hash SHA256 de la semilla:\s+(\S+)"),
            winners=[(cid, None) for cid in declared_ids[:n_winners]],
            alternates=[(cid, None) for cid in declared_ids[n_winners:]],
        )


def cmd_commit():
    """Genera una semilla aleatoria, la guarda en privado y muestra su hash público."""
    commitment = Commitment.generate()
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    seed_file = Path(f"semilla_PRIVADA_{timestamp}.txt")
    commitment_file = Path(f"compromiso_PUBLICO_{timestamp}.txt")

    seed_file.write_text(commitment.seed + "\n", encoding="utf-8")
    commitment_file.write_text(
        f"COMPROMISO DE SORTEO\n"
        f"Generado: {now.isoformat()}\n"
        f"Hash SHA256 de la semilla: {commitment.hash}\n\n"
        f"La semilla original se revelará tras el cierre de inscripciones.\n"
        f"Cualquiera podrá verificar entonces que sha256(semilla) == hash de arriba.\n",
        encoding="utf-8",
    )

    print(f"✅ Semilla generada y guardada en:  {seed_file}  (NO COMPARTIR aún)")
    print(f"✅ Compromiso público guardado en:  {commitment_file}")
    print(f"\n📢 PUBLICAR ESTE HASH ANTES DEL CIERRE DE INSCRIPCIONES:")
    print(f"   {commitment.hash}")


def cmd_draw(csv_path, seed_path, n_winners, n_alternates):
    """Ejecuta el sorteo y genera dos informes (público y privado)."""
    commitment = Commitment.from_file(seed_path)
    participants = ParticipantList.from_csv(csv_path)
    chosen = Draw(participants, commitment).run(n_winners + n_alternates)

    now = datetime.now()
    draw_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{commitment.hash[:8]}"

    report = Report(
        draw_id=draw_id,
        timestamp=now.isoformat(),
        n_participants=len(participants),
        list_hash=participants.public_hash(),
        seed=commitment.seed,
        seed_hash=commitment.hash,
        winners=chosen[:n_winners],
        alternates=chosen[n_winners:],
        private_list_hash=participants.private_hash(),
    )

    public_file = report.write_public(f"informe_publico_{draw_id}.txt")
    private_file = report.write_private(f"informe_PRIVADO_{draw_id}.txt")

    print(f"✅ Sorteo realizado: {draw_id}")
    print(f"   Informe público (compartir): {public_file}")
    print(f"   Informe privado (uso interno): {private_file}")
    print(f"\n📢 Hash de la semilla a publicar/verificar: {commitment.hash}")


def cmd_verify(csv_path, report_path, commitment_path=None):
    """Re-ejecuta el sorteo desde el informe y comprueba que coincide.

    Si se pasa el archivo de compromiso original, también se comprueba que el
    hash de la semilla coincide con el publicado antes del cierre.
    """
    report = Report.parse_public(report_path)
    participants = ParticipantList.from_csv(csv_path)
    commitment = Commitment(report.seed)

    print("Verificación del sorteo")
    print("=======================")
    list_ok = participants.public_hash() == report.list_hash
    seed_ok = commitment.hash == report.seed_hash
    print(f"  Hash lista coincide:    {'✅' if list_ok else '❌'}")
    print(f"  Hash semilla coincide:  {'✅' if seed_ok else '❌'}")

    commitment_ok = True
    if commitment_path:
        commitment_text = Path(commitment_path).read_text(encoding="utf-8")
        m = re.search(r"Hash SHA256 de la semilla:\s+(\S+)", commitment_text)
        if not m:
            raise ValueError("No se encontró el hash de la semilla en el compromiso.")
        commitment_ok = m.group(1).strip() == commitment.hash
        print(f"  Coincide con compromiso publicado: {'✅' if commitment_ok else '❌'}")
    else:
        print(
            f"  ⚠  Sin archivo de compromiso: comprueba a mano que\n"
            f"     {commitment.hash}\n"
            f"     coincide con el hash publicado antes del cierre."
        )

    if not (list_ok and seed_ok and commitment_ok):
        print("\n❌ La verificación FALLA: los hashes no coinciden.")
        sys.exit(1)

    chosen = Draw(participants, commitment).run(report.n_winners + report.n_alternates)
    recalculated_ids = [cid for cid, _ in chosen]
    declared_ids = [cid for cid, _ in report.winners + report.alternates]

    result_ok = recalculated_ids == declared_ids
    print(f"  Resultado reproducible: {'✅' if result_ok else '❌'}")

    if result_ok:
        print("\n✅ SORTEO VERIFICADO CORRECTAMENTE.")
    else:
        print("\n❌ Los ganadores recalculados no coinciden con los del informe.")
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sorteo.py",
        description="Sorteo verificable con commit-reveal para socios de una asociación.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="comando")

    sub.add_parser("commit", help="Genera la semilla y publica su hash (compromiso)")

    p_draw = sub.add_parser("sortear", help="Ejecuta el sorteo y genera los informes")
    p_draw.add_argument("csv", help="CSV con columnas 'Customer ID' y 'Customer Email'")
    p_draw.add_argument("seed_path", help="Ruta al archivo semilla_PRIVADA_*.txt")
    p_draw.add_argument("n_winners", type=int, help="Número de ganadores")
    p_draw.add_argument("n_alternates", type=int, help="Número de suplentes")

    p_verify = sub.add_parser("verificar", help="Verifica un sorteo previo")
    p_verify.add_argument("csv", help="CSV con la lista de participantes")
    p_verify.add_argument("report", help="informe_publico_*.txt a verificar")
    p_verify.add_argument(
        "commitment",
        nargs="?",
        default=None,
        help="(opcional) compromiso_PUBLICO_*.txt para cross-check automático",
    )

    return parser


def main():
    args = build_parser().parse_args()

    if args.cmd == "commit":
        cmd_commit()
    elif args.cmd == "sortear":
        cmd_draw(args.csv, args.seed_path, args.n_winners, args.n_alternates)
    elif args.cmd == "verificar":
        cmd_verify(args.csv, args.report, args.commitment)


if __name__ == "__main__":
    main()
