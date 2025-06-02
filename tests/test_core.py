from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from kubernetes.client import V1Node, V1NodeSpec, V1ObjectMeta, V1Pod, V1PodSpec, V1PodStatus

from custom_scheduler.core import NodePodState, SchedulingActions, schedule


def create_test_node(name: str) -> V1Node:
    """Create a test node with the given name."""
    node = Mock(spec=V1Node)
    node.metadata.name = name
    node.spec = Mock(spec=V1NodeSpec)
    return node


def create_test_pod(
    name: str,
    scheduler_name: str | None = None,
    node_name: str | None = None,
    phase: str = "Pending",
    priority: int = 0,
    group_name: str | None = None,
) -> V1Pod:
    """Create a test pod with the given properties."""
    pod = Mock(spec=V1Pod)
    pod.metadata = Mock(spec=V1ObjectMeta)
    pod.metadata.name = name
    pod.metadata.annotations = {"custom-scheduling.k8s.io/group-name": group_name} if group_name else {}

    pod.spec = Mock(spec=V1PodSpec)
    pod.spec.scheduler_name = scheduler_name
    pod.spec.node_name = node_name
    pod.spec.priority = priority

    pod.status = Mock(spec=V1PodStatus)
    pod.status.phase = phase
    return pod


@pytest.fixture
def mock_node() -> V1Node:
    """Create a mock V1Node for testing."""
    node = Mock(spec=V1Node)
    node.metadata.name = "test-node"
    return node


@pytest.fixture
def mock_pod() -> V1Pod:
    """Create a mock V1Pod for testing."""
    pod = Mock(spec=V1Pod)
    pod.metadata.name = "test-pod"
    return pod


@pytest.fixture
def fixed_time() -> datetime:
    """Return a fixed datetime for testing."""
    return datetime(2024, 3, 14, 15, 30, 45, 123456, tzinfo=UTC)


@pytest.mark.unit
def test_node_pod_state_initialization(mock_node: V1Node, mock_pod: V1Pod, fixed_time: datetime):
    """Test that NodePodState initializes correctly with all fields."""
    state = NodePodState(nodes=[mock_node], pods=[mock_pod], namespace="test-namespace", ts=fixed_time)

    assert state.nodes == [mock_node]
    assert state.pods == [mock_pod]
    assert state.namespace == "test-namespace"
    assert state.ts == fixed_time


@pytest.mark.unit
def test_schedule_empty_state(fixed_time: datetime):
    """Test schedule function with empty state."""
    state = NodePodState(nodes=[], pods=[], namespace="test-namespace", ts=fixed_time)
    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 0


@pytest.mark.unit
def test_schedule_mixed_pods(
    fixed_time: datetime,
):
    """Test schedule function with a mix of pods with different scheduler names."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")
    node_c = create_test_node("node-c")

    # Create pods with different scheduler names and states
    pod1 = create_test_pod("pod1", "test-scheduler")  # Should be scheduled
    pod2 = create_test_pod("pod2", "other-scheduler")  # Should not be scheduled
    pod3 = create_test_pod("pod3", "test-scheduler")  # Should be scheduled
    pod4 = create_test_pod("pod4", None)  # Should not be scheduled
    pod5 = create_test_pod("pod5", "test-scheduler", "node-a", "Running")  # Already running

    state = NodePodState(
        nodes=[node_a, node_b, node_c],
        pods=[pod1, pod2, pod3, pod4, pod5],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 2

    binding = actions.bindings[0]
    assert binding.metadata.name == "pod1"
    assert binding.target.name == "node-b"

    binding = actions.bindings[1]
    assert binding.metadata.name == "pod3"
    assert binding.target.name == "node-c"


@pytest.mark.unit
def test_schedule_all_nodes_occupied(
    fixed_time: datetime,
):
    """Test schedule function when all nodes already have pods assigned."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")

    # Create pods, all already running on nodes
    pod1 = create_test_pod("pod1", "test-scheduler", "node-a", "Running")
    pod2 = create_test_pod("pod2", "test-scheduler", "node-b", "Running")
    pod3 = create_test_pod("pod3", "test-scheduler")  # Pending pod that can't be scheduled

    state = NodePodState(
        nodes=[node_a, node_b],
        pods=[pod1, pod2, pod3],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 0  # No bindings because all nodes are occupied


@pytest.mark.unit
def test_schedule_lexicographical_ordering(
    fixed_time: datetime,
):
    """Test that schedule function respects lexicographical ordering of pods and nodes."""
    # Create nodes in non-alphabetical order
    node_z = create_test_node("node-z")
    node_a = create_test_node("node-a")
    node_m = create_test_node("node-m")

    # Create pods in non-alphabetical order
    pod_z = create_test_pod("pod-z", "test-scheduler")
    pod_a = create_test_pod("pod-a", "test-scheduler")
    pod_m = create_test_pod("pod-m", "test-scheduler")

    state = NodePodState(
        nodes=[node_z, node_a, node_m],
        pods=[pod_z, pod_a, pod_m],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 3

    # Verify bindings are in lexicographical order
    assert actions.bindings[0].metadata.name == "pod-a"
    assert actions.bindings[0].target.name == "node-a"
    assert actions.bindings[1].metadata.name == "pod-m"
    assert actions.bindings[1].target.name == "node-m"
    assert actions.bindings[2].metadata.name == "pod-z"
    assert actions.bindings[2].target.name == "node-z"


@pytest.mark.unit
def test_schedule_with_preemption(fixed_time: datetime):
    """Test schedule function with preemption enabled."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")

    # Create pods with different priorities
    high_priority_pending = create_test_pod("high-priority", "test-scheduler", priority=20)
    low_priority_running = create_test_pod("low-priority", "test-scheduler", "node-a", "Running", priority=5)
    medium_priority_pending = create_test_pod("medium-priority", "test-scheduler", priority=10)

    state = NodePodState(
        nodes=[node_a, node_b],
        pods=[high_priority_pending, low_priority_running, medium_priority_pending],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=True)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 1
    assert len(actions.bindings) == 2

    # Verify the low priority pod is evicted
    assert actions.evictions[0].metadata.name == "low-priority"
    assert actions.evictions[0].metadata.namespace == "test-namespace"

    # Verify both pending pods are bound
    assert actions.bindings[0].metadata.name == "high-priority"
    assert actions.bindings[0].target.name == "node-b"  # Gets the node from the evicted pod
    assert actions.bindings[1].metadata.name == "medium-priority"
    assert actions.bindings[1].target.name == "node-a"


@pytest.mark.unit
def test_schedule_with_preemption_no_effect(fixed_time: datetime):
    """Test schedule function with preemption enabled but no preemption possible."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")

    # Create pods with different priorities
    low_priority_pending = create_test_pod("low-priority", "test-scheduler", priority=5)
    high_priority_running = create_test_pod("high-priority", "test-scheduler", "node-a", "Running", priority=20)
    medium_priority_pending = create_test_pod("medium-priority", "test-scheduler", priority=10)

    state = NodePodState(
        nodes=[node_a, node_b],
        pods=[low_priority_pending, high_priority_running, medium_priority_pending],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=True)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0  # No evictions because running pod has higher priority
    assert len(actions.bindings) == 1  # Only one binding because one node is occupied

    # Verify only the medium priority pod is bound
    assert actions.bindings[0].metadata.name == "medium-priority"
    assert actions.bindings[0].target.name == "node-b"


@pytest.mark.unit
def test_schedule_preempt_lowest_priority(fixed_time: datetime):
    """Test that when a high priority pod needs scheduling, the lowest priority running pod is evicted."""
    # Create two nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")

    # Create running pods with different priorities
    low_priority_running = create_test_pod("low-priority", "test-scheduler", "node-a", "Running", priority=5)
    medium_priority_running = create_test_pod("medium-priority", "test-scheduler", "node-b", "Running", priority=10)

    # Create a high priority pending pod that needs scheduling
    high_priority_pending = create_test_pod("high-priority", "test-scheduler", priority=20)

    state = NodePodState(
        nodes=[node_a, node_b],
        pods=[low_priority_running, medium_priority_running, high_priority_pending],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=True)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 1
    assert len(actions.bindings) == 1

    # Verify the low priority pod is evicted (not the medium priority one)
    assert actions.evictions[0].metadata.name == "low-priority"
    assert actions.evictions[0].metadata.namespace == "test-namespace"

    # Verify the high priority pod is bound to the node that had the low priority pod
    assert actions.bindings[0].metadata.name == "high-priority"
    assert actions.bindings[0].target.name == "node-a"


@pytest.mark.unit
def test_schedule_pod_groups(fixed_time: datetime):
    """Test schedule function with pod groups."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")
    node_c = create_test_node("node-c")

    # Create pods in different groups
    group1_pod1 = create_test_pod("group1-pod1", "test-scheduler", group_name="group1", priority=10)
    group1_pod2 = create_test_pod("group1-pod2", "test-scheduler", group_name="group1", priority=10)
    group2_pod1 = create_test_pod("group2-pod1", "test-scheduler", group_name="group2")
    single_pod = create_test_pod("single-pod", "test-scheduler", priority=5)  # No group name

    state = NodePodState(
        nodes=[node_a, node_b, node_c],
        pods=[group1_pod1, group1_pod2, group2_pod1, single_pod],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 3  # All pods should be scheduled

    # Verify group1 pods are scheduled together
    group1_bindings = [b for b in actions.bindings if b.metadata.name.startswith("group1-")]
    assert len(group1_bindings) == 2
    assert {b.target.name for b in group1_bindings} == {"node-a", "node-b"}  # Should be on different nodes

    # Verify single pod is scheduled
    single_binding = next(b for b in actions.bindings if b.metadata.name == "single-pod")
    assert single_binding.target.name == "node-c"


@pytest.mark.unit
def test_schedule_pod_groups_mixed_priorities(fixed_time: datetime):
    """Test schedule function with pod groups containing pods of different priorities."""
    # Create nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")
    node_c = create_test_node("node-c")

    # Create a group with mixed priorities
    high_priority_pod = create_test_pod("high-priority", "test-scheduler", priority=20, group_name="mixed-group")
    low_priority_pod = create_test_pod("low-priority", "test-scheduler", priority=5, group_name="mixed-group")
    medium_priority_pod = create_test_pod("medium-priority", "test-scheduler", priority=10, group_name="mixed-group")

    # Create some running pods
    running_pod1 = create_test_pod("running1", "test-scheduler", "node-a", "Running", priority=15)
    running_pod2 = create_test_pod("running2", "test-scheduler", "node-b", "Running", priority=8)

    state = NodePodState(
        nodes=[node_a, node_b, node_c],
        pods=[high_priority_pod, low_priority_pod, medium_priority_pod, running_pod1, running_pod2],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=True)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 2  # Both running pods should be evicted
    assert len(actions.bindings) == 3  # All group pods should be scheduled

    # Verify all group pods are scheduled (group max priority is 20)
    group_bindings = [
        b for b in actions.bindings if b.metadata.name in ["high-priority", "low-priority", "medium-priority"]
    ]
    assert len(group_bindings) == 3
    assert {b.target.name for b in group_bindings} == {"node-a", "node-b", "node-c"}

    # Verify running pods are evicted
    evicted_names = {e.metadata.name for e in actions.evictions}
    assert evicted_names == {"running1", "running2"}


@pytest.mark.unit
def test_schedule_pod_groups_insufficient_nodes(fixed_time: datetime):
    """Test schedule function when there aren't enough nodes for a pod group."""
    # Create only two nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")

    # Create a group of three pods
    group_pod1 = create_test_pod("group-pod1", "test-scheduler", group_name="large-group")
    group_pod2 = create_test_pod("group-pod2", "test-scheduler", group_name="large-group")
    group_pod3 = create_test_pod("group-pod3", "test-scheduler", group_name="large-group")

    # Create a single pod that should be scheduled
    single_pod = create_test_pod("single-pod", "test-scheduler")

    state = NodePodState(
        nodes=[node_a, node_b],
        pods=[group_pod1, group_pod2, group_pod3, single_pod],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=False)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 1  # Only the single pod should be scheduled

    # Verify the single pod is scheduled
    assert actions.bindings[0].metadata.name == "single-pod"
    assert actions.bindings[0].target.name in {"node-a", "node-b"}

    # Verify no group pods are scheduled
    group_bindings = [b for b in actions.bindings if b.metadata.name.startswith("group-pod")]
    assert len(group_bindings) == 0


@pytest.mark.unit
def test_schedule_pod_groups_preempt_mixed_running(fixed_time: datetime):
    """Test schedule function with a group preempting both grouped and ungrouped running pods."""
    # Create three nodes
    node_a = create_test_node("node-a")
    node_b = create_test_node("node-b")
    node_c = create_test_node("node-c")

    # Create running pods - one ungrouped, one in group foo
    running_ungrouped = create_test_pod("running-ungrouped", "test-scheduler", "node-a", "Running", priority=10)
    running_grouped = create_test_pod(
        "running-grouped", "test-scheduler", "node-b", "Running", priority=5, group_name="foo"
    )

    # Create pending pods in group foo with higher priority
    pending_group1 = create_test_pod("pending-group1", "test-scheduler", priority=20, group_name="foo")
    pending_group2 = create_test_pod("pending-group2", "test-scheduler", priority=20, group_name="foo")

    state = NodePodState(
        nodes=[node_a, node_b, node_c],
        pods=[running_ungrouped, running_grouped, pending_group1, pending_group2],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state, preempt=True)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 1  # Both running pods should be evicted
    assert len(actions.bindings) == 2  # Both pending group pods should be scheduled

    assert actions.evictions[0].metadata.name == "running-ungrouped"

    # Verify both pending group pods are scheduled
    group_bindings = [b for b in actions.bindings if b.metadata.name.startswith("pending-group")]
    assert len(group_bindings) == 2
    assert {b.target.name for b in group_bindings} == {"node-a", "node-c"}  # Should take over the evicted pods' nodes
