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

# Constants for gang scheduling annotations
GROUP_NAME_ANNOTATION = "custom-scheduling.k8s.io/group-name"
MIN_AVAILABLE_ANNOTATION = "custom-scheduling.k8s.io/minAvailable"


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
        _node_by_name: Internal map of node name to node for efficient lookups
    """

    nodes: list[V1Node]
    pods: list[V1Pod]
    namespace: str
    ts: datetime
    _node_by_name: dict[str, V1Node] = None

    def __post_init__(self):
        """Initialize the node lookup map after instance creation."""
        self._node_by_name = {node.metadata.name: node for node in self.nodes}

    def get_node(self, name: str) -> V1Node:
        """Get a node by name, raising KeyError if not found."""
        return self._node_by_name[name]


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
class GangInfo:
    """Information about a gang of pods."""

    group_name: str  # For single pods, this is the pod name
    min_available: int
    pods: list[V1Pod]
    priority: int  # Maximum priority of pods in the gang

    @property
    def is_single_pod(self) -> bool:
        """Whether this gang should be treated as a single pod (min_available <= 1)."""
        return self.min_available <= 1


@dataclass
class GangSchedulingResult:
    """Result of processing a gang for scheduling."""

    bindings: list[V1Binding]
    evictions: list[V1Eviction]
    available_nodes: list[V1Node]
    running_pods: list[V1Pod]


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


def is_pending(pod: V1Pod) -> bool:
    """Check if a pod is in the Pending phase."""
    return pod.status and pod.status.phase == "Pending"


def is_running(pod: V1Pod) -> bool:
    """Check if a pod is in the Running phase and has a node assigned."""
    return pod.status and pod.status.phase == "Running" and pod.spec and pod.spec.node_name


def get_annotation(pod: V1Pod, key: str, default: str = "") -> str:
    """Get a pod annotation value, returning default if not present."""
    if not pod.metadata or not pod.metadata.annotations:
        return default
    return pod.metadata.annotations.get(key, default)


def get_gang_info(pods: list[V1Pod]) -> dict[str, GangInfo]:
    """
    Get gang information for a list of pods, grouping them by their group name.
    For pods without a group name, they are treated as single-pod gangs.

    Args:
        pods: List of pods to group into gangs

    Returns:
        Dictionary mapping group names to GangInfo objects
    """
    gangs: dict[str, GangInfo] = {}

    # First pass: collect pods into their groups
    for pod in pods:
        group_name = get_annotation(pod, GROUP_NAME_ANNOTATION)
        if not group_name:
            # Single pod gang - use pod name as group name
            group_name = pod.metadata.name

        if group_name not in gangs:
            gangs[group_name] = GangInfo(
                group_name=group_name,
                min_available=0,  # Will be updated in second pass
                pods=[],
                priority=0,  # Will be updated in second pass
            )
        gangs[group_name].pods.append(pod)

    # Second pass: calculate min_available and priority for each gang
    for gang in gangs.values():
        # min_available is the maximum min_available value across all pods in the gang
        gang.min_available = max(int(get_annotation(pod, MIN_AVAILABLE_ANNOTATION, "1")) for pod in gang.pods)
        # priority is the maximum priority across all pods in the gang
        gang.priority = max(get_pod_priority(pod) for pod in gang.pods)

    return gangs


def get_gang_sort_key(gang: GangInfo, order: SortOrder = SortOrder.DESCENDING) -> tuple[int, bool, int, str]:
    """
    Get the sort key for a gang based on priority, gang status, min size, and name.

    Args:
        gang: The gang to get a sort key for
        order: Sort order (ascending/descending)

    Returns:
        Tuple of (priority, is_gang, min_size, group_name) for sorting
    """
    priority = -gang.priority if order == SortOrder.DESCENDING else gang.priority
    # For sorting: gangs (except single pods) come before regular pods
    is_gang = not gang.is_single_pod
    return (priority, is_gang, gang.min_available, gang.group_name)


def process_gang(
    gang: GangInfo,
    available_nodes: list[V1Node],
    running_pods: list[V1Pod],
    state: NodePodState,
    preempt: bool,
) -> GangSchedulingResult:
    """
    Process a single gang for scheduling, handling evictions and bindings in one shot.

    This function takes a snapshot of the current cluster state (nodes and pods) and returns
    a new state after attempting to schedule the gang. The function makes a copy of the
    input state to avoid modifying it unless the gang is successfully scheduled.

    Args:
        gang: The gang to process
        available_nodes: Current list of available nodes (nodes without pods from this scheduler)
        running_pods: Current list of running pods managed by this scheduler
        state: Current cluster state, used for node lookups
        preempt: Whether preemption is enabled

    Returns:
        GangSchedulingResult containing:
        - bindings: New bindings created for this gang
        - evictions: Evictions needed to make room for this gang
        - available_nodes: Updated list of available nodes after scheduling this gang
        - running_pods: Updated list of running pods after scheduling this gang

        If the gang cannot be scheduled (e.g., not enough nodes + evictable pods to meet
        min_available), returns empty bindings/evictions and the original node/pod lists.
    """
    # Create a constant for when scheduling is not possible
    EMPTY_SCHEDULE_RESULT = GangSchedulingResult([], [], available_nodes, running_pods)

    # Make copies of the input state to avoid modifying it unless we successfully schedule
    bindings = []
    evictions = []
    # Convert lists to dictionaries mapping names to objects
    available_nodes = {node.metadata.name: node for node in available_nodes}
    running_pods = {pod.metadata.name: pod for pod in running_pods}

    # Get pending pods from this gang
    pending_gang_pods = [p for p in gang.pods if is_pending(p)]
    if not pending_gang_pods:
        return EMPTY_SCHEDULE_RESULT

    # Count how many pods in this gang are already running
    running_gang_pods = sum(1 for pod in gang.pods if pod.metadata.name in running_pods)

    # Calculate how many more pods we need to schedule
    pods_to_schedule = min(
        len(pending_gang_pods),  # Number of pending pods in the gang
        gang.min_available - running_gang_pods,  # How many more we need to meet min_available
    )

    if pods_to_schedule <= 0:
        return GangSchedulingResult(bindings, evictions, list(available_nodes.values()), list(running_pods.values()))

    # Check if we have enough nodes + potential evictions to schedule the gang
    if preempt:
        # Sort running pods by priority (lowest first) for preemption
        sorted_running = sorted(running_pods.values(), key=lambda p: (get_pod_priority(p), p.metadata.name))

        # Calculate how many more nodes we need
        needed_nodes = pods_to_schedule - len(available_nodes)

        if needed_nodes > 0:
            # Try to find pods to preempt
            pods_to_preempt = []
            for _ in range(needed_nodes):
                if not sorted_running:
                    # Not enough nodes + evictable pods to schedule the gang
                    return EMPTY_SCHEDULE_RESULT

                lowest_running = sorted_running[0]
                if get_pod_priority(lowest_running) >= gang.priority:
                    # Can't preempt pods with equal or higher priority
                    return EMPTY_SCHEDULE_RESULT

                pods_to_preempt.append(lowest_running)
                sorted_running.pop(0)

            # Create evictions and update available nodes
            for pod in pods_to_preempt:
                evictions.append(create_eviction(state.namespace, pod.metadata.name))
                available_nodes[pod.spec.node_name] = state.get_node(pod.spec.node_name)
                del running_pods[pod.metadata.name]

    # If we still don't have enough nodes, we can't schedule the gang
    if len(available_nodes) < pods_to_schedule:
        return EMPTY_SCHEDULE_RESULT

    # Create bindings for the gang
    available_node_list = list(available_nodes.values())
    for node, pod in zip(available_node_list[:pods_to_schedule], pending_gang_pods[:pods_to_schedule], strict=False):
        bindings.append(create_binding(pod.metadata.name, node.metadata.name))
        running_pods[pod.metadata.name] = pod  # Add to running pods
        del available_nodes[node.metadata.name]  # Remove used node

    # Return updated state
    return GangSchedulingResult(
        bindings=bindings,
        evictions=evictions,
        available_nodes=list(available_nodes.values()),
        running_pods=list(running_pods.values()),
    )


def get_evictable_gangs_by_priority(running_pods: list[V1Pod]) -> dict[int, int]:
    """
    Calculate the number of evictable gangs for each priority level.
    For each priority P, returns the number of running gangs with priority < P.
    A gang is a group of pods with the same group name annotation.

    Args:
        running_pods: List of running pods to analyze

    Returns:
        Dictionary mapping each priority to the number of gangs that could be evicted
        (gangs with lower priority)
    """
    # Group pods into gangs
    gangs = get_gang_info(running_pods)

    # Sort gangs by descending priority for O(n log n) calculation
    sorted_gangs = sorted(gangs.values(), key=lambda g: (-g.priority, g.group_name))

    # Calculate evictable gangs using a running sum
    evictable_gangs_by_priority = {}
    current_priority = None
    count_below_current = 0
    for gang in sorted_gangs:
        if gang.priority != current_priority:
            # Store count for previous priority
            if current_priority is not None:
                evictable_gangs_by_priority[current_priority] = count_below_current
            current_priority = gang.priority
        count_below_current += 1

    # Store count for the last priority
    if current_priority is not None:
        evictable_gangs_by_priority[current_priority] = count_below_current

    return evictable_gangs_by_priority


def schedule(scheduler_name: str, state: NodePodState, preempt: bool = True) -> SchedulingActions:
    """
    Creates scheduling actions by matching pending pods to nodes with matching scheduler name.

    The scheduling logic:
    1. Identifies pending pods that need scheduling
    2. Groups all pods into gangs based on their group name
    3. Processes each gang in priority order:
       - If preemption is enabled, evicts lower priority pods if needed
       - Creates bindings for the gang's pods
       - Only proceeds if the gang can be fully scheduled
    4. Updates available nodes and running pods as each gang is processed

    Args:
        scheduler_name: Name of the scheduler to match against
        state: Current state of nodes and pods in the cluster
        preempt: Whether to enable preemption of lower priority pods

    Returns:
        SchedulingActions containing the bindings and evictions to be executed
    """
    in_scope_pods = [pod for pod in state.pods if pod.spec.scheduler_name == scheduler_name]

    # Find running pods for this scheduler
    running_pods = [pod for pod in in_scope_pods if is_running(pod)]

    # Group all pods into gangs
    all_gangs = get_gang_info(in_scope_pods)

    # Filter gangs to only those with pending pods
    pending_gangs = [gang for gang in all_gangs.values() if any(is_pending(pod) for pod in gang.pods)]

    # Find nodes that already have pods with this scheduler running
    nodes_with_scheduler_pods = {pod.spec.node_name for pod in running_pods}

    # Get nodes that are available for scheduling (don't have a pod with this scheduler)
    available_nodes = [node for node in state.nodes if node.metadata.name not in nodes_with_scheduler_pods]

    # Sort nodes by name
    available_nodes.sort(key=lambda n: n.metadata.name)

    # Calculate number of evictable gangs per priority
    # evictable_gangs_by_priority = get_evictable_gangs_by_priority(running_pods) if preempt else {}

    # Sort gangs for scheduling
    pending_gangs.sort(key=lambda g: get_gang_sort_key(g))

    # Process each gang in priority order
    all_bindings = []
    all_evictions = []
    current_nodes = available_nodes
    current_pods = running_pods

    for gang in pending_gangs:
        result = process_gang(gang, current_nodes, current_pods, state, preempt)
        if result.bindings:  # Only update state if the gang was scheduled
            all_bindings.extend(result.bindings)
            all_evictions.extend(result.evictions)
            current_nodes = result.available_nodes
            current_pods = result.running_pods

    return SchedulingActions(
        evictions=all_evictions,
        bindings=all_bindings,
    )
