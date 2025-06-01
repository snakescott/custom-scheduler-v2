from datetime import UTC, datetime

from kubernetes.client import CoreV1Api, V1Binding, V1Eviction, V1Node, V1Pod
from kubernetes.client.rest import ApiException

from custom_scheduler.core import NodePodState, schedule


def get_state(api: CoreV1Api, namespace: str) -> NodePodState:
    """
    Get the current state of nodes and pods in the specified namespace.

    Args:
        api: Kubernetes CoreV1Api instance
        namespace: The namespace to get state for

    Returns:
        NodePodState containing the current state of nodes and pods

    Raises:
        ApiException: If there's an error communicating with the Kubernetes API
    """
    try:
        # Get all nodes in the cluster
        nodes: list[V1Node] = api.list_node().items

        # Get all pods in the specified namespace
        pods: list[V1Pod] = api.list_namespaced_pod(namespace=namespace).items

        return NodePodState(nodes=nodes, pods=pods, namespace=namespace, ts=datetime.now(UTC))
    except ApiException as e:
        # Re-raise with more context
        raise ApiException(
            status=e.status, reason=f"Failed to get state for namespace {namespace}: {e.reason}", http_resp=e.http_resp
        ) from e


def bind(api: CoreV1Api, binding: V1Binding, namespace: str) -> None:
    """
    Bind a pod to a node using the Kubernetes API.

    Args:
        api: Kubernetes CoreV1Api instance
        binding: The binding to create
        namespace: The namespace containing the pod

    Raises:
        ApiException: If there's an error communicating with the Kubernetes API
    """
    try:
        api.create_namespaced_pod_binding(
            name=binding.metadata.name,
            namespace=namespace,
            body=binding,
        )
    except ApiException as e:
        raise ApiException(
            status=e.status,
            reason=f"Failed to bind pod {binding.metadata.name} to node {binding.target.name}: {e.reason}",
            http_resp=e.http_resp,
        ) from e


def evict(api: CoreV1Api, eviction: V1Eviction, namespace: str) -> None:
    """
    Evict a pod from a node using the Kubernetes API.

    Args:
        api: Kubernetes CoreV1Api instance
        eviction: The eviction to create
        namespace: The namespace containing the pod

    Raises:
        ApiException: If there's an error communicating with the Kubernetes API
    """
    try:
        api.create_namespaced_pod_eviction(
            name=eviction.metadata.name,
            namespace=namespace,
            body=eviction,
        )
    except ApiException as e:
        raise ApiException(
            status=e.status,
            reason=f"Failed to evict pod {eviction.metadata.name}: {e.reason}",
            http_resp=e.http_resp,
        ) from e


def execute_scheduling_loop(
    scheduler_name: str,
    namespace: str,
    api: CoreV1Api,
) -> None:
    """
    Execute one iteration of the scheduling loop, printing the current state.

    Args:
        scheduler_name: Name of the scheduler
        namespace: Kubernetes namespace to monitor
        api: Kubernetes CoreV1Api instance
    """
    state = get_state(api, namespace)
    print(f"At {state.ts}, {scheduler_name} processing {len(state.pods)} pods and {len(state.nodes)} nodes")
    actions = schedule(scheduler_name, state)
    print(f"Performing {len(actions.bindings)} bindings and {len(actions.evictions)} evictions")

    for eviction in actions.evictions:
        print(f"Evicting pod {eviction.metadata.name}")
        evict(api, eviction, namespace)

    for binding in actions.bindings:
        print(f"Binding pod {binding.metadata.name} to node {binding.target.name}")
        bind(api, binding, namespace)
