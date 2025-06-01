from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from kubernetes.client import V1Node, V1NodeSpec, V1Pod, V1PodSpec, V1PodStatus

from custom_scheduler.core import NodePodState, SchedulingActions, get_pods_to_preempt, schedule


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
) -> V1Pod:
    """Create a test pod with the given properties."""
    pod = Mock(spec=V1Pod)
    pod.metadata.name = name
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
def test_get_pods_to_preempt_no_preemption_needed():
    """Test get_pods_to_preempt when no preemption is needed."""
    # Create pods with different priorities
    pending_pods = [
        create_test_pod("high-priority", priority=10),
        create_test_pod("low-priority", priority=5),
    ]
    running_pods = [
        create_test_pod("running-1", priority=1, node_name="node-1", phase="Running"),
        create_test_pod("running-2", priority=2, node_name="node-2", phase="Running"),
    ]

    # With 2 available nodes, no preemption needed
    pods_to_preempt = get_pods_to_preempt(pending_pods, running_pods, num_available_nodes=2)
    assert len(pods_to_preempt) == 0


@pytest.mark.unit
def test_get_pods_to_preempt_with_preemption():
    """Test get_pods_to_preempt when preemption is needed."""
    # Create pods with different priorities
    pending_pods = [
        create_test_pod("very-high", priority=20),
        create_test_pod("high", priority=15),
        create_test_pod("medium", priority=10),
    ]
    running_pods = [
        create_test_pod("low-1", priority=5, node_name="node-1", phase="Running"),
        create_test_pod("low-2", priority=1, node_name="node-2", phase="Running"),
    ]

    # With only 1 available node, need to preempt
    pods_to_preempt = get_pods_to_preempt(pending_pods, running_pods, num_available_nodes=1)
    assert len(pods_to_preempt) == 2
    assert pods_to_preempt[0].metadata.name == "low-1"  # Should preempt the lowest priority running pod
    assert pods_to_preempt[1].metadata.name == "low-2"  # Should preempt the lowest priority running pod


@pytest.mark.unit
def test_get_pods_to_preempt_no_preemption_possible():
    """Test get_pods_to_preempt when preemption is needed but not possible."""
    # Create pods with different priorities
    pending_pods = [
        create_test_pod("medium-1", priority=10),
        create_test_pod("medium-2", priority=10),
    ]
    running_pods = [
        create_test_pod("high-1", priority=20, node_name="node-1", phase="Running"),
        create_test_pod("high-2", priority=15, node_name="node-2", phase="Running"),
    ]

    # With no available nodes, but can't preempt because running pods have higher priority
    pods_to_preempt = get_pods_to_preempt(pending_pods, running_pods, num_available_nodes=0)
    assert len(pods_to_preempt) == 0


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
    assert actions.bindings[0].target.name == "node-a"  # Gets the node from the evicted pod
    assert actions.bindings[1].metadata.name == "medium-priority"
    assert actions.bindings[1].target.name == "node-b"


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
