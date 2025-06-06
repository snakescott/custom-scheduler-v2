from datetime import UTC, datetime

from kubernetes.client import CoreV1Api, V1Binding, V1Eviction, V1Node, V1Pod

from custom_scheduler.core import NodePodState, schedule


def get_state(api: CoreV1Api, namespace: str) -> NodePodState:
    """
    Get the current state of nodes and pods in the specified namespace.

    Args:
        api: Kubernetes CoreV1Api instance
        namespace: The namespace to get state for

    Returns:
        NodePodState containing the current state of nodes and pods
    """
    # Get all nodes in the cluster
    nodes: list[V1Node] = api.list_node().items

    # Get all pods in the specified namespace
    pods: list[V1Pod] = api.list_namespaced_pod(namespace=namespace).items

    return NodePodState(nodes=nodes, pods=pods, namespace=namespace, ts=datetime.now(UTC))


def bind(api: CoreV1Api, binding: V1Binding, namespace: str) -> None:
    """
    Bind a pod to a node using the Kubernetes API.

    Args:
        api: Kubernetes CoreV1Api instance
        binding: The binding to create
        namespace: The namespace containing the pod

    """
    api.create_namespaced_pod_binding(
        name=binding.metadata.name,
        namespace=namespace,
        body=binding,
        # https://github.com/kubernetes-client/python/issues/825#issuecomment-613863221
        _preload_content=False,
    )


def evict(api: CoreV1Api, eviction: V1Eviction, namespace: str) -> None:
    """
    Evict a pod from a node using the Kubernetes API.

    Args:
        api: Kubernetes CoreV1Api instance
        eviction: The eviction to create
        namespace: The namespace containing the pod
    """
    api.create_namespaced_pod_eviction(
        name=eviction.metadata.name,
        namespace=namespace,
        body=eviction,
    )


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
    actions = schedule(scheduler_name, state)

    if actions.bindings or actions.evictions:
        print(f"At {state.ts}, {scheduler_name} processing {len(state.pods)} pods and {len(state.nodes)} nodes")
        print(f"Performing {len(actions.bindings)} bindings and {len(actions.evictions)} evictions")

    for eviction in actions.evictions:
        print(f"Evicting pod {eviction.metadata.name}")
        evict(api, eviction, namespace)

    for binding in actions.bindings:
        print(f"Binding pod {binding.metadata.name} to node {binding.target.name}")
        bind(api, binding, namespace)
