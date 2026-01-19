"""
Brand.Me Provenance Client
=========================

Provides O(1) provenance lookups and immutable ownership history
tracking using Spanner interleaved tables.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types

from brandme_core.logging import get_logger

logger = get_logger("spanner.provenance")


class TransferType(Enum):
    """Types of ownership transfers."""
    MINT = "mint"
    PURCHASE = "purchase"
    GIFT = "gift"
    TRADE = "trade"
    INHERITANCE = "inheritance"
    RETURN = "return"


@dataclass
class ProvenanceEntry:
    """A single entry in the provenance chain."""
    provenance_id: str
    asset_id: str
    sequence_num: int
    from_user_id: Optional[str]
    to_user_id: str
    transfer_type: str
    price: Optional[float]
    currency: Optional[str]
    blockchain_tx_hash: Optional[str]
    midnight_proof_hash: Optional[str]
    transfer_at: datetime


@dataclass
class AssetProvenance:
    """Full provenance information for an asset."""
    asset_id: str
    creator_id: str
    creator_name: Optional[str]
    current_owner_id: str
    current_owner_name: Optional[str]
    created_at: datetime
    transfer_count: int
    chain: List[ProvenanceEntry]


@dataclass
class OwnershipInfo:
    """Current ownership information."""
    asset_id: str
    owner_id: str
    owner_name: Optional[str]
    acquired_at: datetime
    transfer_method: Optional[str]
    blockchain_tx_hash: Optional[str]


class ProvenanceClient:
    """
    Provenance operations using Spanner interleaved tables.

    Provides:
    - O(1) current ownership lookup
    - O(n) full provenance chain retrieval (where n = transfers)
    - Immutable provenance recording
    - Creator-Asset relationship tracking
    """

    def __init__(self, pool_manager):
        self.pool = pool_manager

    async def get_current_owner(self, asset_id: str) -> Optional[OwnershipInfo]:
        """
        Get current owner of an asset.

        O(1) lookup using indexed query on Owns table.
        """
        sql = """
        SELECT
            o.asset_id,
            o.owner_id,
            u.display_name,
            o.acquired_at,
            o.transfer_method,
            o.blockchain_tx_hash
        FROM Owns o
        JOIN Users u ON o.owner_id = u.user_id
        WHERE o.asset_id = @asset_id AND o.is_current = true
        """

        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )
            rows = list(result)

        if not rows:
            return None

        row = rows[0]
        return OwnershipInfo(
            asset_id=row[0],
            owner_id=row[1],
            owner_name=row[2],
            acquired_at=row[3],
            transfer_method=row[4],
            blockchain_tx_hash=row[5]
        )

    async def get_creator(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Get creator of an asset.

        O(1) lookup using Created table.
        """
        sql = """
        SELECT
            c.creator_id,
            u.display_name,
            u.handle,
            c.created_at,
            c.blockchain_mint_tx
        FROM Created c
        JOIN Users u ON c.creator_id = u.user_id
        WHERE c.asset_id = @asset_id
        """

        async with self.pool.session() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )
            rows = list(result)

        if not rows:
            return None

        row = rows[0]
        return {
            'creator_id': row[0],
            'display_name': row[1],
            'handle': row[2],
            'created_at': row[3],
            'mint_tx_hash': row[4]
        }

    async def get_full_provenance(self, asset_id: str) -> Optional[AssetProvenance]:
        """
        Get full provenance chain for an asset.

        Uses interleaved ProvenanceChain table for efficient retrieval.
        O(n) where n = number of transfers.
        """
        # Get asset with creator and current owner
        asset_sql = """
        SELECT
            a.asset_id,
            a.creator_user_id,
            cu.display_name as creator_name,
            a.current_owner_id,
            ou.display_name as owner_name,
            a.created_at
        FROM Assets a
        JOIN Users cu ON a.creator_user_id = cu.user_id
        JOIN Users ou ON a.current_owner_id = ou.user_id
        WHERE a.asset_id = @asset_id
        """

        # Get provenance chain (interleaved, very fast)
        chain_sql = """
        SELECT
            provenance_id,
            asset_id,
            sequence_num,
            from_user_id,
            to_user_id,
            transfer_type,
            price,
            currency,
            blockchain_tx_hash,
            midnight_proof_hash,
            transfer_at
        FROM ProvenanceChain
        WHERE asset_id = @asset_id
        ORDER BY sequence_num ASC
        """

        async with self.pool.session() as snapshot:
            # Fetch asset info
            asset_result = snapshot.execute_sql(
                asset_sql,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )
            asset_rows = list(asset_result)

            if not asset_rows:
                return None

            asset = asset_rows[0]

            # Fetch provenance chain
            chain_result = snapshot.execute_sql(
                chain_sql,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )

            chain = []
            for row in chain_result:
                chain.append(ProvenanceEntry(
                    provenance_id=row[0],
                    asset_id=row[1],
                    sequence_num=row[2],
                    from_user_id=row[3],
                    to_user_id=row[4],
                    transfer_type=row[5],
                    price=row[6],
                    currency=row[7],
                    blockchain_tx_hash=row[8],
                    midnight_proof_hash=row[9],
                    transfer_at=row[10]
                ))

        return AssetProvenance(
            asset_id=asset[0],
            creator_id=asset[1],
            creator_name=asset[2],
            current_owner_id=asset[3],
            current_owner_name=asset[4],
            created_at=asset[5],
            transfer_count=len(chain),
            chain=chain
        )

    async def record_transfer(
        self,
        asset_id: str,
        from_user_id: Optional[str],
        to_user_id: str,
        transfer_type: TransferType,
        price: Optional[float] = None,
        currency: str = "USD",
        blockchain_tx_hash: Optional[str] = None,
        midnight_proof_hash: Optional[str] = None,
        region_code: str = "us-east1",
        policy_version: Optional[str] = None
    ) -> ProvenanceEntry:
        """
        Record a new transfer in the provenance chain.

        This is an append-only operation that:
        1. Gets next sequence number
        2. Inserts provenance entry
        3. Updates Owns table (mark old as not current, insert new)
        4. Updates Assets.current_owner_id

        Returns the new ProvenanceEntry.
        """
        provenance_id = str(uuid.uuid4())

        def _record(transaction):
            # Get next sequence number
            seq_result = transaction.execute_sql(
                """
                SELECT COALESCE(MAX(sequence_num), 0) + 1
                FROM ProvenanceChain
                WHERE asset_id = @asset_id
                """,
                params={'asset_id': asset_id},
                param_types={'asset_id': param_types.STRING}
            )
            next_seq = list(seq_result)[0][0]

            # Insert provenance entry
            transaction.insert(
                table='ProvenanceChain',
                columns=[
                    'provenance_id', 'asset_id', 'sequence_num',
                    'from_user_id', 'to_user_id', 'transfer_type',
                    'price', 'currency', 'blockchain_tx_hash',
                    'midnight_proof_hash', 'region_code', 'policy_version',
                    'transfer_at'
                ],
                values=[(
                    provenance_id, asset_id, next_seq,
                    from_user_id, to_user_id, transfer_type.value,
                    price, currency, blockchain_tx_hash,
                    midnight_proof_hash, region_code, policy_version,
                    spanner.COMMIT_TIMESTAMP
                )]
            )

            # Mark previous ownership as not current
            if from_user_id:
                transaction.execute_update(
                    """
                    UPDATE Owns
                    SET is_current = false, ended_at = PENDING_COMMIT_TIMESTAMP()
                    WHERE asset_id = @asset_id AND owner_id = @from_user AND is_current = true
                    """,
                    params={
                        'asset_id': asset_id,
                        'from_user': from_user_id
                    },
                    param_types={
                        'asset_id': param_types.STRING,
                        'from_user': param_types.STRING
                    }
                )

            # Insert new ownership
            transaction.insert(
                table='Owns',
                columns=[
                    'owner_id', 'asset_id', 'acquired_at',
                    'transfer_method', 'price', 'currency',
                    'blockchain_tx_hash', 'is_current'
                ],
                values=[(
                    to_user_id, asset_id, spanner.COMMIT_TIMESTAMP,
                    transfer_type.value, price, currency,
                    blockchain_tx_hash, True
                )]
            )

            # Update asset's current owner
            transaction.execute_update(
                """
                UPDATE Assets
                SET current_owner_id = @to_user, updated_at = PENDING_COMMIT_TIMESTAMP()
                WHERE asset_id = @asset_id
                """,
                params={
                    'asset_id': asset_id,
                    'to_user': to_user_id
                },
                param_types={
                    'asset_id': param_types.STRING,
                    'to_user': param_types.STRING
                }
            )

            return next_seq

        sequence_num = self.pool.run_in_transaction(_record)

        logger.info({
            "event": "transfer_recorded",
            "provenance_id": provenance_id,
            "asset_id": asset_id[:8] + "...",
            "from": from_user_id[:8] + "..." if from_user_id else "mint",
            "to": to_user_id[:8] + "...",
            "type": transfer_type.value,
            "sequence": sequence_num
        })

        return ProvenanceEntry(
            provenance_id=provenance_id,
            asset_id=asset_id,
            sequence_num=sequence_num,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            transfer_type=transfer_type.value,
            price=price,
            currency=currency,
            blockchain_tx_hash=blockchain_tx_hash,
            midnight_proof_hash=midnight_proof_hash,
            transfer_at=datetime.utcnow()  # Approximate, actual is commit timestamp
        )

    async def mint_asset(
        self,
        asset_id: str,
        creator_id: str,
        asset_type: str,
        display_name: str,
        authenticity_hash: str,
        blockchain_mint_tx: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mint a new asset (initial creation).

        Creates:
        1. Asset record
        2. Created relationship
        3. Initial Owns relationship
        4. First provenance entry (mint)
        """
        provenance_id = str(uuid.uuid4())

        def _mint(transaction):
            # Create asset
            transaction.insert(
                table='Assets',
                columns=[
                    'asset_id', 'asset_type', 'display_name',
                    'creator_user_id', 'current_owner_id',
                    'authenticity_hash', 'is_active',
                    'created_at', 'updated_at', 'first_minted_at'
                ],
                values=[(
                    asset_id, asset_type, display_name,
                    creator_id, creator_id,  # Creator is initial owner
                    authenticity_hash, True,
                    spanner.COMMIT_TIMESTAMP,
                    spanner.COMMIT_TIMESTAMP,
                    spanner.COMMIT_TIMESTAMP
                )]
            )

            # Create Created relationship
            transaction.insert(
                table='Created',
                columns=['creator_id', 'asset_id', 'created_at', 'blockchain_mint_tx'],
                values=[(creator_id, asset_id, spanner.COMMIT_TIMESTAMP, blockchain_mint_tx)]
            )

            # Create initial Owns relationship
            transaction.insert(
                table='Owns',
                columns=[
                    'owner_id', 'asset_id', 'acquired_at',
                    'transfer_method', 'blockchain_tx_hash', 'is_current'
                ],
                values=[(
                    creator_id, asset_id, spanner.COMMIT_TIMESTAMP,
                    'mint', blockchain_mint_tx, True
                )]
            )

            # Create first provenance entry
            transaction.insert(
                table='ProvenanceChain',
                columns=[
                    'provenance_id', 'asset_id', 'sequence_num',
                    'from_user_id', 'to_user_id', 'transfer_type',
                    'blockchain_tx_hash', 'transfer_at'
                ],
                values=[(
                    provenance_id, asset_id, 1,
                    None, creator_id, 'mint',
                    blockchain_mint_tx, spanner.COMMIT_TIMESTAMP
                )]
            )

        self.pool.run_in_transaction(_mint)

        logger.info({
            "event": "asset_minted",
            "asset_id": asset_id[:8] + "...",
            "creator_id": creator_id[:8] + "...",
            "type": asset_type
        })

        return {
            'asset_id': asset_id,
            'creator_id': creator_id,
            'provenance_id': provenance_id
        }

    async def verify_provenance_chain(self, asset_id: str) -> Dict[str, Any]:
        """
        Verify the integrity of an asset's provenance chain.

        Checks:
        1. Sequence numbers are continuous
        2. Each transfer's to_user matches next transfer's from_user
        3. Current owner matches last transfer's to_user
        """
        provenance = await self.get_full_provenance(asset_id)

        if not provenance:
            return {'valid': False, 'error': 'asset_not_found'}

        if not provenance.chain:
            return {'valid': False, 'error': 'no_provenance_entries'}

        issues = []

        # Check sequence continuity
        expected_seq = 1
        for entry in provenance.chain:
            if entry.sequence_num != expected_seq:
                issues.append(f"Sequence gap: expected {expected_seq}, got {entry.sequence_num}")
            expected_seq += 1

        # Check transfer continuity
        for i in range(1, len(provenance.chain)):
            prev_entry = provenance.chain[i - 1]
            curr_entry = provenance.chain[i]

            if prev_entry.to_user_id != curr_entry.from_user_id:
                issues.append(
                    f"Transfer discontinuity at seq {curr_entry.sequence_num}: "
                    f"prev.to={prev_entry.to_user_id[:8]}... != curr.from={curr_entry.from_user_id[:8] if curr_entry.from_user_id else 'None'}..."
                )

        # Check current owner
        last_entry = provenance.chain[-1]
        if last_entry.to_user_id != provenance.current_owner_id:
            issues.append(
                f"Current owner mismatch: chain.last.to={last_entry.to_user_id[:8]}... "
                f"!= asset.current_owner={provenance.current_owner_id[:8]}..."
            )

        return {
            'valid': len(issues) == 0,
            'asset_id': asset_id,
            'transfer_count': len(provenance.chain),
            'issues': issues
        }
