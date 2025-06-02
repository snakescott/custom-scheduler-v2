from dataclasses import dataclass
from datetime import datetime

from kubernetes.client import (
    V1Binding,
    V1Eviction,
    V1Node,
    V1Pod,
)

from .core_k8s import (
    AVAILABLE_NODE_PRIORITY,
    GROUP_NAME_ANNOTATION,
    create_binding,
    create_eviction,
    get_annotation,
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
    pods: list[V1Pod]  # All pods in the group
    pending_pods: list[V1Pod]  # Only pending pods in the group
    max_priority: int  # Maximum priority of any pod in the group

    @property
    def num_pending(self) -> int:
        """Number of pending pods in the group."""
        return len(self.pending_pods)


def get_pending_pod_groups(all_pods: list[V1Pod]) -> list[PodGroup]:
    """
    Group pods by their group name annotation.
    For pods without a group name, they are treated as single-pod groups.
    The group's priority is the maximum priority of any pod in the group.
    """
    groups: dict[str, tuple[list[V1Pod], list[V1Pod]]] = {}  # (all_pods, pending_pods)

    # First pass: collect pods into their groups
    for pod in all_pods:
        group_name = get_annotation(pod, GROUP_NAME_ANNOTATION)
        if not group_name:
            # Single pod group - use pod name as group name
            group_name = pod.metadata.name

        if group_name not in groups:
            groups[group_name] = ([], [])
        groups[group_name][0].append(pod)  # Add to all pods
        if is_pending(pod):
            groups[group_name][1].append(pod)  # Add to pending pods

    # Convert to PodGroup objects with max priority from all pods
    pending_pod_groups = [
        PodGroup(
            group_name=group_name,
            pods=all_group_pods,
            pending_pods=pending_group_pods,
            max_priority=max(get_pod_priority(pod) for pod in all_group_pods),
        )
        for group_name, (all_group_pods, pending_group_pods) in groups.items()
    ]

    # Sort by sort key
    return sorted(pending_pod_groups, key=lambda g: (-g.max_priority, -g.num_pending, g.group_name))


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
    pending_pod_groups = get_pending_pod_groups(in_scope_pods)
    sorted_nodes = get_sorted_nodes(state.nodes, pending_pod_groups)

    bindings = []
    evictions = []
    next_node_index = 0

    # Process each pod group in order
    for group in pending_pod_groups:
        # First check if we have enough nodes for the entire group
        if next_node_index + len(group.pending_pods) > len(sorted_nodes):
            continue  # Skip this group if we don't have enough nodes

        # Check if the last node needed for this group can be used
        last_node_index = next_node_index + len(group.pending_pods) - 1
        last_node = sorted_nodes[last_node_index]
        if not (last_node.priority == AVAILABLE_NODE_PRIORITY or (preempt and group.max_priority > last_node.priority)):
            continue  # Skip this group if we can't use the last node

        # Schedule all pending pods in the group
        for pod in group.pending_pods:
            pn = sorted_nodes[next_node_index]
            priority, node = pn.priority, pn.node

            bindings.append(create_binding(pod.metadata.name, node.metadata.name))
            if preempt and priority != AVAILABLE_NODE_PRIORITY:
                victim_pod = node_to_running_pod.get(node.metadata.name)
                if victim_pod:
                    evictions.append(create_eviction(state.namespace, victim_pod.metadata.name))
            next_node_index += 1

    return SchedulingActions(
        evictions=evictions,
        bindings=bindings,
    )
