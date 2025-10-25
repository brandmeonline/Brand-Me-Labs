"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Graph RAG (Retrieval-Augmented Generation)
===========================================
Natural language querying of Brand.Me knowledge graph
"""

from typing import List, Dict, Any, Optional
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage
import openai
import numpy as np
import logging

from .graph_db import BrandMeKnowledgeGraph, get_knowledge_graph

logger = logging.getLogger(__name__)


class GraphRAG:
    """
    Graph RAG system for Brand.Me knowledge graph.

    Pipeline:
    1. Natural language question → Vector embedding
    2. Vector search for relevant entities
    3. Expand to subgraph context
    4. Generate Cypher query
    5. Execute query
    6. Synthesize answer with LLM
    """

    def __init__(
        self,
        graph_db: Optional[BrandMeKnowledgeGraph] = None,
        llm_model: str = "claude-3-5-sonnet-20241022"
    ):
        self.graph = graph_db or get_knowledge_graph()
        self.llm = ChatAnthropic(model=llm_model, temperature=0)
        self.openai_client = openai.Client()

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text"""
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

    def query(
        self,
        question: str,
        include_reasoning: bool = False,
        max_context_entities: int = 10
    ) -> Dict[str, Any]:
        """
        Answer question using knowledge graph.

        Args:
            question: Natural language question
            include_reasoning: Include reasoning steps in response
            max_context_entities: Max entities to include in context

        Returns:
            {
                "answer": str,
                "context": dict,
                "sources": list,
                "reasoning": str (optional)
            }
        """
        reasoning_steps = []

        # Step 1: Generate embedding for question
        question_embedding = self.generate_embedding(question)
        reasoning_steps.append(f"Generated embedding for question: {question}")

        # Step 2: Classify question type
        question_type = self._classify_question(question)
        reasoning_steps.append(f"Classified as: {question_type}")

        # Step 3: Generate Cypher query
        cypher_query = self._generate_cypher_query(question, question_type)
        reasoning_steps.append(f"Generated Cypher: {cypher_query}")

        # Step 4: Execute query
        try:
            query_results = self.graph.execute_cypher(cypher_query)
            reasoning_steps.append(f"Query returned {len(query_results)} results")
        except Exception as e:
            logger.error(f"Cypher query failed: {e}")
            reasoning_steps.append(f"Query failed: {e}")
            query_results = []

        # Step 5: Gather additional context if needed
        context = self._gather_context(question, question_type, query_results)
        reasoning_steps.append(f"Gathered context with {len(context.get('entities', []))} entities")

        # Step 6: Synthesize answer
        answer = self._synthesize_answer(question, query_results, context)
        reasoning_steps.append("Synthesized final answer")

        result = {
            "answer": answer,
            "context": context,
            "sources": query_results,
            "cypher_query": cypher_query
        }

        if include_reasoning:
            result["reasoning"] = "\n".join(reasoning_steps)

        return result

    def _classify_question(self, question: str) -> str:
        """
        Classify question type to guide query generation.

        Types:
        - provenance: Ownership history, creator attribution
        - relationship: User connections, trust paths
        - similarity: Find similar garments
        - verification: Authenticity, blockchain verification
        - policy: Compliance, regional rules
        - analytics: Patterns, trends, insights
        """
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""Classify the question into one of these categories:
            - provenance: About ownership history, creator, origin
            - relationship: About user connections, friends, trust
            - similarity: Finding similar garments or entities
            - verification: About authenticity, blockchain, proofs
            - policy: About compliance, policies, rules
            - analytics: About patterns, trends, statistics

            Respond with just the category name."""),
            HumanMessage(content=question)
        ])

        response = self.llm.invoke(prompt.format_messages())
        return response.content.strip().lower()

    def _generate_cypher_query(self, question: str, question_type: str) -> str:
        """
        Generate Cypher query from natural language question.

        Uses LLM with few-shot examples to translate NL → Cypher
        """
        examples = {
            "provenance": """
            Example 1:
            Question: "What's the ownership history of garment-123?"
            Cypher: MATCH (g:Garment {garment_id: 'garment-123'})<-[:OWNS]-(u:User)
                   OPTIONAL MATCH (s:Scan)-[:VERIFIED]->(g)
                   WHERE (u)-[:SCANNED]->(s)
                   RETURN u.handle, s.timestamp, s.cardano_tx_hash
                   ORDER BY s.timestamp DESC

            Example 2:
            Question: "Who created this garment?"
            Cypher: MATCH (g:Garment {garment_id: $garment_id})-[:CREATED_BY]->(c:Creator)
                   RETURN c.creator_name, c.brand, c.reputation_score
            """,
            "relationship": """
            Example 1:
            Question: "Are user-1 and user-2 friends?"
            Cypher: MATCH (u1:User {user_id: 'user-1'})-[:FRIENDS_WITH]-(u2:User {user_id: 'user-2'})
                   RETURN u1.handle, u2.handle, 'Yes' as are_friends

            Example 2:
            Question: "What's the trust path between Alice and Bob?"
            Cypher: MATCH path = shortestPath(
                       (u1:User {handle: 'Alice'})-[:FRIENDS_WITH*]-(u2:User {handle: 'Bob'})
                   )
                   RETURN [n in nodes(path) | n.handle] as path
            """,
            "similarity": """
            Example: "Find garments similar to garment-123"
            Cypher: MATCH (g1:Garment {garment_id: 'garment-123'})
                   CALL db.index.vector.queryNodes('garment_embedding', 10, g1.embedding)
                   YIELD node as g2, score
                   WHERE g2.garment_id <> 'garment-123'
                   RETURN g2.garment_id, g2.garment_tag, score
                   ORDER BY score DESC
            """
        }

        example_text = examples.get(question_type, "")

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""You are a Cypher query generator for a Neo4j knowledge graph.

            Graph schema:
            - Nodes: User, Garment, Creator, Brand, Scan, Policy
            - Relationships: OWNS, SCANNED, FRIENDS_WITH, CREATED_BY, VERIFIED, ENFORCED_BY

            {example_text}

            Generate a Cypher query to answer the question. Return ONLY the Cypher query, no explanation.
            """),
            HumanMessage(content=question)
        ])

        response = self.llm.invoke(prompt.format_messages())
        return response.content.strip()

    def _gather_context(
        self,
        question: str,
        question_type: str,
        query_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        Gather additional context around query results.

        Expands to related entities for richer context.
        """
        context = {
            "entities": [],
            "relationships": [],
            "metadata": {"question_type": question_type}
        }

        if not query_results:
            return context

        # Extract entity IDs from results
        entity_ids = []
        for result in query_results:
            for key, value in result.items():
                if key.endswith("_id") and isinstance(value, str):
                    entity_ids.append(value)

        # Get related entities
        # (In production, implement more sophisticated context expansion)
        context["entities"] = entity_ids[:10]  # Limit context size

        return context

    def _synthesize_answer(
        self,
        question: str,
        query_results: List[Dict],
        context: Dict[str, Any]
    ) -> str:
        """
        Synthesize natural language answer from query results.

        Uses LLM to convert structured data → conversational answer
        """
        if not query_results:
            return "I couldn't find any information to answer that question."

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a helpful assistant for the Brand.Me platform.

            Given the query results from the knowledge graph, provide a clear, concise answer to the user's question.

            Guidelines:
            - Be accurate and factual
            - Use natural language
            - Cite specific data points
            - If uncertain, say so
            - Keep it concise (2-3 sentences)
            """),
            HumanMessage(content=f"""Question: {question}

            Query Results:
            {query_results}

            Context:
            {context}

            Answer:""")
        ])

        response = self.llm.invoke(prompt.format_messages())
        return response.content.strip()

    # ============================================================
    # Specialized Query Functions
    # ============================================================

    def get_garment_provenance(self, garment_id: str) -> Dict[str, Any]:
        """
        Get full provenance story for garment.

        Returns rich narrative with creator, ownership history, verifications.
        """
        # Get provenance chain
        chain = self.graph.get_provenance_chain(garment_id)

        # Get creator info
        creator_query = """
        MATCH (g:Garment {garment_id: $garment_id})-[:CREATED_BY]->(c:Creator)-[:WORKS_FOR]->(b:Brand)
        RETURN c.creator_name, c.reputation_score, b.brand_name, b.esg_score
        """
        creator_info = self.graph.execute_cypher(creator_query, {"garment_id": garment_id})

        # Synthesize narrative
        question = f"Tell me the complete provenance story of garment {garment_id}"
        answer = self._synthesize_answer(
            question,
            chain + creator_info,
            {"type": "provenance", "garment_id": garment_id}
        )

        return {
            "answer": answer,
            "ownership_chain": chain,
            "creator": creator_info[0] if creator_info else None,
            "blockchain_verified": all(event.get("tx_hash") for event in chain)
        }

    def find_trust_connection(self, user_id1: str, user_id2: str) -> Dict[str, Any]:
        """
        Find and explain trust connection between users.
        """
        path = self.graph.find_trust_path(user_id1, user_id2)

        if not path:
            return {
                "answer": f"No trust path found between {user_id1} and {user_id2}",
                "connected": False
            }

        # Calculate aggregate trust score
        trust_weights = path["trust_weights"]
        aggregate_trust = np.prod(trust_weights) if trust_weights else 0

        answer = f"Found a trust path of length {path['path_length']} with aggregate trust score {aggregate_trust:.2f}. "
        answer += f"The path connects through: {' → '.join([n['handle'] for n in path['nodes']])}"

        return {
            "answer": answer,
            "connected": True,
            "path": path,
            "aggregate_trust": aggregate_trust
        }


# ============================================================
# Factory Function
# ============================================================

def get_graph_rag() -> GraphRAG:
    """Get GraphRAG instance"""
    return GraphRAG()
