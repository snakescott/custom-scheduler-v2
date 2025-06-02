from kubernetes.client import (
    V1Binding,
    V1DeleteOptions,
    V1Eviction,
    V1ObjectMeta,
    V1ObjectReference,
    V1Pod,
)

GROUP_NAME_ANNOTATION = "custom-scheduling.k8s.io/group-name"
MIN_AVAILABLE_ANNOTATION = "custom-scheduling.k8s.io/min-available"
AVAILABLE_NODE_PRIORITY = -2147483649


def is_pending(pod: V1Pod) -> bool:
    return pod.status and pod.status.phase == "Pending"


def is_running(pod: V1Pod) -> bool:
    return pod.status and pod.status.phase == "Running" and pod.spec and pod.spec.node_name is not None


def create_binding(pod_name: str, node_name: str) -> V1Binding:
    target = V1ObjectReference(kind="Node", api_version="v1", name=node_name)
    meta = V1ObjectMeta(name=pod_name)
    return V1Binding(metadata=meta, target=target)


def create_eviction(namespace: str, pod_name: str) -> V1Eviction:
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
    return pod.spec.priority if pod.spec and hasattr(pod.spec, "priority") else 0


def get_annotation(pod: V1Pod, key: str, default: str = "") -> str:
    if not pod.metadata or not pod.metadata.annotations:
        return default
    return pod.metadata.annotations.get(key, default)


def get_min_available(pod: V1Pod) -> int:
    try:
        return int(get_annotation(pod, MIN_AVAILABLE_ANNOTATION, "1"))
    except ValueError:
        return 1


def get_group_name(pod: V1Pod) -> int:
    return get_annotation(pod, GROUP_NAME_ANNOTATION)
