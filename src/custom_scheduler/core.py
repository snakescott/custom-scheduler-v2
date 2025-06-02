from dataclasses import dataclass
from datetime import datetime
from itertools import chain

from kubernetes.client import (
    V1Binding,
    V1Eviction,
    V1Node,
    V1Pod,
)

from .core_k8s import (
    AVAILABLE_NODE_PRIORITY,
    create_binding,
    create_eviction,
    get_group_name,
    get_min_available,
    get_pod_priority,
    is_pending,
    is_running,
)


@dataclass
class NodePodState:
    nodes: list[V1Node]
    pods: list[V1Pod]
    namespace: str
    ts: datetime


@dataclass
class SchedulingActions:
    evictions: list[V1Eviction]
    bindings: list[V1Binding]


@dataclass
class NodeAndPriority:
    node: V1Node
    priority: int


@dataclass
class PodGroup:
    """Represents a group of pods that should be scheduled together."""

    group_name: str  # For single pods, this is the pod name
    running_pods: list[V1Pod]  # All pods in the group
    pending_pods: list[V1Pod]  # Only pending pods in the group
    max_priority: int  # Maximum priority of any pod in the group
    min_available: int

    @property
    def num_pending(self) -> int:
        """Number of pending pods in the group."""
        return len(self.pending_pods)

    @property
    def pods(self) -> list[V1Pod]:
        return chain(self.running_pods, self.pending_pods)


def get_pod_groups(all_pods: list[V1Pod]) -> list[PodGroup]:
    """
    Group pods by their group name annotation.
    For pods without a group name, they are treated as single-pod groups.
    The group's priority is the maximum priority of any pod in the group.
    """
    groups: dict[str, tuple[list[V1Pod], list[V1Pod]]] = {}  # (all_pods, pending_pods)

    # First pass: collect pods into their groups
    for pod in all_pods:
        group_name = get_group_name(pod)
        if not group_name:
            # Single pod group - use pod name as group name
            group_name = pod.metadata.name

        if group_name not in groups:
            groups[group_name] = ([], [])
        # Add to all pods
        if is_pending(pod):
            groups[group_name][1].append(pod)
        elif is_running(pod):
            groups[group_name][0].append(pod)

    # Convert to PodGroup objects with max priority from all pods
    pod_groups = [
        PodGroup(
            group_name=group_name,
            running_pods=running_group_pods,
            pending_pods=pending_group_pods,
            max_priority=max(get_pod_priority(pod) for pod in chain(running_group_pods, pending_group_pods)),
            min_available=max(get_min_available(pod) for pod in pending_group_pods) if pending_group_pods else 1,
        )
        for group_name, (running_group_pods, pending_group_pods) in groups.items()
    ]

    # Sort by sort key
    return sorted(pod_groups, key=lambda g: (-g.max_priority, -g.num_pending, g.group_name))


def get_sorted_nodes(nodes: list[V1Node], pod_groups: list[PodGroup]) -> list[NodeAndPriority]:
    # Create a map of pod names to their group priorities
    pod_to_group_priority: dict[str, int] = {}
    for group in pod_groups:
        for pod in group.pods:
            pod_to_group_priority[pod.metadata.name] = group.max_priority

    # Create a map of node names to their running pod priorities
    node_priorities: dict[str, int] = {}
    running_pods = (pod for group in pod_groups for pod in group.pods if is_running(pod))
    for pod in running_pods:
        node_name = pod.spec.node_name
        if node_name:
            # Use the pod's group priority, which is present even for single pod groups
            node_priorities[node_name] = pod_to_group_priority[pod.metadata.name]

    return sorted(
        [
            NodeAndPriority(node=node, priority=node_priorities.get(node.metadata.name, AVAILABLE_NODE_PRIORITY))
            for node in nodes
        ],
        key=lambda n: (n.priority, n.node.metadata.name),
    )


def schedule(scheduler_name: str, state: NodePodState, preempt: bool = True) -> SchedulingActions:
    # Get pods managed by this scheduler
    in_scope_pods = [pod for pod in state.pods if pod.spec and pod.spec.scheduler_name == scheduler_name]
    node_to_running_pod = {pod.spec.node_name: pod for pod in in_scope_pods if is_running(pod)}
    pod_groups = get_pod_groups(in_scope_pods)
    sorted_nodes = get_sorted_nodes(state.nodes, pod_groups)

    bindings = []
    evictions = []
    next_node_index = 0

    # Process each pod group in order
    for group in pod_groups:
        num_running = len(group.running_pods)
        min_available = group.min_available
        num_pending = len(group.pending_pods)

        # Calculate how many more pods need to be scheduled to meet minAvailable
        min_to_schedule = max(0, min_available - num_running)

        # If we can't schedule at least min_to_schedule pods, skip this group
        if min_to_schedule > 0 and next_node_index + min_to_schedule > len(sorted_nodes):
            continue

        # Check if we can use the last node needed for min_to_schedule pods
        if min_to_schedule > 0:
            last_node_index = next_node_index + min_to_schedule - 1
            last_node = sorted_nodes[last_node_index]
            if not (
                last_node.priority == AVAILABLE_NODE_PRIORITY or (preempt and group.max_priority > last_node.priority)
            ):
                continue  # Skip this group if we can't meet minAvailable

        # Try to schedule as many pending pods as possible
        pods_scheduled = 0
        for i in range(min(num_pending, len(sorted_nodes) - next_node_index)):
            pn = sorted_nodes[next_node_index + i]
            priority, node = pn.priority, pn.node

            # Check if we can use this node
            if not (priority == AVAILABLE_NODE_PRIORITY or (preempt and group.max_priority > priority)):
                break

            bindings.append(create_binding(group.pending_pods[i].metadata.name, node.metadata.name))
            if preempt and priority != AVAILABLE_NODE_PRIORITY:
                victim_pod = node_to_running_pod.get(node.metadata.name)
                if victim_pod:
                    evictions.append(create_eviction(state.namespace, victim_pod.metadata.name))
            pods_scheduled += 1

        # Update next_node_index based on how many pods we actually scheduled
        next_node_index += pods_scheduled

    return SchedulingActions(
        evictions=evictions,
        bindings=bindings,
    )
