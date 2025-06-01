from dataclasses import dataclass
from datetime import datetime

from kubernetes.client import (
    V1Binding,
    V1DeleteOptions,
    V1Eviction,
    V1Node,
    V1ObjectMeta,
    V1ObjectReference,
    V1Pod,
)


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


@dataclass
class SchedulingActions:
    """
    Represents a set of scheduling actions to be taken, including pod evictions and bindings.

    Attributes:
        evictions: List of pod evictions to be executed
        bindings: List of pod bindings to be executed
    """

    evictions: list[V1Eviction]
    bindings: list[V1Binding]


def create_binding(pod_name: str, node_name: str) -> V1Binding:
    """
    Creates a V1Binding object to bind a pod to a specific node.

    Args:
        pod_name: Name of the pod to bind
        node_name: Name of the target node

    Returns:
        A V1Binding object configured to bind the pod to the specified node
    """
    target = V1ObjectReference(kind="Node", api_version="v1", name=node_name)
    meta = V1ObjectMeta(name=pod_name)
    return V1Binding(metadata=meta, target=target)


def create_eviction(namespace: str, pod_name: str) -> V1Eviction:
    """
    Creates a V1Eviction object to evict a pod from a node.

    Args:
        namespace: Namespace where the pod exists
        pod_name: Name of the pod to evict

    Returns:
        A V1Eviction object configured to evict the specified pod
    """
    return V1Eviction(
        api_version="policy/v1",
        kind="Eviction",
        metadata=V1ObjectMeta(
            name=pod_name,
            namespace=namespace,
        ),
        delete_options=V1DeleteOptions(
            grace_period_seconds=0,
        ),
    )


def schedule(scheduler_name: str, state: NodePodState) -> SchedulingActions:
    """
    Creates scheduling actions by matching pending pods to nodes with matching scheduler name.

    The scheduling logic:
    1. Identifies pending pods that need scheduling
    2. For each node that doesn't already have a pod with this scheduler running,
       creates a binding to assign one pod (using lexicographical ordering)

    Args:
        scheduler_name: Name of the scheduler to match against
        state: Current state of nodes and pods in the cluster

    Returns:
        SchedulingActions containing the bindings to be executed
    """

    # Find pending pods that need scheduling
    pending_pods = [
        pod
        for pod in state.pods
        if pod.status and pod.status.phase == "Pending" and pod.spec.scheduler_name == scheduler_name
    ]

    # Find nodes that already have pods with this scheduler running
    nodes_with_scheduler_pods = {
        pod.spec.node_name
        for pod in state.pods
        # TODO(snakescott): is this the right predicate to check?
        if (pod.spec and pod.spec.node_name and pod.spec.scheduler_name == scheduler_name)
    }

    # Get nodes that are available for scheduling (don't have a pod with this scheduler)
    available_nodes = [node for node in state.nodes if node.metadata.name not in nodes_with_scheduler_pods]

    # Sort both lists lexicographically by name
    available_nodes.sort(key=lambda n: n.metadata.name)
    pending_pods.sort(key=lambda p: p.metadata.name)

    # Create bindings for each available node (up to the number of pending pods)
    bindings = []
    for node, pod in zip(available_nodes, pending_pods, strict=False):
        bindings.append(create_binding(pod.metadata.name, node.metadata.name))

    return SchedulingActions(
        evictions=[],  # No evictions in this scheduling pass
        bindings=bindings,
    )
