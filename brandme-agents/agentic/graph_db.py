"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Knowledge Graph Database
========================
Neo4j integration for Brand.Me knowledge graph
"""

from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any, Optional
import os
import logging

logger = logging.getLogger(__name__)


class BrandMeKnowledgeGraph:
    """
    Knowledge graph manager for Brand.Me entities and relationships.

    Manages:
    - Users, Garments, Creators, Brands, Scans, Policies
    - Relationships: OWNS, SCANNED, FRIENDS_WITH, CREATED_BY, etc.
    - Vector embeddings for semantic search
    """

    def __init__(self, uri: str, user: str, password: str):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._create_constraints()
        self._create_indexes()

    def close(self):
        """Close database connection"""
        self.driver.close()

    def _create_constraints(self):
        """Create uniqueness constraints"""
        with self.driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
                "CREATE CONSTRAINT garment_id IF NOT EXISTS FOR (g:Garment) REQUIRE g.garment_id IS UNIQUE",
                "CREATE CONSTRAINT creator_id IF NOT EXISTS FOR (c:Creator) REQUIRE c.creator_id IS UNIQUE",
                "CREATE CONSTRAINT brand_id IF NOT EXISTS FOR (b:Brand) REQUIRE b.brand_id IS UNIQUE",
                "CREATE CONSTRAINT scan_id IF NOT EXISTS FOR (s:Scan) REQUIRE s.scan_id IS UNIQUE",
                "CREATE CONSTRAINT policy_id IF NOT EXISTS FOR (p:Policy) REQUIRE p.policy_id IS UNIQUE",
            ]
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    logger.debug(f"Constraint may already exist: {e}")

    def _create_indexes(self):
        """Create indexes for performance"""
        with self.driver.session() as session:
            indexes = [
                # Vector indexes for semantic search
                "CREATE VECTOR INDEX user_embedding IF NOT EXISTS FOR (u:User) ON u.persona_vector OPTIONS {indexConfig: {`vector.dimensions`: 512, `vector.similarity_function`: 'cosine'}}",
                "CREATE VECTOR INDEX garment_embedding IF NOT EXISTS FOR (g:Garment) ON g.embedding OPTIONS {indexConfig: {`vector.dimensions`: 512, `vector.similarity_function`: 'cosine'}}",

                # Text indexes
                "CREATE INDEX user_handle IF NOT EXISTS FOR (u:User) ON u.handle",
                "CREATE INDEX garment_tag IF NOT EXISTS FOR (g:Garment) ON g.garment_tag",
                "CREATE INDEX creator_name IF NOT EXISTS FOR (c:Creator) ON c.creator_name",
            ]
            for index in indexes:
                try:
                    session.run(index)
                except Exception as e:
                    logger.debug(f"Index may already exist: {e}")

    # ============================================================
    # Entity Creation
    # ============================================================

    def create_user(self, user_data: Dict[str, Any]) -> str:
        """
        Create or update user node.

        Args:
            user_data: {user_id, handle, did_cardano, trust_score, persona_vector}

        Returns:
            user_id
        """
        with self.driver.session() as session:
            result = session.run("""
                MERGE (u:User {user_id: $user_id})
                SET u.handle = $handle,
                    u.did_cardano = $did_cardano,
                    u.trust_score = $trust_score,
                    u.persona_vector = $persona_vector,
                    u.updated_at = datetime()
                RETURN u.user_id as user_id
            """, **user_data)
            return result.single()["user_id"]

    def create_garment(self, garment_data: Dict[str, Any]) -> str:
        """
        Create or update garment node.

        Args:
            garment_data: {garment_id, garment_tag, creator_id, authenticity_hash, embedding}

        Returns:
            garment_id
        """
        with self.driver.session() as session:
            result = session.run("""
                MERGE (g:Garment {garment_id: $garment_id})
                SET g.garment_tag = $garment_tag,
                    g.creator_id = $creator_id,
                    g.authenticity_hash = $authenticity_hash,
                    g.embedding = $embedding,
                    g.updated_at = datetime()
                RETURN g.garment_id as garment_id
            """, **garment_data)
            return result.single()["garment_id"]

    def create_creator(self, creator_data: Dict[str, Any]) -> str:
        """Create or update creator node"""
        with self.driver.session() as session:
            result = session.run("""
                MERGE (c:Creator {creator_id: $creator_id})
                SET c.creator_name = $creator_name,
                    c.brand = $brand,
                    c.reputation_score = $reputation_score,
                    c.style_embedding = $style_embedding,
                    c.updated_at = datetime()
                RETURN c.creator_id as creator_id
            """, **creator_data)
            return result.single()["creator_id"]

    def create_scan(self, scan_data: Dict[str, Any]) -> str:
        """Create scan event node"""
        with self.driver.session() as session:
            result = session.run("""
                CREATE (s:Scan {
                    scan_id: $scan_id,
                    timestamp: datetime($timestamp),
                    decision: $decision,
                    policy_version: $policy_version,
                    cardano_tx_hash: $cardano_tx_hash,
                    midnight_tx_hash: $midnight_tx_hash
                })
                RETURN s.scan_id as scan_id
            """, **scan_data)
            return result.single()["scan_id"]

    # ============================================================
    # Relationship Creation
    # ============================================================

    def create_ownership(self, user_id: str, garment_id: str, timestamp: str):
        """Create OWNS relationship"""
        with self.driver.session() as session:
            session.run("""
                MATCH (u:User {user_id: $user_id})
                MATCH (g:Garment {garment_id: $garment_id})
                MERGE (u)-[r:OWNS {since: datetime($timestamp)}]->(g)
                RETURN r
            """, user_id=user_id, garment_id=garment_id, timestamp=timestamp)

    def create_friendship(self, user_id1: str, user_id2: str, trust_weight: float = 1.0):
        """Create bidirectional FRIENDS_WITH relationship"""
        with self.driver.session() as session:
            session.run("""
                MATCH (u1:User {user_id: $user_id1})
                MATCH (u2:User {user_id: $user_id2})
                MERGE (u1)-[r1:FRIENDS_WITH {trust_weight: $trust_weight}]->(u2)
                MERGE (u2)-[r2:FRIENDS_WITH {trust_weight: $trust_weight}]->(u1)
                RETURN r1, r2
            """, user_id1=user_id1, user_id2=user_id2, trust_weight=trust_weight)

    def create_scan_relationship(self, scan_id: str, user_id: str, garment_id: str):
        """Link scan to user and garment"""
        with self.driver.session() as session:
            session.run("""
                MATCH (s:Scan {scan_id: $scan_id})
                MATCH (u:User {user_id: $user_id})
                MATCH (g:Garment {garment_id: $garment_id})
                MERGE (u)-[:SCANNED]->(s)
                MERGE (s)-[:VERIFIED]->(g)
                RETURN s
            """, scan_id=scan_id, user_id=user_id, garment_id=garment_id)

    # ============================================================
    # Graph Queries
    # ============================================================

    def find_trust_path(self, user_id1: str, user_id2: str) -> Optional[List[Dict]]:
        """
        Find shortest trust path between two users.

        Returns:
            List of nodes and relationships in path, or None if no path exists
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = shortestPath(
                    (u1:User {user_id: $user_id1})-[:FRIENDS_WITH*]-(u2:User {user_id: $user_id2})
                )
                RETURN [node in nodes(path) | {
                    user_id: node.user_id,
                    handle: node.handle,
                    trust_score: node.trust_score
                }] as nodes,
                [rel in relationships(path) | rel.trust_weight] as trust_weights
            """, user_id1=user_id1, user_id2=user_id2)

            record = result.single()
            if record:
                return {
                    "nodes": record["nodes"],
                    "trust_weights": record["trust_weights"],
                    "path_length": len(record["nodes"]) - 1
                }
            return None

    def get_provenance_chain(self, garment_id: str) -> List[Dict]:
        """
        Get full ownership provenance chain.

        Returns:
            Ordered list of ownership events
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (g:Garment {garment_id: $garment_id})
                MATCH path = (g)<-[:OWNS]-(u:User)
                OPTIONAL MATCH (s:Scan)-[:VERIFIED]->(g)
                WHERE (u)-[:SCANNED]->(s)
                RETURN u.user_id as user_id,
                       u.handle as handle,
                       s.timestamp as scan_timestamp,
                       s.cardano_tx_hash as tx_hash
                ORDER BY s.timestamp DESC
            """, garment_id=garment_id)
            return [dict(record) for record in result]

    def find_similar_garments(self, garment_id: str, limit: int = 10) -> List[Dict]:
        """
        Find similar garments using vector similarity.

        Args:
            garment_id: Source garment
            limit: Number of results

        Returns:
            List of similar garments with similarity scores
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (g1:Garment {garment_id: $garment_id})
                CALL db.index.vector.queryNodes('garment_embedding', $limit + 1, g1.embedding)
                YIELD node as g2, score
                WHERE g2.garment_id <> $garment_id
                RETURN g2.garment_id as garment_id,
                       g2.garment_tag as garment_tag,
                       g2.creator_id as creator_id,
                       score as similarity
                ORDER BY score DESC
                LIMIT $limit
            """, garment_id=garment_id, limit=limit)
            return [dict(record) for record in result]

    def get_user_social_graph(self, user_id: str, depth: int = 2) -> Dict:
        """
        Get user's social network up to specified depth.

        Returns:
            Subgraph with nodes and relationships
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (u:User {user_id: $user_id})-[:FRIENDS_WITH*1..$depth]-(friend:User)
                WITH collect(path) as paths
                CALL apoc.convert.toTree(paths) YIELD value
                RETURN value
            """, user_id=user_id, depth=depth)

            record = result.single()
            return record["value"] if record else {}

    # ============================================================
    # Cypher Query Execution (for LLM-generated queries)
    # ============================================================

    def execute_cypher(self, query: str, params: Dict[str, Any] = None) -> List[Dict]:
        """
        Execute arbitrary Cypher query (use with caution).

        Args:
            query: Cypher query string
            params: Query parameters

        Returns:
            List of result records
        """
        with self.driver.session() as session:
            result = session.run(query, **(params or {}))
            return [dict(record) for record in result]


# ============================================================
# Factory Function
# ============================================================

def get_knowledge_graph() -> BrandMeKnowledgeGraph:
    """
    Get knowledge graph instance from environment configuration.
    """
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    return BrandMeKnowledgeGraph(neo4j_uri, neo4j_user, neo4j_password)
