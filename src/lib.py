from dataclasses import dataclass
from datetime import datetime
from typing import List

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
    nodes: List[V1Node]
    pods: List[V1Pod]
    namespace: str
    ts: datetime 