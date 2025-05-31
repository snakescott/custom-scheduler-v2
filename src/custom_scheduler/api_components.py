from datetime import UTC, datetime

from kubernetes.client import CoreV1Api, V1Node, V1Pod
from kubernetes.client.rest import ApiException

from custom_scheduler.core import NodePodState


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
        
        return NodePodState(
            nodes=nodes,
            pods=pods,
            namespace=namespace,
            ts=datetime.now(UTC)
        )
    except ApiException as e:
        # Re-raise with more context
        raise ApiException(
            status=e.status,
            reason=f"Failed to get state for namespace {namespace}: {e.reason}",
            http_resp=e.http_resp
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
    print(
        f"Scheduler {scheduler_name}, state:\n"
        f"{state.summary()}",
        flush=True
    ) 