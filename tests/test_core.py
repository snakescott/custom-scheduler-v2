from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from kubernetes.client import V1Node, V1NodeSpec, V1Pod, V1PodSpec, V1PodStatus

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
) -> V1Pod:
    """Create a test pod with the given properties."""
    pod = Mock(spec=V1Pod)
    pod.metadata.name = name
    pod.spec = Mock(spec=V1PodSpec)
    pod.spec.scheduler_name = scheduler_name
    pod.spec.node_name = node_name
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
    actions = schedule("test-scheduler", state)

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
    pod2 = create_test_pod("pod2", "test-scheduler")  # Should be scheduled
    pod3 = create_test_pod("pod3", "other-scheduler")  # Should not be scheduled
    pod4 = create_test_pod("pod4", None)  # Should not be scheduled
    pod5 = create_test_pod("pod5", "test-scheduler", "node-a", "Running")  # Already running

    state = NodePodState(
        nodes=[node_a, node_b, node_c],
        pods=[pod1, pod2, pod3, pod4, pod5],
        namespace="test-namespace",
        ts=fixed_time,
    )

    actions = schedule("test-scheduler", state)

    assert isinstance(actions, SchedulingActions)
    assert len(actions.evictions) == 0
    assert len(actions.bindings) == 2

    binding = actions.bindings[0]
    assert binding.metadata.name == "pod1"
    assert binding.target.name == "node-b"

    binding = actions.bindings[1]
    assert binding.metadata.name == "pod2"
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

    actions = schedule("test-scheduler", state)

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

    actions = schedule("test-scheduler", state)

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
