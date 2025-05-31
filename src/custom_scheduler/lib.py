from dataclasses import dataclass
from datetime import datetime

from kubernetes.client import V1Node, V1Pod


@dataclass
class NodePodState:
    """
    Represents the state of nodes and pods in a Kubernetes cluster at a specific time.
    
    Attributes:
        nodes: List of Kubernetes nodes
        pods: List of Kubernetes pods
        namespace: The namespace these resources belong to
        ts: Timestamp when this state was captured
    """
    nodes: list[V1Node]
    pods: list[V1Pod]
    namespace: str
    ts: datetime

    def summary(self) -> str:
        """
        Returns a summary of the current state including timestamp, node count, and pod count.
        
        Returns:
            A formatted string containing the state summary
        """
        return (
            f"State at {self.ts.isoformat()}\n"
            f"Namespace: {self.namespace}\n"
            f"Nodes: {len(self.nodes)}\n"
            f"Pods: {len(self.pods)}"
        ) 