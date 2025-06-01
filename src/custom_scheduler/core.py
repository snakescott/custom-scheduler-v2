from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from kubernetes.client import (
    V1Binding,
    V1DeleteOptions,
    V1Eviction,
    V1Node,
    V1ObjectMeta,
    V1ObjectReference,
    V1Pod,
)
from sortedcontainers import SortedList

GROUP_NAME_ANNOTATION = "custom-scheduling.k8s.io/group-name"
AVAILABLE_NODE_PRIORITY = -2147483649


def is_pending(pod: V1Pod) -> bool:
    return pod.status and pod.status.phase == "Pending"


def is_running(pod: V1Pod) -> bool:
    return pod.status and pod.status.phase == "Running" and pod.spec and pod.spec.node_name is not None


class SortOrder(Enum):
    """Enum for specifying sort order."""

    ASCENDING = 1  # Lowest values first
    DESCENDING = 2  # Highest values first


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


@dataclass
class PrioritizedNode:
    """
    Represents a node with an associated priority value.

    Attributes:
        node: The Kubernetes node
        priority: The priority value for this node (higher values are more important)
    """

    node: V1Node
    priority: int


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


def get_pod_priority(pod: V1Pod) -> int:
    """Get the priority of a pod, defaulting to 0 if not specified."""
    return pod.spec.priority if pod.spec and hasattr(pod.spec, "priority") else 0


def get_pod_sort_key(pod: V1Pod, order: SortOrder = SortOrder.DESCENDING) -> tuple[int, str]:
    """Get the sort key for a pod based on priority and name."""
    priority = get_pod_priority(pod)
    return (-priority if order == SortOrder.DESCENDING else priority, pod.metadata.name)


def get_prioritized_nodes(nodes: list[V1Node], running_pods: list[V1Pod]) -> SortedList[PrioritizedNode]:
    # Create a map of node names to their running pod priorities
    node_priorities: dict[str, int] = {}
    for pod in running_pods:
        node_name = pod.spec.node_name
        if node_name:
            node_priorities[node_name] = get_pod_priority(pod)

    return SortedList(
        [
            PrioritizedNode(node=node, priority=node_priorities.get(node.metadata.name, AVAILABLE_NODE_PRIORITY))
            for node in nodes
        ],
        key=lambda n: (n.priority, n.node.metadata.name),
    )


def schedule(scheduler_name: str, state: NodePodState, preempt: bool = True) -> SchedulingActions:
    # Get pods managed by this scheduler
    in_scope_pods = [pod for pod in state.pods if pod.spec and pod.spec.scheduler_name == scheduler_name]

    # Find pending pods that need scheduling
    pending_pods = [pod for pod in in_scope_pods if is_pending(pod)]
    pending_pods.sort(key=lambda p: get_pod_sort_key(p))

    # Find running pods for this scheduler
    running_pods = [pod for pod in in_scope_pods if is_running(pod)]
    node_to_pod = {pod.spec.node_name: pod for pod in running_pods}

    # Get prioritized nodes
    prioritized_nodes = get_prioritized_nodes(state.nodes, running_pods)

    bindings = []
    evictions = []

    for pod, pn in zip(pending_pods, prioritized_nodes, strict=False):
        priority, node = pn.priority, pn.node
        if priority == AVAILABLE_NODE_PRIORITY or (preempt and get_pod_priority(pod) > priority):
            bindings.append(create_binding(pod.metadata.name, node.metadata.name))
            if preempt and priority != AVAILABLE_NODE_PRIORITY:
                victim_pod_name = node_to_pod[node.metadata.name].metadata.name
                evictions.append(create_eviction(state.namespace, victim_pod_name))
        else:
            break

    return SchedulingActions(
        evictions=evictions,
        bindings=bindings,
    )
