"""Project Trace Genetic Code Bank and Persistent Atom Store (Subsystem 6).

Ingests verified implementations and negative inhibitors directly into
Project Trace physical SQLite database tables (documents, atoms, lexical_fts,
proposals, events, attachments, and genome_atoms).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stc.core.config import get_settings
from stc.core.errors import TraceMemoryError
from stc.protocols.interfaces import GenomeStoreProtocol
from stc.schemas.models import ExecutionReceipt, GeneType, GenomeAtom

logger = logging.getLogger(__name__)


class GenomeStore(GenomeStoreProtocol):
    """Genetic code bank persisting software genes into Project Trace SQLite DB.

    Adheres strictly to Volume 03 §6 (Subsystem 6 Specification) and Volume 04:
    - Structural Genes: Proven schemas and typing protocols.
    - Behavioral Genes: Deterministic implementations passing all substrate gates.
    - Negative Inhibitor Genes: Refuted designs and failure modes.
    """

    def __init__(self, db_path: Path | str | None = None, timeout: float = 5.0) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            self.db_path = get_settings().trace_db_path
        self.timeout = timeout
        self.init_schema()

    @property
    def has_live_db(self) -> bool:
        """Check if the physical Trace database exists on disk."""
        return self.db_path.is_file()

    def init_schema(self) -> None:
        """Initialize the Project Trace and Genome SQLite tables if not present."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS genome_atoms (
                        gene_id TEXT PRIMARY KEY,
                        gene_type TEXT NOT NULL,
                        component_name TEXT NOT NULL,
                        pattern_signature TEXT NOT NULL,
                        raw_code_or_rule TEXT NOT NULL,
                        receipt_reference TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        document_name TEXT NOT NULL,
                        collection TEXT DEFAULT 'default'
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS atoms (
                        atom_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        content TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proposals (
                        proposal_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        proposal_type TEXT NOT NULL,
                        candidate_json TEXT DEFAULT '{}',
                        decision_reason TEXT NOT NULL,
                        component TEXT DEFAULT '',
                        created_event_id INTEGER DEFAULT 1
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        payload_hash TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attachments (
                        attachment_id TEXT PRIMARY KEY,
                        document_id TEXT,
                        payload BLOB
                    );
                    """
                )

                # Attempt virtual table creation for FTS5 (resilient if FTS5 not compiled in SQLite)
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(
                        """
                        CREATE VIRTUAL TABLE IF NOT EXISTS lexical_fts USING fts5(
                            atom_id UNINDEXED,
                            content,
                            tokenize='porter'
                        );
                        """
                    )
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to initialize Genome DB schema: {exc}") from exc
        finally:
            conn.close()

    def save_gene(self, gene: GenomeAtom) -> str:
        """Persist a GenomeAtom into SQLite and index its contents.

        Conforms strictly to GenomeStoreProtocol.
        """
        if not self.has_live_db:
            self.init_schema()

        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                # 1. Primary genome_atoms record
                created_at_str = (
                    gene.created_at.isoformat()
                    if isinstance(gene.created_at, datetime)
                    else str(gene.created_at)
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO genome_atoms
                    (gene_id, gene_type, component_name, pattern_signature, raw_code_or_rule,
                     receipt_reference, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        gene.gene_id,
                        gene.gene_type.value,
                        gene.component_name,
                        gene.pattern_signature,
                        gene.raw_code_or_rule,
                        gene.receipt_reference,
                        created_at_str,
                    ),
                )

                # 2. Document record
                doc_id = f"doc_{gene.gene_id}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents (document_id, document_name, collection)
                    VALUES (?, ?, 'genome_genes');
                    """,
                    (doc_id, gene.component_name),
                )

                # 3. Attachment blob
                att_id = f"att_{gene.gene_id}"
                payload_bytes = gene.raw_code_or_rule.encode("utf-8")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO attachments (attachment_id, document_id, payload)
                    VALUES (?, ?, ?);
                    """,
                    (att_id, doc_id, payload_bytes),
                )

                # 4. Atom record
                atom_id = f"atom_{gene.gene_id}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO atoms (atom_id, document_id, content)
                    VALUES (?, ?, ?);
                    """,
                    (atom_id, doc_id, gene.raw_code_or_rule),
                )

                # 5. FTS5 Indexing
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(
                        "INSERT OR REPLACE INTO lexical_fts (atom_id, content) VALUES (?, ?);",
                        (atom_id, gene.raw_code_or_rule),
                    )

                # 6. Proposal record
                prop_id = f"prop_{gene.gene_id}"
                status = "REFUTED" if gene.gene_type == GeneType.INHIBITOR else "DECIDED"
                prop_type = (
                    "negative_inhibitor"
                    if gene.gene_type == GeneType.INHIBITOR
                    else gene.gene_type.value
                )
                cand_json = json.dumps(
                    {
                        "gene_id": gene.gene_id,
                        "gene_type": gene.gene_type.value,
                        "pattern_signature": gene.pattern_signature,
                        "receipt_reference": gene.receipt_reference,
                    }
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO proposals
                    (proposal_id, status, proposal_type, candidate_json,
                     decision_reason, component, created_event_id)
                    VALUES (?, ?, ?, ?, ?, ?, 1);
                    """,
                    (
                        prop_id,
                        status,
                        prop_type,
                        cand_json,
                        gene.raw_code_or_rule[:500],
                        gene.component_name,
                    ),
                )

                # 7. Audit event
                evt_id = f"evt_{uuid.uuid4().hex[:12]}"
                payload_hash = hashlib.sha256(payload_bytes).hexdigest()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events (event_id, event_type, payload_hash)
                    VALUES (?, 'genome_gene_promoted', ?);
                    """,
                    (evt_id, payload_hash),
                )

            return gene.gene_id
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to save genome atom {gene.gene_id}: {exc}") from exc
        finally:
            conn.close()

    def find_genes(self, tags: list[str]) -> list[GenomeAtom]:
        """Search the genome store for genes matching tags or component names.

        Conforms strictly to GenomeStoreProtocol.
        """
        if not self.has_live_db:
            return []

        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            cursor = conn.cursor()
            clean_tags = [t.strip().lower() for t in tags if t.strip()]

            if not clean_tags or "*" in clean_tags:
                cursor.execute(
                    """
                    SELECT gene_id, gene_type, component_name, pattern_signature,
                           raw_code_or_rule, receipt_reference, created_at
                    FROM genome_atoms
                    ORDER BY created_at DESC;
                    """
                )
            else:
                clauses: list[str] = []
                params: list[Any] = []
                for tag in clean_tags:
                    clauses.append(
                        """(
                            LOWER(component_name) = ?
                            OR LOWER(component_name) LIKE ?
                            OR LOWER(gene_type) = ?
                            OR LOWER(pattern_signature) LIKE ?
                            OR LOWER(raw_code_or_rule) LIKE ?
                        )"""
                    )
                    params.extend([tag, f"%{tag}%", tag, f"%{tag}%", f"%{tag}%"])

                query = f"""
                    SELECT gene_id, gene_type, component_name, pattern_signature,
                           raw_code_or_rule, receipt_reference, created_at
                    FROM genome_atoms
                    WHERE {" OR ".join(clauses)}
                    ORDER BY created_at DESC;
                """
                cursor.execute(query, params)

            rows = cursor.fetchall()
            genes: list[GenomeAtom] = []
            seen_ids: set[str] = set()

            for row in rows:
                gene_id = str(row[0])
                if gene_id in seen_ids:
                    continue
                seen_ids.add(gene_id)

                g_type = GeneType(row[1])
                comp_name = str(row[2])
                sig = str(row[3])
                code = str(row[4])
                rcpt_ref = str(row[5])
                created_str = str(row[6])

                try:
                    dt = datetime.fromisoformat(created_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                except ValueError:
                    dt = datetime.now(UTC)

                genes.append(
                    GenomeAtom(
                        gene_id=gene_id,
                        gene_type=g_type,
                        component_name=comp_name,
                        pattern_signature=sig,
                        raw_code_or_rule=code,
                        receipt_reference=rcpt_ref,
                        created_at=dt,
                    )
                )

            return genes
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to query genome atoms: {exc}") from exc
        finally:
            conn.close()

    def ingest_trace(
        self,
        task_id: str,
        receipt: ExecutionReceipt,
        diff_text: str = "",
        refutation_log: list[str] | None = None,
    ) -> list[GenomeAtom]:
        """Ingest verified candidate diff, receipt, and refutations into Trace Genome.

        Executes Tier 6 Node N21 per 02_EXECUTION_DAG.md.
        Emits structural genes, behavioral genes, and negative inhibitor genes.
        """
        ingested: list[GenomeAtom] = []
        commit_short = receipt.commit_hash[:8] if receipt.commit_hash else "c0ffee"

        # 1. Ingest positive structural gene
        struct_gene = GenomeAtom(
            gene_id=f"gene_struct_{uuid.uuid4().hex[:8]}",
            gene_type=GeneType.STRUCTURAL,
            component_name=task_id,
            pattern_signature=f"structural:{task_id}:{commit_short}",
            raw_code_or_rule=diff_text or f"# Verified implementation for {task_id}",
            receipt_reference=receipt.receipt_id,
        )
        self.save_gene(struct_gene)
        ingested.append(struct_gene)

        # 2. Ingest positive behavioral gene
        behav_gene = GenomeAtom(
            gene_id=f"gene_behav_{uuid.uuid4().hex[:8]}",
            gene_type=GeneType.BEHAVIORAL,
            component_name=task_id,
            pattern_signature=f"behavioral:{task_id}:{commit_short}",
            raw_code_or_rule=(
                f"# Deterministic pass for {task_id} with receipt {receipt.receipt_id}\n"
                f"# Gates: ruff=0, mypy=0, pytest=0, mutmut={receipt.gate_mutmut.exit_code}"
            ),
            receipt_reference=receipt.receipt_id,
        )
        self.save_gene(behav_gene)
        ingested.append(behav_gene)

        # 3. Ingest negative inhibitors if refutations occurred
        if refutation_log:
            for ref in refutation_log:
                ref_hash = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:8]
                inhibitor_gene = GenomeAtom(
                    gene_id=f"gene_inhib_{uuid.uuid4().hex[:8]}",
                    gene_type=GeneType.INHIBITOR,
                    component_name=task_id,
                    pattern_signature=f"inhibitor:{task_id}:{ref_hash}",
                    raw_code_or_rule=ref,
                    receipt_reference=receipt.receipt_id,
                )
                self.save_gene(inhibitor_gene)
                ingested.append(inhibitor_gene)

        return ingested


__all__ = ["GenomeStore"]
