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


def get_annotation(pod: V1Pod, key: str, default: str = "") -> str:
    """Get a pod annotation value, returning default if not present."""
    if not pod.metadata or not pod.metadata.annotations:
        return default
    return pod.metadata.annotations.get(key, default)


@dataclass
class PodGroup:
    """Represents a group of pods that should be scheduled together."""

    group_name: str  # For single pods, this is the pod name
    pods: list[V1Pod]
    max_priority: int  # Maximum priority of pods in the group

    @property
    def size(self) -> int:
        """Number of pods in the group."""
        return len(self.pods)

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """Sort key for the group based on (max_priority, size, group_name)."""
        return (-self.max_priority, -self.size, self.group_name)


def get_pod_groups(pods: list[V1Pod]) -> list[PodGroup]:
    groups: dict[str, list[V1Pod]] = {}

    # First pass: collect pods into their groups
    for pod in pods:
        group_name = get_annotation(pod, GROUP_NAME_ANNOTATION)
        if not group_name:
            # Single pod group - use pod name as group name
            group_name = pod.metadata.name

        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(pod)

    # Convert to PodGroup objects with max_priority calculated during initialization
    pod_groups = [
        PodGroup(group_name=group_name, pods=group_pods, max_priority=max(get_pod_priority(pod) for pod in group_pods))
        for group_name, group_pods in groups.items()
    ]

    # Sort by sort key
    return sorted(pod_groups, key=lambda g: g.sort_key)


def schedule(scheduler_name: str, state: NodePodState, preempt: bool = True) -> SchedulingActions:
    # Get pods managed by this scheduler
    in_scope_pods = [pod for pod in state.pods if pod.spec and pod.spec.scheduler_name == scheduler_name]

    # Find pending pods that need scheduling and group them
    pending_pods = [pod for pod in in_scope_pods if is_pending(pod)]
    pod_groups = get_pod_groups(pending_pods)

    # Find running pods for this scheduler
    running_pods = [pod for pod in in_scope_pods if is_running(pod)]
    node_to_pod = {pod.spec.node_name: pod for pod in running_pods}

    # Get prioritized nodes
    prioritized_nodes = get_prioritized_nodes(state.nodes, running_pods)

    bindings = []
    evictions = []
    next_node_index = 0

    # Process each pod group in order
    for group in pod_groups:
        # First check if we have enough nodes for the entire group
        if next_node_index + len(group.pods) > len(prioritized_nodes):
            continue  # Skip this group if we don't have enough nodes

        # Check if the last node needed for this group can be used
        last_node_index = next_node_index + len(group.pods) - 1
        last_node = prioritized_nodes[last_node_index]
        if not (last_node.priority == AVAILABLE_NODE_PRIORITY or (preempt and group.max_priority > last_node.priority)):
            continue  # Skip this group if we can't use the last node

        # Schedule all pods in the group
        for pod in group.pods:
            pn = prioritized_nodes[next_node_index]
            priority, node = pn.priority, pn.node

            bindings.append(create_binding(pod.metadata.name, node.metadata.name))
            if preempt and priority != AVAILABLE_NODE_PRIORITY:
                victim_pod_name = node_to_pod[node.metadata.name].metadata.name
                evictions.append(create_eviction(state.namespace, victim_pod_name))
            next_node_index += 1

    return SchedulingActions(
        evictions=evictions,
        bindings=bindings,
    )
