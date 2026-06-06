import collections
from typing import Dict, List, Set, Tuple, Any, Optional

class Node:
    def __init__(self, node_id: str, node_type: str, properties: Dict[str, Any] = None):
        self.id = node_id  # Unique identifier (e.g., wallet address or token mint)
        self.type = node_type  # 'TraderWallet', 'PumpToken', 'DeveloperWallet'
        self.properties = properties or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "properties": self.properties
        }

class Relationship:
    def __init__(self, start_node: str, end_node: str, rel_type: str, properties: Dict[str, Any] = None):
        self.start_node = start_node
        self.end_node = end_node
        self.type = rel_type  # 'BOUGHT', 'SOLD', 'CREATED', 'TRANSFERRED_SOL'
        self.properties = properties or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_node": self.start_node,
            "end_node": self.end_node,
            "type": self.type,
            "properties": self.properties
        }

class GraphDB:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        # Adjacency lists: source_node -> list of (target_node, relationship)
        self.out_edges: Dict[str, List[Tuple[str, Relationship]]] = collections.defaultdict(list)
        self.in_edges: Dict[str, List[Tuple[str, Relationship]]] = collections.defaultdict(list)

    def add_node(self, node_id: str, node_type: str, properties: Dict[str, Any] = None) -> Node:
        if node_id in self.nodes:
            # Update properties
            self.nodes[node_id].properties.update(properties or {})
        else:
            self.nodes[node_id] = Node(node_id, node_type, properties)
        return self.nodes[node_id]

    def add_relationship(self, start_id: str, end_id: str, rel_type: str, properties: Dict[str, Any] = None) -> Relationship:
        rel = Relationship(start_id, end_id, rel_type, properties)
        self.out_edges[start_id].append((end_id, rel))
        self.in_edges[end_id].append((start_id, rel))
        return rel

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str, rel_type: Optional[str] = None, direction: str = "both") -> List[Tuple[Node, Relationship]]:
        """
        Traverse relationships from a starting node.
        direction: 'out', 'in', or 'both'
        """
        results = []
        if direction in ("out", "both"):
            for target_id, rel in self.out_edges.get(node_id, []):
                if rel_type is None or rel.type == rel_type:
                    target_node = self.nodes.get(target_id)
                    if target_node:
                        results.append((target_node, rel))
        
        if direction in ("in", "both"):
            for source_id, rel in self.in_edges.get(node_id, []):
                if rel_type is None or rel.type == rel_type:
                    source_node = self.nodes.get(source_id)
                    if source_node:
                        results.append((source_node, rel))
        return results

    def get_second_degree_neighbors(self, node_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Returns nodes and relationships within 2 degrees of separation from node_id.
        Useful for graph expansion on double click.
        """
        visited_nodes = {node_id}
        result_nodes = []
        result_rels = []

        start_node = self.get_node(node_id)
        if not start_node:
            return [], []

        result_nodes.append(start_node.to_dict())

        # First degree
        first_deg_ids = set()
        # Outgoing
        for target_id, rel in self.out_edges.get(node_id, []):
            if target_id not in visited_nodes:
                visited_nodes.add(target_id)
                first_deg_ids.add(target_id)
                tgt_node = self.get_node(target_id)
                if tgt_node:
                    result_nodes.append(tgt_node.to_dict())
            result_rels.append(rel.to_dict())

        # Incoming
        for source_id, rel in self.in_edges.get(node_id, []):
            if source_id not in visited_nodes:
                visited_nodes.add(source_id)
                first_deg_ids.add(source_id)
                src_node = self.get_node(source_id)
                if src_node:
                    result_nodes.append(src_node.to_dict())
            result_rels.append(rel.to_dict())

        # Second degree from first degree nodes
        for f_id in first_deg_ids:
            for target_id, rel in self.out_edges.get(f_id, []):
                if target_id not in visited_nodes:
                    visited_nodes.add(target_id)
                    tgt_node = self.get_node(target_id)
                    if tgt_node:
                        result_nodes.append(tgt_node.to_dict())
                # Deduplicate relationships
                rel_dict = rel.to_dict()
                if rel_dict not in result_rels:
                    result_rels.append(rel_dict)

            for source_id, rel in self.in_edges.get(f_id, []):
                if source_id not in visited_nodes:
                    visited_nodes.add(source_id)
                    src_node = self.get_node(source_id)
                    if src_node:
                        result_nodes.append(src_node.to_dict())
                rel_dict = rel.to_dict()
                if rel_dict not in result_rels:
                    result_rels.append(rel_dict)

        return result_nodes, result_rels

    def clear(self):
        self.nodes.clear()
        self.out_edges.clear()
        self.in_edges.clear()
