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


def get_pods_to_preempt(
    pending_pods: list[V1Pod],
    running_pods: list[V1Pod],
    num_available_nodes: int,
) -> list[V1Pod]:
    """
    Determine which running pods should be preempted to make room for higher priority pending pods.

    Args:
        pending_pods: List of pending pods that need scheduling
        running_pods: List of currently running pods
        num_available_nodes: Number of nodes available for scheduling

    Returns:
        List of running pods that should be preempted, sorted by priority (lowest first)
    """
    if len(pending_pods) <= num_available_nodes:
        return []

    # Create sorted lists of pods
    # Pending pods sorted by priority (highest first)
    sorted_pending = SortedList(pending_pods, key=lambda p: get_pod_sort_key(p, SortOrder.DESCENDING))
    # Running pods sorted by priority (lowest first)
    sorted_running = SortedList(running_pods, key=lambda p: get_pod_sort_key(p, SortOrder.ASCENDING))

    # Pop the highest priority pending pods that can be scheduled on available nodes
    for _ in range(num_available_nodes):
        if sorted_pending:
            sorted_pending.pop(0)

    pods_to_preempt = []

    # For each remaining pending pod, check if we can preempt a running pod
    while sorted_pending:
        pending_pod = sorted_pending[0]
        pending_priority = get_pod_priority(pending_pod)

        # Find the lowest priority running pod
        if not sorted_running:
            break
        lowest_running = sorted_running[0]
        running_priority = get_pod_priority(lowest_running)

        # If pending pod has strictly higher priority, mark the running pod for preemption
        if pending_priority > running_priority:
            pods_to_preempt.append(lowest_running)
            sorted_running.pop(0)
            sorted_pending.pop(0)
        else:
            # No more preemption possible
            break

    return pods_to_preempt


def schedule(scheduler_name: str, state: NodePodState, preempt: bool = True) -> SchedulingActions:
    """
    Creates scheduling actions by matching pending pods to nodes with matching scheduler name.

    The scheduling logic:
    1. Identifies pending pods that need scheduling
    2. If preemption is enabled:
       a. Sort pending pods by priority (descending)
       b. For each pending pod with higher priority than running pods, evict a running pod
    3. For each available node, creates a binding to assign one pod (using lexicographical ordering)

    Args:
        scheduler_name: Name of the scheduler to match against
        state: Current state of nodes and pods in the cluster
        preempt: Whether to enable preemption of lower priority pods

    Returns:
        SchedulingActions containing the bindings and evictions to be executed
    """
    # Find pending pods that need scheduling
    pending_pods = [
        pod
        for pod in state.pods
        if pod.status and pod.status.phase == "Pending" and pod.spec.scheduler_name == scheduler_name
    ]

    # Find running pods for this scheduler
    running_pods = [
        pod
        for pod in state.pods
        if (
            pod.status
            and pod.status.phase == "Running"
            and pod.spec
            and pod.spec.node_name
            and pod.spec.scheduler_name == scheduler_name
        )
    ]

    # Find nodes that already have pods with this scheduler running
    nodes_with_scheduler_pods = {pod.spec.node_name for pod in running_pods}

    # Get nodes that are available for scheduling (don't have a pod with this scheduler)
    available_nodes = [node for node in state.nodes if node.metadata.name not in nodes_with_scheduler_pods]

    bindings = []
    evictions = []

    # Handle preemption if enabled
    if preempt:
        pods_to_preempt = get_pods_to_preempt(pending_pods, running_pods, len(available_nodes))

        # Create evictions and update available nodes
        for pod in pods_to_preempt:
            evictions.append(create_eviction(state.namespace, pod.metadata.name))
            # Add the node to available nodes
            available_nodes.append(next(n for n in state.nodes if n.metadata.name == pod.spec.node_name))

    # Sort nodes by name, and pending pods by priority and name
    # TODO(snakescott): cleanup, try to avoid using get_pod_sort_key
    available_nodes.sort(key=lambda n: n.metadata.name)
    pending_pods.sort(key=lambda p: get_pod_sort_key(p))

    # Create bindings for each available node (up to the number of pending pods)
    for node, pod in zip(available_nodes, pending_pods, strict=False):
        bindings.append(create_binding(pod.metadata.name, node.metadata.name))

    return SchedulingActions(
        evictions=evictions,
        bindings=bindings,
    )
