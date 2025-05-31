from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from custom_scheduler.core import NodePodState
from kubernetes.client import V1Node, V1Pod


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
def test_node_pod_state_summary(mock_node: V1Node, mock_pod: V1Pod, fixed_time: datetime):
    """Test that summary method returns expected string format."""
    state = NodePodState(
        nodes=[mock_node, mock_node],  # Two nodes
        pods=[mock_pod, mock_pod, mock_pod],  # Three pods
        namespace="test-namespace",
        ts=fixed_time,
    )

    expected = f"State at {fixed_time.isoformat()}\n" "Namespace: test-namespace\n" "Nodes: 2\n" "Pods: 3"

    assert state.summary() == expected


@pytest.mark.unit
def test_node_pod_state_empty_state(fixed_time: datetime):
    """Test NodePodState with empty node and pod lists."""
    state = NodePodState(nodes=[], pods=[], namespace="empty-namespace", ts=fixed_time)

    expected = f"State at {fixed_time.isoformat()}\n" "Namespace: empty-namespace\n" "Nodes: 0\n" "Pods: 0"

    assert state.summary() == expected
